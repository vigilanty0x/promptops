from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.check_workflow_security import (
    WorkflowSecurityError,
    validate_workflow_text,
    validate_workflows,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def workflow(
    *,
    action_ref: str = SHA,
    persist: str = "false",
    permission: str = "read",
    timeout: str | None = "15",
) -> str:
    timeout_line = "" if timeout is None else f"    timeout-minutes: {timeout}\n"
    return f"""name: test

on:
  pull_request:

permissions:
  contents: {permission}

jobs:
  verify:
    runs-on: ubuntu-latest
{timeout_line}    steps:
      - uses: actions/checkout@{action_ref}
        with:
          persist-credentials: {persist}
      - uses: actions/setup-python@{SHA}
"""


def workflow_with_attestation(*, guarded: bool = True) -> str:
    guard = (
        "${{ github.event_name == 'push' || (github.event_name == 'pull_request' && "
        "github.actor == github.repository_owner && "
        "github.event.pull_request.head.repo.full_name == github.repository) }}"
        if guarded
        else "${{ github.event_name == 'pull_request' }}"
    )
    return workflow() + f"""  attest-wheels:
    needs: [verify, verify-consolidated-package]
    if: {guard}
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
      id-token: write
      attestations: write
      artifact-metadata: write
    steps:
      - uses: actions/attest@{SHA}
"""


def workflow_with_release(*, guarded: bool = True) -> str:
    guard = (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' && "
        "github.actor == github.repository_owner }}"
        if guarded
        else "${{ github.event_name == 'push' }}"
    )
    return workflow() + f"""  publish-release:
    needs: [verify, verify-consolidated-package, attest-wheels]
    if: {guard}
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@{SHA}
        with:
          persist-credentials: false
      - run: test -f release-policy.v1.json
      - run: |
          gh release create "$tag" --target "$GITHUB_SHA"
          gh release view "$tag"
"""


class WorkflowSecurityTests(unittest.TestCase):
    def test_current_repository_workflows_match_security_policy(self):
        receipt = validate_workflows(REPO_ROOT)
        self.assertEqual(receipt.workflows, 2)
        self.assertEqual(receipt.jobs, 5)
        self.assertGreaterEqual(receipt.external_actions, 12)
        self.assertEqual(receipt.checkout_steps, 4)
        self.assertEqual(receipt.attestation_jobs, 1)
        self.assertEqual(receipt.release_jobs, 1)

    def test_valid_fixture_is_accepted(self):
        jobs, actions, checkouts, attestations, releases = validate_workflow_text(
            workflow(), path=Path("fixture.yml")
        )
        self.assertEqual((jobs, actions, checkouts, attestations, releases), (1, 2, 1, 0, 0))

    def test_owner_guarded_attestation_permissions_are_accepted(self):
        jobs, actions, checkouts, attestations, releases = validate_workflow_text(
            workflow_with_attestation(), path=Path("fixture.yml")
        )
        self.assertEqual((jobs, actions, checkouts, attestations, releases), (2, 3, 1, 1, 0))

    def test_unguarded_attestation_job_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "missing required guard"):
            validate_workflow_text(
                workflow_with_attestation(guarded=False), path=Path("fixture.yml")
            )

    def test_owner_guarded_release_permissions_are_accepted(self):
        jobs, actions, checkouts, attestations, releases = validate_workflow_text(
            workflow_with_release(), path=Path("fixture.yml")
        )
        self.assertEqual((jobs, actions, checkouts, attestations, releases), (2, 3, 2, 0, 1))

    def test_unguarded_release_job_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "missing required guard"):
            validate_workflow_text(
                workflow_with_release(guarded=False), path=Path("fixture.yml")
            )

    def test_floating_action_tag_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "full 40-hex"):
            validate_workflow_text(
                workflow(action_ref="v7"), path=Path("fixture.yml")
            )

    def test_persisted_checkout_credentials_are_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "persist-credentials"):
            validate_workflow_text(
                workflow(persist="true"), path=Path("fixture.yml")
            )

    def test_write_permission_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "top-level permissions"):
            validate_workflow_text(
                workflow(permission="write"), path=Path("fixture.yml")
            )

    def test_missing_timeout_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "timeout-minutes exactly once"):
            validate_workflow_text(
                workflow(timeout=None), path=Path("fixture.yml")
            )

    def test_excessive_timeout_is_rejected(self):
        with self.assertRaisesRegex(WorkflowSecurityError, "between 1 and 60"):
            validate_workflow_text(
                workflow(timeout="120"), path=Path("fixture.yml")
            )

    def test_no_workflows_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            with self.assertRaisesRegex(WorkflowSecurityError, "no GitHub Actions"):
                validate_workflows(root)


if __name__ == "__main__":
    unittest.main()
