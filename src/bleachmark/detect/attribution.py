"""Multi-bit user-attribution estimate (FR-39, best-effort).

A multi-bit watermark can carry a user identifier. This module implements a real
position-allocation scheme (MPAC-style) and a best-effort estimator. The estimate
is not a guarantee and is bounded by the undetectability limit: an undetectable
payload gives no signal (research 5).
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

_MOD = 1 << 32


def _is_green_bit(prev: str, token: str, key: str, group: int, bit: int, gamma: float) -> bool:
    h = hashlib.sha256(f"{key}|{group}|{bit}|{prev}|{token}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") < gamma * _MOD


@dataclass
class MultiBitScheme:
    key: str
    vocab: list[str]
    n_bits: int
    gamma: float = 0.25

    def group_of(self, position: int) -> int:
        return position % self.n_bits

    def generate(self, message: list[int], length: int, seed: int, delta: float = 2.0) -> list[str]:
        rng = random.Random(seed)
        green_w = math.exp(delta)
        tokens: list[str] = []
        prev = "<s>"
        for pos in range(length):
            g = self.group_of(pos)
            bit = message[g]
            weights = [
                green_w if _is_green_bit(prev, t, self.key, g, bit, self.gamma) else 1.0
                for t in self.vocab
            ]
            total = sum(weights)
            r = rng.random() * total
            acc = 0.0
            chosen = self.vocab[-1]
            for t, w in zip(self.vocab, weights):
                acc += w
                if r <= acc:
                    chosen = t
                    break
            tokens.append(chosen)
            prev = chosen
        return tokens

    def estimate(self, tokens: list[str]) -> list[int]:
        """Recover each bit by the green list that better fits its position group."""
        vocab_set = set(self.vocab)
        green0 = [0] * self.n_bits
        green1 = [0] * self.n_bits
        prev = "<s>"
        for pos, tok in enumerate(tokens):
            g = self.group_of(pos)
            if tok in vocab_set:
                if _is_green_bit(prev, tok, self.key, g, 0, self.gamma):
                    green0[g] += 1
                if _is_green_bit(prev, tok, self.key, g, 1, self.gamma):
                    green1[g] += 1
            prev = tok
        return [1 if green1[g] > green0[g] else 0 for g in range(self.n_bits)]


def bit_accuracy(true_msg: list[int], est_msg: list[int]) -> float:
    if not true_msg:
        return 1.0
    correct = sum(1 for a, b in zip(true_msg, est_msg) if a == b)
    return correct / len(true_msg)
