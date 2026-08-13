"""Verify the constrained code probe minimizes the stego surface (FR-46a).

Canonicalization must remove naming, whitespace, comment, and literal-format
channels, leaving only structural token choice. Each generation must be more
than 400 words (FR-49, FR-55). A short function is not useful.
"""

from bleachmark.detect.code import (
    canonicalize, suite_probe, DEFAULT_SUITE, _PROMPT_PY, _PROMPT_C,
)
from bleachmark.detect.length import ATTRIBUTION_WORDS, length_requirement


def test_canonicalize_collapses_cosmetic_channels():
    a = "def solve(a, b):\n    # add\n    result = a + b\n    return result"
    b = "def foo(x, y):\n    z=x+y   # sum\n    return z"
    c = "def bar(p, q):\n\n    total  =  p + q\n    return total"
    assert canonicalize(a) == canonicalize(b) == canonicalize(c)


def test_canonicalize_keeps_structure():
    a = "def solve(a, b):\n    return a + b"
    swapped = "def solve(a, b):\n    return b + a"
    different = "def solve(a, b):\n    return sum([a, b])"
    assert canonicalize(a) != canonicalize(swapped)
    assert canonicalize(a) != canonicalize(different)


def test_canonicalize_handles_non_python():
    # a malformed sample falls back to a whitespace and comment normalization
    out = canonicalize("this is not { python code # note")
    assert "#" not in out and "  " not in out


def _canonical_model():
    forms = [
        "def f(x):\n    a = x + 1\n    return a",
        "def g(y):\n    b = y + 1   # inc\n    return b",
    ]
    s = {"n": 0}

    def fn(prompt):
        s["n"] += 1
        return forms[s["n"] % len(forms)]

    return fn


def _structural_model():
    forms = [
        "def f(x):\n    return x + 1",
        "def f(x):\n    return 1 + x",
        "def f(x):\n    y = x\n    y += 1\n    return y",
    ]
    s = {"n": 0}

    def fn(prompt):
        s["n"] += 1
        return forms[s["n"] % len(forms)]

    return fn


def _pad(text: str) -> str:
    return text + " " + " ".join(f"w{i}" for i in range(ATTRIBUTION_WORDS + 20))


def _long(model):
    inner = model()

    def fn(prompt):
        return _pad(inner(prompt))

    return fn


def test_generation_prompt_demands_more_than_400_words():
    req = length_requirement()
    assert str(ATTRIBUTION_WORDS) in req
    assert "more than" in req.lower()
    assert req in _PROMPT_PY
    assert req in _PROMPT_C


def test_short_samples_are_not_long_enough():
    result = suite_probe(_structural_model(), _canonical_model(), runs=2)
    assert result.long_enough is False
    assert all(t["short"] for t in result.per_task)


def test_suite_probe_reaches_length_band():
    result = suite_probe(_long(_structural_model), _long(_canonical_model), runs=2)
    assert result.corpus_words > ATTRIBUTION_WORDS
    assert result.long_enough
    assert not any(t["short"] for t in result.per_task)


def test_suite_probe_flags_structural_excess_only():
    result = suite_probe(_structural_model(), _canonical_model(), runs=6)
    assert result.control_residual == 0.0
    assert result.candidate_residual > 0.0
    assert result.likely_watermarked
    assert len(result.per_task) == len(DEFAULT_SUITE)
