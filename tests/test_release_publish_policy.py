from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_release_publish_policy import (
    ReleasePublishPolicyError,
    validate_release_publish_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_fixture(
    root: Path,
    *,
    project_version: str = "0.5.0",
    policy_version: str = "0.5.0",
    tag: str = "v0.5.0",
    publish_enabled: bool = True,
    wheel_count: int = 10,
    obsolete_notes: bool = False,
) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    policy = {
        "schema_version": "1.0",
        "repository": "vigilanty0x/promptops",
        "version": policy_version,
        "tag": tag,
        "publish_enabled": publish_enabled,
        "publish_event": "push",
        "publish_branch": "main",
        "publisher": "repository-owner",
        "requires_jobs": ["verify", "verify-consolidated-package", "attest-wheels"],
        "release_notes_source": "CHANGELOG.md",
        "draft": False,
        "prerelease": False,
        "idempotent": True,
        "publish_once_per_version": True,
        "assets": {
            "canonical_wheel_count": wheel_count,
            "canonical_wheel_python_source": "3.11",
            "include_sha256sums": True,
            "include_sigstore_provenance_bundle": True,
            "include_release_receipt": True,
        },
    }
    (root / "release-policy.v1.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "promptbench-replay"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    notes = (
        "Release candidate verification remains the full 20-job CI matrix."
        if obsolete_notes
        else "- 40 wheel-producing jobs require signed SLSA provenance before publishing `v0.5.0`."
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {policy_version} - 2026-08-18\n\n{notes}\n\n## 0.4.0 - 2026-08-17\n\n- Older.\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "ci.yml").write_text(
        """name: CI
jobs:
  publish-release:
    needs: [verify, verify-consolidated-package, attest-wheels]
    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' && github.actor == github.repository_owner }}
    runs-on: ubuntu-latest
    steps:
      - run: test -f release-policy.v1.json
      - uses: actions/download-artifact@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          pattern: "*-wheel-py3.11"
      - uses: actions/download-artifact@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          name: wheel-provenance-${{ github.run_id }}
      - run: test "$(find /tmp/release-wheels -maxdepth 1 -name '*.whl' | wc -l)" -eq 10
      - run: test -f /tmp/release-assets/RELEASE-RECEIPT.json
      - run: gh release create "$tag" /tmp/release-assets/*
      - run: gh release view "$tag"
      - run: gh release download "$tag" --dir /tmp/release-readback
""",
        encoding="utf-8",
    )


class ReleasePublishPolicyTests(unittest.TestCase):
    def test_current_repository_policy_is_consistent(self):
        receipt = validate_release_publish_policy(REPO_ROOT)
        self.assertEqual(receipt.version, "0.5.0")
        self.assertEqual(receipt.tag, "v0.5.0")
        self.assertEqual(receipt.required_jobs, 3)
        self.assertEqual(receipt.canonical_wheels, 10)
        self.assertGreater(receipt.release_note_lines, 0)

    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            receipt = validate_release_publish_policy(root)
            self.assertEqual(receipt.version, "0.5.0")
            self.assertEqual(receipt.canonical_wheels, 10)

    def test_project_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, project_version="0.5.1")
            with self.assertRaisesRegex(ReleasePublishPolicyError, "project.version"):
                validate_release_publish_policy(root)

    def test_tag_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, tag="0.5.0")
            with self.assertRaisesRegex(ReleasePublishPolicyError, "tag must equal"):
                validate_release_publish_policy(root)

    def test_disabled_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, publish_enabled=False)
            with self.assertRaisesRegex(ReleasePublishPolicyError, "publish_enabled"):
                validate_release_publish_policy(root)

    def test_release_asset_count_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, wheel_count=9)
            with self.assertRaisesRegex(ReleasePublishPolicyError, "assets"):
                validate_release_publish_policy(root)

    def test_obsolete_ci_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, obsolete_notes=True)
            with self.assertRaisesRegex(ReleasePublishPolicyError, "obsolete 20-job"):
                validate_release_publish_policy(root)


if __name__ == "__main__":
    unittest.main()
