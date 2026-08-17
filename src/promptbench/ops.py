"""Deterministic PromptOps primitives built on PromptBench report contracts.

This module intentionally stays offline and provider-agnostic.  It consumes the
versioned JSON dictionaries emitted by PromptBench and produces content-addressed
scorecards, regressions, consensus decisions, dataset manifests, and failure
corpora without calling a model or network service.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


OPS_SCHEMA_VERSION = "1.0"
MAX_REPORTS = 256
MAX_FAILURES = 10_000
MAX_DATASETS = 512


class OpsValidationError(ValueError):
    """Raised when a PromptOps input violates the stable operations contract."""


def _canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(data: Any) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpsValidationError(f"{field} must be an object")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpsValidationError(f"{field} must be a non-empty string")
    return value


def _require_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpsValidationError(f"{field} must be numeric")
    return float(value)


def _unsigned_report(report: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    expected = payload.pop("report_sha", None)
    if not isinstance(expected, str) or len(expected) != 64:
        raise OpsValidationError("report_sha must be a SHA-256 hex digest")
    if _digest(payload) != expected:
        raise OpsValidationError("report_sha does not match report content")
    return payload


def validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the minimal stable report contract and its content hash.

    The function deliberately validates only fields required by PromptOps so
    future PromptBench report fields can be added without breaking consumers.
    """

    payload = _unsigned_report(_require_mapping(report, "report"))
    _require_text(payload.get("suite_id"), "suite_id")
    _require_text(payload.get("suite_version"), "suite_version")
    candidates = payload.get("candidates")
    records = payload.get("records")
    ranking = payload.get("ranking")
    if not isinstance(candidates, list) or not candidates:
        raise OpsValidationError("candidates must be a non-empty array")
    if not isinstance(records, list):
        raise OpsValidationError("records must be an array")
    if not isinstance(ranking, list) or not ranking:
        raise OpsValidationError("ranking must be a non-empty array")

    ids: list[str] = []
    for index, candidate in enumerate(candidates):
        item = _require_mapping(candidate, f"candidates[{index}]")
        candidate_id = _require_text(item.get("candidate_id"), f"candidates[{index}].candidate_id")
        ids.append(candidate_id)
        _require_number(item.get("pass_rate"), f"candidates[{index}].pass_rate")
        _require_number(item.get("mean_latency_ms"), f"candidates[{index}].mean_latency_ms")
        _require_number(item.get("total_cost_microunits"), f"candidates[{index}].total_cost_microunits")
    if len(ids) != len(set(ids)):
        raise OpsValidationError("candidate ids must be unique")
    if set(ranking) != set(ids) or len(ranking) != len(ids):
        raise OpsValidationError("ranking must contain every candidate exactly once")
    return payload


@dataclass(frozen=True, slots=True)
class RegressionThresholds:
    """Explicit regression tolerances.

    Pass-rate changes are absolute fractions. Latency and cost tolerances are
    relative increases, e.g. ``0.20`` means +20% is tolerated.
    """

    pass_rate_drop: float = 0.0
    latency_increase: float = 0.25
    cost_increase: float = 0.25

    def __post_init__(self) -> None:
        for name, value in (
            ("pass_rate_drop", self.pass_rate_drop),
            ("latency_increase", self.latency_increase),
            ("cost_increase", self.cost_increase),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
                raise OpsValidationError(f"{name} must be between 0 and 10")

    def to_dict(self) -> dict[str, float]:
        return {
            "pass_rate_drop": float(self.pass_rate_drop),
            "latency_increase": float(self.latency_increase),
            "cost_increase": float(self.cost_increase),
        }


def build_scorecard(report: Mapping[str, Any]) -> dict[str, Any]:
    """Create a compact, content-addressed scorecard from one report."""

    payload = validate_report(report)
    by_id = {item["candidate_id"]: item for item in payload["candidates"]}
    rows: list[dict[str, Any]] = []
    for rank, candidate_id in enumerate(payload["ranking"], start=1):
        item = by_id[candidate_id]
        rows.append(
            {
                "rank": rank,
                "candidate_id": candidate_id,
                "model": item.get("model"),
                "pass_rate": item["pass_rate"],
                "pass_at_1": item.get("pass_at_1"),
                "score_variance": item.get("score_variance"),
                "mean_latency_ms": item["mean_latency_ms"],
                "p95_latency_ms": item.get("p95_latency_ms"),
                "total_cost_microunits": item["total_cost_microunits"],
                "recovery_rate": item.get("recovery_rate"),
            }
        )
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "scorecard",
        "suite_id": payload["suite_id"],
        "suite_version": payload["suite_version"],
        "source_report_sha": report["report_sha"],
        "winner": payload["ranking"][0],
        "rows": rows,
    }
    result["artifact_sha"] = _digest(result)
    return result


