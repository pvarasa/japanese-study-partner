import logging
import random
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_user_id
from ..llm import complete_json
from ..models import Item
from ..schemas import ExampleSentence, ReadingPassage, ReadingWord, StudyQuestion, VocabHint
from .settings import LEVEL_DESCRIPTOR, NEW_WORD_TIER, READING_LENGTH, get_jlpt_level

router = APIRouter(prefix="/api/generate", tags=["generate"])

log = logging.getLogger("app.generate")

# Shown to the user when the model call succeeds but the response can't be
# parsed/shaped into what we need (bad JSON, missing keys, etc.). call_claude
# already maps upstream API failures to friendly messages of their own.
_BAD_RESPONSE_MSG = "Couldn't generate this — the AI returned an unexpected response. Please try again."

QUESTION_PROMPT = """You are a Japanese language teaching assistant for a {descriptor} (JLPT {level}) learner.

Generate a study question based on this item:
- Type: {type}
- Japanese: {japanese}
- Reading: {reading}
- Meaning: {meaning}
- Notes: {notes}
- Examples: {examples}

Generate a question of type: {mode}

For "fill_blank": Create a sentence with the target word/grammar blanked out. Provide 4 options.
For "sentence_build": Set "prompt" to ONLY the English sentence the learner should translate into Japanese — no instructions, no vocabulary, no quotation marks. Put the helper words in "vocabulary" instead. The answer should be a natural Japanese sentence.
For "grammar_drill": Create a sentence that tests correct usage of the grammar pattern. Provide 4 options.

Return JSON with:
- "prompt": the question text (for sentence_build, just the plain English sentence to translate)
- "answer": the correct answer
- "options": array of 4 choices (for fill_blank/grammar_drill) or empty array
- "context": optional short hint — for sentence_build, a brief grammar/structure tip in English; do NOT simply restate the full Japanese answer
- "translation": natural English translation of the full sentence (with the blank filled in); include spaces between all words
- "vocabulary": for sentence_build ONLY, an array of 2-4 key words to help, each {{"japanese": dictionary form, "reading": hiragana reading, "meaning": brief English gloss}}; empty array for other types

Return ONLY valid JSON."""


