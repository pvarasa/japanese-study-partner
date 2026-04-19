"""Shared helpers for LLM response handling."""
import json


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object from a Claude response.

    Strips optional ```json / ``` markdown fences and surrounding whitespace.
    Raises json.JSONDecodeError if the stripped payload isn't valid JSON.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        if "\n" in raw:
            raw = raw.split("\n", 1)[1]
        else:
            raw = raw[3:]
        raw = raw.rstrip()
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()
    return json.loads(raw)