def _relative_increase(before: float, after: float) -> float:
    if before == 0:
        return 0.0 if after == 0 else float("inf")
    return (after - before) / before


def compare_reports(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    thresholds: RegressionThresholds | None = None,
) -> dict[str, Any]:
    """Compare two reports and classify deterministic candidate regressions."""

    base = validate_report(baseline)
    now = validate_report(current)
    if base["suite_id"] != now["suite_id"]:
        raise OpsValidationError("reports must use the same suite_id")
    thresholds = thresholds or RegressionThresholds()
    base_by_id = {item["candidate_id"]: item for item in base["candidates"]}
    now_by_id = {item["candidate_id"]: item for item in now["candidates"]}
    shared = sorted(set(base_by_id) & set(now_by_id))
    if not shared:
        raise OpsValidationError("reports have no shared candidates")

    rows: list[dict[str, Any]] = []
    regression_count = 0
    for candidate_id in shared:
        old = base_by_id[candidate_id]
        new = now_by_id[candidate_id]
        pass_delta = float(new["pass_rate"]) - float(old["pass_rate"])
        latency_delta = _relative_increase(float(old["mean_latency_ms"]), float(new["mean_latency_ms"]))
        cost_delta = _relative_increase(float(old["total_cost_microunits"]), float(new["total_cost_microunits"]))
        reasons: list[str] = []
        if pass_delta < -float(thresholds.pass_rate_drop):
            reasons.append("pass_rate")
        if latency_delta > float(thresholds.latency_increase):
            reasons.append("latency")
        if cost_delta > float(thresholds.cost_increase):
            reasons.append("cost")
        if reasons:
            regression_count += 1
        rows.append(
            {
                "candidate_id": candidate_id,
                "pass_rate_delta": pass_delta,
                "latency_relative_delta": latency_delta,
                "cost_relative_delta": cost_delta,
                "regressed": bool(reasons),
                "reasons": reasons,
            }
        )

    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "regression",
        "suite_id": base["suite_id"],
        "baseline_suite_version": base["suite_version"],
        "current_suite_version": now["suite_version"],
        "baseline_report_sha": baseline["report_sha"],
        "current_report_sha": current["report_sha"],
        "thresholds": thresholds.to_dict(),
        "shared_candidates": len(shared),
        "regression_count": regression_count,
        "passed": regression_count == 0,
        "rows": rows,
    }
    result["artifact_sha"] = _digest(result)
    return result


def build_failure_corpus(report: Mapping[str, Any], *, limit: int = MAX_FAILURES) -> dict[str, Any]:
    """Preserve failed attempts as a bounded, deterministic failure corpus."""

    payload = validate_report(report)
    if not isinstance(limit, int) or not 1 <= limit <= MAX_FAILURES:
        raise OpsValidationError(f"limit must be between 1 and {MAX_FAILURES}")
    failures: list[dict[str, Any]] = []
    for record in payload["records"]:
        item = _require_mapping(record, "record")
        if bool(item.get("passed")):
            continue
        failures.append(
            {
                "run_id": item.get("run_id"),
                "candidate_id": item.get("candidate_id"),
                "scenario_id": item.get("scenario_id"),
                "difficulty": item.get("difficulty"),
                "attempt": item.get("attempt"),
                "status": item.get("status"),
                "error": item.get("error"),
                "reason": item.get("reason"),
                "diff": item.get("diff"),
                "output_sha": item.get("output_sha"),
            }
        )
        if len(failures) >= limit:
            break
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "failure_corpus",
        "suite_id": payload["suite_id"],
        "suite_version": payload["suite_version"],
        "source_report_sha": report["report_sha"],
        "failure_count": len(failures),
        "truncated": sum(not bool(item.get("passed")) for item in payload["records"]) > len(failures),
        "failures": failures,
    }
    result["artifact_sha"] = _digest(result)
    return result


