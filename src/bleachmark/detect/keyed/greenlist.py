"""Green-list z-test, the Kirchenbauer scheme (FR-18, research 3).

The whole signal reduces to one count: how many tokens fall in the green list. The
detector recomputes the per-position green list from the key and runs a
one-proportion z-test. This is the only clean statistic (research 3). The scheme is
implemented at the token level with a supplied tokenizer, so it needs no external
model and is fully testable.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from ...decode import DecodedText
from ...model import Finding, Posture, Severity


_MOD = 1 << 32


def _is_green(prev_token: str, token: str, key: str, gamma: float) -> bool:
    """O(1) green-list membership via a hash threshold.

    A token is green for a position when the keyed hash of (prev, token) falls in
    the bottom gamma-fraction of the hash space. Marginally this puts a gamma
    fraction of the vocabulary in the green list, with no per-position sort.
    """
    h = hashlib.sha256(f"{key}|{prev_token}|{token}".encode("utf-8")).digest()
    val = int.from_bytes(h[:4], "big")
    return val < gamma * _MOD


def default_tokenizer(text: str) -> list[str]:
    return [t for t in text.split() if t]


@dataclass
class GreenListScheme:
    key: str
    vocab: list[str]
    gamma: float = 0.25

    def is_green(self, prev_token: str, token: str) -> bool:
        return _is_green(prev_token, token, self.key, self.gamma)

    def green_set(self, prev_token: str) -> set[str]:
        return {t for t in self.vocab if self.is_green(prev_token, t)}

    def count_green(self, tokens: list[str]) -> tuple[int, int]:
        """Return (green_count, scored_count) over the token sequence."""
        vocab_set = set(self.vocab)
        green = 0
        scored = 0
        prev = "<s>"
        for tok in tokens:
            if tok in vocab_set:
                scored += 1
                if self.is_green(prev, tok):
                    green += 1
            prev = tok
        return green, scored

    def z_score(self, tokens: list[str]) -> float:
        green, scored = self.count_green(tokens)
        if scored == 0:
            return 0.0
        expected = self.gamma * scored
        var = scored * self.gamma * (1 - self.gamma)
        if var <= 0:
            return 0.0
        return (green - expected) / math.sqrt(var)


class GreenListDetector:
    name = "greenlist"

    def __init__(self, scheme: GreenListScheme, tokenizer=default_tokenizer, z_threshold: float = 4.0):
        self.scheme = scheme
        self.tokenizer = tokenizer
        self.z_threshold = z_threshold

    def detect(self, decoded: DecodedText) -> list[Finding]:
        tokens = self.tokenizer(decoded.text)
        z = self.scheme.z_score(tokens)
        # a z of 4 corresponds to a one-sided false-positive rate near 3e-5
        fpr = 0.5 * math.erfc(self.z_threshold / math.sqrt(2))
        present = z >= self.z_threshold
        sev = Severity.HIGH if present else Severity.INFO
        return [
            Finding(
                kind="greenlist_ztest",
                detector=self.name,
                severity=sev,
                summary=f"green-list z-score {z:.3f} (threshold {self.z_threshold})",
                posture=Posture.KEYED,
                score=z,
                false_positive_rate=fpr,
                confidence=1.0 if present else 0.0,
                notes=["The clean keyed statistic (research 3)."],
            )
        ]
