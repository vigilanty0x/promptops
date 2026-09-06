"""Local bundle primitives ported from the preserved Apache-2.0 sources.

No source package is imported at runtime. Bounds and binding are applied by
bundles.py. Primitive semantics are kept for true source parity tests.
"""
from __future__ import annotations
from hashlib import sha256
import json, math, re
from string import Formatter
from typing import Any

SHA256 = re.compile(r"[0-9a-f]{64}")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _text(value: Any, limit: int = 300) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _metric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(value) <= 1e15


def record_benchmark(record: dict[str, Any]) -> dict[str, Any]:
    configuration = record.get("configuration")
    result = record.get("result")
    artifacts = record.get("artifacts")
    if not _text(record.get("benchmark")) or not isinstance(configuration, dict) or not configuration or len(configuration) > 100:
        raise ValueError("benchmark and a bounded configuration object are required")
    duration = record.get("duration_ms")
    if not _metric(duration) or not 0 < duration <= 86_400_000:
        raise ValueError("duration_ms must be finite and between 0 and 86400000")
    if not isinstance(result, dict) or not 1 <= len(result) <= 100 or any(not _text(key, 100) or not _metric(value) for key, value in result.items()):
        raise ValueError("result must contain 1-100 named finite numeric metrics")
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 100:
        raise ValueError("artifacts must contain 1-100 digest records")
    normalized_artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"} or not _text(artifact["path"], 500) or not isinstance(artifact["sha256"], str) or not SHA256.fullmatch(artifact["sha256"]):
            raise ValueError("each artifact requires a bounded path and lowercase SHA-256")
        normalized_artifacts.append(dict(artifact))
    return {
        "kind": "benchmark-record",
        "verification": "not-performed",
        "benchmark": record["benchmark"],
        "configuration_sha256": sha256(_canonical(configuration).encode()).hexdigest(),
        "duration_ms": duration,
        "metrics": result,
        "artifacts": normalized_artifacts,
    }


REQUIRED_FIELDS = ("name", "version", "prompt", "variables", "output_schema", "tests")


SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


NAME = re.compile(r"[a-z][a-z0-9-]{0,99}")


VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def _render(prompt: str, variables: dict[str, str], declared: set[str]) -> str:
    parts: list[str] = []
    try:
        parsed = list(Formatter().parse(prompt))
    except ValueError as exc:
        raise ValueError("prompt contains malformed braces") from exc
    found: set[str] = set()
    for literal, field, format_spec, conversion in parsed:
        parts.append(literal)
        if field is not None:
            if not VARIABLE.fullmatch(field) or format_spec or conversion or field not in declared:
                raise ValueError("prompt fields must be simple declared variables without formatting")
            found.add(field)
            parts.append(variables[field])
    if found != declared:
        raise ValueError("declared variables must match prompt placeholders")
    rendered = "".join(parts)
    if len(rendered) > 32_768:
        raise ValueError("rendered prompt exceeds 32768 characters")
    return rendered


def _schema_valid(value: Any, schema: dict[str, Any]) -> bool:
    kind = schema.get("type")
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        return isinstance(value, dict) and isinstance(required, list) and all(isinstance(key, str) and key in value for key in required) and isinstance(properties, dict) and all(key not in value or isinstance(child, dict) and _schema_valid(value[key], child) for key, child in properties.items())
    return False


def build_prompt_package(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record.get("name"), str) or not NAME.fullmatch(record["name"]) or not isinstance(record.get("version"), str) or not SEMVER.fullmatch(record["version"]):
        raise ValueError("name must be a lowercase package name and version must be strict SemVer")
    prompt = record.get("prompt")
    variables = record.get("variables")
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 16_384 or "\x00" in prompt:
        raise ValueError("prompt must contain 1-16384 characters")
    if not isinstance(variables, list) or len(variables) > 64 or len(variables) != len(set(variables)) or any(not isinstance(value, str) or not VARIABLE.fullmatch(value) for value in variables):
        raise ValueError("variables must contain at most 64 unique identifiers")
    schema = record.get("output_schema")
    if not isinstance(schema, dict) or not schema or len(_canonical(schema).encode()) > 16_384 or schema.get("type") not in {"string", "integer", "number", "boolean", "array", "object"}:
        raise ValueError("output_schema must be a bounded supported deterministic schema")
    tests = record.get("tests")
    if not isinstance(tests, list) or not 1 <= len(tests) <= 100:
        raise ValueError("tests must contain 1-100 deterministic cases")
    declared = set(variables)
    results = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict) or set(test) != {"variables", "expected_prompt", "output"} or not isinstance(test["variables"], dict) or set(test["variables"]) != declared or any(not isinstance(value, str) or len(value) > 4096 or "\x00" in value for value in test["variables"].values()) or not isinstance(test["expected_prompt"], str):
            raise ValueError("each test requires exact variables, expected_prompt, and output fields")
        rendered = _render(prompt, test["variables"], declared)
        if rendered != test["expected_prompt"]:
            raise ValueError(f"test {index} rendered prompt does not match expected_prompt")
        if not _schema_valid(test["output"], schema):
            raise ValueError(f"test {index} output does not satisfy output_schema")
        results.append({"index": index, "passed": True, "rendered_sha256": sha256(rendered.encode()).hexdigest()})
    payload = {key: record[key] for key in REQUIRED_FIELDS}
    return {"name": record["name"], "version": record["version"], "digest": sha256(_canonical(payload).encode()).hexdigest(), "tests": results, "test_count": len(results), "installed": False, "stored": False}


PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", re.I), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{8,}\b", re.I), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{8,}\b"), "[REDACTED_STRIPE_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*"), "[REDACTED_BEARER]"),
    (re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?key|secret|token|credential|authorization)\b\s*[:=]\s*[^\s,;]{8,}"), "[REDACTED_SECRET]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
)


ENTROPY_TOKEN = re.compile(r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{24,}(?![A-Za-z0-9_+/=-])")


def _redact(value: str) -> tuple[str, int]:
    redactions = 0
    for pattern, replacement in PATTERNS:
        value, count = pattern.subn(replacement, value)
        redactions += count
    def redact_entropy(match: re.Match[str]) -> str:
        nonlocal redactions
        token = match.group(0)
        counts = {char: token.count(char) for char in set(token)}
        entropy = -sum((count / len(token)) * math.log2(count / len(token)) for count in counts.values())
        classes = sum((any(char.islower() for char in token), any(char.isupper() for char in token), any(char.isdigit() for char in token), any(char in "_+/=-" for char in token)))
        if entropy >= 3.5 and classes >= 2:
            redactions += 1
            return "[REDACTED_HIGH_ENTROPY_TOKEN]"
        return token
    value = ENTROPY_TOKEN.sub(redact_entropy, value)
    return value, redactions
