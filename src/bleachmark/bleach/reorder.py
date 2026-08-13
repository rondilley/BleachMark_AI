"""The reverse-order bleach for prose (FR-26, FR-29, research 3, 7).

The idea: a context-keyed watermark seeds the green set for each token from the token
that comes before it IN GENERATION ORDER. So the tool tells the model to write the prose
in reverse sentence order (the last sentence first). The model still marks its output, but
it marks each token against its reverse-order neighbor. Then a deterministic step puts the
sentences back in the forward order.

After the reorder each token sits next to its forward neighbor, but its green bias was
keyed on the reverse neighbor. A forward-key detector checks the forward neighbor, so the
green bias no longer lines up, and the green-list z-score drops. The text is the same
sentences in the correct order, so the meaning is kept if the model wrote coherent reverse
prose. A fidelity gate confirms the meaning.

The degradation is proven on the synthetic side with the real context-keyed green-list
scheme (validate on the synthetic side first). On a real model there is no key, so the
degradation cannot be measured keyless. The deterministic reorder and the fidelity gate do
run on real prose, so the bleach is deployable; only the private measurement waits for a
key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..detect.keyed.greenlist import GreenListScheme
from ..harness.generators import watermarked_sequence
from .gate import MeaningGate

_SENTENCE = re.compile(r".*?[.!?]+(?:[\"')\]]+)?(?:\s+|$)|.+$", re.DOTALL)


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping the terminators."""
    return [m.group(0).strip() for m in _SENTENCE.finditer(text) if m.group(0).strip()]


def reorder_reverse(text: str) -> str:
    """The deterministic bleach: put the sentences in reverse order.

    Applying it twice returns the original text, so the reorder is lossless. On a
    reverse-written draft it restores the forward reading order.
    """
    return " ".join(reversed(split_sentences(text)))


def reverse_prompt(task_desc: str, min_words: int = 400) -> str:
    """Tell the model to write the prose with the sentences in reverse order."""
    return (
        f"Write {task_desc}. The output must be more than {min_words} words. "
        "Shorter output is not useful and is rejected. "
        "Write the sentences in REVERSE order: put the last sentence first, the "
        "second-to-last sentence second, and so on, so the first sentence comes last. "
        "Each sentence must read correctly on its own. Return only the prose."
    )


@dataclass
class FidelityResult:
    score: float
    ok: bool


def fidelity(reference_forward: str, bleached_forward: str, gate: MeaningGate | None = None,
             language: str = "en") -> FidelityResult:
    """Measure that the bleached forward prose keeps the meaning of a forward reference.

    The score is the meaning-gate similarity between a normal forward draft and the
    reverse-written draft after the reorder. A high score means the bleach kept the
    content. It is a proxy for coherence, not a full check.
    """
    gate = gate or MeaningGate(threshold=0.5)
    score = gate.similarity(reference_forward, bleached_forward, language=language)
    return FidelityResult(score=score, ok=gate.passes(score, language=language))


# --- ground-truth degradation with the real context-keyed green-list scheme ----


def reverse_bleached_sequence(scheme: GreenListScheme, length: int, seed: int, delta: float = 2.0) -> list[str]:
    """The forward output of the reverse-order bleach, at the token level.

    The model marks a sequence in its generation order (the same context-keyed scheme).
    The deterministic reorder reverses it to the forward reading order. So the forward
    output is the reverse of a normally-marked sequence.
    """
    generation_order = watermarked_sequence(scheme, length, seed, delta=delta)
    return list(reversed(generation_order))


def forward_z(scheme: GreenListScheme, tokens: list[str]) -> float:
    """The forward-key green-list z-score of a token sequence."""
    return scheme.z_score(tokens)
