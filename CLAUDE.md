# CLAUDE.md

## Workflow Rules

- **Always ask for explicit permission before running `git commit` or `git push`.** Never commit or push automatically at the end of a task.

## Project Overview

Japanese language learning app (personal use). Web-based with FastAPI backend and React frontend, designed for desktop and mobile access via Tailscale. The user is an intermediate (~N3) learner focused on vocabulary and grammar retention over kanji. Difficulty adapts to a sticky JLPT level setting (N1–N5); conversation mode uses local faster-whisper for speech-to-text.

See [README.md](./README.md) for full documentation: project structure, database schema, API reference, SRS algorithm details, setup instructions, and data flow diagrams.

## Commands

```bash
# Install deps
cd backend && uv sync
cd frontend && npm install

# Dev (both servers) — bash for macOS/Linux/Git Bash, .ps1 for Windows PowerShell
bash start.sh        # or .\start.ps1
bash stop.sh         # or .\stop.ps1   — kills both, frees ports 8000 & 5173

# Dev (separate)
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && npm run dev -- --host 0.0.0.0

# Production build
cd frontend && npm run build
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Test backend imports
cd backend && uv run python -c "from app.main import app; print('OK')"

# Run backend tests
cd backend && uv run pytest

# Build frontend
cd frontend && npx vite build

# Docker (builds image, starts app + PostgreSQL)
docker compose up --build

# Alembic migrations (only needed when DATABASE_URL is set / PostgreSQL)
cd backend && uv run alembic upgrade head          # apply all migrations
cd backend && uv run alembic revision --autogenerate -m "description"  # generate new migration
```

## Architecture

- **Backend**: `backend/app/` — FastAPI, SQLAlchemy ORM. Python deps managed with `uv`.
- **Frontend**: `frontend/src/` — React 19, Vite 8, Tailwind CSS 4. Dark mode only.
- **Database**: SQLite at `backend/nihongo.db` by default (auto-created, `create_all` on startup). Set `DATABASE_URL` to use PostgreSQL instead — schema managed by Alembic (`backend/alembic/`), run automatically by `backend/entrypoint.sh` in Docker.
- **AI**: Anthropic Claude API (Sonnet) for content ingestion, question generation, and the conversation tutor. Word-lookup translation (`/api/furigana/lookup`) is pluggable — Claude by default, or a local Ollama model via `TRANSLATION_PROVIDER=ollama`. Key in `.env` at project root.
- **Speech-to-text**: local faster-whisper (CTranslate2). Default model is the Japanese-tuned `kotoba-tech/kotoba-whisper-v2.0-faster`; overridable via `WHISPER_MODEL`/`WHISPER_DEVICE`/`WHISPER_COMPUTE_TYPE` env vars. Lazy-loaded singleton in `routers/transcribe.py`. Disabled by default in Docker (`WHISPER_ENABLED=false`).
- **JP text processing**: fugashi + unidic-lite for tokenization/readings.

## Key Files

- `backend/app/main.py` — App entry, loads `.env` from project root, mounts routers, serves static frontend in production, exposes `/api/features`. On startup fires a background `prewarm()` against Ollama when `TRANSLATION_PROVIDER=ollama` so the first lookup is warm.
- `backend/app/database.py` — SQLAlchemy engine: PostgreSQL if `DATABASE_URL` is set, otherwise SQLite with Windows path normalization
- `backend/app/models.py` — SQLAlchemy models: Item (word/grammar/expression with SRS fields), Tag, Source, Setting (per-user key/value), StudySession; all data tables carry `user_id`
- `backend/app/deps.py` — FastAPI dependency `get_user_id`: reads `X-User-ID` header, defaults to `"default"` for single-user use
- `backend/app/srs.py` — Spaced repetition logic (again/hard/good ratings)
- `backend/app/routers/items.py` — CRUD for study items
- `backend/app/routers/study.py` — Due items, review submission, dashboard stats, session tracking
- `backend/app/routers/ingest.py` — Text/URL/PDF ingestion via Claude API extraction (JLPT-level-aware)
- `backend/app/routers/generate.py` — AI question generation (fill_blank, sentence_build, grammar_drill), on-demand example sentences, and reading passages (JLPT-level-aware)
- `backend/app/routers/furigana.py` — Furigana annotation endpoint using fugashi tokenizer; `lookup_word` delegates to `app.translation`
- `backend/app/translation.py` — Pluggable JP→EN translation lookup; dispatches to Claude or a local Ollama server based on `TRANSLATION_PROVIDER`
- `backend/app/routers/settings.py` — JLPT level setting + per-level prompt tuning (descriptor, reading length, new-word tier); exposes `get_jlpt_level(db, user_id)` used by ingest/generate/converse
- `backend/app/routers/transcribe.py` — Local faster-whisper transcription; lazy singleton with auto device/compute-type detection; gated by `WHISPER_ENABLED` env var
- `backend/app/routers/converse.py` — Conversation tutor: `/start` opens a level-appropriate question, `/reply` returns corrections + natural rewrite + follow-up
- `backend/alembic/` — Alembic migration environment; `env.py` uses `app.database.engine` directly so it inherits the same DB config as the app
- `backend/entrypoint.sh` — Docker entrypoint: runs `alembic upgrade head` when `DATABASE_URL` is set, then starts uvicorn
- `Dockerfile` — Multi-stage: Node builds frontend, Python installs deps (with `postgres` extra) and serves everything
- `docker-compose.yml` — App + PostgreSQL; passes `DATABASE_URL` and `ANTHROPIC_API_KEY` to the container
- `frontend/src/api.js` — All API client functions
- `frontend/src/App.jsx` — App shell with responsive nav, JLPT level dropdown, font-size control, routing; fetches `/api/features` on mount
- `frontend/src/context/FeaturesContext.jsx` — React context for server feature flags; currently exposes `whisperEnabled`
- `frontend/src/components/Ruby.jsx` — Furigana component, auto-annotates kanji with readings via batched API calls
- `frontend/src/pages/` — Dashboard, Items (library), Study (flashcards + drills + example-sentence button), Reading (AI passages), Converse (Q&A with mic when enabled), Ingest (import)

