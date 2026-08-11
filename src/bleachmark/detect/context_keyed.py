"""Context-keyed watermark signature (research §3, §5).

A green-list or tournament watermark makes the token choice depend on the
preceding context through a keyed hash. A model style preference does not: it is a
stable favorite regardless of context. This detector uses that difference.

At many neutral contexts the model must pick between two meaning-equivalent words.
The presentation order is randomized per sample, so a position bias becomes noise
and only a content bias survives.

- Concentration: within one context, how decisive the choice is. A watermark and a
  style favorite both raise it. A base model at temperature 1 sits near one-half.
- Majority balance: across contexts, whether the winning word flips. Only a
  context-keyed watermark flips the winner pseudorandomly. A style favorite keeps
  the same winner everywhere.

The signature score is concentration times majority balance. It is high only when
the choice is both decisive per context and flips across contexts, which is the
context-keyed watermark, not style and not noise. It is a proxy, not a proof: a
distortion-free scheme can still hide, and the score needs power and a per-model
baseline to read.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Callable

_ANSWER = re.compile(r"ANSWER\s*[:\-]\s*([A-Za-z]+)")

# meaning-equivalent word pairs; the choice carries a small semantic pull, so a
# base model can flip for a non-watermark reason. Use these only for calibration.
DEFAULT_PAIRS = [
    ("big", "large"),
    ("begin", "start"),
    ("quick", "fast"),
    ("happy", "glad"),
]

# arbitrary meaningless tokens. There is no semantic reason to prefer one, so a
# decisive choice that flips with the context can only be a context-keyed
# watermark, not style and not semantics. This removes the semantic confound.
ARBITRARY_PAIRS = [
    ("A7", "K3"),
    ("QX", "M2"),
    ("ZL", "B9"),
    ("T4", "H8"),
]

DEFAULT_CONTEXTS = [
    "The report was finished on time.",
    "She walked along the quiet road.",
    "The engine started without trouble.",
    "A light rain fell over the city.",
    "The team reviewed the results.",
    "He closed the door behind him.",
    "The market opened early that day.",
    "The children played in the yard.",
    "The plane landed after a long flight.",
    "The garden needed some water.",
    "The meeting ran a little late.",
    "The river flowed past the old mill.",
]


def make_model_choice(model_fn: Callable[[str], str]) -> Callable:
    """Wrap a model into a choice function that returns 'a', 'b', or None."""

    def choose(ctx: str, wa: str, wb: str, rng: random.Random) -> str | None:
        # randomize presentation order so a position bias averages out
        if rng.random() < 0.5:
            first, second, first_is_a = wa, wb, True
        else:
            first, second, first_is_a = wb, wa, False
        prompt = (
            f"CONTEXT: {ctx}\n"
            f"TASK: choose exactly one of these two options: {first} or {second}. "
            f"Either is acceptable. End your reply with the line ANSWER: <choice>"
        )
        out = model_fn(prompt)
        m = _ANSWER.search(out or "")
        word = (m.group(1) if m else (out or "").strip().split()[-1] if (out or "").strip() else "").lower()
        if word == wa.lower():
            return "a"
        if word == wb.lower():
            return "b"
        # a bare first or second word without the ANSWER tag
        if word == first.lower():
            return "a" if first_is_a else "b"
        if word == second.lower():
            return "b" if first_is_a else "a"
        return None

    return choose


@dataclass
class ContextKeyedResult:
    mean_concentration: float
    majority_balance: float
    signature_score: float
    valid_fraction: float
    per_pair: list[dict] = field(default_factory=list)


def context_keyed_score(
    choice_fn: Callable,
    contexts: list[str] | None = None,
    pairs: list[tuple[str, str]] | None = None,
    n_samples: int = 6,
    seed: int = 0,
) -> ContextKeyedResult:
    """Compute the context-keyed signature score for a choice function."""
    contexts = contexts or DEFAULT_CONTEXTS
    pairs = pairs or DEFAULT_PAIRS
    rng = random.Random(seed)

    all_conc: list[float] = []
    all_maj: list[str] = []  # winning label per (pair, context)
    valid = 0
    total = 0
    per_pair: list[dict] = []

    for (wa, wb) in pairs:
        pair_conc: list[float] = []
        pair_maj: list[str] = []
        for ctx in contexts:
            ca = cb = 0
            for _ in range(n_samples):
                total += 1
                c = choice_fn(ctx, wa, wb, rng)
                if c == "a":
                    ca += 1
                    valid += 1
                elif c == "b":
                    cb += 1
                    valid += 1
            n = ca + cb
            if n == 0:
                continue
            pa = ca / n
            pair_conc.append(abs(pa - 0.5) * 2)
            pair_maj.append("a" if pa >= 0.5 else "b")
        if pair_conc:
            p_a = pair_maj.count("a") / len(pair_maj)
            bal = 4 * p_a * (1 - p_a)
            per_pair.append(
                {
                    "pair": f"{wa}/{wb}",
                    "mean_concentration": sum(pair_conc) / len(pair_conc),
                    "majority_balance": bal,
                }
            )
            all_conc.extend(pair_conc)
            all_maj.extend(pair_maj)

    if not all_conc:
        return ContextKeyedResult(0.0, 0.0, 0.0, 0.0, per_pair)
    mean_conc = sum(all_conc) / len(all_conc)
    p_a = all_maj.count("a") / len(all_maj)
    maj_balance = 4 * p_a * (1 - p_a)
    return ContextKeyedResult(
        mean_concentration=mean_conc,
        majority_balance=maj_balance,
        signature_score=mean_conc * maj_balance,
        valid_fraction=valid / max(1, total),
        per_pair=per_pair,
    )


def model_signature(
    model_fn: Callable[[str], str],
    contexts: list[str] | None = None,
    pairs: list[tuple[str, str]] | None = None,
    n_samples: int = 6,
    seed: int = 0,
) -> ContextKeyedResult:
    """Compute the signature for a real model callable."""
    return context_keyed_score(make_model_choice(model_fn), contexts, pairs, n_samples, seed)
