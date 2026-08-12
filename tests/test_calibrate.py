"""Validate the calibrated style baseline on the arena (ground truth).

The calibration turns the raw partition gap into a false-positive rate against a style
baseline. It must do two things, both measured on the arena:

- When the reference style is slot-INDEPENDENT, a keyed watermark's gap stands out, so
  the false-positive rate is low and the tool flags it.
- When the reference style is slot-SPECIFIC and strong, its own gap is large, so a real
  watermark does not exceed it. The false-positive rate is high and the tool does not
  claim a watermark. This is the Christ-Gunn-Zamir wall, stated as a number.
"""

from bleachmark.evolve.arena import StructuralArena
from bleachmark.detect.partition_test import steal_and_test
from bleachmark.detect.calibrate import (
    bootstrap_gaps,
    calibrate_style_baseline,
    score_against_baseline,
    StyleBaseline,
)

K, N_SLOTS, N = 4, 80, 40


def _arena():
    return StructuralArena(key="stego-key", gamma=0.4, delta=2.0)


def _watermarked_gap():
    a = _arena()
    table = a.true_partition(K, N_SLOTS)
    wm = [a.watermarked(K, N_SLOTS, seed=i, table=table) for i in range(N)]
    return steal_and_test(wm, K, N_SLOTS, permutations=200, seed=0).gap


def _flat_baseline():
    a = _arena()
    refs = [([a.control(K, N_SLOTS, seed=1000 + c * 100 + i) for i in range(N)], K, N_SLOTS)
            for c in range(2)]
    return calibrate_style_baseline(refs, n_boot=40, permutations=30, seed=7)


def _slot_specific_baseline():
    a = _arena()
    refs = [([a.styled_control(K, N_SLOTS, seed=2000 + c * 100 + i, style=12.0) for i in range(N)],
             K, N_SLOTS) for c in range(2)]
    return calibrate_style_baseline(refs, n_boot=40, permutations=30, seed=7)


def test_bootstrap_returns_a_distribution():
    a = _arena()
    rows = [a.control(K, N_SLOTS, seed=i) for i in range(N)]
    gaps = bootstrap_gaps(rows, K, N_SLOTS, n_boot=30, permutations=30, seed=1)
    assert len(gaps) == 30
    assert min(gaps) != max(gaps)  # a real spread, not a constant


def test_fpr_is_monotone():
    base = _flat_baseline()
    # a larger target gap gives a smaller or equal false-positive rate
    assert base.fpr(50.0) <= base.fpr(5.0) <= base.fpr(0.0)


def test_watermark_detected_against_flat_style():
    finding = score_against_baseline(_watermarked_gap(), _flat_baseline(), alpha=0.05)
    assert finding.fpr <= 0.05
    assert finding.exceeds_baseline


def test_watermark_hidden_against_slot_specific_style():
    # the wall: a strong slot-specific style has a larger gap than the watermark, so the
    # watermark does not exceed the baseline and the tool does not claim it
    finding = score_against_baseline(_watermarked_gap(), _slot_specific_baseline(), alpha=0.05)
    assert finding.fpr > 0.5
    assert not finding.exceeds_baseline


def test_baseline_summary_has_fields():
    s = _flat_baseline().summary()
    for key in ("n", "mean", "p50", "p90", "p95", "max"):
        assert key in s


def test_empty_baseline_is_not_significant():
    base = StyleBaseline(gaps=[])
    finding = score_against_baseline(10.0, base)
    assert finding.fpr == 1.0
    assert not finding.exceeds_baseline
