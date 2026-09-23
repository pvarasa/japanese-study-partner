import random
from typing import Literal, Optional

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from ..cloze import build_cloze
from ..crud import format_library_lines
from ..deps import Db, OwnedItem, UserId
from ..enrich import build_example_sentence
from ..levels import LEVEL_DESCRIPTOR, NEW_WORD_TIER, READING_LENGTH, get_jlpt_level
from ..llm import ai_response, complete_json
from ..models import Item
from ..schemas import ExampleSentence, ReadingPassage, ReadingWord, StudyQuestion, VocabHint

router = APIRouter(prefix="/api/generate", tags=["generate"])

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


QuestionMode = Literal["cloze", "fill_blank", "sentence_build", "grammar_drill"]


def _checked_options(options: list, answer: str) -> list[str]:
    """Shuffle the choices, rejecting a set the learner couldn't answer.

    Grading is an exact match against ``answer``, so a reply whose answer isn't
    literally one of the options would mark every choice wrong and schedule a
    lapse. Raising here lets ``ai_response`` turn it into a retryable 502. The
    shuffle stops the model's habit of always putting the answer in one slot.
    """
    options = [str(o) for o in options]
    if options and answer not in options:
        raise ValueError(f"answer {answer!r} is not among the options {options!r}")
    random.shuffle(options)
    return options


@router.post("/question", response_model=StudyQuestion)
def generate_question(item: OwnedItem, mode: QuestionMode, user_id: UserId, db: Db):
    # Cloze is built from the item's stored example sentences, so it costs no
    # AI call and returns instantly. Handled before the Claude path rather than
    # as its own endpoint so the frontend keeps a single question-fetch flow.
    if mode == "cloze":
        return _cloze_question(item)

    level = get_jlpt_level(db, user_id)
    with ai_response("generate_question", item_id=item.id, mode=mode):
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
            options=_checked_options(data.get("options") or [], data["answer"]),
            context=data.get("context"),
            translation=data.get("translation"),
            vocabulary=vocabulary,
        )


def _cloze_question(item: Item) -> StudyQuestion:
    """Blank the item out of one of its own example sentences.

    422 rather than 500 when the word can't be located in any stored example:
    it's an expected gap (bare items added before enrichment, or a sentence
    that paraphrases instead of using the word), and the frontend skips the
    item rather than stalling the session.
    """
    data = build_cloze(item)
    if not data:
        raise HTTPException(
            422,
            f"No example sentence for {item.japanese} contains the word — "
            "generate one from the card first.",
        )
    return StudyQuestion(
        type="cloze",
        item_id=item.id,
        prompt=data["prompt"],
        answer=data["answer"],
        accepted=data["accepted"],
        translation=data["translation"],
        context=item.meaning,
    )


@router.post("/example-sentence", response_model=ExampleSentence)
def generate_example_sentence(item: OwnedItem, user_id: UserId, db: Db):
    level = get_jlpt_level(db, user_id)
    with ai_response("generate_example_sentence", item_id=item.id):
        data = build_example_sentence(
            item_type=item.type,
            japanese=item.japanese,
            reading=item.reading,
            meaning=item.meaning,
            level=level,
            existing=item.example_sentences,
        )
        return ExampleSentence(**data)


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
def generate_reading(user_id: UserId, db: Db, prompt: Optional[str] = Form(None)):
    # Random subset for variety, sampled in SQL rather than loading every row.
    sample = (
        db.query(Item).filter(Item.user_id == user_id)
        .order_by(func.random()).limit(15).all()
    )
    if not sample:
        raise HTTPException(400, "No items in library yet")
    library_words = format_library_lines(sample)

    topic_instruction = ""
    if prompt:
        topic_instruction = f"TOPIC GUIDANCE: The learner wants the passage to be about: {prompt}"

    level = get_jlpt_level(db, user_id)
    with ai_response("generate_reading", user_id=user_id):
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

        # The passage may use any library word, not just the sampled ones.
        library_set = {
            j for (j,) in db.query(Item.japanese).filter(Item.user_id == user_id)
        }

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
def evaluate_answer(data: EvaluateIn, user_id: UserId, db: Db):
    with ai_response("evaluate_answer"):
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
