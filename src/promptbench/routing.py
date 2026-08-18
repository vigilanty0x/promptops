"""Deterministic offline routing over verified PromptOps scorecards.

Routing never calls a provider and never invents candidate capabilities.  It
consumes one content-addressed scorecard, applies explicit bounded constraints
in scorecard rank order, and either selects an eligible candidate or abstains.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping, Sequence

from .ops import OPS_SCHEMA_VERSION, OpsValidationError, _digest

MAX_ROUTING_CANDIDATES = 256
MAX_FALLBACKS = 64
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _number(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
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


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpsValidationError(f"{field} must be a non-empty string")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OpsValidationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def validate_scorecard(scorecard: Mapping[str, Any]) -> dict[str, Any]:
    """Validate scorecard identity, shape, metrics, ranking and content hash."""

    if not isinstance(scorecard, Mapping):
        raise OpsValidationError("scorecard must be an object")
    signed = dict(scorecard)
    artifact_sha = _sha(signed.pop("artifact_sha", None), "artifact_sha")
    if _digest(signed) != artifact_sha:
        raise OpsValidationError("artifact_sha does not match scorecard content")
    if signed.get("schema_version") != OPS_SCHEMA_VERSION:
        raise OpsValidationError("unsupported scorecard schema_version")
    if signed.get("kind") != "scorecard":
        raise OpsValidationError("routing input must be a scorecard artifact")
    _text(signed.get("suite_id"), "suite_id")
    _text(signed.get("suite_version"), "suite_version")
    _sha(signed.get("source_report_sha"), "source_report_sha")
    winner = _text(signed.get("winner"), "winner")
    rows = signed.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROUTING_CANDIDATES:
        raise OpsValidationError(f"scorecard rows must contain 1 to {MAX_ROUTING_CANDIDATES} candidates")

    candidate_ids: list[str] = []
    ranks: list[int] = []
    normalized_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise OpsValidationError(f"rows[{index}] must be an object")
        rank = raw.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise OpsValidationError(f"rows[{index}].rank must be a positive integer")
        candidate_id = _text(raw.get("candidate_id"), f"rows[{index}].candidate_id")
        pass_rate = _number(raw.get("pass_rate"), f"rows[{index}].pass_rate", minimum=0.0, maximum=1.0)
        latency = _number(raw.get("mean_latency_ms"), f"rows[{index}].mean_latency_ms", minimum=0.0)
        cost = _number(raw.get("total_cost_microunits"), f"rows[{index}].total_cost_microunits", minimum=0.0)
        model = raw.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise OpsValidationError(f"rows[{index}].model must be null or a non-empty string")
        candidate_ids.append(candidate_id)
        ranks.append(rank)
        normalized_rows.append(
            {
                "rank": rank,
                "candidate_id": candidate_id,
                "model": model,
                "pass_rate": pass_rate,
                "mean_latency_ms": latency,
                "total_cost_microunits": cost,
            }
        )

    if len(candidate_ids) != len(set(candidate_ids)):
        raise OpsValidationError("scorecard candidate ids must be unique")
    if sorted(ranks) != list(range(1, len(rows) + 1)) or len(ranks) != len(set(ranks)):
        raise OpsValidationError("scorecard ranks must contain every rank exactly once")
    normalized_rows.sort(key=lambda row: row["rank"])
    if normalized_rows[0]["candidate_id"] != winner:
        raise OpsValidationError("scorecard winner must match rank 1")

    return {
        "schema_version": signed["schema_version"],
        "kind": signed["kind"],
        "suite_id": signed["suite_id"],
        "suite_version": signed["suite_version"],
        "source_report_sha": signed["source_report_sha"],
        "artifact_sha": artifact_sha,
        "winner": winner,
        "rows": normalized_rows,
    }


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Explicit constraints for one deterministic routing decision."""

    min_pass_rate: float = 0.0
    max_mean_latency_ms: float | None = None
    max_total_cost_microunits: float | None = None
    allowed_candidates: tuple[str, ...] | None = None
    fallback_count: int = 0

    def __post_init__(self) -> None:
        _number(self.min_pass_rate, "min_pass_rate", minimum=0.0, maximum=1.0)
        if self.max_mean_latency_ms is not None:
            _number(self.max_mean_latency_ms, "max_mean_latency_ms", minimum=0.0)
        if self.max_total_cost_microunits is not None:
            _number(self.max_total_cost_microunits, "max_total_cost_microunits", minimum=0.0)
        if isinstance(self.fallback_count, bool) or not isinstance(self.fallback_count, int) or not 0 <= self.fallback_count <= MAX_FALLBACKS:
            raise OpsValidationError(f"fallback_count must be between 0 and {MAX_FALLBACKS}")
        if self.allowed_candidates is not None:
            if not isinstance(self.allowed_candidates, tuple):
                raise OpsValidationError("allowed_candidates must be a tuple when provided")
            if not 1 <= len(self.allowed_candidates) <= MAX_ROUTING_CANDIDATES:
                raise OpsValidationError(f"allowed_candidates must contain 1 to {MAX_ROUTING_CANDIDATES} ids")
            normalized = tuple(_text(value, "allowed_candidates[]") for value in self.allowed_candidates)
            if len(normalized) != len(set(normalized)):
                raise OpsValidationError("allowed_candidates must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_pass_rate": float(self.min_pass_rate),
            "max_mean_latency_ms": None if self.max_mean_latency_ms is None else float(self.max_mean_latency_ms),
            "max_total_cost_microunits": None if self.max_total_cost_microunits is None else float(self.max_total_cost_microunits),
            "allowed_candidates": None if self.allowed_candidates is None else list(self.allowed_candidates),
            "fallback_count": self.fallback_count,
        }


