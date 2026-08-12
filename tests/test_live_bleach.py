"""Tests for the live-bleach functional gate and the bleach loop (no network).

The functional gate is the meaning gate for code: it compiles the code and runs a unit
test. Correct code passes, wrong code fails. The bleach loop uses a model double so no
network is needed. The C tests skip when no compiler is on the machine.
"""

import shutil

import pytest

from bleachmark.bleach.live import functional_gate, bleach_task, bleach_gap, TASKS

_HAS_GCC = shutil.which("gcc") is not None
_T = {t.name: t for t in TASKS}


def test_python_gate_passes_correct_and_fails_wrong():
    good = ("def solve(a):\n"
            "    if a < 2: return 0\n"
            "    d = 2\n"
            "    while d * d <= a:\n"
            "        if a % d == 0: return 0\n"
            "        d += 1\n"
            "    return 1")
    wrong = "def solve(a):\n    return 1"
    assert functional_gate(good, _T["is_prime"], "python").passes
    assert not functional_gate(wrong, _T["is_prime"], "python").passes


def test_python_gate_flags_a_syntax_error():
    broken = "def solve(a)\n    return a"  # missing colon
    r = functional_gate(broken, _T["is_prime"], "python")
    assert not r.compiles and not r.passes


@pytest.mark.skipif(not _HAS_GCC, reason="no C compiler on this machine")
def test_c_gate_passes_correct_and_fails_wrong():
    good = "int solve(int a){ if(a<2) return 0; for(int d=2; d*d<=a; d++){ if(a%d==0) return 0; } return 1; }"
    wrong = "int solve(int a){ return a % 2; }"
    assert functional_gate(good, _T["is_prime"], "c").passes
    assert not functional_gate(wrong, _T["is_prime"], "c").passes


def _gcd_double():
    # a model double: first the "watermarked" original, then a restructured bleach
    forms = [
        "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
        "def solve(a, b):\n    while b != 0:\n        r = a % b\n        a = b\n        b = r\n    return a",
    ]
    s = {"n": -1}

    def fn(prompt):
        s["n"] += 1
        return forms[min(s["n"], len(forms) - 1)]

    return fn


def test_bleach_task_preserves_meaning_and_changes_structure():
    r = bleach_task(_gcd_double(), _T["gcd"], "python", attempts=2)
    assert r.original_ok
    assert r.meaning_preserved       # the bleached gcd still passes the unit test
    assert r.changed                 # and it is structurally different from the input
    assert r.structural_change > 0.0


def test_bleach_task_reports_a_broken_original():
    # a model that always returns wrong code: the original fails the gate, so we stop
    def bad_fn(prompt):
        return "def solve(a, b):\n    return 0"

    r = bleach_task(bad_fn, _T["gcd"], "python", attempts=2)
    assert not r.original_ok
    assert not r.meaning_preserved


def _gcd_gap_double():
    # valid gcd forms; the bleach prompt returns a different valid form
    gen = [
        "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
        "def solve(a, b):\n    while b != 0:\n        r = a % b\n        a = b\n        b = r\n    return a",
    ]
    ble = [
        "def solve(a, b):\n    while b > 0:\n        t = a % b\n        a = b\n        b = t\n    return a",
        "def solve(a, b):\n    while 0 != b:\n        c = a % b\n        a = b\n        b = c\n    return a",
        "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
    ]
    sg = {"n": -1}
    sb = {"n": -1}

    def fn(prompt):
        if "Rewrite" in prompt:
            sb["n"] += 1
            return ble[sb["n"] % len(ble)]
        sg["n"] += 1
        return gen[sg["n"] % len(gen)]

    return fn


def test_bleach_gap_runs_and_reports_before_and_after():
    r = bleach_gap(_gcd_gap_double(), _T["gcd"], "python", n_samples=16, attempts=2)
    assert r.n_valid == 16               # every generated sample is valid gcd code
    assert r.bleached_rate == 1.0        # a meaning-preserving bleach was found each time
    assert r.note == "ok"
    assert r.slots_before >= 2
    assert isinstance(r.gap_before, float) and isinstance(r.gap_after, float)
    assert 0.0 <= r.p_before <= 1.0 and 0.0 <= r.p_after <= 1.0
    # the bleach does not raise the raw structural signal
    assert r.z_after <= r.z_before + 1e-6


def _canonical_double():
    # diverse valid gcd forms from the generator; the canonical bleach converges to one
    gen = [
        "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
        "def solve(a, b):\n    while b != 0:\n        r = a % b\n        a = b\n        b = r\n    return a",
        "def solve(a, b):\n    while b > 0:\n        t = a % b\n        a = b\n        b = t\n    return a",
    ]
    canon = "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a"
    s = {"n": -1}

    def fn(prompt):
        if "textbook" in prompt or "most commonly" in prompt:
            return canon
        s["n"] += 1
        return gen[s["n"] % len(gen)]

    return fn


def test_canonical_bleach_closes_the_corpus_channel():
    r = bleach_gap(_canonical_double(), _T["gcd"], "python", n_samples=15, mode="canonical", attempts=2)
    assert r.mode == "canonical"
    assert r.slots_before >= 2          # the diverse corpus has a channel
    assert r.slots_after < r.slots_before   # the canonical bleach shrinks it
    assert r.slots_after <= 1           # the corpus converges to one form
    assert r.note == "channel closed after the bleach"


def test_deterministic_normalizer_closes_structural_slots():
    import random
    from bleachmark.detect.features import featurize
    from bleachmark.detect.code import structural_normalize

    def make(o1, o2, o3, cmp):
        a = "a + b" if o1 else "b + a"
        b = "a * b" if o2 else "b * a"
        c = "x + y" if o3 else "y + x"
        d = "a == b" if cmp else "b == a"
        return f"def solve(a, b):\n    x = {a}\n    y = {b}\n    z = {c}\n    return z if {d} else x"

    rng = random.Random(0)
    corpus = [make(rng.random() < 0.5, rng.random() < 0.5, rng.random() < 0.5, rng.random() < 0.5)
              for _ in range(24)]
    before = featurize(corpus, "python", k=4).n_slots
    after = featurize([structural_normalize(c) for c in corpus], "python", k=4).n_slots
    # the corpus varies only in operand order and comparison direction
    assert before >= 2
    # the deterministic normalizer collapses every such sample to one form
    assert after == 0


def _compare_double():
    # a corpus that varies in operand order (the normalizer collapses it); the diversify
    # bleach returns other valid gcd forms
    gen = [
        "def solve(a, b):\n    while b != 0:\n        a, b = b, a % b\n    return a",
        "def solve(a, b):\n    while 0 != b:\n        a, b = b, a % b\n    return a",
    ]
    div = "def solve(a, b):\n    while b > 0:\n        r = a % b\n        a = b\n        b = r\n    return a"
    s = {"n": -1}

    def fn(prompt):
        if "DIFFERENT" in prompt:
            return div
        s["n"] += 1
        return gen[s["n"] % len(gen)]

    return fn


def test_compare_bleach_modes_reports_three_ways():
    from bleachmark.bleach.live import compare_bleach_modes

    r = compare_bleach_modes(_compare_double(), _T["gcd"], "python", n_samples=16, attempts=2)
    assert r["n_valid"] == 16
    for arm in ("original", "deterministic", "diversify"):
        assert arm in r
        assert "slots" in r[arm] and "gap" in r[arm]
    # the deterministic bleach keeps every sample meaning-valid (it is semantics-preserving)
    assert r["deterministic"]["meaning_kept_rate"] == 1.0
