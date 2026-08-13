# BleachMark — Requirements

**Author:** Ron Dilley
**Date:** 2026-08-10
**Status:** Draft, updated 2026-08-13.
**Companion docs:** `VISION.md`, `SUCCESS_CRITERIA.md`, `ARCHITECTURE.md`,
`2026-08-10_LLM_Text_Watermarking_Research.md`

Keywords MUST, SHOULD, and MAY follow RFC 2119. Each requirement has an ID and a
scope tag. The scope tags are MVP (v0.1), SCALE (v0.2 and later), and VNEXT
(future). The research analysis is the source for each technical claim.

---

## 0. Context and scope

BleachMark is a Python library and CLI. It detects hidden signals in ASCII and
Markdown text from LLMs. It bleaches those signals while it keeps the meaning.
The MVP holds all listed watermark families and the keyed module.

The default posture is keyless but model-equipped. The tool starts with no
watermark key, but it has the source model and comparison models. The keyed
modules wait for keys. The keys come after the first release.

Detection is not passive. The tool uses iteration and comparison across runs and
models to find a possible watermark. A watermark can also attribute the text to a
user, not only to the model.

The tool does not target a specified vendor watermark while no public
specification is available. The tool does not check C2PA file provenance. The
tool does not cover image, audio, or video steganography.

---

## 1. Functional requirements (FR)

### 1.1 Input handling

- **FR-01** (MVP) The tool MUST accept UTF-8 text from a file, from standard
  input, and from a library call. Justification: the primary users run a CLI and
  a library.
- **FR-02** (MVP) The tool MUST decode text to Unicode codepoints without loss
  before each scan. Justification: carrier detection works at the codepoint layer
  (research §7).
- **FR-03** (MVP) The tool MUST record the byte offset and line of each result.
  Justification: a user must find each hidden signal.
- **FR-04** (SCALE) The tool SHOULD accept a directory and process each file in
  it. Justification: pipeline and corpus use.

### 1.2 Post-hoc carrier detection

- **FR-05** (MVP) The tool MUST detect zero-width and format characters in
  the Unicode Format category. Justification: zero-width carriers (research §7.1).
- **FR-06** (MVP) The tool MUST detect Unicode Tags block characters
  (U+E0000 to U+E007F) that float in prose. Justification: ASCII smuggling and
  invisible prompt injection (research §7.2).
- **FR-07** (MVP) The tool MUST detect detached variation-selector runs
  (U+FE00 to U+FE0F and U+E0100 to U+E01EF). Justification: byte smuggling in one
  glyph (research §7.3).
- **FR-08** (MVP) The tool MUST detect homoglyph substitution with a mixed-script
  test for each word, based on Unicode UTS #39. Justification: confusable and IDN
  attacks (research §7.4).
- **FR-09** (MVP) The tool MUST detect whitespace and typographic carriers. These
  include trailing spaces, tabs, and non-U+0020 spaces. Justification: whitespace
  steganography (research §7.5).
- **FR-10** (MVP) The tool MUST detect Markdown-specific carriers. These include
  HTML comments, reference-link sequence, and interchangeable syntax.
  Justification: Markdown covert channels (research §7.5).
- **FR-11** (MVP) The tool MUST detect bidirectional override characters
  (U+202D and U+202E). Justification: Trojan Source reordering, CVE-2021-42574
  (research §7.6).
- **FR-12** (MVP) The tool MUST exonerate a legitimate use of each carrier by
  script, base character, and position before it flags the carrier. Justification:
  false-positive traps (research §7.7).

### 1.3 Keyless corpus watermark estimation

<!-- FR-13, FR-13a, FR-14, FR-15, FR-16 removed 20260812 (see VIBE_HISTORY). -->

- **FR-17** (SCALE) The tool SHOULD estimate green-list bias on a corpus.
  Justification: corpus-level watermark-presence estimation (research §5).

### 1.4 Keyed and active detection (optional modules)

- **FR-18** (MVP) The tool MUST run a green-list z-test when the user gives a key
  and a tokenizer. Justification: the only clean statistic (research §3).
- **FR-19** (MVP) The tool MUST detect the SynthID-Text scheme when the user gives
  the SynthID secret key and configuration. Justification: SynthID-Text support is
  a stated requirement (research §4).
  <!-- AI review 20260810-234903: gemini, mistral, claude -->
