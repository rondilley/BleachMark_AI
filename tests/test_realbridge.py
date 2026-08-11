"""Tests for the real-model evolution bridge (no network; uses doubles).

Verifies that a genome compiles to a constraint prompt, that the cache avoids
repeat calls, and that evolve_real runs the full loop with model callables.
"""

from bleachmark.evolve.realbridge import (
    RealPromptGenome,
    ModelCache,
    real_fitness,
    evolve_real,
)


def _structural_model():
    forms = [
        "def f(x):\n    return x + 1",
        "def f(x):\n    return 1 + x",
        "def f(x):\n    a = x\n    a += 1\n    return a",
    ]
    s = {"n": 0}

    def fn(prompt):
        s["n"] += 1
        return forms[s["n"] % len(forms)]

    return fn


def _canonical_model():
    def fn(prompt):
        return "def f(x):\n    return x + 1"

    return fn


def test_genome_compiles_constraints():
    g = RealPromptGenome(fix_names=True, iterative_only=True, no_comments=True)
    prompt = g.compile_prompt("check whether an integer is prime")
    assert "def f(x)" in prompt
    assert "no recursion" in prompt.lower()
    assert "no comments" in prompt.lower()


def test_cache_avoids_repeat_calls():
    cache = ModelCache()
    model = _structural_model()
    a = cache.samples(model, "m", "same prompt", 3)
    calls_after_first = cache.calls
    b = cache.samples(model, "m", "same prompt", 3)
    assert a == b
    assert cache.calls == calls_after_first  # second request served from cache


def test_real_fitness_rewards_candidate_structure():
    cache = ModelCache()
    ev = real_fitness(
        RealPromptGenome(n_runs=3, n_tasks=2),
        _structural_model(),
        _canonical_model(),
        "cand",
        "ctrl",
        cache,
    )
    assert ev.candidate_residual > ev.control_residual
    assert ev.fitness > 0


def test_evolve_real_runs_full_loop():
    result = evolve_real(
        _structural_model(),
        _canonical_model(),
        "cand",
        "ctrl",
        generations=3,
        pop_size=4,
        seed=1,
    )
    assert len(result.history) == 3
    assert result.best_eval.fitness >= result.history[0]
    assert result.cache_calls > 0
