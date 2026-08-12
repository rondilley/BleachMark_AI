"""Calibrated style baseline for the partition test (FR-14, FR-15, FR-16).

The steal-and-test gap conflates a keyed watermark with the model slot-specific style.
A large gap on real code is style, not proof of a watermark (round 3). So a bare gap and
a slot-permutation p-value are not an honest test: the permutation null is fooled by
slot-specific style, which real code has.

This module gives the honest version. It calibrates a STYLE BASELINE from reference
corpora that the tool treats as unwatermarked (a control model, a pre-cutoff model, a
local model), and it scores a target gap as a false-positive rate against that baseline.
The rate answers the right question: if the target were only the reference style with no
watermark, how often would a gap this large appear? A low rate means the gap is beyond
the style band. A high rate means the gap is inside it, so the tool does not claim a
watermark.

The baseline is bootstrapped: from one reference corpus the tool draws many sub-corpora
and measures the gap of each, so the null is a distribution, not one number. The tool
pools the bootstrap gaps of every reference corpus.

The honest limit stays. If the reference style is itself slot-specific and strong, its
baseline is high, and a real watermark does not exceed it, so the tool reports a high
rate and no claim. That is the Christ-Gunn-Zamir wall, stated as a number. A model with
stronger slot-specific style than the references would also exceed the baseline with no
watermark, so a low rate is suggestive, not proof. The report states this.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

from .partition_test import steal_and_test


def bootstrap_gaps(
    rows: list[list[int]],
    k: int,
    n_slots: int,
    m: int | None = None,
    n_boot: int = 120,
    permutations: int = 60,
    seed: int = 0,
) -> list[float]:
    """Draw n_boot sub-corpora (with replacement) and return the gap of each.

    The default sub-corpus size m is the full corpus size, so a bootstrap gap is
    comparable to the target gap. The gap grows with the corpus size, so the target and
    the baseline must use the same size, or the false-positive rate is not honest.
    """
    if len(rows) < 4 or n_slots < 2:
        return [0.0 for _ in range(n_boot)]
    rng = random.Random(seed)
    m = m or len(rows)
    gaps: list[float] = []
    for b in range(n_boot):
        sub = [rows[rng.randrange(len(rows))] for _ in range(m)]
        r = steal_and_test(sub, k, n_slots, permutations=permutations, seed=seed + 1 + b)
        gaps.append(r.gap)
    return gaps


@dataclass
class StyleBaseline:
    gaps: list[float]
    sources: list[str] = field(default_factory=list)

    def fpr(self, target_gap: float) -> float:
        """Empirical false-positive rate: the share of style gaps at or above the target."""
        n = len(self.gaps)
        if n == 0:
            return 1.0
        hits = sum(1 for g in self.gaps if g >= target_gap)
        return (hits + 1) / (n + 1)

    def quantile(self, q: float) -> float:
        if not self.gaps:
            return 0.0
        gs = sorted(self.gaps)
        idx = min(len(gs) - 1, max(0, int(q * len(gs))))
        return gs[idx]

    def summary(self) -> dict:
        if not self.gaps:
            return {"n": 0}
        return {
            "n": len(self.gaps),
            "mean": round(statistics.mean(self.gaps), 3),
            "std": round(statistics.pstdev(self.gaps), 3),
            "p50": round(self.quantile(0.50), 3),
            "p90": round(self.quantile(0.90), 3),
            "p95": round(self.quantile(0.95), 3),
            "max": round(max(self.gaps), 3),
        }


def calibrate_style_baseline(
    references: list[tuple],
    m: int | None = None,
    n_boot: int = 120,
    permutations: int = 60,
    seed: int = 0,
    sources: list[str] | None = None,
) -> StyleBaseline:
    """Pool bootstrap gaps from every reference corpus into one style baseline.

    Each reference is a (rows, k, n_slots) tuple from a corpus the tool treats as
    unwatermarked. The pooled gaps are the null distribution of the gap under style.
    """
    pooled: list[float] = []
    for i, (rows, k, n_slots) in enumerate(references):
        pooled.extend(bootstrap_gaps(rows, k, n_slots, m=m, n_boot=n_boot,
                                     permutations=permutations, seed=seed + 1000 * (i + 1)))
    return StyleBaseline(gaps=pooled, sources=sources or [])


@dataclass
class CalibratedFinding:
    target_gap: float
    fpr: float                  # false-positive rate against the style baseline
    exceeds_baseline: bool      # the gap is beyond the style band at the given alpha
    alpha: float
    baseline: dict              # the baseline summary
    note: str = ""


def score_against_baseline(target_gap: float, baseline: StyleBaseline, alpha: float = 0.05) -> CalibratedFinding:
    """Score a target gap as a false-positive rate against the calibrated style baseline."""
    fpr = baseline.fpr(target_gap)
    note = (
        "A low rate means the gap is beyond the reference style band. It is suggestive, not "
        "proof: a model with stronger slot-specific style than the references would also "
        "exceed the baseline with no watermark (the keyless undetectability limit)."
    )
    return CalibratedFinding(
        target_gap=round(target_gap, 3),
        fpr=round(fpr, 4),
        exceeds_baseline=fpr <= alpha,
        alpha=alpha,
        baseline=baseline.summary(),
        note=note,
    )


def gap_of_corpus(corpus: list[str], lang: str, k: int = 4, permutations: int = 300, seed: int = 0):
    """Featurize a code corpus and return (gap, n_slots)."""
    from .features import featurize

    fm = featurize(corpus, lang, k=k)
    if fm.n_slots < 2:
        return 0.0, fm.n_slots
    r = steal_and_test(fm.rows, fm.k, fm.n_slots, permutations=permutations, seed=seed)
    return r.gap, fm.n_slots


def calibrate_from_code(
    candidate: list[str],
    references: list[list[str]],
    lang: str,
    k: int = 4,
    n_boot: int = 120,
    permutations: int = 60,
    seed: int = 0,
    alpha: float = 0.05,
    sources: list[str] | None = None,
) -> CalibratedFinding:
    """Calibrate a style baseline from reference code corpora and score the candidate.

    The candidate and each reference must be the same corpus size, so the full-size
    bootstrap gaps are comparable to the candidate gap.
    """
    from .features import featurize

    ref_mats = []
    for corpus in references:
        fm = featurize(corpus, lang, k=k)
        ref_mats.append((fm.rows, fm.k, fm.n_slots))
    baseline = calibrate_style_baseline(ref_mats, n_boot=n_boot, permutations=permutations,
                                        seed=seed, sources=sources)
    target_gap, _slots = gap_of_corpus(candidate, lang, k=k, seed=seed)
    return score_against_baseline(target_gap, baseline, alpha=alpha)
