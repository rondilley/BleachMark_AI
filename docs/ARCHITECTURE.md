# BleachMark — Architecture

**Author:** Ron Dilley
**Date:** 2026-08-10
**Status:** v0.1 built, updated 2026-08-11.
**Companion docs:** `VISION.md`, `REQUIREMENTS.md`, `SUCCESS_CRITERIA.md`,
`2026-08-10_LLM_Text_Watermarking_Research.md`

This document tells why the tool makes each decision. The diagrams support
the prose. The prose is the record.

---

## 1. The shape of the system

BleachMark is not a generic text cleaner. Two facts from the research shape the complete system.

First, detection and removal are not equal in strength. A keyless tool cannot find
a good statistical watermark, because a good watermark is pseudorandom without the
key (research §5, Christ and others). But a keyless tool can remove or weaken many
watermarks, because a meaning-preserving transformation degrades the signal
without a need to find it (research §4). So the system keeps detection and bleaching as two subsystems with different strength claims.

Second, the two signal classes use two different engines. A post-hoc carrier is a
codepoint fact, found by an accurate scan with a context test. A statistical
watermark is a distribution fact, found only by a statistical test, and frequently not
at all. So the detection subsystem holds a carrier engine and a statistical
engine, and it does not mix their confidence claims.

```mermaid
flowchart TD
  IN[Input text UTF-8]
  DEC[Decoder to codepoints]
  IN --> DEC
  DEC --> DET[Detection subsystem]
  DEC --> BLE[Bleach subsystem]
  DET --> CAR[Carrier engine codepoint plus context]
  DET --> STAT[Statistical engine keyless]
  DET --> KEYED[Keyed and active engine optional]
  BLE --> NORM[Normalize carriers]
  BLE --> TOK[Token edits]
  BLE --> PARA[Semantic paraphrase model]
  BLE --> GATE[Meaning gate]
  DET --> REP[Report JSON and Markdown]
  BLE --> REP
```

## 2. Decision: detection and bleaching are two subsystems

Decision: build detection and bleaching as two subsystems with one shared data
model, and not one combined pass.

Alternative: one pass that finds a signal and then removes it.

Why this is correct. The strength claims are different. Detection of a statistical
watermark is weak or not possible without a key, but bleaching does not use
detection first (research §4 and §5). A combined pass would connect the strong function to the weak one, and the tool would under-bleach when detection
did not work. Separation lets the bleach run blind at a chosen strength.

How it could be incorrect. A user may want "find and fix" in one step. Mitigation: the
CLI can chain detect and bleach, but the subsystems stay apart in the code.

## 3. Decision: a keyless default path and a gated keyed path

Decision: the default path is keyless. The keyed and active modes are optional
modules behind a gate.

Alternative: one detection path that assumes key access.

Why this is correct. The realistic defender sees only output text and holds no key
(research §5). The keyless path must work with no model and no secret. The keyed
green-list z-test and the SynthID-Text detector use more inputs (a key, a
tokenizer, a configuration), and the active black-box test needs model queries.
These are strong when the tool has them, but rare, so they must not stop the usual path.

Keyless does not mean model-free. The tool is model-equipped. It uses the source
model and comparison models for the comparison and neural methods (§9). The
no-model carrier path is the baseline for a user without a model.

How it could be incorrect. A user may think the keyless mode is as strong as the keyed
mode. Mitigation: each result carries a posture label and a stated false-positive
rate (FR-14, FR-22).

## 4. Decision: one detector interface with a calibrated score

Decision: each detector gives a result through one interface. The result holds a
score, a stated false-positive rate, a posture label, a list of locations, and a
length-aware confidence (FR-49).

Alternative: each detector gives its own shape.

Why this is correct. The base-rate problem makes an uncalibrated number a danger
(research §5). A single interface forces each detector to tell its false-positive
rate, so the report does not show a bare verdict. A single interface also lets a new
detector connect with no change to the report code (AR-03, AR-04).

How it could be incorrect. Some detectors give a p-value, some give a probability, some
give a z-score. Mitigation: the interface holds the raw statistic and a mapped
score, so the report can show the two.

## 5. Decision: carrier detection is a codepoint scan plus a context test

Decision: the carrier engine finds a candidate by codepoint, then it exonerates a
legitimate use by script, base character, and position before it flags.

Alternative: a codepoint blacklist alone.

