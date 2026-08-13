"""Joint defense/detection co-evolution for the code tranche (FR-56 to FR-60).

The first tranche co-evolves two adversaries against a known code stego modality:

- The DEFENSE: a constraint prompt that makes it hard for the model to insert a
  watermark. Each lock (fixed names, fixed structure, no comments, iterative only)
  removes a class of free slots where a green-list watermark could hide. Fewer free
  slots means a smaller watermark channel. The defense objective is to minimize the
  channel capacity that even an ORACLE (a detector that holds the true key) could
  use, so the mark cannot be embedded at all.

- The DETECTION: a keyless estimating detector that must recover the partition (the
  key, for this modality) and catch the residual mark that survives the constraint.

The two objectives are in tension. The defense shrinks the channel, which starves
the detector. So the detector must adapt to a smaller and smaller residual. This is
honest co-evolution, measured against ground truth in the arena.

The meaning floor is the hard limit. A prompt cannot remove every free slot, because
the task still has to be solved correctly. The floor models the minimum freedom the
task needs. Over-constrain past the floor and the meaning gate rejects the output.
So the defense drives the channel down toward the floor, not to zero. This is the
Christ-Gunn-Zamir wall in miniature: the channel shrinks, it does not vanish, and
what remains is where detection must work.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

from .arena import StructuralArena, EstimatingDetector, partition_recovery

_LOCK_REDUCTION = {
    "lock_names": 0.30,       # fixed identifiers remove the naming slots
    "lock_structure": 0.35,   # a prescribed shape removes the construct slots
    "no_comments": 0.15,      # no comments remove the comment channel
    "iterative_only": 0.10,   # no recursion removes the recursion-variant slots
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _dprime(a: list[float], b: list[float]) -> float:
    pooled = (statistics.pstdev(a) + statistics.pstdev(b)) / 2 or 1e-6
    return (statistics.mean(a) - statistics.mean(b)) / pooled


@dataclass
class CodeModality:
    """A ground-truth arena for one code language.

    base_slots is the intrinsic freedom before any constraint. meaning_floor is the
    minimum free slots the task needs to stay correct. gamma and delta are the
    green-list watermark parameters (the same Kirchenbauer mechanism as elsewhere).
    """

    key: str
    lang: str = "python"
    base_slots: int = 100
    meaning_floor: int = 18
    gamma: float = 0.4
    delta: float = 2.0

    def arena(self) -> StructuralArena:
        return StructuralArena(key=self.key, gamma=self.gamma, delta=self.delta)


@dataclass
class DefensePrompt:
    """A constraint prompt: each active lock removes a class of free slots."""

    lock_names: bool = False
    lock_structure: bool = False
    no_comments: bool = False
    iterative_only: bool = False
    k: int = 5  # residual freedom per slot the model still has

    def reduction(self) -> float:
        return sum(frac for name, frac in _LOCK_REDUCTION.items() if getattr(self, name))

    def open_slots(self, m: CodeModality) -> int:
        raw = m.base_slots * (1.0 - min(0.95, self.reduction()))
        return max(1, round(raw))

    def meaning_penalty(self, m: CodeModality) -> float:
        """Damage from over-constraint: nonzero only below the meaning floor."""
        deficit = m.meaning_floor - self.open_slots(m)
        return max(0.0, deficit) / m.meaning_floor

    def meaning_ok(self, m: CodeModality) -> bool:
        return self.open_slots(m) >= m.meaning_floor

    def mutate(self, rng: random.Random) -> "DefensePrompt":
        g = DefensePrompt(**self.__dict__)
        gene = rng.choice(["lock_names", "lock_structure", "no_comments", "iterative_only", "k"])
        if gene == "k":
            g.k = _clamp(self.k + rng.choice([-1, 0, 1]), 2, 8)
        else:
            setattr(g, gene, not getattr(g, gene))
        return g

    def describe(self, lang: str = "python") -> str:
        """Render the genome as a real constraint prompt fragment that transfers."""
        parts: list[str] = []
        if self.lock_names:
            sig = "int f(int x)" if lang == "c" else "def f(x)"
            parts.append(f"Use exactly this signature: {sig}. Name every local a, b, c.")
        if self.lock_structure:
            parts.append(
                "Use one public entry and helpers named h0, h1, h2. "
                "Helpers are allowed so the module can exceed 400 words."
            )
        if self.iterative_only:
            parts.append("Iterative only, no recursion.")
        if self.no_comments:
            parts.append("No comments, no docstring, no prose.")
        from ..detect.length import length_requirement

        parts.append(length_requirement())
        parts.append("Return only the code.")
        return " ".join(parts)


@dataclass
class DetectorGenome:
    margin: float = 0.15
    z_threshold: float = 3.0

    def mutate(self, rng: random.Random) -> "DetectorGenome":
        return DetectorGenome(
            margin=_clamp(self.margin + rng.choice([-0.05, 0.0, 0.05]), 0.02, 0.6),
            z_threshold=_clamp(self.z_threshold + rng.choice([-0.5, 0.0, 0.5]), 2.0, 5.0),
        )


def oracle_capacity(defense: DefensePrompt, m: CodeModality, n_eval: int = 16, seed: int = 0) -> float:
    """Channel capacity: the separation an ORACLE with the true key could reach.

    This is the ceiling on any detector. The defense minimizes it: a lower capacity
    means the watermark cannot be inserted with signal, no matter the detector.
    """
    arena = m.arena()
    slots, k = defense.open_slots(m), defense.k
    table = arena.true_partition(k, slots)
    det = EstimatingDetector()
    z_wm, z_ctrl = [], []
    for i in range(n_eval):
        wm = arena.watermarked(k, slots, seed=seed + 5000 + i, table=table)
        ct = arena.control(k, slots, seed=seed + 9000 + i)
        z_wm.append(det.z_score(wm, table))     # score with the TRUE partition
        z_ctrl.append(det.z_score(ct, table))
    return _dprime(z_wm, z_ctrl)


@dataclass
class DetectionEval:
    separation: float
    recovery: float
    tpr: float
    fpr: float
    fitness: float


def detection_eval(
    defense: DefensePrompt,
    genome: DetectorGenome,
    m: CodeModality,
    n_steal: int = 24,
    n_eval: int = 16,
    seed: int = 0,
) -> DetectionEval:
    """Keyless detection against a fixed defense prompt: steal, then separate."""
    arena = m.arena()
    slots, k = defense.open_slots(m), defense.k
    table = arena.true_partition(k, slots)
    det = EstimatingDetector(margin=genome.margin, z_threshold=genome.z_threshold)

    steal = [arena.watermarked(k, slots, seed=seed + 1000 + i, table=table) for i in range(n_steal)]
    est = det.estimate_partition(steal, k, slots)
    recovery = partition_recovery(est, table)

    z_wm, z_ctrl, tp, fp = [], [], 0, 0
    for i in range(n_eval):
        wm = arena.watermarked(k, slots, seed=seed + 5000 + i, table=table)
        ct = arena.control(k, slots, seed=seed + 9000 + i)
        z_wm.append(det.z_score(wm, est))
        z_ctrl.append(det.z_score(ct, est))
        tp += 1 if det.detected(wm, est) else 0
        fp += 1 if det.detected(ct, est) else 0
    separation = _dprime(z_wm, z_ctrl)
    tpr, fpr = tp / n_eval, fp / n_eval
    fitness = separation + 0.5 * recovery - 2.0 * fpr
    return DetectionEval(separation, recovery, tpr, fpr, fitness)


@dataclass
class Round:
    generation: int
    defense: DefensePrompt
    capacity: float           # oracle channel capacity (want down)
    meaning_ok: bool
    open_slots: int
    detector: DetectorGenome
    detection: DetectionEval  # keyless detection against the champion defense


@dataclass
class CoEvolutionResult:
    modality: CodeModality
    baseline_capacity: float      # capacity with no defense (all locks off)
    rounds: list[Round]
    best_defense: DefensePrompt
    best_detector: DetectorGenome
    capacity_curve: list[float] = field(default_factory=list)
    separation_curve: list[float] = field(default_factory=list)

    @property
    def final_capacity(self) -> float:
        return self.rounds[-1].capacity

    @property
    def capacity_reduction(self) -> float:
        """Fraction of the undefended channel the evolved defense removed."""
        if self.baseline_capacity <= 0:
            return 0.0
        return 1.0 - self.final_capacity / self.baseline_capacity


def _defense_fitness(defense: DefensePrompt, m: CodeModality, n_eval: int, seed: int) -> float:
    """Minimize the oracle capacity, but never past the meaning floor.

    The floor is a hard gate. A prompt that over-constrains breaks correctness, so it
    is not a valid defense at all, however small its channel. An infeasible prompt
    always loses to any feasible one, yet is still ranked by its deficit so mutation
    can climb back to feasibility.
    """
    cap = oracle_capacity(defense, m, n_eval=n_eval, seed=seed)
    if not defense.meaning_ok(m):
        return -1e6 - defense.meaning_penalty(m)
    return -cap


def coevolve(
    m: CodeModality,
    rounds: int = 8,
    def_pop: int = 8,
    det_pop: int = 8,
    n_eval: int = 16,
    seed: int = 0,
) -> CoEvolutionResult:
    """Co-evolve the defense prompt and the keyless detector against the modality."""
    rng = random.Random(seed)
    baseline = oracle_capacity(DefensePrompt(), m, n_eval=n_eval, seed=seed)

    defenses = [DefensePrompt().mutate(rng) for _ in range(def_pop)]
    detectors = [
        DetectorGenome(rng.choice([0.05, 0.15, 0.3]), rng.choice([2.0, 3.0, 4.0]))
        for _ in range(det_pop)
    ]

    history: list[Round] = []
    best_defense: DefensePrompt | None = None
    best_defense_score = -1e9
    best_detector: DetectorGenome | None = None
    best_detection_fit = -1e9

    for gen in range(rounds):
        # 1) evolve the defense against the oracle channel capacity
        d_scored = sorted(
            ((d, _defense_fitness(d, m, n_eval, seed)) for d in defenses),
            key=lambda p: p[1],
            reverse=True,
        )
        champion_def = d_scored[0][0]
        if d_scored[0][1] > best_defense_score:
            best_defense, best_defense_score = d_scored[0]

        # 2) evolve the detector against the champion defense (the tight residual)
        t_scored = sorted(
            ((t, detection_eval(champion_def, t, m, n_eval=n_eval, seed=seed)) for t in detectors),
            key=lambda p: p[1].fitness,
            reverse=True,
        )
        champion_det, champion_det_eval = t_scored[0]
        if champion_det_eval.fitness > best_detection_fit:
            best_detector, best_detection_fit = champion_det, champion_det_eval.fitness

        history.append(
            Round(
                generation=gen,
                defense=champion_def,
                capacity=oracle_capacity(champion_def, m, n_eval=n_eval, seed=seed),
                meaning_ok=champion_def.meaning_ok(m),
                open_slots=champion_def.open_slots(m),
                detector=champion_det,
                detection=champion_det_eval,
            )
        )

        # 3) reproduce both populations by truncation and mutation
        def_survivors = [d for d, _ in d_scored[: max(2, def_pop // 2)]]
        defenses = def_survivors + [
            rng.choice(def_survivors).mutate(rng)
            for _ in range(def_pop - len(def_survivors))
        ]
        det_survivors = [t for t, _ in t_scored[: max(2, det_pop // 2)]]
        detectors = det_survivors + [
            rng.choice(det_survivors).mutate(rng)
            for _ in range(det_pop - len(det_survivors))
        ]

    return CoEvolutionResult(
        modality=m,
        baseline_capacity=baseline,
        rounds=history,
        best_defense=best_defense,
        best_detector=best_detector,
        capacity_curve=[r.capacity for r in history],
        separation_curve=[r.detection.separation for r in history],
    )
