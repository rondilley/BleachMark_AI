"""In-process llama.cpp local inference (FR-43, NFR-03).

The wiring test always runs with a stubbed loader. The real generation test needs a
GGUF on disk and the optional deps, so it is gated behind BLEACHMARK_TEST_GGUF to keep
the normal suite fast. The measured end-to-end run is recorded in
docs/results/2026-08-12_local_inference.json.
"""

import os

import pytest

import bleachmark.runtime.local_llama as local_llama
from bleachmark.runtime.local_llama import deploy, deps_status

_GGUF = os.environ.get("BLEACHMARK_TEST_GGUF")


def test_deploy_local_path_skips_registry(monkeypatch):
    # local_path must skip hardware detection, selection, and download entirely
    monkeypatch.setattr(local_llama, "make_local_llama",
                        lambda path, **k: (lambda prompt: f"echo:{prompt}"))
    fn, spec, path = deploy("reference", local_path="/some/model.gguf")
    assert fn("hi") == "echo:hi"
    assert spec is None
    assert path == "/some/model.gguf"


@pytest.mark.skipif(
    not (_GGUF and os.path.exists(_GGUF)),
    reason="set BLEACHMARK_TEST_GGUF to a local GGUF to run the in-process generation test",
)
def test_in_process_generation_real():
    deps = deps_status()
    if not (deps["llama_cpp"] and deps["huggingface_hub"]):
        pytest.skip("optional local-inference deps not installed")
    fn, spec, path = deploy("paraphrase", local_path=_GGUF, n_ctx=1024, max_tokens=24)
    out = fn("Reply with one short sentence.")
    assert isinstance(out, str) and len(out.strip()) > 0
    assert spec is None and path == _GGUF
