import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import Db, UserId
from ..levels import LEVEL_DESCRIPTOR, get_jlpt_level
from ..llm import ai_response, complete_json
from ..models import Item

router = APIRouter(prefix="/api/converse", tags=["converse"])


START_PROMPT = """You are a friendly Japanese conversation tutor. The learner is at JLPT {level} ({descriptor}).

Ask a single open-ended question in Japanese that invites the learner to elaborate (2-4 sentences worth of answer). The question should be appropriate for JLPT {level}:
- N5/N4: concrete, daily-life topics (food, weekend plans, hobbies, weather).
- N3: preferences, past experiences, simple opinions, planning.
- N2: opinions with reasons, comparisons, social topics, travel/culture.
- N1: abstract topics, nuanced opinions, current events, philosophical prompts.

If useful, incorporate a topic that connects loosely to one of these library items (do NOT force it):
{library_words}

Return ONLY valid JSON with keys:
- "topic": short English label for the topic (e.g. "weekend plans")
- "question": the Japanese question (a single sentence, ending with ？)
- "english_hint": a short English gloss of the question for the learner"""


REPLY_PROMPT = """You are a friendly Japanese conversation tutor. The learner is at JLPT {level} ({descriptor}).

Conversation so far (most recent last):
{history}

The learner's latest response (may be messy, include typos or transcription artifacts):
"{user_text}"

Your job:
1. Identify concrete grammar/usage/vocabulary errors. For each, give the original fragment, a corrected version, and a short English note (one line). Skip trivial typos. If the response is completely fine, return an empty list.
2. Provide a single natural, fluent rewrite of their whole response in Japanese appropriate for JLPT {level} (keeping their meaning intact). If they said almost nothing, write a short plausible elaboration that builds on what they said.
3. One short line of encouraging English feedback (1 sentence).
4. A natural Japanese follow-up question that continues the conversation (single sentence ending with ？).

Return ONLY valid JSON with keys:
- "corrections": array of {{"original": "...", "fixed": "...", "note": "..."}} (possibly empty)
- "rewrite": the natural Japanese rewrite
- "feedback": short English encouragement
- "follow_up": the next Japanese question
- "follow_up_hint": short English gloss of the follow-up"""


class StartOut(BaseModel):
    topic: str
    question: str
    english_hint: str


class HistoryTurn(BaseModel):
    role: str  # "tutor" | "learner"
    content: str


class ReplyIn(BaseModel):
    history: list[HistoryTurn] = []
    user_text: str


class Correction(BaseModel):
    original: str
    fixed: str
    note: str


class ReplyOut(BaseModel):
    corrections: list[Correction]
    rewrite: str
    feedback: str
    follow_up: str
    follow_up_hint: str


@router.post("/start", response_model=StartOut)
def start_conversation(user_id: UserId, db: Db):
    level = get_jlpt_level(db, user_id)
    items = db.query(Item).filter(Item.user_id == user_id).all()
    sample = random.sample(items, min(len(items), 8)) if items else []
    library_words = "\n".join(
        f"- {it.japanese} ({it.reading}): {it.meaning}" for it in sample
    ) or "(library empty)"

    with ai_response("converse_start", user_id=user_id):
        data = complete_json(
            START_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                library_words=library_words,
            ),
            max_tokens=512,
        )
        return StartOut(
            topic=data.get("topic", "conversation"),
            question=data["question"],
            english_hint=data.get("english_hint", ""),
        )


@router.post("/reply", response_model=ReplyOut)
def reply(data: ReplyIn, user_id: UserId, db: Db):
    level = get_jlpt_level(db, user_id)

    if not data.user_text.strip():
        raise HTTPException(400, "Empty user response")

    history_lines = []
    for turn in data.history[-10:]:
        label = "Tutor" if turn.role == "tutor" else "Learner"
        history_lines.append(f"{label}: {turn.content}")
    history_text = "\n".join(history_lines) or "(no prior turns)"

    with ai_response("converse_reply", user_id=user_id):
        parsed = complete_json(
            REPLY_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                history=history_text,
                user_text=data.user_text.replace('"', '\\"'),
            ),
            max_tokens=1536,
        )

        # Drop malformed correction entries rather than failing the whole reply —
        # the rewrite and follow-up are still useful without them.
        corrections = [
            Correction(
                original=str(c.get("original", "")),
                fixed=str(c.get("fixed", "")),
                note=str(c.get("note", "")),
            )
            for c in parsed.get("corrections", [])
            if isinstance(c, dict) and c.get("original")
        ]
        return ReplyOut(
            corrections=corrections,
            rewrite=parsed.get("rewrite", ""),
            feedback=parsed.get("feedback", ""),
            follow_up=parsed.get("follow_up", ""),
            follow_up_hint=parsed.get("follow_up_hint", ""),
        )
