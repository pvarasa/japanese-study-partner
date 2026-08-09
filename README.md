# 日本語 Study Partner

A personal Japanese language learning app with spaced repetition, AI-powered content ingestion, conversation practice with local speech-to-text, and adaptive study modes. Difficulty adapts to a sticky JLPT level setting (N1–N5).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy |
| Database | SQLite (default, zero-config) or PostgreSQL (via `DATABASE_URL`) |
| Frontend | React 19, Vite 8, Tailwind CSS 4 |
| AI | Anthropic Claude API (Sonnet 4.6); optional local Ollama for word-lookup translations |
| JP Parsing | fugashi + unidic-lite |
| Speech-to-text | faster-whisper (CTranslate2) — local, Japanese-tuned Kotoba-Whisper by default |
| Package Mgmt | uv (Python), npm (JS) |
| Containerisation | Docker + Docker Compose |

## Project Structure

```
jp_study_partner/
├── .env                          # ANTHROPIC_API_KEY (create from .env.example)
├── .env.example
├── Dockerfile                    # Multi-stage build: Node (frontend) + Python (backend)
├── docker-compose.yml            # App + PostgreSQL for containerised deployment
├── .dockerignore
├── start.sh / start.ps1          # Start both dev servers (bash / PowerShell)
├── stop.sh  / stop.ps1           # Stop both servers (frees ports 8000 & 5173)
├── docs/screenshots/             # README screenshots
│
├── backend/
│   ├── pyproject.toml            # Python deps (uv); postgres extra; pytest in dev group
│   ├── alembic.ini               # Alembic config (URL comes from app engine at runtime)
│   ├── entrypoint.sh             # Docker entrypoint: runs Alembic then starts uvicorn
│   ├── nihongo.db                # SQLite database (created at runtime; not used with PostgreSQL)
│   ├── alembic/
│   │   ├── env.py                # Alembic env: uses app.database.engine directly
│   │   └── versions/             # Migration scripts
│   ├── tests/                    # pytest suite: srs, cloze, llm parser, non-AI API smoke
│   ├── scripts/
│   │   ├── backfill_enrich.py    # One-off: fill missing notes/examples (one Claude call per item)
│   │   └── suspend_leeches.py    # One-off: suspend items already past the leech threshold
│   └── app/
│       ├── main.py               # FastAPI app, CORS, static file serving, /api/features
│       ├── database.py           # SQLAlchemy engine: PostgreSQL if DATABASE_URL set, else SQLite
│       ├── sqlite_migrate.py     # Idempotent ADD COLUMN pass for SQLite (create_all can't alter)
│       ├── models.py             # ORM models: Item, Tag, Source, Setting, StudySession
│       ├── schemas.py            # Pydantic request/response schemas
│       ├── srs.py                # Spaced repetition algorithm + leech detection
│       ├── cloze.py              # Builds fill-in-the-blank questions from stored example sentences
│       ├── japanese.py           # fugashi tokenizer helpers: annotate, tokenize, reading_for
│       ├── levels.py             # JLPT level config + per-level prompt tuning, get_jlpt_level
│       ├── crud.py               # Shared data access: get_item_for_user, get_or_create_tags
│       ├── enrich.py             # Generates usage notes + example sentences for bare items
│       ├── llm.py                # Shared LLM helpers: client construction, error-handling wrapper around messages.create, JSON parsing, ai_response guard
│       ├── translation.py        # Pluggable JP→EN translation: Claude or local Ollama (TRANSLATION_PROVIDER)
│       ├── deps.py               # FastAPI dependencies: get_user_id, require_item, Db/UserId/OwnedItem aliases
│       └── routers/
│           ├── items.py          # CRUD for study items + suspend/unsuspend
│           ├── study.py          # Due items, reviews, sessions, dashboard, history
│           ├── ingest.py         # Text/URL/PDF ingestion via Claude API
│           ├── generate.py       # Question generation (cloze locally, the rest via Claude) & reading passages
│           ├── furigana.py       # Furigana HTTP endpoints (tokenizer lives in app/japanese.py)
│           ├── settings.py       # JLPT level read/write endpoints (config lives in levels.py)
│           ├── transcribe.py     # Local Whisper (faster-whisper) audio → text
│           └── converse.py       # AI conversation tutor: open-ended Q&A + corrections
│
└── frontend/
    ├── vite.config.js            # Vite config with Tailwind & API proxy
    ├── index.html
    └── src/
        ├── main.jsx              # React entry with BrowserRouter
        ├── App.jsx               # Shell: header, nav, JLPT level + font-size controls, routing
        ├── api.js                # API client (all fetch calls)
        ├── index.css             # Tailwind imports, dark theme, JP fonts, ruby + skeleton styling
        ├── context/
        │   ├── LevelContext.jsx  # React context for the sticky JLPT level
        │   └── FeaturesContext.jsx # React context for server feature flags (e.g. whisperEnabled)
        ├── components/
        │   ├── Ruby.jsx          # Furigana component (batched, cached kanji annotations)
        │   ├── ReadingText.jsx   # Tokenized passage with per-word click-to-lookup popovers
        │   ├── LevelBadge.jsx    # JLPT level pill shown on study/reading/converse headers
        │   ├── RetentionChart.jsx # Inline SVG: daily recall accuracy + review volume
        │   ├── SpeakButton.jsx   # Japanese TTS via Web Speech API; hidden when no ja voice
        │   └── Skeleton.jsx      # Shimmer skeleton primitives (Skeleton, SkeletonLine)
        └── pages/
            ├── Dashboard.jsx     # Stats, retention trend, leech rework queue, weak areas, streak
            ├── Items.jsx         # Library: search, type/level/accuracy/status filters, suspend, inline edit, delete
            ├── Study.jsx         # Flashcards, cloze & AI drills with SRS; example-sentence button
            ├── Reading.jsx       # AI reading practice with library + new vocabulary
            ├── Converse.jsx      # Conversation mode: tutor prompts, typed/spoken replies, corrections
            └── Ingest.jsx        # Import content via text/URL/PDF + AI extraction
```

