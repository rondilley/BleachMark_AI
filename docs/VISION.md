# BleachMark — Vision

**Author:** Ron Dilley
**Date:** 2026-08-10
**Status:** Draft, updated 2026-08-13.
**Companion docs:** `REQUIREMENTS.md`, `SUCCESS_CRITERIA.md`, `ARCHITECTURE.md`,
`2026-08-10_LLM_Text_Watermarking_Research.md`

---

## 1. Vision

BleachMark is the reference open-source tool for hidden signals in model text.
A defender uses it to examine untrusted LLM text. The tool finds hidden signals.
The tool then makes a clean copy of the text. The clean copy keeps the meaning.
The clean copy removes or weakens the hidden signal.

An analyst gives BleachMark a block of ASCII or Markdown text. The tool reports
each hidden carrier that it finds. The tool reports the strength of each signal
and its confidence.

BleachMark is a steganalysis tool, not a plagiarism tool. Its purpose is
protection for systems and data. It prevents hidden control content and covert
channels in model output.

## 2. Why this tool is necessary, not point solutions

Three facts make a special tool necessary.

First, the hidden signal is not a set of special characters. A text editor cannot
remove it. For a statistical watermark, the signal is the selection of words and
their sequence. A tool must model token statistics to find it and to remove it. A
simple Unicode cleaner does nothing to this class.

Second, the field has two different signal types, and each type needs a different
method. A post-hoc carrier is a zero-width character, a homoglyph, or a
whitespace mark. An accurate character scan finds a post-hoc carrier. A
statistical watermark biases the token selection, and only a statistical test
finds it.

Frequently a tool cannot find a statistical watermark without a secret key. One
tool must hold the two methods. The tool must tell the user which class it
examines.

Third, the correct limits of detection are easy to get incorrect, and an
incorrect claim does much damage. Research shows that a keyless detector flags
human text at a high rate. Research shows that a good watermark is necessary for
detection of its key. A tool that hides these limits will accuse innocent authors
and give incorrect assurance.

BleachMark does this work correctly. It gives calibrated scores. It tells the
user its error rates.

The cost argument is simple. A defender sends model output into an automated
pipeline, and that output can hold a covert channel. A long text can hold
hundreds to thousands of hidden bits. That number is sufficient for a URL, a
command, or a compressed instruction set.

One hidden instruction can get to a tool-runner. The damage from that instruction
is more than the cost of a clean pass. BleachMark makes the clean pass cheap and
measurable, and it keeps the meaning safe.

The stakes are at a human level. A watermark can attribute a text to the
individual user, not only to the model. A multi-bit watermark can hold a user
identifier. Consider a journalist or a dissident who uses a model to write
material against a hostile regime. A hidden user-attribution mark in that text can
identify the author.

The result is not a data loss. The result is a risk to a person. BleachMark
bleaches the attribution mark and keeps the author hidden.

Length is important here. High-confidence attribution uses more than 400 words,
because the signal grows with length. A short text or a divided text is not
useful. For a source at risk, length is a defensive lever, and the tool tells
the user this.

The tool does not work as a passive scanner alone. The tool is model-equipped. It
has the source model and comparison models, but no watermark key at first. It uses
iteration and comparison across runs and models to find a possible watermark. It
uses a model-based bleach behind a meaning gate, and it measures what works. The
tool does not classify text as AI-written.

Source code is a strong target. Code has a defined syntax and a small space of
legitimate variation. A watermark that biases the token choice stands out as odd
variability. The tool tells a model to write a complete module of more than 400
words, then it looks for that variability.

A control model helps here. If one model tells that it adds no watermark, and a
local model adds none, the tool uses each one as a baseline. The difference
between the baseline and a watermarked model is the signal. The tool holds the
"no watermark" claim as unverified and re-checks it.

## 3. The primary parties

| Party | Role | What the party wants |
| --- | --- | --- |
| Ron Dilley | Owner, cybersecurity researcher | A correct threat model and no incorrect claims |
| Blue teams and SOC analysts | Primary users | Hidden covert-channel signals in untrusted model output |
| Pipeline and platform operators | Users | A library for an ingestion path that cleans model text |
| Security researchers | Users | Correct detection statistics and measured watermark robustness |
| Model-safety and red teams | Users | A method to study hidden control content in a malicious model |
| Journalist or dissident in a hostile regime | Protected party | No user-attribution mark that can identify the author of a text |
| Authors with an incorrect accusation | Protected party | No incorrect flag because of a low-perplexity style |

## 4. The strategic bets

**Bet 1 — Removal is stronger than keyless detection.**

Claim: a keyless tool can bleach a statistical watermark more surely than it can
find one. A transformation that keeps the meaning weakens the signal. The tool
does not find the signal first.

