"""Tests for the configurable local OpenAI-compatible provider (no network)."""

from bleachmark.runtime import providers


def test_local_base_url_resolution(monkeypatch):
    monkeypatch.delenv("BLEACHMARK_LOCAL_URL", raising=False)
    assert providers.local_base_url() == "http://localhost:11434/v1"          # default
    assert providers.local_base_url("http://tars.uberadmin.com:5150/v1") == \
        "http://tars.uberadmin.com:5150/v1"                                    # explicit wins
    monkeypatch.setenv("BLEACHMARK_LOCAL_URL", "http://tars.uberadmin.com:5150/v1")
    assert providers.local_base_url() == "http://tars.uberadmin.com:5150/v1"   # env used


def test_list_local_models_parses_data_and_models(monkeypatch):
    monkeypatch.setattr(providers, "_get",
                        lambda url, timeout=15: {"data": [{"id": "unsloth/Llama-3.3-70B-Instruct-GGUF"}]})
    assert providers.list_local_models("http://x/v1") == ["unsloth/Llama-3.3-70B-Instruct-GGUF"]
    monkeypatch.setattr(providers, "_get",
                        lambda url, timeout=15: {"models": [{"name": "qwen2.5-32b"}, {"model": "phi-4"}]})
    assert providers.list_local_models("http://x/v1") == ["qwen2.5-32b", "phi-4"]


def test_make_model_local_discovers_served_model(monkeypatch):
    monkeypatch.setattr(providers, "list_local_models", lambda base=None: ["served-model-x"])
    captured = {}
    monkeypatch.setattr(providers, "_openai_compatible",
                        lambda cfg, base, token_field="max_tokens", timeout=600: captured.update(
                            model=cfg.model, base=base) or (lambda p: "ok"))
    fn = providers.make_model("local", base_url="http://x/v1")
    assert fn("hi") == "ok"
    assert captured["model"] == "served-model-x"     # the served model was auto-selected
    assert captured["base"] == "http://x/v1"


def test_make_model_local_needs_no_key(monkeypatch):
    # a missing key file must not stop a local call
    monkeypatch.setattr(providers, "list_local_models", lambda base=None: [])
    monkeypatch.setattr(providers, "_openai_compatible",
                        lambda cfg, base, token_field="max_tokens", timeout=600: (lambda p: "ok"))
    fn = providers.make_model("local", root="/nonexistent", base_url="http://x/v1")
    assert fn("hi") == "ok"
