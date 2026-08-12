"""Report a calibrated code-watermark finding (FR-14, FR-15, FR-31).

The calibration scores a candidate model structural gap as a false-positive rate against a
reference style baseline. The report shows the rate, not a yes-or-no verdict, and it states
the honest limit: a low rate is suggestive, not proof of a watermark.
"""

from __future__ import annotations

import json

from . import redact_secrets

_CALIB_DISCLAIMER = (
    "This is a false-positive rate against a reference style baseline, not a verdict. A low "
    "rate is suggestive, not proof: a model with stronger slot-specific style than the "
    "references would also stand above the baseline with no watermark (the keyless limit)."
)


def _claim(finding: dict) -> str:
    if finding.get("exceeds_baseline"):
        return "gap above the style baseline (suggestive)"
    return "gap not above the style baseline (no claim)"


def to_json_calibration(result: dict) -> str:
    payload = dict(result)
    payload["disclaimer"] = _CALIB_DISCLAIMER
    return redact_secrets(json.dumps(payload, indent=2))


def to_markdown_calibration(result: dict) -> str:
    if not result.get("ok"):
        return redact_secrets(f"# Code-watermark calibration failed\n\n- Error: {result.get('error', 'unknown')}")

    f = result["finding"]
    base = f.get("baseline", {})
    lines: list[str] = []
    lines.append(f"# BleachMark code-watermark calibration: {result['task']} ({result['lang']})")
    lines.append("")
    lines.append(f"- Candidate model: {result['candidate']}")
    lines.append(f"- Reference models: {', '.join(result['references'])}")
    lines.append(f"- Samples per corpus: {result['n_samples']}")
    lines.append("")
    lines.append(f"> {_CALIB_DISCLAIMER}")
    lines.append("")
    lines.append("## Calibrated finding")
    lines.append("")
    lines.append("| Candidate gap | Baseline mean | Baseline p95 | False-positive rate | Alpha | Claim |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(
        f"| {f['target_gap']} | {base.get('mean', 'n/a')} | {base.get('p95', 'n/a')} "
        f"| {f['fpr']} | {f['alpha']} | {_claim(f)} |"
    )
    lines.append("")
    lines.append(f"Baseline samples: {base.get('n', 0)}. {f.get('note', '')}")
    return redact_secrets("\n".join(lines))
