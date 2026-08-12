"""Security regressions for the review findings (SR-03/04, SR-06, SR-09)."""

import io
import time
import urllib.error

import pytest

import bleachmark
from bleachmark.runtime import providers

ZWSP = chr(0x200B)


def test_carrier_flood_does_not_hang():
    # a hostile input that is one long run of non-ASCII carrier characters must scan
    # in linear time; the pre-fix O(n^2) byte-offset map would take minutes here
    hostile = ZWSP * 200_000
    t0 = time.perf_counter()
    report = bleachmark.detect_carriers(hostile)
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"carrier flood took {dt:.2f}s (possible O(n^2) regression)"
    assert any(f.kind == "zero_width" for f in report.findings)


def test_tag_flood_does_not_hang():
    hostile = chr(0xE0041) * 200_000    # a run of Unicode Tags-block characters
    t0 = time.perf_counter()
    report = bleachmark.detect_carriers(hostile)
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"tag flood took {dt:.2f}s (possible O(n^2) regression)"
    assert any(f.kind == "tags_block" for f in report.findings)


def test_make_model_gates_and_sanitizes_before_call(monkeypatch):
    # the default callable must run the carrier sanitize before the model sees the prompt
    seen = {}
    monkeypatch.setattr(providers, "list_local_models", lambda base=None: ["m"])
    monkeypatch.setattr(
        providers, "_openai_compatible",
        lambda cfg, base, token_field="max_tokens", timeout=600: (
            lambda p: seen.update(prompt=p) or "ok"),
    )
    fn = providers.make_model("local", base_url="http://x/v1")
    assert fn("hello" + ZWSP + "world") == "ok"
    assert ZWSP not in seen["prompt"]           # the carrier never reached the model (SR-06)


def test_make_model_ungated_does_not_sanitize(monkeypatch):
    seen = {}
    monkeypatch.setattr(providers, "list_local_models", lambda base=None: ["m"])
    monkeypatch.setattr(
        providers, "_openai_compatible",
        lambda cfg, base, token_field="max_tokens", timeout=600: (
            lambda p: seen.update(prompt=p) or "ok"),
    )
    fn = providers.make_model("local", base_url="http://x/v1", gated=False)
    fn("a" + ZWSP + "b")
    assert ZWSP in seen["prompt"]               # the explicit raw path is unsanitized


def test_unknown_provider_rejected_before_any_path_build():
    # a traversal-style provider name must be rejected before read_key builds a path
    with pytest.raises(RuntimeError, match="unknown provider"):
        providers.make_model("../../secret")


def test_post_error_does_not_leak_url_query_string(monkeypatch):
    def fake_urlopen(req, timeout=60):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b"error body"))

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as ei:
        providers._post("https://api.example.com/x?key=SECRETKEY123", {}, {"a": 1})
    msg = str(ei.value)
    assert "SECRETKEY123" not in msg            # the key in the query string is gone
    assert "?" not in msg.split(" HTTP")[0]
