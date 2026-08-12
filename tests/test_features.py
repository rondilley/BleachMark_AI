"""Tests for the code featurizer and its end-to-end use with the partition test.

The featurizer must ignore cosmetic variation (names, comments), find a structural
slot, and feed a (slot, variant) matrix that the partition test can separate: a
keyed slot-specific bias reads as a watermark, a slot-independent style does not.
"""

import hashlib
import random

from bleachmark.detect.features import featurize
from bleachmark.detect.partition_test import steal_and_test


def test_featurize_ignores_cosmetic_variation():
    samples = [
        "def f(x):\n    result = x + 1\n    return result",
        "def g(y):\n    total = y + 1  # add one\n    return total",
        "def h(p):\n\n    out  =  p + 1\n    return out",
    ]
    fm = featurize(samples, "python", k=4)
    # after canonicalization these are identical, so there is no slot
    assert fm.n_slots == 0


def test_featurize_finds_a_structural_slot():
    samples = [
        "def f(x):\n    a = x + 1\n    return a",
        "def f(x):\n    a = 1 + x\n    return a",
        "def f(x):\n    a = x + 1\n    return a",
    ]
    fm = featurize(samples, "python", k=4)
    assert fm.n_slots >= 1
    # the operand-order slot has two variants across the samples
    assert any(len(vocab) >= 2 for vocab in fm.slot_vocab)


# --- an end-to-end corpus with M independent structural slots -----------------

M = 12


def _sample(orders: list[int]) -> str:
    lines = ["def f(x):"]
    prev = "x"
    for i, o in enumerate(orders):
        rhs = f"{prev} + {i + 1}" if o == 0 else f"{i + 1} + {prev}"
        lines.append(f"    a{i} = {rhs}")
        prev = f"a{i}"
    lines.append(f"    return {prev}")
    return "\n".join(lines)


def _green(i: int) -> int:
    return hashlib.sha256(f"key|{i}".encode()).digest()[0] & 1


def _watermarked_corpus(n: int, p: float = 0.85) -> list[str]:
    rng = random.Random(1)
    out = []
    for _ in range(n):
        orders = [(_green(i) if rng.random() < p else 1 - _green(i)) for i in range(M)]
        out.append(_sample(orders))
    return out


def _style_corpus(n: int, p: float = 0.85) -> list[str]:
    # slot-independent preference: order 0 favored at every slot
    rng = random.Random(2)
    out = []
    for _ in range(n):
        orders = [(0 if rng.random() < p else 1) for _ in range(M)]
        out.append(_sample(orders))
    return out


def test_featurize_plus_partition_test_flags_keyed_not_style():
    wm = featurize(_watermarked_corpus(48), "python", k=4)
    st = featurize(_style_corpus(48), "python", k=4)
    assert wm.n_slots >= M - 2  # the operand-order slots are found
    r_wm = steal_and_test(wm.rows, wm.k, wm.n_slots, permutations=300, seed=0)
    r_st = steal_and_test(st.rows, st.k, st.n_slots, permutations=300, seed=0)
    # the keyed corpus reads as a watermark; the style corpus does not
    assert r_wm.keyed_signal
    assert not r_st.keyed_signal
    assert r_wm.gap - r_st.gap > 3.0
