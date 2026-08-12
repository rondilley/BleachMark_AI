"""Tests for the local llama.cpp deploy plumbing (no download, no heavy load)."""

import pytest

from bleachmark.runtime.local_llama import deps_status, deploy


def test_deps_status_reports_both_libraries():
    s = deps_status()
    assert set(s) == {"llama_cpp", "huggingface_hub"}
    assert all(isinstance(v, bool) for v in s.values())


def test_deploy_rejects_an_unknown_function():
    # this fails at selection, before any download, so it is safe to run
    with pytest.raises(RuntimeError) as exc:
        deploy("not-a-function")
    assert "no model" in str(exc.value)
