from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from . import srs
from .database import Base

# Many-to-many: items can have multiple tags
item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", Integer, ForeignKey("items.id", ondelete="CASCADE")),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE")),
)


class Item(Base):
    """A study item: word, grammar point, or expression."""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)  # word, grammar, expression
    japanese = Column(Text, nullable=False)
    reading = Column(Text)  # hiragana reading
    meaning = Column(Text, nullable=False)
    notes = Column(Text)
    example_sentences = Column(Text)  # JSON array of {japanese, english} pairs
    jlpt_level = Column(String(5))  # N1-N5
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # SRS fields
    srs_interval = Column(Float, default=0)  # days until next review
    srs_ease = Column(Float, default=2.5)
    srs_due = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    srs_reviews = Column(Integer, default=0)
    # "good" ratings only. Rows created before the hard/correct split also have
    # their "hard" ratings folded in here — there's no way to unmix them after
    # the fact, so treat pre-split accuracy as the lenient (non-lapse) figure.
    srs_correct = Column(Integer, default=0)
    srs_hard = Column(Integer, default=0, nullable=False)
    srs_lapses = Column(Integer, default=0, nullable=False)  # "again" ratings
    # Leeches are pulled out of the review queue until reworked, so a card the
    # learner can't crack stops consuming every session. See app/srs.py.
    suspended = Column(Boolean, default=False, nullable=False)

    source = relationship("Source", back_populates="items")
    tags = relationship("Tag", secondary=item_tags, back_populates="items")

    # Derived SRS figures, exposed through ItemOut so every client reads the
    # same definitions instead of re-deriving them from the raw counters.
    @property
    def pass_rate(self) -> float | None:
        """Share of reviews that weren't lapses ("hard" counts). None if unreviewed."""
        return srs.pass_rate(self)

    @property
    def recall_rate(self) -> float | None:
        """Share of reviews rated "good". None if unreviewed."""
        return srs.recall_rate(self)

    @property
    def is_leech(self) -> bool:
        """Failed often enough to be worth reworking."""
        return srs.is_leech(self)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    items = relationship("Item", secondary=item_tags, back_populates="tags")


class Source(Base):
    """Where study material came from (article, document, manual entry)."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    title = Column(String(500))
    type = Column(String(20))  # url, pdf, text, manual
    url = Column(Text)
    content = Column(Text)  # original text content
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("Item", back_populates="source")


class Setting(Base):
    """Simple key/value app settings (e.g. jlpt_level), keyed per user."""
    __tablename__ = "settings"

    user_id = Column(String(100), primary_key=True)
    key = Column(String(50), primary_key=True)
    value = Column(Text)


class StudySession(Base):
    """Track study sessions for stats."""
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)
    items_reviewed = Column(Integer, default=0)
    items_correct = Column(Integer, default=0)  # "good" ratings only
    items_hard = Column(Integer, default=0)
    mode = Column(String(30))  # flashcard_jp, flashcard_en, cloze, fill_blank, sentence_build, converse
