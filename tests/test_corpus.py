"""Tests for the corpus-level unigram green-bias estimator (FR-17).

A synthetic unigram watermark boosts a fixed green set. Steal-and-test must detect it
on a held-out half, recover the green set, and stay near null on a control corpus.
"""

import random

from bleachmark.detect.corpus import (
    detect_corpus_watermark, steal_green_set, token_freqs,
)

V = 500
GREEN = set(range(0, 125))          # a fixed gamma=0.25 green set


def _doc(rng, n, watermark, boost=0.5):
    out = []
    for _ in range(n):
        if watermark and rng.random() < boost:
            out.append(rng.randrange(0, 125))    # a green token
        else:
            out.append(rng.randrange(0, V))
    return out


def _corpus(seed, n_docs, doclen, watermark):
    rng = random.Random(seed)
    return [_doc(rng, doclen, watermark) for _ in range(n_docs)]


def test_detects_unigram_watermark():
    wm = _corpus(1, 24, 200, True)
    ref = _corpus(2, 24, 200, False)
    res = detect_corpus_watermark(wm, ref)
    assert res["z"] > 4.0
    assert res["false_positive_rate"] < 0.01


def test_control_corpus_near_null():
    cand = _corpus(3, 24, 200, False)            # unwatermarked candidate
    ref = _corpus(2, 24, 200, False)
    res = detect_corpus_watermark(cand, ref)
    assert res["z"] < 4.0                          # no watermark, no held-out signal


def test_estimated_green_set_is_mostly_true_green():
    wm = _corpus(1, 24, 200, True)
    ref = _corpus(2, 24, 200, False)
    green = steal_green_set(token_freqs(wm[0::2]), token_freqs(ref))
    assert green
    hits = sum(1 for t in green if t in GREEN) / len(green)
    assert hits > 0.8                              # the lift recovers the real green set
