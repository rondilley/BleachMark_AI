"""Scheme benchmark table (BC-04).

A small run must produce a cell for every scheme and every bleach. Identity must
not drop the z. A 30 percent substitution must drop more than identity. A unigram
mark must resist a sentence reorder. Every cell carries a meaning cost.
"""

from bleachmark import cli
from bleachmark.harness.schemes import (
    BLEACHES,
    SCHEMES,
    run_scheme_benchmark,
    to_markdown_benchmark,
)


_SMALL = None


def _small():
    global _SMALL
    if _SMALL is None:
        _SMALL = run_scheme_benchmark(samples=4, length=80, seed=2)  # small: the suite stays fast
    return _SMALL


def test_table_covers_every_scheme_and_bleach():
    result = _small()
    pairs = {(c["scheme"], c["bleach"]) for c in result["cells"]}
    assert result["criterion"] == "BC-04"
    for s in SCHEMES:
        for b in BLEACHES:
            assert (s, b) in pairs


def test_identity_does_not_drop_detectability():
    result = _small()
    for c in result["cells"]:
        if c["bleach"] == "identity":
            assert c["detectability_drop"] < 0.05
            assert c["meaning_cost"] == 0.0
            assert c["z_before"] > 3.0


def test_substitution_drops_more_than_identity():
    result = _small()
    by = {(c["scheme"], c["bleach"]): c for c in result["cells"]}
    for s in SCHEMES:
        ident = by[(s, "identity")]["detectability_drop"]
        sub = by[(s, "substitution_30")]["detectability_drop"]
        assert sub > ident
        assert by[(s, "substitution_30")]["meaning_cost"] > 0.2


def test_unigram_resists_sentence_reorder():
    result = _small()
    by = {(c["scheme"], c["bleach"]): c for c in result["cells"]}
    assert by[("unigram", "reorder_sentence")]["detectability_drop"] < 0.1
    assert by[("unigram", "reorder_sentence")]["meaning_cost"] == 0.0


def test_markdown_table_renders():
    md = to_markdown_benchmark(_small())
    assert "BC-04" in md
    assert "greenlist_prev" in md
    assert "roundtrip" in md
    assert "detectability drop" in md.lower()


def test_cli_parser_has_benchmark():
    args = cli.build_parser().parse_args(["benchmark", "--samples", "3", "--length", "40"])
    assert args.command == "benchmark"
    assert args.samples == 3
    assert args.length == 40
    defaults = cli.build_parser().parse_args(["benchmark"])
    assert defaults.samples == 24
    assert defaults.length == 400
