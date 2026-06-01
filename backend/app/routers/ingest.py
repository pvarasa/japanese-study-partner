import json

import httpx
from fastapi import APIRouter, Depends, File, Form, UploadFile
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


@router.post("/text", response_model=IngestResponse)
async def ingest_text(
    content: str = Form(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Ingest raw Japanese text."""
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
    result = _extract_with_llm(text, get_jlpt_level(db, user_id))
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
    import io

    import pdfplumber
    content = await file.read()
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages[:20]:  # limit to 20 pages
            text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)
    result = _extract_with_llm(text, get_jlpt_level(db, user_id))
    return IngestResponse(
        source_title=result.get("title", file.filename or "PDF"),
        items=[IngestItem(**item) for item in result.get("items", [])],
    )


@router.post("/save")
async def save_ingested(
    source_title: str = Form(...),
    source_type: str = Form(...),
    source_url: str = Form(None),
    items_json: str = Form(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Save reviewed/edited ingested items to the database."""
    source = Source(user_id=user_id, title=source_title, type=source_type, url=source_url)
    db.add(source)
    db.flush()

    items_data = json.loads(items_json)
    saved = []
    for item_data in items_data:
        tags = _get_or_create_tags(db, item_data.pop("tags", []))
        item = Item(user_id=user_id, source_id=source.id, **item_data)
        item.tags = tags
        db.add(item)
        saved.append(item)

    db.commit()
    return {"ok": True, "saved_count": len(saved), "source_id": source.id}
