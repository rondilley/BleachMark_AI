"""The context-keyed signature must separate a watermark from style and noise.

A watermark flips its favored word pseudorandomly with the context, so it scores
high. A style favorite is decisive but does not flip, so it scores low. Noise is
not decisive, so it scores low.
"""

import hashlib
import random

from bleachmark.detect.context_keyed import context_keyed_score, DEFAULT_CONTEXTS, DEFAULT_PAIRS


def _watermarked_choice(ctx, wa, wb, rng):
    # the green word is keyed on the context, so the winner flips across contexts
    h = int(hashlib.sha256(f"{ctx}|{wa}|{wb}".encode()).hexdigest(), 16)
    green = "a" if h % 2 == 0 else "b"
    other = "b" if green == "a" else "a"
    return green if rng.random() < 0.85 else other


def _style_choice(ctx, wa, wb, rng):
    # a fixed favorite regardless of context: decisive but never flips
    return "a" if rng.random() < 0.85 else "b"


def _noise_choice(ctx, wa, wb, rng):
    return rng.choice(["a", "b"])


def test_watermark_scores_high():
    r = context_keyed_score(_watermarked_choice, n_samples=8, seed=1)
    assert r.signature_score > 0.3
    assert r.mean_concentration > 0.4
    assert r.majority_balance > 0.5   # the winner flips across contexts


def test_style_scores_low_despite_concentration():
    r = context_keyed_score(_style_choice, n_samples=8, seed=1)
    assert r.mean_concentration > 0.4        # decisive
    assert r.majority_balance < 0.3          # but the same winner every context
    assert r.signature_score < 0.2


def test_noise_scores_low():
    r = context_keyed_score(_noise_choice, n_samples=8, seed=1)
    assert r.mean_concentration < 0.4
    assert r.signature_score < 0.2


def test_watermark_beats_style_and_noise():
    wm = context_keyed_score(_watermarked_choice, n_samples=8, seed=2).signature_score
    st = context_keyed_score(_style_choice, n_samples=8, seed=2).signature_score
    no = context_keyed_score(_noise_choice, n_samples=8, seed=2).signature_score
    assert wm > st and wm > no


def test_signature_works_with_arbitrary_tokens():
    from bleachmark.detect.context_keyed import ARBITRARY_PAIRS

    wm = context_keyed_score(_watermarked_choice, pairs=ARBITRARY_PAIRS[:2], n_samples=8, seed=1)
    st = context_keyed_score(_style_choice, pairs=ARBITRARY_PAIRS[:2], n_samples=8, seed=1)
    assert wm.signature_score > 0.3
    assert st.signature_score < 0.2


def test_valid_fraction_full_for_clean_doubles():
    r = context_keyed_score(_watermarked_choice, n_samples=6, seed=3)
    assert r.valid_fraction == 1.0
    assert len(r.per_pair) == len(DEFAULT_PAIRS)
    assert len(DEFAULT_CONTEXTS) >= 10
