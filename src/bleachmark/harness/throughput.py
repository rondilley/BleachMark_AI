"""Carrier-scan throughput benchmark (NFR-01, TC-14).

NFR-01 requires the deterministic carrier scan to sustain at least 1 MB/s on one
core. This measures it on typical (ASCII) text and on a worst-case all-non-ASCII
input, so the reported rate is honest about both ends.
"""

from __future__ import annotations

import time

from .. import detect_carriers

_ASCII_PARA = (
    "The quarterly report shows steady growth across every region we measured this "
    "year. Teams shipped features on schedule and customers responded well to the "
    "new pricing. "
)


def _ascii_text(target_bytes: int) -> str:
    reps = max(1, target_bytes // len(_ASCII_PARA.encode("utf-8")))
    return _ASCII_PARA * reps


def _non_ascii_text(target_bytes: int) -> str:
    # Cyrillic + Arabic + CJK: every character is non-ASCII, exercising the slow paths
    block = (
        "".join(chr(c) for c in range(0x0410, 0x0450)) + " "
        + "".join(chr(c) for c in range(0x0628, 0x0640)) + " "
        + "".join(chr(c) for c in range(0x4E00, 0x4E20)) + " "
    )
    reps = max(1, target_bytes // len(block.encode("utf-8")))
    return block * reps


def measure_once(text: str) -> dict:
    nbytes = len(text.encode("utf-8"))
    t0 = time.perf_counter()
    report = detect_carriers(text)
    dt = time.perf_counter() - t0
    return {
        "megabytes": round(nbytes / 1e6, 4),
        "seconds": round(dt, 4),
        "mb_per_s": round((nbytes / 1e6) / dt, 3) if dt > 0 else None,
        "findings": len(report.findings),
    }


def measure(target_mb: float = 2.0) -> dict:
    """Measure throughput on typical ASCII text and worst-case non-ASCII text."""
    target = int(target_mb * 1e6)
    ascii_run = measure_once(_ascii_text(target))
    non_ascii_run = measure_once(_non_ascii_text(target))
    return {
        "experiment": "carrier_scan_throughput",
        "criterion": "NFR-01 / TC-14 (>= 1 MB/s on one core)",
        "requirement_mb_per_s": 1.0,
        "typical_ascii": ascii_run,
        "worst_case_non_ascii": non_ascii_run,
        "meets_requirement": (
            ascii_run["mb_per_s"] >= 1.0 and non_ascii_run["mb_per_s"] >= 1.0
        ),
    }
