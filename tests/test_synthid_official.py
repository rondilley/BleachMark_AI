"""Official Hugging Face SynthID-Text cross-check (TC-06 independence).

Needs transformers>=4.46 with SynthIDTextWatermarkLogitsProcessor. Skips if the
class is not importable. Does not download a language model.
"""

import pytest

transformers = pytest.importorskip("transformers")

try:
    from transformers import SynthIDTextWatermarkLogitsProcessor  # noqa: F401
except Exception:
    pytest.skip("transformers has no SynthIDTextWatermarkLogitsProcessor", allow_module_level=True)

from bleachmark.detect.keyed.synthid_official import run_official_cross_check, THRESHOLD


def test_official_and_ours_each_fire_on_their_own_watermark():
    r = run_official_cross_check(seed=2)
    assert r.ours_fires_on_own, r
    assert r.official_null_on_clean, r
    assert r.ours_on_clean < THRESHOLD, r
    # official-on-official should rise; if the processor API changes, record it
    assert r.official_on_official > r.official_on_clean, r
    assert r.ours_null_on_official, r
