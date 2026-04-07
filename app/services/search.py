"""Azure AI Search integration.

Provides:
- ``upsert_chunks``: batch upsert chunk documents into the index.
- ``hybrid_search``: keyword + vector hybrid retrieval filtered by dataset_id.
"""

from __future__ import annotations

from app.config import settings
from app.services.embeddings import embed_texts

_UPSERT_BATCH = 100


def _search_client():
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


async def upsert_chunks(chunks: list[dict]) -> None:
    """Upsert chunk documents into Azure AI Search in batches.

    Each chunk dict should have at minimum:
      id, dataset_id, doc_id, chunk_id, content, contentVector,
      source_name, page (optional), sheet (optional)
    """
    client = _search_client()
    for i in range(0, len(chunks), _UPSERT_BATCH):
        batch = chunks[i : i + _UPSERT_BATCH]
        client.upload_documents(documents=batch)


async def hybrid_search(
    dataset_id: str,
    query: str,
    top_k: int = 8,
) -> list[dict]:
    """Run hybrid (keyword + vector) search filtered to a dataset.

    Returns a list of result dicts with keys:
      chunk_id, content, source_name, page, sheet, score
    """
    from azure.search.documents.models import VectorizedQuery

    # Embed the query
    vectors = await embed_texts([query])
    query_vector = vectors[0] if vectors else []

    client = _search_client()
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="contentVector",
    )

    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        filter=f"dataset_id eq '{dataset_id}'",
        select=["chunk_id", "content", "source_name", "page", "sheet"],
        top=top_k,
    )

    hits = []
    for r in results:
        hits.append(
            {
                "chunk_id": r.get("chunk_id", ""),
                "content": r.get("content", ""),
                "source_name": r.get("source_name", ""),
                "page": r.get("page"),
                "sheet": r.get("sheet"),
                "score": r.get("@search.score", 0.0),
            }
        )
    return hits
