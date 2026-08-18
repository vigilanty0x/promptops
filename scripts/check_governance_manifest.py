"""Validate the machine-readable external governance blocker register.

This gate validates repository-owned truthfulness only. It does not pretend to
read or mutate live GitHub administration state. Live branch protection and
attestation state must still be verified through GitHub server APIs/tools.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "repository-governance.v1.json"
PORTFOLIO = ROOT / "portfolio-compatibility.v1.json"


class GovernanceManifestError(ValueError):
    """Raised when the governance blocker register is internally dishonest."""


@dataclass(frozen=True, slots=True)
class GovernanceReceipt:
    gates: int
    packages: int
    human_approvals: int
    archive_ready: int


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


def validate_governance_manifest(root: Path = ROOT) -> GovernanceReceipt:
    root = Path(root)
    register = _load(root / "repository-governance.v1.json")
    portfolio = _load(root / "portfolio-compatibility.v1.json")

    if register.get("schema_version") != "1.0":
        raise GovernanceManifestError("governance schema_version must be 1.0")
    if register.get("repository") != "vigilanty0x/promptops":
        raise GovernanceManifestError("governance repository identity is invalid")
    observed_sha = register.get("observed_main_sha")
    if not isinstance(observed_sha, str) or len(observed_sha) != 40 or any(
        char not in "0123456789abcdef" for char in observed_sha
    ):
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

    attestation = gates["artifact_attestation"]
    if not isinstance(attestation, dict) or attestation.get("status") != "BLOCKED_VERIFICATION_TOOLING":
        raise GovernanceManifestError(
            "artifact attestation must remain BLOCKED_VERIFICATION_TOOLING until readback proof exists"
        )
    _require_bool(attestation.get("desired"), "artifact_attestation.desired", True)
    _require_bool(
        attestation.get("enabled_by_this_session"),
        "artifact_attestation.enabled_by_this_session",
        False,
    )

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
    )


def main() -> int:
    try:
        receipt = validate_governance_manifest()
    except GovernanceManifestError as exc:
        raise SystemExit(f"governance manifest gate: {exc}") from exc
    print(
        "governance manifest verified: "
        f"gates={receipt.gates} packages={receipt.packages} "
        f"human_approvals={receipt.human_approvals} archive_ready={receipt.archive_ready}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
