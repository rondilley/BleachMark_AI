"""Round-trip translation bleach (FR-29, research 4, arXiv:2402.14007).

A post-hoc round-trip translates existing English to a pivot language and back.
The token-level watermark is keyed on the original English tokens, so a meaning-safe
relabel through another language drops the green count. This is a different attack
from the reversed-word transcode: the model does not need to write a cipher. The
current models write Spanish. They do not write reversed English at editorial length
(lessons, 2026-08-11).

The default translator is a bundled English-Spanish dictionary with synonym collapse.
Several English words share one Spanish gloss. The reverse map returns one canonical
English word. The collapse changes tokens and keeps related meaning. The data lives
in data/translate/en_es.json (MR-02).

A caller may supply outbound and inbound callables for a real MT engine or a local
unwatermarked model. Those callables go through the model gateway (SR-06, SR-09).
The inbound path must not be the marking model, or the return trip can re-mark the
text.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from . import BleachResult
from .gate import MeaningGate
from .normalize import normalize_carriers

_DATA = os.path.join(
    os.path.dirname(__file__), "..", "data", "translate", "en_es.json"
)
_WORD_OR_OTHER = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


@lru_cache(maxsize=1)
def load_lexicon(path: str | None = None) -> dict:
    """Load the pivot lexicon. Returns en_to_pivot, pivot_to_en, and the pivot name."""
    src = path or _DATA
    with open(src, encoding="utf-8") as fh:
        raw = json.load(fh)
    en_to_pivot: dict[str, str] = {}
    pivot_to_en: dict[str, str] = {}
    for group in raw.get("groups", []):
        pivot = group["pivot"]
        pivot_to_en[pivot] = group["canonical"]
        for word in group["en"]:
            en_to_pivot[word] = pivot
    for en, pivot in raw.get("one_to_one", {}).items():
        en_to_pivot[en] = pivot
        pivot_to_en[pivot] = en
    return {
        "pivot": raw.get("pivot", "es"),
        "en_to_pivot": en_to_pivot,
        "pivot_to_en": pivot_to_en,
    }


def english_vocab() -> list[str]:
    """Every English word in the lexicon, sorted. Suitable as a green-list vocabulary."""
    return sorted(load_lexicon()["en_to_pivot"])


def content_vocab() -> list[str]:
    """English words that sit in a synonym group (they can collapse)."""
    src = _DATA
    with open(src, encoding="utf-8") as fh:
        raw = json.load(fh)
    words: set[str] = set()
    for group in raw.get("groups", []):
        words.update(group["en"])
    return sorted(words)


def _case_match(src: str, dest: str) -> str:
    if not dest:
        return dest
    if src.isupper():
        return dest.upper()
    if src[:1].isupper():
        return dest[:1].upper() + dest[1:]
    return dest


def _map_word(word: str, table: dict[str, str]) -> str:
    mapped = table.get(word.lower())
    if mapped is None:
        return word
    return _case_match(word, mapped)


def forward_translate(text: str) -> str:
    """English to the pivot language, word by word. Unknown words stay."""
    table = load_lexicon()["en_to_pivot"]
    return "".join(
        _map_word(part, table) if part.isalpha() else part
        for part in _WORD_OR_OTHER.findall(text)
    )


def back_translate(text: str) -> str:
    """Pivot language to canonical English, word by word. Unknown words stay."""
    table = load_lexicon()["pivot_to_en"]
    return "".join(
        _map_word(part, table) if part.isalpha() else part
        for part in _WORD_OR_OTHER.findall(text)
    )


def roundtrip_translate(text: str) -> str:
    """Deterministic EN -> pivot -> EN. No model. No network."""
    return back_translate(forward_translate(text))


def roundtrip_tokens(tokens: list[str]) -> list[str]:
    """Apply the dictionary round-trip to a token list. Result tokens are lowercase."""
    lex = load_lexicon()
    out: list[str] = []
    for tok in tokens:
        key = tok.lower()
        pivot = lex["en_to_pivot"].get(key)
        if pivot is None:
            out.append(key)
            continue
        out.append(lex["pivot_to_en"].get(pivot, key))
    return out


def cwra_prompt(task_desc: str, pivot: str = "Spanish", min_words: int = 400) -> str:
    """Generation-time CWRA: tell the model to write in the pivot language.

    The model can write Spanish at length. A later deterministic or unwatermarked
    back-translate produces English that the English-key detector does not see.
    """
    return (
        f"Write {task_desc}. Write the full text in {pivot}, not in English. "
        f"The output must be more than {min_words} words. "
        f"Shorter output is not useful and is rejected. Return only the {pivot} text."
    )


def roundtrip_bleach(
    text: str,
    outbound=None,
    inbound=None,
    gate: MeaningGate | None = None,
    language: str = "en",
) -> BleachResult:
    """Bleach existing text by a round-trip through a pivot language (FR-29).

    Default: the bundled dictionary. Optional outbound and inbound callables are a
    real MT pair or a local unwatermarked model. They go through the gateway so a
    carrier does not reach a model (SR-06, SR-09). The inbound callable must not be
    the marking model.
    """
    gate = gate or MeaningGate()
    cleaned = normalize_carriers(text)

    if outbound is not None and inbound is not None:
        from ..runtime.model import ModelGateway

        mid = ModelGateway(outbound).call(cleaned)
        candidate = ModelGateway(inbound).call(mid)
    else:
        candidate = roundtrip_translate(cleaned)

    score = gate.similarity(cleaned, candidate, language=language)
    if not gate.passes(score, language=language):
        return BleachResult(
            cleaned, 4, False, score,
            f"rejected: meaning score {score:.3f} below the gate",
        )
    return BleachResult(candidate, 4, True, score, "round-trip translation bleach")


def measure_roundtrip_removes_watermark(
    samples: int = 6, length: int = 240, delta: float = 2.0, seed: int = 1
) -> dict:
    """Plant a green-list mark on English content words, then apply the dictionary trip.

    Uses the content vocabulary so the collapse has room to change tokens. Returns
    mean z before, mean z after, the changed-token fraction, and the meaning score
    of one joined sample.
    """
    from ..detect.keyed.greenlist import GreenListScheme
    from ..harness.generators import watermarked_sequence

    vocab = content_vocab()
    scheme = GreenListScheme(key="fr29-key", vocab=vocab, gamma=0.25)
    before: list[float] = []
    after: list[float] = []
    changed = 0
    total = 0
    sample_before = sample_after = ""
    for i in range(samples):
        tokens = watermarked_sequence(scheme, length, seed=seed + i, delta=delta)
        bleached = roundtrip_tokens(tokens)
        before.append(scheme.z_score(tokens))
        after.append(scheme.z_score(bleached))
        changed += sum(a != b for a, b in zip(tokens, bleached))
        total += len(tokens)
        if i == 0:
            sample_before = " ".join(tokens)
            sample_after = " ".join(bleached)
    gate = MeaningGate()
    return {
        "z_before": sum(before) / len(before),
        "z_after": sum(after) / len(after),
        "changed_fraction": changed / max(1, total),
        "meaning_score": gate.similarity(sample_before, sample_after),
        "samples": samples,
        "length": length,
        "vocab": len(vocab),
    }
