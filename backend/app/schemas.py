import json
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ItemCreate(BaseModel):
    type: str  # word, grammar, expression
    japanese: str
    reading: Optional[str] = None
    meaning: str
    notes: Optional[str] = None
    example_sentences: Optional[str] = None  # JSON string
    jlpt_level: Optional[str] = None
    source_id: Optional[int] = None
    tags: list[str] = []


class ItemUpdate(BaseModel):
    japanese: Optional[str] = None
    reading: Optional[str] = None
    meaning: Optional[str] = None
    notes: Optional[str] = None
    example_sentences: Optional[str] = None
    jlpt_level: Optional[str] = None
    tags: Optional[list[str]] = None


class ItemOut(BaseModel):
    id: int
    type: str
    japanese: str
    reading: Optional[str]
    meaning: str
    notes: Optional[str]
    example_sentences: Optional[str]
    jlpt_level: Optional[str]
    source_id: Optional[int]
    created_at: datetime
    srs_interval: float
    srs_ease: float
    srs_due: datetime
    srs_reviews: int
    srs_correct: int
    tags: list[str] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def _flatten_tags(cls, v):
        """Accept the ORM's list[Tag] as well as a plain list[str].

        Lets routers use ``ItemOut.model_validate(item)`` directly instead of
        hand-copying every column, which used to drift whenever one was added.
        """
        if v is None:
            return []
        return [t.name if hasattr(t, "name") else t for t in v]


class SRSReview(BaseModel):
    item_id: int
    rating: Literal["again", "hard", "good"]


class IngestItem(BaseModel):
    type: str
    japanese: str
    reading: Optional[str] = None
    meaning: str
    notes: Optional[str] = None
    example_sentences: Optional[str] = None
    jlpt_level: Optional[str] = None
    tags: list[str] = []

    @field_validator("example_sentences", mode="before")
    @classmethod
    def _serialise_examples(cls, v):
        """Accept the array form the model often returns instead of a JSON string.

        The extraction prompt asks for a JSON *string* nested inside a JSON
        object, which models routinely flatten into a real array. Both forms
        mean the same thing, so normalise rather than 422 the whole import.
        """
        if v is None or isinstance(v, str):
            return v
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)


class IngestResponse(BaseModel):
    source_title: str
    items: list[IngestItem]


class VocabHint(BaseModel):
    japanese: str
    reading: str = ""
    meaning: str = ""


class StudyQuestion(BaseModel):
    type: str  # flashcard, fill_blank, sentence_build, grammar_drill
    item_id: int
    prompt: str
    answer: str
    options: list[str] = []  # for multiple choice
    context: Optional[str] = None
    translation: Optional[str] = None
    vocabulary: list[VocabHint] = []  # key-word hints for sentence_build


class ReadingWord(BaseModel):
    japanese: str
    reading: str
    meaning: str
    in_library: bool


class ReadingPassage(BaseModel):
    title: str
    text: str
    words: list[ReadingWord]
    translation: str


class ExampleSentence(BaseModel):
    japanese: str
    english: str


class DashboardStats(BaseModel):
    total_items: int
    due_today: int
    studied_today: int
    accuracy_today: float
    weak_items: list[ItemOut]
    recent_items: list[ItemOut]
    streak_days: int
