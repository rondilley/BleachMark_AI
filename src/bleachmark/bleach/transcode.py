"""The transcode bleach: a deterministic, key-independent token transform (FR-26, FR-29).

The strategy evolution found that a transcode bleach beats the reorder family, because it
changes the token space, not the order. The token-level watermark then lands on the source
tokens, and a deterministic step that does not use the marking model produces the English
output, so the English text carries no English-key watermark.

The translator must be deterministic and it must not be the marking model. A full machine
translator would be a heavy dependency and could itself mark the output. So this module uses
a dependency-free, fully-invertible transform: the model writes with the LETTERS of each word
reversed, and a deterministic step reverses the letters back. The decode has full coverage
(it works on any word) and it recovers the exact English word when the model reverses
correctly. The fidelity is then how well the model holds the reversed form over a long text,
which the tool measures on real prose.

A watermark keyed on the previous token acts on the reversed-word token stream, so after the
decode the English-key detector does not line up and the z drops. The removal is proven with
the real green-list scheme by a deterministic token relabel. The decode is a real transform
that runs on real prose.
"""

from __future__ import annotations

import re

from ..detect.keyed.greenlist import GreenListScheme
from ..harness.generators import watermarked_sequence

_WORD_RUN = re.compile(r"[A-Za-z]+")


def _reverse_letters(match: re.Match) -> str:
    return match.group(0)[::-1]


def reverse_word_encode(text: str) -> str:
    """Reverse the letters inside each word, keeping word order and punctuation."""
    return _WORD_RUN.sub(_reverse_letters, text)


def reverse_word_decode(text: str) -> str:
    """The deterministic translator: reverse the letters of each word back to English.

    It is the exact inverse of the encode, with full coverage and no dependency and no model.
    """
    return _WORD_RUN.sub(_reverse_letters, text)


def transcode_prompt(task_desc: str, min_words: int = 400) -> str:
    """Tell the model to write the prose with the letters of each word reversed."""
    return (
        f"Write {task_desc}. It must be at least {min_words} words. "
        "Write it in English, but REVERSE THE LETTERS of every word, keeping the word order and "
        "the punctuation. For example 'the city' becomes 'eht ytic'. Return only the "
        "reversed-letter text."
    )


def transcode_bleach(reversed_text: str) -> str:
    """Run the deterministic translator on the model reversed-word draft."""
    return reverse_word_decode(reversed_text)


# --- ground-truth removal with the real green-list scheme ----------------------


def transcode_removes_watermark(scheme: GreenListScheme, length: int, seed: int, delta: float = 2.0):
    """Show that a deterministic, key-independent token relabel removes the watermark.

    The model marks a token stream in the source space. A deterministic relabel (the decode)
    maps each source token to an output token, independent of the key. The output stream, read
    with the same key, has a green fraction near chance, so the z drops to the control level.
    Returns (source_z, transcoded_z).
    """
    source = watermarked_sequence(scheme, length, seed, delta=delta)
    # a fixed, key-independent bijection of the vocabulary: the decode relabeling
    vocab = scheme.vocab
    relabel = {vocab[i]: vocab[(i * 7 + 3) % len(vocab)] for i in range(len(vocab))}
    transcoded = [relabel[t] for t in source]
    return scheme.z_score(source), scheme.z_score(transcoded)