- **FR-19a** (MVP) The tool MUST NOT claim to detect a vendor production watermark
  without the vendor key. The signal is pseudorandom without the key (research §4).
  Justification: honesty about the key limit.
- **FR-20** (MVP) The tool SHOULD integrate a published vendor detector when one is
  available, rather than approximate it. No vendor detector is public at the
  research date, so this is a design principle. Justification: a correct result,
  not a guess (research §5).
  <!-- AI review 20260810-234903: claude -->
- **FR-21** (MVP) The tool MUST run a black-box watermark-presence test when the
  user can query the source model. Justification: the strongest keyless result, and
  the tool is model-equipped (research §5, Gloaguen and others).
  <!-- reframe 20260811: model-equipped posture -->
- **FR-22** (MVP) The tool MUST label a keyed or active result as a different
  posture from a keyless result. Justification: honesty about strength
  (VISION §4, Bet 4).

### 1.5 Bleaching

- **FR-23** (MVP) The tool MUST bleach a text at selectable strengths.
  Justification: a range of meaning cost (VISION §4, Bet 1).
- **FR-24** (MVP) At the lowest strength, the tool MUST remove or normalize a
  post-hoc carrier without a model. Justification: deterministic carrier removal
  (research §7).
- **FR-25** (MVP) At a middle strength, the tool MUST apply token-level edits.
  Justification: light statistical dilution (research §4).
- **FR-26** (MVP) At the highest strength, the tool MUST apply a semantic
  paraphrase with a configured model. Justification: the cleanest bleach
  (research §4, DIPPER).
- **FR-27** (MVP) The tool MUST run a meaning-preservation gate with a named
  semantic-similarity metric and a human-band threshold near 0.76 (research §4).
  Justification: a bleach must keep the meaning.
  <!-- AI review 20260810-234903: mistral, claude -->
- **FR-27a** (MVP) For non-English text the gate MUST use a language-matched metric.
  Justification: the English P-SP metric does not fit other languages (research §4).
- **FR-28** (MVP) The tool MUST reject a bleach result that fails the meaning gate.
  Justification: no silent meaning loss (research §4).
- **FR-29** (SCALE) The tool SHOULD offer a round-trip translation bleach.
  Justification: strong signal removal at some meaning drift (research §4).

### 1.6 Reporting

- **FR-30** (MVP) The tool MUST make a JSON report as the canonical output.
  Justification: machine consumption and pipeline use.
- **FR-31** (MVP) The tool MUST make a Markdown report for a human reader.
  Justification: the deliverable for a human reader.
- **FR-32** (MVP) Each report MUST record the result, the location, the strength,
  and the confidence. Justification: a user must use each result.
- **FR-33** (MVP) A bleach report MUST record the before-detection score and the
  after-detection score. Justification: measured effect of the bleach.

### 1.7 CLI and library

- **FR-34** (MVP) The tool MUST give a `detect`, a `bleach`, and a `report`
  subcommand. Justification: the named CLI surface (goal decisions).
- **FR-35** (MVP) The library MUST give a clean API for detect and bleach.
  Justification: the library is a first-class deliverable.
- **FR-36** (MVP) The CLI MUST give a non-zero exit code when it finds a
  high-confidence carrier. A calibrated statistical rate MUST NOT drive the exit
  code. Justification: a pipeline gate on a deterministic result only.
  <!-- AI review 20260810-234903: claude -->

### 1.8 Model-equipped detection and attribution

<!-- reframe 20260811: Ron -->

- **FR-37** (MVP) The tool MUST run keyless with access to the source model or to
  comparison models. Justification: the model-equipped posture (goal.md reframe).
- **FR-38** (MVP) The tool MUST run an investigative comparison across many runs and many models to find a possible watermark. The harness measures its rate (FR-44). Justification: comparison is best-effort, stronger than a passive scan but not a guarantee (research §5).
  <!-- AI review 20260811-003657: gemini, claude, openai -->
- **FR-38a** (MVP) The tool MUST tell the limit of comparison. A cross-model comparison can confuse model style with a watermark, and an undetectable watermark stays undetectable. Justification: honesty (research §5).
- **FR-39** (MVP) The tool MUST make a best-effort estimate of a multi-bit payload
  that could attribute the text to a user. The tool MUST tell the user that the estimate is not a guarantee and is bounded by the undetectability limit. Justification: the
  attribution threat, and the honest limit (research §5, §6).
  <!-- AI review 20260811-003657: gemini, claude -->
