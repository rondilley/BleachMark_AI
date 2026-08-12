"""Variation-selector carriers (FR-07, research 7.3)."""

from __future__ import annotations

import re

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity
from . import context

# variation selectors (U+FE00..FE0F) and the supplement (U+E0100..E01EF); a run of
# consecutive selectors is the carrier. Built from chr() so the source is ASCII-only.
_SELECTOR_RUN = re.compile(
    "[" + chr(0xFE00) + "-" + chr(0xFE0F) + chr(0xE0100) + "-" + chr(0xE01EF) + "]+"
)


class _Selectors:
    name = "variation_selectors"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        for m in _SELECTOR_RUN.finditer(text):
            run_len = m.end() - m.start()
            # a single selector on a valid base is legitimate; a run is smuggling
            if run_len == 1 and context.exonerate_selector(text, m.start()):
                continue
            for j in range(m.start(), m.end()):
                hits.append(decoded.location_of(j))
        if not hits:
            return []
        return [
            Finding(
                kind="variation_selectors",
                detector=self.name,
                severity=Severity.HIGH,
                summary=f"{len(hits)} detached or long variation-selector run(s)",
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.97,
                false_positive_rate=0.0,
                notes=["One byte per selector, hidden on one glyph (research 7.3)."],
            )
        ]


detector = _Selectors()
