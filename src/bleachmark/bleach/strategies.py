"""A library of bleach strategies and the space the evolution searches (FR-26, FR-29).

The reverse-order bleach showed the principle: a context-keyed watermark keys each token on
its neighbor in GENERATION order. So any transform that makes the model generate in an order
that is not the reading order, then puts the reading order back with a deterministic step,
breaks the context-keying. A forward-key detector then does not line up, and the z-score
drops. The reorder is at the unit level (a clause, a sentence, a paragraph), so the model can
still write each unit correctly.

There are two families:

- REORDER: the model writes the units in a permuted order (reverse, block-reverse, stride,
  rotate), and a deterministic inverse permutation restores the reading order. The context
  breaks at the unit boundaries, so a finer unit breaks more context but is harder to keep
  coherent. That is the trade-off the evolution searches.
- TRANSCODE: the model writes in another language, then a deterministic step translates to
  English. The watermark was keyed on the other-language tokens with the other-language key,
  so the English text carries no English-key watermark. The fidelity is the translation
  quality.

A strategy is a small genome: the family, one parameter (block, stride, or rotate), the unit
size, and a translation quality for transcode. Each strategy compiles to a real prompt and a
deterministic restore, so a discovered strategy is deployable on real prose.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

REORDER_KINDS = ("identity", "reverse", "block_reverse", "stride", "rotate")
ALL_KINDS = REORDER_KINDS + ("transcode",)

# unit granularity in approximate tokens per unit: token, clause, sentence, paragraph
UNIT_TOKENS = (1, 4, 12, 40)


@dataclass
class Strategy:
    kind: str = "reverse"
    param: int = 2               # block size, stride k, or rotate amount
    unit_tokens: int = 12        # granularity (approximate tokens per unit)
    translation_quality: float = 0.8  # transcode only

    def generation_order(self, n_units: int) -> list[int]:
        """The order the model generates the reading units in."""
        n = max(1, n_units)
        idx = list(range(n))
        if self.kind == "identity" or self.kind == "transcode":
            return idx
        if self.kind == "reverse":
            return idx[::-1]
        if self.kind == "block_reverse":
            b = max(2, self.param)
            out: list[int] = []
            for start in range(0, n, b):
                out.extend(idx[start:start + b][::-1])
            return out
        if self.kind == "stride":
            k = max(2, self.param)
            return [i for phase in range(k) for i in range(phase, n, k)]
        if self.kind == "rotate":
            r = self.param % n if n else 0
            return idx[r:] + idx[:r]
        return idx

    def inverse_order(self, n_units: int) -> list[int]:
        """The deterministic restore: where each generated unit goes in the reading order."""
        gen = self.generation_order(n_units)
        inv = [0] * len(gen)
        for gen_pos, reading_pos in enumerate(gen):
            inv[reading_pos] = gen_pos
        return inv

    def restore(self, generated_units: list) -> list:
        """Put units the model generated (in generation order) back into reading order."""
        n = len(generated_units)
        order = self.generation_order(n)
        reading = [None] * n
        for gen_pos, reading_pos in enumerate(order):
            reading[reading_pos] = generated_units[gen_pos]
        return reading

    def unit_name(self) -> str:
        return {1: "word", 4: "clause", 12: "sentence", 40: "paragraph"}.get(self.unit_tokens, "unit")

    def mutate(self, rng: random.Random) -> "Strategy":
        g = Strategy(self.kind, self.param, self.unit_tokens, self.translation_quality)
        gene = rng.choice(["kind", "param", "unit_tokens", "quality"])
        if gene == "kind":
            g.kind = rng.choice(ALL_KINDS)
        elif gene == "param":
            g.param = rng.choice([2, 3, 4, 6])
        elif gene == "unit_tokens":
            g.unit_tokens = rng.choice(UNIT_TOKENS)
        else:
            g.translation_quality = rng.choice([0.6, 0.7, 0.8, 0.9])
        return g

    def describe(self) -> str:
        if self.kind == "transcode":
            return f"transcode (write in another language, deterministic translate, quality {self.translation_quality})"
        if self.kind == "identity":
            return "identity (no bleach)"
        detail = ""
        if self.kind == "block_reverse":
            detail = f", block {max(2, self.param)}"
        elif self.kind == "stride":
            detail = f", stride {max(2, self.param)}"
        elif self.kind == "rotate":
            detail = f", rotate {self.param}"
        return f"{self.kind} by {self.unit_name()}{detail}"
