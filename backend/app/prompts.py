"""Shared building blocks for AI prompts.

Kept apart from ``crud.py`` (data access) and ``llm.py`` (the API round-trip):
these only turn already-loaded rows into prompt text.
"""
from .models import Item


def format_library_lines(items: list[Item]) -> str:
    """Render items as the "- japanese (reading): meaning" lines several AI
    prompts (reading passages, conversation starters) use to show library context."""
    return "\n".join(f"- {it.japanese} ({it.reading}): {it.meaning}" for it in items)
