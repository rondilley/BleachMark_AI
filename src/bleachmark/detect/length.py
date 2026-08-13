"""Length-aware detection confidence (FR-49, FR-50).

High-confidence attribution needs more than 400 words (research 3, 5), so a short
text gets a low confidence. A generation below that floor is not useful for a
watermark or attribution test. This is a property of statistical detection power,
not of any single detector, so it lives on its own.
"""

from __future__ import annotations

from ..decode import word_count

ATTRIBUTION_WORDS = 400  # high-confidence attribution length (research 3, 5)
MIN_USEFUL_WORDS = ATTRIBUTION_WORDS + 1  # strictly more than 400
USEFUL_MAX_TOKENS = 4096  # room for more than 400 words after a reasoning model spends budget


def length_confidence(words: int) -> float:
    """Confidence rises with length and saturates near the attribution length."""
    return max(0.0, min(1.0, words / ATTRIBUTION_WORDS))


def is_useful_length(text: str) -> bool:
    """True only when the text is more than 400 words."""
    return word_count(text) > ATTRIBUTION_WORDS


def length_requirement() -> str:
    """Clause every generation prompt must carry. Shorter output is rejected."""
    return (
        f"The output must be more than {ATTRIBUTION_WORDS} words. "
        "Shorter output is not useful and is rejected."
    )
