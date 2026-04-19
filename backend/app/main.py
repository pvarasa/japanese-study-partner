from pathlib import Path
from dotenv import load_dotenv
# Load .env from project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .routers import items, study, ingest, generate, furigana, settings, transcribe, converse
import os

Base.metadata.create_all(bind=engine)

app = FastAPI(title="日本語 Study Partner", version="0.1.0")

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


# Serve frontend static files in production
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
