from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

# Balises de "boilerplate" : structure de page sans valeur informative pour la veille.
BOILERPLATE_TAGS = ["nav", "footer", "header", "aside", "script", "style", "noscript", "form"]


def strip_boilerplate(soup: BeautifulSoup) -> BeautifulSoup:
    """Retire la navigation, le pied de page et autres éléments non informatifs."""
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    return soup


def clean_html_to_markdown(html: str) -> str:
    """Convertit du HTML en Markdown propre (sans balises), après retrait du boilerplate."""
    soup = strip_boilerplate(BeautifulSoup(html, "lxml"))
    markdown = markdownify(str(soup), heading_style="ATX")
    return markdown.strip()


def dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Supprime les doublons d'articles en se basant sur l'URL (1re occurrence gardée)."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for article in articles:
        url = article.get("url")
        if url in seen:
            continue
        seen.add(url)
        unique.append(article)
    return unique


def chunk(text: str, max_chars: int = 1200) -> list[str]:
    """Découpe un texte en morceaux d'au plus ~max_chars, en coupant sur un espace."""
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        # Si on n'est pas à la fin, reculer jusqu'au dernier espace pour ne pas couper un mot.
        if end < length:
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks
