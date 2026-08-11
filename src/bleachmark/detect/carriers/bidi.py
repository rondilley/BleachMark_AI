"""Bidirectional override carriers, Trojan Source (FR-11, research 7.6)."""

from __future__ import annotations

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity

_LRO = 0x202D
_RLO = 0x202E
_EMBED_ISOLATE = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))


class _Bidi:
    name = "bidi"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        for i, ch in enumerate(text):
            cp = ord(ch)
            # overrides are the Trojan Source signal; marks (LRM/RLM) are exonerated
            if cp in (_LRO, _RLO):
                hits.append(decoded.location_of(i))
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
