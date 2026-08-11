"""Exoneration by script, base character, and position (FR-12, research 7.7).

The high-signal cases (tag characters in prose, detached selector runs,
mixed-script single tokens, zero-width between Latin letters) are flagged. The
overlapping legitimate cases (ZWJ in emoji, ZWNJ in Indic or Arabic, VS16 on an
emoji, a leading BOM, LRM in RTL text, NBSP in typography) are cleared.
"""

from __future__ import annotations

import unicodedata

ZWSP = 0x200B
ZWNJ = 0x200C
ZWJ = 0x200D
WJ = 0x2060
BOM = 0xFEFF
VS16 = 0xFE0F
VS15 = 0xFE0E
LRM = 0x200E
RLM = 0x200F
ALM = 0x061C
SUBDIVISION_FLAG_BASE = 0x1F3F4
CANCEL_TAG = 0xE007F

_SCRIPT_PREFIXES = (
    "LATIN",
    "CYRILLIC",
    "GREEK",
    "ARABIC",
    "HEBREW",
    "HANGUL",
    "CJK",
    "HIRAGANA",
    "KATAKANA",
    "DEVANAGARI",
    "BENGALI",
    "TAMIL",
    "THAI",
    "ARMENIAN",
    "GEORGIAN",
)


def script_of(ch: str) -> str | None:
    """Approximate the Unicode script from the character name prefix."""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for prefix in _SCRIPT_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def is_complex_shaping_script(ch: str) -> bool:
    """Scripts where ZWNJ or ZWJ are orthographically required."""
    return script_of(ch) in ("ARABIC", "DEVANAGARI", "BENGALI", "TAMIL")


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x1F1E6 <= cp <= 0x1F1FF
        or cp in (0x2764, 0x2B50, 0x2705)
    )


def exonerate_zero_width(text: str, index: int) -> bool:
    """Return True when the zero-width character at index is legitimate."""
    cp = ord(text[index])
    prev = text[index - 1] if index > 0 else ""
    nxt = text[index + 1] if index + 1 < len(text) else ""
    if cp == BOM and index == 0:
        return True  # byte-order mark at file start
    if cp in (ZWJ, ZWNJ):
        # emoji ZWJ sequence, or required in a complex-shaping script
        if is_emoji(prev) or is_emoji(nxt):
            return True
        if is_complex_shaping_script(prev) or is_complex_shaping_script(nxt):
            return True
    return False


def exonerate_selector(text: str, index: int) -> bool:
    """A variation selector on a valid emoji or CJK base is legitimate."""
    cp = ord(text[index])
    prev = text[index - 1] if index > 0 else ""
    if cp in (VS16, VS15) and is_emoji(prev):
        return True
    # A CJK ideograph base with a single selector is an Ideographic Variation Seq.
    if 0xE0100 <= cp <= 0xE01EF and script_of(prev) == "CJK":
        return True
    return False


def exonerate_bidi_mark(text: str, index: int) -> bool:
    """LRM, RLM, ALM are required in real bidirectional text."""
    cp = ord(text[index])
    if cp in (LRM, RLM, ALM):
        for ch in text:
            if script_of(ch) in ("ARABIC", "HEBREW"):
                return True
    return False


def exonerate_typographic_space(text: str, index: int) -> bool:
    """A no-break or thin space in ordinary typography is not a hidden bit alone."""
    # Low specificity: only an unusual density is a signal. A single one is normal.
    count = sum(1 for ch in text if 0x2000 <= ord(ch) <= 0x200A or ord(ch) in (0xA0, 0x202F, 0x2007))
    return count <= max(1, len(text.split()) // 20)


def in_subdivision_flag(text: str, index: int) -> bool:
    """A tag run framed by U+1F3F4 ... U+E007F is a subdivision flag, not smuggling."""
    # look back for the base and forward for the cancel tag
    back = text.rfind(chr(SUBDIVISION_FLAG_BASE), 0, index)
    if back == -1:
        return False
    fwd = text.find(chr(CANCEL_TAG), index)
    if fwd == -1:
        return False
    # every character between base and cancel must be a tag character
    return all(0xE0000 <= ord(c) <= 0xE007F for c in text[back + 1 : fwd])
