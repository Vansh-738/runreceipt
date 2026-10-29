"""Make two real runs with different data and settings, then compare them."""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from runreceipt.compare import compare
from runreceipt.render import html_report, text_report
from runreceipt.runner import record

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path("demo-report.html"))
args = parser.parse_args()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "job.py").write_text(
        "import json, os\nfrom pathlib import Path\n"
        "items = json.loads(Path('data.json').read_text())\n"
        "limit = int(os.environ['MAX_ITEMS'])\n"
        "print(f'items={len(items)}; limit={limit}')\n"
        "raise SystemExit(0 if len(items) <= limit else 1)\n"
    )
    (root / "data.json").write_text('["first", "second"]\n')
    old = os.environ.get("MAX_ITEMS")
    try:
        os.environ["MAX_ITEMS"] = "2"
        first, _ = record(
            root, sys.executable, ["job.py"], ["job.py", "data.json"], ["MAX_ITEMS"], []
        )
        (root / "data.json").write_text('["first", "second", "third"]\n')
        os.environ["MAX_ITEMS"] = "1"
        second, _ = record(
            root, sys.executable, ["job.py"], ["job.py", "data.json"], ["MAX_ITEMS"], []
        )
    finally:
        if old is None:
            os.environ.pop("MAX_ITEMS", None)
        else:
            os.environ["MAX_ITEMS"] = old
    result = compare(first, second)
    args.output.write_text(html_report(result), encoding="utf-8")
    print(text_report(result), end="")
    print(f"HTML report: {args.output}")
