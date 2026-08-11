"""Slice 1 tests: carrier detection and legitimate-use exoneration.

Carrier characters are built with chr() so the test file holds no literal
invisible characters. TC-01, TC-02, TC-03.
"""

import bleachmark

ZWSP = chr(0x200B)
ZWNJ = chr(0x200C)
ZWJ = chr(0x200D)
BOM = chr(0xFEFF)
VS16 = chr(0xFE0F)
LRO = chr(0x202D)
RLO = chr(0x202E)
TAG_A = chr(0xE0041)  # tag "A"
TAG_CANCEL = chr(0xE007F)
CYR_A = chr(0x0430)  # Cyrillic a, looks like Latin a
NBSP = chr(0x00A0)


def kinds(report):
    return {f.kind for f in report.findings}


# --- TC-01: deterministic carriers are detected at 100 percent -------------

def test_zero_width_detected():
    text = "hello" + ZWSP + ZWNJ + "world"
    report = bleachmark.detect_carriers(text)
    assert "zero_width" in kinds(report)


def test_tags_block_detected_and_payload_redacted():
    text = "please " + TAG_A + TAG_A + " continue"
    report = bleachmark.detect_carriers(text)
    finding = next(f for f in report.findings if f.kind == "tags_block")
    assert finding.payload_len is not None
    assert finding.payload_sha256 is not None
    # default report dict does not leak the cleartext
    assert "payload_cleartext" not in finding.to_dict(show_payload=False)
    assert "payload_cleartext" in finding.to_dict(show_payload=True)


def test_variation_selector_run_detected():
    text = "x" + VS16 + VS16 + VS16 + VS16
    report = bleachmark.detect_carriers(text)
    assert "variation_selectors" in kinds(report)


def test_bidi_override_detected():
    text = "safe" + RLO + "txet" + LRO + "more"
    report = bleachmark.detect_carriers(text)
    assert "bidi_override" in kinds(report)


def test_markdown_comment_detected():
    text = "visible text\n<!-- hidden instruction here -->\nmore"
    report = bleachmark.detect_carriers(text)
    assert "markdown_comment" in kinds(report)


# --- TC-03: homoglyph mixed-script per word --------------------------------

def test_homoglyph_mixed_script_detected():
    text = "the p" + CYR_A + "ssword is secret"  # 'password' with a Cyrillic a
    report = bleachmark.detect_carriers(text)
    assert "homoglyph" in kinds(report)


def test_single_script_word_not_flagged():
    text = "the password is secret"
    report = bleachmark.detect_carriers(text)
    assert "homoglyph" not in kinds(report)


# --- TC-02: no more than 1 percent false positives on legitimate use -------

def test_leading_bom_exonerated():
    text = BOM + "normal file content"
    report = bleachmark.detect_carriers(text)
    assert "zero_width" not in kinds(report)


def test_emoji_zwj_sequence_exonerated():
    # woman + ZWJ + laptop is a legitimate emoji ZWJ sequence
    text = "look " + chr(0x1F469) + ZWJ + chr(0x1F4BB) + " here"
    report = bleachmark.detect_carriers(text)
    assert "zero_width" not in kinds(report)


def test_vs16_on_emoji_exonerated():
    text = "heart " + chr(0x2764) + VS16 + " symbol"
    report = bleachmark.detect_carriers(text)
    assert "variation_selectors" not in kinds(report)


def test_single_nbsp_exonerated():
    text = "5" + NBSP + "km down the road we go"
    report = bleachmark.detect_carriers(text)
    assert "whitespace" not in kinds(report)


def test_clean_prose_has_no_carrier_findings():
    text = "This is an ordinary paragraph of clean English prose with no tricks."
    report = bleachmark.detect_carriers(text)
    assert report.findings == []
