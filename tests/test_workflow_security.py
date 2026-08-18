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


class WorkflowSecurityTests(unittest.TestCase):
    def test_current_repository_workflows_match_security_policy(self):
        receipt = validate_workflows(REPO_ROOT)
        self.assertEqual(receipt.workflows, 1)
        self.assertEqual(receipt.jobs, 2)
        self.assertGreaterEqual(receipt.external_actions, 6)
        self.assertEqual(receipt.checkout_steps, 2)

    def test_valid_fixture_is_accepted(self):
        jobs, actions, checkouts = validate_workflow_text(
            workflow(), path=Path("fixture.yml")
        )
        self.assertEqual((jobs, actions, checkouts), (1, 2, 1))

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
        with self.assertRaisesRegex(WorkflowSecurityError, "permissions must be exactly"):
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
