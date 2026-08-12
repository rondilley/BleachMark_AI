"""Validate the reverse-order bleach on ground truth (the real context-keyed scheme).

A context-keyed green-list marks each token against its generation-order neighbor. If the
model writes in reverse and the tool reorders to forward, the mark no longer lines up with
the forward neighbor, so the forward z-score collapses. The reorder is lossless, so the
content is kept. This is the same real Kirchenbauer scheme the tool detects elsewhere.
"""

from bleachmark.detect.keyed.greenlist import GreenListScheme
from bleachmark.harness.generators import make_vocab, watermarked_sequence, control_sequence, substitution_attack
from bleachmark.bleach.reorder import (
    reverse_bleached_sequence,
    forward_z,
    reorder_reverse,
    split_sentences,
    reverse_prompt,
    fidelity,
)

L = 500


def _scheme():
    return GreenListScheme(key="wm-key", vocab=make_vocab(400), gamma=0.25)


def test_reverse_bleach_collapses_the_watermark_and_is_lossless():
    scheme = _scheme()
    z_wm, z_bleach, z_ctrl = [], [], []
    for s in range(6):
        wm = watermarked_sequence(scheme, L, seed=s, delta=2.0)
        bleach = reverse_bleached_sequence(scheme, L, seed=s, delta=2.0)
        ctrl = control_sequence(scheme.vocab, L, seed=1000 + s)
        z_wm.append(forward_z(scheme, wm))
        z_bleach.append(forward_z(scheme, bleach))
        z_ctrl.append(forward_z(scheme, ctrl))
        assert sorted(bleach) == sorted(wm)   # lossless: the same token multiset
    avg = lambda xs: sum(xs) / len(xs)
    assert avg(z_wm) > 15.0                    # the watermark is strong before the bleach
    assert avg(z_bleach) < 3.0                 # and near control after it
    assert avg(z_bleach) < avg(z_wm) / 4       # a large collapse


def test_reverse_bleach_beats_substitution_and_keeps_all_tokens():
    scheme = _scheme()
    wm = watermarked_sequence(scheme, L, seed=3, delta=2.0)
    bleach = reverse_bleached_sequence(scheme, L, seed=3, delta=2.0)
    sub = substitution_attack(wm, scheme.vocab, fraction=0.3, seed=7)
    # the reorder removes more of the signal than a 30% token substitution
    assert forward_z(scheme, bleach) < forward_z(scheme, sub)
    # and it drops no token, where the substitution rewrites 30 percent of them
    assert sorted(bleach) == sorted(wm)


def test_sentence_reorder_is_lossless_round_trip():
    text = "First sentence here. Second one follows! Third and last?"
    once = reorder_reverse(text)
    assert once.startswith("Third and last?")
    assert reorder_reverse(once) == text       # applying it twice restores the original
    assert len(split_sentences(text)) == 3


def test_reverse_prompt_asks_for_reverse_order_and_length():
    p = reverse_prompt("an editorial on urban transit", min_words=400)
    assert "reverse order" in p.lower()
    assert "400" in p


def test_fidelity_gate_scores_content():
    # identical content passes; unrelated content fails
    a = "the city should invest in rail because buses are slow and crowded"
    assert fidelity(a, a).ok
    b = "quarterly revenue rose as the new product line shipped to retail partners"
    assert not fidelity(a, b).ok
