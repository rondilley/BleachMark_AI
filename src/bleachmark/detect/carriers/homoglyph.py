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

# UTS 39 allowed multi-script combinations: a token that mixes only these scripts
# is legitimate, not a homoglyph attack. Japanese mixes Han, Hiragana, Katakana;
# Korean mixes Han and Hangul; Latin rides along in both.
_ALLOWED_COMBOS = (
    frozenset({"CJK", "HIRAGANA", "KATAKANA", "LATIN"}),
    frozenset({"CJK", "HANGUL", "LATIN"}),
)


def _is_confusable_mix(scripts: set[str]) -> bool:
    """True when a token mixes scripts in a way that is NOT a legitimate combo.

    The confusable attack mixes visually identical alphabets (Latin, Cyrillic,
    Greek). A Japanese or Korean token that mixes Han with a syllabary is legitimate
    and must not fire (UTS 39 highly-restrictive profile).
    """
    if len(scripts) < 2:
        return False
    return not any(scripts <= combo for combo in _ALLOWED_COMBOS)


class _Homoglyph:
    name = "homoglyph"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        for m in _WORD.finditer(text):
            word = m.group(0)
            # an all-ASCII word is single-script (Latin); only a word with a non-ASCII
            # character can mix scripts, so skip the common case without a per-char scan
            if word.isascii():
                continue
            scripts = set()
            for ch in word:
                s = context.script_of(ch)
                if s is not None:
                    scripts.add(s)
            # a word that mixes two confusable alphabets is tampering; a legitimate
            # Japanese/Korean multi-script token is not
            if _is_confusable_mix(scripts):
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
