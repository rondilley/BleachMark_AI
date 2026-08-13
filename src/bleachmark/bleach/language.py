"""Detect a language for the meaning gate (FR-27a).

The detector is dependency-free. It votes on Unicode script first. For Latin
script it then votes on function words, so English and Spanish do not share one
metric. The return value is an ISO 639-1 code, or "und" when the script is
unknown.
"""

from __future__ import annotations

from collections import Counter

_FN = {
    "en": {"the", "and", "of", "to", "a", "in", "is", "that", "for", "it", "on", "with"},
    "es": {"el", "la", "de", "que", "y", "en", "los", "las", "un", "una", "por", "con"},
    "fr": {"le", "la", "de", "et", "les", "des", "un", "une", "que", "est", "dans", "pour"},
    "de": {"der", "die", "und", "das", "den", "von", "zu", "ist", "mit", "ein", "auf"},
}


def _script_bucket(ch: str) -> str | None:
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF:
        return "han"
    if 0x3040 <= o <= 0x30FF:
        return "kana"
    if 0xAC00 <= o <= 0xD7AF:
        return "hangul"
    if 0x0600 <= o <= 0x06FF:
        return "arabic"
    if 0x0590 <= o <= 0x05FF:
        return "hebrew"
    if 0x0400 <= o <= 0x04FF:
        return "cyrillic"
    if 0x0900 <= o <= 0x097F:
        return "devanagari"
    if ch.isascii() and ch.isalpha():
        return "latin"
    return None


def detect_language(text: str) -> str:
    """Return a language code from script counts and Latin function words."""
    counts: Counter[str] = Counter()
    for ch in text:
        bucket = _script_bucket(ch)
        if bucket:
            counts[bucket] += 1
    if not counts:
        return "und"
    top, n = counts.most_common(1)[0]
    if top == "kana" or (top == "han" and counts["kana"] > 0):
        return "ja"
    if top == "han":
        return "zh"
    if top == "hangul":
        return "ko"
    if top == "arabic":
        return "ar"
    if top == "hebrew":
        return "he"
    if top == "cyrillic":
        return "ru"
    if top == "devanagari":
        return "hi"
    if top == "latin":
        words = {w.lower() for w in text.split() if w.isalpha()}
        votes = {lang: len(words & fn) for lang, fn in _FN.items()}
        best = max(votes, key=votes.get)
        if votes[best] > 0:
            return best
        return "en"
    return "und"
