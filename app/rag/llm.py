from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.schemas import ArticleCard, ChatResponse

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Tu es l'assistant de veille technologique interne de Nauda Palisse.\n"
    "Réponds en français, factuel, concis. Cite tes sources via les cartes d'articles.\n"
    "Si aucun article n'est fourni, dis-le poliment et ne fabrique rien.\n"
    "Format de sortie attendu : JSON strict avec les clés `answer` (string) "
    "et `cards` (liste d'objets {title, source, date, snippet, url, tags})."
)


@lru_cache(maxsize=1)
def get_llm():
    settings = get_settings()

    # Essai 1 — Azure
    if settings.azure_ai_inference_endpoint and settings.azure_ai_inference_api_key:
        try:
            return AzureAIChatCompletionsModel(
                endpoint=settings.azure_ai_inference_endpoint,
                credential=settings.azure_ai_inference_api_key,
                model=settings.azure_ai_inference_model,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("Azure LLM indisponible : %s — fallback Groq", exc)

    # Essai 2 — Groq
    if settings.groq_api_key:
        from langchain_groq import ChatGroq
        logger.info("Utilisation de Groq comme LLM")
        return ChatGroq(
            api_key=settings.groq_api_key,
            model="llama-3.1-8b-instant",
            temperature=0.2,
        )

    logger.info("Aucun LLM configuré — mode dégradé")
    return None


def _format_context(retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if retrieved:
        parts.append("## Index interne")
        for i, chunk in enumerate(retrieved, 1):
            meta = chunk.get("metadata") or {}
            parts.append(
                f"[{i}] {meta.get('title', '')} — {meta.get('source', '')} "
                f"({meta.get('date', '')})\n{chunk.get('content', '')[:600]}"
            )
    if fresh:
        parts.append("## Actualité fraîche")
        for i, art in enumerate(fresh, 1):
            parts.append(
                f"[F{i}] {art.get('title', '')} — {art.get('source', '')} "
                f"({art.get('date', '')})\n{art.get('content', '')[:600]}\n{art.get('url', '')}"
            )
    return "\n\n".join(parts) if parts else "(aucune source disponible)"


def _build_cards(
    retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[ArticleCard]:
    cards: list[ArticleCard] = []
    for chunk in retrieved:
        meta = chunk.get("metadata") or {}
        snippet = (chunk.get("content") or "")[:280]
        cards.append(
            ArticleCard(
                title=meta.get("title", "Sans titre"),
                source=meta.get("source", "interne"),
                date=meta.get("date"),
                snippet=snippet,
                url=meta.get("url", ""),
                tags=_split_tags(meta.get("tags")),
            )
        )
    for art in fresh:
        cards.append(
            ArticleCard(
                title=art.get("title", "Sans titre"),
                source=art.get("source", "newsapi"),
                date=art.get("date"),
                snippet=(art.get("content") or art.get("description") or "")[:280],
                url=art.get("url", ""),
                tags=art.get("tags", []),
            )
        )
    return cards


def _split_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


async def compose_answer(
    *,
    question: str,
    topics: list[str],
    retrieved_chunks: list[dict[str, Any]],
    fresh_articles: list[dict[str, Any]],
) -> ChatResponse:
    cards = _build_cards(retrieved_chunks, fresh_articles)

    if not retrieved_chunks and not fresh_articles:
        return ChatResponse(
            answer=(
                "Aucun article ne couvre encore ce sujet dans l'index ou dans "
                "l'actualité collectée. Lance une ingestion pour alimenter la veille."
            ),
            cards=[],
            status="empty",
        )

    llm = get_llm()
    if llm is None:
        return ChatResponse(
            answer=(
                f"{len(cards)} article(s) trouvé(s) pour : {question}. "
                "LLM non configuré — voici les sources brutes."
            ),
            cards=cards,
            status="degraded",
        )

    user_payload = {
        "question": question,
        "topics": topics,
        "context": _format_context(retrieved_chunks, fresh_articles),
    }

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
    ]

    try:
        msg = await llm.ainvoke(messages)
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        answer = _extract_answer(raw)
    except Exception as exc:
        logger.warning("LLM call failed (%s) — trying Groq fallback", exc)
        # Fallback Groq
        try:
            settings = get_settings()
            if settings.groq_api_key:
                from langchain_groq import ChatGroq
                groq_llm = ChatGroq(
                    api_key=settings.groq_api_key,
                    model="llama-3.1-8b-instant",
                    temperature=0.2,
                )
                msg = await groq_llm.ainvoke(messages)
                raw = msg.content if isinstance(msg.content, str) else str(msg.content)
                answer = _extract_answer(raw)
                logger.info("Réponse générée via Groq fallback")
            else:
                raise exc
        except Exception as exc2:
            logger.warning("Groq fallback aussi échoué: %s", exc2)
            answer = f"Synthèse indisponible (erreur LLM). {len(cards)} article(s) référencé(s)."

    return ChatResponse(answer=answer, cards=cards, status="ok")


def _extract_answer(raw: str) -> str:
    # Supprime les balises markdown ```json ... ```
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[start:end]).strip()
    # Essai 1 — JSON complet
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "answer" in data:
            return str(data["answer"])
    except json.JSONDecodeError:
        pass
    # Essai 2 — Extrait juste le bloc JSON { ... }
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        data = json.loads(cleaned[start:end])
        if isinstance(data, dict) and "answer" in data:
            return str(data["answer"])
    except (ValueError, json.JSONDecodeError):
        pass
    return cleaned
