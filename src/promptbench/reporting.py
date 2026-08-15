"""Atomic report output and content-addressed verification."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .models import BenchmarkReport, ValidationError, digest


def write_report(report: BenchmarkReport, path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if target.exists() and not target.is_file():
        raise ValidationError("report output exists and is not a regular file")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", delete=False) as stream:
        staged = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, target)
    verified = verify_report(target)
    if not verified:
        raise ValidationError("written report failed content verification")
    return {"path": str(target), "report_sha": report.report_sha, "verified": True}


def verify_report(path: str | Path) -> bool:
    target = Path(path)
    if not target.is_file() or target.stat().st_size > 20_000_000:
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get("report_sha"), str):
        return False
    expected = data.pop("report_sha")
    return digest(data) == expected
