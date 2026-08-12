"""Live bleach with a compile-and-test meaning gate (FR-25, FR-26, FR-27, SR-06).

This runs the bleach on a configured model and measures the meaning gate, not a model
of it. The flow for one code task:

1. The model writes the function. In the threat model this output can carry a
   watermark, so it is the bleach input.
2. The deterministic carrier bleach runs on the input before the model sees it again
   (SR-06). A smuggled carrier does not get to the model.
3. The bleach asks the model to regenerate the function with a different structure but
   the same behavior. This is the natural-target bleach: a paraphrase.
4. The functional gate compiles the bleached code and runs a unit test. If the bleached
   function compiles and passes every case, the meaning is kept. This is a measured
   gate, stronger than a token-similarity proxy.
5. The probe measures the structural change between the input and the bleach, after
   canonicalization. A watermark rides on structure, so structural change is the
   removal proxy. It is a proxy, not a proof, because the tool holds no key.

The gate runs the model code in a subprocess with a timeout, never in this process. The
tool does not run a decoded payload (SR-02); it compiles and runs only the sanitized
function under test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from ..detect.code import _strip_fences, _residual_variability, structural_normalize
from ..detect.features import featurize
from ..detect.partition_test import steal_and_test
from .normalize import normalize_carriers

_SCRATCH = os.environ.get("BLEACHMARK_SCRATCH") or tempfile.gettempdir()


@dataclass
class Task:
    name: str
    params: int              # 1 or 2 integer parameters
    cases: list              # list of (args_tuple, expected_int)
    desc: str                # the natural-language task for the prompt


TASKS: list[Task] = [
    Task("is_prime", 1, [((2,), 1), ((3,), 1), ((4,), 0), ((1,), 0), ((17,), 1), ((18,), 0), ((97,), 1)],
         "return 1 if the integer is prime, else 0"),
    Task("gcd", 2, [((12, 8), 4), ((100, 75), 25), ((17, 5), 1), ((48, 36), 12), ((7, 7), 7)],
         "return the greatest common divisor of the two integers"),
    Task("fib", 1, [((0,), 0), ((1,), 1), ((2,), 1), ((10,), 55), ((15,), 610), ((20,), 6765)],
         "return the nth Fibonacci number (fib(0)=0, fib(1)=1)"),
    Task("factorial", 1, [((0,), 1), ((1,), 1), ((5,), 120), ((6,), 720), ((9,), 362880)],
         "return the factorial of the integer"),
]


def _sig_py(task: Task) -> str:
    return "def solve(a):" if task.params == 1 else "def solve(a, b):"


def _sig_c(task: Task) -> str:
    return "int solve(int a)" if task.params == 1 else "int solve(int a, int b)"


# --- functional gate: compile and run a unit test in a subprocess -------------


@dataclass
class GateResult:
    compiles: bool
    passes: bool
    detail: str


def _run(cmd: list[str], cwd: str, timeout: int = 15, stdin: str | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:  # missing compiler, etc.
        return 125, "", f"{type(exc).__name__}: {exc}"


def _py_harness(task: Task) -> str:
    lines = ["", "import sys"]
    for args, exp in task.cases:
        call = f"solve({', '.join(str(a) for a in args)})"
        lines.append(f"assert int({call}) == {exp}, ('FAIL', {args!r}, {call})")
    lines.append("print('OK')")
    return "\n".join(lines)


def check_python(code: str, task: Task) -> GateResult:
    code = _strip_fences(code)
    src = code + "\n" + _py_harness(task)
    with tempfile.TemporaryDirectory(dir=_SCRATCH) as d:
        path = os.path.join(d, "prog.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        rc, out, err = _run([sys.executable, path], cwd=d)
    if rc == 0 and "OK" in out:
        return GateResult(True, True, "ok")
    # a syntax error means it did not compile; anything else is a failed test
    compiles = "SyntaxError" not in err
    return GateResult(compiles, False, (err or out).strip().splitlines()[-1] if (err or out).strip() else "no output")


def _c_harness(task: Task) -> str:
    # The exit code carries the result, so the harness needs no headers and no library
    # calls. A pure-arithmetic function then compiles with no include path.
    checks = []
    for i, (args, exp) in enumerate(task.cases, start=1):
        call = f"solve({', '.join(str(a) for a in args)})"
        checks.append(f"    if ({call} != {exp}) return {i};")
    body = "\n".join(checks)
    return "\nint main(void) {\n" + body + "\n    return 0;\n}\n"


def check_c(code: str, task: Task, compiler: str = "gcc") -> GateResult:
    code = _strip_fences(code)
    src = code + "\n" + _c_harness(task)
    with tempfile.TemporaryDirectory(dir=_SCRATCH) as d:
        cpath = os.path.join(d, "prog.c")
        opath = os.path.join(d, "prog.exe")
        with open(cpath, "w", encoding="utf-8") as fh:
            fh.write(src)
        rc, out, err = _run([compiler, cpath, "-o", opath, "-w"], cwd=d, timeout=30)
        if rc == 125:
            return GateResult(False, False, "no compiler")
        if rc != 0:
            tail = err.strip().splitlines()[-1] if err.strip() else "compile failed"
            return GateResult(False, False, tail)
        rc2, out2, err2 = _run([opath], cwd=d)
    if rc2 == 0:
        return GateResult(True, True, "ok")
    return GateResult(True, False, f"failed case {rc2}" if 0 < rc2 < 250 else (err2 or "run error").strip())


def functional_gate(code: str, task: Task, lang: str) -> GateResult:
    return check_c(code, task) if lang == "c" else check_python(code, task)


# --- the live bleach ----------------------------------------------------------


def gen_prompt(task: Task, lang: str, tight: bool = True) -> str:
    sig = _sig_c(task) if lang == "c" else _sig_py(task)
    verb = "a C function" if lang == "c" else "a Python function"
    tail = " No includes." if lang == "c" else ""
    # a light prompt leaves the natural structural variation in place, so the
    # deterministic normalizer has operand-order and comparison slots to close
    style = " Iterative where you can." if tight else ""
    return f"Write {verb}: {sig} that will {task.desc}.{style}{tail} Return only the code."


def deterministic_bleach(code: str, lang: str) -> str:
    """The deterministic corpus bleach: close the structural slots with no model call.

    For Python it normalizes the AST (commutative operand order, comparison direction).
    C has no standard-library parser, so the C arm returns the code unchanged and needs a
    C parser to normalize structure (a known limit).
    """
    if lang == "c":
        return code
    return structural_normalize(code)


def bleach_prompt(task: Task, lang: str, original: str, mode: str = "diversify") -> str:
    sig = _sig_c(task) if lang == "c" else _sig_py(task)
    lang_name = "C" if lang == "c" else "Python"
    if mode == "canonical":
        # Drive every sample toward ONE textbook form, so the corpus converges and the
        # residual structural channel closes. This is the corpus-level bleach.
        return (
            f"Rewrite this {lang_name} function as the single most standard, textbook "
            f"implementation, with the signature {sig}. Use the conventional loop and the "
            f"conventional local names a, b, c. Do not vary the structure and do not add "
            f"cleverness or comments. Write it the way it is most commonly written. Return "
            f"only the code.\n\n{original}"
        )
    return (
        f"Rewrite this {lang_name} function with a DIFFERENT internal structure but the "
        f"exact same behavior and the same signature {sig}. Change the operand order, the "
        f"loop style, the temporaries, and the statement order where you can. Do not add "
        f"comments. Return only the code.\n\n{original}"
    )


@dataclass
class BleachTaskResult:
    task: str
    lang: str
    original_ok: bool
    bleached_ok: bool           # the meaning gate: bleach compiles and passes the test
    meaning_preserved: bool
    changed: bool               # the bleach actually altered the canonical structure
    structural_change: float    # canonical residual distance, input vs bleach
    attempts: int
    note: str = ""


def _try_bleach(model_fn, task: Task, lang: str, original: str, attempts: int, mode: str = "diversify"):
    """Return (bleached_code, gate, change, attempts_used).

    bleached_code is the accepted rewrite, else None. The diversify mode needs the
    rewrite to change the structure. The canonical mode does not: it wants the sample to
    converge to one form, so a rewrite that is already canonical is fine.
    """
    require_change = mode == "diversify"
    gate = None
    change = 0.0
    for i in range(attempts):
        bleached = normalize_carriers(model_fn(bleach_prompt(task, lang, original, mode)))
        gate = functional_gate(bleached, task, lang)
        change = _residual_variability([original, bleached], lang)
        changed = _strip_fences(bleached).strip() != _strip_fences(original).strip()
        if gate.passes and (changed or not require_change):
            return bleached, gate, round(change, 4), i + 1
    return None, gate, round(change, 4), attempts


def bleach_task(model_fn, task: Task, lang: str, attempts: int = 2, mode: str = "diversify") -> BleachTaskResult:
    # 1) generate the (possibly watermarked) input, then sanitize it (SR-06)
    original = normalize_carriers(model_fn(gen_prompt(task, lang)))
    orig_gate = functional_gate(original, task, lang)
    if not orig_gate.passes:
        return BleachTaskResult(task.name, lang, False, False, False, False, 0.0, 0,
                                note=f"original failed the gate: {orig_gate.detail}")
    bleached, gate, change, used = _try_bleach(model_fn, task, lang, original, attempts, mode)
    ok = bleached is not None
    return BleachTaskResult(
        task.name, lang, True, ok, ok, ok, change, used,
        note="ok" if ok else f"bleach failed the gate: {gate.detail if gate else 'n/a'}",
    )


# --- the steal-and-test gap before and after the bleach -----------------------


@dataclass
class GapResult:
    task: str
    lang: str
    mode: str                   # "diversify" or "canonical"
    n_valid: int
    bleached_rate: float        # fraction of the corpus a meaning-preserving bleach reached
    slots_before: int
    slots_after: int
    gap_before: float
    gap_after: float
    z_before: float
    z_after: float
    p_before: float
    p_after: float
    note: str = ""


def bleach_gap(model_fn, task: Task, lang: str, n_samples: int = 24, k: int = 4,
               attempts: int = 2, mode: str = "diversify") -> GapResult:
    """Measure the steal-and-test gap on a corpus before and after the bleach.

    The gap is the slot-specific structural signal a corpus watermark rides on. The
    diversify bleach rewrites each sample with a different structure. The canonical bleach
    rewrites each sample toward one textbook form, so the corpus converges and the residual
    channel closes. A meaning-preserving bleach keeps the compile-and-test gate. If a
    bleach breaks the code, the original stays, so the corpus is always meaning-valid.
    """
    originals = [normalize_carriers(model_fn(gen_prompt(task, lang))) for _ in range(n_samples)]
    valid = [o for o in originals if functional_gate(o, task, lang).passes]
    if len(valid) < 4:
        return GapResult(task.name, lang, mode, len(valid), 0.0, 0, 0, 0, 0, 0, 0, 1, 1,
                         note="too few valid samples for a partition test")

    bleached_corpus: list[str] = []
    n_bleached = 0
    for o in valid:
        b, _gate, _chg, _used = _try_bleach(model_fn, task, lang, o, attempts, mode)
        if b is not None:
            bleached_corpus.append(b)
            n_bleached += 1
        else:
            bleached_corpus.append(o)  # keep the meaning-valid original when the bleach fails

    fm_b = featurize(valid, lang, k=k)
    fm_a = featurize(bleached_corpus, lang, k=k)
    rb = steal_and_test(fm_b.rows, fm_b.k, fm_b.n_slots, permutations=300, seed=0) if fm_b.n_slots >= 2 else None
    ra = steal_and_test(fm_a.rows, fm_a.k, fm_a.n_slots, permutations=300, seed=0) if fm_a.n_slots >= 2 else None
    note = "ok"
    if fm_b.n_slots < 2:
        note = "no channel before the bleach"
    elif fm_a.n_slots < 2:
        note = "channel closed after the bleach"
    return GapResult(
        task.name, lang, mode, len(valid), round(n_bleached / len(valid), 3),
        fm_b.n_slots, fm_a.n_slots,
        round(rb.gap, 3) if rb else 0.0, round(ra.gap, 3) if ra else 0.0,
        round(rb.z_true, 3) if rb else 0.0, round(ra.z_true, 3) if ra else 0.0,
        round(rb.p_value, 4) if rb else 1.0, round(ra.p_value, 4) if ra else 1.0,
        note=note,
    )


def _gap_of(corpus: list[str], lang: str, k: int = 4):
    """Featurize a corpus and return (n_slots, gap, z_true, p_value)."""
    fm = featurize(corpus, lang, k=k)
    if fm.n_slots < 2:
        return fm.n_slots, 0.0, 0.0, 1.0
    r = steal_and_test(fm.rows, fm.k, fm.n_slots, permutations=300, seed=0)
    return fm.n_slots, round(r.gap, 3), round(r.z_true, 3), round(r.p_value, 4)


def compare_bleach_modes(model_fn, task: Task, lang: str, n_samples: int = 20, k: int = 4,
                         attempts: int = 2) -> dict:
    """Bleach ONE corpus three ways and measure the gap for each, on a shared before.

    The corpus is generated once with a light prompt, so the natural structural variation
    stays. Then the same corpus is measured three ways: as generated, after the diversify
    bleach (a model rewrite), and after the deterministic bleach (the structural
    normalizer, no model call). Every corpus stays meaning-valid: a bleach that breaks the
    gate falls back to the original sample.
    """
    originals = [normalize_carriers(model_fn(gen_prompt(task, lang, tight=False))) for _ in range(n_samples)]
    valid = [o for o in originals if functional_gate(o, task, lang).passes]
    if len(valid) < 4:
        return {"task": task.name, "lang": lang, "n_valid": len(valid),
                "note": "too few valid samples for a partition test"}

    # deterministic bleach: no model call; verify each still passes the gate
    det_corpus, det_kept = [], 0
    for o in valid:
        b = deterministic_bleach(o, lang)
        if functional_gate(b, task, lang).passes:
            det_corpus.append(b)
            det_kept += 1
        else:
            det_corpus.append(o)

    # diversify bleach: a model rewrite per sample
    div_corpus, div_kept = [], 0
    for o in valid:
        b, _g, _c, _u = _try_bleach(model_fn, task, lang, o, attempts, "diversify")
        if b is not None:
            div_corpus.append(b)
            div_kept += 1
        else:
            div_corpus.append(o)

    s0, g0, z0, p0 = _gap_of(valid, lang, k)
    sd, gd, zd, pd = _gap_of(det_corpus, lang, k)
    sv, gv, zv, pv = _gap_of(div_corpus, lang, k)
    return {
        "task": task.name,
        "lang": lang,
        "n_valid": len(valid),
        "original": {"slots": s0, "gap": g0, "z": z0, "p": p0},
        "deterministic": {"slots": sd, "gap": gd, "z": zd, "p": pd,
                          "meaning_kept_rate": round(det_kept / len(valid), 3)},
        "diversify": {"slots": sv, "gap": gv, "z": zv, "p": pv,
                      "meaning_kept_rate": round(div_kept / len(valid), 3)},
    }


def run_style_calibration(candidate_provider: str, reference_providers: list[str], task: Task,
                          lang: str = "python", n_samples: int = 16, root: str = ".",
                          k: int = 4, alpha: float = 0.05,
                          model_factory=None) -> dict:
    """Calibrate a style baseline from reference models and score the candidate model.

    The candidate is the model the tool checks for a watermark. The references are models
    the tool treats as unwatermarked. Every corpus is generated at the same size with a
    light prompt, so the structural style is in place. The result is a false-positive rate
    against the reference style, not a yes-or-no verdict (FR-14, FR-15).
    """
    from ..runtime.providers import make_model, DEFAULT_MODELS
    from ..detect.calibrate import calibrate_from_code

    if model_factory is None:
        model_factory = make_model

    def corpus(provider: str) -> list[str]:
        fn = model_factory(provider, root=root, temperature=1.0, max_tokens=500)
        return [normalize_carriers(fn(gen_prompt(task, lang, tight=False))) for _ in range(n_samples)]

    try:
        candidate = corpus(candidate_provider)
        references, used = [], []
        for rp in reference_providers:
            try:
                references.append(corpus(rp))
                used.append(f"{rp}:{DEFAULT_MODELS.get(rp, '')}")
            except Exception as exc:  # a reference provider may fail; keep the others
                used.append(f"{rp}: ERROR {type(exc).__name__}")
        live_refs = [c for c in references if c]
        if not live_refs:
            return {"ok": False, "error": "no reference corpus was generated"}
        finding = calibrate_from_code(candidate, live_refs, lang, k=k, alpha=alpha,
                                      sources=used)
        return {
            "ok": True,
            "task": task.name,
            "lang": lang,
            "candidate": f"{candidate_provider}:{DEFAULT_MODELS.get(candidate_provider, '')}",
            "references": used,
            "n_samples": n_samples,
            "finding": finding.__dict__,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


PROSE_TOPICS = [
    "cities should expand protected bike lanes",
    "public libraries deserve more funding",
    "remote work is good for the economy",
    "schools should start later in the morning",
    "cities should plant more street trees",
    "public transit should be free at the point of use",
    "governments should invest in flood defenses",
    "small towns need faster internet",
    "museums should stay free to enter",
    "cities should cap short-term rentals",
    "universities should teach more statistics",
    "local news deserves public support",
    "parks are worth the maintenance cost",
    "recycling programs should be simplified",
    "cities should widen sidewalks downtown",
    "night trains should return to the region",
    "farmers markets strengthen local economies",
    "coding should be taught in primary school",
    "streetlights should switch to warmer light",
    "the city should protect its old cinemas",
    "apprenticeships deserve the same respect as degrees",
    "cities should meter downtown parking",
    "rivers in the region should be cleaned up",
    "the school day should include more time outdoors",
    "public swimming pools should stay open all year",
    "the region needs more affordable housing",
    "voting should be easier for shift workers",
    "food waste should be composted at the curb",
    "the town should bury its power lines",
    "sports fields should be shared with the public",
    "the region should protect its dark night skies",
    "clinics should open on weekends",
]


def run_prose_calibration(candidate_provider: str, reference_providers: list[str],
                          n_samples: int = 16, root: str = ".", min_words: int = 400,
                          alpha: float = 0.05, model_factory=None) -> dict:
    """Dense prose detection: score a candidate model against a reference style baseline (FR-14/15).

    Each model writes one editorial for each of several varied topics, so the shared structure is
    the language and any watermark, not the topic. The tool tokenizes the editorials and scores the
    candidate context-structure gap as a false-positive rate against the reference models. Prose
    needs a dense corpus, so this uses many long samples.
    """
    from ..runtime.providers import make_model, DEFAULT_MODELS
    from ..detect.prose import prose_tokens, calibrate_prose

    if model_factory is None:
        model_factory = make_model
    topics = PROSE_TOPICS[:n_samples]

    def _spec(ref: str):
        # a reference is "provider" or "provider:model" (a pre-cutoff or a local model)
        provider, _, model = ref.partition(":")
        return provider, (model or None)

    def _label(provider: str, model) -> str:
        if provider == "local" and not model:
            try:  # name the model the local engine actually serves, not the default
                from ..runtime.providers import list_local_models
                served = list_local_models()
                model = served[0] if served else None
            except Exception:
                pass
        return f"{provider}:{model or DEFAULT_MODELS.get(provider, '')}"

    def corpus(provider: str, model=None) -> list[list[str]]:
        fn = model_factory(provider, model=model, root=root, temperature=1.0, max_tokens=1200)
        out = []
        for topic in topics:
            text = normalize_carriers(fn(
                f"Write an editorial of at least {min_words} words arguing that {topic}. "
                "Return only the prose."))
            out.append(prose_tokens(text))
        return out

    try:
        candidate = corpus(candidate_provider)
        references, used = [], []
        for rp in reference_providers:
            provider, model = _spec(rp)
            try:
                references.append(corpus(provider, model))
                used.append(_label(provider, model))
            except Exception as exc:
                used.append(f"{_label(provider, model)}: ERROR {type(exc).__name__}")
        live_refs = [c for c in references if c]
        if not live_refs:
            return {"ok": False, "error": "no reference corpus was generated"}
        finding = calibrate_prose(candidate, live_refs, alpha=alpha, sources=used)
        cand_words = sum(len(s) for s in candidate)
        return {
            "ok": True,
            "task": "prose editorials",
            "lang": "english",
            "candidate": f"{candidate_provider}:{DEFAULT_MODELS.get(candidate_provider, '')}",
            "references": used,
            "n_samples": n_samples,
            "candidate_words": cand_words,
            "finding": finding.__dict__,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


