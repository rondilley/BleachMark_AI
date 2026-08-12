"""Evolve bleach strategies against a known watermark (FR-56 to FR-60, research 3, 7).

The tool does not only run the strategies a person names. It searches the strategy space and
evolves toward the strategies that remove the most watermark while they keep the meaning. The
search runs against the real context-keyed green-list scheme, so the degradation is measured,
not asserted.

The degradation model is honest about the unit granularity. A reorder bleach breaks the
context only at the unit boundaries. Inside a unit the model still writes forward, so those
tokens keep the correct context and the green bias. So a coarse unit (a sentence) breaks few
boundaries and removes little watermark, and a fine unit (a word) breaks every boundary and
removes a lot, but a word-order rewrite is not coherent. That is the trade-off. The earlier
token-level number was the fine-grain upper bound, not the deployable sentence-level effect.

The fidelity is a model. A coarse unit is easier to keep coherent than a fine unit. Transcode
(write in another language, deterministic translate) removes the whole English-key watermark,
so its degradation is full and its fidelity is the translation quality. The meaning gate is a
hard limit: a strategy below the gate is not valid, however much watermark it removes.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

from ..detect.keyed.greenlist import GreenListScheme
from ..bleach.strategies import Strategy, ALL_KINDS, UNIT_TOKENS

_GRAN_FIDELITY = {1: 0.05, 4: 0.6, 12: 0.85, 40: 0.95}
_DISRUPTION = {"identity": 1.0, "reverse": 1.0, "block_reverse": 0.95,
               "stride": 0.8, "rotate": 0.9, "transcode": 1.0}


def _sample_green(scheme: GreenListScheme, prev: str, rng: random.Random, delta: float) -> str:
    gw = math.exp(delta)
    weights = [gw if scheme.is_green(prev, t) else 1.0 for t in scheme.vocab]
    total = sum(weights)
    r = rng.random() * total
    acc = 0.0
    for t, w in zip(scheme.vocab, weights):
        acc += w
        if r <= acc:
            return t
    return scheme.vocab[-1]


def generate_unit_order(scheme, unit_sizes, gen_order, seed, delta) -> list[str]:
    """Generate green-list tokens in a unit order, with forward context inside each unit."""
    rng = random.Random(seed)
    offsets, acc = [], 0
    for s in unit_sizes:
        offsets.append(acc)
        acc += s
    reading: list[str] = [""] * acc
    prev = "<s>"
    for ui in gen_order:
        for k in range(unit_sizes[ui]):
            tok = _sample_green(scheme, prev, rng, delta)
            reading[offsets[ui] + k] = tok
            prev = tok
    return reading


def _unit_sizes(total_tokens: int, unit_tokens: int) -> list[int]:
    n_units = max(1, total_tokens // max(1, unit_tokens))
    base = total_tokens // n_units
    sizes = [base] * n_units
    for i in range(total_tokens - base * n_units):
        sizes[i] += 1
    return sizes


def forward_z(strategy: Strategy, scheme: GreenListScheme, total_tokens: int, seed: int, delta: float) -> float:
    sizes = _unit_sizes(total_tokens, strategy.unit_tokens)
    gen_order = strategy.generation_order(len(sizes))
    reading = generate_unit_order(scheme, sizes, gen_order, seed, delta)
    return scheme.z_score(reading)


@dataclass
class StrategyEval:
    degradation: float     # fraction of the watermark z removed (want high)
    residual_z: float
    base_z: float
    fidelity: float        # modeled meaning preservation (want >= gate)
    fidelity_ok: bool
    fitness: float


def fidelity_of(strategy: Strategy) -> float:
    if strategy.kind == "transcode":
        return strategy.translation_quality
    return _GRAN_FIDELITY.get(strategy.unit_tokens, 0.7) * _DISRUPTION.get(strategy.kind, 0.9)


def base_forward_z(scheme: GreenListScheme, total_tokens: int = 500, delta: float = 2.0,
                   n_eval: int = 4, seed: int = 0) -> float:
    """The full-watermark forward z (identity order). It does not depend on the unit size."""
    ident = Strategy(kind="identity")
    return statistics.mean(forward_z(ident, scheme, total_tokens, seed + i, delta) for i in range(n_eval))


def evaluate_strategy(
    strategy: Strategy,
    scheme: GreenListScheme,
    total_tokens: int = 500,
    delta: float = 2.0,
    n_eval: int = 4,
    gate: float = 0.7,
    seed: int = 0,
    base_z: float | None = None,
) -> StrategyEval:
    if base_z is None:
        base_z = base_forward_z(scheme, total_tokens, delta, n_eval, seed)
    if strategy.kind == "transcode":
        # a deterministic translate removes the whole English-key watermark
        residual_z = 0.0
    else:
        residual_z = statistics.mean(
            forward_z(strategy, scheme, total_tokens, seed + 100 + i, delta) for i in range(n_eval)
        )
    degradation = max(0.0, 1.0 - residual_z / base_z) if base_z > 1e-6 else 0.0
    fid = fidelity_of(strategy)
    fidelity_ok = fid >= gate
    fitness = degradation if fidelity_ok else -1.0 - (gate - fid)
    return StrategyEval(degradation, residual_z, base_z, fid, fidelity_ok, fitness)


@dataclass
class StrategyEvolutionResult:
    best: Strategy
    best_eval: StrategyEval
    history: list[float]
    ranked: list[tuple]  # (Strategy, StrategyEval) top few, for the report


def _random_strategy(rng: random.Random) -> Strategy:
    return Strategy(kind=rng.choice(ALL_KINDS), param=rng.choice([2, 3, 4, 6]),
                    unit_tokens=rng.choice(UNIT_TOKENS),
                    translation_quality=rng.choice([0.6, 0.7, 0.8, 0.9]))


def evolve_strategies(
    scheme: GreenListScheme,
    generations: int = 10,
    pop_size: int = 10,
    total_tokens: int = 500,
    delta: float = 2.0,
    n_eval: int = 4,
    gate: float = 0.7,
    seed: int = 0,
) -> StrategyEvolutionResult:
    """Evolve the bleach strategy population against the watermark and the meaning gate."""
    rng = random.Random(seed)
    # seed the first generation with one of each family, so the search covers them all
    population = [Strategy(kind=k, unit_tokens=12) for k in ALL_KINDS]
    population += [_random_strategy(rng) for _ in range(max(0, pop_size - len(population)))]
    best: Strategy | None = None
    best_eval: StrategyEval | None = None
    history: list[float] = []
    base_z = base_forward_z(scheme, total_tokens, delta, n_eval, seed)

    scored: list[tuple] = []
    for _ in range(generations):
        scored = [(s, evaluate_strategy(s, scheme, total_tokens, delta, n_eval, gate, seed, base_z=base_z))
                  for s in population]
        scored.sort(key=lambda pair: pair[1].fitness, reverse=True)
        history.append(scored[0][1].fitness)
        if best_eval is None or scored[0][1].fitness > best_eval.fitness:
            best, best_eval = scored[0]
        survivors = [s for s, _ in scored[: max(2, pop_size // 2)]]
        population = survivors + [
            rng.choice(survivors).mutate(rng) for _ in range(pop_size - len(survivors))
        ]

    # de-duplicate the ranked list by description for the report
    seen, ranked = set(), []
    for s, ev in sorted(scored, key=lambda p: p[1].fitness, reverse=True):
        d = s.describe()
        if d not in seen:
            seen.add(d)
            ranked.append((s, ev))
    return StrategyEvolutionResult(best=best, best_eval=best_eval, history=history, ranked=ranked[:6])
