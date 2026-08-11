"""Canonical JSON report (FR-30, DR-02)."""

from __future__ import annotations

import json

from ..model import Report
from . import disclaimer, redact_secrets


def to_json(report: Report, show_payload: bool = False, indent: int = 2) -> str:
    data = report.to_dict(show_payload=show_payload)
    data["disclaimer"] = disclaimer()
    text = json.dumps(data, ensure_ascii=True, indent=indent)
    return redact_secrets(text)
