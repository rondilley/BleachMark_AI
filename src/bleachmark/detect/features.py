"""Featurize model code into slots and variants (FR-45, FR-53 to FR-55).

The steal-and-test partition z-test works on a matrix of (slot, variant) choices.
This module turns a set of code samples for one task into that matrix.

Method:

1. Canonicalize each sample, so naming, formatting, and comments are not slots.
2. Tokenize each canonical form.
3. Pick a reference: the most common token sequence (the canonical skeleton).
4. Align each sample to the reference with a token diff. A reference position where
   the samples agree is not a slot. A reference position where the samples disagree
   is a SLOT, and the token the sample puts there is its VARIANT.
5. Keep only the varying slots. Map each slot's variants to a fixed set of k indices:
   the most common variant is 0, the next is 1, and so on, and the rest go to the
   last bucket. So the matrix has a fixed variant count k for the detector.

A green-list watermark biases the token choice, so it acts in these slots. The
featurization exposes the residual token-choice channel, after the cosmetic channels
are removed by canonicalization. It is honest and lexical, not a full parse.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass

from .code import _TOKEN, canonicalize_for


def _tokens(sample: str, lang: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(canonicalize_for(lang, sample)))


@dataclass
class FeatureMatrix:
    rows: list[list[int]]      # one row per sample, one column per slot, cell = variant
    n_slots: int
    k: int
    slot_positions: list[int]  # the reference index of each kept slot
    slot_vocab: list[dict]     # per-slot variant token -> index (for reporting)


def featurize(samples: list[str], lang: str, k: int = 4) -> FeatureMatrix:
    """Turn code samples for one task into a fixed-k (slot, variant) matrix."""
    toks = [_tokens(s, lang) for s in samples]
    if not toks:
        return FeatureMatrix([], 0, k, [], [])
    ref = list(Counter(toks).most_common(1)[0][0])
    n = len(ref)

    # per reference position, collect the variant token each sample places there
    per_pos: list[list[str]] = [[] for _ in range(n)]
    for t in toks:
        placed = [None] * n
        sm = difflib.SequenceMatcher(a=ref, b=list(t), autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for off in range(i2 - i1):
                    placed[i1 + off] = ref[i1 + off]
            elif op == "replace":
                var = " ".join(t[j1:j2]) or "<del>"
                for pos in range(i1, i2):
                    placed[pos] = var
            elif op == "delete":
                for pos in range(i1, i2):
                    placed[pos] = "<del>"
            # 'insert' has no reference position; it is dropped to keep slots aligned
        for pos in range(n):
            per_pos[pos].append(placed[pos] if placed[pos] is not None else ref[pos])

    # a slot is a reference position with more than one observed variant
    slot_positions = [pos for pos in range(n) if len(set(per_pos[pos])) > 1]
    slot_vocab: list[dict] = []
    columns: list[list[int]] = []
    for pos in slot_positions:
        # Order variants by a slot-INDEPENDENT rule (the token string), never by
        # frequency. Frequency ranking would map the favored variant to index 0 at
        # every slot, which erases the slot-specific green index a keyed watermark
        # writes and makes the slot-permutation null blind to it.
        order = sorted(set(per_pos[pos]))
        vocab: dict[str, int] = {}
        for i, tok in enumerate(order):
            vocab[tok] = min(i, k - 1)  # first k-1 keep an index, the rest share k-1
        slot_vocab.append(vocab)
        columns.append([vocab[tok] for tok in per_pos[pos]])

    n_slots = len(slot_positions)
    rows = [[columns[c][r] for c in range(n_slots)] for r in range(len(samples))]
    return FeatureMatrix(rows=rows, n_slots=n_slots, k=k,
                         slot_positions=slot_positions, slot_vocab=slot_vocab)
