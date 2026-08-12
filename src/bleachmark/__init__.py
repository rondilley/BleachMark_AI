"""BleachMark: detect and bleach watermarks and carriers in LLM text.

Public API. The default posture is keyless and model-equipped. The core detect and
carrier-bleach paths need no model and make no network call (NFR-02).
"""

from __future__ import annotations

from .decode import decode, word_count
from .detect import default_carrier_detectors, run_detectors
from .model import Finding, Posture, Report, Severity

__version__ = "0.1.0"

__all__ = [
    "detect",
    "detect_carriers",
    "bleach",
    "Finding",
    "Report",
    "Posture",
    "Severity",
    "__version__",
]


def bleach(text: str, strength: int = 1, model=None, gate=None, language: str = "en"):
    """Bleach text at the selected strength behind the meaning gate."""
    from .bleach import bleach as _bleach

    return _bleach(text, strength=strength, model=model, gate=gate, language=language)


def detect_carriers(text: str, target: str = "<text>") -> Report:
    """Run the deterministic carrier detectors only (no model, no network)."""
    decoded = decode(text)
    findings = run_detectors(decoded, default_carrier_detectors())
    return Report(
        target=target,
        text_length_words=word_count(text),
        findings=findings,
    )


def detect(text: str, target: str = "<text>") -> Report:
    """Keyless carrier detection over the input text.

    The input is assumed to be model output; the tool looks for hidden watermark and
    carrier signals in it, not for whether the text is machine-written.
    """
    return detect_carriers(text, target)