- **FR-40** (MVP) The tool MUST bleach a text to defeat an easily-damaged
  user-attribution watermark. The bleach runs blind and does not use the estimate.
  Justification: a blind bleach is honest with Bet 1 and the undetectability limit
  (research §4, §5).
  <!-- AI review 20260811-003657: claude -->

<!-- FR-41 removed 20260812 (see VIBE_HISTORY). -->

- **FR-42** (MVP) The tool MUST give model-based bleaching in addition to
  deterministic bleaching. Justification: model-based methods are a first-class
  bleach lever (goal.md reframe).
- **FR-43** (MVP) The tool SHOULD use NPU or GPU acceleration when the host has it.
  Justification: local model inference is heavy (goal.md reframe).
- **FR-44** (MVP) The tool MUST give an effectiveness harness. The harness makes
  watermarked samples with reference generators or test keys, attacks them, and
  measures the detection and bleach rates. Justification: the tool has no key, so
  it uses a reference generator to make a sample (goal.md reframe).
  <!-- AI review 20260811-003657: claude -->

### 1.9 Source code detection and control-model comparison

<!-- reframe 20260811: Ron -->

- **FR-45** (MVP) The tool MUST detect a watermark and a carrier in source code,
  not only in prose. Justification: code is a text surface with its own carriers
  (research §7, Trojan Source) and a low-entropy structure.
- **FR-46** (MVP) The tool MUST give a repeated-generation method for code. The
  method tells a model to write a well-known function many times, then it looks
  for odd variability across the runs. Justification: canonical code has a small
  variation space, so a watermark bias stands out (goal.md reframe).
- **FR-46a** (MVP) The code method MUST constrain the generation. It sets or
  limits the variable and function names and the structure. This forces a
  watermarking model to encode its bits in a small space, so the change is more
  obvious. The tool MUST NOT force the full output, because a forced token carries
  no watermark. Justification: a smaller cover makes the signal clearer
  (research §3, goal.md reframe).
- **FR-47** (MVP) The comparison MUST use a control model as the baseline. A
  control model is a model that tells it adds no watermark, or a local model. The
  differential variability between the control and a watermarked model is the
  signal. Justification: a control gives the null distribution (research §5).
- **FR-48** (MVP) The tool MUST hold the "no watermark" claim of a control model
  as unverified. The tool MUST re-check the claim at intervals. Justification: a claim
  is not proof, and a model can change (goal.md reframe).

### 1.10 Length-aware confidence

<!-- reframe 20260811: Ron -->

- **FR-49** (MVP) The tool MUST report a confidence that depends on the text
  length. Detectability scales with length, and high-confidence attribution uses
  more than 400 words. A shorter generation is not useful. Justification: the
  signal grows with the square root of the token count (research §3, §5).
- **FR-50** (MVP) The tool MUST report low confidence for a text below the
  attribution length. The tool MUST NOT overclaim on a short text. Justification:
  a short text carries a weak signal (research §3, §5).
- **FR-51** (MVP) The tool MAY suggest a length mitigation. A shorter text or a
  divided text falls below the reliable-attribution length. Justification: length is
  a defensive lever for a source at risk (VISION §2).

### 1.11 Real-model adapter and canonical code probe

<!-- build 20260811: Ron -->

- **FR-52** (MVP) The tool MUST give a provider adapter. The adapter turns a
  provider into a callable that takes a prompt and gives text. Justification: the
  validated pipeline must run against a provider model (goal.md reframe, IR-01).
- **FR-53** (MVP) The code probe MUST canonicalize each generation. It parses the
  code to a syntax tree, renames each local identifier, and unparses. This removes
  the name, whitespace, comment, and literal-format channels. Justification: the
  probe must minimize the places a watermark can hide (FR-46a).
- **FR-54** (MVP) The code probe MUST measure the residual variability after
  canonicalization, so the signal is structural token choice, not the code format.
  Justification: a watermark works in the residual channel (FR-46a).
- **FR-55** (MVP) Each code-probe generation MUST be more than 400 words. A
  short function is not useful. The probe asks for a complete module, not one
  small function. Justification: attribution and the z-test use length
  (FR-49).
- **FR-61** (MVP) The tool MUST give a context-keyed signature detector. It
  measures if a model picks one option decisively at each context, and if the
  winner changes across contexts. Justification: a watermark is context-keyed, but
  a style favorite stays the same (research §3, §5).

  <!-- build 20260811: Ron -->

