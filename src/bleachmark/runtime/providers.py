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
    max_tokens: int = 4096


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
        # never echo the query string: some providers carry the API key there (SR-03/04)
        safe_url = url.split("?", 1)[0]
        raise RuntimeError(f"{safe_url} HTTP {exc.code}: {detail}")


_MAX_GET_BYTES = 5 * 1024 * 1024  # cap the local-discovery response (SSRF hardening)


def _get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(_MAX_GET_BYTES).decode("utf-8"))


def local_base_url(base_url: str | None = None) -> str:
    """Resolve the local OpenAI-compatible base URL.

    Order: an explicit argument, then the BLEACHMARK_LOCAL_URL environment variable, then the
    default. The operator points BLEACHMARK_LOCAL_URL at a local engine, for example
    http://tars.uberadmin.com:5150/v1, and every local call uses it.
    """
    return base_url or os.environ.get("BLEACHMARK_LOCAL_URL") or _OPENAI_COMPAT["local"]


def list_local_models(base_url: str | None = None) -> list[str]:
    """Query the local engine for the model ids it serves (GET /v1/models)."""
    url = local_base_url(base_url).rstrip("/") + "/models"
    data = _get(url)
    items = data.get("data") or data.get("models") or []
    ids = []
    for it in items:
        mid = it.get("id") or it.get("name") or it.get("model")
        if mid:
            ids.append(mid)
    return ids


def _openai_compatible(cfg: ModelConfig, base_url: str, token_field: str = "max_tokens",
                       timeout: int = 60) -> Callable[[str], str]:
    def call(prompt: str) -> str:
        body = {
            "model": cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            token_field: cfg.max_tokens,
        }
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        out = _post(f"{base_url}/chat/completions", headers, body, timeout=timeout)
        return out["choices"][0]["message"]["content"] or ""

    return call


def make_embedding(provider: str = "openai", model: str = "text-embedding-3-small",
                   root: str = ".") -> Callable[[str], list]:
    """Build a callable(text)->vector for a real embedding model (FR-27, TC-09).

    Used to give the meaning gate a semantic metric instead of a token n-gram proxy.
    Keys are read from the same `<provider>.key.txt` files and never logged.
    """
    provider = provider.lower()
    if provider == "openai":
        key = read_key("openai", root)

        def embed(text: str) -> list:
            body = {"model": model, "input": text}
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            out = _post("https://api.openai.com/v1/embeddings", headers, body)
            return out["data"][0]["embedding"]

        return embed
    raise RuntimeError(f"no embedding adapter for provider: {provider}")


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
        timeout = int(os.environ.get("BLEACHMARK_API_TIMEOUT", "300"))
        out = _post("https://api.anthropic.com/v1/messages", headers, body, timeout=timeout)
        parts = [b.get("text", "") for b in out.get("content", []) if b.get("type") == "text"]
        return "".join(parts)

    return call


def _gemini(cfg: ModelConfig) -> Callable[[str], str]:
    def call(prompt: str) -> str:
        # the key goes in a header, never in the URL (SR-03/04): a URL can be logged,
        # cached, or echoed in an error message
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.model}:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens},
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": cfg.api_key}
        out = _post(url, headers, body)
        cands = out.get("candidates", [])
        if not cands:
            return ""
        parts = cands[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    return call


_KNOWN_PROVIDERS = {"local", "claude", "gemini"} | set(_OPENAI_COMPAT)


def make_model(
    provider: str,
    model: str | None = None,
    root: str = ".",
    temperature: float = 1.0,
    max_tokens: int = 4096,
    base_url: str | None = None,
    gated: bool = True,
) -> Callable[[str], str]:
    """Build a callable(prompt)->text for a real provider (FR-37, IR-01).

    By default the callable is wrapped in the ModelGateway, so every model-bound path
    runs the carrier sanitize before the model sees the prompt and fails closed (SR-06,
    SR-09). Pass gated=False only for a sandbox path that must never reach an API.

    For the local provider the base URL is configurable (base_url, then BLEACHMARK_LOCAL_URL),
    so it can point at a local engine such as tars.uberadmin.com:5150. When no model is named,
    the tool asks the local engine for the model it serves.
    """
    provider = provider.lower()
    # validate before building any file path, so a provider name cannot traverse (SR-03/04)
    if provider not in _KNOWN_PROVIDERS:
        raise RuntimeError(f"unknown provider: {provider}")
    if provider == "local":
        url = local_base_url(base_url)
        chosen = model
        if not chosen or chosen == DEFAULT_MODELS["local"]:
            try:
                served = list_local_models(url)
                chosen = served[0] if served else DEFAULT_MODELS["local"]
            except Exception:
                chosen = model or DEFAULT_MODELS["local"]
        cfg = ModelConfig("local", chosen, "", temperature, max_tokens)
        # a local model can be large and slow, so allow a long timeout (env-overridable)
        timeout = int(os.environ.get("BLEACHMARK_LOCAL_TIMEOUT", "600"))
        raw = _openai_compatible(cfg, url, token_field="max_tokens", timeout=timeout)
    else:
        api_key = read_key(provider, root)
        cfg = ModelConfig(provider, model or DEFAULT_MODELS.get(provider, provider), api_key,
                          temperature, max_tokens)
        if provider == "claude":
            raw = _anthropic(cfg)
        elif provider == "gemini":
            raw = _gemini(cfg)
        else:  # an OpenAI-compatible provider (openai, xai, mistral)
            # newer OpenAI models reject max_tokens and want max_completion_tokens
            field = "max_completion_tokens" if provider == "openai" else "max_tokens"
            raw = _openai_compatible(cfg, _OPENAI_COMPAT[provider], token_field=field)
    if not gated:
        return raw
    from .model import ModelGateway

    return ModelGateway(raw, is_api=True).call