## Database Schema

### Item
The core study unit. Can be a **word**, **grammar** point, or **expression**.

| Column | Type | Description |
|--------|------|-------------|
| id | int PK | |
| user_id | string | Owner (from `X-User-ID` header; `"default"` for single-user) |
| type | string | `word`, `grammar`, or `expression` |
| japanese | text | The Japanese text |
| reading | text | Hiragana reading |
| meaning | text | English meaning |
| notes | text | Usage notes |
| example_sentences | text | JSON array of `{japanese, english}` |
| jlpt_level | string | N1-N5 |
| source_id | int FK | Reference to Source |
| created_at | datetime | |
| srs_interval | float | Days until next review |
| srs_ease | float | Difficulty factor (1.3-3.0, default 2.5) |
| srs_due | datetime | When the item is next due |
| srs_reviews | int | Total review count |
| srs_correct | int | "Good" rating count (see note below) |
| srs_hard | int | "Hard" rating count |
| srs_lapses | int | "Again" rating count |
| suspended | bool | Pulled out of the review queue (leech, or manual) |

Two accuracy measures fall out of these, both computed in `app/srs.py` and exposed on
`ItemOut` as `recall_rate` / `pass_rate` (and `is_leech`) so no client re-derives them:

- **recall rate** = `srs_correct / srs_reviews` — clean recalls only (strict)
- **pass rate** = `(srs_correct + srs_hard) / srs_reviews` — anything that wasn't a lapse (lenient)

Both are `null` until the item has been reviewed at least once. Leech detection and the
Library's accuracy filters use the pass rate; the dashboard's accuracy and trend use the
recall rate.

> **Note on historical rows.** `srs_hard` and `srs_lapses` were added later. Reviews
> recorded before then counted "hard" as correct, so those rows have `srs_hard = 0`
> and a `srs_correct` that folds the hards in. There's no way to unmix them after the
> fact, so pre-migration accuracy reads as the *pass* rate, not the recall rate.

### Tag
Many-to-many with Item via `item_tags` join table. Tags are global (shared label names across users).

### Source
Where study material came from. Fields: `user_id`, `title`, `type` (url/pdf/text/manual), `url`, `content`, `created_at`. Has many Items.

### Setting
Per-user key/value settings. Composite PK `(user_id, key)`. Currently stores `jlpt_level` (N1–N5, default N3).

### StudySession
Tracks study sessions. Fields: `user_id`, `started_at`, `ended_at`, `items_reviewed`, `items_correct` ("good" only), `items_hard`, `mode` (one of `flashcard_jp`, `flashcard_en`, `cloze`, `fill_blank`, `sentence_build`, `grammar_drill`, `converse`).

