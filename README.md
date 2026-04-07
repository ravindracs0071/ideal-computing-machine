# Document Processing Pipeline

An end-to-end document ingestion, embedding, and RAG chat service built with:

- **FastAPI** – REST API + SSE streaming
- **RQ + Redis** – async background ingestion jobs
- **Azure AI Search** – hybrid (keyword + vector) retrieval
- **LiteLLM** – OpenAI-compatible gateway to Azure AI Foundry Claude models
- **SQLAlchemy 2.0 + SQLite** – lightweight metadata storage (swap for Postgres in production)
- **pypdf / PyMuPDF / pytesseract** – PDF text + OCR fallback
- **python-docx / pandas** – DOCX and Excel extraction

---

## Supported document types

| Extension | Extraction method |
|-----------|-------------------|
| `.md`, `.txt` | UTF-8 decode |
| `.pdf` | pypdf text; PyMuPDF + Tesseract OCR fallback |
| `.docx`, `.doc` | python-docx |
| `.xlsx`, `.xls` | pandas / openpyxl (per-sheet) |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.gif`, `.webp` | pytesseract OCR |

---

## Setup

### 1. Prerequisites

- Python 3.11+
- [Docker](https://docs.docker.com/get-docker/) (for Redis)
- [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html) installed on the host
- An Azure AI Search service
- A LiteLLM gateway (or Azure AI Foundry endpoint) with a chat model and an embedding model

### 2. Clone and install dependencies

```bash
git clone https://github.com/ravindracs0071/ideal-computing-machine.git
cd ideal-computing-machine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Key variables:

| Variable | Description |
|----------|-------------|
| `APP_DB_URL` | SQLAlchemy async DB URL (default: SQLite) |
| `REDIS_URL` | Redis connection URL |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint |
| `AZURE_SEARCH_API_KEY` | Azure AI Search admin key |
| `AZURE_SEARCH_INDEX` | Search index name |
| `LITELLM_BASE_URL` | LiteLLM gateway base URL |
| `LITELLM_API_KEY` | LiteLLM API key |
| `LITELLM_CHAT_MODEL` | Model name for chat completions |
| `LITELLM_EMBED_MODEL` | Model name for embeddings |
| `EMBEDDING_DIMENSIONS` | Vector dimensions (must match the model) |
| `CHUNK_SIZE` | Characters per chunk (default: 1000) |
| `CHUNK_OVERLAP` | Overlap characters (default: 150) |
| `MAX_UPLOAD_MB` | Max upload size in MB (default: 50) |

### 4. Start Redis

```bash
docker-compose up -d redis
```

### 5. Create the Azure AI Search index

```bash
python scripts/create_search_index.py
```

This reads `infra/azure_search/index.json` and creates/updates the index using `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, and `AZURE_SEARCH_INDEX` from your environment.

> **Note:** If your embedding model has a different dimension than 3072, set `EMBEDDING_DIMENSIONS` in your `.env` before running this script.

### 6. Run the API server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 7. Run the RQ worker

In a separate terminal (with the same `.env` loaded):

```bash
rq worker --url $REDIS_URL
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/datasets` | Create a new dataset |
| `GET` | `/datasets` | List all datasets |
| `GET` | `/datasets/{dataset_id}` | Get a dataset |
| `POST` | `/datasets/{dataset_id}/documents` | Upload documents (returns 202 + job_id) |
| `GET` | `/jobs/{job_id}` | Get ingestion job status/progress |
| `POST` | `/chat` | Non-streaming RAG chat |
| `POST` | `/chat/stream` | SSE streaming RAG chat |
| `GET` | `/health` | Health check |

---

## Example curl commands

### Create a dataset

```bash
curl -s -X POST http://localhost:8000/datasets \
  -H "Content-Type: application/json" \
  -d '{"name": "My Documents"}' | jq .
```

### Upload documents

```bash
curl -s -X POST "http://localhost:8000/datasets/<dataset_id>/documents" \
  -F "files=@/path/to/document.pdf" \
  -F "files=@/path/to/spreadsheet.xlsx" | jq .
```

### Poll job status

```bash
curl -s "http://localhost:8000/jobs/<job_id>" | jq .
```

### Chat (non-streaming)

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "<dataset_id>",
    "message": "What is the vacation policy?",
    "top_k": 8
  }' | jq .
```

### Chat (SSE streaming)

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "<dataset_id>",
    "message": "Summarize the key points",
    "top_k": 8
  }'
```

---

## Running tests

```bash
pytest tests/ -v
```

---

## Project structure

```
.
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── config.py            # Pydantic settings
│   ├── database.py          # SQLAlchemy async engine + session
│   ├── models.py            # ORM models (Dataset, Document, IngestJob)
│   ├── routers/
│   │   ├── datasets.py      # POST/GET /datasets
│   │   ├── documents.py     # POST /datasets/{id}/documents
│   │   ├── jobs.py          # GET /jobs/{id}
│   │   └── chat.py          # POST /chat, POST /chat/stream
│   ├── services/
│   │   ├── extraction.py    # Document text extraction
│   │   ├── chunking.py      # Text chunking
│   │   ├── embeddings.py    # LiteLLM embeddings
│   │   └── search.py        # Azure AI Search upsert + hybrid retrieval
│   └── worker/
│       └── tasks.py         # RQ worker task (ingest pipeline)
├── infra/
│   └── azure_search/
│       └── index.json       # Azure AI Search index schema
├── scripts/
│   └── create_search_index.py
├── tests/
│   ├── test_chunking.py
│   └── test_extraction.py
├── docker-compose.yml       # Redis service
├── requirements.txt
└── .env.example
```

---

## Ingestion pipeline stages

Each uploaded document goes through the following stages tracked in the job record:

1. **extract** – text/OCR extraction per document
2. **chunk** – split text into overlapping windows
3. **embed** – call LiteLLM embedding endpoint (batched, 32 at a time)
4. **index** – upsert chunks into Azure AI Search
5. **done** – job marked succeeded or failed

---

## RAG prompt design

The system prompt enforces:
- Answer **only** from the retrieved context chunks
- Cite sources by `chunk_id` and `source` filename
- If the answer is not in the context, say so explicitly (no hallucination)
