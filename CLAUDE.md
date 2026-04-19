# CLAUDE.md

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
```

## Architecture

- **Backend**: `backend/app/` — FastAPI, SQLAlchemy ORM, SQLite (`nihongo.db`). Python deps managed with `uv`.
- **Frontend**: `frontend/src/` — React 19, Vite 8, Tailwind CSS 4. Dark mode only.
- **Database**: SQLite at `backend/nihongo.db`. Created automatically on first run.
- **AI**: Anthropic Claude API (Sonnet) for content ingestion, question generation, and the conversation tutor. Key in `.env` at project root.
- **Speech-to-text**: local faster-whisper (CTranslate2). Default model is the Japanese-tuned `kotoba-tech/kotoba-whisper-v2.0-faster`; overridable via `WHISPER_MODEL`/`WHISPER_DEVICE`/`WHISPER_COMPUTE_TYPE` env vars. Lazy-loaded singleton in `routers/transcribe.py`.
- **JP text processing**: fugashi + unidic-lite for tokenization/readings.

## Key Files

- `backend/app/main.py` — App entry, loads `.env` from project root, mounts routers, serves static frontend in production
- `backend/app/models.py` — SQLAlchemy models: Item (word/grammar/expression with SRS fields), Tag, Source, Setting (key/value), StudySession
- `backend/app/srs.py` — Spaced repetition logic (again/hard/good ratings)
- `backend/app/routers/items.py` — CRUD for study items
- `backend/app/routers/study.py` — Due items, review submission, dashboard stats, session tracking
- `backend/app/routers/ingest.py` — Text/URL/PDF ingestion via Claude API extraction (JLPT-level-aware)
- `backend/app/routers/generate.py` — AI question generation (fill_blank, sentence_build, grammar_drill) and reading passages (JLPT-level-aware)
- `backend/app/routers/furigana.py` — Furigana annotation endpoint using fugashi tokenizer
- `backend/app/routers/settings.py` — JLPT level setting + per-level prompt tuning (descriptor, reading length, new-word tier); exposes `get_jlpt_level(db)` used by ingest/generate/converse
- `backend/app/routers/transcribe.py` — Local faster-whisper transcription; lazy singleton with auto device/compute-type detection
- `backend/app/routers/converse.py` — Conversation tutor: `/start` opens a level-appropriate question, `/reply` returns corrections + natural rewrite + follow-up
- `frontend/src/api.js` — All API client functions
- `frontend/src/App.jsx` — App shell with responsive nav, JLPT level dropdown, font-size control, routing
- `frontend/src/components/Ruby.jsx` — Furigana component, auto-annotates kanji with readings via batched API calls
- `frontend/src/pages/` — Dashboard, Items (library), Study (flashcards + drills), Reading (AI passages), Converse (Q&A with mic), Ingest (import)

## Code Style

- Backend: Python, FastAPI conventions, type hints, Pydantic schemas in `schemas.py`
- Frontend: React functional components with hooks, Tailwind utility classes, no CSS modules
- Dark theme: `gray-950` body, `gray-900` cards, `gray-800` inputs/borders, `indigo` accents, alpha-transparency for colored badges (e.g. `red-500/15`)
- Japanese text uses `jp-text` CSS class (Noto Sans JP font)
- No auth — single user, network-secured

## Gotchas

- SQLite path uses forward-slash normalization for Windows compatibility (`database.py`)
- `.env` is loaded from project root (`../../.env` relative to `app/main.py`), not from `backend/`
- Vite dev server proxies `/api` to `http://localhost:8000` — in production, backend serves frontend static files from `frontend/dist/`
- The `example_sentences` field on Item is a JSON string (array of `{japanese, english}` objects), not a relation
- SRS intervals are in fractional days (e.g., 0.00694 = ~10 minutes)
- Claude API calls in ingest truncate input to 8000 chars
- First `/api/transcribe` call downloads the Whisper model (~1.5 GB for Kotoba default) to the HF cache and loads it onto GPU/CPU — subsequent calls reuse the in-process singleton
- JLPT level is persisted in the `settings` table; frontend also caches it in `localStorage` (`jlpt-level`) for instant load, then reconciles with the server on mount
