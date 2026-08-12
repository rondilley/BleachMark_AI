"""Tests for the calibrate-code CLI path and its report emitter (no network).

The emitter shows a false-positive rate, not a verdict, and it redacts a secret. The CLI
subcommand parses, runs, and never lets the statistical rate drive the exit code (FR-36).
The calibration pipeline runs with an injected model double, so no network is needed.
"""

from bleachmark import cli
from bleachmark.report.calibration_emit import to_markdown_calibration, to_json_calibration
from bleachmark.bleach.live import run_style_calibration, TASKS

_T = {t.name: t for t in TASKS}


def _ok_result():
    return {
        "ok": True,
        "task": "fib",
        "lang": "python",
        "candidate": "claude:claude-opus-5",
        "references": ["openai:gpt-5.5", "gemini:gemini-3.1-pro"],
        "n_samples": 14,
        "finding": {
            "target_gap": 0.0,
            "fpr": 0.9585,
            "exceeds_baseline": False,
            "alpha": 0.05,
            "baseline": {"n": 240, "mean": 8.2, "p95": 17.6},
            "note": "A low rate is suggestive, not proof.",
        },
    }


def test_markdown_shows_fpr_and_not_a_verdict():
    md = to_markdown_calibration(_ok_result())
    assert "0.9585" in md                       # the false-positive rate is shown
    assert "no claim" in md.lower()             # not a yes-or-no verdict
    assert "not a verdict" in md.lower()        # the disclaimer is present
    assert "candidate model: claude:claude-opus-5" in md.lower()


def test_json_is_valid_and_redacts_a_secret():
    import json

    result = _ok_result()
    result["references"] = ["openai: ERROR key sk-abcdef0123456789abcdef"]
    text = to_json_calibration(result)
    parsed = json.loads(text)
    assert parsed["finding"]["fpr"] == 0.9585
    assert "disclaimer" in parsed
    assert "sk-abcdef0123456789abcdef" not in text   # the secret is redacted


def test_markdown_reports_a_failure():
    md = to_markdown_calibration({"ok": False, "error": "no reference corpus was generated"})
    assert "failed" in md.lower()
    assert "no reference corpus" in md


def _corpus_factory():
    varied = [
        "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
        "def solve(a, b):\n    while b != 0:\n        r = a % b\n        a = b\n        b = r\n    return a",
    ]
    converged = "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return a"

    def factory(provider, root=".", temperature=1.0, max_tokens=500):
        if provider == "claude":
            s = {"n": -1}

            def fn(prompt):
                s["n"] += 1
                return varied[s["n"] % len(varied)]

            return fn

        def fn(prompt):
            return converged

        return fn

    return factory


def test_calibration_pipeline_runs_with_a_double():
    result = run_style_calibration(
        candidate_provider="claude",
        reference_providers=["openai", "gemini"],
        task=_T["gcd"], lang="python", n_samples=12,
        model_factory=_corpus_factory(),
    )
    assert result["ok"]
    assert result["candidate"].startswith("claude:")
    f = result["finding"]
    assert isinstance(f["fpr"], float)
    assert 0.0 <= f["fpr"] <= 1.0


def test_cli_parser_has_calibrate_code():
    args = cli.build_parser().parse_args(
        ["calibrate-code", "--candidate", "claude", "--references", "openai,gemini", "--task", "fib"]
    )
    assert args.command == "calibrate-code"
    assert args.candidate == "claude"
    assert args.references == "openai,gemini"


def test_cli_exit_code_never_reflects_the_rate(monkeypatch, capsys):
    # a statistical finding, even one that stands out, must exit 0 (FR-36)
    import bleachmark.bleach.live as live

    def fake(**kwargs):
        r = _ok_result()
        r["finding"]["exceeds_baseline"] = True   # even a stand-out gap
        r["finding"]["fpr"] = 0.001
        return r

    monkeypatch.setattr(live, "run_style_calibration", fake)
    rc = cli.main(["calibrate-code", "--candidate", "claude", "--references", "openai"])
    out = capsys.readouterr().out
    assert rc == 0                    # never non-zero from the rate
    assert "0.001" in out


def test_cli_exit_one_on_operational_failure(monkeypatch):
    import bleachmark.bleach.live as live

    monkeypatch.setattr(live, "run_style_calibration",
                        lambda **kwargs: {"ok": False, "error": "no reference corpus"})
    rc = cli.main(["calibrate-code", "--candidate", "claude", "--references", "openai"])
    assert rc == 1                    # non-zero only when the probe cannot run


def test_cli_rejects_unknown_task(capsys):
    rc = cli.main(["calibrate-code", "--candidate", "claude", "--references", "openai", "--task", "nope"])
    assert rc == 1
    assert "unknown task" in capsys.readouterr().err


def _prose_factory(calls):
    # a fake model that returns varied editorial-like prose so featurization finds contexts
    import random

    def factory(provider, model=None, root=".", temperature=1.0, max_tokens=1200):
        calls.append((provider, model))

        def fn(prompt):
            rng = random.Random(hash((provider, model, prompt)) & 0xFFFF)
            words = ["the", "city", "should", "build", "more", "lanes", "now", "and", "save",
                     "lives", "cut", "traffic", "for", "people", "who", "ride", "a", "bike", "today"]
            return " ".join(rng.choice(words) for _ in range(120)) + "."

        return fn

    return factory


def test_cli_parser_has_calibrate_prose():
    args = cli.build_parser().parse_args(
        ["calibrate-prose", "--candidate", "claude", "--references", "openai,gemini", "--samples", "8"]
    )
    assert args.command == "calibrate-prose"
    assert args.candidate == "claude"
    assert args.samples == 8


def test_run_prose_calibration_with_a_double():
    from bleachmark.bleach.live import run_prose_calibration

    calls: list = []
    result = run_prose_calibration(
        candidate_provider="claude",
        reference_providers=["openai", "gemini", "claude:claude-opus-4-7"],  # a pre-cutoff spec
        n_samples=10, model_factory=_prose_factory(calls),
    )
    assert result["ok"]
    assert result["candidate"].startswith("claude:")
    assert "claude:claude-opus-4-7" in result["references"]   # the provider:model spec is parsed
    assert isinstance(result["finding"]["fpr"], float)
    assert 0.0 <= result["finding"]["fpr"] <= 1.0
