"""Tests for the hardware-aware model registry and selection."""

from bleachmark.runtime.models import (
    REGISTRY, select_for, recommend, candidates_for,
    REFERENCE, PARAPHRASE, NEURAL,
)


def test_vram_estimate_grows_with_params():
    ordered = sorted(REGISTRY, key=lambda m: m.params_b)
    vrams = [m.vram_mb() for m in ordered]
    assert vrams == sorted(vrams)                  # more parameters, more video memory
    assert 40000 < ordered[-1].vram_mb() < 50000   # a 70B at Q4 is about 45 GB


def test_select_picks_largest_that_fits():
    sel = select_for(REFERENCE, 32607)             # a 32 GB card
    assert sel.fits
    assert sel.model.params_b == 32.0              # the 32B fits, the 70B does not
    small = select_for(REFERENCE, 8000)            # an 8 GB card
    assert small.fits
    assert small.model.params_b == 8.0


def test_select_reports_when_nothing_fits():
    sel = select_for(REFERENCE, 2000)              # too small for any reference model
    assert not sel.fits
    assert sel.model is not None                   # it still names the smallest option
    assert "none fits" in sel.note


def test_function_partitions_the_registry():
    assert all(NEURAL in m.functions for m in candidates_for(NEURAL))
    # the 70B is a reference model, not a neural detector
    ref_names = {m.name for m in candidates_for(REFERENCE)}
    assert "Llama-3.3-70B-Instruct" in ref_names
    assert "Llama-3.3-70B-Instruct" not in {m.name for m in candidates_for(NEURAL)}


def test_recommend_covers_all_functions():
    rec = recommend(32607)
    assert set(rec) == {REFERENCE, PARAPHRASE, NEURAL}
    assert rec[NEURAL].model.params_b == 8.0       # the largest neural model that fits