## Code Style

- Backend: Python, FastAPI conventions, type hints, Pydantic schemas in `schemas.py`
- Frontend: React functional components with hooks, Tailwind utility classes, no CSS modules
- Dark theme: `gray-950` body, `gray-900` cards, `gray-800` inputs/borders, `indigo` accents, alpha-transparency for colored badges (e.g. `red-500/15`)
- Japanese text uses `jp-text` CSS class (Noto Sans JP font)
- No auth — single user, network-secured

## Gotchas

- SQLite path uses forward-slash normalization for Windows compatibility (`database.py`)
- `create_all()` only runs when `DATABASE_URL` is not set (SQLite path); PostgreSQL schema is managed by Alembic
- `.env` is loaded from project root (`../../.env` relative to `app/main.py`), not from `backend/`; in Docker the file won't exist and env vars come from the container environment directly
- Vite dev server proxies `/api` to `http://localhost:8000` — in production, backend serves frontend static files from `frontend/dist/`
- The `example_sentences` field on Item is a JSON string (array of `{japanese, english}` objects), not a relation
- SRS intervals are in fractional days (e.g., 0.00694 = ~10 minutes)
- Claude API calls in ingest truncate input to 8000 chars
- First `/api/transcribe` call downloads the Whisper model (~1.5 GB for Kotoba default) to the HF cache and loads it onto GPU/CPU — subsequent calls reuse the in-process singleton; the model is never loaded when `WHISPER_ENABLED=false`
- JLPT level is persisted in the `settings` table (composite PK `user_id + key`); frontend also caches it in `localStorage` (`jlpt-level`) for instant load, then reconciles with the server on mount
- `alembic.ini` has an empty `sqlalchemy.url` — the actual URL is derived from `app.database.engine` at runtime in `alembic/env.py`; do not hardcode it there
- Multi-user: every data-bearing endpoint reads `X-User-ID` from the request header (default `"default"`); the frontend currently omits this header so all data lands under the `"default"` user. To wire up multi-user on the frontend, add the header in the `request()` helper in `frontend/src/api.js`
- Translation provider for `/api/furigana/lookup` is selected at request time via `TRANSLATION_PROVIDER` (`anthropic` default, `ollama` for a local model). The in-process lookup cache key includes `(provider, model)`, so flipping the env var doesn't return stale results — but the cache is per-process, so it's wiped on restart
- Ollama translation requests use `keep_alive: -1` (load forever) and a 300s per-request timeout. The 300s figure is sized for qwen3.5:9b's ~191s cold load measured in the bench. The startup prewarm in `main.py` is fire-and-forget — uvicorn accepts connections immediately and a user lookup arriving before prewarm finishes just joins the in-flight model load. With Ollama's default `OLLAMA_MAX_LOADED_MODELS=1`, using any other model on the same Ollama host evicts the translation model and the next lookup pays the cold load again
- Dockerfile WORKDIR is `/app/backend` (not `/app`) so that `main.py`'s `../frontend/dist` path matches the same relative layout as local dev
