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
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
