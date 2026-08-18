from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr

from promptbench.ops import OpsValidationError, _digest, build_scorecard, compare_reports, dataset_manifest
from promptbench.ops_cli import main
from promptbench.release_ops import release_manifest


def report(*, version="1.0.0", pass_rate=1.0):
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.3.0",
        "suite_id": "release-suite",
        "suite_version": version,
        "suite_sha": "0" * 64,
        "records": [],
        "candidates": [
            {
                "candidate_id": "alpha",
                "model": "replay/a",
                "pass_rate": pass_rate,
                "pass_at_1": pass_rate,
                "score_variance": 0.0,
                "mean_latency_ms": 10.0,
                "p95_latency_ms": 10.0,
                "total_cost_microunits": 100,
                "recovery_rate": 0.0,
            }
        ],
        "ranking": ["alpha"],
        "methodology": ["offline"],
        "limitations": ["replay"],
    }
    payload["report_sha"] = _digest(payload)
    return payload


def evidence():
    dataset = dataset_manifest([
        {"schema_version": "1.0", "suite_id": "release-suite", "version": "1.0.0"}
    ])
    card = build_scorecard(report())
    regression = compare_reports(report(), report(version="1.1.0", pass_rate=0.0))
    return dataset, card, regression


class ReleaseEvidenceTests(unittest.TestCase):
    def test_valid_release_verifies_all_evidence_hashes(self):
        dataset, card, _ = evidence()
        result = release_manifest(
            release_version="0.3.0",
            dataset=dataset,
            scorecards=[card],
            regressions=[],
        )
        self.assertTrue(result["evidence_hashes_verified"])
        self.assertTrue(result["regression_gate_passed"])
        self.assertEqual(result["scorecard_shas"], [card["artifact_sha"]])

    def test_tampered_scorecard_is_rejected_even_if_old_sha_is_retained(self):
        dataset, card, _ = evidence()
        card["winner"] = "forged"
        with self.assertRaisesRegex(OpsValidationError, "does not match"):
            release_manifest(
                release_version="0.3.0",
                dataset=dataset,
                scorecards=[card],
            )

    def test_red_regression_cannot_be_flipped_green_without_rehashing(self):
        dataset, card, regression = evidence()
        self.assertFalse(regression["passed"])
        regression["passed"] = True
        with self.assertRaisesRegex(OpsValidationError, "does not match artifact content"):
            release_manifest(
                release_version="0.3.0",
                dataset=dataset,
                scorecards=[card],
                regressions=[regression],
            )

    def test_wrong_artifact_kind_is_rejected_even_with_matching_hash(self):
        dataset, card, _ = evidence()
        dataset["kind"] = "scorecard"
        dataset.pop("artifact_sha")
        dataset["artifact_sha"] = _digest(dataset)
        with self.assertRaisesRegex(OpsValidationError, "dataset_manifest"):
            release_manifest(
                release_version="0.3.0",
                dataset=dataset,
                scorecards=[card],
            )

    def test_genuine_red_regression_keeps_release_gate_red(self):
        dataset, card, regression = evidence()
        result = release_manifest(
            release_version="0.3.0",
            dataset=dataset,
            scorecards=[card],
            regressions=[regression],
        )
        self.assertFalse(result["regression_gate_passed"])
        self.assertEqual(result["failed_regression_count"], 1)


class ReleaseEvidenceCliTests(unittest.TestCase):
    def test_cli_returns_two_for_tampered_regression_instead_of_trusting_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset, card, regression = evidence()
            regression["passed"] = True
            dataset_path = root / "dataset.json"
            card_path = root / "card.json"
            regression_path = root / "regression.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            card_path.write_text(json.dumps(card), encoding="utf-8")
            regression_path.write_text(json.dumps(regression), encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                rc = main([
                    "release",
                    "--version", "0.3.0",
                    "--dataset", str(dataset_path),
                    "--scorecard", str(card_path),
                    "--regression", str(regression_path),
                ])
            self.assertEqual(rc, 2)
            self.assertIn("does not match artifact content", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
