from __future__ import annotations

import logging

from app.ingest import enrich as ingest_enrich
from app.rag import retrieval
from app.rag.llm import compose_answer
from app.runtime import fresh_news
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


SOURCE_BY_TOPIC = {
    "javascript": "Next.js Blog",
    "nextjs": "Next.js Blog",
    "python": "Python Docs",
    "github": "GitHub Changelog",
}


def _build_where(topics: list[str]) -> dict | None:
    for t in topics:
        src = SOURCE_BY_TOPIC.get(t.lower())
        if src:
            return {"source": {"$eq": src}}
    return None


async def handle_chat(req: ChatRequest) -> ChatResponse:
    query = _expand_query(req.question, req.topics)

    where = _build_where(req.topics)
    retrieved = retrieval.retrieve(query, k=8, where=where)

    try:
        enriched = ingest_enrich.enrich_retrieval(retrieved)
    except NotImplementedError:
        enriched = []
    if enriched:
        retrieved = retrieved + enriched

    try:
        fresh = await fresh_news.fetch(topics=req.topics, since=None)
    except NotImplementedError:
        fresh = []

    return await compose_answer(
        question=req.question,
        topics=req.topics,
        retrieved_chunks=retrieved,
        fresh_articles=fresh,
    )


def _expand_query(question: str, topics: list[str]) -> str:
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"
