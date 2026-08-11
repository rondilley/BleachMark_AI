"""The adversarial arena: a known stego embedder and an estimating detector.

Embedder (fixed, known modality): a green-list watermark over k structural
variants per slot. A "slot" is a place in the output where the model picks among k
equivalent structural choices (for example a+b versus b+a). The watermark biases
the choice toward a keyed green subset by +delta. This is the same Kirchenbauer
mechanism the tool detects elsewhere, cast into the code-structure setting.

Control (no watermark): the choice follows a fixed style prior that does not depend
on the key. This models model style, the confound the detector must beat.

Detector (keyless, estimating): the detector does not hold the key. It estimates
the green partition from watermarked samples (watermark stealing), then detects a
held-out sample with the estimated partition. Recovering the partition is, for this
modality, recovering the key.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

_MOD = 1 << 32


def _green(key: str, slot: int, variant: int, gamma: float) -> bool:
    h = hashlib.sha256(f"{key}|{slot}|{variant}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") < gamma * _MOD


def _weighted_index(rng: random.Random, weights: list[float]) -> int:
    total = sum(weights)
    r = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(weights) - 1


@dataclass
class StructuralArena:
    key: str
    gamma: float = 0.4
    delta: float = 2.0

    def true_partition(self, k: int, n_slots: int) -> list[list[bool]]:
        return [[_green(self.key, s, v, self.gamma) for v in range(k)] for s in range(n_slots)]

    def watermarked(self, k: int, n_slots: int, seed: int, table=None) -> list[int]:
        rng = random.Random(seed)
        table = table or self.true_partition(k, n_slots)
        gw = math.exp(self.delta)
        return [
            _weighted_index(rng, [gw if table[s][v] else 1.0 for v in range(k)])
            for s in range(n_slots)
        ]

    def control(self, k: int, n_slots: int, seed: int, style: float = 1.6) -> list[int]:
        rng = random.Random(seed)
        weights = [style ** (-v) for v in range(k)]  # key-independent style prior
        return [_weighted_index(rng, weights) for _ in range(n_slots)]


@dataclass
class EstimatingDetector:
    margin: float = 0.15   # how far above chance a variant must be to be called green
    z_threshold: float = 3.0

    def estimate_partition(self, samples: list[list[int]], k: int, n_slots: int) -> list[list[bool]]:
        counts = [[0] * k for _ in range(n_slots)]
        for seq in samples:
            for s, v in enumerate(seq):
                counts[s][v] += 1
        total = max(1, len(samples))
        thresh = (1.0 / k) * (1.0 + self.margin)
        return [[(counts[s][v] / total) > thresh for v in range(k)] for s in range(n_slots)]

    @staticmethod
    def _gamma_est(est: list[list[bool]]) -> float:
        cells = sum(len(row) for row in est)
        green = sum(1 for row in est for c in row if c)
        return green / max(1, cells)

    def z_score(self, seq: list[int], est: list[list[bool]]) -> float:
        gamma_est = self._gamma_est(est) or 1e-6
        n = len(seq)
        green = sum(1 for s, v in enumerate(seq) if s < len(est) and v < len(est[s]) and est[s][v])
        var = n * gamma_est * (1 - gamma_est)
        if var <= 0:
            return 0.0
        return (green - gamma_est * n) / math.sqrt(var)

    def detected(self, seq: list[int], est: list[list[bool]]) -> bool:
        return self.z_score(seq, est) >= self.z_threshold


def partition_recovery(estimated: list[list[bool]], true: list[list[bool]]) -> float:
    """Fraction of (slot, variant) cells where the estimate matches the truth."""
    cells = 0
    match = 0
    for s in range(min(len(estimated), len(true))):
        for v in range(min(len(estimated[s]), len(true[s]))):
            cells += 1
            if estimated[s][v] == true[s][v]:
                match += 1
    return match / max(1, cells)
