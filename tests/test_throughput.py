"""Carrier-scan throughput regression gate (NFR-01, TC-14).

The requirement is 1 MB/s on one core. The dev-host headroom is large (about 8x on
ASCII, 2x on all-non-ASCII), so the floor guards against a real regression without
flaking on a slower machine.
"""

from bleachmark.harness.throughput import measure, measure_once, _ascii_text


def test_typical_throughput_meets_requirement():
    run = measure_once(_ascii_text(2_000_000))
    assert run["mb_per_s"] >= 1.0, f"typical throughput {run['mb_per_s']} MB/s below 1 MB/s"


def test_measure_reports_both_regimes_and_meets_requirement():
    result = measure(target_mb=1.0)
    assert result["typical_ascii"]["mb_per_s"] >= 1.0
    assert result["worst_case_non_ascii"]["mb_per_s"] >= 1.0
    assert result["meets_requirement"] is True
