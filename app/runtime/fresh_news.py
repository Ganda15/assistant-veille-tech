from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import requests

from app.config import get_settings
from app.utils import normalize_date

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


def _fetch_live(topic: str, since: datetime | None) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.news_api_key:
        logger.warning("NEWS_API_KEY absent — fresh_news ignorée")
        return []

    params: dict[str, Any] = {
        "q": topic,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
        "apiKey": settings.news_api_key,
    }
    if since:
        params["from"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = requests.get(
            f"{settings.news_api_base_url}/everything",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("fresh_news NewsAPI échouée (topic=%s): %s", topic, exc)
        return []

    articles = []
    for raw in data.get("articles") or []:
        url = (raw.get("url") or "").strip()
        if not url or url == "https://removed.com":
            continue

        content = (raw.get("content") or raw.get("description") or "").strip()
        if "[+" in content:
            content = content[: content.rfind("[+")].strip()

        articles.append({
            "title":   (raw.get("title") or "Sans titre").strip(),
            "source":  (raw.get("source") or {}).get("name") or "NewsAPI",
            "date":    normalize_date(raw.get("publishedAt")),
            "content": content or (raw.get("title") or ""),
            "url":     url,
            "tags":    [topic],
        })

    logger.info("fresh_news: %d articles pour '%s'", len(articles), topic)
    return articles

async def fetch(
    topics: list[str],
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    all_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for topic in topics:
        batch = await asyncio.to_thread(_fetch_live, topic, since)
        for art in batch:
            if art["url"] not in seen_urls:
                seen_urls.add(art["url"])
                all_articles.append(art)

    logger.info("fresh_news total: %d articles uniques", len(all_articles))
    return all_articles

    