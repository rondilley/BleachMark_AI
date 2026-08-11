"""SynthID-Text tournament-sampling detector (FR-19, research 4).

SynthID-Text biases token choice toward a high pseudorandom g-value, so watermarked
text scores an anomalously high mean g-value under the same g-function at detection.
Detection needs the secret key and configuration; the tool does not detect a vendor
production watermark without the vendor key (FR-19a). This is a real, simplified
g-value scheme, testable with a reference generator.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

_MOD = 1 << 32


def _g_value(prev: str, token: str, key: str) -> float:
    h = hashlib.sha256(f"{key}|{prev}|{token}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / _MOD  # uniform in [0, 1)


@dataclass
class SynthIDScheme:
    key: str
    vocab: list[str]
    layers: int = 4  # tournament candidates = 2 ** layers is the config knob

    def g_value(self, prev: str, token: str) -> float:
        return _g_value(prev, token, self.key)

    def generate(self, length: int, seed: int) -> list[str]:
        """Tournament sampling: draw candidates and keep the highest g-value."""
        rng = random.Random(seed)
        candidates = min(len(self.vocab), 2 ** self.layers)
        tokens: list[str] = []
        prev = "<s>"
        for _ in range(length):
            pool = rng.sample(self.vocab, candidates)
            chosen = max(pool, key=lambda t: self.g_value(prev, t))
            tokens.append(chosen)
            prev = chosen
        return tokens

    def mean_g(self, tokens: list[str]) -> float:
        if not tokens:
            return 0.5
        prev = "<s>"
        total = 0.0
        for tok in tokens:
            total += self.g_value(prev, tok)
            prev = tok
        return total / len(tokens)

    def z_score(self, tokens: list[str]) -> float:
        """z of the mean g-value against the null mean 0.5, variance 1/12 per token."""
        n = len(tokens)
        if n == 0:
            return 0.0
        mean = self.mean_g(tokens)
        se = math.sqrt((1 / 12) / n)
        return (mean - 0.5) / se


class SynthIDDetector:
    name = "synthid"

    def __init__(self, scheme: SynthIDScheme, tokenizer=None, z_threshold: float = 4.0):
        from .greenlist import default_tokenizer

        self.scheme = scheme
        self.tokenizer = tokenizer or default_tokenizer
        self.z_threshold = z_threshold

    def detect(self, decoded):
        from ...model import Finding, Posture, Severity

        tokens = self.tokenizer(decoded.text)
        z = self.scheme.z_score(tokens)
        present = z >= self.z_threshold
        fpr = 0.5 * math.erfc(self.z_threshold / math.sqrt(2))
        return [
            Finding(
                kind="synthid",
                detector=self.name,
                severity=Severity.HIGH if present else Severity.INFO,
                summary=f"SynthID mean-g z-score {z:.3f}",
                posture=Posture.KEYED,
                score=z,
                false_positive_rate=fpr,
                confidence=1.0 if present else 0.0,
                notes=["Needs the vendor key; no vendor watermark without it (FR-19a)."],
            )
        ]
