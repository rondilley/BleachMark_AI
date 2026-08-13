"""Bleach subsystem: a strength ladder with a meaning gate (FR-23, ARCHITECTURE 6).

The lowest strength removes a post-hoc carrier with no model and no meaning cost.
The middle strength makes token-level edits. The highest strength makes a semantic
paraphrase through the model gateway. Every model-bound strength runs the carrier
normalize first (SR-06), enforced at the gateway (SR-09).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Strength(IntEnum):
    NORMALIZE = 1  # deterministic carrier removal, no model
    TOKEN = 2  # token-level edits, no model
    PARAPHRASE = 3  # semantic paraphrase, needs a model


@dataclass
class BleachResult:
    text: str
    strength: int
    accepted: bool
    meaning_score: float | None
    message: str


def bleach(
    text: str,
    strength: int = Strength.NORMALIZE,
    model=None,
    gate=None,
    language: str = "en",
) -> BleachResult:
    """Bleach text at the selected strength behind the meaning gate (FR-27, FR-28)."""
    from .normalize import normalize_carriers
    from .tokens import token_edits
    from .gate import MeaningGate

    gate = gate or MeaningGate()

    # The deterministic carrier normalize always runs first (SR-06).
    cleaned = normalize_carriers(text)

    if strength <= Strength.NORMALIZE:
        # a carrier normalize does not change what a human reads, so it always passes
        return BleachResult(cleaned, int(Strength.NORMALIZE), True, 1.0, "normalized carriers")

    if strength == Strength.TOKEN:
        candidate = token_edits(cleaned)
    else:  # PARAPHRASE
        from .neural import paraphrase_bleach

        candidate = paraphrase_bleach(cleaned, model=model)

    score = gate.similarity(cleaned, candidate, language=language)
    if not gate.passes(score, language=language):
        # reject a bleach that does not keep the meaning; return the input (FR-28)
        return BleachResult(
            cleaned, int(strength), False, score,
            f"rejected: meaning score {score:.3f} below the gate",
        )
    return BleachResult(candidate, int(strength), True, score, "bleached and meaning kept")
