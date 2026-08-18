"""Validate the machine-readable external governance blocker register.

This gate validates repository-owned truthfulness only. It does not pretend to
read or mutate live GitHub administration state. Live branch protection remains
a server-side observation. Signed wheel provenance may be recorded as verified
only when the register contains an executed owner/same-repository CI proof.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PREFIXED = re.compile(r"^sha256:[0-9a-f]{64}$")


class GovernanceManifestError(ValueError):
    """Raised when the governance register is internally dishonest."""


@dataclass(frozen=True, slots=True)
class GovernanceReceipt:
    gates: int
    packages: int
    human_approvals: int
    archive_ready: int
    attestation_status: str


def _load(path: Path) -> dict:
    if not path.is_file():
        raise GovernanceManifestError(f"required governance file is missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GovernanceManifestError(f"cannot parse governance file: {path.name}") from exc
    if not isinstance(value, dict):
        raise GovernanceManifestError(f"{path.name} root must be an object")
    return value


def _require_bool(value: object, field: str, expected: bool) -> None:
    if value is not expected:
        raise GovernanceManifestError(f"{field} must be {str(expected).lower()}")


def _require_nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceManifestError(f"{field} must be a non-empty string")
    return value


def _portfolio_counts(portfolio: dict) -> tuple[int, int, int]:
    packages = portfolio.get("packages")
    if not isinstance(packages, list) or not packages:
        raise GovernanceManifestError("portfolio manifest must contain packages")
    approvals = 0
    ready = 0
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            raise GovernanceManifestError(f"portfolio packages[{index}] must be an object")
        approval = item.get("human_archive_approval")
        archive_ready = item.get("archive_ready")
        if not isinstance(approval, bool) or not isinstance(archive_ready, bool):
            raise GovernanceManifestError(
                f"portfolio packages[{index}] archive approval fields must be boolean"
            )
        approvals += int(approval)
        ready += int(archive_ready)
        if archive_ready and not approval:
            raise GovernanceManifestError(
                f"portfolio packages[{index}] cannot be archive_ready without human approval"
            )
    return len(packages), approvals, ready


def _verify_attestation(attestation: object) -> str:
    if not isinstance(attestation, dict):
        raise GovernanceManifestError("artifact_attestation must be an object")
    expected_status = "IMPLEMENTED_VERIFIED_OWNER_PR"
    if attestation.get("status") != expected_status:
        raise GovernanceManifestError(
            f"artifact attestation status must be {expected_status} after verified provenance CI proof"
        )
    for field in (
        "desired",
        "enabled_by_this_session",
        "owner_same_repo_pr_verified",
        "main_push_configured",
    ):
        _require_bool(attestation.get(field), f"artifact_attestation.{field}", True)
    _require_bool(
        attestation.get("external_fork_pr_attestation_allowed"),
        "artifact_attestation.external_fork_pr_attestation_allowed",
        False,
    )
    if attestation.get("main_push_readback") != "TOOL_LIMITED":
        raise GovernanceManifestError(
            "artifact_attestation.main_push_readback must remain TOOL_LIMITED until live push readback is available"
        )

    strict = attestation.get("strict_verification")
    if not isinstance(strict, dict):
        raise GovernanceManifestError("artifact_attestation.strict_verification must be an object")
    for field in (
        "repository_required",
        "signer_workflow_required",
        "source_ref_required",
        "source_digest_required",
        "deny_self_hosted_runners",
    ):
        _require_bool(strict.get(field), f"artifact_attestation.strict_verification.{field}", True)

    proof = attestation.get("verified_run")
    if not isinstance(proof, dict):
        raise GovernanceManifestError("artifact_attestation.verified_run must be an object")
    if not isinstance(proof.get("run_id"), int) or proof["run_id"] <= 0:
        raise GovernanceManifestError("artifact_attestation.verified_run.run_id must be positive")
    if proof.get("event") != "pull_request":
        raise GovernanceManifestError("artifact_attestation verified proof must be a pull_request run")
    if not isinstance(proof.get("pull_request"), int) or proof["pull_request"] <= 0:
        raise GovernanceManifestError("artifact_attestation.verified_run.pull_request must be positive")
    if proof.get("workflow") != ".github/workflows/ci.yml":
        raise GovernanceManifestError("artifact attestation proof must use .github/workflows/ci.yml")
    source_ref = _require_nonempty_text(
        proof.get("source_ref"), "artifact_attestation.verified_run.source_ref"
    )
    if not source_ref.startswith("refs/pull/") or not source_ref.endswith("/merge"):
        raise GovernanceManifestError("artifact attestation proof source_ref must be a PR merge ref")
    source_digest = proof.get("source_digest")
    if not isinstance(source_digest, str) or _SHA40.fullmatch(source_digest) is None:
        raise GovernanceManifestError("artifact attestation proof source_digest must be a 40-hex commit")
    if proof.get("runner_environment") != "github-hosted":
        raise GovernanceManifestError("artifact attestation proof must use a github-hosted runner")
    if proof.get("canonical_subject_count") != 10:
        raise GovernanceManifestError("artifact attestation proof must cover exactly 10 canonical wheels")
    for field in ("attestation_id", "provenance_artifact_id"):
        if not isinstance(proof.get(field), (str, int)) or str(proof[field]).strip() in {"", "0"}:
            raise GovernanceManifestError(f"artifact_attestation.verified_run.{field} must be recorded")
    artifact_digest = proof.get("provenance_artifact_digest")
    if not isinstance(artifact_digest, str) or _SHA256_PREFIXED.fullmatch(artifact_digest) is None:
        raise GovernanceManifestError(
            "artifact attestation provenance artifact digest must be sha256:<64-hex>"
        )
    if proof.get("sigstore_media_type") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise GovernanceManifestError("artifact attestation proof must record the Sigstore bundle media type")
    if proof.get("predicate_type") != "https://slsa.dev/provenance/v1":
        raise GovernanceManifestError("artifact attestation proof must record SLSA provenance v1")
    _require_bool(
        proof.get("verified_with_gh_cli"),
        "artifact_attestation.verified_run.verified_with_gh_cli",
        True,
    )
    _require_nonempty_text(attestation.get("note"), "artifact_attestation.note")
    return expected_status


def validate_governance_manifest(root: Path = ROOT) -> GovernanceReceipt:
    root = Path(root)
    register = _load(root / "repository-governance.v1.json")
    portfolio = _load(root / "portfolio-compatibility.v1.json")

    if register.get("schema_version") != "1.0":
        raise GovernanceManifestError("governance schema_version must be 1.0")
    if register.get("repository") != "vigilanty0x/promptops":
        raise GovernanceManifestError("governance repository identity is invalid")
    observed_sha = register.get("observed_main_sha")
    if not isinstance(observed_sha, str) or _SHA40.fullmatch(observed_sha) is None:
        raise GovernanceManifestError("observed_main_sha must be a lowercase 40-hex commit SHA")

    gates = register.get("gates")
    if not isinstance(gates, dict) or set(gates) != {
        "branch_protection",
        "artifact_attestation",
        "historical_repository_archival",
    }:
        raise GovernanceManifestError("governance register must contain exactly the three external gates")

    branch = gates["branch_protection"]
    if not isinstance(branch, dict) or branch.get("status") != "BLOCKED_TOOLING":
        raise GovernanceManifestError("branch protection must remain BLOCKED_TOOLING until live closure proof")
    _require_bool(branch.get("observed_protected"), "branch_protection.observed_protected", False)
    _require_bool(branch.get("target_protected"), "branch_protection.target_protected", True)
    _require_bool(
        branch.get("write_capability_available_in_session"),
        "branch_protection.write_capability_available_in_session",
        False,
    )
    desired = branch.get("desired")
    if not isinstance(desired, dict):
        raise GovernanceManifestError("branch protection desired policy must be an object")
    for field in (
        "require_pull_request",
        "require_ci_before_merge",
        "disallow_force_push",
        "disallow_branch_deletion",
        "apply_to_administrators",
    ):
        _require_bool(desired.get(field), f"branch_protection.desired.{field}", True)

    attestation_status = _verify_attestation(gates["artifact_attestation"])

    package_count, approval_count, ready_count = _portfolio_counts(portfolio)
    archival = gates["historical_repository_archival"]
    if not isinstance(archival, dict) or archival.get("status") != "BLOCKED_HUMAN_APPROVAL":
        raise GovernanceManifestError(
            "historical repository archival must remain BLOCKED_HUMAN_APPROVAL until explicit approval"
        )
    expected_counts = {
        "packages_total": package_count,
        "human_archive_approval_count": approval_count,
        "archive_ready_count": ready_count,
    }
    for field, expected in expected_counts.items():
        if archival.get(field) != expected:
            raise GovernanceManifestError(
                f"historical_repository_archival.{field} must equal portfolio value {expected}"
            )
    if approval_count != 0 or ready_count != 0:
        raise GovernanceManifestError(
            "this blocked register must be updated/reviewed once human archive approvals change"
        )

    truth = register.get("truth_contract")
    if not isinstance(truth, dict):
        raise GovernanceManifestError("truth_contract must be an object")
    for field in (
        "blocked_is_not_done",
        "server_state_is_not_inferred_from_repository_files",
        "human_approval_is_never_synthesized",
        "tooling_limits_are_reported_instead_of_bypassed",
    ):
        _require_bool(truth.get(field), f"truth_contract.{field}", True)

    return GovernanceReceipt(
        gates=len(gates),
        packages=package_count,
        human_approvals=approval_count,
        archive_ready=ready_count,
        attestation_status=attestation_status,
    )


def main() -> int:
    try:
        receipt = validate_governance_manifest()
    except GovernanceManifestError as exc:
        raise SystemExit(f"governance manifest gate: {exc}") from exc
    print(
        "governance manifest verified: "
        f"gates={receipt.gates} packages={receipt.packages} "
        f"human_approvals={receipt.human_approvals} archive_ready={receipt.archive_ready} "
        f"attestation={receipt.attestation_status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