Why this is correct. Each carrier codepoint has a legitimate use (research §7.7). A
blacklist alone flags each emoji joiner, each RTL mark, and each BOM at the file start,
and the user turns the tool off. The context test keeps the high-signal results
(tag characters in prose, detached selector runs, mixed-script single tokens) and clears the legitimate results.

How it could be incorrect. The context rules are complex and can miss a legitimate use.
Mitigation: keep the codepoint sets and the context rules in data files. Give each carrier a positive fixture and a legitimate-use fixture (MR-02, TR-02).

## 6. Decision: bleaching is a strength ladder with a meaning gate

Decision: the bleach subsystem offers three strengths. Each strength runs behind a
meaning-preservation gate.

Alternative: one fixed bleach method.

Why this is correct. The research gives a clear sequence of effect for each meaning cost
(research §4 and §8).

The lowest strength normalizes a post-hoc carrier with no
model and no meaning cost. The middle strength makes token-level edits. The highest
strength makes a semantic paraphrase with a model, which is the cleanest strip but
uses a model and costs some meaning. A ladder lets the user select the trade-off.
The gate rejects each result that does not keep the meaning (FR-27, FR-28).

How it could be incorrect. The paraphrase strength uses a model, which is a heavy
dependency. Mitigation: the model sits behind an optional install group, and the
two lower strengths work with no model (NFR-03).

Security sequence. The tool runs the deterministic carrier bleach before a model
request. A smuggled payload does not get to the paraphrase model (SR-06). This
sequence is a hard rule, not an option. The model gateway holds this rule (§9).

<!-- AI review 20260810-234903: gemini, claude -->

The gate is the load-bearing node. The meaning gate is the single node of the
bleach thesis. If the gate is too strict, the tool rejects a good bleach. If the
gate is too loose, the tool removes meaning with no warning.

The default metric is a sentence-embedding cosine similarity in the P-SP family.
The English human band is near 0.76 (research §4). For non-English text the gate
uses a language-matched metric (FR-27a). The gate calibration is a prerequisite
for the bleach slices, not an open question.

<!-- AI review 20260811-003657: gemini, claude -->

## 7. Decision: keyless statistical detection uses pluggable scorers

Decision: the statistical engine holds pluggable machine-generation scorers of the
Binoculars and Fast-DetectGPT class. It does not claim per-document watermark
identification.

Alternative: claim keyless detection of a specified watermark in one document.

Why this is correct. No published method does passive single-document keyless
detection of a distortion-free or undetectable watermark, and theory says there
may be none (research §5). The honest keyless result is a calibrated
machine-generation score plus a corpus-level estimator. A pluggable structure lets the
tool add a better scorer as the field improves.

How it could be incorrect. A scorer can hold a demographic bias (research §5).
Mitigation: the engine attaches a confound note to a low-perplexity result and tells the false-positive rate (FR-15, FR-16).

## 8. Decision: keyed modules sit behind optional extras

Decision: the green-list z-test, the SynthID-Text detector, and the active
black-box test live in optional modules with their own install groups.

Alternative: build these into the core.

Why this is correct. Each module uses a heavy or special input: a tokenizer, a
SynthID configuration, or a model query function (IR-02, IR-03, IR-04). The core
must stay light and offline (NFR-02, NFR-03). The SynthID-Text support is a stated
requirement (FR-19), so the module ships in v0.1, but its dependency is optional.

How it could be incorrect. A user may want SynthID detection with no configuration.
Mitigation: the module gives a clear message when the user gives no configuration.

## 9. Decision: model-equipped detection, neural methods, and the harness

Decision: the tool has access to the source model and comparison models. It uses
comparison and neural methods for detection and for bleaching. It estimates a
user-attribution payload. It measures its own effectiveness.

Alternative: a passive tool with heuristics alone and no model access.

Why this is correct. The realistic tool is model-equipped, not passive
(goal.md reframe). With model access the tool runs a black-box watermark-presence test and a
cross-run comparison, which are the strongest keyless methods (research §5). A
neural detector and a model-based bleach add strength that a heuristic does not
give. A watermark can attribute a text to a user, so the tool must estimate and
defeat that payload (research §6).

The tool measures what works with an effectiveness harness. The harness makes
watermarked samples, attacks them, and reports the detection rate and the bleach
rate for each stego method. This is a research project, so measurement is a core
function.

