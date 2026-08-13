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


def load_labeled_pairs(path: str | None = None) -> dict:
    """Load language-labeled preserved/changed sentence pairs (FR-27a)."""
    import json
    import os

    src = path or os.path.join(
        os.path.dirname(__file__), "..", "data", "meaning", "pairs.json"
    )
    with open(src, encoding="utf-8") as fh:
        return json.load(fh)


def calibrate_language_thresholds(pairs: dict | None = None,
                                  target_false_accept: float = 0.0,
                                  gate=None) -> dict:
    """Calibrate one threshold per language from labeled pairs (FR-27a)."""
    from .gate import MeaningGate
    from .language import detect_language

    gate = gate or MeaningGate()
    pairs = pairs if pairs is not None else load_labeled_pairs()
    out = {}
    for lang, bundle in pairs.items():
        preserved, changed = [], []
        for a, b in bundle.get("preserved", []):
            preserved.append(gate.similarity(a, b, language=lang))
        for a, b in bundle.get("changed", []):
            changed.append(gate.similarity(a, b, language=lang))
        cal = calibrate_meaning_threshold(preserved, changed, target_false_accept)
        cal["language"] = lang
        first = bundle.get("preserved") or [["", ""]]
        cal["detected"] = detect_language(first[0][0])
        out[lang] = cal
    return out
