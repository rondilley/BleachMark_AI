"""BleachMark CLI: detect, bleach, report (FR-34, FR-36).

The exit code is non-zero only for a high-confidence carrier finding. A
machine-generation score never drives the exit code (FR-36).
"""

from __future__ import annotations

import argparse
import sys

from . import detect_carriers
from .bleach import bleach as bleach_text
from .report.json_emit import to_json
from .report.markdown_emit import to_markdown
from .report.calibration_emit import to_json_calibration, to_markdown_calibration


def _read_input(path: str | None) -> str:
    if path and path != "-":
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return sys.stdin.read()


def _cmd_detect(args) -> int:
    text = _read_input(args.file)
    report = detect_carriers(text, target=args.file or "<stdin>")
    if args.json:
        print(to_json(report, show_payload=args.show_payload))
    else:
        print(to_markdown(report, show_payload=args.show_payload))
    # FR-36: exit non-zero only on a high-confidence carrier
    return 2 if report.high_confidence_carriers() else 0


def _cmd_bleach(args) -> int:
    text = _read_input(args.file)
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
    cp.add_argument("--min-words", type=int, default=400, help="minimum words per editorial")
    cp.add_argument("--alpha", type=float, default=0.05, help="the rate below which the gap stands out")
    cp.add_argument("--root", default=".", help="root that holds <provider>.key.txt")
    cp.add_argument("--json", action="store_true", help="emit the JSON calibration report")
    cp.set_defaults(func=_cmd_calibrate_prose)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