How it could be incorrect. Model access and neural methods are heavy, and a
comparison method can give an incorrect signal. Mitigation: the tool uses NPU or GPU
acceleration when the host has it (FR-43). The tool gives a false-positive rate
for each comparison result. The keyless heuristics run with no model, so a user
without a model keeps a baseline.

The honest limit. A perfectly undetectable watermark stays undetectable. Model queries do not
change that (research §5, Christ and others). Comparison and neural methods work
against a deployed and leaky scheme, not against the ideal scheme. The tool tells
this limit.

The model gateway. Every model-bound path goes through one gateway in
`runtime/model.py` (SR-09). The gateway runs the carrier normalization first and
stops the call on an error. This puts the SR-06 sequence at one
choke-point, not at five call sites. The harness is the one audited special case. It sends a raw sample
only in a sandbox, not to an API (SR-10).

Investigative, not guaranteed. The comparison, the attribution estimate, and the
neural detectors are investigative methods. The harness measures each one. The
success is a measured rate, not a guaranteed detection. The attribution bleach
runs blind, so it does not use the estimate (FR-40).

Source code is a strong comparison target. Code has a defined syntax and a small
space of legitimate variation. The `detect/code.py` module tells a model to write
a well-known function many times, then it measures the variability (FR-45, FR-46).
A watermark bias stands out against the low-entropy background of canonical code.

The probe constrains the generation. The module fixes or limits the variable and
function names and the structure (FR-46a). This shrinks the innocuous variation
space. A watermarking model must then encode its bits in the small space that is
left, so the change becomes more obvious. The tool does not force the full
output, because a forced token carries no watermark (research §3).

The control model gives the null. A control model tells that it adds no
watermark, or it is a local model (FR-47). The differential variability between
the control and a watermarked model is the signal, and it answers the comparison
null question (§18). The tool holds the control claim as unverified and re-checks
it (FR-48).

<!-- reframe 20260811: Ron. AI review 20260811-003657 -->

<!-- AI review 20260811-003657: gemini, xai, claude, openai -->

## 10. Decision: JSON is canonical, Markdown is the human report

Decision: the JSON report is the canonical output. The Markdown report is a view
for a human reader.

Alternative: one human-only report.

Why this is correct. A pipeline consumes JSON. A human reads Markdown. A versioned
JSON schema lets a downstream tool parse the result with time (DR-02). This matches
the report pattern of the sibling tools.

How it could be incorrect. The two reports can drift. Mitigation: the Markdown report
renders from the JSON model, not from a different path.

## 11. Cross-cutting points

**Observability.** Each detection step logs at a selectable level (OR-01). Each
score records its method and its parameters, so a second run gives the same score
(OR-02, TC-16). The default log level does not record a decoded payload (OR-03).

**Error handling.** A missing optional dependency gives a clear message, not a long error output. A bleach that does not keep the meaning gives the input text and a message (TC-10). A detector failure does not stop the other detectors.

**Security.** The tool uses input as untrusted data (SR-01). The tool does not
run or transmit a decoded payload (SR-02). The tool reads a model API key only from
an environment variable or a key file (SR-04). The tool labels a covert-channel
result as a possible prompt-injection vector (SR-05).

The tool runs the carrier bleach before a model request (SR-06). The tool redacts a
decoded payload in a report by default, and it shows the payload length and a hash,
not the cleartext (SR-07). A cleartext payload is available only behind an explicit
flag with a warning (SR-08).

<!-- AI review 20260810-234903: gemini, claude -->

**Report layer.** The report layer holds three homes for a MUST. A redaction filter
in `report/` removes a key or a secret from each
output stream (SR-03). The report
tells the user that a machine-generation score is not a verdict and not watermark
identification (FR-13a). The report does not claim to detect a vendor production
watermark without the vendor key (FR-19a).

<!-- AI review 20260811-003657: claude, openai -->

**Exit code.** The `cli.py` sets a non-zero exit code from a high-confidence
carrier result only. A machine-generation score does not set the exit code
(FR-36).

<!-- AI review 20260811-003657: gemini, claude, openai -->

**Cost.** The core path makes no network request and no model request (NFR-02). Only the
paraphrase bleach and the active test spend a model request, and the two are optional.

## 12. Module layout

