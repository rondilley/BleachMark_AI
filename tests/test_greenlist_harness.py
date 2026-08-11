"""Slice 9 and 10 tests: green-list z-test and the effectiveness harness.

TC-05, TC-22. Real detection runs over generated watermarked and control samples.
"""

from bleachmark.detect.keyed.greenlist import GreenListScheme, GreenListDetector, default_tokenizer
from bleachmark.decode import decode
from bleachmark.harness import generators
from bleachmark.harness.measure import (
    measure_greenlist_detection,
    measure_greenlist_bleach,
    run_default_harness,
)


def _scheme():
    return GreenListScheme(key="test-key", vocab=generators.make_vocab(250), gamma=0.25)


def test_watermarked_sequence_has_high_z():
    scheme = _scheme()
    wm = generators.watermarked_sequence(scheme, length=180, seed=1, delta=2.0)
    assert scheme.z_score(wm) > 4.0


def test_control_sequence_has_low_z():
    scheme = _scheme()
    ctrl = generators.control_sequence(scheme.vocab, length=180, seed=1)
    assert scheme.z_score(ctrl) < 4.0


def test_wrong_key_does_not_detect():
    scheme = _scheme()
    wm = generators.watermarked_sequence(scheme, length=180, seed=1, delta=2.0)
    wrong = GreenListScheme(key="other-key", vocab=scheme.vocab, gamma=0.25)
    assert wrong.z_score(wm) < 4.0


def test_detection_rates_high_tpr_low_fpr():
    scheme = _scheme()
    rates = measure_greenlist_detection(scheme, samples=24, length=180)
    assert rates.true_positive_rate >= 0.95
    assert rates.false_positive_rate <= 0.05


def test_bleach_reduces_detection():
    scheme = _scheme()
    # a lighter watermark (delta 1.0) with a heavy substitution bleaches, per research
    rates = measure_greenlist_bleach(scheme, samples=24, length=180, delta=1.0, fraction=0.5)
    assert rates.detected_before >= 0.8
    assert rates.detected_after < rates.detected_before
    assert rates.bleach_success_rate >= 0.3


def test_strong_watermark_resists_light_bleach():
    # research faithfulness: delta 2.0 resists a 20 percent substitution
    scheme = _scheme()
    rates = measure_greenlist_bleach(scheme, samples=20, length=180, delta=2.0, fraction=0.2)
    assert rates.detected_after >= 0.8


def test_greenlist_detector_finding():
    scheme = _scheme()
    wm = generators.watermarked_sequence(scheme, length=180, seed=3, delta=2.0)
    det = GreenListDetector(scheme, tokenizer=default_tokenizer)
    text = " ".join(wm)
    findings = det.detect(decode(text))
    assert findings[0].posture.value == "keyed"
    assert findings[0].score > 4.0


def test_default_harness_runs():
    out = run_default_harness()
    assert out["detection"]["true_positive_rate"] >= 0.9
    assert out["detection"]["false_positive_rate"] <= 0.05
    assert out["bleach"]["bleach_success_rate"] >= 0.3
