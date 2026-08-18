from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from promptbench.bundle_verification import verify_release_bundle
from promptbench.ops import (
    OpsValidationError,
    _digest,
    build_failure_corpus,
    build_scorecard,
    compare_reports,
    dataset_manifest,
    release_manifest,
)
from promptbench.ops_cli import main


def report(*, version="1.0.0", pass_rate=1.0):
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.4.0",
        "suite_id": "bundle-suite",
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


def evidence(*, red=True):
    baseline = report()
    current = report(version="1.1.0", pass_rate=0.0 if red else 1.0)
    dataset = dataset_manifest([
        {"schema_version": "1.0", "suite_id": "bundle-suite", "version": "1.0.0"}
    ])
    card = build_scorecard(baseline)
    regression = compare_reports(baseline, current)
    release = release_manifest(
        release_version="0.4.0",
        dataset=dataset,
        scorecards=[card],
        regressions=[regression],
    )
    return release, dataset, card, regression


class BundleVerificationTests(unittest.TestCase):
    def test_complete_red_release_bundle_is_valid_even_though_gate_is_red(self):
        release, dataset, card, regression = evidence(red=True)
        receipt = verify_release_bundle(release, [dataset, card, regression])
        self.assertTrue(receipt["valid"])
        self.assertEqual(receipt["linkage"], "verified")
        self.assertEqual(receipt["provenance"], "not-verified")
        self.assertFalse(receipt["release_gate_passed"])
        self.assertEqual(receipt["observed_failed_regression_count"], 1)
        self.assertEqual(receipt["expected_unique_evidence_count"], 3)
        self.assertEqual(receipt["provided_unique_evidence_count"], 3)
        self.assertEqual(receipt["regression_reference_count"], 1)
        self.assertEqual(receipt["unique_regression_count"], 1)

    def test_repeated_red_regression_reference_uses_one_file_but_preserves_gate_count(self):
        _, dataset, card, regression = evidence(red=True)
        release = release_manifest(
            release_version="0.4.0",
            dataset=dataset,
            scorecards=[card],
            regressions=[regression, regression],
        )
        receipt = verify_release_bundle(release, [dataset, card, regression])
        self.assertEqual(receipt["regression_reference_count"], 2)
        self.assertEqual(receipt["unique_regression_count"], 1)
        self.assertEqual(receipt["observed_failed_regression_count"], 2)
        self.assertFalse(receipt["release_gate_passed"])

    def test_missing_evidence_fails_closed(self):
        release, dataset, _, regression = evidence()
        with self.assertRaisesRegex(OpsValidationError, "missing evidence"):
            verify_release_bundle(release, [dataset, regression])

    def test_unexpected_evidence_fails_closed(self):
        release, dataset, card, regression = evidence()
        extra = build_scorecard(report(version="2.0.0"))
        with self.assertRaisesRegex(OpsValidationError, "unexpected evidence"):
            verify_release_bundle(release, [dataset, card, regression, extra])

    def test_duplicate_supplied_evidence_is_rejected(self):
        release, dataset, card, regression = evidence()
        with self.assertRaisesRegex(OpsValidationError, "duplicate supplied evidence"):
            verify_release_bundle(release, [dataset, card, card, regression])

    def test_tampered_supplied_evidence_is_rejected_before_linkage(self):
        release, dataset, card, regression = evidence()
        card["winner"] = "forged"
        with self.assertRaisesRegex(OpsValidationError, "does not match"):
            verify_release_bundle(release, [dataset, card, regression])

    def test_rehashed_release_cannot_lie_about_red_regression_gate(self):
        release, dataset, card, regression = evidence(red=True)
        release["failed_regression_count"] = 0
        release["regression_gate_passed"] = True
        release.pop("artifact_sha")
        release["artifact_sha"] = _digest(release)
        with self.assertRaisesRegex(OpsValidationError, "failed_regression_count"):
            verify_release_bundle(release, [dataset, card, regression])

    def test_rehashed_release_reference_must_match_actual_evidence(self):
        release, dataset, card, regression = evidence()
        other_card = build_scorecard(report(version="9.9.9"))
        release["scorecard_shas"] = [other_card["artifact_sha"]]
        release.pop("artifact_sha")
        release["artifact_sha"] = _digest(release)
        with self.assertRaisesRegex(OpsValidationError, "release bundle mismatch"):
            verify_release_bundle(release, [dataset, card, regression])

    def test_non_release_evidence_kind_is_rejected(self):
        release, dataset, card, regression = evidence()
        failure = build_failure_corpus(report())
        with self.assertRaisesRegex(OpsValidationError, "unsupported bundle evidence kind"):
            verify_release_bundle(release, [dataset, card, regression, failure])

    def test_legacy_release_bundle_preserves_not_recorded_source_integrity(self):
        release, dataset, card, regression = evidence(red=False)
        release.pop("evidence_hashes_verified")
        release.pop("artifact_sha")
        release["artifact_sha"] = _digest(release)
        receipt = verify_release_bundle(release, [dataset, card, regression])
        self.assertEqual(receipt["release_source_evidence_integrity"], "not-recorded")
        self.assertTrue(receipt["release_gate_passed"])


class BundleVerificationCliTests(unittest.TestCase):
    def test_cli_verifies_explicit_bundle_and_returns_zero_for_coherent_red_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, dataset, card, regression = evidence(red=True)
            values = {
                "release.json": release,
                "dataset.json": dataset,
                "card.json": card,
                "regression.json": regression,
            }
            for name, value in values.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                rc = main([
                    "verify-bundle",
                    str(root / "release.json"),
                    "--artifact", str(root / "dataset.json"),
                    "--artifact", str(root / "card.json"),
                    "--artifact", str(root / "regression.json"),
                ])
            self.assertEqual(rc, 0)
            receipt = json.loads(output.getvalue())
            self.assertTrue(receipt["valid"])
            self.assertFalse(receipt["release_gate_passed"])

    def test_cli_returns_two_when_bundle_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, dataset, _, _ = evidence()
            (root / "release.json").write_text(json.dumps(release), encoding="utf-8")
            (root / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                rc = main([
                    "verify-bundle",
                    str(root / "release.json"),
                    "--artifact", str(root / "dataset.json"),
                ])
            self.assertEqual(rc, 2)
            self.assertIn("missing evidence", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
