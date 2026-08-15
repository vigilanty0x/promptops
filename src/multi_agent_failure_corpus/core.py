from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any

PROJECT = "multi-agent-failure-corpus"
REQUIRED_FIELDS = ("scenario_id", "category", "reproduction", "expected_failure")
MAX_INPUT_BYTES = 65_536
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}")
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


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and "\x00" not in value


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


def build_corpus_entry(record: dict[str, Any]) -> dict[str, Any]:
    if set(record) != set(REQUIRED_FIELDS):
        raise ValueError("record contains fields outside the minimized allowlist")
    if not isinstance(record.get("scenario_id"), str) or not IDENTIFIER.fullmatch(record["scenario_id"]) or record.get("category") not in {"conflict", "timeout", "false-proof", "coordination"}:
        raise ValueError("scenario_id or category is invalid")
    reproduction = record.get("reproduction")
    if not isinstance(reproduction, list) or not 1 <= len(reproduction) <= 50 or any(not _text(step, 2000) for step in reproduction) or not _text(record.get("expected_failure"), 2000):
        raise ValueError("bounded reproduction and expected_failure are required")
    scenario_id, redactions = _redact(record["scenario_id"])
    steps = []
    for step in reproduction:
        cleaned, count = _redact(step)
        steps.append(cleaned)
        redactions += count
    expected, count = _redact(record["expected_failure"])
    redactions += count
    entry = {"scenario_id": scenario_id, "category": record["category"], "steps": steps, "expected_failure": expected}
    entry["content_sha256"] = sha256(_canonical(entry).encode()).hexdigest()
    entry["redactions"] = redactions
    entry["anonymization"] = "best-effort pattern redaction only; not an anonymity guarantee"
    return entry


def evaluate(record: Any) -> dict[str, Any]:
    artifact: Any = None
    try:
        if not isinstance(record, dict):
            raise ValueError("record must be a JSON object")
        if len(_canonical(record).encode()) > MAX_INPUT_BYTES:
            raise ValueError("record exceeds 65536 bytes")
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            status, reason = "blocked", "missing required fields: " + ", ".join(missing)
        else:
            artifact = build_corpus_entry(record)
            if artifact["redactions"]:
                status, reason = "failed", "sensitive-looking material was detected and removed; review sanitized output before retrying"
            else:
                status, reason = "passed", "allowlisted corpus entry contains no detected sensitive patterns"
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        status, reason = "failed", str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "corpus_entry": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt
