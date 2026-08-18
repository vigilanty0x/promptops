from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from promptbench.ops import (
    OpsValidationError,
    _digest,
    build_failure_corpus,
    build_scorecard,
    compare_reports,
    dataset_manifest,
    jury_consensus,
    release_manifest,
)
from promptbench.ops_cli import main
from promptbench.routing import RoutingPolicy, route_scorecard
from promptbench.verification import verify_artifact


def report(*, version="1.0.0", alpha_pass=1.0, ranking=None):
    ranking = ranking or ["alpha", "beta"]
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.3.0",
        "suite_id": "verify-suite",
        "suite_version": version,
        "suite_sha": "0" * 64,
        "records": [
            {
                "run_id": "r-alpha",
                "candidate_id": "alpha",
                "scenario_id": "s1",
                "difficulty": "easy",
                "attempt": 1,
                "status": "ok" if alpha_pass else "failed",
                "error": None,
                "passed": bool(alpha_pass),
                "reason": "exact match" if alpha_pass else "mismatch",
                "diff": "" if alpha_pass else "expected x; got y",
                "output_sha": "1" * 64,
            },
            {
                "run_id": "r-beta",
                "candidate_id": "beta",
                "scenario_id": "s1",
                "difficulty": "easy",
                "attempt": 1,
                "status": "failed",
                "error": None,
                "passed": False,
                "reason": "mismatch",
                "diff": "expected x; got z",
                "output_sha": "2" * 64,
            },
        ],
        "candidates": [
            {
                "candidate_id": "alpha",
                "model": "replay/a",
                "pass_rate": alpha_pass,
                "pass_at_1": alpha_pass,
                "score_variance": 0.0,
                "mean_latency_ms": 20.0,
                "p95_latency_ms": 20.0,
                "total_cost_microunits": 100,
                "recovery_rate": 0.0,
            },
            {
                "candidate_id": "beta",
                "model": "replay/b",
                "pass_rate": 0.0,
                "pass_at_1": 0.0,
                "score_variance": 0.0,
                "mean_latency_ms": 10.0,
                "p95_latency_ms": 10.0,
                "total_cost_microunits": 50,
                "recovery_rate": 0.0,
            },
        ],
        "ranking": ranking,
        "methodology": ["offline"],
        "limitations": ["replay"],
    }
    payload["report_sha"] = _digest(payload)
    return payload


def artifacts():
    baseline = report()
    current = report(version="1.1.0", alpha_pass=0.0)
    card = build_scorecard(baseline)
    regression = compare_reports(baseline, current)
    failure = build_failure_corpus(baseline)
    jury = jury_consensus([
        baseline,
        report(version="1.0.1", ranking=["beta", "alpha"]),
    ])
    dataset = dataset_manifest([
        {"schema_version": "1.0", "suite_id": "verify-suite", "version": "1.0.0"}
    ])
    route = route_scorecard(card, policy=RoutingPolicy(fallback_count=1))
    release = release_manifest(
        release_version="0.3.0",
        dataset=dataset,
        scorecards=[card],
        regressions=[regression],
    )
    return {
        "scorecard": card,
        "regression": regression,
        "failure_corpus": failure,
        "jury_consensus": jury,
        "dataset_manifest": dataset,
        "route_decision": route,
        "release_manifest": release,
    }


class ArtifactVerificationTests(unittest.TestCase):
    def test_all_supported_generated_artifacts_verify(self):
        for kind, artifact in artifacts().items():
            with self.subTest(kind=kind):
                receipt = verify_artifact(copy.deepcopy(artifact))
                self.assertTrue(receipt["valid"])
                self.assertEqual(receipt["kind"], kind)
                self.assertEqual(receipt["artifact_sha"], artifact["artifact_sha"])
                self.assertEqual(receipt["integrity"], "verified")
                self.assertEqual(receipt["contract"], "verified")
                self.assertEqual(receipt["provenance"], "not-verified")

    def test_expected_kind_is_an_explicit_guard(self):
        card = artifacts()["scorecard"]
        verify_artifact(card, expected_kind="scorecard")
        with self.assertRaisesRegex(OpsValidationError, "expected regression"):
            verify_artifact(card, expected_kind="regression")

    def test_stale_hash_is_rejected(self):
        card = artifacts()["scorecard"]
        card["winner"] = "forged"
        with self.assertRaisesRegex(OpsValidationError, "does not match"):
            verify_artifact(card)

    def test_rehashed_inconsistent_regression_is_still_rejected(self):
        regression = artifacts()["regression"]
        self.assertFalse(regression["passed"])
        regression["passed"] = True
        regression.pop("artifact_sha")
        regression["artifact_sha"] = _digest(regression)
        with self.assertRaisesRegex(OpsValidationError, "passed must equal"):
            verify_artifact(regression)

    def test_rehashed_inconsistent_route_is_still_rejected(self):
        route = artifacts()["route_decision"]
        route["selected_candidate"] = "beta"
        route.pop("artifact_sha")
        route["artifact_sha"] = _digest(route)
        with self.assertRaisesRegex(OpsValidationError, "does not match eligible rank order"):
            verify_artifact(route)

    def test_rehashed_release_with_fake_gate_is_rejected(self):
        release = artifacts()["release_manifest"]
        release["regression_gate_passed"] = True
        release.pop("artifact_sha")
        release["artifact_sha"] = _digest(release)
        with self.assertRaisesRegex(OpsValidationError, "must match failed_regression_count"):
            verify_artifact(release)

    def test_unknown_kind_is_refused(self):
        value = {"schema_version": "1.0", "kind": "mystery"}
        value["artifact_sha"] = _digest(value)
        with self.assertRaisesRegex(OpsValidationError, "unsupported"):
            verify_artifact(value)


class ArtifactVerificationCliTests(unittest.TestCase):
    def test_verify_command_prints_receipt_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps(artifacts()["dataset_manifest"]), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                rc = main(["verify", str(path), "--kind", "dataset_manifest"])
            self.assertEqual(rc, 0)
            receipt = json.loads(output.getvalue())
            self.assertTrue(receipt["valid"])
            self.assertEqual(receipt["kind"], "dataset_manifest")

    def test_verify_command_returns_two_for_contract_invalid_rehashed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = artifacts()["route_decision"]
            value["eligible_count"] = 99
            value.pop("artifact_sha")
            value["artifact_sha"] = _digest(value)
            path = Path(tmp) / "route.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                rc = main(["verify", str(path)])
            self.assertEqual(rc, 2)
            self.assertIn("eligible_count", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
