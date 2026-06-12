"""Démo input/output : trace un appel fresh_news de bout en bout.

Montre les 3 états :
  1. INPUT   — le topic + les paramètres envoyés à NewsAPI
  2. BRUT    — le JSON renvoyé par NewsAPI (1er article, tel quel)
  3. OUTPUT  — l'article normalisé par _fetch_live (le format du pipeline)

Usage :
  docker compose exec -e PYTHONPATH=/srv backend uv run python scripts/show_fresh_news_io.py
"""
from __future__ import annotations

import json

import requests

from app.config import get_settings
from app.runtime.fresh_news import _fetch_live, PAGE_SIZE

TOPIC = "python"

settings = get_settings()

print("=" * 70)
print("ETAPE 1 — INPUT : ce que fresh_news envoie a NewsAPI")
print("=" * 70)

params = {
    "q": TOPIC,
    "language": "en",
    "sortBy": "publishedAt",
    "pageSize": PAGE_SIZE,
    "apiKey": settings.news_api_key[:8] + "..." if settings.news_api_key else "(absente)",
}
print(f"\nURL    : GET {settings.news_api_base_url}/everything")
print("Params :")
print(json.dumps(params, indent=2, ensure_ascii=False))

print()
print("=" * 70)
print("ETAPE 2 — BRUT : ce que NewsAPI renvoie (JSON, 1er article tel quel)")
print("=" * 70)

resp = requests.get(
    f"{settings.news_api_base_url}/everything",
    params={
        "q": TOPIC,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
        "apiKey": settings.news_api_key,
    },
    timeout=10,
)
data = resp.json()
print(f"\nstatus       : {data.get('status')}")
print(f"totalResults : {data.get('totalResults')}")
print(f"articles recus : {len(data.get('articles') or [])}\n")
print("Premier article BRUT (le JSON exact de NewsAPI) :\n")
print(json.dumps((data.get("articles") or [{}])[0], indent=2, ensure_ascii=False)[:1200])
print("\n[... tronque pour l'affichage ...]")

print()
print("=" * 70)
print("ETAPE 3 — OUTPUT : le meme article apres _fetch_live (normalise)")
print("=" * 70)

articles = _fetch_live(TOPIC, since=None)
print(f"\n{len(articles)} articles normalises. Le premier :\n")
print(json.dumps(articles[0], indent=2, ensure_ascii=False))

print()
print("=" * 70)
print("RESUME DE LA TRANSFORMATION")
print("=" * 70)
print("""
  INPUT  : un topic ('python') -> parametres HTTP pour /everything
  BRUT   : JSON NewsAPI — cles 'source.name', 'publishedAt' ISO,
           contenu tronque avec '[+N chars]', articles 'removed.com'
  OUTPUT : dict normalise du pipeline — title, source, date (YYYY-MM-DD),
           content (sans le '[+'), url, tags
  Ces articles ne sont PAS stockes dans Chroma : ils enrichissent
  la reponse du chat en cours, puis disparaissent (online/ephemere).
""")
