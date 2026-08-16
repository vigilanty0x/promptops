from __future__ import annotations

from hashlib import sha256
import json
from string import Formatter
import re
from typing import Any

PROJECT = "prompt-package-manager"
REQUIRED_FIELDS = ("name", "version", "prompt", "variables", "output_schema", "tests")
MAX_INPUT_BYTES = 131_072
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")
NAME = re.compile(r"[a-z][a-z0-9-]{0,99}")
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


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


def evaluate(record: Any) -> dict[str, Any]:
    artifact: Any = None
    safe_record = None
    try:
        if not isinstance(record, dict):
            raise ValueError("record must be a JSON object")
        if len(_canonical(record).encode()) > MAX_INPUT_BYTES:
            raise ValueError("record exceeds 131072 bytes")
        safe_record = record
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            status, reason = "blocked", "missing required fields: " + ", ".join(missing)
        else:
            artifact = build_prompt_package(record)
            status, reason = "passed", "deterministic local package tests passed; no installation or storage was performed"
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        status, reason = "failed", str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": safe_record, "package_manifest": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt
