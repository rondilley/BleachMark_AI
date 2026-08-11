"""Whitespace and typographic carriers (FR-09, research 7.5)."""

from __future__ import annotations

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity
from . import context

_NORMAL_SPACE = 0x20
_TAB = 0x09


def _is_space_like(cp: int) -> bool:
    return (
        cp in (0xA0, 0x2007, 0x202F, 0xFEFF)
        or 0x2000 <= cp <= 0x200A
    )


class _Whitespace:
    name = "whitespace"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        notes: list[str] = []

        # trailing whitespace at end of a line (structured pattern is a signal)
        trailing_lines = 0
        for line in text.split("\n"):
            if line and line[-1] in (" ", "\t"):
                trailing_lines += 1
        if trailing_lines >= 2:
            notes.append(f"{trailing_lines} line(s) with trailing whitespace (SNOW-style)")

        # non-U+0020 space characters substituted for a normal space
        for i, ch in enumerate(text):
            cp = ord(ch)
            if cp in (_NORMAL_SPACE, _TAB):
                continue
            if _is_space_like(cp):
                if context.exonerate_typographic_space(text, i):
                    continue
                hits.append(decoded.location_of(i))

        if not hits and not notes:
            return []
        summary = "whitespace or typographic carrier"
        if hits:
            summary = f"{len(hits)} substituted space character(s)"
        return [
            Finding(
                kind="whitespace",
                detector=self.name,
                severity=Severity.MEDIUM if hits else Severity.LOW,
                summary=summary,
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.7,
                false_positive_rate=0.05,
                notes=notes or ["Substituted Unicode space (research 7.5)."],
            )
        ]


detector = _Whitespace()
