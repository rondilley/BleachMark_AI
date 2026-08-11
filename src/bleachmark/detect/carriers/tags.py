"""Unicode Tags block carriers, ASCII smuggling (FR-06, research 7.2)."""

from __future__ import annotations

from ...decode import DecodedText
from ...model import Finding, Location, Posture, Severity, redact_payload
from . import context


def decode_tag_run(text: str) -> str:
    """Decode a run of tag characters back to ASCII for the redacted payload."""
    out = []
    for ch in text:
        cp = ord(ch)
        if 0xE0020 <= cp <= 0xE007E:
            out.append(chr(cp - 0xE0000))
    return "".join(out)


class _Tags:
    name = "tags_block"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        hits: list[Location] = []
        payload_chars: list[str] = []
        for i, ch in enumerate(text):
            cp = ord(ch)
            if not (0xE0000 <= cp <= 0xE007F):
                continue
            if context.in_subdivision_flag(text, i):
                continue
            hits.append(decoded.location_of(i))
            payload_chars.append(ch)
        if not hits:
            return []
        decoded_ascii = decode_tag_run("".join(payload_chars))
        payload_bytes = decoded_ascii.encode("utf-8")
        length, digest = redact_payload(payload_bytes)
        return [
            Finding(
                kind="tags_block",
                detector=self.name,
                severity=Severity.HIGH,
                summary=f"{len(hits)} Unicode Tags-block character(s): ASCII smuggling",
                locations=hits,
                posture=Posture.KEYLESS,
                confidence=0.99,
                false_positive_rate=0.0,
                payload_len=length,
                payload_sha256=digest,
                payload_cleartext=decoded_ascii,
                notes=["Invisible prompt-injection vector (research 7.2)."],
            )
        ]


detector = _Tags()
