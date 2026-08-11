"""Reference watermark generators and test keys (FR-44).

A reference generator makes a real watermarked token sequence with the green-list
scheme, and a control generator makes an unwatermarked one. The harness measures
detection and bleach against these known samples. The generator is a stand-in for a
real watermarked model output; it is a real Kirchenbauer-style scheme, not a stub.
"""

from __future__ import annotations

import math
import random

from ..detect.keyed.greenlist import GreenListScheme


def make_vocab(size: int = 400) -> list[str]:
    return [f"w{i}" for i in range(size)]


def watermarked_sequence(
    scheme: GreenListScheme, length: int, seed: int, delta: float = 2.0
) -> list[str]:
    """Generate a green-list watermarked sequence (a +delta bias toward green)."""
    rng = random.Random(seed)
    vocab = scheme.vocab
    green_w = math.exp(delta)
    tokens: list[str] = []
    prev = "<s>"
    for _ in range(length):
        # base logits uniform, green tokens get +delta, then softmax sample
        weights = [green_w if scheme.is_green(prev, t) else 1.0 for t in vocab]
        total = sum(weights)
        r = rng.random() * total
        acc = 0.0
        chosen = vocab[-1]
        for t, w in zip(vocab, weights):
            acc += w
            if r <= acc:
                chosen = t
                break
        tokens.append(chosen)
        prev = chosen
    return tokens


def control_sequence(vocab: list[str], length: int, seed: int) -> list[str]:
    """Generate an unwatermarked control sequence (uniform sampling)."""
    rng = random.Random(seed)
    tokens: list[str] = []
    for _ in range(length):
        tokens.append(rng.choice(vocab))
    return tokens


def substitution_attack(tokens: list[str], vocab: list[str], fraction: float, seed: int) -> list[str]:
    """A token-level bleach: replace a fraction of tokens with random vocabulary."""
    rng = random.Random(seed)
    out = list(tokens)
    n = int(round(fraction * len(out)))
    idx = rng.sample(range(len(out)), min(n, len(out)))
    for i in idx:
        out[i] = rng.choice(vocab)
    return out
