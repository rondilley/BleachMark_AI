"""Bound the reorder bleach with reorder-invariant watermark variants.

The reorder bleach works by breaking the order the watermark keys on. A context-free (unigram)
watermark does not key on order, so its green count is invariant under a reorder and the bleach
removes nothing at any granularity. A window watermark (a multiset of the last w tokens) is not
reorder-invariant, because the reorder changes which tokens are in the window at the boundaries.
The context-keyed (prev) watermark gives the bleach a channel at a fine granularity.
"""

import random

from bleachmark.harness.generators import make_vocab
from bleachmark.detect.keyed.windowed import (
    ContextScheme,
    generate_in_unit_order,
    reorder_degradation,
    _unit_sizes,
)

VOCAB = make_vocab(80)


def _scheme(kind, window=3):
    return ContextScheme(key="wm-key", vocab=VOCAB, gamma=0.25, kind=kind, window=window)


def test_all_contexts_produce_a_strong_watermark():
    # a sanity check: each context marks the identity-order sequence strongly
    for kind in ("unigram", "window", "prev"):
        r = reorder_degradation(_scheme(kind), unit_tokens=12, total_tokens=240, n_eval=2, seed=0)
        assert r["base_z"] > 8.0


def test_unigram_watermark_is_reorder_invariant_at_every_granularity():
    # THE BOUND: the reorder bleach removes nothing from a context-free watermark
    for unit in (1, 12):
        r = reorder_degradation(_scheme("unigram"), unit_tokens=unit, total_tokens=240, n_eval=2, seed=0)
        assert r["degradation"] < 0.05


def test_prev_watermark_degrades_at_fine_granularity_only():
    word = reorder_degradation(_scheme("prev"), unit_tokens=1, total_tokens=240, n_eval=2, seed=0)
    sentence = reorder_degradation(_scheme("prev"), unit_tokens=12, total_tokens=240, n_eval=2, seed=0)
    assert word["degradation"] > 0.5          # a word-order reverse removes most of it
    assert sentence["degradation"] < 0.2      # a sentence-order reverse removes little


def test_window_watermark_is_not_reorder_resistant():
    # correcting the guess: a multiset window is disrupted by the reorder, not protected by it
    word = reorder_degradation(_scheme("window"), unit_tokens=1, total_tokens=240, n_eval=2, seed=0)
    assert word["degradation"] > 0.5


def test_selfhash_detects_and_is_calibrated():
    # SelfHash (Kirchenbauer 2306.04634, Algorithm 3): strong on watermarked, near zero on control
    import random
    scheme = _scheme("selfhash")
    scheme.h = 4
    sizes = _unit_sizes(400, 1)
    wm = generate_in_unit_order(scheme, sizes, list(range(len(sizes))), seed=1, delta=2.0)
    ctrl = [random.Random(9 + i).choice(VOCAB) for i in range(400)]
    assert scheme.z_score(wm) > 8.0
    assert abs(scheme.z_score(ctrl)) < 3.0     # the marginal green fraction matches the null


def test_selfhash_is_reorder_vulnerable_not_invariant():
    scheme = _scheme("selfhash")
    scheme.h = 4
    word = reorder_degradation(scheme, unit_tokens=1, total_tokens=240, n_eval=2, seed=0)
    sentence = reorder_degradation(scheme, unit_tokens=12, total_tokens=240, n_eval=2, seed=0)
    # SelfHash keys on a context window, so a reorder breaks it (unlike the context-free unigram)
    assert word["degradation"] > 0.3
    # but the self-min makes it more reorder-robust than plain LeftHash at the fine granularity
    prev_word = reorder_degradation(_scheme("prev"), unit_tokens=1, total_tokens=240, n_eval=2, seed=0)
    assert word["degradation"] < prev_word["degradation"] + 1e-6
    # a coarse reorder removes little, the same trade-off as the other context-keyed schemes
    assert sentence["degradation"] < 0.3


def test_context_free_watermark_still_falls_to_substitution():
    # the trade-off: unigram resists reorder but a token substitution removes it
    scheme = _scheme("unigram")
    sizes = _unit_sizes(240, 1)
    base, after = [], []
    for i in range(2):
        seq = generate_in_unit_order(scheme, sizes, list(range(len(sizes))), seed=i, delta=2.0)
        rng = random.Random(99 + i)
        sub = list(seq)
        for j in rng.sample(range(len(sub)), int(0.30 * len(sub))):
            sub[j] = rng.choice(VOCAB)
        base.append(scheme.z_score(seq))
        after.append(scheme.z_score(sub))
    b = sum(base) / len(base)
    a = sum(after) / len(after)
    assert (1 - a / b) > 0.1                   # substitution removes a real fraction
