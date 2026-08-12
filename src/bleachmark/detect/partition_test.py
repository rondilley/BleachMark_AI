"""The steal-and-test partition z-test with a slot-permutation null (FR-45, FR-18).

This is the same-model watermark test that isolates a keyed watermark from model
style. It works on a matrix of (slot, variant) choices: one row per sample, one
column per structural slot, each cell the variant index the model chose there.

The mechanism:

1. Split the rows into a STEAL set and a disjoint TEST set.
2. Steal the green partition from the STEAL set: at each slot, mark a variant green if
   the model picks it more than chance plus a margin (watermark stealing).
3. Test the held-out set: count how many of its picks land in the stolen green cells,
   and z-test that green count against the estimated green fraction.
4. Slot-permutation null: shuffle the stolen partition across slots and z-test the
   same held-out set again. Repeat many times to get a null distribution.

Why the null matters. A plain held-out z-test is fooled by style. Model style is a
slot-INDEPENDENT preference: the model tends to pick the same canonical variant at
every slot. So a held-out styled sample also lands in the green cells and gives a
large z, but that z is not a watermark. A keyed watermark is slot-SPECIFIC: the green
variant is different at each slot, set by the secret key. The slot-permutation
destroys the slot-specific alignment but keeps the green fraction and the style
preference. So:

- A keyed watermark: the true partition predicts the held-out greens, the permuted
  partition does not. The gap z_true minus z_null is large, the p-value is small.
- Slot-independent style: the true and the permuted partition predict the held-out
  greens the same. The gap is near zero, the p-value is large, EVEN IF z_true is
  large.
- No signal: z_true is near zero and the gap is near zero.

On a real model with a distortion-free scheme the test hits the undetectability wall,
and real code style is not perfectly slot-independent, so the gap on a real model is a
proxy, not a proof (research §5). The test is validated on the arena, where the ground
truth is known.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


def estimate_partition(rows: list[list[int]], k: int, n_slots: int, margin: float = 0.15) -> list[list[bool]]:
    """Mark a (slot, variant) cell green if it appears more than chance plus a margin."""
    counts = [[0] * k for _ in range(n_slots)]
    for row in rows:
        for s, v in enumerate(row):
            if s < n_slots and 0 <= v < k:
                counts[s][v] += 1
    total = max(1, len(rows))
    thresh = (1.0 / k) * (1.0 + margin)
    return [[(counts[s][v] / total) > thresh for v in range(k)] for s in range(n_slots)]


def _gamma(est: list[list[bool]]) -> float:
    cells = sum(len(row) for row in est)
    green = sum(1 for row in est for c in row if c)
    return green / max(1, cells)


def _aggregate_z(rows: list[list[int]], est: list[list[bool]], gamma: float) -> float:
    """One z-score for the whole held-out set under a partition."""
    n = 0
    green = 0
    for row in rows:
        for s, v in enumerate(row):
            if s < len(est):
                n += 1
                if 0 <= v < len(est[s]) and est[s][v]:
                    green += 1
    if n == 0 or gamma <= 0 or gamma >= 1:
        return 0.0
    var = n * gamma * (1 - gamma)
    if var <= 0:
        return 0.0
    return (green - gamma * n) / math.sqrt(var)


@dataclass
class PartitionTestResult:
    z_true: float          # held-out z under the stolen partition
    z_null_mean: float     # mean held-out z under the slot-permuted partitions
    gap: float             # z_true - z_null_mean; the keyed-structure signal
    p_value: float         # permutation p-value for the gap
    gamma_est: float
    n_steal: int
    n_test: int
    keyed_signal: bool     # gap is positive and the p-value passes


def steal_and_test(
    rows: list[list[int]],
    k: int,
    n_slots: int,
    margin: float = 0.15,
    permutations: int = 300,
    split: float = 0.5,
    alpha: float = 0.05,
    seed: int = 0,
) -> PartitionTestResult:
    """Split, steal the partition, test held-out, and run the slot-permutation null."""
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    cut = max(1, int(len(rows) * split))
    steal = [rows[i] for i in idx[:cut]]
    test = [rows[i] for i in idx[cut:]] or steal  # fall back if too few rows

    est = estimate_partition(steal, k, n_slots, margin=margin)
    gamma = _gamma(est)
    z_true = _aggregate_z(test, est, gamma)

    z_null: list[float] = []
    slots = list(range(n_slots))
    for p in range(permutations):
        perm = slots[:]
        random.Random(seed + 1 + p).shuffle(perm)
        est_perm = [est[perm[s]] for s in range(n_slots)]
        z_null.append(_aggregate_z(test, est_perm, gamma))
    z_null_mean = sum(z_null) / max(1, len(z_null))
    # permutation p-value: how often the null reaches the observed z
    hits = sum(1 for z in z_null if z >= z_true)
    p_value = (hits + 1) / (len(z_null) + 1)
    gap = z_true - z_null_mean
    return PartitionTestResult(
        z_true=z_true,
        z_null_mean=z_null_mean,
        gap=gap,
        p_value=p_value,
        gamma_est=gamma,
        n_steal=len(steal),
        n_test=len(test),
        keyed_signal=(gap > 0 and p_value <= alpha),
    )
