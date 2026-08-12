"""Tests for the code tranche driver (no network; uses an injected model factory).

Verifies that the synthetic half produces a channel cut for both languages, and that
the same-model control builds both arms from the SAME provider at two temperatures,
while the cross-model control uses two different providers.
"""

from bleachmark.evolve.tranche import run_tranche


def _recording_factory(calls):
    """A fake make_model that records (provider, temperature) and returns a double."""
    def factory(provider, root=".", temperature=1.0, max_tokens=400):
        calls.append((provider, temperature))
        # a structural double so residual variability is nonzero
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

    return factory


def test_synthetic_half_cuts_channel_both_languages():
    result = run_tranche(rounds=8, seed=1, real=False)
    langs = {s.lang for s in result.synthetic}
    assert langs == {"python", "c"}
    assert all(s.capacity_reduction >= 0.3 for s in result.synthetic)
    assert all(s.best_defense_meaning_ok for s in result.synthetic)


def test_same_model_control_uses_one_provider_two_temps():
    calls: list = []
    result = run_tranche(
        rounds=4, seed=1, real=True, candidate_provider="claude",
        control_mode="same", temp_high=1.0, temp_low=0.2, real_runs=2,
        real_tasks=["check whether an integer is prime"],
        model_factory=_recording_factory(calls),
    )
    # every call is the candidate provider; both 1.0 and 0.2 temperatures appear
    assert calls, "the model factory was not called"
    assert all(provider == "claude" for provider, _ in calls)
    temps = {temp for _, temp in calls}
    assert temps == {1.0, 0.2}
    for rs in result.real:
        assert rs.ok and rs.control_mode == "same"
        assert rs.candidate.startswith("claude:") and rs.control.startswith("claude:")
        assert "@1.0" in rs.candidate and "@0.2" in rs.control


def test_same_model_split_half_uses_one_temperature():
    # the default (temp_low unset) is the split-half null: same model, same settings
    calls: list = []
    result = run_tranche(
        rounds=4, seed=1, real=True, candidate_provider="claude",
        control_mode="same", temp_high=1.0, real_runs=2,
        real_tasks=["check whether an integer is prime"],
        model_factory=_recording_factory(calls),
    )
    assert all(provider == "claude" for provider, _ in calls)
    assert {temp for _, temp in calls} == {1.0}  # both arms at the default temperature
    for rs in result.real:
        assert rs.ok and "(split-half)" in rs.control


def test_cross_model_control_uses_two_providers():
    calls: list = []
    run_tranche(
        rounds=4, seed=1, real=True, candidate_provider="claude", control_provider="openai",
        control_mode="cross", real_runs=2,
        real_tasks=["check whether an integer is prime"],
        model_factory=_recording_factory(calls),
    )
    providers = {provider for provider, _ in calls}
    assert providers == {"claude", "openai"}