- **FR-62** (MVP) The tool MUST tell the honest limit for a provider model. No
  keyless probe gave a confound-free watermark signal on a production model.
  Justification: the undetectability wall holds (research §5, Christ and others).

### 1.12 Adversarial training and evolution

<!-- build 20260811: Ron -->

- **FR-56** (MVP) The tool MUST give an evolution loop. The loop evolves prompt
  strategies and detectors against a known stego modality. Justification: the tool
  must learn a prompt and detector that make the stego easier to detect.
- **FR-57** (MVP) The embedder MUST use a known stego modality, such as the
  green-list scheme. Justification: the loop needs a ground-truth watermark.
- **FR-58** (MVP) The detector MUST estimate the stego partition from samples, and
  it MUST report a partition-recovery rate. Justification: partition recovery
  is key recovery for this modality (watermark stealing, research §5).
- **FR-59** (MVP) The fitness MUST reward detection separation and partition
  recovery, and it MUST penalize a false-positive result. Justification: the loop must
  select a config that detects cleanly and steals the key.
- **FR-60** (MVP) The fitness MUST go up across the generations, and
  the tool MUST record the fitness of each generation. Justification: the tool must
  show that the training works.

---

## 2. Non-functional requirements (NFR)

- **NFR-01** (MVP) The keyless carrier scan MUST process a minimum of 1 MB of text
  each second on one core, with no model in the path. The mixed-script test is a
  softer target (ARCHITECTURE §18). Justification: pipeline throughput.
  <!-- AI review 20260810-234903: gemini, claude -->
- **NFR-02** (MVP) The tool MUST run the core detect path with no network call.
  Justification: local-first and data safety.
- **NFR-03** (MVP) A heavy dependency MUST sit behind an optional install group.
  Justification: the core stays light (research §4, model is optional).
- **NFR-04** (MVP) The tool MUST run on Windows and on POSIX systems.
  Justification: the owner host is Windows. Users run Linux.

---

## 3. Security requirements (SR)

- **SR-01** (MVP) The tool MUST use all input text as untrusted data.
  Justification: input can hold an injection payload (research §6).
- **SR-02** (MVP) The tool MUST NOT run or transmit a decoded hidden payload.
  Justification: a payload can hold a command (research §6).
- **SR-03** (MVP) The tool MUST NOT write an API key or a secret to a report, a
  log, stdout, or an output stream. Justification: secret hygiene.
  <!-- AI review 20260810-234903: claude -->
- **SR-04** (MVP) The tool MUST read a model API key only from an environment
  variable or a key file. Justification: no secret in source or in a report.
- **SR-05** (MVP) The tool MUST label a covert-channel result as a possible
  prompt-injection vector. Justification: the defensive purpose (VISION §1).
- **SR-06** (MVP) The tool MUST run the deterministic carrier bleach and remove all
  hidden carriers before it sends the text to a model. Justification: a smuggled
  payload must not get to the paraphrase model (research §6, §7.2).
  <!-- AI review 20260810-234903: gemini, claude -->
- **SR-07** (MVP) The tool MUST redact a decoded payload in a report by default.
  The report shows the payload length and a hash, not the cleartext. Justification:
  a cleartext payload re-delivers the injection (research §6).
  <!-- AI review 20260810-234903: gemini, claude -->
- **SR-08** (MVP) The tool MUST gate the cleartext payload behind an explicit flag
  with a warning. Justification: safe examination of the payload.
- **SR-09** (MVP) Every model-bound path MUST go through one model gateway that runs the carrier normalization first and stops the call on an error. Justification: SR-06 must have one choke-point, not a rule across five call sites.
  <!-- AI review 20260811-003657: gemini, xai, claude, openai -->
- **SR-10** (MVP) The harness MAY send an unsanitized sample to a model only in an isolated sandbox, not to an API. The tool MUST record each such call.
  Justification: the harness uses raw samples, but the tool must audit the exception.
  <!-- AI review 20260811-003657: claude -->

---

## 4. Integration requirements (IR)

- **IR-01** (MVP) The tool MUST let the user configure a paraphrase model as a
  local runtime or an API. An API model is opt-in and gives a data-egress warning.
  Justification: the paraphrase bleach uses a model, and an API sends untrusted text
  off the host (research §4).
  <!-- AI review 20260810-234903: claude -->
