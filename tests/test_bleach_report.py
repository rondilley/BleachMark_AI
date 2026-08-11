"""Slice 2 tests: carrier bleach, reports, redaction, exit codes.

TC-07, TC-10, TC-12, TC-13, FR-36.
"""

import json

import bleachmark
from bleachmark.bleach import bleach, Strength
from bleachmark.bleach.gate import MeaningGate
from bleachmark.report.json_emit import to_json
from bleachmark.report.markdown_emit import to_markdown

ZWSP = chr(0x200B)
TAG_A = chr(0xE0041)
RLO = chr(0x202E)
CYR_A = chr(0x0430)


# --- TC-07: the lowest-strength bleach removes each carrier ------------------

def test_normalize_removes_carriers_second_scan_clean():
    dirty = "hi" + ZWSP + "there " + TAG_A + TAG_A + " end" + RLO + "x"
    result = bleach(dirty, strength=Strength.NORMALIZE)
    assert result.accepted
    rescan = bleachmark.detect_carriers(result.text)
    assert rescan.findings == []


def test_normalize_folds_homoglyph():
    dirty = "p" + CYR_A + "ssword here and there"
    result = bleach(dirty, strength=Strength.NORMALIZE)
    assert "password" in result.text
    rescan = bleachmark.detect_carriers(result.text)
    assert "homoglyph" not in {f.kind for f in rescan.findings}


# --- TC-10: reject a bleach that does not keep the meaning -------------------

def test_meaning_gate_rejects_destructive_change():
    gate = MeaningGate(threshold=0.6)
    original = "The quick brown fox jumps over the lazy dog many times today."
    destroyed = "completely unrelated words about nothing at all here now"
    score = gate.similarity(original, destroyed)
    assert not gate.passes(score)


def test_token_bleach_keeps_meaning():
    text = "The system does not fail. " * 5
    result = bleach(text, strength=Strength.TOKEN)
    assert result.accepted
    assert result.meaning_score >= 0.6


def test_paraphrase_without_model_gives_clear_error():
    text = "some text to paraphrase " * 10
    try:
        bleach(text, strength=Strength.PARAPHRASE)
        assert False, "expected a clear error"
    except RuntimeError as exc:
        assert "needs a configured model" in str(exc)


# --- TC-12 / TC-13: payload redaction and secret hygiene --------------------

def test_json_report_does_not_leak_payload_by_default():
    text = "run " + TAG_A + TAG_A + " now"
    report = bleachmark.detect_carriers(text)
    out = to_json(report, show_payload=False)
    assert "payload_cleartext" not in out
    assert "payload_sha256" in out


def test_report_redacts_a_secret():
    from bleachmark.report import redact_secrets

    assert "[REDACTED-SECRET]" in redact_secrets("key sk-ABCDEFGHIJKLMNOPQRST here")


def test_markdown_report_renders_disclaimer():
    report = bleachmark.detect_carriers("clean text here")
    md = to_markdown(report)
    assert "not a verdict" in md


# --- FR-36: exit code from a high-confidence carrier only -------------------

def test_high_confidence_carrier_flags_exit():
    report = bleachmark.detect_carriers("hi" + ZWSP + "there")
    assert report.high_confidence_carriers()


def test_clean_text_no_exit_flag():
    report = bleachmark.detect_carriers("perfectly ordinary text")
    assert not report.high_confidence_carriers()
