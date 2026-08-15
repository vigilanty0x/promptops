from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any

PROJECT = "multi-agent-failure-corpus"
REQUIRED_FIELDS = ["scenario_id","category","reproduction","expected_failure"]

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

def build_corpus_entry(record: dict[str, Any]) -> dict[str, Any]:
    if not _text(record["scenario_id"]) or record["category"] not in {"conflict", "timeout", "false-proof", "coordination"}:
        raise ValueError("scenario id or category is invalid")
    if not _string_list(record["reproduction"]) or not _text(record["expected_failure"]):
        raise ValueError("bounded reproduction and expected failure are required")
    if any(term in _canonical(record).casefold() for term in ("password", "private key", "api_key")):
        raise ValueError("sensitive material is not allowed")
    return {"scenario_id": record["scenario_id"], "category": record["category"], "steps": record["reproduction"], "expected_failure": record["expected_failure"], "content_sha256": sha256(_canonical(record).encode()).hexdigest()}

def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    artifact: Any = None
    if missing:
        status = "blocked"
        reason = "missing required fields: " + ", ".join(missing)
    else:
        try:
            artifact = build_corpus_entry(record)
            status = "passed"
            reason = "build_corpus_entry completed"
        except (TypeError, ValueError, KeyError) as exc:
            status = "failed"
            reason = str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": record, "corpus_entry": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt

