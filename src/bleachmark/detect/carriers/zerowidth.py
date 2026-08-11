"""Zero-width and format-character carriers (FR-05, research 7.1)."""

from __future__ import annotations

import unicodedata

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity
from . import context


class _ZeroWidth:
    name = "zero_width"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        for i, ch in enumerate(text):
            if unicodedata.category(ch) != "Cf":
                continue
            cp = ord(ch)
            # the Tags block is Cf too, but the tags detector owns it
            if 0xE0000 <= cp <= 0xE007F:
                continue
            if context.exonerate_zero_width(text, i):
                continue
            hits.append(decoded.location_of(i))
        if not hits:
            return []
        return [
            Finding(
                kind="zero_width",
                detector=self.name,
                severity=Severity.HIGH,
                summary=f"{len(hits)} zero-width or format character(s) in the text",
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.99,
                false_positive_rate=0.0,
                notes=["Cf-category characters after exoneration (research 7.1)."],
            )
        ]


detector = _ZeroWidth()
