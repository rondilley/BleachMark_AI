"""Corpus-level green-bias estimator for a leaky unigram watermark (FR-17).

Single-document keyless detection of a distortion-free watermark is impossible (the
Christ-Gunn-Zamir wall, research 5). A context-free (unigram) watermark is the one
leaky case: it favors the SAME fixed green set on every generation, so across a corpus
that set is systematically over-represented and can be estimated without the key.

The method is steal-and-test, the same shape as the code and prose detectors:
  1. steal a candidate green set from one half of the candidate corpus, as the tokens
     whose frequency is lifted over a reference (unwatermarked) corpus,
  2. test that set on the OTHER, independent half: a real green set stays elevated,
     a set stolen from sampling noise regresses to the reference rate.
The reference must be the same source with the mark off (or a control model), or a
style difference is confounded with a watermark. That limit is stated (FR-38a).
"""

from __future__ import annotations

import math
from collections import Counter


def token_freqs(corpus: list) -> Counter:
    """Pool a corpus (a list of token lists) into one frequency count."""
    c: Counter = Counter()
    for doc in corpus:
        c.update(doc)
    return c


def steal_green_set(steal_freq: Counter, ref_freq: Counter,
                    min_count: int = 5, lift: float = 1.3, smoothing: float = 0.5) -> set:
    """Estimate the green set: tokens lifted over the reference by at least `lift`.

    A unigram watermark raises the probability of its green tokens by a constant factor,
    so the green set shows up as a coherent block of high-lift tokens.
    """
    total_steal = sum(steal_freq.values()) or 1
    total_ref = sum(ref_freq.values()) + smoothing * max(1, len(ref_freq))
    green = set()
    for tok, cnt in steal_freq.items():
        if cnt < min_count:
            continue
        p_steal = cnt / total_steal
        p_ref = (ref_freq.get(tok, 0) + smoothing) / total_ref
        if p_steal / p_ref >= lift:
            green.add(tok)
    return green


def _green_count(tokens: list, green_set: set) -> tuple:
    return sum(1 for t in tokens if t in green_set), len(tokens)


def detect_corpus_watermark(candidate_corpus: list, reference_corpus: list,
                            min_count: int = 5, lift: float = 1.3) -> dict:
    """Steal a green set on one half, then compare the candidate and the reference on it.

    Both corpora split into a steal half and a test half. The green set is stolen from the
    candidate steal-half against the reference steal-half. The statistic is a two-proportion
    z on the INDEPENDENT test halves: the candidate green rate minus the reference green
    rate. This cancels the finite-sample bias that a token rare in the reference would
    otherwise create. Under a unigram watermark the candidate test-half is elevated over the
    reference test-half; a control candidate regresses to z near zero.
    """
    cand = list(candidate_corpus)
    ref = list(reference_corpus)
    green = steal_green_set(token_freqs(cand[0::2]), token_freqs(ref[0::2]),
                            min_count=min_count, lift=lift)
    cand_test = [t for d in cand[1::2] for t in d]
    ref_test = [t for d in ref[1::2] for t in d]
    gc, nc = _green_count(cand_test, green)
    gr, nr = _green_count(ref_test, green)
    if not green or nc == 0 or nr == 0:
        z = 0.0
    else:
        pc, pr = gc / nc, gr / nr
        se = math.sqrt(pc * (1 - pc) / nc + pr * (1 - pr) / nr)
        z = (pc - pr) / se if se > 0 else 0.0
    return {
        "z": z,
        "false_positive_rate": 0.5 * math.erfc(max(0.0, z) / math.sqrt(2)),
        "green_set_size": len(green),
        "candidate_test_tokens": nc,
        "reference_test_tokens": nr,
        "note": "corpus-level unigram estimate; the reference must be the same source "
                "with the mark off, or model style is confounded (FR-38a).",
    }
