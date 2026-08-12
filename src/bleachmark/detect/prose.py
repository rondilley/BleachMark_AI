"""Keyless corpus detection for prose (FR-16, FR-45, research 3).

Code detection aligns constrained samples into positional (slot, variant) cells. Free
prose (a story, an editorial) does not align, so a positional featurizer does not fit.
Prose uses the green-list structure instead. A context-keyed watermark biases the NEXT
token from the token before it, so the slot is the CONTEXT (the previous token) and the
variant is the next token.

The tool steals a green set per context from half the corpus (the next tokens that a
context favors), then tests the held-out half for a green-fraction that is above chance. A
context-permutation null shuffles which context each green set belongs to. A context-keyed
watermark has a context-specific green set, so the permutation breaks it and the gap is
large. A context-independent style favors the same tokens whatever the context, so the
permutation does not change the score and the gap is near zero.

The gap plugs into the same calibrated style baseline as the code path (detect.calibrate),
so prose gets a false-positive rate too, not a verdict (FR-14, FR-15).
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9']+")


def prose_tokens(text: str) -> list[str]:
    """Lowercase word tokens: the canonicalization for prose (case is not a channel)."""
    return _WORD.findall(text.lower())


def _green_by_context(samples: list[list[str]], margin: float, min_context: int, min_obs: int) -> dict:
    """Steal a green next-token set for each frequent context, by lift.

    A next token is green for a context when it is more likely after that context than in
    the corpus overall: P(t | context) > P(t) * (1 + margin). This isolates a
    context-specific boost, which a context-keyed watermark makes, from a context-independent
    style, where P(t | context) is about P(t) and no token is green.
    """
    counts: dict = defaultdict(Counter)
    prev_total: Counter = Counter()
    global_counts: Counter = Counter()
    total = 0
    for toks in samples:
        prev = "<s>"
        for t in toks:
            counts[prev][t] += 1
            prev_total[prev] += 1
            global_counts[t] += 1
            total += 1
            prev = t
    if total == 0:
        return {}
    green: dict = {}
    for ctx, nexts in counts.items():
        if prev_total[ctx] < min_context:
            continue
        gset = set()
        for t, c in nexts.items():
            if c < min_obs:
                continue
            p_t_given_c = c / prev_total[ctx]
            p_t = global_counts[t] / total
            if p_t_given_c > p_t * (1.0 + margin):
                gset.add(t)
        if gset:
            green[ctx] = gset
    return green


def _green_fraction(samples: list[list[str]], green: dict) -> tuple[int, int]:
    """Return (green_hits, scored_bigrams) under a stolen green map."""
    scored = 0
    hit = 0
    for toks in samples:
        prev = "<s>"
        for t in toks:
            gset = green.get(prev)
            if gset is not None:
                scored += 1
                if t in gset:
                    hit += 1
            prev = t
    return hit, scored


def _green_fraction_z(samples: list[list[str]], green: dict, gamma: float) -> float:
    """Aggregate z of the held-out green-fraction under a stolen green map."""
    hit, scored = _green_fraction(samples, green)
    if scored == 0 or gamma <= 0 or gamma >= 1:
        return 0.0
    var = scored * gamma * (1 - gamma)
    return (hit - gamma * scored) / math.sqrt(var) if var > 0 else 0.0


@dataclass
class ProseGapResult:
    gap: float
    z_true: float
    z_null_mean: float
    p_value: float
    n_contexts: int


def prose_gap(
    samples: list[list[str]],
    margin: float = 0.5,
    min_context: int = 4,
    min_obs: int = 3,
    permutations: int = 200,
    split: float = 0.5,
    seed: int = 0,
) -> ProseGapResult:
    """Steal a green-by-context map, test the held-out set, and run the context-permutation null."""
    rng = random.Random(seed)
    idx = list(range(len(samples)))
    rng.shuffle(idx)
    cut = max(1, int(len(samples) * split))
    steal = [samples[i] for i in idx[:cut]]
    test = [samples[i] for i in idx[cut:]] or steal

    green = _green_by_context(steal, margin, min_context, min_obs)
    if len(green) < 2:
        return ProseGapResult(0.0, 0.0, 0.0, 1.0, len(green))
    # a stable null green rate; it is the same for z_true and z_null, so it cancels in the gap
    hit_s, scored_s = _green_fraction(steal, green)
    gamma = min(0.5, max(0.01, hit_s / scored_s if scored_s else 0.1))
    z_true = _green_fraction_z(test, green, gamma)

    contexts = list(green.keys())
    gsets = [green[c] for c in contexts]
    z_null = []
    for p in range(permutations):
        perm = contexts[:]
        random.Random(seed + 1 + p).shuffle(perm)
        permuted = {perm[i]: gsets[i] for i in range(len(contexts))}
        z_null.append(_green_fraction_z(test, permuted, gamma))
    z_null_mean = sum(z_null) / max(1, len(z_null))
    hits = sum(1 for z in z_null if z >= z_true)
    p_value = (hits + 1) / (len(z_null) + 1)
    return ProseGapResult(
        gap=z_true - z_null_mean,
        z_true=z_true,
        z_null_mean=z_null_mean,
        p_value=p_value,
        n_contexts=len(green),
    )


def prose_gap_value(samples, **kwargs) -> float:
    """The prose gap as a single number, for the calibrated style baseline."""
    return prose_gap(samples, **kwargs).gap


def prose_bootstrap_gaps(
    samples: list[list[str]],
    n_boot: int = 80,
    permutations: int = 40,
    margin: float = 0.5,
    min_context: int = 4,
    seed: int = 0,
) -> list[float]:
    """Bootstrap prose gaps from one reference corpus, for the style baseline."""
    if len(samples) < 4:
        return [0.0 for _ in range(n_boot)]
    rng = random.Random(seed)
    m = len(samples)
    gaps = []
    for b in range(n_boot):
        sub = [samples[rng.randrange(m)] for _ in range(m)]
        gaps.append(prose_gap(sub, margin=margin, min_context=min_context,
                              permutations=permutations, seed=seed + 1 + b).gap)
    return gaps


def calibrate_prose(
    candidate_corpus: list[list[str]],
    reference_corpora: list[list[list[str]]],
    margin: float = 0.5,
    min_context: int = 4,
    n_boot: int = 60,
    permutations: int = 40,
    seed: int = 0,
    alpha: float = 0.05,
    sources: list[str] | None = None,
):
    """Score a candidate prose corpus as a false-positive rate against a reference style baseline.

    Each corpus is a list of token-list samples. The reference corpora come from models the tool
    treats as unwatermarked. The baseline pools the bootstrap gaps of every reference corpus, and
    the candidate gap is scored against it. The result is a rate, not a verdict (FR-14, FR-15).
    """
    from .calibrate import StyleBaseline, score_against_baseline

    pooled: list[float] = []
    for corpus in reference_corpora:
        pooled.extend(prose_bootstrap_gaps(corpus, n_boot=n_boot, permutations=permutations,
                                           margin=margin, min_context=min_context, seed=seed))
    baseline = StyleBaseline(gaps=pooled, sources=sources or [])
    target = prose_gap(candidate_corpus, margin=margin, min_context=min_context,
                       permutations=max(permutations, 100), seed=seed).gap
    return score_against_baseline(target, baseline, alpha=alpha)
