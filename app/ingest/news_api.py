from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.ingest.cleaning import clean_html_to_markdown, chunk, dedupe
from app.rag.chroma_client import get_collection
from app.rag.retrieval import embed
from app.schemas import Article
from app.utils import chunk_id, normalize_date

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


def _parse_article(raw: dict[str, Any], topics: list[str]) -> Article | None:
    url = (raw.get("url") or "").strip()
    if not url or url == "https://removed.com":
        return None

    title = (raw.get("title") or "").strip()
    source_name = (raw.get("source") or {}).get("name") or "NewsAPI"
    date_str = normalize_date(raw.get("publishedAt"))

    content = (raw.get("content") or raw.get("description") or "").strip()
    if "[+" in content:
        content = content[: content.rfind("[+")].strip()

    try:
        return Article(
            id=hashlib.sha1(url.encode()).hexdigest()[:8],
            title=title or "Sans titre",
            source=source_name,
            date=datetime.fromisoformat(date_str) if date_str else None,
            content=content or title,
            url=url,
            tags=topics,
        )
    except (ValidationError, ValueError) as exc:
        logger.debug("Article invalide ignoré (%s): %s", url, exc)
        return None



def _upsert_chunks(articles: list[Article]) -> int:
    collection = get_collection()
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ids: list[str] = []
    docs: list[str] = []
    embeddings: list[list[float]] = []
    metas: list[dict[str, Any]] = []

    for article in articles:
        markdown = clean_html_to_markdown(article.content)
        pieces = chunk(markdown) or [article.content[:1200]]

        date_str = article.date.strftime("%Y-%m-%d") if article.date else ""
        url_str = str(article.url)
        tags_str = ", ".join(article.tags)

        for i, piece in enumerate(pieces):
            ids.append(chunk_id(url_str, i))
            docs.append(piece)
            embeddings.append(embed(piece))
            metas.append({
                "title": article.title,
                "source": article.source,
                "date": date_str,
                "url": url_str,
                "tags": tags_str,
                "collected_at": collected_at,
                "chunk_index": i,
            })

    if ids:
        collection.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
        logger.info("Upsert : %d chunks depuis %d articles", len(ids), len(articles))

    return len(ids)
@dataclass
class NewsApiIngester:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_settings()

    def _fetch_topic(self, topic: str) -> list[dict[str, Any]]:
        if not self.settings.news_api_key:
            logger.warning("NEWS_API_KEY absent — NewsAPI ignorée")
            return []

        articles: list[dict[str, Any]] = []
        page = 1

        while True:
            try:
                resp = requests.get(
                    f"{self.settings.news_api_base_url}/everything",
                    params={
                        "q": topic,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": PAGE_SIZE,
                        "page": page,
                        "apiKey": self.settings.news_api_key,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("NewsAPI échouée (topic=%s page=%d): %s", topic, page, exc)
                break

            batch = data.get("articles") or []
            articles.extend(batch)

            total = data.get("totalResults", 0)
            if not batch or len(articles) >= total or len(batch) < PAGE_SIZE or page >= 5:
                break
            page += 1

        logger.info("NewsAPI: %d articles pour '%s'", len(articles), topic)
        return articles

    def run(self, topics: list[str]) -> list[dict[str, Any]]:
        raw_all: list[dict[str, Any]] = []

        for topic in topics:
            raw_all.extend(self._fetch_topic(topic))

        raw_unique = dedupe(raw_all)
        logger.info("Après dédup: %d articles uniques sur %d bruts", len(raw_unique), len(raw_all))

        articles = [
            a
            for raw in raw_unique
            if (a := _parse_article(raw, topics)) is not None
        ]
        logger.info("%d articles valides à indexer", len(articles))
        

        _upsert_chunks(articles)

        return [a.model_dump(mode="json") for a in articles]