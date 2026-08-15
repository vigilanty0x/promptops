"""Bounded versioned schemas for datasets, replay samples, runs, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any


MAX_SCENARIOS = 200
MAX_CANDIDATES = 20
MAX_REPEATS = 20
MAX_TEXT_BYTES = 100_000
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


class ValidationError(ValueError):
    """Raised when a suite violates its reproducibility contract."""


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"


def _text(value: Any, field: str, limit: int = MAX_TEXT_BYTES, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if not value.strip() and not empty:
        raise ValidationError(f"{field} must not be empty")
    if len(value.encode("utf-8")) > limit:
        raise ValidationError(f"{field} exceeds {limit} bytes")
    return value


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field, 128)
    if not IDENTIFIER.fullmatch(value):
        raise ValidationError(f"{field} must use lowercase letters, digits, dots, underscores, or hyphens")
    return value


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Limits:
    repeats: int = 3
    max_output_chars: int = 8_000

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Limits":
        data = data or {}
        if not isinstance(data, dict):
            raise ValidationError("limits must be an object")
        repeats = data.get("repeats", 3)
        maximum = data.get("max_output_chars", 8_000)
        if not isinstance(repeats, int) or not 1 <= repeats <= MAX_REPEATS:
            raise ValidationError(f"repeats must be between 1 and {MAX_REPEATS}")
        if not isinstance(maximum, int) or not 1 <= maximum <= MAX_TEXT_BYTES:
            raise ValidationError(f"max_output_chars must be between 1 and {MAX_TEXT_BYTES}")
        return cls(repeats, maximum)

    def to_dict(self) -> dict[str, int]:
        return {"repeats": self.repeats, "max_output_chars": self.max_output_chars}


@dataclass(frozen=True, slots=True)
class JudgeSpec:
    kind: str
    case_sensitive: bool = True
    normalize_whitespace: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JudgeSpec":
        if not isinstance(data, dict):
            raise ValidationError("judge must be an object")
        kind = data.get("type")
        if kind not in {"exact", "contains", "json_equal"}:
            raise ValidationError("judge type must be exact, contains, or json_equal")
        case_sensitive = data.get("case_sensitive", True)
        normalize = data.get("normalize_whitespace", True)
        if not isinstance(case_sensitive, bool) or not isinstance(normalize, bool):
            raise ValidationError("judge options must be booleans")
        return cls(kind, case_sensitive, normalize)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "case_sensitive": self.case_sensitive,
            "normalize_whitespace": self.normalize_whitespace,
        }


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    difficulty: Difficulty
    input_text: str
    expected: Any
    judge: JudgeSpec

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        if not isinstance(data, dict):
            raise ValidationError("each scenario must be an object")
        try:
            difficulty = Difficulty(data.get("difficulty"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("scenario difficulty is invalid") from exc
        judge = JudgeSpec.from_dict(data.get("judge"))
        expected = data.get("expected")
        if judge.kind in {"exact", "contains"}:
            expected = _text(expected, "expected", MAX_TEXT_BYTES, empty=True)
        elif not isinstance(expected, (dict, list, str, int, float, bool, type(None))):
            raise ValidationError("json_equal expected value is not JSON-compatible")
        return cls(
            scenario_id=_identifier(data.get("id"), "scenario id"),
            difficulty=difficulty,
            input_text=_text(data.get("input"), "scenario input", 20_000),
            expected=expected,
            judge=judge,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.scenario_id,
            "difficulty": self.difficulty.value,
            "input": self.input_text,
            "expected": self.expected,
            "judge": self.judge.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    model: str
    prompt_template: str
    input_price_microunits_per_1k: int = 0
    output_price_microunits_per_1k: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        if not isinstance(data, dict):
            raise ValidationError("each candidate must be an object")
        template = _text(data.get("prompt_template"), "prompt_template", 20_000)
        if template.count("{input}") != 1:
            raise ValidationError("prompt_template must contain {input} exactly once")
        input_price = data.get("input_price_microunits_per_1k", 0)
        output_price = data.get("output_price_microunits_per_1k", 0)
        for name, value in (("input price", input_price), ("output price", output_price)):
            if not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
                raise ValidationError(f"{name} must be a bounded non-negative integer")
        return cls(
            candidate_id=_identifier(data.get("id"), "candidate id"),
            model=_text(data.get("model"), "model", 256),
            prompt_template=template,
            input_price_microunits_per_1k=input_price,
            output_price_microunits_per_1k=output_price,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "model": self.model,
            "prompt_template": self.prompt_template,
            "input_price_microunits_per_1k": self.input_price_microunits_per_1k,
            "output_price_microunits_per_1k": self.output_price_microunits_per_1k,
        }


@dataclass(frozen=True, slots=True)
class ReplaySample:
    output: str | None
    error: str | None
    latency_ms: float
    input_tokens: int
    output_tokens: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplaySample":
        if not isinstance(data, dict):
            raise ValidationError("each replay sample must be an object")
        output = data.get("output")
        error = data.get("error")
        if (output is None) == (error is None):
            raise ValidationError("replay sample must contain exactly one of output or error")
        if output is not None:
            output = _text(output, "sample output", MAX_TEXT_BYTES, empty=True)
        if error is not None:
            error = _text(error, "sample error", 1_000)
        latency = data.get("latency_ms", 0)
        if not isinstance(latency, (int, float)) or not 0 <= latency <= 600_000:
            raise ValidationError("latency_ms must be between 0 and 600000")
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if not isinstance(value, int) or not 0 <= value <= 1_000_000:
                raise ValidationError(f"{name} must be a bounded non-negative integer")
        return cls(output, error, float(latency), input_tokens, output_tokens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    schema_version: str
    suite_id: str
    version: str
    limits: Limits
    scenarios: tuple[Scenario, ...]
    candidates: tuple[Candidate, ...]
    replay: dict[str, dict[str, tuple[ReplaySample, ...]]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkSuite":
        if not isinstance(data, dict) or data.get("schema_version") != "1.0":
            raise ValidationError("suite schema_version must be 1.0")
        version = _text(data.get("version"), "suite version", 64)
        if not SEMVER.fullmatch(version):
            raise ValidationError("suite version must use semantic versioning")
        raw_scenarios = data.get("scenarios")
        raw_candidates = data.get("candidates")
        if not isinstance(raw_scenarios, list) or not 1 <= len(raw_scenarios) <= MAX_SCENARIOS:
            raise ValidationError(f"scenarios must contain 1 to {MAX_SCENARIOS} entries")
        if not isinstance(raw_candidates, list) or not 1 <= len(raw_candidates) <= MAX_CANDIDATES:
            raise ValidationError(f"candidates must contain 1 to {MAX_CANDIDATES} entries")
        scenarios = tuple(Scenario.from_dict(item) for item in raw_scenarios)
        candidates = tuple(Candidate.from_dict(item) for item in raw_candidates)
        for label, values in (("scenario", [x.scenario_id for x in scenarios]), ("candidate", [x.candidate_id for x in candidates])):
            if len(values) != len(set(values)):
                raise ValidationError(f"{label} ids must be unique")
        limits = Limits.from_dict(data.get("limits"))
        raw_replay = data.get("replay")
        if not isinstance(raw_replay, dict):
            raise ValidationError("replay must be an object")
        replay: dict[str, dict[str, tuple[ReplaySample, ...]]] = {}
        expected_candidates = {item.candidate_id for item in candidates}
        expected_scenarios = {item.scenario_id for item in scenarios}
        if set(raw_replay) != expected_candidates:
            raise ValidationError("replay candidate keys must exactly match candidates")
        for candidate_id, scenario_map in raw_replay.items():
            if not isinstance(scenario_map, dict) or set(scenario_map) != expected_scenarios:
                raise ValidationError("replay scenario keys must exactly match scenarios")
            replay[candidate_id] = {}
            for scenario_id, samples in scenario_map.items():
                if not isinstance(samples, list) or len(samples) != limits.repeats:
                    raise ValidationError("each replay series must exactly match limits.repeats")
                replay[candidate_id][scenario_id] = tuple(ReplaySample.from_dict(item) for item in samples)
        return cls(
            schema_version="1.0",
            suite_id=_identifier(data.get("suite_id"), "suite_id"),
            version=version,
            limits=limits,
            scenarios=scenarios,
            candidates=candidates,
            replay=replay,
        )

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "version": self.version,
            "limits": self.limits.to_dict(),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "candidates": [item.to_dict() for item in self.candidates],
            "replay": {
                candidate: {
                    scenario: [sample.to_dict() for sample in samples]
                    for scenario, samples in sorted(scenario_map.items())
                }
                for candidate, scenario_map in sorted(self.replay.items())
            },
        }

    @property
    def suite_sha(self) -> str:
        return digest(self.unsigned_dict())


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    candidate_id: str
    model: str
    scenario_id: str
    difficulty: Difficulty
    attempt: int
    prompt_sha: str
    output: str | None
    output_sha: str | None
    status: str
    error: str | None
    passed: bool
    score: float
    reason: str
    diff: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_microunits: int

    def to_dict(self) -> dict[str, Any]:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__}
        data["difficulty"] = self.difficulty.value
        return data


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    candidate_id: str
    model: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    pass_at_1: float
    score_variance: float
    mean_latency_ms: float
    p95_latency_ms: float
    total_cost_microunits: int
    mean_tokens_per_run: float
    recovery_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    schema_version: str
    tool_version: str
    suite_id: str
    suite_version: str
    suite_sha: str
    records: tuple[RunRecord, ...]
    candidates: tuple[CandidateMetrics, ...]
    ranking: tuple[str, ...]
    methodology: tuple[str, ...]
    limitations: tuple[str, ...]
    report_sha: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "suite_sha": self.suite_sha,
            "records": [record.to_dict() for record in self.records],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "ranking": list(self.ranking),
            "methodology": list(self.methodology),
            "limitations": list(self.limitations),
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data["report_sha"] = self.report_sha
        return data