Counters are written **incrementally**, as each review happens — not at session end. A
session that's abandoned part-way keeps the reviews already done. See
[Session recording](#session-recording).

## Multi-User Support

All data-bearing endpoints are scoped to a user via the `X-User-ID` request header. If the header is absent the user is `"default"`, which preserves single-user SQLite behaviour without any configuration.

```
X-User-ID: alice
```

Items, sources, settings, and study sessions are all isolated per user. Tags are global (shared label names). The frontend currently omits the header (uses `"default"`); to support multiple users, set the header in `frontend/src/api.js`'s `request()` helper.

## API Endpoints

Base URL: `http://localhost:8000/api`

### Items (`/api/items`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/items/` | List items. Query: `type`, `search`, `tag`, `jlpt_level` (N1–N5), `accuracy` (`new`/`struggling`/`learning`/`strong`), `suspended` (bool), `limit`, `offset` |
| POST | `/items/` | Create item |
| GET | `/items/{id}` | Get single item |
| PUT | `/items/{id}` | Update item (partial) |
| DELETE | `/items/{id}` | Delete item |
| POST | `/items/{id}/suspend` | Pull the item out of the review queue |
| POST | `/items/{id}/unsuspend` | Return it to the queue. Query: `reset` (default `true`) also clears its SRS history, so a reworked card doesn't re-trip the leech threshold on its first lapse |

### Study (`/api/study`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/study/due` | Get items due for review (excludes suspended). Query: `limit`, `type` |
| POST | `/study/review` | Submit review. Body: `{item_id, rating, session_id?}` where rating is `again`/`hard`/`good`. With `session_id`, folds the review into that session's counters in the same transaction |
| GET | `/study/dashboard` | Stats: total, due, studied today, accuracy, weak items, streak, leeches, suspended count |
| GET | `/study/history` | Per-day graded review counts for the trend chart. Query: `days` (default 60, max 365) |
| POST | `/study/session/start` | Start session. Query: `mode` |
| POST | `/study/session/{id}/progress` | Add to a session's counters. Body: `{reviewed, correct, hard}`. For modes that aren't item reviews (conversation turns) |
| POST | `/study/session/{id}/end` | Close a session (stamps `ended_at`). Takes no counts — counters only ever move through `/review` and `/progress` |

### Ingest (`/api/ingest`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest/text` | Extract items from pasted text (Form: `content`) |
| POST | `/ingest/url` | Extract items from URL (Form: `url`) |
| POST | `/ingest/pdf` | Extract items from PDF upload (Form: `file`) |
| POST | `/ingest/save` | Save reviewed items to DB (Form: `source_title`, `source_type`, `source_url`, `items_json`) |

### Generate (`/api/generate`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate/question` | Drill question. Query: `item_id`, `mode` (`cloze`/`fill_blank`/`sentence_build`/`grammar_drill`). **`cloze` costs no AI call** — it's built from the item's stored example sentences and returns instantly; 422 if no stored example contains the word |
| POST | `/generate/example-sentence` | Generate a fresh example sentence for an item. Query: `item_id`. Returns `{japanese, english}`. Each call produces a different sentence. |
| POST | `/generate/reading` | Generate reading passage using library words + new vocabulary. Form: `prompt` (optional topic guidance) |
| POST | `/generate/evaluate` | AI evaluation of a sentence_build answer. Body: `{user_answer, expected_answer, prompt}`. Returns `{verdict: "correct"\|"partial"\|"incorrect", feedback, corrected}`. Accepts natural variations; provides specific feedback and a corrected version when the answer has errors. |

### Furigana (`/api/furigana`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/furigana/annotate` | Annotate texts with furigana ruby HTML. Body: `{texts: string[]}` → `{results: string[]}` |
| POST | `/furigana/tokenize` | Split text into tokens with surface/reading/lemma, merging meanings from a supplied word list. Used by the reading-page word popover. |
| POST | `/furigana/lookup` | English gloss for a Japanese word or phrase. Body: `{surface, lemma, context, is_phrase}` → `{meaning, reading}`. With `is_phrase=true` (used by the selection-translation popup), the prompt asks for a natural translation instead of a single-word gloss. Backed by Claude or a local Ollama model — see `TRANSLATION_PROVIDER`. Cached in-process per `(provider, model, lemma_or_surface, is_phrase)`. |

### Settings (`/api/settings`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings/` | Get app settings (currently `{jlpt_level}`) |
| PUT | `/settings/` | Update settings. Body: `{jlpt_level: "N1"..."N5"}` |

### Transcribe (`/api/transcribe`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/transcribe/` | Transcribe an audio upload (multipart `audio`) to Japanese text. Uses local faster-whisper. First call lazy-loads the model (slow on first run). Returns 503 if `WHISPER_ENABLED=false`. |

### Features (`/api/features`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/features` | Returns server feature flags. Currently: `{whisper_enabled: bool}`. Read by the frontend on mount to adapt the UI. |

### Health (`/api/health`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check. Returns `{status: "ok"}`. |

### Converse (`/api/converse`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/converse/start` | Open a new conversation. Returns `{topic, question, english_hint}` calibrated to current JLPT level. |
| POST | `/converse/reply` | Body: `{history: [{role, content}], user_text}`. Returns `{corrections, rewrite, feedback, follow_up, follow_up_hint}`. |

## SRS Algorithm

Simple spaced repetition with three ratings:

| Rating | Effect | Counter |
|--------|--------|---------|
| **Again** | Reset interval to ~10 min, ease -0.2 | `srs_lapses` |
| **Hard** | Short interval (1hr if new, else x1.2), ease -0.1 | `srs_hard` |
| **Good** | Standard interval (1 day if new, else x ease), ease +0.05 | `srs_correct` |

Ease factor is clamped to [1.3, 3.0]. Items are due when `srs_due <= now` and not
suspended, ordered by most overdue first.

Each rating increments its own counter. "Hard" is deliberately **not** counted as
correct — folding it into `srs_correct` made a card the learner barely dredged up look
identical to one they knew cold, which flattered the accuracy number and hid exactly the
items worth attention.

### Leeches

A card that keeps failing comes back every session, never matures, and crowds out items
that would actually stick. Past a threshold it's **suspended** — removed from `/study/due`
until the card itself is reworked.

- **Threshold:** `srs_reviews >= 8` and pass rate `< 60%` (`LEECH_MIN_REVIEWS` /
  `LEECH_MAX_PASS_RATE` in `backend/app/srs.py`)
- **Trigger:** only on a lapse. Crossing the threshold on a *correct* answer would yank a
  card the learner just got right, which reads as a bug.
- **Recovery:** restore from the dashboard's "Needs rework" list or the Library. That
  resets the SRS history by default, so a rewritten card isn't instantly re-suspended by
  its old failure count.

Leeches that predate the feature stay in rotation until they next lapse. To sweep them all
at once:

```bash
cd backend && uv run python -m scripts.suspend_leeches --dry-run   # preview
cd backend && uv run python -m scripts.suspend_leeches             # apply
```

### Session recording

Session counters are advanced **per review** (`POST /study/review` with a `session_id`),
not at session end. Recording only on completion meant an abandoned session logged nothing
at all — which silently zeroed every mode the learner didn't run to the last card, and
broke the streak. `/study/session/{id}/end` now only stamps `ended_at`: letting the
closing call also *set* totals would give an exit path — which may fire from an unmount
handler, or not at all — the power to overwrite what actually happened.

Conversation has no item reviews, so it posts each turn to
`/study/session/{id}/progress` as it happens rather than reporting a total from an unmount
handler that may never run.

## Study Modes

1. **JP to EN Flashcard** - See Japanese, recall English meaning
2. **EN to JP Flashcard** - See English, recall Japanese
3. **Cloze** - The word blanked out of one of *its own* stored example sentences, with the English gloss as the hint. Free-form input; **either the kanji or the kana reading counts**, so it's playable without switching to a Japanese IME. Costs no AI call and returns instantly — it reuses `example_sentences`, which every enriched item already has. Rotates among matching sentences so repeat reviews aren't identical. Items whose examples don't actually contain the word are skipped rather than erroring.
4. **Fill in the Blank** - AI generates a sentence with the target word blanked out, 4 multiple-choice options
5. **Sentence Building** - Given an English prompt, write the Japanese sentence (free-form input). On submit, calls `/generate/evaluate` for AI assessment: **correct** (accepts natural variations), **almost there** (right idea, grammar/particle error — shows a corrected version), or **incorrect** (wrong meaning).
6. **Grammar Drill** - AI generates a usage question for a grammar point, 4 multiple-choice options

Modes 1–6 use SRS rating after each card. Flashcard modes (1–2) include a **Generate example** button on reveal that calls `/generate/example-sentence` to produce a fresh AI-generated sentence with translation; press it multiple times for variety.

Japanese text on cards, example sentences, and cloze answers carries a **speaker button**
(Web Speech API, `ja-JP`, rate 0.85). It's local to the browser — no API key, no network,
no audio files — and is hidden entirely on a machine with no Japanese voice installed,
rather than letting an English voice mangle the kana.

7. **Reading Practice** - AI generates a short passage using words from your library + new vocabulary. Accepts optional topic prompt. Shows furigana, toggleable translation, and word list. Click any word for an inline gloss, or **drag-select a phrase or sentence fragment** to get a natural English translation in a popup. New words can be added to library with one click.
8. **Conversation** - Open-ended Japanese Q&A. The tutor asks a level-appropriate question; you reply by typing or by recording audio (local Whisper transcription). Returns inline corrections, a natural rewrite of your answer, short feedback, and a follow-up question. Each turn is recorded to the study session as it happens.

## JLPT Level Setting

A single sticky setting (N1–N5, default N3) scales AI-generated content: ingest extraction focus, question difficulty, reading-passage length, and conversation topic depth. Items stored in the DB (manual entry or ingest) are always available regardless of the level. Change it from the header dropdown — it's persisted server-side and mirrored in `localStorage` for instant load.

## Running

### Prerequisites
- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Setup
```bash
cp .env.example .env
# Edit .env and add your Anthropic API key

cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
```

### Development
```bash
bash start.sh         # macOS / Linux / Git Bash
.\start.ps1           # Windows PowerShell
# Backend:  http://localhost:8000
# Frontend: http://localhost:5173

bash stop.sh          # or .\stop.ps1 — kills both servers, frees the ports
```

Both start scripts call their stop counterpart first to clear stale processes, then write `.dev-pids.json` so the stop script can tree-kill the servers (and their grandchildren — uvicorn `--reload` and `npm → node` spawn deep trees).

Or run separately:
```bash
# Terminal 1
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd frontend && npm run dev -- --host 0.0.0.0
```

### Testing
```bash
cd backend && uv sync --group dev     # installs pytest once
cd backend && uv run pytest           # runs the suite (<1s)
```
Covers the SRS algorithm, the shared LLM JSON-response parser, and TestClient smoke tests for the non-AI API (items CRUD, study/review/session, settings, health). AI-backed routes (`ingest`, `generate`, `converse`, `transcribe`, `furigana/lookup`) are intentionally not tested — they hit external services.

### Production (single server)
```bash
cd frontend && npm run build && cd ..
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
The backend serves the built frontend from `frontend/dist/` automatically.

### Docker (with PostgreSQL)
```bash
# Copy and fill in at minimum ANTHROPIC_API_KEY
cp .env.example .env

# Build and start (app + PostgreSQL)
docker compose up --build

# App is available at http://localhost:8000
# Migrations run automatically on startup via entrypoint.sh
```

The Docker image sets `WHISPER_ENABLED=false` by default. To enable speech-to-text, set `WHISPER_ENABLED=true` and mount a volume at `/root/.cache/huggingface` so the model persists across restarts.

### Access via Tailscale
Use `--host 0.0.0.0` (already set in the start scripts) to bind to all interfaces, then access via your Tailscale IP.

## Environment Variables

All loaded from `.env` at the project root via `python-dotenv`. See `.env.example`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for Import, AI study, Reading, Converse) | — | Claude API key |
| `DATABASE_URL` | No | — (uses SQLite) | PostgreSQL connection string, e.g. `postgresql+psycopg2://user:pass@host/dbname`. When set, SQLite is not used and Alembic runs migrations on startup. |
| `WHISPER_ENABLED` | No | `true` | Set to `false` to disable speech-to-text entirely. The `/transcribe/` endpoint returns 503 and the mic controls are hidden in the UI. Default is `false` in the Docker image. |
| `WHISPER_MODEL` | No | `kotoba-tech/kotoba-whisper-v2.0-faster` | faster-whisper model name or HF repo. Alternatives: `large-v3-turbo`, `large-v3`, `medium`, `small` |
| `WHISPER_DEVICE` | No | `auto` | `auto` / `cuda` / `cpu`. `auto` picks CUDA if available |
| `WHISPER_COMPUTE_TYPE` | No | `auto` | `auto` / `float16` / `int8_float16` / `int8` / `float32`. `auto` picks `float16` on GPU, `int8` on CPU |
| `TRANSLATION_PROVIDER` | No | `anthropic` | Backend for `/api/furigana/lookup`. `anthropic` calls Claude; `ollama` calls a local Ollama server. |
| `OLLAMA_BASE_URL` | No | `http://host.docker.internal:11434` | Ollama server URL. From WSL, point at the Windows host (enable "Expose Ollama to the network" in the Ollama tray). |
| `OLLAMA_TRANSLATION_MODEL` | No | `qwen3.5:9b` | Ollama model tag used for translation lookups. |

The Kotoba-Whisper default is a Japanese-fine-tuned Whisper variant (~1.5 GB). It downloads to the Hugging Face cache on first transcription call. Not downloaded when `WHISPER_ENABLED=false`.

### Local translations via Ollama (optional)

Set `TRANSLATION_PROVIDER=ollama` to route hover/select word lookups through a local model instead of Claude. Pull the model once on the Ollama host: `ollama pull qwen3.5:9b`. See [`bench_report.html`](./bench_report.html) for the model selection rationale (50-case comparison across 8 providers). Other lookups (ingest, reading-passage generation, conversation tutor) still use Claude.

When the backend boots with `TRANSLATION_PROVIDER=ollama`, it fires a background prewarm against the configured model so the first user lookup doesn't pay the cold-load tax (~3 min for qwen3.5:9b at Q4). The Ollama request also sets `keep_alive: -1` to pin the model in VRAM indefinitely — once loaded it stays loaded until Ollama itself is restarted.

If you also use other Ollama models on the same host, set `OLLAMA_MAX_LOADED_MODELS=2` (or higher) on the Ollama side; otherwise Ollama's default of 1 loaded model will evict qwen3.5:9b every time another model is used and the next lookup will cold-load again.

## Data Flow

### Content Ingestion
Input (text/URL/PDF) -> backend extracts text -> sends to Claude with extraction prompt -> returns extracted vocab/grammar/expressions -> user reviews & selects -> `POST /api/ingest/save` -> creates Source + Items

### Study Session
Select mode -> `POST /study/session/start` -> `GET /study/due` (up to 20 unsuspended items) -> show card/question -> user rates -> `POST /study/review` with `session_id` (updates SRS *and* the session counters in one transaction; may auto-suspend a leech) -> next card -> `POST /study/session/{id}/end` (just stamps `ended_at`; quitting early loses nothing)

### Conversation Turn
`POST /converse/start` returns a question -> user types or records audio -> (audio path: `POST /transcribe/` -> text appended to textarea) -> `POST /converse/reply` with history + user text -> corrections, rewrite, follow-up rendered -> user clicks Continue to loop.

## Design Decisions

- **SQLite by default**: single-user local app, zero setup, easy backup (copy the .db file). PostgreSQL is supported via `DATABASE_URL` for Docker/K8s deployments; schema is managed by Alembic in that path.
- **No auth**: personal tool, secured at network level (Tailscale)
- **Claude Sonnet for ingestion/generation**: balances cost and quality across JLPT levels
- **Simple SRS over SM-2**: three buttons instead of five, easier to use, good enough for personal use
- **"Hard" is not "correct"**: counting it as a success made the accuracy number flatter than reality and hid the cards most worth reworking
- **Leeches are suspended, not deleted**: the word is still worth knowing — the *card* is what's broken. Suspension keeps it out of the queue until it's rewritten, and restoring resets its history so the old failures don't immediately re-trip the threshold
- **Cloze is built from stored examples, not generated**: every enriched item already carries example sentences, so blanking the word out of one costs nothing, returns instantly, and works offline. fugashi lemma matching handles conjugation (済む → 済みました) and phrases that inflect internally (手に入れる → 手に入れた)
- **Browser TTS over server-side audio**: every target platform ships a `ja-JP` voice, so there's no key, no latency, and nothing to cache. Quality varies by OS, which is an acceptable trade for a personal tool
- **Session progress recorded per review**: writing counters only at session end meant an abandoned session logged nothing, which silently erased whole modes from the stats and broke the streak
- **Dark mode only**: personal preference, easier on the eyes for study sessions
- **Local Whisper over cloud STT**: avoids per-minute API costs, keeps audio on-device, runs fast on the 3080. Kotoba-Whisper over vanilla large-v3 because it's Japanese-fine-tuned with better CER at lower latency
- **JLPT level stored server-side**: the app is used from multiple devices over Tailscale, so the DB is the source of truth; `localStorage` is only a cache for first-paint

## Screenshots

![Dashboard](docs/screenshots/dashboard.png)

![Library](docs/screenshots/items.png)