```
src/bleachmark/
  __init__.py          package API surface
  cli.py               detect, bleach, report subcommands
  model.py             shared data model: Finding, Score, Report
  decode.py            UTF-8 to codepoint decode with offsets
  detect/
    __init__.py        detector interface and registry
    carriers/
      zerowidth.py     zero-width and format characters
      tags.py          Unicode Tags block, ASCII smuggling
      selectors.py     variation-selector runs
      homoglyph.py     confusable and mixed-script test
      whitespace.py    whitespace and typographic carriers
      markdown.py      Markdown-specific carriers
      bidi.py          bidirectional override characters
      context.py       exoneration by script, base, position
    statistical/
      scorer.py        pluggable machine-generation scorers
      corpus.py        corpus-level estimator (SCALE)
    comparison.py      cross-run and cross-model inference
    code.py            constrained repeated-generation probe for code
    context_keyed.py   context-keyed signature, watermark against style
    attribution.py     multi-bit user-attribution estimate
    neural/
      __init__.py      neural detector interface
      llm.py           LLM-based detector
      slm.py           SLM-based detector
      net.py           neural-net detector
    keyed/
      greenlist.py     green-list z-test
      synthid.py       SynthID-Text detector
      active.py        black-box watermark-presence test
  bleach/
    __init__.py        bleach interface and strength ladder
    normalize.py       carrier removal, lowest strength
    tokens.py          token-level edits, middle strength
    paraphrase.py      semantic paraphrase, highest strength
    neural.py          model-based bleach
    attribution.py     defeat a user-attribution mark
    translate.py       round-trip translation (SCALE)
    gate.py            meaning-preservation gate
  report/
    json_emit.py       canonical JSON report
    markdown_emit.py   Markdown report from the JSON model
  data/
    codepoints/        codepoint set data files
  runtime/
    model.py           the one model gateway, sanitize before every call
    accel.py           NPU or GPU acceleration
    providers.py       provider adapters, a real model as a callable
  harness/
    __init__.py        effectiveness harness
    generators.py      reference watermark generators and test keys
    measure.py         attack the samples and measure the rates
  evolve/
    __init__.py        evolution API surface
    arena.py           known stego embedder and the estimating detector
    evolution.py       the prompt and detector genomes and the loop
    realbridge.py      evolve a constraint prompt against a provider model
tests/
  fixtures/            watermarked, clean, and legitimate-use corpora
benchmark/             larger scheme benchmark (SCALE)
```

The `detect/code.py` module holds the constrained probe with the AST
canonicalization (Section 16). The `detect/neural/` and the `bleach/neural.py`
modules take a model callable through the gateway.

## 13. Data flow

```mermaid
sequenceDiagram
  participant U as User
  participant C as CLI
  participant D as Decoder
  participant DET as Detectors
  participant B as Bleach
  participant G as Model gateway
  participant R as Report
  U->>C: detect or bleach a text
  C->>D: decode UTF-8 to codepoints
  D->>DET: codepoints with offsets
  DET->>DET: run carrier and statistical detectors
  DET->>R: findings with score and false-positive rate
  C->>B: bleach at a selected strength
  B->>B: normalize carriers first
  B->>G: paraphrase or neural call on clean text
  G->>G: sanitize check then call the model
  B->>B: run the meaning gate
  B->>R: before and after scores
  R->>U: JSON and Markdown reports
```

## 14. Failure modes

- A legitimate-use carrier gives an incorrect flag. Surface: the legitimate-use
  fixture test. Recovery: the context rule in `detect/carriers/context.py`.
- A low-perplexity human text gets a high machine-generation score. Surface: the
  confound note and the stated false-positive rate. Recovery: no binary verdict
  (FR-15).
- The tool does not have the paraphrase model. Surface: a clear message at bleach time.
  Recovery: the two lower bleach strengths run.
- A bleach removes the signal but changes the meaning. Surface: the meaning gate.
  Recovery: reject the result and give the input text (FR-28).
- A keyed module gets no key or configuration. Surface: a clear message. Recovery:
  the keyless path runs.
- A smuggled payload rides in the input to the paraphrase model. Surface: the
  carrier scan. Recovery: the carrier bleach removes the payload before the model
  request (SR-06).

## 15. Version boundary

**v0.1 (MVP).** The owner keeps the full scope in v0.1 (goal.md reframe). v0.1
covers these parts:

- All carrier detectors with context exoneration.
- The keyless statistical scorer with a stated false-positive rate.
- The comparison detector and the neural detectors.
- The black-box watermark-presence test and the attribution estimate.
- The three bleach strengths with the meaning gate.
- The model-based bleach and the attribution bleach.
- The green-list z-test and the SynthID-Text module for the time when keys arrive.
- The effectiveness harness and the NPU or GPU acceleration.
- The JSON and Markdown reports, the CLI, and the library.

