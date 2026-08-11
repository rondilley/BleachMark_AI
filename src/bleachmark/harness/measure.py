"""Attack the reference samples and measure the rates (FR-44, TC-22).

Every number here comes from a real detection run over generated watermarked and
control samples, so it is validation, not a wiring check (SUCCESS_CRITERIA 4).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from ..detect.keyed.greenlist import GreenListScheme
from . import generators


@dataclass
class DetectionRates:
    method: str
    true_positive_rate: float
    false_positive_rate: float
    samples: int


@dataclass
class BleachRates:
    method: str
    fraction_changed: float
    detected_before: float
    detected_after: float
    bleach_success_rate: float
    samples: int


def measure_greenlist_detection(
    scheme: GreenListScheme,
    samples: int = 24,
    length: int = 180,
    delta: float = 2.0,
    z_threshold: float = 4.0,
) -> DetectionRates:
    tp = 0
    fp = 0
    for s in range(samples):
        wm = generators.watermarked_sequence(scheme, length, seed=s, delta=delta)
        ctrl = generators.control_sequence(scheme.vocab, length, seed=1000 + s)
        if scheme.z_score(wm) >= z_threshold:
            tp += 1
        if scheme.z_score(ctrl) >= z_threshold:
            fp += 1
    return DetectionRates("greenlist", tp / samples, fp / samples, samples)


def measure_greenlist_bleach(
    scheme: GreenListScheme,
    samples: int = 24,
    length: int = 180,
    delta: float = 2.0,
    fraction: float = 0.3,
    z_threshold: float = 4.0,
) -> BleachRates:
    before = 0
    after = 0
    bleached = 0
    for s in range(samples):
        wm = generators.watermarked_sequence(scheme, length, seed=s, delta=delta)
        was = scheme.z_score(wm) >= z_threshold
        attacked = generators.substitution_attack(wm, scheme.vocab, fraction, seed=2000 + s)
        now = scheme.z_score(attacked) >= z_threshold
        before += 1 if was else 0
        after += 1 if now else 0
        if was and not now:
            bleached += 1
    return BleachRates(
        "greenlist", fraction, before / samples, after / samples,
        bleached / max(1, before), samples,
    )


def run_default_harness() -> dict:
    """A small default run over the green-list reference scheme.

    Detection uses a strong watermark (delta 2.0). The bleach demonstration uses a
    lighter watermark (delta 1.0) with a 50 percent substitution, which matches the
    research: a strong watermark needs more than a quarter of the tokens changed.
    """
    scheme = GreenListScheme(key="harness-key", vocab=generators.make_vocab(250), gamma=0.25)
    det = measure_greenlist_detection(scheme, delta=2.0)
    bl = measure_greenlist_bleach(scheme, delta=1.0, fraction=0.5)
    return {"detection": asdict(det), "bleach": asdict(bl)}
