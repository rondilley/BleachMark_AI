"""Validate the deterministic transcode translator and its watermark removal.

The reversed-word transform is deterministic, fully invertible, and dependency-free. The
decode recovers the exact English. A deterministic, key-independent token relabel removes the
watermark, shown with the real green-list scheme.
"""

import statistics

from bleachmark.bleach.transcode import (
    reverse_word_encode,
    reverse_word_decode,
    transcode_prompt,
    transcode_removes_watermark,
)
from bleachmark.detect.keyed.greenlist import GreenListScheme
from bleachmark.harness.generators import make_vocab


def test_encode_decode_round_trip_is_lossless():
    text = "The city should build more bike lanes now, quickly! (2024)"
    assert reverse_word_decode(reverse_word_encode(text)) == text


def test_decode_recovers_english_from_a_reversed_draft():
    # exactly what the model produced in the probe
    assert reverse_word_decode("ehT ytic dluohs dliub erom ekib senal won.") == \
        "The city should build more bike lanes now."


def test_encode_keeps_word_order_and_punctuation():
    enc = reverse_word_encode("the city should")
    assert enc == "eht ytic dluohs"
    assert reverse_word_encode("a-b, c.") == "a-b, c."  # single letters and punctuation unchanged


def test_transcode_prompt_asks_for_reversed_letters():
    p = transcode_prompt("an editorial on transit", min_words=400)
    assert "reverse" in p.lower()
    assert "400" in p


def test_transcode_removes_the_watermark():
    scheme = GreenListScheme(key="wm-key", vocab=make_vocab(400), gamma=0.25)
    pairs = [transcode_removes_watermark(scheme, 500, seed=s) for s in range(6)]
    source_z = statistics.mean(p[0] for p in pairs)
    transcoded_z = statistics.mean(p[1] for p in pairs)
    assert source_z > 15.0            # the source stream is strongly watermarked
    assert abs(transcoded_z) < 3.0    # the deterministic relabel removes it, near control
