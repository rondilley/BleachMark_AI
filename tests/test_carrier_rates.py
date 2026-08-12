"""Carrier detection rates over the fixture corpus (TC-01, TC-02, TR-01, TR-02).

TC-01: every carrier positive fixture fires an actionable alarm (100% TPR).
TC-02: no legitimate-use fixture fires an actionable alarm (<=1% FPR).

An "actionable alarm" is a high-confidence carrier finding, the same set that drives
the CLI exit code (model.Report.high_confidence_carriers).
"""

import bleachmark
from fixtures.carrier_corpus import carrier_corpus


def _alarm_kinds(text):
    report = bleachmark.detect_carriers(text)
    return {f.kind for f in report.high_confidence_carriers()}


CORPUS = carrier_corpus()
POSITIVES = [f for f in CORPUS if f["label"] == "positive"]
LEGITS = [f for f in CORPUS if f["label"] == "legit"]


def test_corpus_has_positive_and_legit_for_every_carrier():
    carriers = {f["carrier"] for f in CORPUS if f["carrier"] != "none"}
    for c in carriers:
        pos = [f for f in POSITIVES if f["carrier"] == c]
        legit = [f for f in LEGITS if f["carrier"] == c]
        assert pos, f"{c} has no positive fixture"
        assert legit, f"{c} has no legitimate-use fixture (TR-02)"


def test_tc01_true_positive_rate_is_100_percent():
    misses = [f["name"] for f in POSITIVES if f["carrier"] not in _alarm_kinds(f["text"])]
    assert misses == [], f"positives not detected: {misses}"


def test_tc02_false_positive_rate_under_one_percent():
    fps = [(f["carrier"], f["name"], sorted(_alarm_kinds(f["text"])))
           for f in LEGITS if _alarm_kinds(f["text"])]
    fpr = len(fps) / len(LEGITS)
    assert fpr <= 0.01, f"FPR {fpr:.3f} over 1%; false positives: {fps}"


# --- regression tests for the two precision fixes this corpus surfaced -------

def test_rtl_directional_mark_not_flagged_as_zero_width():
    # an LRM inside Arabic text is legitimate bidi, not a hidden carrier
    f = next(f for f in LEGITS if f["name"] == "arabic_with_lrm")
    assert "zero_width" not in _alarm_kinds(f["text"])


def test_japanese_multiscript_token_not_flagged_as_homoglyph():
    for name in ("japanese_kana", "japanese_kanji", "korean"):
        f = next(f for f in LEGITS if f["name"] == name)
        assert "homoglyph" not in _alarm_kinds(f["text"]), name


def test_latin_cyrillic_mix_still_flagged_as_homoglyph():
    # the fix must not weaken the real confusable-attack signal
    f = next(f for f in POSITIVES if f["name"] == "cyrillic_a")
    assert "homoglyph" in _alarm_kinds(f["text"])
