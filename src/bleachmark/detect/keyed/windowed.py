"""Reorder-invariant watermark variants, to bound the reorder bleach (research 3, 7).

The reorder bleach (reverse, block-reverse, and so on) works because a context-keyed green-list
keys each token on the token before it in generation order. A reorder changes that neighbor, so
the green bias no longer lines up.

This module builds watermark variants with a different context, to find where the reorder bleach
stops working:

- unigram: the green set for a token depends only on the token, not on any neighbor. The green
  count is then the count of green tokens, which does not change when the tokens are reordered.
  So the reorder bleach removes nothing, at any granularity. This is the hard bound.
- window: the green set depends on the SORTED multiset of the last w tokens, not their order. A
  reorder inside the window does not change the context, so the reorder bleach is weak against
  it. A reorder across the window still breaks it.
- prev: the standard context-keyed green-list, keyed on the previous token. The reorder bleach
  works against it, and its strength depends on the unit granularity (the eleventh round).

The trade-off is the point. A context-free watermark resists the reorder bleach fully, but it is
easier to remove by a token substitution, because each green token is green on its own. A
context-keyed watermark resists substitution better, but it gives the reorder bleach a channel.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

_MOD = 1 << 32


def _green(key: str, context: str, token: str, gamma: float) -> bool:
    h = hashlib.sha256(f"{key}|{context}|{token}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") < gamma * _MOD


def _h32(key: str, s: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{key}|{s}".encode("utf-8")).digest()[:4], "big")


def _selfhash_green(key: str, prev_window: list[str], token: str, gamma: float) -> bool:
    """SelfHash green membership (Kirchenbauer 2306.04634, Algorithm 3).

    The seed is a min over the width-h context that INCLUDES the candidate token, so the
    green set depends on the token itself, not only the left context. A min combination
    makes the seed hard to steal from the context alone. Green membership of the candidate
    then follows from a hash of the seed and the candidate, so about gamma of the vocabulary
    is green at each position.
    """
    ctx_min = min((_h32(key, p) for p in prev_window), default=_MOD)
    seed = min(ctx_min, _h32(key, token))
    return _h32(f"{key}|{seed}", token) < gamma * _MOD


@dataclass
class ContextScheme:
    key: str
    vocab: list[str]
    gamma: float = 0.25
    kind: str = "prev"     # "unigram" | "prev" | "window" | "selfhash"
    window: int = 3
    h: int = 4             # SelfHash context width (h-1 previous tokens plus the token itself)

    def context(self, history: list[str]) -> str:
        if self.kind == "unigram":
            return ""
        if self.kind == "window":
            w = history[-self.window:]
            return "+".join(sorted(w)) if w else "<s>"
        if self.kind == "selfhash":
            return "|".join(history[-(self.h - 1):]) if self.h > 1 else ""
        return history[-1] if history else "<s>"

    def is_green(self, context: str, token: str) -> bool:
        if self.kind == "selfhash":
            prev = context.split("|") if context else []
            return _selfhash_green(self.key, prev, token, self.gamma)
        return _green(self.key, context, token, self.gamma)

    def z_score(self, tokens: list[str]) -> float:
        vocab_set = set(self.vocab)
        green = scored = 0
        history: list[str] = []
        for t in tokens:
            ctx = self.context(history)
            if t in vocab_set:
                scored += 1
                if self.is_green(ctx, t):
                    green += 1
            history.append(t)
        if scored == 0:
            return 0.0
        var = scored * self.gamma * (1 - self.gamma)
        return (green - self.gamma * scored) / math.sqrt(var) if var > 0 else 0.0


def generate_in_unit_order(scheme: ContextScheme, unit_sizes: list[int], gen_order: list[int],
                           seed: int, delta: float = 2.0) -> list[str]:
    """Generate a green-list watermarked sequence in a unit order, with the scheme context."""
    rng = random.Random(seed)
    offsets, acc = [], 0
    for s in unit_sizes:
        offsets.append(acc)
        acc += s
    reading: list[str] = [""] * acc
    gw = math.exp(delta)
    history: list[str] = []
    for ui in gen_order:
        for k in range(unit_sizes[ui]):
            ctx = scheme.context(history)
            weights = [gw if scheme.is_green(ctx, t) else 1.0 for t in scheme.vocab]
            total = sum(weights)
            r = rng.random() * total
            accw = 0.0
            chosen = scheme.vocab[-1]
            for t, w in zip(scheme.vocab, weights):
                accw += w
                if r <= accw:
                    chosen = t
                    break
            reading[offsets[ui] + k] = chosen
            history.append(chosen)
    return reading


def _unit_sizes(total_tokens: int, unit_tokens: int) -> list[int]:
    n_units = max(1, total_tokens // max(1, unit_tokens))
    base = total_tokens // n_units
    sizes = [base] * n_units
    for i in range(total_tokens - base * n_units):
        sizes[i] += 1
    return sizes


def reorder_degradation(scheme: ContextScheme, unit_tokens: int, total_tokens: int = 300,
                        delta: float = 2.0, n_eval: int = 3, seed: int = 0) -> dict:
    """Measure the reverse-order bleach degradation against this scheme at a unit granularity."""
    z_ident, z_reverse = [], []
    for i in range(n_eval):
        sizes = _unit_sizes(total_tokens, unit_tokens)
        n_units = len(sizes)
        # the same seed for both arms: only the order differs, so the measure isolates the
        # reorder effect and is not sampling noise. A context-free watermark then reads as
        # exactly zero degradation, its true value.
        ident = generate_in_unit_order(scheme, sizes, list(range(n_units)), seed + i, delta)
        reverse = generate_in_unit_order(scheme, sizes, list(range(n_units))[::-1], seed + i, delta)
        z_ident.append(scheme.z_score(ident))
        z_reverse.append(scheme.z_score(reverse))
    base = sum(z_ident) / len(z_ident)
    after = sum(z_reverse) / len(z_reverse)
    degradation = max(0.0, 1.0 - after / base) if base > 1e-6 else 0.0
    return {"kind": scheme.kind, "unit_tokens": unit_tokens, "base_z": round(base, 2),
            "reverse_z": round(after, 2), "degradation": round(degradation, 3)}
