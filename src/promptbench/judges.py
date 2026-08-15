"""Explicit judges that are separate from response producers."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import json
from typing import Any

from .models import JudgeSpec


@dataclass(frozen=True, slots=True)
class JudgeResult:
    passed: bool
    score: float
    reason: str
    diff: str


def _normalize(value: str, spec: JudgeSpec) -> str:
    if spec.normalize_whitespace:
        value = " ".join(value.split())
    if not spec.case_sensitive:
        value = value.casefold()
    return value


def _diff(expected: Any, actual: Any) -> str:
    expected_text = json.dumps(expected, sort_keys=True, indent=2) if not isinstance(expected, str) else expected
    actual_text = json.dumps(actual, sort_keys=True, indent=2) if not isinstance(actual, str) else actual
    lines = list(difflib.unified_diff(
        expected_text.splitlines(), actual_text.splitlines(),
        fromfile="expected", tofile="actual", lineterm="",
    ))[:80]
    return "\n".join(lines)[:4_000]


def judge(spec: JudgeSpec, expected: Any, actual: str) -> JudgeResult:
    if spec.kind == "exact":
        expected_norm = _normalize(str(expected), spec)
        actual_norm = _normalize(actual, spec)
        passed = actual_norm == expected_norm
        return JudgeResult(passed, 1.0 if passed else 0.0, "exact match" if passed else "exact mismatch", "" if passed else _diff(expected_norm, actual_norm))
    if spec.kind == "contains":
        expected_norm = _normalize(str(expected), spec)
        actual_norm = _normalize(actual, spec)
        passed = expected_norm in actual_norm
        return JudgeResult(passed, 1.0 if passed else 0.0, "required text present" if passed else "required text missing", "" if passed else _diff(expected_norm, actual_norm))
    if spec.kind == "json_equal":
        try:
            parsed = json.loads(actual)
        except json.JSONDecodeError as exc:
            return JudgeResult(False, 0.0, f"invalid JSON: {exc.msg}", _diff(expected, actual))
        passed = parsed == expected
        return JudgeResult(passed, 1.0 if passed else 0.0, "JSON equal" if passed else "JSON mismatch", "" if passed else _diff(expected, parsed))
    raise AssertionError("validated judge kind is unreachable")
