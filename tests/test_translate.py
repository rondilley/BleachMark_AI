"""Round-trip translation bleach (FR-29).

The dictionary trip is deterministic and dependency-free. Synonym collapse changes
tokens. A planted green-list mark on English content words drops. The meaning gate
accepts a typical sentence. Optional translator callables go through the gateway.
"""

from bleachmark.bleach.gate import MeaningGate
from bleachmark.bleach.translate import (
    back_translate,
    content_vocab,
    cwra_prompt,
    english_vocab,
    forward_translate,
    measure_roundtrip_removes_watermark,
    roundtrip_bleach,
    roundtrip_tokens,
    roundtrip_translate,
)


def test_round_trip_is_deterministic():
    text = "The large city can help the people find a good way."
    assert roundtrip_translate(text) == roundtrip_translate(text)


def test_one_to_one_function_words_survive():
    assert roundtrip_translate("the and or") == "the and or"


def test_synonym_collapse_changes_a_content_word():
    # big and large share the Spanish gloss; the reverse map is canonical "large"
    assert "large" in roundtrip_translate("big")
    assert roundtrip_tokens(["big", "huge", "large"]) == ["large", "large", "large"]


def test_forward_then_back_on_known_sentence():
    src = "The big house"
    mid = forward_translate(src)
    assert "grande" in mid.lower()
    back = back_translate(mid)
    assert "large" in back.lower()
    assert "house" in back.lower() or "casa" not in back.lower()


def test_unknown_words_stay():
    assert "BleachMark" in roundtrip_translate("BleachMark keeps meaning")


def test_meaning_gate_accepts_a_typical_sentence():
    text = "The people need a good way to find money for the new house in the city."
    out = roundtrip_translate(text)
    score = MeaningGate().similarity(text, out)
    assert score >= 0.6
    result = roundtrip_bleach(text)
    assert result.accepted
    assert result.strength == 4
    assert result.meaning_score is not None and result.meaning_score >= 0.6


def test_watermark_z_drops_on_content_vocab():
    m = measure_roundtrip_removes_watermark(samples=5, length=200, seed=3)
    assert m["z_before"] > 8.0
    assert m["z_after"] < m["z_before"] * 0.7
    assert m["changed_fraction"] > 0.3
    assert m["meaning_score"] >= 0.5
    assert len(content_vocab()) >= 80
    assert len(english_vocab()) > len(content_vocab())


def test_callable_translators_go_through_the_gateway():
    calls = []

    def outbound(text):
        calls.append(("out", text))
        return "pivot-text"

    def inbound(text):
        calls.append(("in", text))
        return "The people need a good way to find money."

    src = "The people need a good way to find money."
    result = roundtrip_bleach(src, outbound=outbound, inbound=inbound)
    assert result.accepted
    assert [c[0] for c in calls] == ["out", "in"]
    # the gateway sanitizes before the outbound model sees the text
    assert calls[0][1] == src


def test_carrier_is_stripped_before_a_translator(monkeypatch):
    seen = []

    def outbound(text):
        seen.append(text)
        return text

    def inbound(text):
        return text

    # zero-width space must not reach the translator
    dirty = "The people\u200b need money."
    roundtrip_bleach(dirty, outbound=outbound, inbound=inbound)
    assert seen
    assert "\u200b" not in seen[0]


def test_cwra_prompt_asks_for_the_pivot_language():
    p = cwra_prompt("an editorial on transit", pivot="Spanish", min_words=400)
    assert "Spanish" in p
    assert "400" in p
    assert "English" in p