Why it is correct: each primary source accepts paraphrase and re-sampling as the
usual failure of a token-level watermark. One semantic paraphrase drops one
detector from 70.3 percent to 4.6 percent at a 1 percent false-positive rate.

How it could be incorrect: a fixed-key scheme on long text resists light
bleaching, and a strong paraphrase costs some meaning. Mitigation: give a range
of bleach strengths with a meaning-preservation gate. Tell the user which schemes
resist each strength.

**Bet 2 — Honesty about limits is a feature, not a weak point.**

Claim: a user trusts a tool that tells its false-positive rate. A user does not
trust a tool that overclaims.

Why it is correct: an incorrect flag, not a miss, damages the confidence in a
detector. Commercial detectors flagged non-native writers at more than 60
percent.

How it could be incorrect: some users want a simple yes-or-no, and they will
select a louder tool. Mitigation: give calibrated scores with a stated
false-positive rate and a clear cause. The honest output stays easy to use.

**Bet 3 — Post-hoc carriers are the high-confidence entry point.**

Claim: accurate detection of a zero-width, homoglyph, or whitespace carrier gives
a clear result immediately. That result builds trust for the harder statistical
work.

Why it is correct: a character-level carrier is deterministic to find and to
remove. It is also a live prompt-injection vector.

How it could be incorrect: these characters have legitimate uses, such as emoji
joiners and non-Latin scripts. A naive scan makes incorrect alarms. Mitigation:
make carrier detection script-aware and context-aware. Keep "present" apart from
"suspect".

**Bet 4 — Keyed and active modes belong in the tool, but behind a gate.**

Claim: the strongest true-detection results use a published detector, a key, or
black-box queries to the source model. These results must be available. The tool
must mark them as a different posture from keyless work.

Why it is correct: a black-box query test is the strongest keyless result in the
literature. A published z-test is the only clean statistic.

How it could be incorrect: these modes add heavy dependencies, and they can make
a user think keyless mode is as strong. Mitigation: keep them as optional modules.
Tell the user the preconditions. Add clear labels.

## 5. The three-year arc

**Year 1 — Foundation (2026).** Release v0.1 with the full scope.

The tool detects a post-hoc carrier accurately with context exoneration. The tool
uses comparison across runs and models to find a possible watermark. The tool runs
the keyed watermark tests (the green-list z-test and SynthID) when a key is
available, and a black-box watermark-presence test.

The tool bleaches text at selectable strengths behind a meaning-preservation gate.
The bleach includes deterministic, token-level, and model-based methods. The
bleach defeats a user-attribution mark. The release holds the keyed z-test and the
SynthID-Text module for the time when keys arrive. An effectiveness harness
measures the detection rate and the bleach rate for each stego method. The tool
makes Markdown and JSON reports and gives a CLI and a library.

The tool also gives an evolution loop. The loop trains a prompt strategy and a
detector against a known stego modality. Detection gets better across the
generations, and the detector estimates the partition. A provider adapter runs the
comparison detector and the code probe against a provider model.

**Year 2 — Earn (2027).**

Add measured robustness at scale. The scheme benchmark, the corpus-level
estimator, the round-trip translation bleach, and the language-matched meaning
gate are in the 2026 tree with data. Year 2 work that remains is a
directory ingest, a service surface, and new schemes as they come.

**Year 3 — Scale (2028).**
Give a service surface for pipeline integration. Track new watermark schemes as
they come. Keep a public and reproducible analysis of detection and bleaching
against the newest known methods.

## 6. What this tool is not

- BleachMark is not a plagiarism tool. It does not find who wrote an essay.
- BleachMark does not claim to detect a specified vendor watermark while no public
  technical specification is available. The Anthropic text watermark is one
  example.
- BleachMark does not check or repair C2PA file provenance. Signed metadata is a
  different problem for a different tool.
- BleachMark does not cover image, audio, or video steganography. Its surface is
  ASCII and Markdown text statistics.
- BleachMark does not promise to remove a robust or undetectable watermark without
  a cost to meaning. It tells the user the limit.
- BleachMark does not classify text as AI-written or human-written. Its input is
  model output by definition, so that question is not in scope.

## 7. What success looks like at the horizon

- A defender runs one command on untrusted model text. The defender gets a clean
  copy and a calibrated report of the hidden signals.
- Each detection score carries a stated false-positive rate. The tool does not
  accuse without a stated error rate.
- The bleach function removes or weakens a known and easily damaged watermark or
  carrier signal. The bleach function keeps the semantic similarity in the
  human-paraphrase band.
- The public benchmark shows the measured drop in detectability for each scheme
  and each bleach strength. The benchmark shows the measured cost to meaning.
- Security teams cite BleachMark as the honest reference for the limits of text
  steganalysis.
