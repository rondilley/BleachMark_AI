"""Bridge the evolution loop to a real model (FR-56, FR-52).

The synthetic arena evolves against a known embedder with ground truth. This
bridge closes the full loop: a genome compiles into a real constraint prompt, a
fitness function runs that prompt through the provider adapter against a candidate
model and a control model, measures the canonical residual, and feeds the number
back so the population evolves against a live target.

Honesty: on a real model the tool has no key and no ground truth, so the fitness is
a proxy, not a validated watermark detection. The bridge optimizes the constraint
that most exposes the candidate's structural residual relative to the control. It
demonstrates the full pipeline and produces a real evolved constraint template. It
does not prove a watermark, because a distortion-free scheme stays invisible and
model style confounds the residual.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Callable

from ..detect.code import _residual_variability

TASKS = [
    "check whether an integer is prime",
    "return the nth Fibonacci number",
    "compute the greatest common divisor of two integers",
    "return the maximum value in a list",
]


@dataclass
class RealPromptGenome:
    fix_names: bool = True          # fix the identifier names
    fix_structure: bool = False     # prescribe one structure (tightest)
    iterative_only: bool = True     # forbid recursion
    no_comments: bool = True        # forbid comments and docstrings
    temperature: float = 1.0        # sampling temperature
    n_runs: int = 3                 # samples per task
    n_tasks: int = 2                # tasks used from TASKS

    def mutate(self, rng: random.Random) -> "RealPromptGenome":
        g = RealPromptGenome(**self.__dict__)
        gene = rng.choice(
            ["fix_names", "fix_structure", "iterative_only", "no_comments", "temperature", "n_tasks"]
        )
        if gene == "temperature":
            g.temperature = rng.choice([0.7, 1.0, 1.3])
        elif gene == "n_tasks":
            g.n_tasks = rng.choice([2, 3, 4])
        else:
            setattr(g, gene, not getattr(g, gene))
        return g

    def compile_prompt(self, task: str) -> str:
        parts = [f"Write a Python function for: {task}."]
        if self.fix_names:
            parts.append("Use exactly this signature: def f(x). Name every local a, b, c.")
        if self.fix_structure:
            parts.append("Use a single loop and a single return. Do not use a helper.")
        if self.iterative_only:
            parts.append("Iterative only, no recursion.")
        if self.no_comments:
            parts.append("No comments, no docstring, no prose.")
        parts.append("Return only the code.")
        return " ".join(parts)


class ModelCache:
    """Cache generations by (model id, prompt) so evolution does not re-pay."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], list[str]] = {}
        self.calls = 0

    def samples(self, fn: Callable[[str], str], model_id: str, prompt: str, n: int) -> list[str]:
        key = (model_id, prompt)
        have = self.store.setdefault(key, [])
        while len(have) < n:
            have.append(fn(prompt))
            self.calls += 1
        return have[:n]


@dataclass
class RealEvaluation:
    fitness: float
    candidate_residual: float
    control_residual: float
    corpus_words: int


def real_fitness(
    genome: RealPromptGenome,
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    candidate_id: str,
    control_id: str,
    cache: ModelCache,
) -> RealEvaluation:
    """Measure the candidate's exposed structural residual against the control."""
    cand_res: list[float] = []
    ctrl_res: list[float] = []
    corpus_words = 0
    for task in TASKS[: genome.n_tasks]:
        prompt = genome.compile_prompt(task)
        cand = cache.samples(candidate_fn, candidate_id, prompt, genome.n_runs)
        ctrl = cache.samples(control_fn, control_id, prompt, genome.n_runs)
        corpus_words += sum(len(s.split()) for s in cand)
        cand_res.append(_residual_variability(cand))
        ctrl_res.append(_residual_variability(ctrl))
    cr = statistics.mean(cand_res)
    xr = statistics.mean(ctrl_res)
    # reward exposing the candidate structure, penalize generic looseness that also
    # makes the control vary. This is a proxy, not a validated watermark signal.
    fitness = cr - 0.5 * xr
    return RealEvaluation(fitness, cr, xr, corpus_words)


@dataclass
class RealEvolutionResult:
    best: RealPromptGenome
    best_eval: RealEvaluation
    history: list[float]
    cache_calls: int
    population_final: list[RealPromptGenome] = field(default_factory=list)


def evolve_real(
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    candidate_id: str,
    control_id: str,
    generations: int = 3,
    pop_size: int = 4,
    seed: int = 0,
) -> RealEvolutionResult:
    """Evolve a constraint prompt against a live candidate and control model."""
    rng = random.Random(seed)
    cache = ModelCache()
    population = [RealPromptGenome().mutate(rng) for _ in range(pop_size)]
    history: list[float] = []
    best: RealPromptGenome | None = None
    best_eval: RealEvaluation | None = None

    for _ in range(generations):
        scored = [
            (g, real_fitness(g, candidate_fn, control_fn, candidate_id, control_id, cache))
            for g in population
        ]
        scored.sort(key=lambda pair: pair[1].fitness, reverse=True)
        history.append(scored[0][1].fitness)
        if best_eval is None or scored[0][1].fitness > best_eval.fitness:
            best, best_eval = scored[0]
        survivors = [g for g, _ in scored[: max(2, pop_size // 2)]]
        children: list[RealPromptGenome] = []
        while len(survivors) + len(children) < pop_size:
            children.append(rng.choice(survivors).mutate(rng))
        population = survivors + children

    return RealEvolutionResult(best, best_eval, history, cache.calls, population)
