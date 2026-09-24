"""Kanji-level views over the learner's own library, for the reading drill.

Pure functions — no DB access, no HTTP. The reading drill uses them to decide
which items get a reading card, to show on the reveal the other words in the
library that share each kanji, and to point at which of a kanji's readings
the word uses. Seeing 決断 (けつだん) next to 断る (ことわる) teaches the
on/kun split from words the learner already knows. The per-kanji facts
themselves (readings, mnemonic, origin) come from ``app.kanji_details``.
"""
import re
from collections.abc import Iterable

from .models import Item

# Grammar points are patterns (〜に対して), not vocabulary to read aloud.
READING_TYPES = ("word", "expression")

# CJK Unified Ideographs plus Extension A. Deliberately excludes 々 (U+3005):
# it repeats the previous kanji rather than being one to learn.
_KANJI = re.compile(r"[㐀-䶿一-鿿]")

# How many sibling words to list per kanji — enough to show a reading pattern
# without turning the reveal into a scrolling list.
MAX_SIBLINGS = 4


def kanji_in(text: str) -> list[str]:
    """Distinct kanji in ``text``, in order of first appearance."""
    return list(dict.fromkeys(_KANJI.findall(text or "")))


def is_reading_candidate(item: Item) -> bool:
    """Whether an item is worth drilling for its reading: vocabulary that
    contains kanji and has a stored reading to check against."""
    return (
        item.type in READING_TYPES
        and bool((item.reading or "").strip())
        and bool(kanji_in(item.japanese))
    )


def to_hiragana(text: str) -> str:
    """Katakana → hiragana; everything else passes through."""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


# Sound changes a reading undergoes inside a compound: rendaku voices the first
# kana (人 ひと → 人々 ひとびと, 会社 しゃ → がいしゃ) and a trailing つ/く/ち/き
# can geminate (学 がく → 学校 がっこう).
_VOICED = dict(zip(
    "かきくけこさしすせそたちつてとはひふへほ",
    "がぎぐげござじずぜぞだぢづでどばびぶべぼ",
))
_SEMI_VOICED = dict(zip("はひふへほ", "ぱぴぷぺぽ"))


def _sound_variants(stem: str) -> list[str]:
    variants = [stem]
    for table in (_VOICED, _SEMI_VOICED):
        if stem[0] in table:
            variants.append(table[stem[0]] + stem[1:])
    if len(stem) > 1 and stem[-1] in "つくちき":
        variants += [v[:-1] + "っ" for v in list(variants)]
    return variants


def readings_in_word(word: str, reading: str, details: dict[str, dict]) -> dict[str, dict]:
    """Guess which of each kanji's readings a word uses.

    ``details`` maps kanji → ``{"onyomi": [...], "kunyomi": [...]}`` in
    KANJIDIC notation (kun okurigana after a ".", affix markers as "-"). Kanji
    are matched left to right against the word's reading, each taking the
    earliest match after the previous one — longest on a tie, then the reading
    whose okurigana is what follows the kanji in ``word``; the kana between
    them is okurigana. Returns kanji → ``{"reading", "kind"}`` where
    ``reading`` is the entry exactly as listed, so the caller can highlight it.

    A heuristic: irregular readings (今日 きょう, 大人 おとな) match nothing
    and are simply left out rather than guessed.
    """
    target = to_hiragana((reading or "").split("/")[0].split("・")[0].replace(" ", ""))
    found: dict[str, dict] = {}
    cursor = 0
    for k in kanji_in(word):
        info = details.get(k)
        if not info:
            continue
        # Kana written right after the kanji — its okurigana, if it has any.
        # Breaks ties between kun readings sharing a stem (立てる: た.てる, not た.つ).
        after = to_hiragana(word[word.index(k) + 1:])
        best = None  # (index, -length, okurigana mismatch, listed, kind, matched_len)
        for kind, key in (("on", "onyomi"), ("kun", "kunyomi")):
            for listed in info.get(key) or []:
                stem, _, okurigana = to_hiragana(listed.strip("-")).partition(".")
                if not stem:
                    continue
                mismatch = 0 if okurigana and after.startswith(okurigana) else 1
                for v in _sound_variants(stem):
                    i = target.find(v, cursor)
                    if i >= 0 and (best is None or (i, -len(v), mismatch) < best[:3]):
                        best = (i, -len(v), mismatch, listed, kind, len(v))
        if best:
            found[k] = {"reading": best[3], "kind": best[4]}
            cursor = best[0] + best[5]
    return found


def kanji_families(item: Item, library: Iterable[Item]) -> list[dict]:
    """For each kanji in ``item``, the other library words that contain it.

    Kanji with no siblings are still listed (with an empty ``words``) so the
    frontend can render the word's kanji in order either way.
    """
    families = []
    for k in kanji_in(item.japanese):
        words = [
            {"japanese": other.japanese, "reading": other.reading or "", "meaning": other.meaning}
            for other in library
            if other.id != item.id and k in other.japanese
        ][:MAX_SIBLINGS]
        families.append({"kanji": k, "words": words})
    return families
