# BleachMark — Success Criteria

**Author:** Ron Dilley
**Date:** 2026-08-10
**Status:** Draft, updated 2026-08-13.
**Companion docs:** `VISION.md`, `REQUIREMENTS.md`, `ARCHITECTURE.md`,
`2026-08-10_LLM_Text_Watermarking_Research.md`

Each criterion is measurable. A criterion has an ID and a scope tag. The scope
tags are MVP (v0.1), SCALE (v0.2 and later), and VNEXT (future).

---

## 1. Business success criteria

- **BC-01** (MVP) A defender runs one command on untrusted model text and gets a
  clean copy and a report. The report shows each hidden signal.
- **BC-02** (MVP) A user reads the report and knows the false-positive rate for
  each score. No score is a bare yes-or-no verdict.
- **BC-03** (MVP) A pipeline operator imports the library and gets a detect result
  in code. The result carries a location and a confidence.
- **BC-04** (SCALE) A researcher runs the benchmark and gets a table. The table
  shows the detectability drop and the meaning cost for each scheme.
- **BC-05** (VNEXT) A blue team cites BleachMark as the reference for the
  limits of text steganalysis. The tool has a public and reproducible benchmark.

---

## 2. Technical success criteria

### 2.1 Detection

- **TC-01** (MVP) The tool detects a known zero-width, tags-block, or
  variation-selector carrier at a true-positive rate of 100 percent on the
  fixture corpus. Each carrier is a deterministic codepoint test.
- **TC-02** (MVP) The tool makes no more than 1 percent false-positive results on the
  legitimate-use fixture corpus. That corpus holds emoji, RTL text, and
  multilingual text.
- **TC-03** (MVP) The tool detects a homoglyph substitution with a mixed-script
  test for each word. The tool does not flag a single-script word.
<!-- TC-04 removed 20260812 (see VIBE_HISTORY). -->
- **TC-05** (MVP) The keyed green-list z-test gives the same z-score as the
  reference method for a given key and tokenizer. The two numbers are equal to three
  decimal digits.
- **TC-06** (MVP) The tool detects the SynthID-Text scheme from a SynthID secret
  key and configuration. The tool reports a score and a false-positive rate.

### 2.2 Bleaching

- **TC-07** (MVP) The lowest-strength bleach removes each detected post-hoc
  carrier. A second scan finds no carrier.
- **TC-08** (MVP) The semantic-paraphrase bleach drops the detection score of a
  green-list watermark by a measured value. The report shows the before number
  and the after number.
- **TC-09** (MVP) Each bleach keeps the semantic similarity in the human-paraphrase
  band. The gate uses a named metric. For English the embedding band is near 0.76.
  For non-English text the gate uses a language-matched metric and threshold
  (FR-27a).
- **TC-10** (MVP) The tool rejects a bleach that does not keep the meaning. The tool
  gives the input text and a clear message.

### 2.3 Reliability and safety

- **TC-11** (MVP) The core detect path makes no network call. A network monitor
  shows no traffic during a core run.
- **TC-12** (MVP) The tool does not run or transmit a decoded payload, and it
  redacts the payload in a report by default. A test with a command payload shows
  no execution and no cleartext payload.
- **TC-13** (MVP) The tool does not write a secret to a report or a log. A test
  with a key in the environment shows no key in the output.
- **TC-14** (MVP) The keyless carrier scan processes a minimum of 1 MB of text
  each second on one core with no model in the path. A benchmark measures the rate.

### 2.4 Maintainability and observability

- **TC-15** (MVP) The build runs a linter and a type check with no error.
  The build stops when a check gives an error.
- **TC-16** (MVP) Each score records its method and its parameters. A second run
  with the same input gives the same score.
- **TC-17** (MVP) A new carrier connects as a module with no change to the core.
  A test adds a sample module.

### 2.5 Model-equipped detection and attribution

<!-- reframe 20260811: Ron -->

These criteria measure an investigative method. Success is a measured rate from
the harness, not a guaranteed detection. Each result tells the undetectability
limit (research §5).

