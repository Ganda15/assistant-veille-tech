# Note de flux — comment marche la veille de bout en bout

> Doc pour l'équipe. Si tu reprends le projet, lis ça en premier : ça explique d'où vient la donnée,
> ce qu'on lui fait, et comment la relancer. Le schéma visuel est dans `schema-flux.md`.

## En une phrase

On va chercher des articles tech (NewsAPI + scraping RSS/HTML), on les nettoie et on les découpe, on
les vectorise et on les range dans Chroma. Quand quelqu'un pose une question, on ressort les morceaux
les plus proches, on y ajoute des news fraîches, et le LLM (Kimi sur Azure) rédige une réponse avec les
sources citées.

Il y a donc **deux temps** :
- l'**ingestion** (on remplit l'index, une fois, hors ligne) ;
- le **runtime** (au moment de la question, on lit l'index + on va chercher du frais en direct).

## Le flux étape par étape

### 1. Les sources
Trois entrées, dans `app/ingest/` :
- **NewsAPI** (`news_api.py`) → tendances générales, endpoint `/everything`.
- **GitHub Changelog** (RSS) → `github.blog/changelog/feed/`, le `content:encoded` contient le HTML
  complet.
- **Next.js Blog** (RSS) + **Python Docs** (HTML) → côté `scraper.py`.

Le scraper choisit le bon parser selon le `type` de la source : `lxml-xml` pour le RSS, `lxml` pour le
HTML. Avant toute transformation, on garde la réponse brute dans `data/raw/` (couche raw) — comme ça on
peut re-traiter sans re-télécharger, et on sait toujours d'où vient un chunk.

### 2 → 4. Nettoyage, dédup, chunking
Tout passe par `app/ingest/cleaning.py` :
- `clean_html_to_markdown()` : on vire le boilerplate (`nav, footer, header, aside, script, style,
  noscript, form`) puis on convertit en Markdown propre avec `markdownify`.
- `dedupe()` : on retire les doublons par **URL** (un `set` des URLs déjà vues).
- `chunk()` : on coupe le texte en morceaux d'environ **1200 caractères**, en coupant sur un espace
  pour ne pas casser un mot. Pas de tokenizer, on reste simple.

### 5. Les métadonnées (le point important pour la traçabilité)
Pour chaque chunk on attache toujours les mêmes clés :

```
title · source · date (YYYY-MM-DD) · url · tags · collected_at · chunk_index
```

Les 5 premières (`title, source, date, url, tags`) ne sont pas choisies au hasard : c'est exactement ce
que `app/rag/llm.py` (`_build_cards`) lit pour fabriquer les cards du frontend. Si une clé manque, la
card est vide. `url` + `collected_at` servent à **remonter chaque chunk jusqu'à sa source** (critère du
brief).

### 6 → 7. Embeddings et stockage
- `embed()` (dans `app/rag/retrieval.py`) charge le modèle `intfloat/multilingual-e5-small` en local
  (chargé une seule fois via `@lru_cache`) et transforme chaque chunk en vecteur de **384 dimensions**,
  normalisé.
- On `upsert` le tout dans **Chroma** (collection `articles`, distance cosinus). L'id du chunk est
  déterministe (`sha1(url)[:8]_index`), donc relancer l'ingestion **met à jour** au lieu de créer des
  doublons.

Réglages Chroma à connaître (`app/rag/chroma_client.py`) : `hnsw:space=cosine`, `M=64`,
`construction_ef=200`, `search_ef=100` — c'est ce qui corrige le bug "ef or M too small" quand on
filtre sur une petite source.

### 8 → 11. Le runtime (quand on pose une question)
Tout est orchestré dans `app/chat.py` (`handle_chat`) :
1. on élargit la question avec les topics (`_expand_query`) ;
2. on construit un filtre éventuel (`_build_where`) — table `SOURCE_BY_TOPIC`, ex. topic `javascript`
   → source `Next.js Blog`, filtre `{"source": {"$eq": ...}}` ;
3. `retrieval.retrieve(query, k=8, where=...)` → les 8 chunks Chroma les plus proches ;
4. `enrich_retrieval(...)` (hook, `app/ingest/enrich.py`) → part des tags des chunks et va chercher des
   repos GitHub populaires (Search API) ; renvoie une liste au **même format** qu'un chunk ;
5. `fresh_news.fetch(topics)` (`app/runtime/fresh_news.py`) → NewsAPI en direct (~24-48h), non indexé,
   injecté uniquement pour cette réponse (éphémère) ;
6. `compose_answer(...)` envoie question + chunks + news au LLM **Kimi-K2.6 (Azure AI Inference)**, qui
   rédige une synthèse avec sources.

> Important : c'est un **pipeline RAG**, pas un agent ReAct. C'est le code qui décide les étapes
> (retrieval → news → génération), pas le LLM. Le LLM n'intervient qu'à la fin pour rédiger.

### 12. Le frontend
Le front Next.js affiche la réponse + des **cards** : titre, source, date, extrait tronqué (3 lignes),
tags colorés, bouton « Lire l'article » (le lien `url`).

## Comment relancer le pipeline

Il faut un `.env` rempli (clé NewsAPI, config Azure, etc.). Ensuite, en une commande :

```bash
make up        # démarre Chroma + backend + frontend (docker compose)
make ingest    # lance scripts/ingest_cli.py → news + scrape → remplit Chroma
```

`make ingest` sans argument lance les deux (news sur `python, llm, AI` puis le scraping). On peut aussi
cibler : `uv run python scripts/ingest_cli.py news -t python -t llm`.

Pour tester le chat en ligne de commande : `make chat-test`.

## Comment ajouter une source

- **Source RSS ou HTML** → ajouter une entrée dans la liste `SOURCES` de `app/ingest/scraper.py`
  (`url`, `source`, `tags`, `type` = `rss` ou `html`). Le bon parser est choisi tout seul.
- **Nouveau topic NewsAPI** → le passer au CLI (`-t mon_topic`).
- Si le topic doit pouvoir **filtrer** une source précise au runtime → ajouter la correspondance dans
  `SOURCE_BY_TOPIC` (`app/chat.py`).

## À savoir (limites connues)

- Le LLM Azure (Kimi-K2.6) peut renvoyer une **404** si le modèle n'est pas déployé sur la ressource —
  c'est un souci de config Azure, pas du code du pipeline.
- Quelques chunks issus de NewsAPI peuvent contenir une page anti-bot ("A required part of this site
  couldn't load…"). Amélioration prévue : un filtre dans `cleaning.py` pour rejeter ces pages avant
  l'indexation.
- Les tests : `make test`. En local il faut pointer Chroma sur `http://localhost:8002` (le nom docker
  `chromadb` ne résout pas depuis Windows).