- **IR-02** (MVP) The tool MUST accept a tokenizer for the keyed z-test.
  Justification: the green-list test uses the tokenizer (research §3).
- **IR-03** (MVP) The tool MUST accept a SynthID secret key and configuration
  object. Justification: SynthID-Text detection uses the key and the configuration
  (research §4).
  <!-- AI review 20260810-234903: gemini, mistral, claude -->
- **IR-04** (MVP) The tool MUST accept a query function to the source model for
  the active test. Justification: FR-21 uses the query function, so the two must
  have the same scope (research §5).
  <!-- AI review 20260811-003657: openai -->

---

## 5. Data requirements (DR)

- **DR-01** (MVP) The tool MUST NOT store input text longer than the run needs.
  Justification: data minimization.
- **DR-02** (MVP) The JSON report schema MUST have a version field.
  Justification: the schema changes with time.
- **DR-03** (MVP) The tool MUST classify a decoded payload as sensitive data and
  redact it in a report by default (SR-07). Justification: a payload can hold PII
  or a secret (research §6).

---

## 6. Observability requirements (OR)

- **OR-01** (MVP) The tool MUST log each detection step at a selectable level.
  Justification: debug and audit.
- **OR-02** (MVP) The tool MUST record the method and the parameters for each
  score. Justification: reproducible statistics.
- **OR-03** (MVP) The tool MUST NOT log the decoded payload content at the default
  level. Justification: SR-02 and DR-03.

---

## 7. Operational requirements

- **OP-01** (MVP) The tool MUST run as a single command with no service.
  Justification: simple first use.
- **OP-02** (MVP) The install MUST succeed with a core install group and no model.
  Justification: fast first run (NFR-03).
- **OP-03** (SCALE) The tool MAY run as a local service for pipeline integration.
  Justification: the Year 3 arc (VISION §5).

---

## 8. Architectural requirements (AR)

- **AR-01** (MVP) The architecture MUST keep detection apart from bleaching.
  Justification: removal is stronger than detection (VISION §4, Bet 1).
- **AR-02** (MVP) The architecture MUST keep the keyless path apart from the keyed
  and active paths. Justification: different posture and dependencies (FR-22).
- **AR-03** (MVP) Each detector MUST give a calibrated score and a stated
  false-positive rate through one interface. Justification: honest reporting
  (research §5).
- **AR-04** (MVP) A new carrier or scheme MUST connect as a module.
  Justification: the field adds new schemes (VISION §5).

---

## 9. Maintainability requirements (MR)

- **MR-01** (MVP) Each detector and each bleach method MUST live in its own module.
  Justification: change velocity.
- **MR-02** (MVP) The codepoint sets MUST live in data files, not in code.
  Justification: Unicode updates (research §7).
- **MR-03** (MVP) The code build MUST run a linter and a type check with no error.
  Justification: code health.

---

## 10. Testing requirements (TR)

- **TR-01** (MVP) The tool MUST have a fixture corpus of watermarked and clean
  text. Justification: detection tests on watermarked and clean data.
- **TR-02** (MVP) Each carrier detector MUST have a positive fixture and a
  legitimate-use fixture. Justification: false-positive control (research §7.7).
- **TR-03** (MVP) The bleach tests MUST measure detection before and after and the
  meaning score. Justification: proof the bleach works (research §4).
- **TR-04** (MVP) A stated success MUST come from a detection run that gives data, not a stub.
  Justification: the anti-stub rule (SUCCESS_CRITERIA §4).
- **TR-05** (SCALE) The benchmark MUST run known schemes and report the measured
  drop for each bleach strength. Justification: the Year 2 arc (VISION §5).

---

## 11. Out of scope

- **OOS-01** The tool does not check or repair C2PA file provenance. C2PA is
  signed metadata, not a text signal (research §6). Re-entry: a different metadata
  component.
- **OOS-02** The tool does not cover image, audio, or video steganography. The
  surface is text statistics (VISION §6). Re-entry: none planned.
- **OOS-03** The tool does not claim to detect the Anthropic text watermark while
  no public specification is available (research §6). Re-entry: when Anthropic
  publishes a detector or a specification.
- **OOS-04** The tool does not do plagiarism or academic-integrity detection
  (VISION §6). Re-entry: none planned.
- **OOS-05** The tool does not promise to remove a cryptographically undetectable
  watermark (research §4, Christ and others). Re-entry: none, the limit is formal.
