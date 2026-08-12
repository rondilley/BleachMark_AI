"""SynthID positive control: fires on watermark, null on clean, key-specific (TC-06).

The full measured sqrt(T) / FPR sweep is in
docs/results/2026-08-12_synthid_positive_control.json; this locks the three qualitative
controls in the suite at a modest length.
"""

from bleachmark.detect.keyed.synthid import SynthIDScheme
from bleachmark.harness.generators import control_sequence, make_vocab

VOCAB = make_vocab(400)
KEY = "synthid-control-key-v1"
WRONG_KEY = "synthid-adversary-guess-key"
T = 300
THRESHOLD = 4.0


def test_watermarked_fires():
    scheme = SynthIDScheme(key=KEY, vocab=VOCAB, layers=4)
    zs = [scheme.z_score(scheme.generate(T, seed=s)) for s in range(5)]
    assert all(z >= THRESHOLD for z in zs), zs


def test_clean_text_is_null():
    scheme = SynthIDScheme(key=KEY, vocab=VOCAB, layers=4)
    zs = [scheme.z_score(control_sequence(VOCAB, T, seed=100 + s)) for s in range(5)]
    assert all(abs(z) < THRESHOLD for z in zs), zs


def test_detection_is_key_specific():
    scheme = SynthIDScheme(key=KEY, vocab=VOCAB, layers=4)
    wrong = SynthIDScheme(key=WRONG_KEY, vocab=VOCAB, layers=4)
    # watermarked-then-read-with-the-wrong-key must not fire
    zs = [wrong.z_score(scheme.generate(T, seed=s)) for s in range(5)]
    assert all(abs(z) < THRESHOLD for z in zs), zs
