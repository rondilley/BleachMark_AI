"""Report layer: canonical JSON and a human Markdown view (FR-30, FR-31).

The Markdown renders from the JSON model, so the two do not drift. A redaction
filter removes a key or a secret from every output stream (SR-03). The report tells
the user that a machine-generation score is not a verdict and not watermark
identification (FR-13a), and it does not claim a vendor watermark without a key
(FR-19a).
"""

from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"xai-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S+"),
]

_MGT_DISCLAIMER = (
    "A machine-generation score is not a verdict and not watermark identification. "
    "This tool does not detect a vendor watermark without the vendor key."
)


def redact_secrets(text: str) -> str:
    """Remove a key or a secret from any output (SR-03)."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED-SECRET]", text)
    return text


def disclaimer() -> str:
    return _MGT_DISCLAIMER
