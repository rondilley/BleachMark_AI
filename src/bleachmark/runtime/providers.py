"""Real model adapters (FR-37, IR-01).

Each adapter turns a real provider into a callable(prompt) -> text, so the
validated comparison detector and code probe can point at a real watermarking
model and an unwatermarked control model. Pure stdlib (urllib), no dependency.

This is the drop-in swap for the deterministic test doubles: the detector code does
not change, only the callable does. Keys are read from a `<provider>.key.txt` file
at the project root and are never written to a report or a log (SR-03, SR-04).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

DEFAULT_MODELS = {
    "openai": "gpt-5.5",
    "xai": "grok-4.3",
    # a watermark test needs a model launched on or after 2026-08-02, when
    # Anthropic marks at launch. claude-opus-4-7 predates that (research §6).
    "claude": "claude-opus-5",
    "gemini": "gemini-3.1-pro-preview",
    "mistral": "mistral-large-latest",
    "local": "local-model",
}

_OPENAI_COMPAT = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "local": "http://localhost:11434/v1",
}


@dataclass
class ModelConfig:
    provider: str
    model: str
    api_key: str
    temperature: float = 1.0
    max_tokens: int = 512


def read_key(provider: str, root: str = ".") -> str:
    path = os.path.join(root, f"{provider}.key.txt")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                return line
    raise RuntimeError(f"no key found in {path}")


def _post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"{url} HTTP {exc.code}: {detail}")


def _openai_compatible(cfg: ModelConfig, base_url: str, token_field: str = "max_tokens") -> Callable[[str], str]:
    def call(prompt: str) -> str:
        body = {
            "model": cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            token_field: cfg.max_tokens,
        }
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        out = _post(f"{base_url}/chat/completions", headers, body)
        return out["choices"][0]["message"]["content"] or ""

    return call


def _anthropic(cfg: ModelConfig) -> Callable[[str], str]:
    def call(prompt: str) -> str:
        body = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        out = _post("https://api.anthropic.com/v1/messages", headers, body)
        parts = [b.get("text", "") for b in out.get("content", []) if b.get("type") == "text"]
        return "".join(parts)

    return call


def _gemini(cfg: ModelConfig) -> Callable[[str], str]:
    def call(prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.model}:generateContent?key={cfg.api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens},
        }
        out = _post(url, {"Content-Type": "application/json"}, body)
        cands = out.get("candidates", [])
        if not cands:
            return ""
        parts = cands[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    return call


def make_model(
    provider: str,
    model: str | None = None,
    root: str = ".",
    temperature: float = 1.0,
    max_tokens: int = 512,
) -> Callable[[str], str]:
    """Build a callable(prompt)->text for a real provider (FR-37, IR-01)."""
    provider = provider.lower()
    api_key = "" if provider == "local" else read_key(provider, root)
    cfg = ModelConfig(provider, model or DEFAULT_MODELS.get(provider, provider), api_key,
                      temperature, max_tokens)
    if provider == "claude":
        return _anthropic(cfg)
    if provider == "gemini":
        return _gemini(cfg)
    if provider in _OPENAI_COMPAT:
        # newer OpenAI models reject max_tokens and want max_completion_tokens
        field = "max_completion_tokens" if provider == "openai" else "max_tokens"
        return _openai_compatible(cfg, _OPENAI_COMPAT[provider], token_field=field)
    raise RuntimeError(f"unknown provider: {provider}")