- **TC-18** (MVP) The harness reports the true-positive rate and the false-positive
  rate of the comparison detector on a reference corpus. A cross-model result also
  tells the model-style confound.
- **TC-19** (MVP) The harness reports how many payload bits the estimate recovers on
  a fixture that carries a known payload. The result tells that an undetectable
  payload gives no signal.
- **TC-20** (MVP) The harness reports the drop in recovered attribution bits after
  the blind bleach. The bleach keeps the meaning in the human-paraphrase band.
<!-- TC-21 removed 20260812 (see VIBE_HISTORY). -->
- **TC-22** (MVP) The effectiveness harness reports the detection rate and the
  bleach rate for each stego method. A run makes the samples and measures the two
  rates.
- **TC-23** (MVP) The tool reports a low confidence for a text of 400 words or
  fewer. The harness shows the confidence as a function of the text length.

### 2.6 Code probe, adapter, and evolution

<!-- build 20260811: Ron -->

- **TC-24** (MVP) The code-probe canonicalization gives the same form for two
  cosmetically-different inputs. A structural change gives a different form.
- **TC-25** (MVP) Each code-probe generation is more than 400 words. The probe
  reports the corpus word count and rejects a short sample.
- **TC-26** (MVP) The best fitness goes up across the generations. The
  tool records the fitness of each generation.
- **TC-27** (MVP) The evolved detector estimates the stego partition at a rate of 70
  percent or more. This estimate is key recovery for the modality.
- **TC-28** (MVP) The provider adapter gives text from a provider model. This test
  uses network access and a key.
- **TC-29** (MVP) The context-keyed signature scores a context-keyed pick above a
  stable favorite and above noise. A validated test uses doubles.
- **TC-30** (MVP) A keyless probe on a production model reports no confound-free
  watermark signal, and it tells the undetectability limit. The result is an honest
  null, not an incorrect flag.

---

## 3. Test plan

| Criterion | Test | Data source | Threshold | Cadence |
| --- | --- | --- | --- | --- |
| TC-01 | Carrier detection test | Watermarked fixture corpus | 100 percent true-positive | Each build |
| TC-02 | Legitimate-use test | Emoji, RTL, multilingual fixtures | 1 percent maximum false-positive | Each build |
| TC-03 | Mixed-script test | Homoglyph and native-script fixtures | No single-script flag | Each build |
| TC-05 | Keyed z-test parity | Reference key and tokenizer | Equal to three decimals | Each build |
| TC-06 | SynthID detection test | SynthID configuration and samples | Score and rate given | Each build |
| TC-07 | Carrier removal test | Watermarked fixture corpus | No carrier after bleach | Each build |
| TC-08 | Paraphrase bleach test | Green-list watermarked text | Measured score drop | Each build |
| TC-09 | Meaning-gate test | Bleach input and output | Similarity in human band | Each build |
| TC-11 | Network test | Core detect run | No network traffic | Each release |
| TC-14 | Throughput test | 10 MB text sample | 1 MB each second minimum | Each release |
| TC-25 | Live length | Live model generation | Each sample more than 400 words | Each release |
| FR-27a | Language-matched gate | Bundled pairs en/es/zh/ja/ar | Paraphrase passes, other fails | Each build |
| BC-04 | Scheme benchmark | Reference generators, 24 by 400 | Table of drop and meaning cost | Each release |

---

## 4. What does NOT count as success

- A test that uses a stub rather than a detector is a wiring check, not
  validation.
- A statement that "the tests pass" without a detection run does not count.
- A claim that the paraphrase bleach works without a configured model does not
  count.
- A detection number without a stated false-positive rate does not count.
- A bleach that drops the detection score but does not keep the meaning does not
  count.

**The load-bearing rule.** No iteration, MVP, or version is "shipped", "closed",
or "complete" until a minimum of one call against the external service has
given data. For BleachMark, the external service is the configured
paraphrase model for a bleach test, and the detection run for a detection
test. A stub-based test is a wiring check, not validation.
