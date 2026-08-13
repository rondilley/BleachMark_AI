"""Deploy and run a local GGUF model with llama.cpp (FR-43, NFR-03).

This is the self-contained local path: detect the hardware, select a model for the function,
download the GGUF from Hugging Face, and run it in-process with llama.cpp on the GPU. The two
heavy libraries (`llama-cpp-python` and `huggingface_hub`) sit behind an optional install group,
so the core stays light. Each entry gives a clear message when a library is absent.

The other local path is a running engine that speaks the OpenAI API (see
`runtime.providers.make_model("local", ...)` and `BLEACHMARK_LOCAL_URL`). That path needs no
heavy library in this process, because the engine holds the model.
"""

from __future__ import annotations

from .hardware import detect_hardware
from .models import ModelSpec, select_for


def deps_status() -> dict:
    """Report which optional local-inference libraries are present."""
    status = {}
    for mod in ("llama_cpp", "huggingface_hub"):
        try:
            __import__(mod)
            status[mod] = True
        except Exception:
            status[mod] = False
    return status


def ensure_model(spec: ModelSpec, cache_dir: str | None = None) -> str:
    """Download the GGUF for a model spec from Hugging Face and return the local path."""
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:  # optional dependency
        raise RuntimeError(
            "huggingface_hub is not installed; install the optional group "
            "(pip install 'bleachmark[local]')"
        ) from exc
    return hf_hub_download(repo_id=spec.hf_repo, filename=spec.hf_file, cache_dir=cache_dir)


def make_local_llama(model_path: str, n_gpu_layers: int = -1, n_ctx: int = 4096,
                     temperature: float = 1.0, max_tokens: int = 1600):
    """Build a callable(prompt)->text backed by an in-process llama.cpp model.

    n_gpu_layers = -1 puts every layer on the GPU; the caller can lower it when the model does
    not fit the video memory.
    """
    try:
        from llama_cpp import Llama
    except Exception as exc:  # optional dependency
        raise RuntimeError(
            "llama-cpp-python is not installed; install the optional group "
            "(pip install 'bleachmark[local]')"
        ) from exc
    llm = Llama(model_path=model_path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx, verbose=False)

    def call(prompt: str) -> str:
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return out["choices"][0]["message"]["content"] or ""

    return call


def deploy(function: str, cache_dir: str | None = None, n_ctx: int = 4096,
           local_path: str | None = None, **gen):
    """Detect the hardware, select a model for the function, download it, and load it.

    Returns (callable, ModelSpec | None, model_path). The registry path downloads several
    gigabytes on the first call, so it is not run by the test suite. When local_path points
    at a GGUF already on disk, the download and the registry selection are skipped, so an
    air-gapped host (or a test) can run a model it already has.
    """
    if local_path is not None:
        fn = make_local_llama(local_path, n_gpu_layers=-1, n_ctx=n_ctx, **gen)
        return fn, None, local_path
    profile = detect_hardware()
    best = profile.best_gpu()
    budget = best.vram_total_mb if best else 0
    sel = select_for(function, budget)
    if sel.model is None:
        raise RuntimeError(f"no model for function '{function}'")
    path = ensure_model(sel.model, cache_dir=cache_dir)
    n_gpu_layers = -1 if sel.fits else 0   # spill to the CPU when it does not fit the GPU
    fn = make_local_llama(path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx, **gen)
    return fn, sel.model, path
