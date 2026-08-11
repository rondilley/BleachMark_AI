"""The evolution loop over prompt strategies and detectors.

A prompt genome shapes the generation (structural freedom k, sequence length, and
the number of stealing samples). A detector genome tunes the estimating detector.
Fitness is the detection separation between watermarked and control under the
current pair, plus a bonus for recovering the partition (the key). Over generations
the population evolves toward configurations that expose and recover the stego.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from .arena import EstimatingDetector, StructuralArena, partition_recovery


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


@dataclass
class PromptGenome:
    k: int = 4            # structural variants per slot (constraint tightness)
    n_slots: int = 60     # slots per generated sample (length -> signal)
    n_steal: int = 20     # watermarked samples used to steal the partition

    def mutate(self, rng: random.Random) -> "PromptGenome":
        return PromptGenome(
            k=_clamp(self.k + rng.choice([-1, 0, 1]), 2, 8),
            n_slots=_clamp(self.n_slots + rng.choice([-20, 0, 20]), 20, 160),
            n_steal=_clamp(self.n_steal + rng.choice([-8, 0, 8]), 6, 60),
        )


@dataclass
class DetectorGenome:
    margin: float = 0.15
    z_threshold: float = 3.0

    def mutate(self, rng: random.Random) -> "DetectorGenome":
        return DetectorGenome(
            margin=_clamp(self.margin + rng.choice([-0.05, 0.0, 0.05]), 0.02, 0.6),
            z_threshold=_clamp(self.z_threshold + rng.choice([-0.5, 0.0, 0.5]), 2.0, 5.0),
        )


@dataclass
class Individual:
    prompt: PromptGenome
    detector: DetectorGenome


@dataclass
class Evaluation:
    fitness: float
    separation: float
    recovery: float
    tpr: float
    fpr: float


def evaluate(ind: Individual, arena: StructuralArena, n_eval: int = 12, seed: int = 0) -> Evaluation:
    """Measure how well this (prompt, detector) pair exposes and steals the stego."""
    pg, dg = ind.prompt, ind.detector
    det = EstimatingDetector(margin=dg.margin, z_threshold=dg.z_threshold)
    table = arena.true_partition(pg.k, pg.n_slots)

    # 1) steal the partition from watermarked samples (the key-recovery step)
    steal = [arena.watermarked(pg.k, pg.n_slots, seed=1000 + i, table=table) for i in range(pg.n_steal)]
    est = det.estimate_partition(steal, pg.k, pg.n_slots)
    recovery = partition_recovery(est, table)

    # 2) detect held-out watermarked vs control with the estimated partition
    z_wm, z_ctrl, tp, fp = [], [], 0, 0
    for i in range(n_eval):
        wm = arena.watermarked(pg.k, pg.n_slots, seed=5000 + i, table=table)
        ct = arena.control(pg.k, pg.n_slots, seed=9000 + i)
        z_wm.append(det.z_score(wm, est))
        z_ctrl.append(det.z_score(ct, est))
        tp += 1 if det.detected(wm, est) else 0
        fp += 1 if det.detected(ct, est) else 0

    pooled = (statistics.pstdev(z_wm) + statistics.pstdev(z_ctrl)) / 2 or 1e-6
    separation = (statistics.mean(z_wm) - statistics.mean(z_ctrl)) / pooled  # d-prime
    tpr, fpr = tp / n_eval, fp / n_eval
    # fitness rewards clean separation and low false positives, plus key recovery
    fitness = separation + 0.5 * recovery - 2.0 * fpr
    return Evaluation(fitness, separation, recovery, tpr, fpr)


def random_individual(rng: random.Random) -> Individual:
    return Individual(
        PromptGenome(k=rng.randint(2, 8), n_slots=rng.choice([20, 40, 60, 80, 120]),
                     n_steal=rng.choice([6, 12, 20, 40])),
        DetectorGenome(margin=rng.choice([0.05, 0.15, 0.3, 0.5]),
                       z_threshold=rng.choice([2.0, 3.0, 4.0])),
    )


@dataclass
class EvolutionResult:
    best: Individual
    best_eval: Evaluation
    history: list[float]           # best fitness per generation
    mean_history: list[float]      # mean fitness per generation


def evolve(
    arena: StructuralArena,
    generations: int = 8,
    pop_size: int = 10,
    n_eval: int = 12,
    seed: int = 0,
) -> EvolutionResult:
    """Evolve the prompt and detector populations against the fixed embedder."""
    rng = random.Random(seed)
    population = [random_individual(rng) for _ in range(pop_size)]
    history: list[float] = []
    mean_history: list[float] = []
    best: Individual | None = None
    best_eval: Evaluation | None = None

    for _ in range(generations):
        scored = [(ind, evaluate(ind, arena, n_eval=n_eval)) for ind in population]
        scored.sort(key=lambda pair: pair[1].fitness, reverse=True)
        history.append(scored[0][1].fitness)
        mean_history.append(statistics.mean(e.fitness for _, e in scored))
        if best_eval is None or scored[0][1].fitness > best_eval.fitness:
            best, best_eval = scored[0]

        # keep the top half, refill by mutating survivors
        survivors = [ind for ind, _ in scored[: max(2, pop_size // 2)]]
        children: list[Individual] = []
        while len(survivors) + len(children) < pop_size:
            parent = rng.choice(survivors)
            children.append(Individual(parent.prompt.mutate(rng), parent.detector.mutate(rng)))
        population = survivors + children

    return EvolutionResult(best, best_eval, history, mean_history)
