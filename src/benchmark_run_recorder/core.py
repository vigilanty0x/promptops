from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any

PROJECT = "benchmark-run-recorder"
REQUIRED_FIELDS = ["benchmark","configuration","duration_ms","result","artifacts"]

def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)

def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)

def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def record_benchmark(record: dict[str, Any]) -> dict[str, Any]:
    if not _text(record["benchmark"]) or not isinstance(record["configuration"], dict) or not record["configuration"]:
        raise ValueError("benchmark and configuration are required")
    if not _number(record["duration_ms"]) or record["duration_ms"] <= 0:
        raise ValueError("duration must be positive")
    if not isinstance(record["result"], dict) or not record["result"] or not _string_list(record["artifacts"]):
        raise ValueError("result and artifacts are required")
    config_digest = sha256(_canonical(record["configuration"]).encode()).hexdigest()
    return {"benchmark": record["benchmark"], "configuration_sha256": config_digest, "duration_ms": record["duration_ms"], "result": record["result"], "artifacts": record["artifacts"]}

def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    artifact: Any = None
    if missing:
        status = "blocked"
        reason = "missing required fields: " + ", ".join(missing)
    else:
        try:
            artifact = record_benchmark(record)
            status = "passed"
            reason = "record_benchmark completed"
        except (TypeError, ValueError, KeyError) as exc:
            status = "failed"
            reason = str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": record, "run_manifest": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt

