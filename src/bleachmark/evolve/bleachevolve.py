"""Evolve a bleach that removes a watermark and keeps the meaning (FR-24 to FR-28).

The other loops make it hard to add a watermark, or try to detect one. This loop is
the third objective: take text that is ALREADY watermarked, and bleach it. The bleach
must lower the watermark signal and keep the meaning of the output.

The arena has the ground truth, so the two effects are measured, not asserted:

- A NATURAL reference. This is the content the model would write with no watermark: the
  correct choice at each slot. It is the meaning to keep.
- A WATERMARKED sample. The green-list watermark pushes some slots away from the
  natural choice toward a keyed green variant. So the watermark shifts the output away
  from the meaning, and the mark rides on the green count.
- A BLEACH policy. It edits some slots. For an edited slot it re-samples a new variant.
  The target is the lever: a "natural" target re-samples from the model's natural
  distribution (a paraphrase that regenerates the slot), a "uniform" target picks any
  variant, an "avoid" target picks any variant that is not the current one.

The bleach holds no key. It cannot see which slots are green and which are natural. So
it edits blind. The measured result: a natural-target bleach removes the watermark and
keeps the meaning, because a re-generated slot lands on the natural choice most of the
time. It even raises the meaning above the watermarked input, because it undoes the
watermark's push away from the natural choice. A uniform target removes the watermark
too, but it scatters the meaning. The meaning gate is a hard limit, the same as the
generation-time defense: a bleach that drops the meaning below the gate is not valid.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from .arena import _green, _weighted_index


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


@dataclass
class BleachArena:
    """A green-list watermark on top of a natural content distribution (ground truth)."""

    wm_key: str
    content_key: str = "content"
    gamma: float = 0.4
    delta: float = 1.5           # watermark strength (a low-distortion nudge)
    content_sharp: float = 17.0  # how strongly the natural choice is preferred

    def green_table(self, k: int, n_slots: int) -> list[list[bool]]:
        return [[_green(self.wm_key, s, v, self.gamma) for v in range(k)] for s in range(n_slots)]

    def natural(self, k: int, n_slots: int) -> list[int]:
        """The correct content choice at each slot: the meaning to keep."""
        out = []
        for s in range(n_slots):
            digest = hashlib.sha256(f"{self.content_key}|{s}".encode()).digest()
            out.append(int.from_bytes(digest[:4], "big") % k)
        return out

    def _natural_weights(self, s: int, k: int, nat: list[int]) -> list[float]:
        return [self.content_sharp if v == nat[s] else 1.0 for v in range(k)]

    def watermarked(self, k: int, n_slots: int, seed: int, table, nat) -> list[int]:
        """Sample content, but with the watermark pushing some slots toward green."""
        rng = random.Random(seed)
        gw = math.exp(self.delta)
        out = []
        for s in range(n_slots):
            base = self._natural_weights(s, k, nat)
            weights = [base[v] * (gw if table[s][v] else 1.0) for v in range(k)]
            out.append(_weighted_index(rng, weights))
        return out

    def resample_natural(self, s: int, k: int, nat: list[int], rng: random.Random) -> int:
        """Regenerate a slot from the natural distribution (no key, no watermark)."""
        return _weighted_index(rng, self._natural_weights(s, k, nat))

    def oracle_z(self, seq: list[int], table) -> float:
        """The watermark signal an oracle with the key sees: the green-count z."""
        n = len(seq)
        green = sum(1 for s, v in enumerate(seq) if table[s][v])
        cells = sum(len(r) for r in table)
        gamma = sum(1 for r in table for c in r if c) / max(1, cells)
        if gamma <= 0 or gamma >= 1:
            return 0.0
        var = n * gamma * (1 - gamma)
        return (green - gamma * n) / math.sqrt(var) if var > 0 else 0.0

    def meaning(self, seq: list[int], nat: list[int]) -> float:
        """Fraction of slots that keep the natural (correct) content choice."""
        return sum(1 for s, v in enumerate(seq) if v == nat[s]) / max(1, len(seq))


@dataclass
class BleachPolicy:
    edit_rate: float = 0.5
    target: str = "natural"  # "natural" | "uniform" | "avoid"

    def apply(self, seq, arena: BleachArena, k, n_slots, nat, seed) -> list[int]:
        rng = random.Random(seed)
        out = list(seq)
        for s in range(n_slots):
            if rng.random() >= self.edit_rate:
                continue
            if self.target == "uniform":
                out[s] = rng.randrange(k)
            elif self.target == "avoid":
                choices = [v for v in range(k) if v != seq[s]] or [seq[s]]
                out[s] = rng.choice(choices)
            else:  # natural: regenerate the slot from the model's natural distribution
                out[s] = arena.resample_natural(s, k, nat, rng)
        return out

    def mutate(self, rng: random.Random) -> "BleachPolicy":
        g = BleachPolicy(self.edit_rate, self.target)
        if rng.random() < 0.5:
            g.edit_rate = _clamp(self.edit_rate + rng.choice([-0.15, -0.05, 0.05, 0.15]), 0.0, 1.0)
        else:
            g.target = rng.choice(["natural", "uniform", "avoid"])
        return g


@dataclass
class BleachEval:
    detect_reduction: float   # fraction of the watermark z removed (want high)
    residual_z: float         # the watermark z after the bleach (want low)
    base_z: float             # the watermark z before the bleach
    meaning: float            # meaning after the bleach (absolute, for reference)
    base_meaning: float       # meaning of the watermarked input (the reference to keep)
    retention: float          # meaning after the bleach divided by the input meaning
    meaning_ok: bool          # the bleach keeps at least the input meaning (gate)
    fitness: float


def evaluate_bleach(
    policy: BleachPolicy,
    arena: BleachArena,
    k: int = 4,
    n_slots: int = 80,
    n_eval: int = 16,
    gate: float = 0.99,
    seed: int = 0,
) -> BleachEval:
    """Measure the bleach: how much watermark it removes, and the meaning it keeps.

    The gate is a RETENTION ratio against the watermarked input, not an absolute score.
    The bleach must keep at least `gate` of the input meaning (default 0.99, so it does
    not degrade the output). A natural-target bleach can exceed 1.0, because it undoes
    the watermark's push away from the natural content.
    """
    table = arena.green_table(k, n_slots)
    nat = arena.natural(k, n_slots)
    reductions, residuals, bases, meanings, base_meanings = [], [], [], [], []
    for i in range(n_eval):
        wm = arena.watermarked(k, n_slots, seed=seed + i, table=table, nat=nat)
        base_z = arena.oracle_z(wm, table)
        bleached = policy.apply(wm, arena, k, n_slots, nat, seed=seed + 1000 + i)
        after_z = arena.oracle_z(bleached, table)
        bases.append(base_z)
        residuals.append(after_z)
        reductions.append((base_z - after_z) / base_z if base_z > 1e-6 else 0.0)
        meanings.append(arena.meaning(bleached, nat))
        base_meanings.append(arena.meaning(wm, nat))

    mean_red = sum(reductions) / len(reductions)
    mean_res = sum(residuals) / len(residuals)
    mean_base = sum(bases) / len(bases)
    mean_meaning = sum(meanings) / len(meanings)
    mean_base_meaning = sum(base_meanings) / max(1e-9, len(base_meanings))
    retention = mean_meaning / mean_base_meaning if mean_base_meaning > 1e-9 else 0.0
    meaning_ok = retention >= gate
    # reward watermark removal, but never past the meaning gate (a hard limit)
    fitness = mean_red if meaning_ok else -1.0 - (gate - retention)
    return BleachEval(
        detect_reduction=mean_red,
        residual_z=mean_res,
        base_z=mean_base,
        meaning=mean_meaning,
        base_meaning=mean_base_meaning,
        retention=retention,
        meaning_ok=meaning_ok,
        fitness=fitness,
    )


@dataclass
class BleachResult:
    best: BleachPolicy
    best_eval: BleachEval
    history: list[float] = field(default_factory=list)


def evolve_bleach(
    arena: BleachArena,
    generations: int = 10,
    pop_size: int = 8,
    k: int = 4,
    n_slots: int = 80,
    n_eval: int = 16,
    gate: float = 0.99,
    seed: int = 0,
) -> BleachResult:
    """Evolve a bleach policy that removes the watermark and holds the meaning gate."""
    rng = random.Random(seed)
    population = [
        BleachPolicy(edit_rate=rng.choice([0.2, 0.4, 0.6, 0.8]),
                     target=rng.choice(["natural", "uniform", "avoid"]))
        for _ in range(pop_size)
    ]
    best: BleachPolicy | None = None
    best_eval: BleachEval | None = None
    history: list[float] = []

    for _ in range(generations):
        scored = [(p, evaluate_bleach(p, arena, k, n_slots, n_eval, gate, seed)) for p in population]
        scored.sort(key=lambda pair: pair[1].fitness, reverse=True)
        history.append(scored[0][1].fitness)
        if best_eval is None or scored[0][1].fitness > best_eval.fitness:
            best, best_eval = scored[0]
        survivors = [p for p, _ in scored[: max(2, pop_size // 2)]]
        population = survivors + [
            rng.choice(survivors).mutate(rng) for _ in range(pop_size - len(survivors))
        ]

    return BleachResult(best=best, best_eval=best_eval, history=history)
