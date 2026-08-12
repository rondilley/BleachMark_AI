"""Shared data model for BleachMark.

These dataclasses are the one shared vocabulary between the detection subsystem,
the bleach subsystem, and the report layer (ARCHITECTURE section 2 and 4). Every
detector returns Finding objects and a Score through the same interface so the
report never sees a bare, uncalibrated verdict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.0"  # DR-02: the JSON report schema carries a version.


class Posture(str, Enum):
    """How strong a result is (FR-22). Keyless is the weakest, keyed the cleanest."""

    KEYLESS = "keyless"
    COMPARISON = "comparison"
    ACTIVE = "active"
    KEYED = "keyed"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Location:
    """Where a finding sits in the input (FR-03)."""

    start: int  # byte offset
    end: int
    line: int


@dataclass
class Finding:
    """One detected signal.

    A carrier finding is deterministic and high confidence. A statistical finding
    carries a calibrated score plus a stated false-positive rate (FR-14).
    """

    kind: str  # e.g. "zero_width", "tags_block", "homoglyph", "greenlist_ztest"
    detector: str
    severity: Severity
    summary: str
    locations: list[Location] = field(default_factory=list)
    posture: Posture = Posture.KEYLESS
    score: float | None = None
    false_positive_rate: float | None = None
    confidence: float | None = None
    # SR-07: a decoded payload is stored redacted, never in cleartext by default.
    payload_len: int | None = None
    payload_sha256: str | None = None
    payload_cleartext: str | None = None  # only populated when the caller opts in
    notes: list[str] = field(default_factory=list)

    def to_dict(self, show_payload: bool = False) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["posture"] = self.posture.value
        d["locations"] = [asdict(loc) for loc in self.locations]
        if not show_payload:
            d.pop("payload_cleartext", None)
        return d


@dataclass
class Report:
    """The canonical result (FR-30). The Markdown view renders from this model."""

    target: str
    text_length_words: int
    findings: list[Finding] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    # A bleach report also records before and after detection (FR-33).
    before_score: float | None = None
    after_score: float | None = None

    def high_confidence_carriers(self) -> list[Finding]:
        """Carriers that drive the CLI exit code (FR-36). MGT scores never do."""
        return [
            f
            for f in self.findings
            if f.posture == Posture.KEYLESS
            and f.severity in (Severity.HIGH, Severity.MEDIUM)
            and f.kind
            not in ("comparison", "attribution")
        ]

    def to_dict(self, show_payload: bool = False) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target": self.target,
            "text_length_words": self.text_length_words,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "scores": self.scores,
            "findings": [f.to_dict(show_payload) for f in self.findings],
        }


def redact_payload(payload: bytes) -> tuple[int, str]:
    """Return (length, sha256) for a decoded payload (SR-07, DR-03)."""
    return len(payload), hashlib.sha256(payload).hexdigest()
