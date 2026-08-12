"""Tests for the meaning-gate threshold calibration (FR-27, TC-09)."""

from bleachmark.bleach.gate import MeaningGate, _dense_cosine
from bleachmark.bleach.meaning_calibrate import (
    calibrate_meaning_threshold,
    separation_auc,
    threshold_at_false_accept,
)


def test_dense_cosine_matches_hand_calculation():
    assert _dense_cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _dense_cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert abs(_dense_cosine([1.0, 1.0], [1.0, 0.0]) - (1 / (2 ** 0.5))) < 1e-9
    assert _dense_cosine([], [1.0]) == 0.0            # length mismatch is 0


def test_gate_uses_dense_cosine_when_embedding_supplied():
    # a fake embedding: preserved text maps near the original, changed text far
    table = {"orig": [1.0, 0.0, 0.0], "para": [0.98, 0.2, 0.0], "diff": [0.0, 0.0, 1.0]}
    gate = MeaningGate(embedding=lambda t: table[t], embedding_threshold=0.9)
    assert gate.similarity("orig", "para") > 0.9
    assert gate.similarity("orig", "diff") < 0.9
    assert gate.passes(gate.similarity("orig", "para")) is True
    assert gate.passes(gate.similarity("orig", "diff")) is False


def test_auc_is_one_for_perfect_separation():
    assert separation_auc([0.9, 0.95, 0.99], [0.1, 0.2, 0.3]) == 1.0
    assert separation_auc([0.5], [0.5]) == 0.5      # a tie is half a win


def test_threshold_holds_false_accept_at_target():
    changed = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    # a 20% false-accept target allows 2 of 10 changed pairs at or above the threshold
    thr = threshold_at_false_accept(changed, 0.2)
    passing = sum(1 for c in changed if c >= thr)
    assert passing <= 2


def test_calibration_reports_rates_and_separation():
    preserved = [0.82, 0.85, 0.88, 0.9, 0.93, 0.95]
    changed = [0.3, 0.4, 0.45, 0.5, 0.55, 0.6]
    out = calibrate_meaning_threshold(preserved, changed, target_false_accept=0.1)
    assert out["auc"] == 1.0                     # fully separated
    # floor(0.1*6)=0 changed pairs may pass, so the threshold sits above every changed sim
    assert out["false_accept_rate"] == 0.0
    assert out["true_accept_rate"] == 1.0        # and below all preserved sims
    assert out["threshold"] >= max(changed)
