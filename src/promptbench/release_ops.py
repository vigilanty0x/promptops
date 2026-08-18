"""Fail-closed release evidence validation for PromptOps.

The 0.3 release path verifies every content-addressed input before trusting its
kind or gate fields. This prevents a caller from editing a scorecard or flipping
a regression result while retaining the old artifact SHA.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .ops import OPS_SCHEMA_VERSION, OpsValidationError, _digest
from .routing import validate_scorecard

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _verify_artifact(artifact: Mapping[str, Any], *, kind: str, field: str) -> dict[str, Any]:
    if not isinstance(artifact, Mapping):
        raise OpsValidationError(f"{field} must be an object")
    payload = dict(artifact)
    artifact_sha = payload.pop("artifact_sha", None)
    if not isinstance(artifact_sha, str) or _SHA256.fullmatch(artifact_sha) is None:
        raise OpsValidationError(f"{field}.artifact_sha must be a lowercase SHA-256 hex digest")
    if _digest(payload) != artifact_sha:
        raise OpsValidationError(f"{field}.artifact_sha does not match artifact content")
    if payload.get("schema_version") != OPS_SCHEMA_VERSION:
        raise OpsValidationError(f"{field} uses an unsupported schema_version")
    if payload.get("kind") != kind:
        raise OpsValidationError(f"{field} must be a {kind} artifact")
    payload["artifact_sha"] = artifact_sha
    return payload


def _verify_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    value = _verify_artifact(dataset, kind="dataset_manifest", field="dataset")
    datasets = value.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise OpsValidationError("dataset.datasets must be a non-empty array")
    return value


def _verify_regression(regression: Mapping[str, Any], index: int) -> dict[str, Any]:
    value = _verify_artifact(regression, kind="regression", field=f"regressions[{index}]")
    if not isinstance(value.get("passed"), bool):
        raise OpsValidationError(f"regressions[{index}].passed must be boolean")
    count = value.get("regression_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise OpsValidationError(f"regressions[{index}].regression_count must be a non-negative integer")
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise OpsValidationError(f"regressions[{index}].rows must be an array")
    return value


def release_manifest(
    *,
    release_version: str,
    dataset: Mapping[str, Any],
    scorecards: Sequence[Mapping[str, Any]],
    regressions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Bind verified PromptOps artifacts into one deterministic release gate."""

    if not isinstance(release_version, str) or not release_version.strip():
        raise OpsValidationError("release_version must be a non-empty string")
    verified_dataset = _verify_dataset(dataset)
    if not isinstance(scorecards, Sequence) or isinstance(scorecards, (str, bytes)) or not scorecards:
        raise OpsValidationError("release requires at least one scorecard")
    if not isinstance(regressions, Sequence) or isinstance(regressions, (str, bytes)):
        raise OpsValidationError("regressions must be an array")

    verified_scorecards: list[dict[str, Any]] = []
    for index, scorecard in enumerate(scorecards):
        try:
            verified_scorecards.append(validate_scorecard(scorecard))
        except OpsValidationError as exc:
            raise OpsValidationError(f"scorecards[{index}]: {exc}") from exc
    verified_regressions = [_verify_regression(item, index) for index, item in enumerate(regressions)]
    failed = [item for item in verified_regressions if item["passed"] is False]

    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "release_manifest",
        "release_version": release_version,
        "dataset_sha": verified_dataset["artifact_sha"],
        "scorecard_shas": sorted(item["artifact_sha"] for item in verified_scorecards),
        "regression_shas": sorted(item["artifact_sha"] for item in verified_regressions),
        "evidence_hashes_verified": True,
        "regression_gate_passed": not failed,
        "failed_regression_count": len(failed),
    }
    result["artifact_sha"] = _digest(result)
    return result
