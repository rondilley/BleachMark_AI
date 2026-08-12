"""Decode input text to Unicode codepoints with byte offsets (FR-02, FR-03).

Carrier detection works at the codepoint layer, so every detector needs a lossless
mapping from a character index back to its byte offset and line number. The map is
computed on demand: a scan of clean text asks for no locations, so building an
N-length table up front is pure waste. ASCII text has byte offset equal to the
character index, the common fast path.
"""

from __future__ import annotations

import bisect


class DecodedText:
    __slots__ = ("text", "_ascii", "_line_starts", "_byte_prefix")

    def __init__(self, text: str):
        self.text = text
        self._ascii = text.isascii()
        self._byte_prefix: list[int] | None = None
        # character index at which each line begins, for O(log n) line lookup
        starts = [0]
        find = text.find
        i = find("\n")
        while i != -1:
            starts.append(i + 1)
            i = find("\n", i + 1)
        self._line_starts = starts

    def _byte_offset(self, index: int) -> int:
        if self._ascii:
            return index
        # non-ASCII: build a cumulative byte-offset table once, then O(1) per lookup.
        # Without this, a hostile input full of carrier characters would force an
        # O(n^2) rescan (one O(index) slice-encode per hit).
        if self._byte_prefix is None:
            pref = [0] * (len(self.text) + 1)
            off = 0
            for i, ch in enumerate(self.text):
                cp = ord(ch)
                off += 1 if cp < 0x80 else 2 if cp < 0x800 else 3 if cp < 0x10000 else 4
                pref[i + 1] = off
            self._byte_prefix = pref
        return self._byte_prefix[index]

    def line_of(self, index: int) -> int:
        """1-based line number of the character at index."""
        return bisect.bisect_right(self._line_starts, index)

    def location_of(self, index: int, length: int = 1):
        from .model import Location

        start = self._byte_offset(index)
        end_char = min(index + length, len(self.text))
        end = self._byte_offset(end_char)
        return Location(start=start, end=end, line=self.line_of(index))


def decode(text: str) -> DecodedText:
    """Wrap the text with a lazy codepoint-to-byte-offset map."""
    return DecodedText(text)


def word_count(text: str) -> int:
    """Approximate word count for the length-aware confidence (FR-49)."""
    return len(text.split())
