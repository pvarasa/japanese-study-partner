from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
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
    srs_correct = Column(Integer, default=0)

    source = relationship("Source", back_populates="items")
    tags = relationship("Tag", secondary=item_tags, back_populates="items")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    items = relationship("Item", secondary=item_tags, back_populates="tags")


class Source(Base):
    """Where study material came from (article, document, manual entry)."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    type = Column(String(20))  # url, pdf, text, manual
    url = Column(Text)
    content = Column(Text)  # original text content
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("Item", back_populates="source")


class Setting(Base):
    """Simple key/value app settings (e.g. jlpt_level)."""
    __tablename__ = "settings"

    key = Column(String(50), primary_key=True)
    value = Column(Text)


class StudySession(Base):
    """Track study sessions for stats."""
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)
    items_reviewed = Column(Integer, default=0)
    items_correct = Column(Integer, default=0)
    mode = Column(String(30))  # flashcard_jp, flashcard_en, fill_blank, sentence_build, converse
