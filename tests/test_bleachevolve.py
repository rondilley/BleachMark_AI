"""Tests for the bleach co-evolution (watermark removal with a meaning gate).

The bleach must lower the watermark signal and keep the meaning of the output. The
arena has the ground truth, so the two effects are measured. The key claims: a
natural-target bleach removes the watermark and keeps (or raises) the meaning, a
uniform bleach removes the watermark but fails the meaning gate, and evolution finds
the natural target.
"""

from bleachmark.evolve.bleachevolve import (
    BleachArena,
    BleachPolicy,
    evaluate_bleach,
    evolve_bleach,
)


def _arena():
    return BleachArena(wm_key="stego-key", gamma=0.4, delta=1.5, content_sharp=17.0)


def test_natural_bleach_removes_watermark_and_keeps_meaning():
    e = evaluate_bleach(BleachPolicy(edit_rate=1.0, target="natural"), _arena(), n_eval=24)
    assert e.detect_reduction >= 0.8          # most of the watermark z is gone
    assert abs(e.residual_z) < 1.0            # residual near the no-watermark level
    assert e.meaning_ok                       # meaning kept
    assert e.retention >= 1.0                 # meaning is at least as good as the input


def test_uniform_bleach_fails_the_meaning_gate():
    e = evaluate_bleach(BleachPolicy(edit_rate=1.0, target="uniform"), _arena(), n_eval=24)
    assert e.detect_reduction >= 0.5          # it does remove the watermark
    assert not e.meaning_ok                   # but it degrades the meaning
    assert e.retention < 0.8


def test_natural_beats_uniform_at_equal_edit_rate():
    a = _arena()
    nat = evaluate_bleach(BleachPolicy(edit_rate=0.8, target="natural"), a, n_eval=24)
    uni = evaluate_bleach(BleachPolicy(edit_rate=0.8, target="uniform"), a, n_eval=24)
    # at the same edit rate, both remove the watermark, but natural keeps the meaning
    assert nat.meaning > uni.meaning
    assert nat.meaning_ok and not uni.meaning_ok


def test_evolution_finds_a_meaning_safe_bleach():
    r = evolve_bleach(_arena(), generations=12, pop_size=8, n_eval=24, gate=0.99, seed=1)
    assert r.best.target == "natural"
    assert r.best_eval.meaning_ok
    assert r.best_eval.detect_reduction >= 0.8
    assert abs(r.best_eval.residual_z) < 1.0


def test_meaning_gate_is_a_hard_limit():
    a = _arena()
    # a meaning-safe bleach outranks a meaning-breaking one even if the latter removes
    # more of the watermark
    safe = evaluate_bleach(BleachPolicy(edit_rate=1.0, target="natural"), a, n_eval=24)
    breaking = evaluate_bleach(BleachPolicy(edit_rate=1.0, target="avoid"), a, n_eval=24)
    assert breaking.detect_reduction > safe.detect_reduction  # avoid removes more signal
    assert safe.fitness > breaking.fitness                    # but it loses on the gate