@router.post("/question", response_model=StudyQuestion)
def generate_question(
    item_id: int,
    mode: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()
    if not item:
        raise HTTPException(404, "Item not found")

    level = get_jlpt_level(db, user_id)
    try:
        data = complete_json(
            QUESTION_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                type=item.type,
                japanese=item.japanese,
                reading=item.reading or "",
                meaning=item.meaning,
                notes=item.notes or "",
                examples=item.example_sentences or "[]",
                mode=mode,
            ),
            max_tokens=1024,
        )

        vocabulary = [
            VocabHint(
                japanese=v.get("japanese", ""),
                reading=v.get("reading", ""),
                meaning=v.get("meaning", ""),
            )
            for v in data.get("vocabulary", [])
            if v.get("japanese")
        ]

        return StudyQuestion(
            type=mode,
            item_id=item.id,
            prompt=data["prompt"],
            answer=data["answer"],
            options=data.get("options", []),
            context=data.get("context"),
            translation=data.get("translation"),
            vocabulary=vocabulary,
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("generate_question failed (item_id=%s, mode=%s)", item_id, mode)
        raise HTTPException(status_code=502, detail=_BAD_RESPONSE_MSG)


EXAMPLE_SENTENCE_PROMPT = """You are a Japanese language teaching assistant for a {descriptor} (JLPT {level}) learner.

Generate ONE natural example sentence using this item:
- Japanese: {japanese}
- Reading: {reading}
- Meaning: {meaning}
- Type: {type}

Requirements:
- The sentence must be natural and contextually appropriate
- Match grammar/vocabulary difficulty to JLPT {level}
- Use the word/grammar naturally in context
- Do NOT reuse any of these existing examples: {examples}

Return JSON with:
- "japanese": the example sentence in Japanese
- "english": natural English translation

Return ONLY valid JSON."""


@router.post("/example-sentence", response_model=ExampleSentence)
def generate_example_sentence(
    item_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()
    if not item:
        raise HTTPException(404, "Item not found")

    level = get_jlpt_level(db, user_id)
    try:
        data = complete_json(
            EXAMPLE_SENTENCE_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                type=item.type,
                japanese=item.japanese,
                reading=item.reading or "",
                meaning=item.meaning,
                examples=item.example_sentences or "[]",
            ),
            max_tokens=256,
        )
        return ExampleSentence(japanese=data["japanese"], english=data["english"])
    except HTTPException:
        raise
    except Exception:
        log.exception("generate_example_sentence failed (item_id=%s)", item_id)
        raise HTTPException(status_code=502, detail=_BAD_RESPONSE_MSG)


READING_PROMPT = """You are a Japanese language teaching assistant for a {descriptor} (JLPT {level}) learner.

Write a short, natural Japanese passage ({length} characters). The passage should read like a blog post, diary entry, news snippet, or short essay — something a real person would write. Match the overall grammar and vocabulary difficulty to JLPT {level}.

REQUIREMENTS:
1. Use these words/grammar from the learner's library (try to include at least 5-8 of them naturally):
{library_words}

2. Also introduce 3-5 NEW useful words/expressions that are NOT in the list above. Pick words at {new_word_tier} level that fit the passage naturally.

3. Keep the Japanese natural — don't force words in awkwardly.

{topic_instruction}

Return a JSON object with:
- "title": a short title for the passage (in Japanese)
- "text": the full Japanese passage
- "translation": natural English translation of the passage
- "words": array of ALL key words used, each with:
  - "japanese": the word as it appears (dictionary form for verbs)
  - "reading": hiragana reading
  - "meaning": brief English meaning
  - "in_library": true if from the library list above, false if it's a new word

Return ONLY valid JSON, no markdown fences."""


@router.post("/reading", response_model=ReadingPassage)
def generate_reading(
    prompt: Optional[str] = Form(None),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    items = db.query(Item).filter(Item.user_id == user_id).all()
    if not items:
        raise HTTPException(400, "No items in library yet")

    # Pick a random subset to encourage variety
    sample = random.sample(items, min(len(items), 15))
    library_words = "\n".join(
        f"- {it.japanese} ({it.reading}): {it.meaning}" for it in sample
    )

    topic_instruction = ""
    if prompt:
        topic_instruction = f"TOPIC GUIDANCE: The learner wants the passage to be about: {prompt}"

    level = get_jlpt_level(db, user_id)
    try:
        data = complete_json(
            READING_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                length=READING_LENGTH[level],
                new_word_tier=NEW_WORD_TIER[level],
                library_words=library_words,
                topic_instruction=topic_instruction,
            ),
            # Headroom for Sonnet 5's tokenizer (~30% more tokens than Sonnet 4.6)
            # so a full-length passage + translation + word list isn't truncated.
            max_tokens=3072,
        )

        # Build lookup of library items for matching
        library_set = {it.japanese for it in items}

        words = []
        for w in data.get("words", []):
            words.append(ReadingWord(
                japanese=w["japanese"],
                reading=w.get("reading", ""),
                meaning=w.get("meaning", ""),
                in_library=w["japanese"] in library_set or w.get("in_library", False),
            ))

        return ReadingPassage(
            title=data.get("title", "Reading Practice"),
            text=data["text"],
            words=words,
            translation=data.get("translation", ""),
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("generate_reading failed (user_id=%s)", user_id)
        raise HTTPException(status_code=502, detail=_BAD_RESPONSE_MSG)


EVALUATE_PROMPT = """You are a Japanese language teacher evaluating a student's translation exercise.

English sentence to translate: {prompt}
Reference translation: {expected}
Student's answer: {user_answer}

Evaluate strictly but fairly. Accept natural variations and synonyms that preserve the meaning.
- "correct": meaning is right, grammar is acceptable (minor stylistic differences are fine)
- "partial": the right idea but has a significant grammar, particle, or conjugation error
- "incorrect": wrong meaning, key element missing, or incomprehensible

Return ONLY valid JSON:
- "verdict": "correct", "partial", or "incorrect"
- "feedback": 1-2 sentences of specific English feedback. For correct answers, brief encouragement. For partial/incorrect, name the exact error and why it matters.
- "corrected": for partial or incorrect, a natural corrected Japanese sentence that preserves their intended meaning. null if verdict is "correct"."""


class EvaluateIn(BaseModel):
    user_answer: str
    expected_answer: str
    prompt: str


class EvaluateOut(BaseModel):
    verdict: str
    feedback: str
    corrected: Optional[str] = None


@router.post("/evaluate", response_model=EvaluateOut)
def evaluate_answer(
    data: EvaluateIn,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    try:
        result = complete_json(
            EVALUATE_PROMPT.format(
                prompt=data.prompt,
                expected=data.expected_answer,
                user_answer=data.user_answer,
            ),
            max_tokens=512,
        )
        return EvaluateOut(
            verdict=result.get("verdict", "incorrect"),
            feedback=result.get("feedback", ""),
            corrected=result.get("corrected"),
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("evaluate_answer failed")
        raise HTTPException(status_code=502, detail=_BAD_RESPONSE_MSG)
