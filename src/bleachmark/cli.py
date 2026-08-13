"""BleachMark CLI: detect, bleach, report (FR-34, FR-36).

The exit code is non-zero only for a high-confidence carrier finding. A
machine-generation score never drives the exit code (FR-36).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import detect_carriers
from .bleach import bleach as bleach_text
from .report.json_emit import to_json
from .report.markdown_emit import to_markdown
from .report.calibration_emit import to_json_calibration, to_markdown_calibration


def _read_input(path: str | None) -> str:
    # the input is hostile and may hold malformed bytes; decode without crashing
    # (replace bad bytes) rather than dumping a traceback
    if path and path != "-":
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return sys.stdin.buffer.read().decode("utf-8", errors="replace")


def _cmd_detect(args) -> int:
    text = _read_input(args.file)
    if args.show_payload:
        sys.stderr.write(
            "WARNING: --show-payload prints decoded payload cleartext; "
            "do not paste it where it could execute (SR-08).\n"
        )
    report = detect_carriers(text, target=args.file or "<stdin>")
    if args.json:
        print(to_json(report, show_payload=args.show_payload))
    else:
        print(to_markdown(report, show_payload=args.show_payload))
    # FR-36: exit non-zero only on a high-confidence carrier
    return 2 if report.high_confidence_carriers() else 0


def _cmd_bleach(args) -> int:
    text = _read_input(args.file)
    if getattr(args, "translate", False):
        from .bleach.translate import roundtrip_bleach

        result = roundtrip_bleach(text)
    else:
        result = bleach_text(text, strength=args.strength)
    if args.json:
        import json

        print(
            json.dumps(
                {
                    "strength": result.strength,
                    "accepted": result.accepted,
                    "meaning_score": result.meaning_score,
                    "message": result.message,
                },
                indent=2,
            )
        )
        if result.accepted:
            sys.stderr.write(result.text)
    else:
        sys.stdout.write(result.text)
    return 0 if result.accepted else 1


def _cmd_report(args) -> int:
    args.json = False
    args.show_payload = getattr(args, "show_payload", False)
    return _cmd_detect(args)


def _cmd_calibrate_code(args) -> int:
    """Score a candidate model for a code watermark, calibrated against reference models.

    This is a model-equipped probe, not a text scan. It emits a false-positive rate against
    a reference style baseline. The rate never drives the exit code, because a statistical
    score is not a verdict (FR-14, FR-15, FR-36). The exit code is non-zero only when the
    probe cannot run.
    """
    from .bleach.live import run_style_calibration, TASKS

    tasks = {t.name: t for t in TASKS}
    if args.task not in tasks:
        sys.stderr.write(f"unknown task '{args.task}'. choices: {', '.join(sorted(tasks))}\n")
        return 1
    references = [r.strip() for r in args.references.split(",") if r.strip()]
    if not references:
        sys.stderr.write("at least one reference model is required (--references)\n")
        return 1

    result = run_style_calibration(
        candidate_provider=args.candidate,
        reference_providers=references,
        task=tasks[args.task],
        lang=args.lang,
        n_samples=args.samples,
        root=args.root,
        alpha=args.alpha,
    )
    if args.json:
        print(to_json_calibration(result))
    else:
        print(to_markdown_calibration(result))
    # a statistical score never drives the exit code; non-zero only on an operational failure
    return 0 if result.get("ok") else 1


def _cmd_calibrate_prose(args) -> int:
    """Score a candidate model for a prose watermark, calibrated against reference models.

    Like calibrate-code, the rate never drives the exit code (FR-36); the exit is non-zero only
    when the probe cannot run.
    """
    from .bleach.live import run_prose_calibration

    references = [r.strip() for r in args.references.split(",") if r.strip()]
    if not references:
        sys.stderr.write("at least one reference model is required (--references)\n")
        return 1
    result = run_prose_calibration(
        candidate_provider=args.candidate,
        reference_providers=references,
        n_samples=args.samples,
        root=args.root,
        alpha=args.alpha,
        min_words=args.min_words,
    )
    if args.json:
        print(to_json_calibration(result))
    else:
        print(to_markdown_calibration(result))
    return 0 if result.get("ok") else 1


def _hardware_report(root: str = ".") -> dict:
    from .runtime.hardware import detect_hardware
    from .runtime.models import recommend
    from .runtime.providers import local_base_url, list_local_models

    prof = detect_hardware()
    best = prof.best_gpu()
    budget = best.vram_total_mb if best else 0
    rec = recommend(budget) if budget else {}
    url = local_base_url()
    served, reachable, err = [], False, ""
    try:
        served = list_local_models(url)
        reachable = True
    except Exception as exc:
        err = type(exc).__name__
    return {
        "hardware": prof.summary(),
        "endpoint": {"url": url, "reachable": reachable, "served_models": served, "error": err},
        "recommended": {
            fn: {
                "model": s.model.name if s.model else None,
                "fits": s.fits,
                "vram_mb": s.model.vram_mb() if s.model else None,
                "hf_repo": s.model.hf_repo if s.model else None,
                "note": s.note,
            } for fn, s in rec.items()
        },
    }


def _hardware_markdown(r: dict) -> str:
    hw = r["hardware"]
    gpu = hw["gpu"]
    ep = r["endpoint"]
    lines = ["# BleachMark local inference", ""]
    lines.append("## Detected hardware")
    lines.append(f"- Accelerator: {hw['accelerator']}")
    if gpu:
        lines.append(f"- GPU: {gpu['name']} ({gpu['vram_total_mb']} MB total, "
                     f"{gpu['vram_free_mb']} MB free), driver {gpu['driver']}, CUDA {hw['cuda_version']}")
    else:
        lines.append("- GPU: none detected")
    lines.append(f"- CPU cores: {hw['cpu_count']}")
    lines.append(f"- RAM: {hw['ram_mb']} MB")
    lines.append("")
    lines.append("## Local inference engine")
    lines.append(f"- Endpoint: {ep['url']}")
    lines.append(f"- Reachable: {'yes' if ep['reachable'] else 'no' + (' (' + ep['error'] + ')' if ep['error'] else '')}")
    if ep["served_models"]:
        lines.append(f"- Served models: {', '.join(ep['served_models'])}")
    lines.append("")
    lines.append(f"## Recommended local models (video-memory budget {hw['total_vram_mb']} MB, estimate)")
    lines.append("")
    lines.append("| Function | Model | Fits | Est. VRAM | Hugging Face repo |")
    lines.append("| --- | --- | --- | --- | --- |")
    for fn, s in r["recommended"].items():
        lines.append(f"| {fn} | {s['model']} | {'yes' if s['fits'] else 'no'} | "
                     f"{s['vram_mb']} MB | {s['hf_repo']} |")
    return "\n".join(lines)


def _cmd_hardware(args) -> int:
    """Detect the host hardware, check the local engine, and recommend local models."""
    report = _hardware_report(root=args.root)
    print(json.dumps(report, indent=2) if args.json else _hardware_markdown(report))
    return 0


def _cmd_benchmark(args) -> int:
    """Run the keyed scheme benchmark and print the BC-04 table (no network)."""
    from .harness.schemes import run_scheme_benchmark, to_markdown_benchmark

    result = run_scheme_benchmark(samples=args.samples, length=args.length)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(to_markdown_benchmark(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleachmark", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("detect", help="detect carriers and hidden signals")
    d.add_argument("file", nargs="?", help="input file, or - for stdin")
    d.add_argument("--json", action="store_true", help="emit the canonical JSON report")
    d.add_argument("--show-payload", action="store_true", help="include cleartext payloads (SR-08)")
    d.set_defaults(func=_cmd_detect)

    b = sub.add_parser("bleach", help="bleach carriers and watermarks")
    b.add_argument("file", nargs="?", help="input file, or - for stdin")
    b.add_argument("--strength", type=int, default=1, help="1 normalize, 2 token, 3 paraphrase")
    b.add_argument("--translate", action="store_true",
                   help="round-trip translation bleach (FR-29)")
    b.add_argument("--json", action="store_true", help="emit a JSON bleach summary")
    b.set_defaults(func=_cmd_bleach)

    r = sub.add_parser("report", help="detect and print a Markdown report")
    r.add_argument("file", nargs="?", help="input file, or - for stdin")
    r.set_defaults(func=_cmd_report)

    c = sub.add_parser("calibrate-code",
                       help="score a model for a code watermark against reference models (FPR)")
    c.add_argument("--candidate", required=True, help="candidate provider (marks at launch)")
    c.add_argument("--references", required=True,
                   help="comma-separated reference providers treated as unwatermarked")
    c.add_argument("--task", default="fib", help="code task (e.g. fib, gcd, is_prime, factorial)")
    c.add_argument("--lang", default="python", choices=["python", "c"])
    c.add_argument("--samples", type=int, default=16, help="samples per corpus")
    c.add_argument("--alpha", type=float, default=0.05, help="the rate below which the gap stands out")
    c.add_argument("--root", default=".", help="root that holds <provider>.key.txt")
    c.add_argument("--json", action="store_true", help="emit the JSON calibration report")
    c.set_defaults(func=_cmd_calibrate_code)

    cp = sub.add_parser("calibrate-prose",
                        help="score a model for a prose watermark against reference models (FPR)")
    cp.add_argument("--candidate", required=True, help="candidate provider (marks at launch)")
    cp.add_argument("--references", required=True,
                    help="comma-separated reference providers treated as unwatermarked")
    cp.add_argument("--samples", type=int, default=16, help="editorials per model (dense corpus)")
    cp.add_argument("--min-words", type=int, default=400,
                    help="each editorial must be more than this many words")
    cp.add_argument("--alpha", type=float, default=0.05, help="the rate below which the gap stands out")
    cp.add_argument("--root", default=".", help="root that holds <provider>.key.txt")
    cp.add_argument("--json", action="store_true", help="emit the JSON calibration report")
    cp.set_defaults(func=_cmd_calibrate_prose)

    hw = sub.add_parser("hardware",
                        help="detect the host hardware, check the local engine, recommend local models")
    hw.add_argument("--json", action="store_true", help="emit the JSON hardware report")
    hw.add_argument("--root", default=".", help="root that holds <provider>.key.txt")
    hw.set_defaults(func=_cmd_hardware)

    bm = sub.add_parser("benchmark", help="scheme benchmark: detectability drop and meaning cost (BC-04)")
    bm.add_argument("--samples", type=int, default=24, help="watermarked samples per cell")
    bm.add_argument("--length", type=int, default=400, help="tokens per sample")
    bm.add_argument("--json", action="store_true", help="emit the canonical JSON table")
    bm.set_defaults(func=_cmd_benchmark)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
