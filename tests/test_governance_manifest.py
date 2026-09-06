from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.check_governance_manifest import (
    GovernanceManifestError,
    validate_governance_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def copy_inputs(target: Path) -> None:
    for name in (
        "repository-governance.v1.json",
        "portfolio-compatibility.v1.json",
        "published-release.v1.json",
    ):
        shutil.copy2(REPO_ROOT / name, target / name)


class GovernanceManifestTests(unittest.TestCase):
    def test_current_repository_governance_is_consistent(self):
        receipt = validate_governance_manifest(REPO_ROOT)
        self.assertEqual(receipt.gates, 3)
        self.assertEqual(receipt.packages, 9)
        self.assertEqual(receipt.human_approvals, 9)
        self.assertEqual(receipt.archive_ready, 9)
        self.assertEqual(
            receipt.attestation_status,
            "IMPLEMENTED_VERIFIED_PR_AND_MAIN_RELEASE",
        )
        self.assertEqual(receipt.published_release, "0.5.0@v0.5.0")

    def test_persisted_live_main_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "repository-governance.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["observed_main_sha"] = "a" * 40
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "must not be persisted"):
                validate_governance_manifest(root)

    def test_old_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "repository-governance.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["schema_version"] = "1.0"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "schema_version must be 1.1"):
                validate_governance_manifest(root)

    def test_partial_archive_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "portfolio-compatibility.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["packages"][0]["human_archive_approval"] = False
            value["packages"][0]["archive_ready"] = False
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "all-or-none"):
                validate_governance_manifest(root)

    def test_approved_archive_requires_a_human_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "repository-governance.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            del value["gates"]["historical_repository_archival"]["approval"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "matching approval records"):
                validate_governance_manifest(root)

    def test_archive_approval_cannot_authorize_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "repository-governance.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["gates"]["historical_repository_archival"]["approval"]["action"] = "delete"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "forbid deletion"):
                validate_governance_manifest(root)

    def test_archive_approval_scope_must_match_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "portfolio-compatibility.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["human_approval"]["repositories"].pop()
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "repository scope"):
                validate_governance_manifest(root)

    def test_consumer_inventory_digest_must_match_portfolio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            path = root / "portfolio-compatibility.v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["consumer_search"]["evidence_sha256"] = "a" * 64
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "digest must match"):
                validate_governance_manifest(root)

    def test_candidate_policy_cannot_redefine_published_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            published = root / "published-release.v1.json"
            value = json.loads(published.read_text(encoding="utf-8"))
            value["version"] = "0.6.0"
            value["tag"] = "v0.6.0"
            published.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "version/tag must match"):
                validate_governance_manifest(root)

    def test_published_source_digest_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_inputs(root)
            published = root / "published-release.v1.json"
            value = json.loads(published.read_text(encoding="utf-8"))
            value["source_digest"] = "a" * 40
            published.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(GovernanceManifestError, "source_digest must match"):
                validate_governance_manifest(root)


if __name__ == "__main__":
    unittest.main()
