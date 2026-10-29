import json
import tempfile
import unittest
from pathlib import Path

from helpers import sample

from runreceipt.capture import ReceiptError
from runreceipt.compare import compare, has_differences
from runreceipt.render import html_report, text_report
from runreceipt.store import load, validate


class CompareTests(unittest.TestCase):
    def test_identical_receipts_have_no_differences(self):
        result = compare(sample(), sample())
        self.assertFalse(has_differences(result))
        self.assertIn("0 recorded difference", text_report(result))

    def test_changes_to_packages_files_python_and_exit(self):
        before, after = sample(), sample()
        after["inputs"]["packages"]["example"] = ["2.0"]
        after["inputs"]["python"]["version"] = "3.15.0"
        after["inputs"]["files"]["src/app.py"]["sha256"] = "c" * 64
        after["files_after"] = after["inputs"]["files"]
        after["exit_code"] = 1
        result = compare(before, after)
        self.assertEqual(
            {item["area"] for item in result["changes"]},
            {"packages", "python", "files", "outcome"},
        )
        self.assertTrue(has_differences(result))

    def test_environment_values_are_comparable_only_with_the_same_key(self):
        before, after = sample(), sample()
        after["inputs"]["environment"]["MODE"]["fingerprint"] = "c" * 64
        result = compare(before, after)
        self.assertEqual(result["changes"][0]["area"], "environment")
        self.assertNotIn("c" * 64, json.dumps(result))
        after["key_id"] = "d" * 16
        result = compare(before, after)
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["environment_not_comparable"], ["MODE"])
        self.assertTrue(has_differences(result))

    def test_absent_values_can_be_compared_across_keys(self):
        before, after = sample(), sample()
        for item in [before, after]:
            item["inputs"]["environment"]["MODE"] = {"present": False}
        after["key_id"] = "d" * 16
        self.assertFalse(has_differences(compare(before, after)))

    def test_capture_selection_changes_are_visible(self):
        before, after = sample(), sample()
        after["selection"]["track"] = []
        after["inputs"]["files"] = {}
        after["files_after"] = {}
        result = compare(before, after)
        self.assertTrue(result["selection_changed"])
        self.assertIn("changed coverage", text_report(result))

    def test_environment_unset_and_not_captured_are_different(self):
        before, after = sample(), sample()
        after["inputs"]["environment"] = {}
        change = compare(before, after)["changes"][0]
        self.assertEqual(change["after"], "not captured")
        after["inputs"]["environment"] = {"MODE": {"present": False}}
        self.assertEqual(compare(before, after)["changes"][0]["after"], "unset")

    def test_mutations_are_separate_from_starting_input_changes(self):
        before, after = sample(), sample()
        after["files_after"]["src/app.py"]["sha256"] = "c" * 64
        result = compare(before, after)
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["mutations"]["after"][0]["name"], "src/app.py")
        self.assertTrue(has_differences(result))

    def test_incomplete_snapshot_does_not_become_mass_deletion(self):
        before, after = sample(), sample()
        after["files_after"] = {}
        after["errors"] = ["input could not be read"]
        result = compare(before, after)
        self.assertIsNone(result["mutations"]["after"])
        self.assertIn("incomplete", text_report(result))

    def test_html_escapes_untrusted_names_and_values(self):
        before, after = sample(), sample()
        after["inputs"]["packages"]["<script>alert(1)</script>"] = ["<img src=x>"]
        html = html_report(compare(before, after))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("https://", html)

    def test_unknown_schema_and_malformed_fields_fail_cleanly(self):
        for value in [None, [], {}, {"schema_version": 2}]:
            with self.assertRaises(ReceiptError):
                validate(value)
        for field in ["command", "inputs", "files_after", "errors", "duration_ms"]:
            value = sample()
            value[field] = None
            with self.assertRaises(ReceiptError):
                validate(value)
        value = sample()
        value["inputs"]["environment"]["MODE"] = "private-value"
        with self.assertRaises(ReceiptError):
            validate(value)

    def test_invalid_json_error_does_not_echo_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"private-value')
            with self.assertRaises(ReceiptError) as error:
                load(path)
            self.assertNotIn("private-value", str(error.exception))

    def test_imported_receipt_identifiers_cannot_inject_terminal_controls(self):
        for field in ["id", "key_id", "started_at"]:
            value = sample()
            value[field] = "bad\x1b[31m"
            with self.assertRaises(ReceiptError):
                validate(value)
