import random
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_user_id
from ..llm import call_claude, get_anthropic_client, parse_json_response
from ..models import Item
from ..schemas import ExampleSentence, ReadingPassage, ReadingWord, StudyQuestion
from .settings import LEVEL_DESCRIPTOR, NEW_WORD_TIER, READING_LENGTH, get_jlpt_level

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
For "sentence_build": Give an English sentence and key vocabulary. The answer should be a natural Japanese sentence.
For "grammar_drill": Create a sentence that tests correct usage of the grammar pattern. Provide 4 options.

Return JSON with:
- "prompt": the question text
- "answer": the correct answer
- "options": array of 4 choices (for fill_blank/grammar_drill) or empty array
- "context": optional hint or context

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
    message = call_claude(
        get_anthropic_client(),
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": QUESTION_PROMPT.format(
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
        }],
    )

    data = parse_json_response(message.content[0].text)

    return StudyQuestion(
        type=mode,
        item_id=item.id,
        prompt=data["prompt"],
        answer=data["answer"],
        options=data.get("options", []),
        context=data.get("context"),
    )


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
    message = call_claude(
        get_anthropic_client(),
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": EXAMPLE_SENTENCE_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                type=item.type,
                japanese=item.japanese,
                reading=item.reading or "",
                meaning=item.meaning,
                examples=item.example_sentences or "[]",
            ),
        }],
    )

    data = parse_json_response(message.content[0].text)
    return ExampleSentence(japanese=data["japanese"], english=data["english"])


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
    message = call_claude(
        get_anthropic_client(),
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": READING_PROMPT.format(
                level=level,
                descriptor=LEVEL_DESCRIPTOR[level],
                length=READING_LENGTH[level],
                new_word_tier=NEW_WORD_TIER[level],
                library_words=library_words,
                topic_instruction=topic_instruction,
            ),
        }],
    )

    data = parse_json_response(message.content[0].text)

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
