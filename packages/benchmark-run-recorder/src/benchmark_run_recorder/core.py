from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any

PROJECT = "benchmark-run-recorder"
REQUIRED_FIELDS = ("benchmark", "configuration", "duration_ms", "result", "artifacts")
MAX_INPUT_BYTES = 65_536
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


def evaluate(record: Any) -> dict[str, Any]:
    artifact: Any = None
    safe_record = None
    try:
        if not isinstance(record, dict):
            raise ValueError("record must be a JSON object")
        if len(_canonical(record).encode()) > MAX_INPUT_BYTES:
            raise ValueError("record exceeds 65536 bytes")
        safe_record = record
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            status, reason = "blocked", "missing required fields: " + ", ".join(missing)
        else:
            artifact = record_benchmark(record)
            status, reason = "passed", "bounded benchmark record created; measurements were not independently verified"
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        status, reason = "failed", str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": safe_record, "run_manifest": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt
