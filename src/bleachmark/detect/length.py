"""Length-aware detection confidence (FR-49, FR-50).

High-confidence attribution needs about 400 words (research 3, 5), so a short text
gets a low confidence. This is a property of statistical detection power and of the
attribution length, not of any single detector, so it lives on its own.
"""

from __future__ import annotations

ATTRIBUTION_WORDS = 400  # high-confidence attribution length (research 3, 5)


def length_confidence(words: int) -> float:
    """Confidence rises with length and saturates near the attribution length."""
    return max(0.0, min(1.0, words / ATTRIBUTION_WORDS))
