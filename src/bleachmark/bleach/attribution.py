"""Blind attribution bleach (FR-40).

The bleach runs blind: it does not depend on the attribution estimate. It applies a
heavy, meaning-preserving perturbation to lower the recoverable attribution bits.
For a token sequence it is a substitution attack; for prose it is the paraphrase
strength through the model gateway. A blind bleach is honest with Bet 1 and with the
undetectability limit.
"""

from __future__ import annotations

import random


def blind_token_bleach(tokens: list[str], vocab: list[str], fraction: float, seed: int) -> list[str]:
    """Replace a fraction of tokens with random vocabulary, blind to any payload."""
    rng = random.Random(seed)
    out = list(tokens)
    n = int(round(fraction * len(out)))
    for i in rng.sample(range(len(out)), min(n, len(out))):
        out[i] = rng.choice(vocab)
    return out
