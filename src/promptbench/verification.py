"""Generic fail-closed verification for stored PromptOps artifacts.

The verifier recomputes content hashes and then checks kind-specific internal
invariants.  It does not claim provenance: it proves that the supplied local
artifact is self-consistent under the PromptOps 1.0 contracts.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

from .ops import (
    MAX_DATASETS,
    MAX_FAILURES,
    OpsValidationError,
    _verified_artifact,
)
from .routing import MAX_ROUTING_CANDIDATES, validate_scorecard

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED = {
    "scorecard",
    "regression",
    "failure_corpus",
    "jury_consensus",
    "dataset_manifest",
    "route_decision",
    "release_manifest",
}


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpsValidationError(f"{field} must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpsValidationError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OpsValidationError(f"{field} must be an integer >= {minimum}")
    return value


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpsValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise OpsValidationError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise OpsValidationError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise OpsValidationError(f"{field} must be <= {maximum}")
    return result


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OpsValidationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _verify_regression(value: Mapping[str, Any]) -> None:
    _text(value.get("suite_id"), "suite_id")
    _text(value.get("baseline_suite_version"), "baseline_suite_version")
    _text(value.get("current_suite_version"), "current_suite_version")
    _sha(value.get("baseline_report_sha"), "baseline_report_sha")
    _sha(value.get("current_report_sha"), "current_report_sha")
    passed = value.get("passed")
    if not isinstance(passed, bool):
        raise OpsValidationError("passed must be boolean")
    count = _integer(value.get("regression_count"), "regression_count")
    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        raise OpsValidationError("rows must be a non-empty array")
    observed = 0
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"rows[{index}]")
        candidate = _text(row.get("candidate_id"), f"rows[{index}].candidate_id")
        if candidate in seen:
            raise OpsValidationError("regression candidate ids must be unique")
        seen.add(candidate)
        regressed = row.get("regressed")
        reasons = row.get("reasons")
        if not isinstance(regressed, bool) or not isinstance(reasons, list):
            raise OpsValidationError(f"rows[{index}] must contain boolean regressed and array reasons")
        if len(reasons) != len(set(reasons)):
            raise OpsValidationError(f"rows[{index}] regression reasons must be unique")
        if regressed != bool(reasons):
            raise OpsValidationError(f"rows[{index}] regressed must match presence of reasons")
        for reason in reasons:
            if reason not in {"pass_rate", "latency", "cost"}:
                raise OpsValidationError(f"rows[{index}] contains an unknown regression reason")
        for field in ("pass_rate_delta", "latency_relative_delta", "cost_relative_delta"):
            # compare_reports can legitimately emit +inf when the baseline metric is zero.
            metric = row.get(field)
            if isinstance(metric, bool) or not isinstance(metric, (int, float)) or math.isnan(float(metric)):
                raise OpsValidationError(f"rows[{index}].{field} must be numeric and not NaN")
        if regressed:
            observed += 1
    if count != observed:
        raise OpsValidationError("regression_count does not match regressed rows")
    if passed != (count == 0):
        raise OpsValidationError("passed must equal regression_count == 0")


def _verify_failure_corpus(value: Mapping[str, Any]) -> None:
    _text(value.get("suite_id"), "suite_id")
    _text(value.get("suite_version"), "suite_version")
    _sha(value.get("source_report_sha"), "source_report_sha")
    count = _integer(value.get("failure_count"), "failure_count")
    if not isinstance(value.get("truncated"), bool):
        raise OpsValidationError("truncated must be boolean")
    failures = value.get("failures")
    if not isinstance(failures, list) or len(failures) > MAX_FAILURES:
        raise OpsValidationError(f"failures must be an array bounded to {MAX_FAILURES}")
    if count != len(failures):
        raise OpsValidationError("failure_count must equal failures length")
    for index, raw in enumerate(failures):
        failure = _mapping(raw, f"failures[{index}]")
        if "output" in failure or "raw_output" in failure:
            raise OpsValidationError("failure corpus must not duplicate raw output")
        if failure.get("output_sha") is not None:
            _sha(failure.get("output_sha"), f"failures[{index}].output_sha")


def _verify_jury(value: Mapping[str, Any]) -> None:
    _text(value.get("suite_id"), "suite_id")
    ballots = value.get("ballots")
    ranking = value.get("ranking")
    rows = value.get("rows")
    if not isinstance(ballots, list) or not ballots:
        raise OpsValidationError("ballots must be a non-empty array")
    if _integer(value.get("ballot_count"), "ballot_count", minimum=1) != len(ballots):
        raise OpsValidationError("ballot_count must equal ballots length")
    if not isinstance(ranking, list) or not ranking or len(ranking) != len(set(ranking)):
        raise OpsValidationError("ranking must be a non-empty unique array")
    ranking = [_text(item, "ranking[]") for item in ranking]
    if value.get("winner") != ranking[0]:
        raise OpsValidationError("winner must equal rank 1")
    if not isinstance(rows, list) or len(rows) != len(ranking):
        raise OpsValidationError("rows must align with ranking")
    row_ids: list[str] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"rows[{index}]")
        row_ids.append(_text(row.get("candidate_id"), f"rows[{index}].candidate_id"))
        _integer(row.get("points"), f"rows[{index}].points")
        _integer(row.get("ballots"), f"rows[{index}].ballots", minimum=1)
        for field in ("mean_pass_rate", "mean_cost_microunits", "mean_latency_ms"):
            _number(row.get(field), f"rows[{index}].{field}", minimum=0.0)
    if row_ids != ranking:
        raise OpsValidationError("jury rows must follow ranking order")
    for index, raw in enumerate(ballots):
        ballot = _mapping(raw, f"ballots[{index}]")
        _sha(ballot.get("report_sha"), f"ballots[{index}].report_sha")
        _text(ballot.get("suite_version"), f"ballots[{index}].suite_version")
        ballot_ranking = ballot.get("ranking")
        if (
            not isinstance(ballot_ranking, list)
            or not ballot_ranking
            or len(ballot_ranking) != len(set(ballot_ranking))
        ):
            raise OpsValidationError(f"ballots[{index}].ranking must be non-empty and unique")
        for candidate in ballot_ranking:
            _text(candidate, f"ballots[{index}].ranking[]")


def _verify_dataset(value: Mapping[str, Any]) -> None:
    datasets = value.get("datasets")
    if not isinstance(datasets, list) or not 1 <= len(datasets) <= MAX_DATASETS:
        raise OpsValidationError(f"datasets must contain 1 to {MAX_DATASETS} entries")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(datasets):
        item = _mapping(raw, f"datasets[{index}]")
        suite_id = _text(item.get("suite_id"), f"datasets[{index}].suite_id")
        version = _text(item.get("version"), f"datasets[{index}].version")
        _sha(item.get("suite_sha"), f"datasets[{index}].suite_sha")
        key = (suite_id, version)
        if key in seen:
            raise OpsValidationError("dataset manifest contains duplicate suite_id/version pairs")
        seen.add(key)
        for field in ("scenario_count", "candidate_count"):
            count = item.get(field)
            if count is not None:
                _integer(count, f"datasets[{index}].{field}")


def _verify_route(value: Mapping[str, Any]) -> None:
    _text(value.get("suite_id"), "suite_id")
    _text(value.get("suite_version"), "suite_version")
    _sha(value.get("source_scorecard_sha"), "source_scorecard_sha")
    policy = _mapping(value.get("policy"), "policy")
    min_pass = _number(policy.get("min_pass_rate"), "policy.min_pass_rate", minimum=0.0, maximum=1.0)
    max_latency_raw = policy.get("max_mean_latency_ms")
    max_cost_raw = policy.get("max_total_cost_microunits")
    max_latency = None if max_latency_raw is None else _number(
        max_latency_raw, "policy.max_mean_latency_ms", minimum=0.0
    )
    max_cost = None if max_cost_raw is None else _number(
        max_cost_raw, "policy.max_total_cost_microunits", minimum=0.0
    )
    allowed_raw = policy.get("allowed_candidates")
    if allowed_raw is None:
        allowed = None
    else:
        if (
            not isinstance(allowed_raw, list)
            or not 1 <= len(allowed_raw) <= MAX_ROUTING_CANDIDATES
            or len(allowed_raw) != len(set(allowed_raw))
        ):
            raise OpsValidationError("policy.allowed_candidates must be a bounded unique array or null")
        allowed = {_text(item, "policy.allowed_candidates[]") for item in allowed_raw}
    fallback_count = _integer(policy.get("fallback_count"), "policy.fallback_count")
    if fallback_count > 64:
        raise OpsValidationError("policy.fallback_count exceeds 64")

    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_ROUTING_CANDIDATES:
        raise OpsValidationError("route candidates must be a bounded non-empty array")
    if _integer(value.get("considered_count"), "considered_count", minimum=1) != len(candidates):
        raise OpsValidationError("considered_count must equal candidates length")
    ranks: list[int] = []
    eligible: list[str] = []
    for index, raw in enumerate(candidates):
        row = _mapping(raw, f"candidates[{index}]")
        ranks.append(_integer(row.get("rank"), f"candidates[{index}].rank", minimum=1))
        candidate = _text(row.get("candidate_id"), f"candidates[{index}].candidate_id")
        pass_rate = _number(
            row.get("pass_rate"), f"candidates[{index}].pass_rate", minimum=0.0, maximum=1.0
        )
        latency = _number(
            row.get("mean_latency_ms"), f"candidates[{index}].mean_latency_ms", minimum=0.0
        )
        cost = _number(
            row.get("total_cost_microunits"),
            f"candidates[{index}].total_cost_microunits",
            minimum=0.0,
        )
        is_eligible = row.get("eligible")
        reasons = row.get("reasons")
        if not isinstance(is_eligible, bool) or not isinstance(reasons, list):
            raise OpsValidationError(f"candidates[{index}] eligibility contract is invalid")
        expected_reasons: list[str] = []
        if allowed is not None and candidate not in allowed:
            expected_reasons.append("not_allowed")
        if pass_rate < min_pass:
            expected_reasons.append("pass_rate")
        if max_latency is not None and latency > max_latency:
            expected_reasons.append("latency")
        if max_cost is not None and cost > max_cost:
            expected_reasons.append("cost")
        if reasons != expected_reasons:
            raise OpsValidationError(f"candidates[{index}] reasons do not match policy and metrics")
        if is_eligible != (len(expected_reasons) == 0):
            raise OpsValidationError(f"candidates[{index}] eligible does not match policy and metrics")
        if is_eligible:
            eligible.append(candidate)
    if ranks != list(range(1, len(candidates) + 1)):
        raise OpsValidationError("route candidate ranks must be consecutive and ordered")
    if _integer(value.get("eligible_count"), "eligible_count") != len(eligible):
        raise OpsValidationError("eligible_count must equal eligible candidates")
    decision = value.get("decision")
    selected = value.get("selected_candidate")
    fallbacks = value.get("fallback_candidates")
    if not isinstance(fallbacks, list):
        raise OpsValidationError("fallback_candidates must be an array")
    expected_selected = eligible[0] if eligible else None
    expected_fallbacks = eligible[1 : 1 + fallback_count] if eligible else []
    if decision not in {"route", "abstain"}:
        raise OpsValidationError("decision must be route or abstain")
    if decision != ("route" if eligible else "abstain") or selected != expected_selected:
        raise OpsValidationError("route decision does not match eligible rank order")
    if fallbacks != expected_fallbacks:
        raise OpsValidationError("fallback_candidates do not match routing policy")


def _verify_release(value: Mapping[str, Any]) -> None:
    _text(value.get("release_version"), "release_version")
    _sha(value.get("dataset_sha"), "dataset_sha")
    scorecards = value.get("scorecard_shas")
    regressions = value.get("regression_shas")
    if not isinstance(scorecards, list) or not scorecards:
        raise OpsValidationError("scorecard_shas must be a non-empty array")
    if not isinstance(regressions, list):
        raise OpsValidationError("regression_shas must be an array")
    for index, digest in enumerate(scorecards):
        _sha(digest, f"scorecard_shas[{index}]")
    for index, digest in enumerate(regressions):
        _sha(digest, f"regression_shas[{index}]")
    if scorecards != sorted(scorecards) or regressions != sorted(regressions):
        raise OpsValidationError("release evidence SHA arrays must be sorted")
    if value.get("evidence_hashes_verified") is not True:
        raise OpsValidationError("release manifest must record evidence_hashes_verified=true")
    gate = value.get("regression_gate_passed")
    if not isinstance(gate, bool):
        raise OpsValidationError("regression_gate_passed must be boolean")
    failed = _integer(value.get("failed_regression_count"), "failed_regression_count")
    if gate != (failed == 0):
        raise OpsValidationError("regression_gate_passed must match failed_regression_count")
    if failed > len(regressions):
        raise OpsValidationError("failed_regression_count exceeds regression evidence count")


def verify_artifact(artifact: Mapping[str, Any], *, expected_kind: str | None = None) -> dict[str, Any]:
    """Verify one stored PromptOps artifact and return a compact receipt."""

    raw = _mapping(artifact, "artifact")
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in _SUPPORTED:
        raise OpsValidationError("unsupported PromptOps artifact kind")
    if expected_kind is not None:
        if expected_kind not in _SUPPORTED:
            raise OpsValidationError("expected_kind is unsupported")
        if kind != expected_kind:
            raise OpsValidationError(f"expected {expected_kind} artifact, got {kind}")

    if kind == "scorecard":
        value = validate_scorecard(raw)
    else:
        value = _verified_artifact(raw, kind=kind, field="artifact")
        {
            "regression": _verify_regression,
            "failure_corpus": _verify_failure_corpus,
            "jury_consensus": _verify_jury,
            "dataset_manifest": _verify_dataset,
            "route_decision": _verify_route,
            "release_manifest": _verify_release,
        }[kind](value)

    return {
        "valid": True,
        "schema_version": value["schema_version"],
        "kind": kind,
        "artifact_sha": raw["artifact_sha"],
        "integrity": "verified",
        "contract": "verified",
        "provenance": "not-verified",
    }
