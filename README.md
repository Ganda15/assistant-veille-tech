# Assistant Veille Tech — Nauda Palisse

Nauda Palisse — assistant de veille technologique. RAG sur Chroma + injection de news fraîches + scraping de sources tech.

## Fonctionnalités

- Sélection de sujets populaires (Python, JavaScript, AI/ML, DevOps, Web) + saisie libre
- Question en langage naturel → réponse synthétique citant ses sources
- Retrieval sémantique sur une base vectorielle (Chroma) alimentée par scraping et NewsAPI
- Injection d'articles récents au moment du chat pour couvrir l'actualité chaude
- UI Next.js : grille de cards (titre, source, date, snippet, tags couleur, lien)

## Stack

- **Backend** : Python 3.11, uv, FastAPI ≥0.115, Pydantic 2
- **RAG** : ChromaDB 0.5, sentence-transformers 3 (`intfloat/multilingual-e5-small`)
- **LLM** : LangChain 0.3 + `langchain-azure-ai` → Azure AI Inference (Kimi-K2.6), avec fallback Groq
- **Scraping / HTTP** : requests, BeautifulSoup 4 + lxml, markdownify
- **Frontend** : Next.js 15 (App Router), React 19, TypeScript 5, Tailwind CSS 4
- **Orchestration** : Docker Compose (chromadb + backend + frontend)

## Layout

```
.
├── app/                      # backend FastAPI
│   ├── main.py               # endpoints /health, /topics, /chat
│   ├── chat.py               # orchestration retrieval + fresh news + LLM
│   ├── config.py             # settings (env)
│   ├── schemas.py            # modèles pydantic
│   ├── utils.py              # helpers partagés (normalize_date, chunk_id)
│   ├── rag/
│   │   ├── chroma_client.py  # client HTTP Chroma + collection `articles`
│   │   ├── retrieval.py      # embedding + query top-k
│   │   └── llm.py            # pipeline LangChain → Azure AI (Kimi-K2.6)
│   ├── ingest/
│   │   ├── news_api.py       # ingester NewsAPI → Chroma
│   │   ├── scraper.py        # scraping de sources tech
│   │   ├── cleaning.py       # HTML→Markdown, dedup, chunking, boilerplate
│   │   └── enrich.py         # hook d'enrichissement post-retrieval
│   └── runtime/
│       └── fresh_news.py     # fetch live NewsAPI au moment du chat
├── scripts/
│   ├── ingest_cli.py         # CLI d'ingestion (news / scrape)
│   ├── show_before_after.py  # démo : trace un article à travers le pipeline
│   └── show_fresh_news_io.py # démo : trace un appel fresh_news (input/output)
├── tests/
│   └── acceptance/           # tests d'acceptance de la chaîne d'ingestion
├── docs/                     # livrables : note de conception, note de flux, schéma
├── web/                      # frontend Next.js 15
│   ├── app/                  # App Router (page principale + layout)
│   ├── lib/api.ts            # client REST vers le backend
│   └── Dockerfile
├── Dockerfile.backend
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── .env.example
```

## Documentation

- `docs/note-conception.md` — choix des sources, modèle des chunks / métadonnées, schéma de flux.
- `docs/note-flux.md` — le pipeline de bout en bout (ingestion + runtime) et comment le relancer.
- `docs/schema-flux.md` — le schéma du flux au format Mermaid (s'affiche sur GitHub).

## Setup

```bash
cp .env.example .env          # renseigner AZURE_AI_INFERENCE_*, NEWS_API_KEY
make install                  # uv sync (backend)
make up                       # docker compose up -d (chromadb + backend + frontend)
```

- Backend : http://localhost:8000 (`/health`, `/topics`, `/chat`)
- Frontend : http://localhost:3000
- ChromaDB : http://localhost:8002

Tests :

```bash
make test                     # uv run pytest
```

Ingestion (CLI) :

```bash
make ingest                   # passe par scripts/ingest_cli.py
```

## Sources indexées

Les sources retenues pour cette phase (détail et justification dans `docs/note-conception.md`) :

- **NewsAPI v2** (`/everything`) — agrégateur, apporte la largeur sur les tendances générales. Doc : https://newsapi.org/docs
- **GitHub Changelog** (RSS `github.blog/changelog/feed/`) — changelog produit, annonces officielles vérifiées.
- **Blog Next.js** (RSS `nextjs.org/feed.xml`) — blog technique, écosystème web / JS.
- **Python Docs** (HTML `docs.python.org/.../whatsnew`) — page de doc / release notes.

Autres pistes possibles, non retenues pour l'instant : Hacker News, DEV.to, ou les changelogs Vercel / OpenAI (chargés en JavaScript, ils nécessiteraient un navigateur headless type Playwright).

## Aller plus loin (optionnel)

La stack est extensible vers **Postgres** pour porter des comptes utilisateur (sign-up / sign-in), des sujets favoris et un historique des recherches — non couvert ici. Cela ajouterait des endpoints `/users`, `/me/favorites`, `/me/history` et une page « Mon compte » côté frontend, avec un schéma user-scoped et les obligations RGPD associées (hash des mots de passe, durée de conservation, droit à l'effacement).

## Utiles

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make logs       # docker compose logs -f
make down       # stop services
```

## Licence

Interne Nauda Palisse.

## Contact

veille@nauda-palisse.example
