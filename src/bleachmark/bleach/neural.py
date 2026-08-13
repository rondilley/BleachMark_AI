"""Highest-strength bleach: model-based semantic paraphrase (FR-26, FR-42).

The paraphrase needs a configured model. The model is a callable that takes text
and returns paraphrased text. Every call goes through the model gateway, which runs
the carrier normalize first and fails closed (SR-06, SR-09). When no model is
configured the caller gets a clear message, not a stack dump.
"""

from __future__ import annotations

from ..runtime.model import ModelGateway


def paraphrase_bleach(text: str, model=None, gateway: ModelGateway | None = None) -> str:
    if model is None:
        raise RuntimeError(
            "the paraphrase bleach needs a configured model. "
            "Give a callable(text)->text, or use a lower bleach strength."
        )
    gw = gateway or ModelGateway(model)
    prompt = (
        "Paraphrase the following text. Keep the meaning and the facts. "
        "Change the wording and the sentence structure. "
        "If the input is more than 400 words, the rewrite must also be more than 400 words. "
        "Shorter output is not useful and is rejected.\n\n" + text
    )
    return gw.call(prompt)
