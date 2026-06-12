from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/search/repositories"

def _extract_topics(retrieved: list[dict[str, Any]]) -> list[str]:
    topics: set[str] = set()
    for chunk in retrieved:
        meta = chunk.get("metadata") or {}
        tags = meta.get("tags") or ""
        for tag in tags.split(","):
            tag = tag.strip().lower()
            if tag:
                topics.add(tag)
    return list(topics)[:3]

def _search_github(topic: str) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            GITHUB_API,
            params={
                "q": topic,
                "sort": "stars",
                "order": "desc",
                "per_page": 3,
            },
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("GitHub API échouée (topic=%s): %s", topic, exc)
        return []

    results = []
    for repo in data.get("items") or []:
        updated = repo.get("updated_at") or ""
        date = updated[:10] if updated else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = (
            f"{repo.get('description') or ''} "
            f"⭐ {repo.get('stargazers_count', 0)} étoiles. "
            f"Dernière mise à jour : {date}."
        )
        results.append({
            "content": content,
            "metadata": {
                "title":  repo.get("full_name", ""),
                "source": "GitHub",
                "date":   date,
                "url":    repo.get("html_url", ""),
                "tags":   topic,
            },
        })

    logger.info("GitHub: %d repos pour '%s'", len(results), topic)
    return results


def enrich_retrieval(retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not retrieved:
        return []

    topics = _extract_topics(retrieved)
    if not topics:
        logger.info("enrich: aucun topic extrait — enrichissement ignoré")
        return []

    enriched: list[dict[str, Any]] = []
    for topic in topics:
        enriched.extend(_search_github(topic))

    logger.info("enrich: %d repos GitHub ajoutés au contexte", len(enriched))
    return enriched

    