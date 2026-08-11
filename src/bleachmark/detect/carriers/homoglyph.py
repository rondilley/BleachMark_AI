"""Homoglyph and mixed-script carriers (FR-08, research 7.4).

The mixed-script test runs per word, not per document, so legitimately multilingual
text is not flagged. A single token that mixes scripts (Latin plus Cyrillic) is the
high-signal indicator (Unicode UTS 39).
"""

from __future__ import annotations

import re

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity
from . import context

_WORD = re.compile(r"\w+", re.UNICODE)


class _Homoglyph:
    name = "homoglyph"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        for m in _WORD.finditer(text):
            word = m.group(0)
            scripts = set()
            for ch in word:
                s = context.script_of(ch)
                if s is not None:
                    scripts.add(s)
            # a single word that mixes two real scripts is confusable tampering
            if len(scripts) >= 2:
                hits.append(decoded.location_of(m.start(), len(word)))
        if not hits:
            return []
        return [
            Finding(
                kind="homoglyph",
                detector=self.name,
                severity=Severity.HIGH,
                summary=f"{len(hits)} mixed-script token(s): possible homoglyph substitution",
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.9,
                false_positive_rate=0.01,
                notes=["Per-word mixed-script test (UTS 39, research 7.4)."],
            )
        ]


detector = _Homoglyph()
