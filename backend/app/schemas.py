import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ItemCreate(BaseModel):
    type: str  # word, grammar, expression
    japanese: str
    reading: str | None = None
    meaning: str
    notes: str | None = None
    example_sentences: str | None = None  # JSON string
    jlpt_level: str | None = None
    source_id: int | None = None
    tags: list[str] = []


class ItemUpdate(BaseModel):
    japanese: str | None = None
    reading: str | None = None
    meaning: str | None = None
    notes: str | None = None
    example_sentences: str | None = None
    jlpt_level: str | None = None
    tags: list[str] | None = None


class ItemOut(BaseModel):
    id: int
    type: str
    japanese: str
    reading: str | None
    meaning: str
    notes: str | None
    example_sentences: str | None
    jlpt_level: str | None
    source_id: int | None
    created_at: datetime
    srs_interval: float
    srs_ease: float
    srs_due: datetime
    srs_reviews: int
    srs_correct: int
    srs_hard: int
    srs_lapses: int
    suspended: bool
    # Derived on the model so clients don't re-implement the arithmetic.
    # Both are None until the item has been reviewed at least once.
    pass_rate: float | None
    recall_rate: float | None
    is_leech: bool
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


class ReadingCardStats(BaseModel):
    """SRS state of an item's reading card (see models.ReadingCard)."""
    srs_interval: float
    srs_due: datetime
    srs_reviews: int
    srs_correct: int
    srs_hard: int
    srs_lapses: int

    model_config = ConfigDict(from_attributes=True)


class KanjiSibling(BaseModel):
    japanese: str
    reading: str
    meaning: str
    jlpt_level: str | None = None


class KanjiFamily(BaseModel):
    """One kanji of a word, plus the other library words that contain it."""
    kanji: str
    words: list[KanjiSibling] = []


class KanjiComponent(BaseModel):
    part: str
    meaning: str = ""


class KanjiExampleWord(BaseModel):
    word: str
    reading: str = ""
    meaning: str
    link: str = ""  # how the kanji's meaning shows up in the word
    jlpt_level: str | None = None


class KanjiDetail(BaseModel):
    """Cached facts about one kanji (models.KanjiInfo), plus which of its
    readings the requested word uses — a best guess, None when irregular."""
    kanji: str
    meaning: str
    onyomi: list[str] = []
    kunyomi: list[str] = []
    jlpt_level: str | None = None
    strokes: int | None = None
    components: list[KanjiComponent] = []
    origin: str = ""
    example_words: list[KanjiExampleWord] = []
    reading_in_word: str | None = None
    reading_kind: Literal["on", "kun"] | None = None


class KanjiMarkIn(BaseModel):
    """Body of ``PUT /kanji/marks/{kanji}``. A missing note keeps the stored one,
    so re-marking from the drill can't wipe what was written on the Kanji page."""
    note: str | None = None


class MarkedKanji(BaseModel):
    """A marked kanji with what the Kanji page shows for it. ``detail`` is None
    when the kanji's facts were never generated (its reveal failed to load)."""
    kanji: str
    note: str = ""
    created_at: datetime | None = None
    detail: KanjiDetail | None = None
    words: list[KanjiSibling] = []  # library words containing it, capped
    word_count: int = 0             # how many there are in all


class ReadingItemOut(ItemOut):
    """An item served for the kanji-reading drill.

    ``reading_card`` is None for an item that has never had a reading review.
    """
    reading_card: ReadingCardStats | None = None
    kanji: list[KanjiFamily] = []


class SRSReview(BaseModel):
    item_id: int
    rating: Literal["again", "hard", "good"]
    # Which SRS track the rating applies to: the item's own (meaning recall)
    # or its reading card (see models.ReadingCard).
    card: Literal["meaning", "reading"] = "meaning"
    # When present the server folds this review into the session's counters, so
    # progress survives abandoning the session part-way. See routers/study.py.
    session_id: int | None = None
    # Practice reps are extra drilling outside the SRS schedule — the server
    # records the rep but leaves the item's schedule/history untouched.
    practice: bool = False


class SessionProgress(BaseModel):
    """Incremental counter deltas for study modes that aren't item reviews."""
    reviewed: int = 0
    correct: int = 0
    hard: int = 0


class IngestItem(BaseModel):
    type: str
    japanese: str
    reading: str | None = None
    meaning: str
    notes: str | None = None
    example_sentences: str | None = None
    jlpt_level: str | None = None
    tags: list[str] = []
    # Set server-side on the extraction response only, when `japanese` matches
    # an item already in the user's library (or repeats earlier in the same
    # batch). Not an input field, but accepted here too so the review step's
    # save request round-trips the same shape without a 422.
    duplicate: bool = False

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
    type: str  # flashcard, cloze, fill_blank, sentence_build, grammar_drill
    item_id: int
    prompt: str
    answer: str
    options: list[str] = []  # for multiple choice
    context: str | None = None
    translation: str | None = None
    vocabulary: list[VocabHint] = []  # key-word hints for sentence_build
    # Alternate spellings graded as correct (cloze accepts the kana reading as
    # well as the kanji, so the mode works without a Japanese IME).
    accepted: list[str] = []


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


class DayStat(BaseModel):
    date: str  # local calendar day, YYYY-MM-DD
    reviewed: int
    correct: int
    hard: int
    accuracy: float  # strict: "good" as a share of reviews


class DashboardStats(BaseModel):
    total_items: int
    due_today: int
    studied_today: int
    accuracy_today: float
    weak_items: list[ItemOut]
    recent_items: list[ItemOut]
    streak_days: int
    leeches: list[ItemOut] = []
    suspended_count: int = 0
    marked_kanji: int = 0


# --- Sentence-build evaluation (routers/generate.py) ---

class EvaluateIn(BaseModel):
    user_answer: str
    expected_answer: str
    prompt: str


class EvaluateOut(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    feedback: str
    corrected: str | None = None


# --- Settings (routers/settings.py) ---

class SettingsOut(BaseModel):
    jlpt_level: str


class SettingsUpdate(BaseModel):
    jlpt_level: str | None = None


# --- Furigana / tokenize / lookup (routers/furigana.py) ---

class FuriganaRequest(BaseModel):
    texts: list[str]


class FuriganaResponse(BaseModel):
    results: list[str]


class TokenizeWord(BaseModel):
    japanese: str
    reading: str
    meaning: str


class TokenizeRequest(BaseModel):
    text: str
    words: list[TokenizeWord] = []


class Token(BaseModel):
    surface: str
    reading: str
    meaning: str
    lemma: str = ""


class TokenizeResponse(BaseModel):
    tokens: list[Token]


class LookupRequest(BaseModel):
    surface: str
    lemma: str = ""
    context: str = ""
    is_phrase: bool = False


class LookupResponse(BaseModel):
    meaning: str
    reading: str = ""


# --- Conversation tutor (routers/converse.py) ---

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
