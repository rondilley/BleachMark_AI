"""Accelerator selection for the neural methods (FR-43, NFR-04).

The tool uses an NPU or a GPU when the host has one, and falls back to the CPU.
Detection is best-effort and cross-platform: it reads environment hints and probes
for optional libraries without a hard dependency.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass


@dataclass
class Accelerator:
    kind: str  # "npu", "cuda", "metal", or "cpu"
    detail: str


def select_accelerator() -> Accelerator:
    forced = os.environ.get("BLEACHMARK_ACCEL")
    if forced:
        return Accelerator(forced.lower(), "forced by BLEACHMARK_ACCEL")
    if os.environ.get("BLEACHMARK_NPU"):
        return Accelerator("npu", "env hint")
    if shutil.which("nvidia-smi"):
        return Accelerator("cuda", "nvidia-smi present")
    if sys.platform == "darwin":
        return Accelerator("metal", "apple platform")
    return Accelerator("cpu", "fallback, no accelerator found")
