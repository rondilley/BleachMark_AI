"""Verify the C lexical canonicalizer minimizes the stego surface (FR-46a, C arm).

The C canonicalizer removes naming, whitespace, comment, and literal channels, and
keeps the token structure. The suite probe must run with lang="c" and flag a
structural excess only, exactly as the Python arm does.
"""

from bleachmark.detect.code import canonicalize_for, suite_probe, DEFAULT_SUITE_C
from bleachmark.detect.code_c import canonicalize_c


def test_c_canonicalize_collapses_cosmetic_channels():
    a = "int f(int x){\n    /* add one */\n    int result = x + 1;\n    return result;\n}"
    b = "int f(int y){\n    int z=y+1; // increment\n    return z;\n}"
    c = "int f(int p){\n\n    int  total  =  p + 1 ;\n    return total;\n}"
    assert canonicalize_c(a) == canonicalize_c(b) == canonicalize_c(c)


def test_c_canonicalize_keeps_structure():
    a = "int f(int x){ return x + 1; }"
    swapped = "int f(int x){ return 1 + x; }"
    different = "int f(int x){ int a = x; a += 1; return a; }"
    assert canonicalize_c(a) != canonicalize_c(swapped)
    assert canonicalize_c(a) != canonicalize_c(different)


def test_c_canonicalize_keeps_types_drops_names():
    # a variable rename collapses, but an int -> long type change does not
    same_but_named = "long g(long m){ long q = m + 1; return q; }"
    typed = "int g(int m){ int q = m + 1; return q; }"
    assert canonicalize_c(same_but_named) != canonicalize_c(typed)
    # the string literal is normalized away, so two messages collapse
    s1 = 'int f(int x){ char *m = "hello"; return x; }'
    s2 = 'int f(int x){ char *m = "world"; return x; }'
    assert canonicalize_c(s1) == canonicalize_c(s2)


def test_canonicalize_for_dispatch():
    py = "def f(x):\n    return x + 1"
    c = "int f(int x){ return x + 1; }"
    assert canonicalize_for("python", py) == canonicalize_for("python", py)
    assert canonicalize_for("c", c) != canonicalize_for("python", py)


def _legit_c_model():
    # a control model that emits one canonical form (with cosmetic-only variation)
    forms = [
        "int f(int x){ int a = x + 1; return a; }",
        "int f(int y){ int b = y + 1; /* inc */ return b; }",
    ]
    s = {"n": 0}

    def fn(prompt):
        s["n"] += 1
        return forms[s["n"] % len(forms)]

    return fn


def _structural_c_model():
    # a watermarked model that varies the residual structural channel
    forms = [
        "int f(int x){ return x + 1; }",
        "int f(int x){ return 1 + x; }",
        "int f(int x){ int y = x; y += 1; return y; }",
    ]
    s = {"n": 0}

    def fn(prompt):
        s["n"] += 1
        return forms[s["n"] % len(forms)]

    return fn


def test_c_suite_probe_flags_structural_excess_only():
    result = suite_probe(_structural_c_model(), _legit_c_model(), runs=6, lang="c")
    assert result.control_residual == 0.0
    assert result.candidate_residual > 0.0
    assert result.likely_watermarked
    assert len(result.per_task) == len(DEFAULT_SUITE_C)
