import json
from pathlib import Path
import tempfile
import unittest

from fixtures import suite_data
from promptbench.harness import BenchmarkHarness
from promptbench.models import BenchmarkSuite, ValidationError
from promptbench.reporting import verify_report, write_report


def report():
    return BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()


class ReportingTests(unittest.TestCase):
    def test_write_and_verify_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.json"
            receipt = write_report(report(), target)
            self.assertTrue(receipt["verified"])
            self.assertTrue(verify_report(target))

    def test_tampered_report_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.json"
            write_report(report(), target)
            data = json.loads(target.read_text(encoding="utf-8"))
            data["ranking"].reverse()
            target.write_text(json.dumps(data), encoding="utf-8")
            self.assertFalse(verify_report(target))

    def test_invalid_json_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.json"
            target.write_text("{broken", encoding="utf-8")
            self.assertFalse(verify_report(target))

    def test_missing_file_fails_verification(self):
        self.assertFalse(verify_report("/tmp/promptbench-missing-report-never-created.json"))

    def test_directory_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValidationError, "regular file"):
                write_report(report(), tmp)


if __name__ == "__main__":
    unittest.main()
