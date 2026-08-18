from __future__ import annotations

import unittest

from promptbench.ops import OpsValidationError, _digest
from promptbench.verification import verify_artifact


def release_manifest(*, evidence_hashes_verified="absent"):
    value = {
        "schema_version": "1.0",
        "kind": "release_manifest",
        "release_version": "0.2.0",
        "dataset_sha": "0" * 64,
        "scorecard_shas": ["1" * 64],
        "regression_shas": [],
        "regression_gate_passed": True,
        "failed_regression_count": 0,
    }
    if evidence_hashes_verified != "absent":
        value["evidence_hashes_verified"] = evidence_hashes_verified
    value["artifact_sha"] = _digest(value)
    return value


class LegacyReleaseVerificationTests(unittest.TestCase):
    def test_pre_03_release_manifest_verifies_without_inventing_source_evidence_integrity(self):
        receipt = verify_artifact(release_manifest())
        self.assertTrue(receipt["valid"])
        self.assertEqual(receipt["kind"], "release_manifest")
        self.assertEqual(receipt["source_evidence_integrity"], "not-recorded")

    def test_03_style_release_reports_verified_source_evidence_integrity(self):
        receipt = verify_artifact(release_manifest(evidence_hashes_verified=True))
        self.assertEqual(receipt["source_evidence_integrity"], "verified")

    def test_explicit_false_source_evidence_integrity_is_rejected(self):
        with self.assertRaisesRegex(OpsValidationError, "must be true when recorded"):
            verify_artifact(release_manifest(evidence_hashes_verified=False))


if __name__ == "__main__":
    unittest.main()
