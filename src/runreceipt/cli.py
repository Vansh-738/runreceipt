from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .capture import ReceiptError
from .compare import compare, has_differences
from .render import html_report, text_report
from .runner import record
from .store import load, resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record Python runs and compare the inputs behind different results."
    )
    parser.add_argument(
        "--version", action="version", version=f"runreceipt {__version__}"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="project directory (default: current directory)",
    )
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser(
        "run", help="capture inputs, run Python, and save a receipt"
    )
    run.add_argument(
        "--python", default=sys.executable, help="Python interpreter to run and inspect"
    )
    run.add_argument(
        "--track",
        action="append",
        default=[],
        metavar="PATH",
        help="relative file or directory to hash; repeatable",
    )
    run.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME",
        help="fingerprint a selected environment value; repeatable",
    )
    run.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="exclude matching relative paths; repeatable",
    )
    run.add_argument(
        "arguments", nargs=argparse.REMAINDER, help="Python arguments after '--'"
    )
    diff = commands.add_parser("diff", help="compare two receipt IDs or JSON files")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--format", choices=("text", "json", "html"), default="text")
    diff.add_argument(
        "--check",
        action="store_true",
        help="exit 1 for differences or incomplete comparisons",
    )
    show = commands.add_parser("show", help="print a receipt as JSON")
    show.add_argument("reference")
    listing = commands.add_parser("list", help="list saved receipts, newest first")
    listing.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.action == "run":
            command = (
                args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            )
            receipt, path = record(
                root, args.python, command, args.track, args.env, args.exclude
            )
            print(
                f"runreceipt: saved {receipt['id']} (exit {receipt['exit_code']}, {receipt['duration_ms']} ms)",
                file=sys.stderr,
            )
            for error in receipt["errors"]:
                print(f"runreceipt: incomplete capture: {error!a}", file=sys.stderr)
            return receipt["exit_code"] or (2 if receipt["errors"] else 0)
        if args.action == "diff":
            result = compare(
                load(resolve(root, args.before)), load(resolve(root, args.after))
            )
            if args.format == "json":
                output = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
            elif args.format == "html":
                output = html_report(result)
            else:
                output = text_report(result)
            if args.format == "html" and hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(output.encode("utf-8"))
                sys.stdout.buffer.flush()
            else:
                sys.stdout.write(output)
                sys.stdout.flush()
            return int(args.check and has_differences(result))
        if args.action == "show":
            print(
                json.dumps(
                    load(resolve(root, args.reference)), indent=2, ensure_ascii=True
                )
            )
            return 0
        directory = root / ".runreceipt" / "runs"
        receipts = [load(path) for path in directory.glob("*.json")]
        receipts.sort(key=lambda item: (item["started_at"], item["id"]), reverse=True)
        if args.format == "json":
            print(json.dumps(receipts, indent=2, ensure_ascii=True))
        else:
            for item in receipts:
                print(
                    f"{item['id']}  {item['started_at']}  exit {item['exit_code']}  {item['duration_ms']} ms"
                )
        return 0
    except BrokenPipeError:
        import os

        sys.stdout = open(os.devnull, "w")
        return 0
    except (ReceiptError, OSError) as error:
        print(f"runreceipt: {str(error)!a}", file=sys.stderr)
        return 2
