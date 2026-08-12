"""Tests for host hardware detection (injected probes, no real GPU needed)."""

from bleachmark.runtime.hardware import (
    detect_hardware,
    parse_gpus,
    parse_cuda_version,
    GPU,
)


def test_parse_single_gpu():
    gpus = parse_gpus("NVIDIA GeForce RTX 5090, 32607, 29918, 596.49")
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 5090"
    assert gpus[0].vram_total_mb == 32607
    assert gpus[0].vram_free_mb == 29918
    assert gpus[0].driver == "596.49"


def test_parse_multiple_gpus_and_best():
    csv = "NVIDIA A100, 40536, 40000, 550.0\nNVIDIA RTX 3090, 24576, 24000, 550.0"
    gpus = parse_gpus(csv)
    assert len(gpus) == 2
    prof = detect_hardware(smi_query=csv, smi_header="CUDA Version: 12.4", cpu_count=8, ram_mb=64000)
    assert prof.best_gpu().vram_total_mb == 40536      # the larger card
    assert prof.total_vram_mb() == 40536 + 24576


def test_parse_cuda_version():
    assert parse_cuda_version("| NVIDIA-SMI 596.49  Driver Version: 596.49  CUDA Version: 13.2 |") == "13.2"
    assert parse_cuda_version("no cuda here") is None


def test_detect_hardware_with_injected_probes():
    prof = detect_hardware(
        smi_query="NVIDIA GeForce RTX 5090, 32607, 29918, 596.49",
        smi_header="CUDA Version: 13.2",
        cpu_count=20, ram_mb=262144,
    )
    s = prof.summary()
    assert s["cuda_version"] == "13.2"
    assert s["cpu_count"] == 20
    assert s["ram_mb"] == 262144
    assert s["gpu"]["name"] == "NVIDIA GeForce RTX 5090"
    assert s["total_vram_mb"] == 32607


def test_no_gpu_is_graceful():
    # an empty query stands for a host with no NVIDIA GPU (None means "detect for real")
    prof = detect_hardware(smi_query="", smi_header="", cpu_count=4, ram_mb=8000)
    assert prof.gpus == []
    assert prof.best_gpu() is None
    assert prof.total_vram_mb() == 0
    assert prof.summary()["gpu"] is None
