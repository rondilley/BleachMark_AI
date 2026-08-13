"""Scheme benchmark: detectability drop and meaning cost per watermark family (BC-04).

A researcher runs this module and gets a table. Each row is a watermark scheme.
Each column is a bleach. Each cell holds the z drop and the meaning cost. The run
uses reference generators with a known key, so the numbers are validation, not a
wiring check (SUCCESS_CRITERIA 4, FR-44).

The English lexicon is the shared vocabulary. The round-trip bleach is then a real
token change, not a no-op on abstract w0 tokens.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from ..bleach.translate import english_vocab, roundtrip_tokens
from ..detect.keyed.greenlist import GreenListScheme
from ..detect.keyed.synthid import SynthIDScheme
from ..detect.keyed.windowed import ContextScheme, generate_in_unit_order
from ..harness.generators import substitution_attack, watermarked_sequence

SCHEMES = ("greenlist_prev", "unigram", "window", "selfhash", "synthid")
BLEACHES = ("identity", "substitution_15", "substitution_30", "reorder_sentence", "roundtrip")
Z_THRESHOLD = 4.0
SENTENCE_UNIT = 12


@dataclass
class Cell:
    scheme: str
    bleach: str
    z_before: float
    z_after: float
    detectability_drop: float
    tpr_before: float
    tpr_after: float
    meaning_cost: float
    samples: int
    length: int


def _scheme_obj(kind: str, vocab: list[str], key: str = "bc04-key"):
    if kind == "synthid":
        return SynthIDScheme(key=key, vocab=vocab)
    if kind == "greenlist_prev":
        return GreenListScheme(key=key, vocab=vocab, gamma=0.25)
    name = {"unigram": "unigram", "window": "window", "selfhash": "selfhash"}[kind]
    return ContextScheme(key=key, vocab=vocab, gamma=0.25, kind=name)


def generate_watermarked(kind: str, vocab: list[str], length: int, seed: int,
                         delta: float = 2.0) -> list[str]:
    obj = _scheme_obj(kind, vocab)
    if kind == "synthid":
        return obj.generate(length, seed)
    if kind == "greenlist_prev":
        return watermarked_sequence(obj, length, seed, delta=delta)
    return generate_in_unit_order(obj, [length], [0], seed, delta=delta)


def score_tokens(kind: str, vocab: list[str], tokens: list[str]) -> float:
    return _scheme_obj(kind, vocab).z_score(tokens)


def _reorder_units(tokens: list[str], unit: int = SENTENCE_UNIT) -> list[str]:
    units = [tokens[i : i + unit] for i in range(0, len(tokens), unit)]
    return [t for u in reversed(units) for t in u]


def apply_bleach(name: str, tokens: list[str], vocab: list[str], seed: int) -> list[str]:
    if name == "identity":
        return list(tokens)
    if name == "substitution_15":
        return substitution_attack(tokens, vocab, 0.15, seed)
    if name == "substitution_30":
        return substitution_attack(tokens, vocab, 0.30, seed)
    if name == "reorder_sentence":
        return _reorder_units(tokens)
    if name == "roundtrip":
        return roundtrip_tokens(tokens)
    raise ValueError(f"unknown bleach: {name}")


def meaning_cost(name: str, before: list[str], after: list[str]) -> float:
    """Token-level meaning cost. 0 keeps every token. 1 replaces every token.

    The cost is 1 minus the multiset overlap. A reorder keeps the bag of tokens, so
    its cost is 0. That is the lossless-reorder fact. A human reading cost is a
    different number (strategies fidelity 0.85 at sentence grain) and is not this cell.
    """
    if not before:
        return 0.0
    kept = sum((Counter(before) & Counter(after)).values())
    return 1.0 - kept / max(len(before), 1)


def _drop(z_before: float, z_after: float) -> float:
    if z_before <= 1e-6:
        return 0.0
    return max(0.0, 1.0 - z_after / z_before)


def measure_scheme(scheme: str, vocab: list[str], samples: int, length: int,
                   seed: int = 0, delta: float = 2.0) -> list[Cell]:
    """Generate one corpus per scheme, then apply every bleach to that corpus.

    One corpus keeps the before-z the same across bleaches (lessons: do not
    regenerate when you compare modes).
    """
    corpus = [
        generate_watermarked(scheme, vocab, length, seed + i, delta=delta)
        for i in range(samples)
    ]
    z_before = [score_tokens(scheme, vocab, t) for t in corpus]
    mean_b = sum(z_before) / len(z_before)
    tp_b = sum(1 for z in z_before if z >= Z_THRESHOLD)
    cells = []
    for bleach in BLEACHES:
        za: list[float] = []
        costs: list[float] = []
        tp_a = 0
        for i, tokens in enumerate(corpus):
            attacked = apply_bleach(bleach, tokens, vocab, seed=10_000 + i)
            a = score_tokens(scheme, vocab, attacked)
            za.append(a)
            costs.append(meaning_cost(bleach, tokens, attacked))
            if a >= Z_THRESHOLD:
                tp_a += 1
        mean_a = sum(za) / len(za)
        cells.append(Cell(
            scheme=scheme,
            bleach=bleach,
            z_before=round(mean_b, 3),
            z_after=round(mean_a, 3),
            detectability_drop=round(_drop(mean_b, mean_a), 3),
            tpr_before=round(tp_b / samples, 3),
            tpr_after=round(tp_a / samples, 3),
            meaning_cost=round(sum(costs) / len(costs), 3),
            samples=samples,
            length=length,
        ))
    return cells


def run_scheme_benchmark(samples: int = 24, length: int = 400, seed: int = 1,
                         delta: float = 2.0) -> dict:
    """Run every scheme against every bleach. Returns a table plus a summary."""
    vocab = english_vocab()
    cells = []
    for s in SCHEMES:
        cells.extend(measure_scheme(s, vocab, samples, length, seed=seed, delta=delta))
    return {
        "criterion": "BC-04",
        "vocab": len(vocab),
        "samples": samples,
        "length": length,
        "z_threshold": Z_THRESHOLD,
        "schemes": list(SCHEMES),
        "bleaches": list(BLEACHES),
        "cells": [asdict(c) for c in cells],
        "note": (
            "Keyed reference generators. Detectability drop is 1 - z_after/z_before. "
            "Meaning cost is the fraction of tokens that change. Reorder keeps the "
            "token multiset so its token cost is 0."
        ),
    }


def to_markdown_benchmark(result: dict) -> str:
    """Human table: one row per scheme, drop and cost per bleach."""
    by = {(c["scheme"], c["bleach"]): c for c in result["cells"]}
    lines = [
        "# Scheme benchmark (BC-04)",
        "",
        f"Samples: {result['samples']}. Length: {result['length']} tokens. "
        f"Vocabulary: {result['vocab']} English words. "
        f"Threshold z >= {result['z_threshold']}.",
        "",
        result["note"],
        "",
        "Each cell is detectability drop / meaning cost.",
        "",
    ]
    header = "| Scheme | " + " | ".join(result["bleaches"]) + " |"
    sep = "| --- | " + " | ".join("---" for _ in result["bleaches"]) + " |"
    lines.append(header)
    lines.append(sep)
    for scheme in result["schemes"]:
        bits = []
        for bleach in result["bleaches"]:
            c = by[(scheme, bleach)]
            bits.append(f"{c['detectability_drop']:.2f} / {c['meaning_cost']:.2f}")
        lines.append("| " + scheme + " | " + " | ".join(bits) + " |")
    lines.append("")
    lines.append("## z before and after")
    lines.append("")
    lines.append("| Scheme | Bleach | z before | z after | TPR before | TPR after |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for c in result["cells"]:
        lines.append(
            f"| {c['scheme']} | {c['bleach']} | {c['z_before']} | {c['z_after']} | "
            f"{c['tpr_before']} | {c['tpr_after']} |"
        )
    return "\n".join(lines)
