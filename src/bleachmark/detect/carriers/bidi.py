"""Bidirectional override carriers, Trojan Source (FR-11, research 7.6)."""

from __future__ import annotations

import re

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity

_LRO = 0x202D
_RLO = 0x202E
# overrides are the Trojan Source signal; the marks (LRM/RLM) are exonerated and
# handled by the zero-width detector's context rules. Build the class from chr() so
# the source holds no literal invisible character.
_OVERRIDE = re.compile("[" + chr(_LRO) + chr(_RLO) + "]")


class _Bidi:
    name = "bidi"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = [decoded.location_of(m.start()) for m in _OVERRIDE.finditer(text)]
        if not hits:
            return []
        return [
            Finding(
                kind="bidi_override",
                detector=self.name,
                severity=Severity.HIGH,
                summary=f"{len(hits)} bidirectional override character(s): reordering risk",
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.95,
                false_positive_rate=0.0,
                notes=["Trojan Source, CVE-2021-42574 (research 7.6)."],
            )
        ]


detector = _Bidi()