def route_scorecard(scorecard: Mapping[str, Any], *, policy: RoutingPolicy | None = None) -> dict[str, Any]:
    """Select the highest-ranked eligible candidate or explicitly abstain."""

    card = validate_scorecard(scorecard)
    policy = policy or RoutingPolicy()
    if not isinstance(policy, RoutingPolicy):
        raise OpsValidationError("policy must be a RoutingPolicy")
    allowed = None if policy.allowed_candidates is None else set(policy.allowed_candidates)

    decisions: list[dict[str, Any]] = []
    eligible: list[str] = []
    for row in card["rows"]:
        reasons: list[str] = []
        candidate_id = row["candidate_id"]
        if allowed is not None and candidate_id not in allowed:
            reasons.append("not_allowed")
        if row["pass_rate"] < float(policy.min_pass_rate):
            reasons.append("pass_rate")
        if policy.max_mean_latency_ms is not None and row["mean_latency_ms"] > float(policy.max_mean_latency_ms):
            reasons.append("latency")
        if policy.max_total_cost_microunits is not None and row["total_cost_microunits"] > float(policy.max_total_cost_microunits):
            reasons.append("cost")
        is_eligible = not reasons
        if is_eligible:
            eligible.append(candidate_id)
        decisions.append(
            {
                "rank": row["rank"],
                "candidate_id": candidate_id,
                "eligible": is_eligible,
                "reasons": reasons,
                "pass_rate": row["pass_rate"],
                "mean_latency_ms": row["mean_latency_ms"],
                "total_cost_microunits": row["total_cost_microunits"],
            }
        )

    selected = eligible[0] if eligible else None
    fallbacks = eligible[1 : 1 + policy.fallback_count] if selected is not None else []
    result: dict[str, Any] = {
        "schema_version": OPS_SCHEMA_VERSION,
        "kind": "route_decision",
        "suite_id": card["suite_id"],
        "suite_version": card["suite_version"],
        "source_scorecard_sha": card["artifact_sha"],
        "policy": policy.to_dict(),
        "decision": "route" if selected is not None else "abstain",
        "selected_candidate": selected,
        "fallback_candidates": fallbacks,
        "eligible_count": len(eligible),
        "considered_count": len(decisions),
        "candidates": decisions,
    }
    result["artifact_sha"] = _digest(result)
    return result
