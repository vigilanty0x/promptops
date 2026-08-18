from __future__ import annotations

import copy
import unittest

from promptbench.ops import (
    OpsValidationError,
    RegressionThresholds,
    _digest,
    build_failure_corpus,
    build_scorecard,
    compare_reports,
    dataset_manifest,
    jury_consensus,
    release_manifest,
    validate_report,
)


def report(*, suite_version: str = "1.0.0", a_pass: float = 1.0, a_latency: float = 10.0, a_cost: int = 100, ranking=None):
    ranking = ranking or ["alpha", "beta"]
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.1.0",
        "suite_id": "ops-suite",
        "suite_version": suite_version,
        "suite_sha": "0" * 64,
        "records": [
            {
                "run_id": "r1",
                "candidate_id": "alpha",
                "scenario_id": "s1",
                "difficulty": "easy",
                "attempt": 1,
                "status": "ok" if a_pass else "failed",
                "error": None,
                "passed": bool(a_pass),
                "reason": "exact match" if a_pass else "mismatch",
                "diff": "" if a_pass else "expected x; got y",
                "output_sha": "1" * 64,
            },
            {
                "run_id": "r2",
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
                "total_runs": 1,
                "passed_runs": int(bool(a_pass)),
                "failed_runs": int(not bool(a_pass)),
                "pass_rate": a_pass,
                "pass_at_1": a_pass,
                "score_variance": 0.0,
                "mean_latency_ms": a_latency,
                "p95_latency_ms": a_latency,
                "total_cost_microunits": a_cost,
                "mean_tokens_per_run": 2.0,
                "recovery_rate": 0.0,
            },
            {
                "candidate_id": "beta",
                "model": "replay/b",
                "total_runs": 1,
                "passed_runs": 0,
                "failed_runs": 1,
                "pass_rate": 0.0,
                "pass_at_1": 0.0,
                "score_variance": 0.0,
                "mean_latency_ms": 8.0,
                "p95_latency_ms": 8.0,
                "total_cost_microunits": 50,
                "mean_tokens_per_run": 2.0,
                "recovery_rate": 0.0,
            },
        ],
        "ranking": ranking,
        "methodology": ["offline"],
        "limitations": ["replay"],
    }
    payload["report_sha"] = _digest(payload)
    return payload


class OpsTests(unittest.TestCase):
    def test_validate_report_detects_tampering(self):
        value = report()
        validate_report(value)
        value["candidates"][0]["pass_rate"] = 0.2
        with self.assertRaisesRegex(OpsValidationError, "does not match"):
            validate_report(value)

    def test_scorecard_follows_report_ranking(self):
        value = report(ranking=["beta", "alpha"])
        card = build_scorecard(value)
        self.assertEqual(card["winner"], "beta")
        self.assertEqual([row["rank"] for row in card["rows"]], [1, 2])
        self.assertEqual(card["source_report_sha"], value["report_sha"])
        self.assertEqual(len(card["artifact_sha"]), 64)

    def test_compare_reports_detects_quality_latency_and_cost_regressions(self):
        baseline = report(a_pass=1.0, a_latency=10.0, a_cost=100)
        current = report(suite_version="1.1.0", a_pass=0.5, a_latency=14.0, a_cost=140)
        delta = compare_reports(
            baseline,
            current,
            thresholds=RegressionThresholds(pass_rate_drop=0.1, latency_increase=0.2, cost_increase=0.2),
        )
        alpha = next(row for row in delta["rows"] if row["candidate_id"] == "alpha")
        self.assertFalse(delta["passed"])
        self.assertEqual(set(alpha["reasons"]), {"pass_rate", "latency", "cost"})

    def test_compare_reports_allows_explicit_tolerance(self):
        baseline = report(a_pass=1.0, a_latency=10.0, a_cost=100)
        current = report(suite_version="1.0.1", a_pass=0.95, a_latency=11.0, a_cost=105)
        delta = compare_reports(
            baseline,
            current,
            thresholds=RegressionThresholds(pass_rate_drop=0.1, latency_increase=0.2, cost_increase=0.2),
        )
        self.assertTrue(delta["passed"])
        self.assertEqual(delta["regression_count"], 0)

    def test_failure_corpus_preserves_failed_attempts_without_raw_output(self):
        corpus = build_failure_corpus(report())
        self.assertEqual(corpus["failure_count"], 1)
        failure = corpus["failures"][0]
        self.assertEqual(failure["candidate_id"], "beta")
        self.assertNotIn("output", failure)
        self.assertIn("diff", failure)

    def test_jury_consensus_is_deterministic_and_tie_broken_by_quality(self):
        first = report(ranking=["alpha", "beta"])
        second = report(suite_version="1.1.0", ranking=["beta", "alpha"], a_pass=1.0)
        result_a = jury_consensus([first, second])
        result_b = jury_consensus([copy.deepcopy(first), copy.deepcopy(second)])
        self.assertEqual(result_a, result_b)
        self.assertEqual(result_a["winner"], "alpha")
        self.assertEqual(result_a["ballot_count"], 2)

    def test_dataset_manifest_sorts_and_rejects_duplicate_versions(self):
        suite_a = {"schema_version": "1.0", "suite_id": "b", "version": "1.0.0", "scenarios": [], "candidates": []}
        suite_b = {"schema_version": "1.0", "suite_id": "a", "version": "2.0.0", "scenarios": [1], "candidates": [1]}
        manifest = dataset_manifest([suite_a, suite_b])
        self.assertEqual([item["suite_id"] for item in manifest["datasets"]], ["a", "b"])
        with self.assertRaisesRegex(OpsValidationError, "duplicate"):
            dataset_manifest([suite_a, copy.deepcopy(suite_a)])

    def test_release_manifest_fails_closed_on_regression_evidence(self):
        dataset = dataset_manifest([{"schema_version": "1.0", "suite_id": "ops-suite", "version": "1.0.0"}])
        scorecard = build_scorecard(report())
        failed_regression = compare_reports(report(), report(suite_version="1.1.0", a_pass=0.0))
        release = release_manifest(
            release_version="0.2.0",
            dataset=dataset,
            scorecards=[scorecard],
            regressions=[failed_regression],
        )
        self.assertFalse(release["regression_gate_passed"])
        self.assertEqual(release["failed_regression_count"], 1)


if __name__ == "__main__":
    unittest.main()
