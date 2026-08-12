"""Meaning-preservation gate (FR-27, FR-27a, ARCHITECTURE 6).

The gate is the load-bearing node of the bleach thesis. The default metric is a
token n-gram cosine similarity, a real and computable proxy. For non-English text
the gate falls back to a character n-gram metric (FR-27a). A sentence-embedding
P-SP metric with the English human band near 0.76 is the documented optional
upgrade; when that metric is supplied its own threshold applies.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"\w+", re.UNICODE)


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[t] * b[t] for t in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def _dense_cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two dense embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def _word_ngrams(text: str, n: int = 2) -> Counter:
    words = _WORD.findall(text.lower())
    grams = list(words)
    grams += [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
    return Counter(grams)


def _char_ngrams(text: str, n: int = 3) -> Counter:
    t = text.lower()
    return Counter(t[i : i + n] for i in range(len(t) - n + 1))


class MeaningGate:
    def __init__(self, threshold: float = 0.6, embedding=None, embedding_threshold: float = 0.76):
        self.threshold = threshold
        self.embedding = embedding  # optional callable(text)->vector
        self.embedding_threshold = embedding_threshold

    def similarity(self, before: str, after: str, language: str = "en") -> float:
        if self.embedding is not None:
            return _dense_cosine(self.embedding(before), self.embedding(after))
        # A character n-gram cosine is robust to a small meaning-preserving edit
        # (a contraction, a punctuation swap) and still drops for a destructive
        # change. The English word-band P-SP metric is the documented upgrade.
        char = _cosine(_char_ngrams(before), _char_ngrams(after))
        if language.lower().startswith("en"):
            word = _cosine(_word_ngrams(before), _word_ngrams(after))
            return max(char, word)
        return char

    def passes(self, score: float) -> bool:
        thr = self.embedding_threshold if self.embedding is not None else self.threshold
        return score >= thr
