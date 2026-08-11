"""Variation-selector carriers (FR-07, research 7.3)."""

from __future__ import annotations

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity
from . import context


def _is_selector(cp: int) -> bool:
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


class _Selectors:
    name = "variation_selectors"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        i = 0
        while i < len(text):
            if not _is_selector(ord(text[i])):
                i += 1
                continue
            # measure the run length starting here
            run = i
            while run < len(text) and _is_selector(ord(text[run])):
                run += 1
            run_len = run - i
            # a single selector on a valid base is legitimate; a run is smuggling
            if run_len == 1 and context.exonerate_selector(text, i):
                i = run
                continue
            for j in range(i, run):
                hits.append(decoded.location_of(j))
            i = run
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