def jury_consensus(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate report rankings into a deterministic Borda-style jury.

    Every report is one bounded jury ballot. Missing candidates receive no
    points. Ties are broken by mean pass rate, lower mean cost, lower mean
    latency, then candidate id.
    """

    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)):
        raise OpsValidationError("reports must be an array")
    if not 1 <= len(reports) <= MAX_REPORTS:
        raise OpsValidationError(f"reports must contain 1 to {MAX_REPORTS} entries")
    validated = [validate_report(item) for item in reports]
    suite_ids = {item["suite_id"] for item in validated}
    if len(suite_ids) != 1:
        raise OpsValidationError("jury reports must use the same suite_id")

    ids = sorted({candidate_id for report in validated for candidate_id in report["ranking"]})
    aggregates: dict[str, dict[str, Any]] = {
        candidate_id: {"points": 0, "ballots": 0, "pass_rates": [], "costs": [], "latencies": []}
        for candidate_id in ids
    }
    ballots: list[dict[str, Any]] = []
    for raw, report in zip(reports, validated):
        ranking = list(report["ranking"])
        score_max = len(ranking)
        candidate_metrics = {item["candidate_id"]: item for item in report["candidates"]}
        for index, candidate_id in enumerate(ranking):
            aggregate = aggregates[candidate_id]
            aggregate["points"] += score_max - index
            aggregate["ballots"] += 1
            metric = candidate_metrics[candidate_id]
            aggregate["pass_rates"].append(float(metric["pass_rate"]))
            aggregate["costs"].append(float(metric["total_cost_microunits"]))
            aggregate["latencies"].append(float(metric["mean_latency_ms"]))
        ballots.append({"report_sha": raw["report_sha"], "suite_version": report["suite_version"], "ranking": ranking})

    rows: list[dict[str, Any]] = []
    for candidate_id in ids:
        aggregate = aggregates[candidate_id]
        ballots_count = aggregate["ballots"]
        rows.append(
            {
                "candidate_id": candidate_id,
                "points": aggregate["points"],
                "ballots": ballots_count,
                "mean_pass_rate": sum(aggregate["pass_rates"]) / ballots_count,
                "mean_cost_microunits": sum(aggregate["costs"]) / ballots_count,
                "mean_latency_ms": sum(aggregate["latencies"]) / ballots_count,
            }
        )
    rows.sort(
        key=lambda row: (
            -row["points"],
            -row["mean_pass_rate"],
            row["mean_cost_microunits"],
            row["mean_latency_ms"],
            row["candidate_id"],
        )
    )
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "jury_consensus",
        "suite_id": next(iter(suite_ids)),
        "ballot_count": len(ballots),
        "winner": rows[0]["candidate_id"],
        "ranking": [row["candidate_id"] for row in rows],
        "rows": rows,
        "ballots": ballots,
    }
    result["artifact_sha"] = _digest(result)
    return result


def dataset_manifest(suites: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a content-addressed manifest for versioned benchmark datasets."""

    entries: list[dict[str, Any]] = []
    for index, suite in enumerate(suites):
        if index >= MAX_DATASETS:
            raise OpsValidationError(f"dataset manifest exceeds {MAX_DATASETS} entries")
        item = _require_mapping(suite, f"suites[{index}]")
        suite_id = _require_text(item.get("suite_id"), f"suites[{index}].suite_id")
        version = _require_text(item.get("version"), f"suites[{index}].version")
        entries.append(
            {
                "suite_id": suite_id,
                "version": version,
                "schema_version": item.get("schema_version"),
                "suite_sha": _digest(dict(item)),
                "scenario_count": len(item.get("scenarios", [])) if isinstance(item.get("scenarios"), list) else None,
                "candidate_count": len(item.get("candidates", [])) if isinstance(item.get("candidates"), list) else None,
            }
        )
    if not entries:
        raise OpsValidationError("dataset manifest requires at least one suite")
    entries.sort(key=lambda item: (item["suite_id"], item["version"], item["suite_sha"]))
    keys = [(item["suite_id"], item["version"]) for item in entries]
    if len(keys) != len(set(keys)):
        raise OpsValidationError("dataset manifest contains duplicate suite_id/version pairs")
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "dataset_manifest",
        "datasets": entries,
    }
    result["artifact_sha"] = _digest(result)
    return result


def release_manifest(
    *,
    release_version: str,
    dataset: Mapping[str, Any],
    scorecards: Sequence[Mapping[str, Any]],
    regressions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Bind PromptOps evidence into one deterministic release gate artifact."""

    release_version = _require_text(release_version, "release_version")
    dataset = _require_mapping(dataset, "dataset")
    if dataset.get("kind") != "dataset_manifest" or not isinstance(dataset.get("artifact_sha"), str):
        raise OpsValidationError("dataset must be a dataset_manifest artifact")
    if not scorecards:
        raise OpsValidationError("release requires at least one scorecard")
    for artifact in [*scorecards, *regressions]:
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("artifact_sha"), str):
            raise OpsValidationError("release evidence must contain artifact_sha")
    failed = [item for item in regressions if item.get("passed") is False]
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "release_manifest",
        "release_version": release_version,
        "dataset_sha": dataset["artifact_sha"],
        "scorecard_shas": sorted(str(item["artifact_sha"]) for item in scorecards),
        "regression_shas": sorted(str(item["artifact_sha"]) for item in regressions),
        "regression_gate_passed": not failed,
        "failed_regression_count": len(failed),
    }
    result["artifact_sha"] = _digest(result)
    return result
