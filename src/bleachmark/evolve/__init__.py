"""Adversarial training and evolution for watermark exposure and recovery.

The loop fixes a known stego modality (the embedder) and evolves two things against
it:

- Prompt and constraint strategies that shape the generation, so the stego signal
  is more and more exposed (Ron's constrain-to-expose idea, made adaptive).
- Detectors that get better at seeing the signal and at stealing the partition,
  which for the green-list modality is the key (watermark stealing).

It runs in the reference domain where the ground truth is known, so "better
detection" and "key recovery" are measured, not asserted. The evolved prompt
strategy is a constraint template that then transfers to a real model.
"""

from .arena import StructuralArena, EstimatingDetector
from .evolution import PromptGenome, DetectorGenome, evolve, evaluate, random_individual
from .realbridge import RealPromptGenome, ModelCache, real_fitness, evolve_real
from .coevolve import (
    CodeModality,
    DefensePrompt,
    oracle_capacity,
    detection_eval,
    coevolve,
    CoEvolutionResult,
)
from .bleachevolve import (
    BleachArena,
    BleachPolicy,
    evaluate_bleach,
    evolve_bleach,
    BleachEval,
    BleachResult,
)

__all__ = [
    "StructuralArena",
    "EstimatingDetector",
    "PromptGenome",
    "DetectorGenome",
    "evolve",
    "evaluate",
    "random_individual",
    # the bridge to a live model
    "RealPromptGenome",
    "ModelCache",
    "real_fitness",
    "evolve_real",
    # the joint defense/detection co-evolution (the code tranche)
    "CodeModality",
    "DefensePrompt",
    "oracle_capacity",
    "detection_eval",
    "coevolve",
    "CoEvolutionResult",
    # the bleach co-evolution (watermark removal with a meaning gate)
    "BleachArena",
    "BleachPolicy",
    "evaluate_bleach",
    "evolve_bleach",
    "BleachEval",
    "BleachResult",
]
