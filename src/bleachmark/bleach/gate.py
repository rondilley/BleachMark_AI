"""Meaning-preservation gate (FR-27, FR-27a, ARCHITECTURE 6).

The gate is the load-bearing node of the bleach thesis. The metric and the
threshold are language-matched (FR-27a). English uses word and character n-grams.
A language without spaces (Chinese, Japanese) uses character n-grams only. Each
language has its own threshold in data/meaning/thresholds.json (MR-02). A
sentence-embedding metric is an optional upgrade; when it is supplied, its own
threshold applies.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from functools import lru_cache

from .language import detect_language

_WORD = re.compile(r"\w+", re.UNICODE)
_SPEC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "meaning", "thresholds.json"
)


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


@lru_cache(maxsize=1)
def load_language_specs(path: str | None = None) -> dict:
    src = path or _SPEC_PATH
    with open(src, encoding="utf-8") as fh:
        return json.load(fh)


def _norm_lang(language: str | None) -> str:
    if not language:
        return "und"
    return language.split("-")[0].lower()


def spec_for(language: str) -> dict:
    specs = load_language_specs()
    return specs.get(_norm_lang(language)) or specs["und"]


class MeaningGate:
    def __init__(self, threshold: float | None = None, embedding=None,
                 embedding_threshold: float = 0.76):
        self.threshold = threshold
        self.embedding = embedding
        self.embedding_threshold = embedding_threshold

    def threshold_for(self, language: str) -> float:
        if self.embedding is not None:
            return self.embedding_threshold
        if self.threshold is not None:
            return self.threshold
        return float(spec_for(language)["threshold"])

    def similarity(self, before: str, after: str, language: str | None = None) -> float:
        if self.embedding is not None:
            return _dense_cosine(self.embedding(before), self.embedding(after))
        lang = _norm_lang(language or detect_language(before))
        spec = spec_for(lang)
        char_n = int(spec.get("char_n", 3))
        char = _cosine(_char_ngrams(before, char_n), _char_ngrams(after, char_n))
        if spec.get("metric") == "word_char":
            word_n = int(spec.get("word_n", 2))
            word = _cosine(_word_ngrams(before, word_n), _word_ngrams(after, word_n))
            return max(char, word)
        return char

    def passes(self, score: float, language: str | None = None) -> bool:
        lang = _norm_lang(language or "en")
        return score >= self.threshold_for(lang)
