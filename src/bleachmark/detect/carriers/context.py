"""Exoneration by script, base character, and position (FR-12, research 7.7).

The high-signal cases (tag characters in prose, detached selector runs,
mixed-script single tokens, zero-width between Latin letters) are flagged. The
overlapping legitimate cases (ZWJ in emoji, ZWNJ in Indic or Arabic, VS16 on an
emoji, a leading BOM, LRM in RTL text, NBSP in typography) are cleared.

The text-global checks (does the text contain RTL script, is the typographic-space
density normal) are computed once per document by the caller, not once per hit, so a
hostile input full of carrier characters cannot force an O(n^2) rescan.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

ZWNJ = 0x200C
ZWJ = 0x200D
BOM = 0xFEFF
VS16 = 0xFE0F
VS15 = 0xFE0E
LRM = 0x200E
RLM = 0x200F
ALM = 0x061C
SUBDIVISION_FLAG_BASE = 0x1F3F4
CANCEL_TAG = 0xE007F

# shared by the carrier detectors that scan only the non-ASCII positions
NON_ASCII = re.compile(r"[^\x00-\x7f]")

# Hebrew, Arabic, and the Arabic presentation forms; used to clear directional marks
_RTL = re.compile(
    "[" + chr(0x0590) + "-" + chr(0x05FF) + chr(0x0600) + "-" + chr(0x06FF)
    + chr(0x0750) + "-" + chr(0x077F) + chr(0xFB50) + "-" + chr(0xFDFF)
    + chr(0xFE70) + "-" + chr(0xFEFF) + "]"
)

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


@lru_cache(maxsize=4096)
def script_of(ch: str) -> str | None:
    """Approximate the Unicode script from the character name prefix.

    ASCII takes a fast path (letters are Latin, the rest have no script), so the
    common case never pays for unicodedata.name. The result is cached per character.
    """
    if ord(ch) < 0x80:
        return "LATIN" if ch.isalpha() else None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for prefix in _SCRIPT_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def contains_rtl(text: str) -> bool:
    """True when the text contains any Hebrew or Arabic character (one C-speed scan)."""
    return bool(_RTL.search(text))


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


def exonerate_zero_width(text: str, index: int, has_rtl: bool | None = None) -> bool:
    """Return True when the zero-width character at index is legitimate.

    has_rtl is the document-global "text contains RTL script" flag; pass it in from a
    loop so a run of directional marks is not an O(n^2) rescan.
    """
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
    if cp in (LRM, RLM, ALM):
        # a directional mark is required in real bidirectional text; the bidi detector
        # owns the override characters (research 7.6)
        return contains_rtl(text) if has_rtl is None else has_rtl
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


def typographic_density_exonerates(text: str) -> bool:
    """True when the substituted-space density is normal typography, not a signal.

    This is a document-global decision (independent of any single position), so the
    caller computes it once for the whole text.
    """
    count = sum(1 for ch in text if 0x2000 <= ord(ch) <= 0x200A or ord(ch) in (0xA0, 0x202F, 0x2007))
    return count <= max(1, len(text.split()) // 20)


def subdivision_flag_indices(text: str) -> set[int]:
    """Indices covered by a valid subdivision flag (base U+1F3F4 ... cancel U+E007F).

    Computed once per text so the tags detector does not rescan for every tag char.
    """
    covered: set[int] = set()
    base = chr(SUBDIVISION_FLAG_BASE)
    cancel = chr(CANCEL_TAG)
    start = 0
    while True:
        b = text.find(base, start)
        if b == -1:
            break
        f = text.find(cancel, b)
        if f == -1:
            break
        if all(0xE0000 <= ord(c) <= 0xE007F for c in text[b + 1 : f]):
            # cover the tag letters and the cancel tag itself (inclusive of f)
            covered.update(range(b + 1, f + 1))
        start = b + 1
    return covered
