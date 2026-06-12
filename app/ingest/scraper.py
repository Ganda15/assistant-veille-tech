from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.ingest.cleaning import clean_html_to_markdown, chunk, dedupe
from app.rag.chroma_client import get_collection
from app.rag.retrieval import embed

logger = logging.getLogger(__name__)


SOURCES = [
    {
        "url": "https://github.blog/changelog/feed/",
        "source": "GitHub Changelog",
        "tags": ["github", "changelog"],
        "type": "rss",
    },
    {
        "url": "https://nextjs.org/feed.xml",
        "source": "Next.js Blog",
        "tags": ["nextjs", "javascript"],
        "type": "rss",
    },
    {
        "url": "https://docs.python.org/3/whatsnew/3.13.html",
        "source": "Python Docs",
        "tags": ["python", "docs"],
        "type": "html",
        "title": "What's New in Python 3.13",
    },
]



def _chunk_id(url: str, index: int) -> str:
    h = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{h}_{index}"


def _normalize_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


RAW_DIR = Path("/srv/data/raw")


def _save_raw(source_name: str, content: bytes, extension: str) -> None:
    """Persiste la donnée brute avant toute transformation (couche raw)."""
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = source_name.lower().replace(" ", "-").replace(".", "")
        path = RAW_DIR / f"{today}_{slug}.{extension}"
        path.write_bytes(content)
        logger.info("Raw sauvegardé : %s (%d octets)", path, len(content))
    except OSError as exc:
        logger.warning("Sauvegarde raw impossible (%s): %s", source_name, exc)



def _parse_rss_feed(source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            source["url"],
            timeout=15,
            headers={"User-Agent": "nauda-palisse-veille/0.1"},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("RSS échoué (%s): %s", source["url"], exc)
        return []

    _save_raw(source["source"], resp.content, "xml")

    soup = BeautifulSoup(resp.content, "lxml-xml")

    entries = soup.find_all("item") or soup.find_all("entry")

    articles = []
    for entry in entries:
        title_tag = entry.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Sans titre"

        link_tag = entry.find("link")
        url = ""
        if link_tag:
            url = link_tag.get("href") or link_tag.get_text(strip=True)

        content_tag = (
            entry.find("content:encoded")
            or entry.find("content")
            or entry.find("description")
        )
        content = content_tag.get_text(strip=True) if content_tag else ""

        pub_tag = (
            entry.find("pubDate")
            or entry.find("published")
            or entry.find("updated")
        )
        date = _normalize_date(pub_tag.get_text(strip=True) if pub_tag else "")

        if not url:
            continue

        articles.append({
            "title": title,
            "source": source["source"],
            "date": date,
            "url": url,
            "content": content or title,
            "tags": source["tags"],
        })

    logger.info("RSS %s : %d articles", source["source"], len(articles))
    return articles    



def _parse_html_page(source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            source["url"],
            timeout=15,
            headers={"User-Agent": "nauda-palisse-veille/0.1"},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("HTML échoué (%s): %s", source["url"], exc)
        return []

    _save_raw(source["source"], resp.content, "html")

    soup = BeautifulSoup(resp.content, "lxml")

    main = (
        soup.find("div", {"class": "body"})
        or soup.find("article")
        or soup.find("main")
        or soup.body
    )

    content = str(main) if main else ""
    title_tag = soup.find("title")
    title = source.get("title") or (title_tag.get_text(strip=True) if title_tag else "Sans titre")

    return [{
        "title": title,
        "source": source["source"],
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "url": source["url"],
        "content": content or title,
        "tags": source["tags"],
    }]



def _upsert_chunks(articles: list[dict[str, Any]]) -> int:
    collection = get_collection()
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ids: list[str] = []
    docs: list[str] = []
    embeddings: list[list[float]] = []
    metas: list[dict[str, Any]] = []

    for article in articles:
        markdown = clean_html_to_markdown(article["content"])
        pieces = chunk(markdown) or [article["content"][:1200]]

        tags_str = ", ".join(article.get("tags") or [])
        url_str = str(article["url"])

        for i, piece in enumerate(pieces):
            ids.append(_chunk_id(url_str, i))
            docs.append(piece)
            embeddings.append(embed(piece))
            metas.append({
                "title": article["title"],
                "source": article["source"],
                "date": article["date"],
                "url": url_str,
                "tags": tags_str,
                "collected_at": collected_at,
                "chunk_index": i,
            })

    if ids:
        collection.upsert(ids=ids, documents=docs,
                          embeddings=embeddings, metadatas=metas)
        logger.info("Upsert scraper : %d chunks depuis %d articles", len(ids), len(articles))

    return len(ids)



@dataclass
class Scraper:
    user_agent: str = "nauda-palisse-veille/0.1"
    timeout: float = 10.0

    def run(self, urls: list[str]) -> list[dict[str, Any]]:
        all_articles: list[dict[str, Any]] = []

        for source in SOURCES:
            if source["type"] == "rss":
                all_articles.extend(_parse_rss_feed(source))
            else:
                all_articles.extend(_parse_html_page(source))

        unique = dedupe(all_articles)
        logger.info("Scraper: %d articles uniques", len(unique))

        _upsert_chunks(unique)
        return unique
    
    
