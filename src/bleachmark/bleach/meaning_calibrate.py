"""Calibrate the meaning-gate threshold from labeled pairs (FR-27, TC-09).

The gate needs a threshold that separates a meaning-preserving edit (a paraphrase)
from a meaning-changing edit. Rather than assert a fixed number, this calibrates the
threshold from data: given the similarity scores of known meaning-preserving pairs
and known meaning-changing pairs, it picks the threshold that holds the false-accept
rate (a meaning-changing edit passing the gate) at or below a target, and reports the
true-accept rate at that threshold plus the separation between the two distributions.

The right threshold depends on the metric. A token n-gram cosine and a sentence
embedding sit on different scales, so each must be calibrated on its own pairs; the
0.76 P-SP band is one such calibration, not a universal constant.
"""

from __future__ import annotations

import math


def separation_auc(preserved: list[float], changed: list[float]) -> float:
    """P(random preserved score > random changed score); 1.0 is perfect separation."""
    if not preserved or not changed:
        return 0.5
    wins = 0.0
    for p in preserved:
        for c in changed:
            if p > c:
                wins += 1.0
            elif p == c:
                wins += 0.5
    return wins / (len(preserved) * len(changed))


def threshold_at_false_accept(changed: list[float], target_false_accept: float) -> float:
    """Smallest threshold whose false-accept rate is at most target_false_accept.

    A meaning-changing pair "false-accepts" when its similarity is at or above the
    threshold, so the threshold must sit above all but a target fraction of the
    changed similarities.
    """
    if not changed:
        return 0.0
    s = sorted(changed)
    n = len(s)
    k = math.floor(target_false_accept * n)  # at most k changed pairs may pass
    if k <= 0:
        # strictest the corpus supports: just above the highest changed similarity
        return math.nextafter(s[-1], math.inf)
    return s[n - k]


def calibrate_meaning_threshold(preserved: list[float], changed: list[float],
                                target_false_accept: float = 0.05) -> dict:
    """Calibrate a gate threshold and report how well the metric separates."""
    thr = threshold_at_false_accept(changed, target_false_accept)
    ta = sum(1 for p in preserved if p >= thr) / len(preserved) if preserved else 0.0
    fa = sum(1 for c in changed if c >= thr) / len(changed) if changed else 0.0
    return {
        "threshold": round(thr, 4),
        "target_false_accept": target_false_accept,
        "true_accept_rate": round(ta, 4),
        "false_accept_rate": round(fa, 4),
        "auc": round(separation_auc(preserved, changed), 4),
        "n_preserved": len(preserved),
        "n_changed": len(changed),
        "preserved_mean": round(sum(preserved) / len(preserved), 4) if preserved else None,
        "changed_mean": round(sum(changed) / len(changed), 4) if changed else None,
    }
