"""Validate the machine-readable governance register.

Live branch protection remains a server-side observation. Historical signed
provenance is immutable evidence and must agree with `published-release.v1.json`,
not with `release-policy.v1.json` (which may already authorize the next release).
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
    published_release: str


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


def _require_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise GovernanceManifestError(f"{field} must be a positive integer")
    return value


def _portfolio_counts(portfolio: dict) -> tuple[int, int, int]:
    packages = portfolio.get("packages")
    if not isinstance(packages, list) or not packages:
        raise GovernanceManifestError("portfolio manifest must contain packages")
    approvals = ready = 0
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


def _verify_published_record(record: object) -> tuple[str, str, str, str]:
    if not isinstance(record, dict):
        raise GovernanceManifestError("published-release record must be an object")
    if record.get("schema_version") != "1.0":
        raise GovernanceManifestError("published-release schema_version must be 1.0")
    if record.get("repository") != "vigilanty0x/promptops":
        raise GovernanceManifestError("published-release repository mismatch")
    version = _require_nonempty_text(record.get("version"), "published-release.version")
    tag = _require_nonempty_text(record.get("tag"), "published-release.tag")
    if tag != f"v{version}":
        raise GovernanceManifestError("published-release tag/version mismatch")
    if record.get("source_ref") != "refs/heads/main":
        raise GovernanceManifestError("published-release source_ref must be refs/heads/main")
    digest = record.get("source_digest")
    if not isinstance(digest, str) or _SHA40.fullmatch(digest) is None:
        raise GovernanceManifestError("published-release source_digest must be 40-hex")
    if record.get("release_asset_count") != 13 or record.get("canonical_wheel_count") != 10:
        raise GovernanceManifestError("published-release must record 13 assets and 10 wheels")
    attestation_id = record.get("attestation_id")
    if not isinstance(attestation_id, str) or not attestation_id.isdigit():
        raise GovernanceManifestError("published-release attestation_id must be numeric text")
    if record.get("verification_workflow") != ".github/workflows/release-verify.yml":
        raise GovernanceManifestError("published-release verification workflow mismatch")
    _require_positive_int(record.get("verification_run_id"), "published-release.verification_run_id")
    _require_positive_int(record.get("verification_pull_request"), "published-release.verification_pull_request")
    for field in (
        "source_commit_signature_verified",
        "release_integrity_verified",
        "wheel_provenance_verified",
        "immutable",
    ):
        _require_bool(record.get(field), f"published-release.{field}", True)
    return version, tag, digest, attestation_id


def _verify_owner_pr_proof(proof: object) -> None:
    if not isinstance(proof, dict):
        raise GovernanceManifestError("artifact_attestation.verified_run must be an object")
    _require_positive_int(proof.get("run_id"), "artifact_attestation.verified_run.run_id")
    if proof.get("event") != "pull_request":
        raise GovernanceManifestError("artifact attestation owner proof must be a pull_request run")
    _require_positive_int(proof.get("pull_request"), "artifact_attestation.verified_run.pull_request")
    if proof.get("workflow") != ".github/workflows/ci.yml":
        raise GovernanceManifestError("artifact attestation owner proof must use .github/workflows/ci.yml")
    source_ref = _require_nonempty_text(proof.get("source_ref"), "artifact_attestation.verified_run.source_ref")
    if not source_ref.startswith("refs/pull/") or not source_ref.endswith("/merge"):
        raise GovernanceManifestError("artifact attestation owner proof source_ref must be a PR merge ref")
    source_digest = proof.get("source_digest")
    if not isinstance(source_digest, str) or _SHA40.fullmatch(source_digest) is None:
        raise GovernanceManifestError("artifact attestation owner proof source_digest must be 40-hex")
    if proof.get("runner_environment") != "github-hosted":
        raise GovernanceManifestError("artifact attestation owner proof must use github-hosted")
    if proof.get("canonical_subject_count") != 10:
        raise GovernanceManifestError("artifact attestation owner proof must cover 10 wheels")
    for field in ("attestation_id", "provenance_artifact_id"):
        if str(proof.get(field, "")).strip() in {"", "0"}:
            raise GovernanceManifestError(f"artifact_attestation.verified_run.{field} must be recorded")
    artifact_digest = proof.get("provenance_artifact_digest")
    if not isinstance(artifact_digest, str) or _SHA256_PREFIXED.fullmatch(artifact_digest) is None:
        raise GovernanceManifestError("owner provenance artifact digest must be sha256:<64-hex>")
    if proof.get("sigstore_media_type") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise GovernanceManifestError("owner proof must record Sigstore bundle v0.3")
    if proof.get("predicate_type") != "https://slsa.dev/provenance/v1":
        raise GovernanceManifestError("owner proof must record SLSA provenance v1")
    _require_bool(proof.get("verified_with_gh_cli"), "artifact_attestation.verified_run.verified_with_gh_cli", True)


def _verify_main_release_proof(proof: object, published_record: dict) -> str:
    version, tag, source_digest, attestation_id = _verify_published_record(published_record)
    if not isinstance(proof, dict):
        raise GovernanceManifestError("artifact_attestation.main_release_proof must be an object")
    if proof.get("release_verification_run_id") != published_record.get("verification_run_id"):
        raise GovernanceManifestError("main release proof verification run must match published-release record")
    if proof.get("release_verification_workflow") != published_record.get("verification_workflow"):
        raise GovernanceManifestError("main release proof workflow must match published-release record")
    if proof.get("verification_pull_request") != published_record.get("verification_pull_request"):
        raise GovernanceManifestError("main release proof PR must match published-release record")
    if proof.get("verification_event") != "pull_request":
        raise GovernanceManifestError("main release proof verification event must be pull_request")
    expected = {
        "published_version": version,
        "published_tag": tag,
        "source_ref": "refs/heads/main",
        "source_digest": source_digest,
        "canonical_subject_count": 10,
        "release_asset_count": 13,
        "attestation_id": attestation_id,
    }
    for field, value in expected.items():
        if proof.get(field) != value:
            raise GovernanceManifestError(
                f"artifact_attestation.main_release_proof.{field} must match published-release record"
            )
    for field in (
        "release_tag_matches_source",
        "source_commit_signature_verified",
        "published_release_integrity_verified",
        "published_wheel_provenance_verified",
    ):
        _require_bool(proof.get(field), f"artifact_attestation.main_release_proof.{field}", True)
    if proof.get("verification_token_permissions") != {"contents": "read", "metadata": "read"}:
        raise GovernanceManifestError("main release proof must record read-only verification token permissions")
    return f"{version}@{tag}"


def _verify_attestation(attestation: object, published_record: dict) -> tuple[str, str]:
    if not isinstance(attestation, dict):
        raise GovernanceManifestError("artifact_attestation must be an object")
    expected_status = "IMPLEMENTED_VERIFIED_PR_AND_MAIN_RELEASE"
    if attestation.get("status") != expected_status:
        raise GovernanceManifestError(f"artifact attestation status must be {expected_status}")
    for field in (
        "desired",
        "enabled_by_this_session",
        "owner_same_repo_pr_verified",
        "main_push_configured",
        "main_push_verified_via_release",
    ):
        _require_bool(attestation.get(field), f"artifact_attestation.{field}", True)
    _require_bool(
        attestation.get("external_fork_pr_attestation_allowed"),
        "artifact_attestation.external_fork_pr_attestation_allowed",
        False,
    )
    if attestation.get("main_push_readback") != "VERIFIED_VIA_PUBLISHED_RELEASE":
        raise GovernanceManifestError("artifact_attestation.main_push_readback must be VERIFIED_VIA_PUBLISHED_RELEASE")
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
    _verify_owner_pr_proof(attestation.get("verified_run"))
    published = _verify_main_release_proof(attestation.get("main_release_proof"), published_record)
    _require_nonempty_text(attestation.get("note"), "artifact_attestation.note")
    return expected_status, published


def validate_governance_manifest(root: Path = ROOT) -> GovernanceReceipt:
    root = Path(root)
    register = _load(root / "repository-governance.v1.json")
    portfolio = _load(root / "portfolio-compatibility.v1.json")
    published_record = _load(root / "published-release.v1.json")

    if register.get("schema_version") != "1.1":
        raise GovernanceManifestError("governance schema_version must be 1.1")
    if register.get("repository") != "vigilanty0x/promptops":
        raise GovernanceManifestError("governance repository identity is invalid")
    if "observed_main_sha" in register:
        raise GovernanceManifestError(
            "observed_main_sha must not be persisted: merging a live-SHA claim makes it self-obsoleting"
        )

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
    if branch.get("observed_ref") != "main":
        raise GovernanceManifestError("branch protection observed_ref must be main")
    _require_nonempty_text(branch.get("observation_semantics"), "branch_protection.observation_semantics")
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

    attestation_status, published_release = _verify_attestation(
        gates["artifact_attestation"], published_record
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
        "live_main_sha_is_not_persisted",
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
        published_release=published_release,
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
        f"attestation={receipt.attestation_status} published_release={receipt.published_release}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
