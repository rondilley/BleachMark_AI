"""Tests for the joint defense/detection co-evolution (the code tranche).

Validates that a tighter defense prompt shrinks the oracle channel capacity, that
the meaning floor is a hard gate the evolved defense respects, that co-evolution
cuts the channel against the undefended baseline, and that the keyless detector
still recovers the partition and holds false positives down in the residual.
"""

from bleachmark.evolve.coevolve import (
    CodeModality,
    DefensePrompt,
    DetectorGenome,
    oracle_capacity,
    detection_eval,
    coevolve,
)


def _modality(lang="python"):
    return CodeModality(key="stego-key", lang=lang, base_slots=100, meaning_floor=18)


def test_tighter_prompt_shrinks_capacity():
    m = _modality()
    loose = DefensePrompt()  # no locks
    tight = DefensePrompt(lock_names=True, lock_structure=True)
    assert tight.open_slots(m) < loose.open_slots(m)
    assert oracle_capacity(tight, m) < oracle_capacity(loose, m)


def test_meaning_floor_is_a_hard_gate():
    m = _modality()
    over = DefensePrompt(lock_names=True, lock_structure=True, no_comments=True, iterative_only=True)
    assert not over.meaning_ok(m)          # all four locks over-constrain
    assert over.meaning_penalty(m) > 0
    ok = DefensePrompt(lock_names=True, lock_structure=True)
    assert ok.meaning_ok(m)
    assert ok.meaning_penalty(m) == 0.0


def test_coevolution_cuts_the_channel():
    m = _modality()
    r = coevolve(m, rounds=8, def_pop=8, det_pop=8, n_eval=16, seed=1)
    # the evolved defense removes a real fraction of the undefended channel
    assert r.final_capacity < r.baseline_capacity
    assert r.capacity_reduction >= 0.3
    # and it never sacrifices correctness to do it
    assert r.best_defense.meaning_ok(m)
    assert r.rounds[-1].meaning_ok


def test_capacity_curve_is_non_increasing():
    m = _modality()
    r = coevolve(m, rounds=8, def_pop=8, det_pop=8, n_eval=16, seed=2)
    curve = r.capacity_curve
    # the defense champion never gets worse (elitist truncation on a hard gate)
    assert all(curve[i + 1] <= curve[i] + 1e-9 for i in range(len(curve) - 1))


def test_detector_still_works_in_the_residual():
    m = _modality()
    r = coevolve(m, rounds=8, def_pop=8, det_pop=8, n_eval=16, seed=3)
    final = r.rounds[-1].detection
    # even in the squeezed channel the keyless detector recovers most of the key
    assert final.recovery >= 0.7
    assert final.fpr <= 0.2


def test_coevolution_runs_for_c():
    m = _modality(lang="c")
    r = coevolve(m, rounds=6, def_pop=6, det_pop=6, n_eval=12, seed=4)
    assert r.capacity_reduction > 0.0
    assert r.best_defense.meaning_ok(m)
    # the defense renders a real C constraint fragment
    frag = r.best_defense.describe(lang="c")
    assert "Return only the code" in frag
