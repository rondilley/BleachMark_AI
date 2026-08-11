"""Detector interface and registry (AR-03, AR-04).

Every detector returns Findings through one interface, so a new detector plugs in
with no change to the report code, and every result carries a calibrated score and
a stated false-positive rate where one applies.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

from ..decode import DecodedText
from ..model import Finding


class Detector(Protocol):
    name: str

    def detect(self, decoded: DecodedText) -> list[Finding]:
        """Return findings for the decoded text."""
        ...


_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "codepoints")


def load_codepoints(filename: str = "carriers.json") -> dict:
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as fh:
        return json.load(fh)


_REGISTRY: dict[str, Detector] = {}


def register(detector: Detector) -> Detector:
    _REGISTRY[detector.name] = detector
    return detector


def registry() -> dict[str, Detector]:
    return dict(_REGISTRY)


def run_detectors(
    decoded: DecodedText, detectors: list[Detector] | None = None
) -> list[Finding]:
    """Run each detector. A failure in one does not stop the others."""
    findings: list[Finding] = []
    for det in detectors if detectors is not None else _REGISTRY.values():
        try:
            findings.extend(det.detect(decoded))
        except Exception as exc:  # a detector failure is isolated
            from ..model import Finding as _F, Severity, Posture

            findings.append(
                _F(
                    kind="detector_error",
                    detector=getattr(det, "name", "unknown"),
                    severity=Severity.INFO,
                    summary=f"detector failed: {exc}",
                    posture=Posture.KEYLESS,
                )
            )
    return findings


def default_carrier_detectors() -> list[Detector]:
    """The deterministic carrier detectors that run with no model (Slice 1)."""
    from .carriers import zerowidth, tags, selectors, homoglyph, whitespace, markdown, bidi

    return [
        zerowidth.detector,
        tags.detector,
        selectors.detector,
        homoglyph.detector,
        whitespace.detector,
        markdown.detector,
        bidi.detector,
    ]
