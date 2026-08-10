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

# Backfill missing notes/examples and top up items holding fewer than
# EXAMPLES_PER_ITEM sentences (--dry-run still makes the Claude calls, just no writes)
cd backend && uv run python -m scripts.backfill_enrich --dry-run
cd backend && uv run python -m scripts.backfill_enrich

# Suspend items already past the leech threshold (no AI calls, pure DB sweep)
cd backend && uv run python -m scripts.suspend_leeches --dry-run
cd backend && uv run python -m scripts.suspend_leeches

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
- `backend/app/llm.py` — Anthropic client construction, `call_claude` (maps SDK errors to friendly HTTPExceptions, retries on 529), `complete_json`, and the `ai_response(...)` context manager. **Wrap any block that consumes model output in `ai_response`** — it turns a malformed reply (bad JSON, missing key, failed validation) into a 502 with a user-facing message instead of a bare 500, while letting existing HTTPExceptions through untouched.
- `backend/app/database.py` — SQLAlchemy engine: PostgreSQL if `DATABASE_URL` is set, otherwise SQLite with Windows path normalization
- `backend/app/models.py` — SQLAlchemy models: Item (word/grammar/expression with SRS fields), Tag, Source, Setting (per-user key/value), StudySession. All carry `user_id` **except `Tag`**, which is a globally shared namespace (items are still user-scoped, so this leaks no data — but tag names are common to all users). `Item.is_leech` is a Python property delegating to `srs.is_leech`; `srs.py` keeps its `models` import under `TYPE_CHECKING` so the two don't cycle
- `backend/app/deps.py` — FastAPI dependencies: `get_user_id` (reads `X-User-ID`, defaults to `"default"`), `require_item` (resolves `item_id` to a caller-owned Item or 404s), plus the `Db` / `UserId` / `OwnedItem` annotated aliases used across routers
- `backend/app/levels.py` — JLPT level constants (`VALID_LEVELS`, `LEVEL_DESCRIPTOR`, `READING_LENGTH`, `NEW_WORD_TIER`) and `get_jlpt_level(db, user_id)`. Lives outside `routers/` so ingest/generate/converse don't depend on the settings *router*
- `backend/app/crud.py` — Shared data access with no HTTP knowledge: `get_item_for_user`, `get_or_create_tags`
- `backend/app/enrich.py` — Generates the `notes` + `example_sentences` that only the ingest path used to produce, plus `build_example_sentence` for one more sentence that avoids the stored ones. Owns **`EXAMPLES_PER_ITEM`** (currently 2), the single source of truth for how many examples an item ships with — the enrich prompt, the ingest extraction prompt, and the backfill's top-up threshold all read it. Shared by `POST /api/items/?enrich=true`, `POST /generate/example-sentence`, and `scripts/backfill_enrich.py` so they can't drift
- `backend/scripts/backfill_enrich.py` — One-off backfill, two passes picked per item: **enrich** (notes and/or examples absent → one call fills both) and **top-up** (fewer than `EXAMPLES_PER_ITEM` examples → one call per missing sentence, *appended* so text already on the card survives). `--dry-run` to preview; backs up SQLite and commits per item, so it's safe to re-run and resumes after an interruption
- `backend/app/srs.py` — Spaced repetition logic (again/hard/good ratings), the two accuracy measures (`pass_rate` counts "hard", `recall_rate` doesn't), and leech detection/auto-suspension
- `backend/app/cloze.py` — Builds fill-in-the-blank questions from an item's stored `example_sentences`. **No AI call.** Locates the word via exact match, then fugashi lemma matching over token runs, which handles conjugation (済む → 済みました), suru-verb stems (把握する → 把握し), and phrases that inflect internally (手に入れる → 手に入れた). Also splits `・`/`/` alternatives (増える・減る). Returns `None` when no example contains the word — the caller 422s and the frontend skips the item
- `backend/app/japanese.py` — fugashi tokenizer helpers (`annotate`, `tokenize`, `reading_for`), factored out of `routers/furigana.py` so `cloze.py` doesn't have to import a router (same reasoning as `levels.py`). `routers/furigana.py` re-exports them for back-compat
- `backend/app/sqlite_migrate.py` — Idempotent `ADD COLUMN` pass run at startup on the SQLite path. `create_all()` builds missing *tables* but never alters existing ones, so a column added to a model is silently absent from an older `nihongo.db` and every query against it fails. Additive only; PostgreSQL gets the same columns via Alembic
- `backend/scripts/suspend_leeches.py` — One-off sweep suspending items already past the leech threshold (auto-suspension only fires on a *future* lapse). `--dry-run` to preview; backs up SQLite before writing
- `backend/app/routers/items.py` — CRUD for study items plus `POST /items/{id}/suspend|unsuspend`; `GET /items/` supports `type`, `search`, `tag`, `jlpt_level`, `suspended`, and `accuracy` (`new`/`struggling`/`learning`/`strong`) filters. The accuracy buckets use the **lenient pass rate** so they line up with the leech threshold
- `backend/app/routers/study.py` — Due items (excludes suspended), review submission, dashboard stats, session tracking, and `GET /study/history` for the retention chart
- `backend/app/routers/ingest.py` — Text/URL/PDF ingestion via Claude API extraction (JLPT-level-aware)
- `backend/app/routers/generate.py` — AI question generation (fill_blank, sentence_build, grammar_drill), on-demand example sentences, reading passages, and `/evaluate` for AI-assessed sentence_build answers (verdict + feedback + corrected version); all JLPT-level-aware
- `backend/app/routers/furigana.py` — Furigana annotation endpoint using fugashi tokenizer; `lookup_word` delegates to `app.translation`
- `backend/app/translation.py` — Pluggable JP→EN translation lookup; dispatches to Claude or a local Ollama server based on `TRANSLATION_PROVIDER`
- `backend/app/routers/settings.py` — JLPT level read/write endpoints only; the level constants and `get_jlpt_level` live in `app/levels.py`
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
- `require_item` binds `item_id` from the **path** on `/items/{item_id}` and from the **query string** on `/generate/*` — FastAPI resolves it either way from the dependency's parameter name. `/study/review` can't use it because `item_id` arrives in the JSON body; it calls `get_item_for_user` directly
- Dashboard `accuracy_today` only counts sessions whose `mode` is in `study.GRADED_MODES`. Conversation practice has no right/wrong answer, so including it pinned accuracy near 100%. Converse still records turns (so it counts toward `studied_today` and the streak) and reports turns-with-no-corrections as `items_correct`. **Add any new study mode to `GRADED_MODES` if its answers are graded**
- **`srs_correct` counts "good" only.** "Hard" goes to `srs_hard`, "again" to `srs_lapses`. Two derived measures live in `srs.py`: `pass_rate` (lenient, counts hard) and `recall_rate` (strict). Both are surfaced as `Item` properties and serialised on `ItemOut` alongside `is_leech` — **read them from the API rather than re-deriving the arithmetic in a component**. Leech detection and the Library accuracy filters use pass rate; the dashboard accuracy and trend chart use recall rate. Rows predating the split have `srs_hard = 0` and a `srs_correct` that folds hards in — unmixable after the fact, so their historical accuracy reads as the pass rate
- **Session counters are written per review, not at session end.** `POST /study/review` takes an optional `session_id` and bumps the session in the same transaction. `/session/{id}/end` only stamps `ended_at` — **don't reintroduce counts there**; an exit path that may fire from an unmount handler (or not at all) must not be able to overwrite real progress. Converse has no item reviews, so it posts each turn to `/session/{id}/progress`
- Leeches auto-suspend **only on a lapse** (`srs.process_review`). Crossing the threshold on a correct answer would yank a card the learner just got right. Items that were already leeches before the feature existed stay in rotation until they next fail — `scripts/suspend_leeches.py` sweeps them
- `unsuspend` resets SRS history by default (`?reset=false` to keep it). Without the reset a reworked card re-trips the leech threshold on its first lapse and vanishes again
- Adding a column to a model needs **both** an Alembic revision (PostgreSQL) **and** an entry in `sqlite_migrate.ADDED_COLUMNS` (SQLite) — `create_all()` won't alter an existing table, so the dev DB silently lacks it otherwise. SQLite needs a DEFAULT on any `NOT NULL` added column
- Cloze grading happens client-side against `StudyQuestion.accepted` (kanji **and** kana), not `answer` — use `isAnswerAccepted` in `Study.jsx`, not a bare `===`. `CLOZE_BLANK` in `Study.jsx` must stay in sync with `BLANK` in `app/cloze.py`; it's what reconstitutes the full sentence for read-aloud
- The backend serves `frontend/dist` via `StaticFiles`, which has **no SPA fallback**: deep links like `/study` 404 in production-mode serving. Vite handles them in dev. Navigate via the in-app nav when testing against port 8000
- `SpeakButton` renders nothing when the browser reports no `ja-*` voice. Headless browsers typically report zero voices, so it's invisible in automated screenshots — that's the gating working, not a bug
- Only the ingest path generates `notes`/`example_sentences`. `POST /api/items/` stores exactly what it's given unless `?enrich=true`, which the Reading page's "Add to library" now passes. Enrichment failure is non-fatal — the item still saves, bare, and the backfill script can pick it up later
- `example_sentences` is an LLM-authored JSON string in a text column with no DB-level validation. `IngestItem` coerces the array form the model often returns; the backend reads it through `cloze.parse_examples` and the frontend through `parseExamples` in `Study.jsx` — use those, don't reintroduce a bare `JSON.parse`/`json.loads` on it
- `EXAMPLES_PER_ITEM` is a **floor the prompts request, not an invariant the schema enforces** — nothing rejects a row with one example or trims one with four. The Study card caps its reveal at `SHOWN_EXAMPLES` (`Study.jsx`) for a stable card height, and the backfill's top-up pass fills shortfalls. Raising the constant means re-running the backfill; the older rows aren't rewritten on their own
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
