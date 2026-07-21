import json

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_user_id
from ..llm import complete_json
from ..models import Item, Source
from ..schemas import IngestItem, IngestResponse
from .items import _get_or_create_tags
from .settings import LEVEL_DESCRIPTOR, get_jlpt_level

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

EXTRACT_PROMPT = """You are a Japanese language teaching assistant. The user is at JLPT {level} level ({descriptor}).

Analyze the following Japanese content and extract study materials. For each item, provide:
- type: "word", "grammar", or "expression"
- japanese: the Japanese text
- reading: hiragana reading (for words/expressions)
- meaning: English meaning
- notes: brief usage notes if helpful
- example_sentences: JSON string of array with objects {{"japanese": "...", "english": "..."}}
- jlpt_level: estimated JLPT level (N1-N5)
- tags: relevant tags as array of strings

Focus on items that would be most useful for a JLPT {level} learner:
1. Vocabulary words at or slightly above {level}
2. Grammar patterns at or slightly above {level}
3. Useful expressions or collocations
4. Idiomatic phrases

Skip items that are clearly far below the learner's level unless they are genuinely useful (e.g. common idioms). Prefer items that stretch the learner a little.

Return a JSON object with:
- "title": a short title for this source material
- "items": array of extracted items

Return ONLY valid JSON, no markdown fences or explanation."""


async def _fetch_url(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)


def _extract_with_llm(text: str, level: str) -> dict:
    prompt = EXTRACT_PROMPT.format(level=level, descriptor=LEVEL_DESCRIPTOR[level])
    return complete_json(f"{prompt}\n\n---\n\n{text[:8000]}", max_tokens=4096)


def _extract_pdf(content: bytes, level: str) -> dict:
    """Parse PDF bytes and run extraction. Blocking — call via threadpool."""
    import io

    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages[:20]:  # limit to 20 pages
            text_parts.append(page.extract_text() or "")
    return _extract_with_llm("\n".join(text_parts), level)


@router.post("/text", response_model=IngestResponse)
def ingest_text(
    content: str = Form(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Ingest raw Japanese text."""
    # Plain def so FastAPI runs the blocking Claude extraction in a threadpool
    # instead of on the event loop, where it would freeze every other request.
    result = _extract_with_llm(content, get_jlpt_level(db, user_id))
    return IngestResponse(
        source_title=result.get("title", "Text input"),
        items=[IngestItem(**item) for item in result.get("items", [])],
    )


@router.post("/url", response_model=IngestResponse)
async def ingest_url(
    url: str = Form(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Ingest content from a URL."""
    text = await _fetch_url(url)
    level = get_jlpt_level(db, user_id)
    result = await run_in_threadpool(_extract_with_llm, text, level)
    return IngestResponse(
        source_title=result.get("title", url),
        items=[IngestItem(**item) for item in result.get("items", [])],
    )


@router.post("/pdf", response_model=IngestResponse)
async def ingest_pdf(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Ingest content from a PDF."""
    content = await file.read()
    level = get_jlpt_level(db, user_id)
    result = await run_in_threadpool(_extract_pdf, content, level)
    return IngestResponse(
        source_title=result.get("title", file.filename or "PDF"),
        items=[IngestItem(**item) for item in result.get("items", [])],
    )


@router.post("/save")
def save_ingested(
    source_title: str = Form(...),
    source_type: str = Form(...),
    source_url: str = Form(None),
    items_json: str = Form(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Save reviewed/edited ingested items to the database."""
    try:
        raw_items = json.loads(items_json)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"items_json is not valid JSON: {e}")

    # Validate each item through IngestItem so unexpected keys are dropped
    # (rather than crashing Item(**...) with a 500) and missing required
    # fields surface as a clean 422.
    try:
        parsed_items = [IngestItem(**item) for item in raw_items]
    except (ValidationError, TypeError) as e:
        raise HTTPException(422, f"Invalid item data: {e}")

    source = Source(user_id=user_id, title=source_title, type=source_type, url=source_url)
    db.add(source)
    db.flush()

    saved = []
    for parsed in parsed_items:
        tags = _get_or_create_tags(db, parsed.tags)
        item = Item(
            user_id=user_id,
            source_id=source.id,
            **parsed.model_dump(exclude={"tags"}),
        )
        item.tags = tags
        db.add(item)
        saved.append(item)

    db.commit()
    return {"ok": True, "saved_count": len(saved), "source_id": source.id}
