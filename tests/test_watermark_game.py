"""Validate the watermark-context vs bleach co-evolution on ground truth.

The game has two fidelity-safe attacks: a sentence-order reorder and a 15 percent substitution.
The co-evolution reaches a stable equilibrium at the unigram context and the substitution attack,
because at equal fidelity the substitution removes more than the reorder against every context.
"""

from bleachmark.harness.generators import make_vocab
from bleachmark.evolve.watermark_game import (
    Watermark,
    Attack,
    attack_fidelity,
    attack_feasible,
    game_payoff,
    degradation,
    co_evolve_game,
    fictitious_play,
    is_mixed,
    enriched_game,
)

VOCAB = make_vocab(80)


def test_attack_fidelity_and_feasibility():
    assert attack_feasible(Attack("reorder", unit_tokens=12))      # sentence reorder, 0.85
    assert not attack_feasible(Attack("reorder", unit_tokens=1))   # word reorder, 0.05
    assert attack_feasible(Attack("substitution", fraction=0.15))  # 0.70, at the gate
    assert not attack_feasible(Attack("substitution", fraction=0.30))  # 0.40


def test_infeasible_attack_has_zero_usable_degradation():
    # a word-order reverse removes signal, but it breaks the meaning, so it does not count
    raw = degradation(Watermark("prev"), Attack("reorder", unit_tokens=1), VOCAB, n_eval=2)
    usable = game_payoff(Watermark("prev"), Attack("reorder", unit_tokens=1), VOCAB, n_eval=2)
    assert raw > 0.5
    assert usable == 0.0


def test_substitution_beats_reorder_against_unigram():
    reorder = game_payoff(Watermark("unigram"), Attack("reorder", unit_tokens=12), VOCAB, n_eval=2)
    sub = game_payoff(Watermark("unigram"), Attack("substitution", fraction=0.15), VOCAB, n_eval=2)
    assert reorder == 0.0        # the reorder does nothing to a context-free watermark
    assert sub > 0.05            # the substitution does remove signal


def test_co_evolution_settles_on_unigram_and_substitution():
    r = co_evolve_game(VOCAB, rounds=8, total_tokens=200, n_eval=2, seed=0)
    assert r.stable
    assert r.best_context.kind == "unigram"        # the designer settles on the context-free watermark
    assert r.best_attack.kind == "substitution"    # the bleach settles on the substitution
    assert 0.05 < r.value < 0.5                     # a real, bounded equilibrium degradation


def test_fictitious_play_finds_a_mixed_equilibrium_when_one_exists():
    # matching pennies: the column player maximizes a match; the mix is one half each
    row, col, value = fictitious_play([[1, -1], [-1, 1]], iters=4000)
    assert is_mixed(row) and is_mixed(col)
    assert abs(row[0] - 0.5) < 0.1 and abs(value) < 0.05
    # rock-paper-scissors: the mix is one third each
    rps = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]
    r2, c2, v2 = fictitious_play(rps, iters=6000)
    assert is_mixed(r2) and abs(r2[0] - 1 / 3) < 0.1


def test_fictitious_play_finds_a_pure_equilibrium_when_one_dominates():
    row, col, value = fictitious_play([[0.1, 0.2], [0.5, 0.6]], iters=3000)
    assert not is_mixed(row)                       # the minimizer takes the dominant row
    assert row[0] > 0.9


def test_enriched_game_has_no_mixed_equilibrium_unigram_dominates():
    r = enriched_game(make_vocab(80), total_tokens=200, n_eval=2, seed=0)
    # unigram is the minimum in every column, so it is a dominant defense
    for col in range(len(r.attacks)):
        umin = min(range(len(r.contexts)), key=lambda row: r.matrix[row][col])
        assert r.contexts[umin] == "unigram"
    # so the equilibrium is pure: the designer plays unigram and does not mix
    assert not r.designer_mixed
    assert r.designer_mix["unigram"] > 0.9
