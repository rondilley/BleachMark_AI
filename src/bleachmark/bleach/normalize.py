"""Lowest-strength bleach: deterministic carrier removal (FR-24, research 7).

The normalize mirrors the carrier detectors' exoneration, so a second scan of the
output finds no carrier (TC-07). It does not change what a human reads.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

from ..detect.carriers import context

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "codepoints")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _confusables() -> dict[int, str]:
    with open(os.path.join(_DATA, "confusables.json"), encoding="utf-8") as fh:
        raw = json.load(fh)["map"]
    return {int(k): v for k, v in raw.items()}


_CONFUSABLE_MAP = _confusables()
_WORD = re.compile(r"\w+", re.UNICODE)


def _is_selector(cp: int) -> bool:
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


def _strip_carriers(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        cp = ord(ch)
        # tag-block characters, unless a subdivision flag
        if 0xE0000 <= cp <= 0xE007F:
            if context.in_subdivision_flag(text, i):
                out.append(ch)
            i += 1
            continue
        # bidi overrides
        if cp in (0x202D, 0x202E):
            i += 1
            continue
        # zero-width and format characters, unless exonerated
        if unicodedata.category(ch) == "Cf":
            if context.exonerate_zero_width(text, i):
                out.append(ch)
            i += 1
            continue
        # variation-selector runs: drop a detached or long run, keep a single on emoji
        if _is_selector(cp):
            run = i
            while run < n and _is_selector(ord(text[run])):
                run += 1
            if run - i == 1 and context.exonerate_selector(text, i):
                out.append(ch)
            i = run
            continue
        # substituted Unicode space characters become a normal space
        if cp != 0x20 and cp != 0x09 and (0x2000 <= cp <= 0x200A or cp in (0xA0, 0x2007, 0x202F)):
            if context.exonerate_typographic_space(text, i):
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _fold_homoglyphs(text: str) -> str:
    """Map a confusable to Latin inside a mixed-script word only."""
    def repl(m: re.Match) -> str:
        word = m.group(0)
        scripts = {context.script_of(c) for c in word if context.script_of(c)}
        if len(scripts) < 2:
            return word
        return "".join(_CONFUSABLE_MAP.get(ord(c), c) for c in word)

    return _WORD.sub(repl, text)


def normalize_carriers(text: str) -> str:
    """Remove or normalize every post-hoc carrier deterministically."""
    text = _HTML_COMMENT.sub("", text)
    text = _strip_carriers(text)
    text = _fold_homoglyphs(text)
    return text
