"""Tests for Slices 3-9: scorer, comparison, code probe, model bleach,
attribution, neural, SynthID, active test.

Model access is simulated with deterministic doubles (callables text->text). The
green-list, SynthID, and attribution schemes are real and run on real generated
samples.
"""

import random

from bleachmark.decode import decode
from bleachmark.detect.statistical.scorer import MgtScorer, length_confidence, ATTRIBUTION_WORDS
from bleachmark.detect.comparison import compare_models
from bleachmark.detect.code import constrained_probe
from bleachmark.detect.attribution import MultiBitScheme, bit_accuracy
from bleachmark.bleach.attribution import blind_token_bleach
from bleachmark.detect.neural import NeuralDetector
from bleachmark.detect.keyed.synthid import SynthIDScheme, SynthIDDetector
from bleachmark.detect.keyed.active import active_presence_test
from bleachmark.runtime.model import ModelGateway
from bleachmark.harness import generators


# ---- Slice 3: statistical scorer + length-aware confidence ----------------

def test_length_confidence():
    assert length_confidence(0) == 0.0
    assert length_confidence(ATTRIBUTION_WORDS // 2) == 0.5
    assert length_confidence(ATTRIBUTION_WORDS) == 1.0
    assert length_confidence(ATTRIBUTION_WORDS * 2) == 1.0


def test_scorer_repetitive_scores_higher():
    scorer = MgtScorer()
    repetitive = "the the the same same same word word word " * 10
    varied = (
        "A curious fox wandered through misty hills while distant thunder rolled "
        "over quiet valleys and travellers hurried homeward before nightfall."
    )
    assert scorer.score(repetitive) > scorer.score(varied)


def test_scorer_finding_is_not_a_verdict_and_length_aware():
    scorer = MgtScorer()
    finding = scorer.detect(decode("short text here"))[0]
    assert finding.false_positive_rate is not None
    assert any("not a verdict" in n for n in finding.notes)
    assert finding.confidence < 1.0  # short text is low confidence
    assert any("below" in n for n in finding.notes)


# ---- Slice 4: comparison detector -----------------------------------------

def _biased_model(bias_words, seed_base):
    state = {"n": 0}

    def fn(prompt):
        state["n"] += 1
        rng = random.Random(f"{seed_base}-{state['n']}")
        words = []
        for _ in range(40):
            if rng.random() < 0.85:
                words.append(rng.choice(bias_words))
            else:
                words.append(rng.choice([f"w{i}" for i in range(50)]))
        return " ".join(words)

    return fn


def _plain_model(seed_base):
    state = {"n": 0}

    def fn(prompt):
        state["n"] += 1
        rng = random.Random(f"{seed_base}-{state['n']}")
        return " ".join(rng.choice([f"w{i}" for i in range(50)]) for _ in range(40))

    return fn


def test_comparison_flags_watermarked_candidate():
    candidate = _biased_model(["green", "mark", "bias"], "cand")
    control = _plain_model("ctrl")
    result = compare_models("prompt", candidate, control, runs=8)
    assert result.likely_watermarked
    assert "Investigative" in result.note


def test_comparison_control_versus_control_is_baseline():
    a = _plain_model("a")
    b = _plain_model("b")
    result = compare_models("prompt", a, b, runs=8)
    assert not result.likely_watermarked


# ---- Slice 5: code probe --------------------------------------------------

def _converging_code_model():
    # cosmetic-only variation: different names, whitespace, and comments, same
    # structure. Canonicalization must collapse these to one form.
    forms = [
        "def solve(a, b):\n    r = a + b\n    return r",
        "def foo(x, y):\n    z = x + y  # sum\n    return z",
        "def bar(p, q):\n\n    total = p + q\n    return total",
    ]
    state = {"n": 0}

    def fn(prompt):
        state["n"] += 1
        return forms[state["n"] % len(forms)]

    return fn


def _varying_code_model():
    # structural variation that survives canonicalization
    forms = [
        "def solve(a, b):\n    return a + b",
        "def solve(a, b):\n    return b + a",
        "def solve(a, b):\n    return sum([a, b])",
    ]
    state = {"n": 0}

    def fn(prompt):
        state["n"] += 1
        return forms[state["n"] % len(forms)]

    return fn


def test_code_probe_flags_structural_excess():
    result = constrained_probe(_varying_code_model(), _converging_code_model(), task="add two ints", runs=6)
    assert result.control_residual == 0.0        # cosmetic noise canonicalized away
    assert result.candidate_residual > 0.0       # structural token choice survives
    assert result.likely_watermarked


# ---- Slice 6: model bleach through the gateway ----------------------------

def test_gateway_sanitizes_before_model():
    seen = {}

    def model(text):
        seen["text"] = text
        return text.upper()

    gw = ModelGateway(model)
    dirty = "hi" + chr(0x200B) + " there " + chr(0xE0041)
    gw.call(dirty)
    # the model must not see the zero-width or the tag character
    assert chr(0x200B) not in seen["text"]
    assert chr(0xE0041) not in seen["text"]
    assert gw.audit_log[-1].sanitized


def test_gateway_sandbox_refused_to_api():
    gw = ModelGateway(lambda t: t, is_api=True)
    try:
        gw.call("raw", sandbox=True)
        assert False
    except RuntimeError as exc:
        assert "SR-10" in str(exc)


def test_paraphrase_bleach_with_model_accepts():
    from bleachmark.bleach import bleach, Strength

    def paraphraser(text):
        # a meaning-preserving reshuffle: keep words, change spacing and case lightly
        return text.replace("does not", "doesn't")

    text = "The system does not fail. " * 6
    result = bleach(text, strength=Strength.PARAPHRASE, model=paraphraser)
    assert result.accepted


# ---- Slice 7: attribution -------------------------------------------------

def test_attribution_estimate_recovers_bits():
    vocab = generators.make_vocab(200)
    scheme = MultiBitScheme(key="attr-key", vocab=vocab, n_bits=16, gamma=0.25)
    message = [(i * 7) % 2 for i in range(16)]
    tokens = scheme.generate(message, length=480, seed=5, delta=3.0)
    est = scheme.estimate(tokens)
    assert bit_accuracy(message, est) >= 0.8


def test_blind_bleach_lowers_attribution():
    vocab = generators.make_vocab(200)
    scheme = MultiBitScheme(key="attr-key", vocab=vocab, n_bits=16, gamma=0.25)
    message = [(i * 7) % 2 for i in range(16)]
    tokens = scheme.generate(message, length=480, seed=5, delta=3.0)
    before = bit_accuracy(message, scheme.estimate(tokens))
    bleached = blind_token_bleach(tokens, vocab, fraction=0.6, seed=9)
    after = bit_accuracy(message, scheme.estimate(bleached))
    assert after < before


# ---- Slice 8: neural detector ---------------------------------------------

def test_neural_detector_reports_score():
    det = NeuralDetector(score_fn=lambda t: 0.73, model_name="fake-slm")
    finding = det.detect(decode("some text"))[0]
    assert finding.score == 0.73
    assert finding.false_positive_rate is not None


# ---- Slice 9: SynthID + active test ---------------------------------------

def test_synthid_detects_watermarked():
    vocab = generators.make_vocab(250)
    scheme = SynthIDScheme(key="synth-key", vocab=vocab, layers=4)
    wm = scheme.generate(length=200, seed=1)
    assert scheme.z_score(wm) > 4.0


def test_synthid_control_and_wrong_key_low():
    vocab = generators.make_vocab(250)
    scheme = SynthIDScheme(key="synth-key", vocab=vocab, layers=4)
    ctrl = generators.control_sequence(vocab, 200, seed=1)
    assert scheme.z_score(ctrl) < 4.0
    wm = scheme.generate(length=200, seed=1)
    wrong = SynthIDScheme(key="other", vocab=vocab, layers=4)
    assert wrong.z_score(wm) < 4.0


def test_synthid_detector_finding():
    vocab = generators.make_vocab(250)
    scheme = SynthIDScheme(key="synth-key", vocab=vocab, layers=4)
    wm = scheme.generate(length=200, seed=2)
    det = SynthIDDetector(scheme)
    finding = det.detect(decode(" ".join(wm)))[0]
    assert finding.posture.value == "keyed"
    assert finding.score > 4.0


def test_active_presence_test():
    candidate = _biased_model(["green", "mark"], "acand")
    control = _plain_model("actrl")
    result = active_presence_test(candidate, control, runs=8)
    assert result.likely_watermarked
