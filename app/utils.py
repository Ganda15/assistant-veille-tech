from __future__ import annotations

import hashlib
from datetime import datetime

# Petits helpers partagés par l'ingestion (news_api, scraper) et le runtime (fresh_news).
# Avant ils étaient copiés dans chaque fichier — je les mets ici pour éviter les doublons.


def normalize_date(raw: str | None) -> str:
    """Ramène une date (ISO, RSS...) au format YYYY-MM-DD. Vide si absente ou illisible."""
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def chunk_id(url: str, index: int) -> str:
    """Id déterministe d'un chunk : hash de l'url + numéro. Relancer l'ingestion ne duplique pas."""
    h = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{h}_{index}"
