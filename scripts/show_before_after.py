"""Démo avant/après : trace un article GitHub Changelog à travers le pipeline.

Montre les 3 états de la donnée :
  1. AVANT  — le XML brut du flux RSS (ce que requests.get() reçoit)
  2. MILIEU — le Markdown après cleaning (strip_boilerplate + markdownify)
  3. APRÈS  — les chunks prêts pour Chroma (avec leurs IDs)

Usage :
  docker compose exec -e PYTHONPATH=/srv backend uv run python scripts/show_before_after.py
"""
from __future__ import annotations

import hashlib

import requests
from bs4 import BeautifulSoup

from app.ingest.cleaning import clean_html_to_markdown, chunk

URL = "https://github.blog/changelog/feed/"

print("=" * 70)
print("ETAPE 1 — AVANT : le XML brut recu de", URL)
print("=" * 70)

resp = requests.get(URL, timeout=15, headers={"User-Agent": "nauda-palisse-veille/0.1"})
raw_xml = resp.content.decode("utf-8", errors="replace")
print(f"\nTaille totale du flux : {len(raw_xml)} caracteres\n")

soup = BeautifulSoup(resp.content, "lxml-xml")
first_item = soup.find("item")
print("Le premier <item> du flux, tel quel (XML brut) :\n")
print(str(first_item)[:1500])
print("\n[... tronque pour l'affichage ...]")

title = first_item.find("title").get_text(strip=True)
link = first_item.find("link").get_text(strip=True)
content_tag = (
    first_item.find("content:encoded")
    or first_item.find("content")
    or first_item.find("description")
)
raw_html = content_tag.get_text(strip=True) if content_tag else ""

print(f"\nArticle : {title}")
print(f"URL     : {link}")
print(f"Contenu HTML brut : {len(raw_html)} caracteres")

print()
print("=" * 70)
print("ETAPE 2 — MILIEU : apres cleaning (strip_boilerplate + markdownify)")
print("=" * 70)

markdown = clean_html_to_markdown(raw_html)
print(f"\nMarkdown propre : {len(markdown)} caracteres "
      f"(reduction : {len(raw_html)} -> {len(markdown)})\n")
print(markdown[:1200])
print("\n[... tronque pour l'affichage ...]")

print()
print("=" * 70)
print("ETAPE 3 — APRES : les chunks prets pour Chroma (max 1200 chars)")
print("=" * 70)

pieces = chunk(markdown)
h = hashlib.sha1(link.encode()).hexdigest()[:8]
print(f"\n{len(pieces)} chunk(s) genere(s) pour cet article\n")
for i, piece in enumerate(pieces):
    print(f"--- chunk id={h}_{i} ({len(piece)} chars) ---")
    print(piece[:300])
    print()

print("=" * 70)
print("RESUME DU VOYAGE DE LA DONNEE")
print("=" * 70)
print(f"""
  XML brut RSS        : {len(raw_xml):>7} chars  (le flux complet)
  HTML de l'article   : {len(raw_html):>7} chars  (extrait du <content:encoded>)
  Markdown nettoye    : {len(markdown):>7} chars  (boilerplate supprime)
  Chunks              : {len(pieces):>7} morceau(x) de max 1200 chars
  IDs deterministes   : sha1(url)[:8] + index -> upsert sans doublons

  NOTE : seuls les chunks sont persistes (dans Chroma).
  Les etats 1 et 2 n'existent qu'en memoire pendant l'execution.
  Amelioration prevue : persister le brut (couche raw) avant transformation.
""")
