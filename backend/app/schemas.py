from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


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


class SRSReview(BaseModel):
    item_id: int
    rating: Literal["again", "hard", "good"]


class IngestRequest(BaseModel):
    content: str  # raw text, URL, or "uploaded file" marker
    type: str  # text, url, pdf


class IngestItem(BaseModel):
    type: str
    japanese: str
    reading: Optional[str] = None
    meaning: str
    notes: Optional[str] = None
    example_sentences: Optional[str] = None
    jlpt_level: Optional[str] = None
    tags: list[str] = []


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
