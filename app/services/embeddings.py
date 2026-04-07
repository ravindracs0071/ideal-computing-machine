"""Embeddings service using LiteLLM / OpenAI-compatible endpoint."""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from app.config import settings

_BATCH_SIZE = 32


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.litellm_base_url or None,
        api_key=settings.litellm_api_key or "placeholder",
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of texts.

    Sends requests in batches of up to *_BATCH_SIZE* texts.
    """
    if not texts:
        return []

    client = _client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.litellm_embed_model,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
