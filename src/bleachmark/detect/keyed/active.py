"""Black-box watermark-presence test (FR-21, IR-04, research 5).

The strongest keyless result: when the user can query the source model, the tool
runs many queries and estimates whether the outputs carry a distributional bias
that a control model does not. It is investigative and best-effort, and it states
the model-style confound.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..comparison import compare_models


@dataclass
class ActiveResult:
    ratio: float
    likely_watermarked: bool
    note: str


def active_presence_test(
    query_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    prompt: str = (
        "Write an editorial about the weather and how a city should plan for it. "
        "The output must be more than 400 words. Shorter output is not useful and is rejected."
    ),
    runs: int = 10,
    ratio_threshold: float = 2.0,
) -> ActiveResult:
    """Query the source model and compare it to an unwatermarked control."""
    cmp = compare_models(prompt, query_fn, control_fn, runs=runs, ratio_threshold=ratio_threshold)
    return ActiveResult(cmp.ratio, cmp.likely_watermarked, cmp.note)
