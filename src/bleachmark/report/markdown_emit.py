"""Markdown report rendered from the JSON model (FR-31)."""

from __future__ import annotations

from ..model import Report
from . import disclaimer, redact_secrets


def to_markdown(report: Report, show_payload: bool = False) -> str:
    lines: list[str] = []
    lines.append(f"# BleachMark report: {report.target}")
    lines.append("")
    lines.append(f"- Text length: {report.text_length_words} words")
    if report.before_score is not None:
        lines.append(f"- Before-detection score: {report.before_score:.3f}")
    if report.after_score is not None:
        lines.append(f"- After-detection score: {report.after_score:.3f}")
    lines.append("")
    lines.append(f"> {disclaimer()}")
    lines.append("")
    if not report.findings:
        lines.append("No hidden signal found.")
        return redact_secrets("\n".join(lines))
    lines.append("## Findings")
    lines.append("")
    lines.append("| Kind | Detector | Severity | Posture | Score | FPR | Summary |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for f in report.findings:
        score = "" if f.score is None else f"{f.score:.3f}"
        fpr = "" if f.false_positive_rate is None else f"{f.false_positive_rate:.4f}"
        lines.append(
            f"| {f.kind} | {f.detector} | {f.severity.value} | {f.posture.value} "
            f"| {score} | {fpr} | {f.summary} |"
        )
    lines.append("")
    for f in report.findings:
        if f.payload_len is not None:
            lines.append(
                f"- Payload for `{f.kind}`: {f.payload_len} bytes, "
                f"sha256 `{f.payload_sha256[:16]}...`"
            )
            if show_payload and f.payload_cleartext is not None:
                lines.append(f"  - cleartext: `{f.payload_cleartext}`")
    return redact_secrets("\n".join(lines))
