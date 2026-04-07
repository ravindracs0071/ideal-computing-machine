"""Chat router – POST /chat (non-streaming) and POST /chat/stream (SSE)."""

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Dataset
from app.services.search import hybrid_search
from openai import AsyncOpenAI

router = APIRouter(tags=["chat"])

RAG_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question using ONLY "
    "the context chunks provided below. Do NOT use any outside knowledge. "
    "If the answer is not found in the context, respond with: "
    "'I could not find an answer in the provided documents.' "
    "Always cite sources using the chunk_id and source filename."
)


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        meta = f"[chunk_id={c['chunk_id']}, source={c['source_name']}"
        if c.get("page"):
            meta += f", page={c['page']}"
        if c.get("sheet"):
            meta += f", sheet={c['sheet']}"
        meta += "]"
        parts.append(f"{meta}\n{c['content']}")
    return "\n\n---\n\n".join(parts)


def _get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.litellm_base_url or None,
        api_key=settings.litellm_api_key or "placeholder",
    )


class ChatRequest(BaseModel):
    dataset_id: str
    message: str
    top_k: int = 8


class Citation(BaseModel):
    chunk_id: str
    source: str
    page: int | None = None
    sheet: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    ds = await db.get(Dataset, body.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    chunks = await hybrid_search(body.dataset_id, body.message, body.top_k)
    if not chunks:
        return ChatResponse(
            answer="I could not find an answer in the provided documents.",
            citations=[],
        )

    context = _build_context(chunks)
    user_message = f"Context:\n\n{context}\n\nQuestion: {body.message}"

    client = _get_openai_client()
    response = await client.chat.completions.create(
        model=settings.litellm_chat_model,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    answer = response.choices[0].message.content or ""
    citations = [
        Citation(
            chunk_id=c["chunk_id"],
            source=c["source_name"],
            page=c.get("page"),
            sheet=c.get("sheet"),
        )
        for c in chunks
    ]
    return ChatResponse(answer=answer, citations=citations)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    ds = await db.get(Dataset, body.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    chunks = await hybrid_search(body.dataset_id, body.message, body.top_k)
    context = _build_context(chunks) if chunks else "(no context found)"
    user_message = f"Context:\n\n{context}\n\nQuestion: {body.message}"
    citations = [
        Citation(
            chunk_id=c["chunk_id"],
            source=c["source_name"],
            page=c.get("page"),
            sheet=c.get("sheet"),
        )
        for c in chunks
    ]

    async def event_generator() -> AsyncIterator[str]:
        client = _get_openai_client()
        stream = await client.chat.completions.create(
            model=settings.litellm_chat_model,
            messages=[
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                payload = json.dumps({"token": delta})
                yield f"event: token\ndata: {payload}\n\n"

        citations_payload = json.dumps(
            [c.model_dump(exclude_none=True) for c in citations]
        )
        yield f"event: citations\ndata: {citations_payload}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
