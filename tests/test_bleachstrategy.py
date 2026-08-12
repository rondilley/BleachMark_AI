"""Validate the bleach-strategy library and the strategy evolution on ground truth.

The reorder family has a real trade-off: a finer unit removes more watermark but is harder to
keep coherent. The evolution measures the degradation against the real green-list scheme, holds
the meaning gate, and finds the strongest meaning-safe strategy. The transcode strategy (write
in another language, deterministic translate) removes the whole English-key watermark, so the
evolution favors it over the reorder family.
"""

from bleachmark.detect.keyed.greenlist import GreenListScheme
from bleachmark.harness.generators import make_vocab
from bleachmark.bleach.strategies import Strategy
from bleachmark.evolve.bleachstrategy import evaluate_strategy, evolve_strategies, base_forward_z

TT = 200


def _scheme():
    return GreenListScheme(key="wm-key", vocab=make_vocab(80), gamma=0.25)


def test_restore_is_a_lossless_inverse():
    for kind, param in (("reverse", 0), ("block_reverse", 3), ("stride", 3), ("rotate", 2)):
        s = Strategy(kind=kind, param=param)
        units = [f"u{i}" for i in range(9)]
        order = s.generation_order(len(units))
        generated = [units[i] for i in order]     # what the model writes, in generation order
        assert s.restore(generated) == units       # the deterministic restore inverts it


def test_finer_unit_removes_more_watermark_but_loses_fidelity():
    scheme = _scheme()
    base = base_forward_z(scheme, TT, n_eval=2, seed=0)
    word = evaluate_strategy(Strategy("reverse", unit_tokens=1), scheme, TT, n_eval=2, seed=0, base_z=base)
    sentence = evaluate_strategy(Strategy("reverse", unit_tokens=12), scheme, TT, n_eval=2, seed=0, base_z=base)
    # a word-order reverse removes almost all the watermark, a sentence-order reverse little
    assert word.degradation > sentence.degradation + 0.3
    # but the word-order rewrite is not coherent, so it fails the meaning gate
    assert not word.fidelity_ok
    assert sentence.fidelity_ok


def test_transcode_removes_the_watermark_and_keeps_fidelity():
    scheme = _scheme()
    e = evaluate_strategy(Strategy("transcode", translation_quality=0.8), scheme, TT, n_eval=2, seed=0)
    assert e.degradation >= 0.99
    assert e.fidelity == 0.8
    assert e.fidelity_ok


def test_evolution_finds_a_meaning_safe_high_degradation_strategy():
    scheme = _scheme()
    r = evolve_strategies(scheme, generations=6, pop_size=8, total_tokens=TT, n_eval=2, seed=1)
    assert r.best_eval.fidelity_ok
    assert r.best_eval.degradation >= 0.5      # far beyond what a deployable reorder alone reaches
    # transcode dominates the reorder family in the search
    assert r.best.kind == "transcode"
