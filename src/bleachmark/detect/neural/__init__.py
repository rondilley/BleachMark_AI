"""Neural detectors (FR-41).

A neural detector wraps a model-scoring callable and returns a calibrated Finding.
The harness measures how much a neural detector adds above the statistical scorer.
A neural detector is a machine-generation classifier, so it inherits the same
base-rate and confound limits; it does not defeat an undetectable watermark.
"""

from __future__ import annotations

from typing import Callable

from ...decode import DecodedText
from ...model import Finding, Posture, Severity


class NeuralDetector:
    def __init__(
        self,
        score_fn: Callable[[str], float],
        model_name: str,
        false_positive_rate: float = 0.01,
        name: str = "neural",
    ):
        self.score_fn = score_fn
        self.model_name = model_name
        self.false_positive_rate = false_positive_rate
        self.name = name

    def detect(self, decoded: DecodedText) -> list[Finding]:
        s = float(self.score_fn(decoded.text))
        return [
            Finding(
                kind="neural",
                detector=self.name,
                severity=Severity.INFO,
                summary=f"neural machine-generation score {s:.3f} from {self.model_name}",
                posture=Posture.KEYLESS,
                score=s,
                false_positive_rate=self.false_positive_rate,
                confidence=0.5,
                notes=[
                    "A neural detector is a classifier, not watermark identification.",
                    f"model={self.model_name}",
                ],
            )
        ]
