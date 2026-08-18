"""Verify a release manifest against an explicit set of local evidence artifacts.

The bundle verifier never scans directories and never fetches remote evidence.
Callers supply the release manifest and every local dataset/scorecard/regression
artifact that should satisfy its references. Each artifact is verified first,
then the exact unique evidence set and release-gate semantics are reconciled.

One physical evidence artifact may satisfy repeated identical SHA references in
the release manifest. Reference multiplicity still matters for gate counters.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .ops import OpsValidationError
from .verification import verify_artifact

MAX_BUNDLE_ARTIFACTS = 1024
_EVIDENCE_KINDS = {"dataset_manifest", "scorecard", "regression"}


def _reference_key(kind: str, artifact_sha: str) -> tuple[str, str]:
    return kind, artifact_sha


def verify_release_bundle(
    release: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify one release manifest and the exact local evidence set it names."""

    release_receipt = verify_artifact(release, expected_kind="release_manifest")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)):
        raise OpsValidationError("artifacts must be an array")
    if not 1 <= len(artifacts) <= MAX_BUNDLE_ARTIFACTS:
        raise OpsValidationError(
            f"bundle must contain 1 to {MAX_BUNDLE_ARTIFACTS} evidence artifacts"
        )

    expected: set[tuple[str, str]] = {
        _reference_key("dataset_manifest", release["dataset_sha"]),
    }
    expected.update(
        _reference_key("scorecard", artifact_sha)
        for artifact_sha in release["scorecard_shas"]
    )
    expected.update(
        _reference_key("regression", artifact_sha)
        for artifact_sha in release["regression_shas"]
    )
    if len(expected) > MAX_BUNDLE_ARTIFACTS:
        raise OpsValidationError(
            f"release references more than {MAX_BUNDLE_ARTIFACTS} unique evidence artifacts"
        )

    supplied: dict[tuple[str, str], Mapping[str, Any]] = {}
    receipts: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        receipt = verify_artifact(artifact)
        kind = receipt["kind"]
        if kind not in _EVIDENCE_KINDS:
            raise OpsValidationError(
                f"artifacts[{index}] has unsupported bundle evidence kind: {kind}"
            )
        key = _reference_key(kind, receipt["artifact_sha"])
        if key in supplied:
            raise OpsValidationError(
                f"duplicate supplied evidence: {kind} {receipt['artifact_sha']}"
            )
        supplied[key] = artifact
        receipts.append(receipt)

    supplied_keys = set(supplied)
    missing = sorted(expected - supplied_keys)
    extra = sorted(supplied_keys - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            preview = ", ".join(f"{kind}:{digest}" for kind, digest in missing[:8])
            details.append(f"missing evidence [{preview}]")
        if extra:
            preview = ", ".join(f"{kind}:{digest}" for kind, digest in extra[:8])
            details.append(f"unexpected evidence [{preview}]")
        raise OpsValidationError("release bundle mismatch: " + "; ".join(details))

    dataset_key = _reference_key("dataset_manifest", release["dataset_sha"])
    if dataset_key not in supplied:
        raise OpsValidationError("release dataset evidence is missing")

    # Preserve reference multiplicity from the producer: a release may contain
    # the same regression SHA more than once. One supplied artifact satisfies
    # the repeated reference, while each reference still contributes to the
    # release producer's failed_regression_count.
    regression_references = [
        supplied[_reference_key("regression", artifact_sha)]
        for artifact_sha in release["regression_shas"]
    ]
    observed_failed = sum(
        1 for regression in regression_references if regression.get("passed") is False
    )
    if release["failed_regression_count"] != observed_failed:
        raise OpsValidationError(
            "release failed_regression_count does not match supplied regression evidence"
        )
    observed_gate = observed_failed == 0
    if release["regression_gate_passed"] != observed_gate:
        raise OpsValidationError(
            "release regression_gate_passed does not match supplied regression evidence"
        )

    receipts.sort(key=lambda item: (item["kind"], item["artifact_sha"]))
    unique_scorecards = {
        _reference_key("scorecard", sha) for sha in release["scorecard_shas"]
    }
    unique_regressions = {
        _reference_key("regression", sha) for sha in release["regression_shas"]
    }
    return {
        "valid": True,
        "release_sha": release_receipt["artifact_sha"],
        "release_version": release["release_version"],
        "release_source_evidence_integrity": release_receipt.get(
            "source_evidence_integrity", "not-applicable"
        ),
        "expected_unique_evidence_count": len(expected),
        "provided_unique_evidence_count": len(supplied),
        "dataset_verified": True,
        "scorecard_reference_count": len(release["scorecard_shas"]),
        "unique_scorecard_count": len(unique_scorecards),
        "regression_reference_count": len(release["regression_shas"]),
        "unique_regression_count": len(unique_regressions),
        "observed_failed_regression_count": observed_failed,
        "release_gate_passed": observed_gate,
        "integrity": "verified",
        "contract": "verified",
        "linkage": "verified",
        "provenance": "not-verified",
        "evidence": receipts,
    }
