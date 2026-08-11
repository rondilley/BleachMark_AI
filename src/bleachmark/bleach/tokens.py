"""Middle-strength bleach: token-level edits (FR-25, research 4).

Light, meaning-preserving surface edits dilute a token-level statistical signal.
This is weaker than a semantic paraphrase and pays less meaning cost. The research
is clear that token edits alone are a poor bleach against a strong watermark, so
this strength is a light dilution, not a guarantee.

The typographic characters are built with chr() so this source holds no literal
non-ASCII symbol.
"""

from __future__ import annotations

import re

_EM_DASH = chr(0x2014)
_EN_DASH = chr(0x2013)
_LSQUO = chr(0x2018)
_RSQUO = chr(0x2019)
_LDQUO = chr(0x201C)
_RDQUO = chr(0x201D)
_ELLIPSIS = chr(0x2026)

_SUBS = [
    (re.compile(_EM_DASH), " - "),
    (re.compile(_EN_DASH), "-"),
    (re.compile(f"[{_LSQUO}{_RSQUO}]"), "'"),
    (re.compile(f"[{_LDQUO}{_RDQUO}]"), '"'),
    (re.compile(_ELLIPSIS), "..."),
    (re.compile(r"[ \t]{2,}"), " "),
]

_CONTRACTIONS = {
    "do not": "don't",
    "does not": "doesn't",
    "is not": "isn't",
    "it is": "it's",
    "cannot": "can't",
    "will not": "won't",
}


def token_edits(text: str) -> str:
    out = text
    for pat, rep in _SUBS:
        out = pat.sub(rep, out)
    for a, b in _CONTRACTIONS.items():
        out = re.sub(rf"\b{re.escape(a)}\b", b, out)
    return out
