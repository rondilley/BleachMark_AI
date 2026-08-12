"""Validate the steal-and-test partition z-test on the arena (ground truth).

The key claim: the slot-permutation gap isolates a keyed watermark from model style.
Slot-independent style gives a large raw held-out z (it would fool a plain z-test),
but the permutation gap is near zero. A keyed watermark gives a large gap and a small
p-value. Noise gives neither.
"""

import random

from bleachmark.evolve.arena import StructuralArena
from bleachmark.detect.partition_test import steal_and_test, estimate_partition


def _arena():
    return StructuralArena(key="stego-key", gamma=0.4, delta=2.0)


K, N_SLOTS, N = 4, 80, 40


def _watermarked_rows():
    arena = _arena()
    table = arena.true_partition(K, N_SLOTS)
    return [arena.watermarked(K, N_SLOTS, seed=i, table=table) for i in range(N)]


def _style_rows():
    arena = _arena()
    return [arena.control(K, N_SLOTS, seed=1000 + i) for i in range(N)]


def _noise_rows():
    rng = random.Random(7)
    return [[rng.randrange(K) for _ in range(N_SLOTS)] for _ in range(N)]


def test_keyed_watermark_gives_a_large_gap():
    r = steal_and_test(_watermarked_rows(), K, N_SLOTS, permutations=300, seed=0)
    assert r.gap > 5.0
    assert r.p_value <= 0.05
    assert r.keyed_signal


def test_style_does_not_fool_the_gap():
    r = steal_and_test(_style_rows(), K, N_SLOTS, permutations=300, seed=0)
    # a plain held-out z-test would false-positive: the raw z is large
    assert r.z_true > 3.0
    # but the slot-permutation gap is near zero, so the test is not fooled
    assert r.gap < 1.0
    assert r.p_value > 0.05
    assert not r.keyed_signal


def test_noise_gives_no_signal():
    r = steal_and_test(_noise_rows(), K, N_SLOTS, permutations=300, seed=0)
    assert abs(r.gap) < 3.0
    assert not r.keyed_signal


def _styled_rows():
    # slot-specific style, NO watermark: models real code style
    arena = _arena()
    return [arena.styled_control(K, N_SLOTS, seed=2000 + i) for i in range(N)]


def test_slot_specific_style_fools_the_gap():
    # THE HONEST LIMIT: slot-specific style carries no watermark, yet the gap flags it.
    # A keyed watermark and slot-specific style are not separable keyless. So a positive
    # gap on a real model is not proof of a watermark (upholds the no-overclaim rule).
    r = steal_and_test(_styled_rows(), K, N_SLOTS, permutations=300, seed=0)
    assert r.gap > 5.0
    assert r.keyed_signal  # a false positive, on purpose, to document the confound


def test_gap_beats_raw_z_at_separating_watermark_from_style():
    wm = steal_and_test(_watermarked_rows(), K, N_SLOTS, permutations=200, seed=0)
    st = steal_and_test(_style_rows(), K, N_SLOTS, permutations=200, seed=0)
    # the raw held-out z barely separates the two (style is high)
    # the gap separates them by a wide margin
    assert wm.gap - st.gap > 10.0


def test_estimate_partition_marks_frequent_variants_green():
    arena = _arena()
    table = arena.true_partition(K, N_SLOTS)
    rows = [arena.watermarked(K, N_SLOTS, seed=i, table=table) for i in range(30)]
    est = estimate_partition(rows, K, N_SLOTS, margin=0.15)
    # the estimate recovers most of the true green partition
    cells = sum(len(r) for r in est)
    match = sum(1 for s in range(N_SLOTS) for v in range(K) if est[s][v] == table[s][v])
    assert match / cells >= 0.75
