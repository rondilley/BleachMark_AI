"""Keyless machine-generation scorer with length-aware confidence.

FR-13 to FR-16, FR-49, FR-50. The score is a calibrated machine-generation
likelihood, not watermark identification and not a verdict (FR-13a). It carries a
stated false-positive rate and a confound note for low-perplexity text. The
confidence depends on the text length: high-confidence attribution needs about 400
words, so a short text gets a low confidence (FR-49, FR-50).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from ...decode import DecodedText, word_count
from ...model import Finding, Posture, Severity

_WORD = re.compile(r"\w+", re.UNICODE)
_SENT = re.compile(r"[.!?]+")

ATTRIBUTION_WORDS = 400  # high-confidence attribution length (research 3, 5)


def length_confidence(words: int) -> float:
    """Confidence rises with length and saturates near the attribution length."""
    return max(0.0, min(1.0, words / ATTRIBUTION_WORDS))


def _repetition_rate(words: list[str]) -> float:
    if len(words) < 2:
        return 0.0
    bigrams = Counter(zip(words, words[1:]))
    repeated = sum(c - 1 for c in bigrams.values() if c > 1)
    return repeated / max(1, len(words) - 1)


def _type_token_ratio(words: list[str]) -> float:
    if not words:
        return 1.0
    return len(set(words)) / len(words)


def _burstiness(text: str) -> float:
    lengths = [len(s.split()) for s in _SENT.split(text) if s.strip()]
    if len(lengths) < 2:
        return 0.5
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    cv = math.sqrt(var) / mean  # coefficient of variation
    # human text is burstier (higher cv); machine text is more uniform (lower cv)
    return max(0.0, min(1.0, 1.0 - cv))


class MgtScorer:
    name = "mgt_score"

    def __init__(self, false_positive_rate: float = 0.01):
        self.false_positive_rate = false_positive_rate

    def score(self, text: str) -> float:
        words = [w.lower() for w in _WORD.findall(text)]
        rep = _repetition_rate(words)
        ttr = _type_token_ratio(words)
        uniform = _burstiness(text)
        # more repetition, lower vocabulary richness, and more uniform sentence
        # length push the machine-likelihood up
        raw = 0.4 * rep + 0.3 * (1 - ttr) + 0.3 * uniform
        return max(0.0, min(1.0, raw))

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        words = word_count(text)
        s = self.score(text)
        conf = length_confidence(words)
        notes = [
            "This score is not a verdict and not watermark identification (FR-13a).",
            "A stated false-positive rate applies; a low-perplexity non-native style "
            "is a known confound (research 5).",
        ]
        if words < ATTRIBUTION_WORDS:
            notes.append(
                f"Low confidence: {words} words is below the {ATTRIBUTION_WORDS}-word "
                "attribution length (FR-50)."
            )
        return [
            Finding(
                kind="mgt_score",
                detector=self.name,
                severity=Severity.INFO,
                summary=f"machine-generation score {s:.3f} at {self.false_positive_rate:.2%} FPR",
                posture=Posture.KEYLESS,
                score=s,
                false_positive_rate=self.false_positive_rate,
                confidence=conf,
                notes=notes,
            )
        ]
