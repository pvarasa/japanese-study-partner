from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import converse, furigana, generate, ingest, items, settings, study, transcribe
from .routers.transcribe import whisper_enabled
from .sqlite_migrate import ensure_columns
from .translation import prewarm as prewarm_translation

# SQLite only — PostgreSQL schema is managed by Alembic (run via entrypoint)
if not os.environ.get("DATABASE_URL"):
    Base.metadata.create_all(bind=engine)
    # create_all builds missing tables but never alters existing ones, so an
    # older nihongo.db needs new columns added explicitly.
    ensure_columns(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick off the Ollama model load in the background so it doesn't block
    # uvicorn from accepting connections. The first user lookup will join the
    # in-flight load if it isn't done yet. Hold a reference on app.state so the
    # task isn't garbage-collected mid-flight.
    app.state.prewarm_task = asyncio.create_task(prewarm_translation())
    yield


app = FastAPI(title="日本語 Study Partner", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router)
app.include_router(study.router)
app.include_router(ingest.router)
app.include_router(generate.router)
app.include_router(furigana.router)
app.include_router(settings.router)
app.include_router(transcribe.router)
app.include_router(converse.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/features")
def features():
    return {"whisper_enabled": whisper_enabled()}


# Serve frontend static files in production
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
