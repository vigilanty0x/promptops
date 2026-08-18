from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from promptbench.ops import _digest, build_scorecard, dataset_manifest
from promptbench.ops_cli import main


def make_report(pass_rate=1.0, version="1.0.0"):
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.1.0",
        "suite_id": "cli-suite",
        "suite_version": version,
        "suite_sha": "0" * 64,
        "records": [],
        "candidates": [{
            "candidate_id": "alpha",
            "model": "replay/a",
            "total_runs": 1,
            "passed_runs": int(pass_rate > 0),
            "failed_runs": int(pass_rate <= 0),
            "pass_rate": pass_rate,
            "pass_at_1": pass_rate,
            "score_variance": 0.0,
            "mean_latency_ms": 10.0,
            "p95_latency_ms": 10.0,
            "total_cost_microunits": 100,
            "mean_tokens_per_run": 1.0,
            "recovery_rate": 0.0,
        }],
        "ranking": ["alpha"],
        "methodology": ["offline"],
        "limitations": ["replay"],
    }
    payload["report_sha"] = _digest(payload)
    return payload


class OpsCliTests(unittest.TestCase):
    def test_scorecard_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "report.json"
            out = Path(tmp) / "card.json"
            src.write_text(json.dumps(make_report()), encoding="utf-8")
            self.assertEqual(main(["scorecard", str(src), "-o", str(out)]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "scorecard")
            self.assertEqual(data["winner"], "alpha")

    def test_regression_gate_returns_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.json"
            current = Path(tmp) / "current.json"
            base.write_text(json.dumps(make_report(1.0, "1.0.0")), encoding="utf-8")
            current.write_text(json.dumps(make_report(0.0, "1.1.0")), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                rc = main(["regress", str(base), str(current)])
            self.assertEqual(rc, 3)

    def test_invalid_input_returns_two_without_traceback(self):
        stream = io.StringIO()
        with redirect_stderr(stream):
            rc = main(["scorecard", "/definitely/missing.json"])
        self.assertEqual(rc, 2)
        self.assertIn("file not found", stream.getvalue())

    def test_release_gate_uses_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = make_report()
            dataset = dataset_manifest([{"schema_version": "1.0", "suite_id": "cli-suite", "version": "1.0.0"}])
            card = build_scorecard(report)
            dataset_path = root / "dataset.json"
            card_path = root / "card.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            card_path.write_text(json.dumps(card), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                rc = main(["release", "--version", "0.2.0", "--dataset", str(dataset_path), "--scorecard", str(card_path)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
