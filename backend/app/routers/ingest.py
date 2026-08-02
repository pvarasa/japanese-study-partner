import json
import logging

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from ..crud import get_or_create_tags
from ..deps import Db, UserId
from ..levels import LEVEL_DESCRIPTOR, get_jlpt_level
from ..llm import ai_response, complete_json
from ..models import Item, Source
from ..schemas import IngestItem, IngestResponse

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

log = logging.getLogger("app.ingest")

MAX_INPUT_CHARS = 8000

# Extraction is the one AI call whose output grows with its input — every other
# one returns a single fixed-shape object. Left uncapped it runs past max_tokens
# on a page of ordinary Japanese (~1800 chars was enough), and the truncated JSON
# then fails to parse. Cap the item count so the reply stays bounded no matter how
# long the source is, and budget enough tokens for a full batch at that cap.
MAX_ITEMS = 25
EXTRACT_MAX_TOKENS = 8192

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

Return at most {max_items} items. If the text contains more than that, pick the {max_items} most valuable ones rather than covering everything.

Return a JSON object with:
- "title": a short title for this source material
- "items": array of extracted items

Return ONLY valid JSON, no markdown fences or explanation."""


def _parse_items(raw_items) -> list[IngestItem]:
    """Validate extracted items, skipping any the model got wrong.

    One malformed entry in a batch of twenty shouldn't cost the user the whole
    import, so bad items are logged and dropped instead of raising.
    """
    parsed = []
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            log.warning("Skipping non-object item in extraction: %.120r", raw)
            continue
        try:
            parsed.append(IngestItem(**raw))
        except ValidationError as e:
            log.warning(
                "Skipping invalid extracted item (%s): %.120r",
                e.errors()[0].get("type", "?"), raw,
            )
    return parsed


async def _fetch_url(url: str) -> str:
    """Fetch a page and strip it to readable text.

    Network and HTTP failures here are the caller's problem (bad or unreachable
    URL), so they surface as 4xx/504 rather than being folded into the generic
    AI-failure path.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise HTTPException(504, "That URL took too long to respond.") from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            400, f"That URL returned HTTP {e.response.status_code}."
        ) from e
    except httpx.RequestError as e:
        log.warning("Failed to fetch %s: %s", url, e)
        raise HTTPException(400, "Couldn't fetch that URL.") from e

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove scripts and styles
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_with_llm(text: str, level: str) -> dict:
    prompt = EXTRACT_PROMPT.format(
        level=level, descriptor=LEVEL_DESCRIPTOR[level], max_items=MAX_ITEMS
    )
    return complete_json(
        f"{prompt}\n\n---\n\n{text[:MAX_INPUT_CHARS]}", max_tokens=EXTRACT_MAX_TOKENS
    )


def _pdf_text(content: bytes) -> str:
    """Extract text from PDF bytes. Blocking — call via threadpool."""
    import io

    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages[:20]:  # limit to 20 pages
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


@router.post("/text", response_model=IngestResponse)
def ingest_text(user_id: UserId, db: Db, content: str = Form(...)):
    """Ingest raw Japanese text."""
    # Plain def so FastAPI runs the blocking Claude extraction in a threadpool
    # instead of on the event loop, where it would freeze every other request.
    level = get_jlpt_level(db, user_id)
    with ai_response("ingest_text", user_id=user_id):
        result = _extract_with_llm(content, level)
        return IngestResponse(
            source_title=result.get("title", "Text input"),
            items=_parse_items(result.get("items")),
        )


@router.post("/url", response_model=IngestResponse)
async def ingest_url(user_id: UserId, db: Db, url: str = Form(...)):
    """Ingest content from a URL."""
    text = await _fetch_url(url)
    level = get_jlpt_level(db, user_id)
    with ai_response("ingest_url", url=url):
        result = await run_in_threadpool(_extract_with_llm, text, level)
        return IngestResponse(
            source_title=result.get("title", url),
            items=_parse_items(result.get("items")),
        )


@router.post("/pdf", response_model=IngestResponse)
async def ingest_pdf(user_id: UserId, db: Db, file: UploadFile = File(...)):
    """Ingest content from a PDF."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty PDF upload")

    level = get_jlpt_level(db, user_id)
    try:
        text = await run_in_threadpool(_pdf_text, content)
    except Exception as e:
        log.warning("Failed to parse PDF %r: %s", file.filename, e)
        raise HTTPException(400, "Couldn't read that PDF — is the file valid?") from e

    if not text.strip():
        raise HTTPException(400, "No extractable text in that PDF (is it a scan?)")

    with ai_response("ingest_pdf", filename=file.filename):
        result = await run_in_threadpool(_extract_with_llm, text, level)
        return IngestResponse(
            source_title=result.get("title", file.filename or "PDF"),
            items=_parse_items(result.get("items")),
        )


@router.post("/save")
def save_ingested(
    user_id: UserId,
    db: Db,
    source_title: str = Form(...),
    source_type: str = Form(...),
    items_json: str = Form(...),
    source_url: str = Form(None),
):
    """Save reviewed/edited ingested items to the database."""
    try:
        raw_items = json.loads(items_json)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"items_json is not valid JSON: {e}")

    if not isinstance(raw_items, list):
        raise HTTPException(422, "items_json must be a JSON array")

    # Validate each item through IngestItem so unexpected keys are dropped
    # (rather than crashing Item(**...) with a 500) and missing required
    # fields surface as a clean 422. Unlike extraction, this payload came from
    # the user's own review step, so a bad item is worth reporting rather than
    # silently dropping.
    try:
        parsed_items = [IngestItem(**item) for item in raw_items]
    except (ValidationError, TypeError) as e:
        raise HTTPException(422, f"Invalid item data: {e}")

    source = Source(user_id=user_id, title=source_title, type=source_type, url=source_url)
    db.add(source)
    db.flush()

    saved = []
    for parsed in parsed_items:
        tags = get_or_create_tags(db, parsed.tags)
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