**v0.2 (SCALE).** The larger benchmark. The corpus-level estimator. The round-trip
translation bleach.

**v0.3 (VNEXT).** A local service surface for pipeline integration. A tracker for
new watermark schemes.

## 16. Decision: the constrained code probe minimizes the stego surface

Decision: the code probe constrains the generation, then canonicalizes each output,
then measures the residual variability.

Alternative: measure the raw variability of unconstrained code.

Why this is correct. Code has a small space of legitimate variation. The probe
sets the names and the structure in the prompt. Then it parses each output to a
syntax tree, renames each identifier, and unparses (FR-53). This removes the name,
the whitespace, the comment, and the literal-format channels. This leaves only
structural token choice, and a watermark must work there (FR-54).

The probe aggregates a suite of functions to get to the 400-word band (FR-55,
FR-49). One canonical function is too short for attribution.

How it could be incorrect. A fully canonical task gives the model no room. The watermark and the detector
then have no signal. Mitigation: the evolution
loop looks for the structural freedom that exposes the signal (Section 17).

```mermaid
flowchart TD
  T[Constrained task with fixed names]
  G[N generations from the model]
  C[Canonicalize each parse rename unparse]
  R[Residual variability structural only]
  X[Compare candidate to control]
  T --> G
  G --> C
  C --> R
  R --> X
```

## 17. Decision: adversarial training and evolution

Decision: the tool evolves prompt strategies and detectors against a known stego
embedder, and it measures the fitness across the generations.

Alternative: a fixed prompt and a fixed detector.

Why this is correct. The best prompt and the best detector are not known before the
run. The loop fixes a known stego modality, such as the green-list scheme (FR-57).
It evolves a prompt genome and a detector genome (FR-56). The detector estimates
the stego partition from samples, which is key recovery for this modality (FR-58).

The fitness rewards detection separation and partition recovery, and it penalizes a
false-positive result (FR-59). The fitness goes up across the generations (FR-60).

How it could be incorrect. The loop learns against the reference embedder, not a
provider model. Mitigation: the evolved prompt is a constraint template that
moves to a provider model, and the tool tells the limit of that move.

```mermaid
flowchart TD
  E[Known stego embedder]
  A[Arena]
  P[Population of prompt and detector genomes]
  V[Evaluate separation and recovery]
  S[Select the top half]
  M[Mutate to refill]
  B[Best config exposes and recovers]
  E --> A
  P --> V
  A --> V
  V --> S
  S --> M
  M --> P
  V --> B
```

The empirical limit on a provider model. The evolution and the signature work in
the reference domain, where the tool plants the key. On a live provider model the
tool ran three keyless probes: a structural residual, a synonym context-flip, and
an arbitrary-token context-flip. Each one confounded or gave no signal (VIBE_HISTORY
2026-08-11).

The candidate for the tests was `claude-opus-5`, a model launched on or after
2026-08-02, so it marks at launch (research §6). No keyless probe gave a
confound-free watermark signal. This is the undetectability wall in practice, and
the tool reports an honest null, not an incorrect flag (FR-62).

<!-- build 20260811: Ron -->

## 18. Open questions

- Which machine-generation scorer is the best default for the keyless path, given
  the false-positive risk? A measured comparison must give the answer.
- Which paraphrase model gives the cleanest bleach for each meaning cost on a local
  runtime? A benchmark must give the answer.
- What is the correct meaning-gate threshold for a high-stakes text? The research
  gives a band, not a single number (research §4).
- Can the corpus-level green-list estimator give a useful signal on a document set without a key? A test must give the answer.
- Can the mixed-script test hold 1 MB each second in pure Python, or must it have a
  compiled part? A benchmark must give the answer (NFR-01).
  <!-- AI review 20260810-234903: gemini, xai -->
- How does the NPU or GPU acceleration stay the same on Windows and on POSIX
  (NFR-04, FR-43)? What is the fallback when the host has no accelerator? A
runtime-selection plan must give the answer.
  <!-- AI review 20260811-003657: gemini, openai -->
- What is the null hypothesis for the comparison detector, so it does not confuse
  sampler variance or model style with a watermark? A method and a benchmark must
give the answer (research §5).
  <!-- AI review 20260811-003657: claude, gemini, openai -->
