"""Cross-check against Hugging Face Transformers SynthID-Text (FR-19, TC-06).

Google's production implementation lives in Transformers v4.46+
(SynthIDTextWatermarkLogitsProcessor). This module uses that official g-value
function. It does not download a language model. It samples from uniform logits
after the official processor, then scores the same sequences with the official
mean g-value and with the tool's own simplified scheme.

An honest result is expected: the two g-functions are not the same, so each
detector fires on its own watermark and not on the other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch

from .synthid import SynthIDScheme
from ...harness.generators import control_sequence, make_vocab

OFFICIAL_KEYS = [654, 400, 836, 123, 340, 443, 597, 160, 57]
NGRAM_LEN = 5
VOCAB_SIZE = 256
LENGTH = 240
THRESHOLD = 4.0


def _official_processor(device: str = "cpu"):
    from transformers import SynthIDTextWatermarkLogitsProcessor

    return SynthIDTextWatermarkLogitsProcessor(
        ngram_len=NGRAM_LEN,
        keys=OFFICIAL_KEYS,
        sampling_table_size=65536,
        sampling_table_seed=0,
        context_history_size=1024,
        device=torch.device(device),
    )


def official_generate(length: int, seed: int, device: str = "cpu") -> list[int]:
    """Sample token ids from uniform logits after the official processor."""
    torch.manual_seed(seed)
    proc = _official_processor(device)
    ids = torch.zeros((1, 1), dtype=torch.long, device=device)
    for _ in range(length):
        scores = torch.zeros((1, VOCAB_SIZE), device=device)
        scores = proc(ids, scores)
        nxt = torch.multinomial(torch.softmax(scores, dim=-1), 1)
        ids = torch.cat([ids, nxt], dim=1)
    return ids[0, 1:].tolist()


def official_mean_g(token_ids: list[int], device: str = "cpu") -> float:
    """Official mean g-value over the token-id sequence."""
    proc = _official_processor(device)
    ids = torch.tensor([token_ids], dtype=torch.long, device=device)
    g = proc.compute_g_values(ids)
    return float(g.float().mean().item())


def official_z(token_ids: list[int], device: str = "cpu") -> float:
    """z of official mean g against null mean 0.5, variance 1/12 per token."""
    n = max(1, len(token_ids))
    mean = official_mean_g(token_ids, device)
    se = math.sqrt((1 / 12) / n)
    return (mean - 0.5) / se


def ours_on_ids(token_ids: list[int], key: str) -> float:
    vocab = [str(i) for i in range(VOCAB_SIZE)]
    scheme = SynthIDScheme(key=key, vocab=vocab, layers=4)
    return scheme.z_score([str(t) for t in token_ids])


@dataclass
class OfficialCrossCheck:
    official_on_official: float
    official_on_clean: float
    official_on_ours: float
    ours_on_ours: float
    ours_on_official: float
    ours_on_clean: float
    official_fires_on_own: bool
    ours_fires_on_own: bool
    official_null_on_clean: bool
    ours_null_on_official: bool
    note: str


def run_official_cross_check(seed: int = 1, device: str = "cpu") -> OfficialCrossCheck:
    vocab = make_vocab(VOCAB_SIZE)
    ours = SynthIDScheme(key="tool-synthid-key", vocab=vocab, layers=4)
    official_ids = official_generate(LENGTH, seed, device)
    clean_ids = [int(t[1:]) % VOCAB_SIZE for t in control_sequence(vocab, LENGTH, seed=90)]
    ours_tokens = ours.generate(LENGTH, seed)
    ours_ids = [int(t[1:]) % VOCAB_SIZE for t in ours_tokens]

    z_off_off = official_z(official_ids, device)
    z_off_clean = official_z(clean_ids, device)
    z_off_ours = official_z(ours_ids, device)
    z_ours_ours = ours.z_score(ours_tokens)
    z_ours_off = ours_on_ids(official_ids, ours.key)
    z_ours_clean = ours.z_score(control_sequence(vocab, LENGTH, seed=91))

    return OfficialCrossCheck(
        official_on_official=round(z_off_off, 3),
        official_on_clean=round(z_off_clean, 3),
        official_on_ours=round(z_off_ours, 3),
        ours_on_ours=round(z_ours_ours, 3),
        ours_on_official=round(z_ours_off, 3),
        ours_on_clean=round(z_ours_clean, 3),
        official_fires_on_own=z_off_off >= THRESHOLD,
        ours_fires_on_own=z_ours_ours >= THRESHOLD,
        official_null_on_clean=abs(z_off_clean) < THRESHOLD,
        ours_null_on_official=abs(z_ours_off) < THRESHOLD,
        note=(
            "Official g-values come from transformers.SynthIDTextWatermarkLogitsProcessor "
            f"(v installed). Our scheme is a simplified sha256 tournament. "
            "Each detector should fire on its own watermark and not on the other."
        ),
    )
