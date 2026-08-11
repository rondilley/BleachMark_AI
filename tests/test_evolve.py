"""Tests for the adversarial training and evolution subsystem.

Validates that the detector steals the partition (recovers the key), that recovery
improves with more samples, that evolution improves fitness over generations, and
that the evolved configuration beats a random one.
"""

import random
import statistics

from bleachmark.evolve.arena import StructuralArena, EstimatingDetector, partition_recovery
from bleachmark.evolve.evolution import (
    Individual,
    PromptGenome,
    DetectorGenome,
    evaluate,
    evolve,
    random_individual,
)


def _arena():
    return StructuralArena(key="stego-key", gamma=0.4, delta=2.0)


def test_detector_steals_partition():
    arena = _arena()
    k, n_slots = 4, 80
    table = arena.true_partition(k, n_slots)
    det = EstimatingDetector(margin=0.15)
    samples = [arena.watermarked(k, n_slots, seed=i, table=table) for i in range(40)]
    est = det.estimate_partition(samples, k, n_slots)
    # recovering the green partition is recovering the key for this modality
    assert partition_recovery(est, table) >= 0.75


def test_recovery_improves_with_more_samples():
    arena = _arena()
    k, n_slots = 4, 80
    table = arena.true_partition(k, n_slots)
    det = EstimatingDetector(margin=0.15)

    def recov(n):
        samples = [arena.watermarked(k, n_slots, seed=i, table=table) for i in range(n)]
        return partition_recovery(det.estimate_partition(samples, k, n_slots), table)

    assert recov(40) > recov(4)


def test_estimated_detector_separates_watermark_from_control():
    arena = _arena()
    k, n_slots = 4, 80
    table = arena.true_partition(k, n_slots)
    det = EstimatingDetector(margin=0.15, z_threshold=3.0)
    steal = [arena.watermarked(k, n_slots, seed=i, table=table) for i in range(30)]
    est = det.estimate_partition(steal, k, n_slots)
    wm = arena.watermarked(k, n_slots, seed=999, table=table)
    ctrl = arena.control(k, n_slots, seed=999)
    assert det.z_score(wm, est) > det.z_score(ctrl, est)
    assert det.detected(wm, est)
    assert not det.detected(ctrl, est)


def test_evolution_improves_fitness():
    arena = _arena()
    result = evolve(arena, generations=6, pop_size=8, n_eval=10, seed=1)
    # the best fitness found is at least the first generation's best, and improves
    assert result.best_eval.fitness >= result.history[0]
    assert result.best_eval.fitness > 1.0  # a clear separation was found


def test_evolved_beats_random_baseline():
    arena = _arena()
    result = evolve(arena, generations=6, pop_size=8, n_eval=10, seed=2)
    rng = random.Random(123)
    random_fitness = statistics.mean(
        evaluate(random_individual(rng), arena, n_eval=10).fitness for _ in range(8)
    )
    assert result.best_eval.fitness > random_fitness


def test_evolved_config_recovers_key():
    arena = _arena()
    result = evolve(arena, generations=6, pop_size=8, n_eval=10, seed=3)
    ev = evaluate(result.best, arena, n_eval=12)
    assert ev.recovery >= 0.7
