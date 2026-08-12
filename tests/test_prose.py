"""Validate the keyless prose corpus detector on the green-list arena (ground truth).

Prose uses green-list-context stealing: the slot is the previous token (the context) and
the variant is the next token. The lift estimator marks a next token green for a context
when it is more likely after that context than in general, so a context-keyed watermark is
flagged and a context-independent style is not. It needs a dense corpus (long texts, enough
samples), the same reason prose needs the 400-word band.
"""

import random

from bleachmark.detect.keyed.greenlist import GreenListScheme
from bleachmark.harness.generators import make_vocab, watermarked_sequence, control_sequence
from bleachmark.detect.prose import prose_tokens, prose_gap, prose_bootstrap_gaps, calibrate_prose
from bleachmark.detect.calibrate import StyleBaseline, score_against_baseline

V, L, N = 60, 800, 40


def _scheme():
    return GreenListScheme(key="wm-key", vocab=make_vocab(V), gamma=0.25)


def _watermarked():
    s = _scheme()
    return [watermarked_sequence(s, L, seed=i, delta=2.0) for i in range(N)]


def _control():
    s = _scheme()
    return [control_sequence(s.vocab, L, seed=1000 + i) for i in range(N)]


def _context_independent_style():
    s = _scheme()
    v = s.vocab

    def one(seed):
        rng = random.Random(seed)
        return [(rng.choice(v[:15]) if rng.random() < 0.6 else rng.choice(v)) for _ in range(L)]

    return [one(2000 + i) for i in range(N)]


def test_prose_tokens_lowercase_words():
    assert prose_tokens("The City Should INVEST, now!") == ["the", "city", "should", "invest", "now"]


def test_watermark_has_a_large_gap():
    r = prose_gap(_watermarked(), min_obs=3, permutations=150, seed=0)
    assert r.gap > 20.0
    assert r.p_value <= 0.05


def test_control_has_a_small_gap():
    r = prose_gap(_control(), min_obs=3, permutations=150, seed=0)
    assert abs(r.gap) < 5.0
    assert r.p_value > 0.05


def test_context_independent_style_is_not_flagged():
    # a context-independent style has no context-specific green set, so the gap is not positive
    r = prose_gap(_context_independent_style(), min_obs=3, permutations=150, seed=0)
    assert r.gap <= 5.0
    assert r.p_value > 0.05


def test_calibrated_prose_fpr_flags_the_watermark():
    base = StyleBaseline(gaps=prose_bootstrap_gaps(_control(), n_boot=40, permutations=30, seed=7))
    target = prose_gap(_watermarked(), min_obs=3, permutations=150, seed=0).gap
    finding = score_against_baseline(target, base, alpha=0.05)
    assert finding.fpr <= 0.05
    assert finding.exceeds_baseline


def test_calibrate_prose_flags_watermark_not_control():
    # the full calibrate_prose path: a watermark candidate is flagged, a control is not
    def control_b():
        s = _scheme()
        return [control_sequence(s.vocab, L, seed=3000 + i) for i in range(N)]

    wm = calibrate_prose(_watermarked(), [_control(), control_b()], n_boot=30, permutations=30, seed=0)
    ctrl = calibrate_prose(_control(), [control_b()], n_boot=30, permutations=30, seed=0)
    assert wm.exceeds_baseline and wm.fpr <= 0.05
    assert not ctrl.exceeds_baseline and ctrl.fpr > 0.05
