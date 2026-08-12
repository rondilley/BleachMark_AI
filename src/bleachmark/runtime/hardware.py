"""Host hardware detection for local inference (FR-43, NFR-04).

The tool detects the local hardware, so it can select a model that fits and pick a device.
Detection is best-effort and dependency-free: it parses `nvidia-smi` for the GPU and the
video memory, and it uses the standard library (and `psutil` when present) for the CPU and
the RAM. Every probe is injectable, so the tests do not need a real GPU.

The detection does not assume the stated hardware. It reports what it finds. On the build
host it found an RTX 5090 with 32 GB of video memory, not the RTX 5070 the operator named,
which is the point: the tool measures, it does not trust the label.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

from .accel import select_accelerator


@dataclass
class GPU:
    name: str
    vram_total_mb: int
    vram_free_mb: int
    driver: str


@dataclass
class HardwareProfile:
    gpus: list[GPU] = field(default_factory=list)
    cuda_version: str | None = None
    cpu_count: int = 1
    ram_mb: int = 0
    accelerator: str = "cpu"

    def total_vram_mb(self) -> int:
        return sum(g.vram_total_mb for g in self.gpus)

    def best_gpu(self) -> GPU | None:
        return max(self.gpus, key=lambda g: g.vram_total_mb, default=None)

    def summary(self) -> dict:
        best = self.best_gpu()
        return {
            "accelerator": self.accelerator,
            "cuda_version": self.cuda_version,
            "cpu_count": self.cpu_count,
            "ram_mb": self.ram_mb,
            "gpu": None if best is None else {
                "name": best.name, "vram_total_mb": best.vram_total_mb,
                "vram_free_mb": best.vram_free_mb, "driver": best.driver,
            },
            "gpu_count": len(self.gpus),
            "total_vram_mb": self.total_vram_mb(),
        }


def _run_smi_query() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def _run_smi_header() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def parse_gpus(csv_text: str | None) -> list[GPU]:
    """Parse the nvidia-smi CSV query into a list of GPUs."""
    gpus: list[GPU] = []
    for line in (csv_text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, total, free, driver = parts[0], parts[1], parts[2], parts[3]
        try:
            gpus.append(GPU(name=name, vram_total_mb=int(float(total)),
                            vram_free_mb=int(float(free)), driver=driver))
        except ValueError:
            continue
    return gpus


def parse_cuda_version(header_text: str | None) -> str | None:
    for line in (header_text or "").splitlines():
        if "CUDA Version" in line:
            after = line.split("CUDA Version:", 1)[1]
            token = after.strip().split()[0].strip("|").strip()
            return token or None
    return None


def _detect_ram_mb() -> int:
    try:
        import psutil  # optional, present on the build host
        return int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        pass
    try:  # POSIX fallback
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024))
    except Exception:
        return 0


def detect_hardware(smi_query=None, smi_header=None, cpu_count=None, ram_mb=None) -> HardwareProfile:
    """Detect the host GPU(s), CUDA, CPU, and RAM. Every probe is injectable for tests."""
    query = smi_query if smi_query is not None else _run_smi_query()
    header = smi_header if smi_header is not None else _run_smi_header()
    gpus = parse_gpus(query)
    return HardwareProfile(
        gpus=gpus,
        cuda_version=parse_cuda_version(header),
        cpu_count=cpu_count if cpu_count is not None else (os.cpu_count() or 1),
        ram_mb=ram_mb if ram_mb is not None else _detect_ram_mb(),
        accelerator=select_accelerator().kind,
    )
