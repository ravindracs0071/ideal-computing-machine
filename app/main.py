"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import chat, datasets, documents, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Document Processing Pipeline",
    description=(
        "End-to-end document ingestion, embedding, and RAG chat service "
        "powered by FastAPI, Azure AI Search, and LiteLLM."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(datasets.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(chat.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
