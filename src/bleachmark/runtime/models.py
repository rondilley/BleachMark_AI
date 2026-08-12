"""Hardware-aware model registry and selection (FR-43, NFR-03, NFR-04).

The tool picks a local model for the function it runs and the video memory it has. The
registry holds a small set of known GGUF models on Hugging Face, with the function each one
suits and an estimate of the video memory it needs. The selection returns the largest model
that fits the budget, or the smallest one with a note when none fits.

The video-memory estimate is a Q4 rule of thumb, about 0.62 GB for each billion parameters,
plus a fixed overhead for the context and the runtime. It is an estimate, not an exact
measure, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass

# functions the tool runs a local model for
REFERENCE = "reference"       # unwatermarked generation for a calibration baseline
PARAPHRASE = "paraphrase"     # a paraphrase bleach
NEURAL = "neural_detect"      # a small neural detector


@dataclass(frozen=True)
class ModelSpec:
    name: str
    params_b: float
    quant: str
    hf_repo: str
    hf_file: str
    functions: tuple

    def vram_mb(self, context: int = 4096) -> int:
        """An estimate of the video memory the model needs at a Q4 quant."""
        weights = self.params_b * 620.0            # ~0.62 GB per billion params at Q4
        overhead = 1500.0 + context * 0.10         # runtime plus a rough KV-cache term
        return int(weights + overhead)


REGISTRY: list[ModelSpec] = [
    ModelSpec("Llama-3.3-70B-Instruct", 70.0, "Q4_K_M",
              "unsloth/Llama-3.3-70B-Instruct-GGUF", "Llama-3.3-70B-Instruct-Q4_K_M.gguf",
              (REFERENCE,)),
    ModelSpec("Qwen2.5-32B-Instruct", 32.0, "Q4_K_M",
              "bartowski/Qwen2.5-32B-Instruct-GGUF", "Qwen2.5-32B-Instruct-Q4_K_M.gguf",
              (REFERENCE, PARAPHRASE)),
    ModelSpec("Qwen2.5-14B-Instruct", 14.0, "Q4_K_M",
              "bartowski/Qwen2.5-14B-Instruct-GGUF", "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
              (REFERENCE, PARAPHRASE)),
    ModelSpec("Llama-3.1-8B-Instruct", 8.0, "Q4_K_M",
              "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF", "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
              (REFERENCE, PARAPHRASE, NEURAL)),
    ModelSpec("Qwen2.5-3B-Instruct", 3.0, "Q4_K_M",
              "bartowski/Qwen2.5-3B-Instruct-GGUF", "Qwen2.5-3B-Instruct-Q4_K_M.gguf",
              (NEURAL,)),
]


@dataclass
class Selection:
    function: str
    model: ModelSpec | None
    fits: bool
    vram_budget_mb: int
    note: str


def candidates_for(function: str) -> list[ModelSpec]:
    return [m for m in REGISTRY if function in m.functions]


def select_for(function: str, vram_mb: int) -> Selection:
    """Pick the largest model for the function that fits the video-memory budget."""
    cands = candidates_for(function)
    if not cands:
        return Selection(function, None, False, vram_mb, "no model for this function")
    fitting = [m for m in cands if m.vram_mb() <= vram_mb]
    if fitting:
        best = max(fitting, key=lambda m: m.params_b)
        return Selection(function, best, True, vram_mb,
                         f"fits the {vram_mb} MB budget (needs about {best.vram_mb()} MB)")
    smallest = min(cands, key=lambda m: m.params_b)
    return Selection(function, smallest, False, vram_mb,
                     f"none fits {vram_mb} MB; the smallest needs about {smallest.vram_mb()} MB "
                     "(use a remote local engine, or a smaller quant)")


def recommend(vram_mb: int) -> dict:
    """A per-function selection for a video-memory budget."""
    return {fn: select_for(fn, vram_mb) for fn in (REFERENCE, PARAPHRASE, NEURAL)}
