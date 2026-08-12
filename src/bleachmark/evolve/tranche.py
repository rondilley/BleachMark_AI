"""The code tranche driver: run many co-evolution rounds, then confirm on real models.

This is the first learning tranche, focused on writing code in Python and C. It has
two halves:

1. Synthetic co-evolution against a known code stego modality, where the ground
   truth is known, so the defense channel-cut and the detection recovery are
   measured, not asserted. This runs many rounds cheaply and deterministically.

2. A real-model confirmation. The evolved constraint prompt runs against a live
   candidate model and a live control model for each language. The tool measures
   the residual variability that survives the constraint, after canonicalization.
   On a real model there is no key and no ground truth, so this residual is an
   honest proxy for the surviving channel, not a proof of a watermark (research 3,
   5). It satisfies the evidence rule: the tranche produces real data, not a stub.

Run: python -m bleachmark.evolve.tranche [--rounds N] [--no-real] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import Callable

from ..detect.code import _residual_variability
from ..detect.features import featurize
from ..detect.partition_test import steal_and_test
from .coevolve import CodeModality, DefensePrompt, coevolve, CoEvolutionResult

LANGS = ("python", "c")


@dataclass
class SyntheticSummary:
    lang: str
    baseline_capacity: float
    final_capacity: float
    capacity_reduction: float
    capacity_curve: list[float]
    separation_curve: list[float]
    best_defense: dict
    best_defense_open_slots: int
    best_defense_meaning_ok: bool
    best_detector: dict
    final_recovery: float
    final_fpr: float


def _synthetic(lang: str, rounds: int, seed: int) -> tuple[SyntheticSummary, CoEvolutionResult]:
    m = CodeModality(key=f"stego-{lang}", lang=lang)
    r = coevolve(m, rounds=rounds, def_pop=8, det_pop=8, n_eval=16, seed=seed)
    last = r.rounds[-1]
    summary = SyntheticSummary(
        lang=lang,
        baseline_capacity=round(r.baseline_capacity, 4),
        final_capacity=round(r.final_capacity, 4),
        capacity_reduction=round(r.capacity_reduction, 4),
        capacity_curve=[round(x, 4) for x in r.capacity_curve],
        separation_curve=[round(x, 4) for x in r.separation_curve],
        best_defense=asdict(r.best_defense),
        best_defense_open_slots=r.best_defense.open_slots(m),
        best_defense_meaning_ok=r.best_defense.meaning_ok(m),
        best_detector=asdict(r.best_detector),
        final_recovery=round(last.detection.recovery, 4),
        final_fpr=round(last.detection.fpr, 4),
    )
    return summary, r


@dataclass
class RealSummary:
    lang: str
    ok: bool
    control_mode: str = "same"      # "same" model at two settings, or "cross" model
    candidate: str = ""
    control: str = ""
    constraint: str = ""
    candidate_residual: float = 0.0
    control_residual: float = 0.0
    excess: float = 0.0
    corpus_words: int = 0
    error: str = ""


def _real_probe(
    defense: DefensePrompt,
    lang: str,
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    tasks: list[str],
    runs: int,
) -> tuple[float, float, int, str]:
    """Run the evolved constraint against two model arms; measure the residual."""
    constraint = defense.describe(lang=lang)
    verb = "a C function" if lang == "c" else "a Python function"
    tail = " Return only the code, no includes." if lang == "c" else ""
    cand_res, ctrl_res, corpus_words = [], [], 0
    for task in tasks:
        prompt = f"Write {verb} for: {task}. {constraint}{tail}"
        cand = [candidate_fn(prompt) for _ in range(runs)]
        ctrl = [control_fn(prompt) for _ in range(runs)]
        corpus_words += sum(len(s.split()) for s in cand)
        cand_res.append(_residual_variability(cand, lang))
        ctrl_res.append(_residual_variability(ctrl, lang))
    return statistics.mean(cand_res), statistics.mean(ctrl_res), corpus_words, constraint


def _real(
    lang: str,
    defense: DefensePrompt,
    candidate_provider: str,
    control_provider: str,
    tasks: list[str],
    runs: int,
    root: str,
    control_mode: str = "same",
    temp_high: float = 1.0,
    temp_low: float | None = None,
    model_factory: Callable[..., Callable[[str], str]] | None = None,
) -> RealSummary:
    """Run the model confirmation for one language.

    control_mode "same": both arms are the SAME candidate model. This holds the model
    style constant, so the residual difference no longer mixes two models' styles. By
    default both arms use the same settings, so the two arms are a split-half null:
    the same model, drawn twice into disjoint sample sets. A near-zero excess then
    shows that a cross-model excess was model style, not a watermark. If temp_low is
    given and the model accepts it, the control arm drops to that temperature, near
    the model's structural mode. control_mode "cross": the old different-model
    baseline (the residual difference mixes the two models' styles).

    Note: some newer models (for example claude-opus-5) reject a non-default
    temperature. For those, leave temp_low unset so the same-model split-half runs.
    """
    if model_factory is None:
        from ..runtime.providers import make_model as model_factory  # type: ignore
    from ..runtime.providers import DEFAULT_MODELS

    def label(provider: str, temp: float, tag: str = "") -> str:
        model = DEFAULT_MODELS.get(provider, "")
        return f"{provider}:{model}@{temp}{tag}"

    try:
        if control_mode == "same":
            ctrl_temp = temp_high if temp_low is None else temp_low
            candidate_fn = model_factory(candidate_provider, root=root, temperature=temp_high, max_tokens=400)
            control_fn = model_factory(candidate_provider, root=root, temperature=ctrl_temp, max_tokens=400)
            cand_label = label(candidate_provider, temp_high)
            split = " (split-half)" if temp_low is None else ""
            ctrl_label = label(candidate_provider, ctrl_temp, split)
        else:
            candidate_fn = model_factory(candidate_provider, root=root, temperature=temp_high, max_tokens=400)
            control_fn = model_factory(control_provider, root=root, temperature=temp_high, max_tokens=400)
            cand_label = label(candidate_provider, temp_high)
            ctrl_label = label(control_provider, temp_high)
        cr, xr, words, constraint = _real_probe(
            defense, lang, candidate_fn, control_fn, tasks, runs
        )
        return RealSummary(
            lang=lang,
            ok=True,
            control_mode=control_mode,
            candidate=cand_label,
            control=ctrl_label,
            constraint=constraint,
            candidate_residual=round(cr, 4),
            control_residual=round(xr, 4),
            excess=round(cr - xr, 4),
            corpus_words=words,
        )
    except Exception as exc:  # network, key, or provider error: record, do not crash
        return RealSummary(lang=lang, ok=False, control_mode=control_mode,
                           error=f"{type(exc).__name__}: {exc}"[:300])


@dataclass
class PartitionSummary:
    lang: str
    ok: bool
    model: str = ""
    runs_per_task: int = 0
    variants_k: int = 4
    per_task: list[dict] = field(default_factory=list)
    mean_gap: float = 0.0
    mean_z_true: float = 0.0
    min_p_value: float = 1.0
    any_keyed: bool = False
    error: str = ""


def _partition_probe(
    lang: str,
    defense: DefensePrompt,
    provider: str,
    tasks: list[str],
    runs: int,
    k: int,
    root: str,
    model_factory: Callable[..., Callable[[str], str]] | None = None,
) -> PartitionSummary:
    """Featurize one model's constrained code and run the steal-and-test z-test.

    This is the same-model keyed-watermark test. For each task the model writes the
    function `runs` times. The featurizer turns the samples into a (slot, variant)
    matrix. The steal-and-test z-test splits the samples, steals the green partition,
    tests the held-out set, and runs the slot-permutation null. A large positive gap
    with a small p-value is keyed structure. On a real distortion-free scheme the test
    is expected to hit the wall (research §5).
    """
    if model_factory is None:
        from ..runtime.providers import make_model as model_factory  # type: ignore
    from ..runtime.providers import DEFAULT_MODELS

    try:
        fn = model_factory(provider, root=root, temperature=1.0, max_tokens=400)
        constraint = defense.describe(lang=lang)
        verb = "a C function" if lang == "c" else "a Python function"
        tail = " Return only the code, no includes." if lang == "c" else ""
        per_task: list[dict] = []
        gaps, zs, ps, keyed = [], [], [], []
        for task in tasks:
            prompt = f"Write {verb} for: {task}. {constraint}{tail}"
            samples = [fn(prompt) for _ in range(runs)]
            fm = featurize(samples, lang, k=k)
            if fm.n_slots < 2:
                per_task.append({"task": task, "n_slots": fm.n_slots, "note": "too few slots"})
                continue
            r = steal_and_test(fm.rows, fm.k, fm.n_slots, permutations=300, seed=0)
            per_task.append({
                "task": task, "n_slots": fm.n_slots,
                "z_true": round(r.z_true, 3), "z_null_mean": round(r.z_null_mean, 3),
                "gap": round(r.gap, 3), "p_value": round(r.p_value, 4),
                "keyed_signal": r.keyed_signal,
            })
            gaps.append(r.gap); zs.append(r.z_true); ps.append(r.p_value); keyed.append(r.keyed_signal)
        return PartitionSummary(
            lang=lang, ok=True, model=f"{provider}:{DEFAULT_MODELS.get(provider, '')}",
            runs_per_task=runs, variants_k=k, per_task=per_task,
            mean_gap=round(statistics.mean(gaps), 3) if gaps else 0.0,
            mean_z_true=round(statistics.mean(zs), 3) if zs else 0.0,
            min_p_value=round(min(ps), 4) if ps else 1.0,
            any_keyed=any(keyed),
        )
    except Exception as exc:
        return PartitionSummary(lang=lang, ok=False, error=f"{type(exc).__name__}: {exc}"[:300])


@dataclass
class TrancheResult:
    rounds: int
    seed: int
    synthetic: list[SyntheticSummary] = field(default_factory=list)
    real: list[RealSummary] = field(default_factory=list)
    partition: list[PartitionSummary] = field(default_factory=list)


def run_tranche(
    rounds: int = 10,
    seed: int = 1,
    real: bool = True,
    candidate_provider: str = "claude",
    control_provider: str = "openai",
    real_tasks: list[str] | None = None,
    real_runs: int = 4,
    root: str = ".",
    control_mode: str = "same",
    temp_high: float = 1.0,
    temp_low: float | None = None,
    partition_runs: int = 0,
    partition_k: int = 4,
    partition_tasks: list[str] | None = None,
    model_factory: Callable[..., Callable[[str], str]] | None = None,
) -> TrancheResult:
    tasks = real_tasks or [
        "check whether an integer is prime",
        "return the nth Fibonacci number, iterative",
        "compute the greatest common divisor of two integers",
    ]
    result = TrancheResult(rounds=rounds, seed=seed)
    evolved: dict[str, DefensePrompt] = {}
    for lang in LANGS:
        summary, coev = _synthetic(lang, rounds, seed)
        result.synthetic.append(summary)
        evolved[lang] = coev.best_defense
    if real:
        for lang in LANGS:
            result.real.append(
                _real(lang, evolved[lang], candidate_provider, control_provider, tasks,
                      real_runs, root, control_mode=control_mode, temp_high=temp_high,
                      temp_low=temp_low, model_factory=model_factory)
            )
    if partition_runs > 0:
        ptasks = partition_tasks or tasks
        for lang in LANGS:
            result.partition.append(
                _partition_probe(lang, evolved[lang], candidate_provider, ptasks,
                                 partition_runs, partition_k, root, model_factory=model_factory)
            )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the code learning tranche.")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-real", action="store_true", help="skip the real-model confirmation")
    ap.add_argument("--candidate", default="claude", help="candidate provider (marks at launch)")
    ap.add_argument("--control", default="openai", help="control provider (cross mode only)")
    ap.add_argument("--control-mode", default="same", choices=["same", "cross"],
                    help="'same' model at two temperatures, or 'cross' different model")
    ap.add_argument("--temp-high", type=float, default=1.0, help="candidate-arm temperature")
    ap.add_argument("--temp-low", type=float, default=None,
                    help="same-model control temperature; unset runs the split-half null "
                         "(needed for models that reject a non-default temperature)")
    ap.add_argument("--runs", type=int, default=4, help="real samples per task")
    ap.add_argument("--partition-runs", type=int, default=0,
                    help="samples per task for the steal-and-test partition probe (0 skips)")
    ap.add_argument("--partition-k", type=int, default=4, help="variants per slot for the featurizer")
    ap.add_argument("--root", default=".", help="root that holds <provider>.key.txt")
    ap.add_argument("--out", default="", help="write the JSON result to this path")
    args = ap.parse_args()

    result = run_tranche(
        rounds=args.rounds,
        seed=args.seed,
        real=not args.no_real,
        candidate_provider=args.candidate,
        control_provider=args.control,
        real_runs=args.runs,
        root=args.root,
        control_mode=args.control_mode,
        temp_high=args.temp_high,
        temp_low=args.temp_low,
        partition_runs=args.partition_runs,
        partition_k=args.partition_k,
    )
    payload = {
        "rounds": result.rounds,
        "seed": result.seed,
        "synthetic": [asdict(s) for s in result.synthetic],
        "real": [asdict(s) for s in result.real],
        "partition": [asdict(s) for s in result.partition],
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
