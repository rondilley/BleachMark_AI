"""Decode input text to Unicode codepoints with byte offsets (FR-02, FR-03).

Carrier detection works at the codepoint layer, so every detector needs a lossless
mapping from a character index back to its byte offset and line number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecodedText:
    text: str
    # byte_offsets[i] is the UTF-8 byte offset of character i.
    byte_offsets: list[int]
    # lines[i] is the 1-based line number of character i.
    lines: list[int]

    def location_of(self, index: int, length: int = 1):
        from .model import Location

        start = self.byte_offsets[index]
        end_char = min(index + length, len(self.text))
        end = (
            self.byte_offsets[end_char]
            if end_char < len(self.byte_offsets)
            else self.byte_offsets[-1] + len(self.text[-1].encode("utf-8"))
            if self.text
            else start
        )
        return Location(start=start, end=end, line=self.lines[index])


def decode(text: str) -> DecodedText:
    """Build the codepoint-to-byte-offset map without loss."""
    byte_offsets: list[int] = []
    lines: list[int] = []
    offset = 0
    line = 1
    for ch in text:
        byte_offsets.append(offset)
        lines.append(line)
        offset += len(ch.encode("utf-8"))
        if ch == "\n":
            line += 1
    return DecodedText(text=text, byte_offsets=byte_offsets, lines=lines)


def word_count(text: str) -> int:
    """Approximate word count for the length-aware confidence (FR-49)."""
    return len(text.split())
