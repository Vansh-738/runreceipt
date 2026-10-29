import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import sample


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "runreceipt", "--root", str(self.root), *args],
            capture_output=True,
            check=False,
        )

    def test_run_preserves_stdout_and_exit_status_and_can_be_listed(self):
        result = self.cli(
            "run", "--", "-c", "print('command-output'); raise SystemExit(7)"
        )
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout.strip(), b"command-output")
        listing = self.cli("list", "--format", "json")
        items = json.loads(listing.stdout)
        self.assertEqual(len(items), 1)
        receipt = self.cli("show", items[0]["id"])
        self.assertEqual(json.loads(receipt.stdout)["exit_code"], 7)

    def test_list_in_empty_project_does_not_create_storage(self):
        self.assertEqual(self.cli("list").stdout, b"")
        self.assertFalse((self.root / ".runreceipt").exists())

    def test_diff_formats_and_check_exit_code(self):
        a, b = sample(), sample()
        b["id"] = "bbbbbbbbbbbb"
        b["exit_code"] = 1
        for name, data in [("a.json", a), ("b.json", b)]:
            (self.root / name).write_text(json.dumps(data))
        for fmt in ["text", "json", "html"]:
            result = self.cli("diff", "a.json", "b.json", "--format", fmt)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout)
        self.assertEqual(self.cli("diff", "a.json", "b.json", "--check").returncode, 1)
        self.assertEqual(self.cli("diff", "a.json", "a.json", "--check").returncode, 0)

    def test_input_errors_are_two(self):
        for args in [
            ("show", "missing.json"),
            ("run",),
            ("run", "--track", "missing", "--", "-c", "pass"),
        ]:
            self.assertEqual(self.cli(*args).returncode, 2)
