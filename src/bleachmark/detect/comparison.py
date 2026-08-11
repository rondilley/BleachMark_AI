"""Cross-run and cross-model comparison (FR-38, FR-47, FR-48, ARCHITECTURE 9).

This is an investigative, best-effort method, not a guaranteed detection. It runs a
candidate model and a control model on the same prompt many times, then compares
the token distributions. A control model that adds no watermark gives the null
baseline. The result states the model-style confound and the undetectability limit.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

_WORD = re.compile(r"\w+", re.UNICODE)


def _distribution(samples: list[str]) -> Counter:
    c: Counter = Counter()
    for s in samples:
        c.update(_WORD.findall(s.lower()))
    total = sum(c.values()) or 1
    return Counter({k: v / total for k, v in c.items()})


def _l1(a: Counter, b: Counter) -> float:
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


@dataclass
class ComparisonResult:
    divergence: float
    baseline: float
    ratio: float
    likely_watermarked: bool
    note: str


def compare_models(
    prompt: str,
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    runs: int = 8,
    ratio_threshold: float = 2.0,
) -> ComparisonResult:
    """Compare a candidate against an unwatermarked control (FR-38, FR-47)."""
    cand = [candidate_fn(prompt) for _ in range(runs)]
    ctrl = [control_fn(prompt) for _ in range(runs)]
    # split the control in half to measure the natural run-to-run baseline
    half = max(1, runs // 2)
    ctrl_a = _distribution(ctrl[:half])
    ctrl_b = _distribution(ctrl[half:])
    baseline = _l1(ctrl_a, ctrl_b) or 1e-9
    divergence = _l1(_distribution(cand), _distribution(ctrl))
    ratio = divergence / baseline
    note = (
        "Investigative and best-effort. A cross-model result can confuse model "
        "style with a watermark, and an undetectable watermark stays undetectable "
        "(research 5). The control claim is unverified and must be re-checked (FR-48)."
    )
    return ComparisonResult(divergence, baseline, ratio, ratio >= ratio_threshold, note)
