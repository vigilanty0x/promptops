from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import suite_data
from promptbench.cli import main


def invoke(argv):
    output = StringIO()
    with redirect_stdout(output):
        code = main(argv)
    return code, json.loads(output.getvalue())


class CliTests(unittest.TestCase):
    def test_validate_reports_identity_and_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(suite_data()), encoding="utf-8")
            code, result = invoke(["validate", "--suite", str(path)])
            self.assertEqual(code, 0)
            self.assertTrue(result["valid"])
            self.assertEqual(result["scenarios"], 2)

    def test_run_prints_complete_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(suite_data()), encoding="utf-8")
            code, result = invoke(["run", "--suite", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(result["report"]["ranking"][0], "good")
            self.assertEqual(len(result["report"]["records"]), 8)

    def test_run_writes_and_verifies_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "suite.json"
            report = Path(tmp) / "report.json"
            suite.write_text(json.dumps(suite_data()), encoding="utf-8")
            code, result = invoke(["run", "--suite", str(suite), "--output", str(report)])
            self.assertEqual(code, 0)
            self.assertTrue(result["receipt"]["verified"])
            self.assertEqual(invoke(["verify", "--report", str(report)]), (0, {"report": str(report.resolve()), "verified": True}))

    def test_minimum_pass_rate_can_fail_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = suite_data()
            for samples in data["replay"]["good"].values():
                for sample in samples:
                    sample["output"] = "wrong"
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            code, result = invoke(["run", "--suite", str(path), "--minimum-pass-rate", "1"])
            self.assertEqual(code, 3)
            self.assertLess(max(item["pass_rate"] for item in result["report"]["candidates"]), 1.0)

    def test_invalid_threshold_is_bounded_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(suite_data()), encoding="utf-8")
            code, result = invoke(["run", "--suite", str(path), "--minimum-pass-rate", "2"])
            self.assertEqual(code, 2)
            self.assertIn("between 0 and 1", result["error"])

    def test_invalid_json_is_bounded_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text("{broken", encoding="utf-8")
            code, result = invoke(["validate", "--suite", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(result["type"], "ValidationError")
            self.assertLess(len(result["error"]), 1_000)

    def test_functional_probe(self):
        code, result = invoke(["probe", "--level", "functional"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "proven")

    def test_demo_is_reproducible_and_keeps_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result = invoke(["demo", "--workspace", tmp])
            self.assertEqual(code, 0)
            self.assertTrue(result["report_verified"])
            self.assertGreater(result["failed_runs_preserved"], 0)
            self.assertTrue(Path(tmp, "suite.json").is_file())
            self.assertTrue(Path(tmp, "report.json").is_file())


if __name__ == "__main__":
    unittest.main()
