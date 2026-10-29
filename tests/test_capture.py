import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runreceipt.capture import ReceiptError, environment, files, interpreter_info
from runreceipt.runner import record
from runreceipt.store import initialize, key_id, load


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_environment_uses_keyed_fingerprints_without_storing_values(self):
        result = environment(["TOKEN", "ABSENT"], b"a" * 32, {"TOKEN": "private-value"})
        self.assertNotIn("private-value", json.dumps(result))
        self.assertFalse(result["ABSENT"]["present"])
        other = environment(["TOKEN"], b"b" * 32, {"TOKEN": "private-value"})
        self.assertNotEqual(
            result["TOKEN"]["fingerprint"], other["TOKEN"]["fingerprint"]
        )
        self.assertEqual(
            result,
            environment(["ABSENT", "TOKEN"], b"a" * 32, {"TOKEN": "private-value"}),
        )

    def test_empty_environment_value_differs_from_unset(self):
        self.assertNotEqual(
            environment(["X"], b"a" * 32, {"X": ""}), environment(["X"], b"a" * 32, {})
        )
        for name in ["", "A=B", "A\0B"]:
            with self.assertRaises(ReceiptError):
                environment([name], b"a" * 32, {})

    def test_selected_file_hashes_and_exclusions(self):
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_bytes(b"hello")
        (self.root / "src/skip.py").write_bytes(b"skip")
        report = files(self.root, ["src"], ["src/skip.py"])
        self.assertEqual(list(report), ["src/app.py"])
        self.assertEqual(
            report["src/app.py"]["sha256"], hashlib.sha256(b"hello").hexdigest()
        )

    def test_storage_and_virtual_environment_are_always_excluded(self):
        for directory in [".runreceipt", ".venv", "__pycache__"]:
            (self.root / directory).mkdir()
            (self.root / directory / "private").write_text("do not hash")
        (self.root / "app.py").write_text("pass")
        self.assertEqual(list(files(self.root, ["."], [])), ["app.py"])

    def test_no_tracking_means_no_file_scan(self):
        self.assertEqual(files(self.root, [], []), {})

    def test_path_escape_and_missing_inputs_fail(self):
        for path in ["../outside", str(self.root), "missing.txt"]:
            with self.assertRaises(ReceiptError):
                files(self.root, [path], [])
        self.assertEqual(files(self.root, ["missing.txt"], [], allow_missing=True), {})

    @unittest.skipIf(os.name == "nt", "Windows symlinks require additional privileges")
    def test_symlink_files_and_ancestors_are_rejected(self):
        real = self.root / "real"
        real.mkdir()
        (real / "data").write_text("hello")
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        for name in ["alias", "alias/data", "."]:
            with self.assertRaises(ReceiptError):
                files(self.root, [name], [])
        self.assertEqual(
            files(self.root, ["."], ["alias"]),
            {"real/data": {"sha256": hashlib.sha256(b"hello").hexdigest(), "size": 5}},
        )

    def test_interpreter_is_the_one_selected_for_execution(self):
        executable, data = interpreter_info(sys.executable, self.root)
        self.assertEqual(executable, sys.executable)
        self.assertEqual(
            data["python"]["version"], ".".join(map(str, sys.version_info[:3]))
        )
        self.assertIsInstance(data["packages"], dict)
        with self.assertRaises(ReceiptError):
            interpreter_info(str(self.root / "not-python"), self.root)

    def test_key_is_stable_and_never_part_of_receipt(self):
        runs, first = initialize(self.root)
        _, second = initialize(self.root)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)
        self.assertEqual(len(key_id(first)), 16)
        self.assertEqual(runs.name, "runs")
        if os.name != "nt":
            self.assertEqual(
                (self.root / ".runreceipt/key").stat().st_mode & 0o777, 0o600
            )

    def test_invalid_existing_key_is_not_overwritten(self):
        initialize(self.root)
        (self.root / ".runreceipt/key").write_bytes(b"broken")
        with self.assertRaises(ReceiptError):
            initialize(self.root)
        self.assertEqual((self.root / ".runreceipt/key").read_bytes(), b"broken")

    def test_command_failure_is_recorded(self):
        receipt, path = record(
            self.root, sys.executable, ["-c", "raise SystemExit(7)"], [], [], []
        )
        self.assertEqual(receipt["exit_code"], 7)
        self.assertEqual(load(path), receipt)
        self.assertGreaterEqual(receipt["duration_ms"], 0)

    def test_file_mutations_and_selected_environment_are_recorded(self):
        (self.root / "data").mkdir()
        (self.root / "data/before.txt").write_text("before")
        code = "from pathlib import Path; Path('data/before.txt').unlink(); Path('data/after.txt').write_text('after')"
        with patch.dict(os.environ, {"RECEIPT_TEST_TOKEN": "private-value"}):
            receipt, path = record(
                self.root,
                sys.executable,
                ["-c", code],
                ["data"],
                ["RECEIPT_TEST_TOKEN"],
                [],
            )
        self.assertEqual(list(receipt["inputs"]["files"]), ["data/before.txt"])
        self.assertEqual(list(receipt["files_after"]), ["data/after.txt"])
        self.assertNotIn("private-value", path.read_text())
        self.assertEqual(receipt["exit_code"], 0)

    def test_invalid_arguments_do_not_execute_code(self):
        code = "from pathlib import Path; Path('executed').touch()"
        with self.assertRaises(ReceiptError):
            record(self.root, sys.executable, ["-c", code], ["missing"], [], [])
        self.assertFalse((self.root / "executed").exists())
        with self.assertRaises(ReceiptError):
            record(self.root, sys.executable, [], [], [], [])

    def test_concurrent_initialization_uses_one_complete_key(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(lambda _: initialize(self.root)[1], range(16)))
        self.assertTrue(all(key == keys[0] for key in keys))
