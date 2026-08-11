"""Markdown-specific carriers (FR-10, research 7.5)."""

from __future__ import annotations

import re

from ...decode import DecodedText
from ...model import Finding, Posture, Severity, redact_payload

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)


class _Markdown:
    name = "markdown"

    def detect(self, decoded: DecodedText) -> list[Finding]:
        text = decoded.text
        findings: list[Finding] = []

        comments = list(_HTML_COMMENT.finditer(text))
        # a review-annotation comment is benign; a long hidden block is the carrier
        payloads = [c for c in comments if len(c.group(1).strip()) > 0]
        if payloads:
            locs = [decoded.location_of(c.start(), c.end() - c.start()) for c in payloads]
            joined = "\n".join(c.group(1) for c in payloads).encode("utf-8")
            length, digest = redact_payload(joined)
            findings.append(
                Finding(
                    kind="markdown_comment",
                    detector=self.name,
                    severity=Severity.MEDIUM,
                    summary=f"{len(payloads)} HTML comment(s): hidden text that renders to nothing",
                    locations=locs,
                    posture=Posture.KEYLESS,
                    confidence=0.75,
                    false_positive_rate=0.05,
                    payload_len=length,
                    payload_sha256=digest,
                    payload_cleartext="\n".join(c.group(1) for c in payloads),
                    notes=["Most capacious Markdown carrier (research 7.5)."],
                )
            )
        return findings


detector = _Markdown()
