"""Bounded CLI for validation, replay, comparison, probes, and evidence output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .harness import BenchmarkHarness
from .models import BenchmarkSuite, ValidationError
from .probes import functional_probe, inventory, liveness_probe, readiness_probe
from .reporting import verify_report, write_report


MAX_SUITE_BYTES = 10_000_000


def _emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _read_json(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(f"suite does not exist: {path}")
    if target.stat().st_size > MAX_SUITE_BYTES:
        raise ValidationError(f"suite exceeds {MAX_SUITE_BYTES} bytes")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON suite: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("suite must be a JSON object")
    return data


def _suite(path: str) -> BenchmarkSuite:
    return BenchmarkSuite.from_dict(_read_json(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptbench",
        description="Compare prompt/model replay candidates on versioned datasets.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a suite without running it")
    validate.add_argument("--suite", required=True)

    run = commands.add_parser("run", help="Run the reproducible replay harness")
    run.add_argument("--suite", required=True)
    run.add_argument("--output")
    run.add_argument("--minimum-pass-rate", type=float)

    verify = commands.add_parser("verify", help="Verify a report's embedded SHA")
    verify.add_argument("--report", required=True)

    probe = commands.add_parser("probe", help="Run a separated operational probe")
    probe.add_argument("--level", choices=("liveness", "readiness", "functional"), required=True)

    commands.add_parser("inventory", help="Print the canonical harness inventory")

    demo = commands.add_parser("demo", help="Run a fully synthetic comparison")
    demo.add_argument("--workspace", required=True)
    return parser


def _demo_suite_dict() -> dict[str, Any]:
    def samples(first: str, second: str, base: int):
        return [
            {"output": first, "latency_ms": base, "input_tokens": 7, "output_tokens": 2},
            {"output": second, "latency_ms": base + 2, "input_tokens": 7, "output_tokens": 2},
            {"output": second, "latency_ms": base + 1, "input_tokens": 7, "output_tokens": 2},
        ]
    return {
        "schema_version": "1.0",
        "suite_id": "offline-demo",
        "version": "1.0.0",
        "limits": {"repeats": 3, "max_output_chars": 1_000},
        "scenarios": [
            {
                "id": "capital",
                "difficulty": "easy",
                "input": "What is the capital of France?",
                "expected": "Paris",
                "judge": {"type": "exact", "case_sensitive": False, "normalize_whitespace": True},
            },
            {
                "id": "structured",
                "difficulty": "medium",
                "input": "Return JSON with ok=true.",
                "expected": {"ok": True},
                "judge": {"type": "json_equal"},
            },
        ],
        "candidates": [
            {
                "id": "concise",
                "model": "replay-v1",
                "prompt_template": "Answer concisely: {input}",
                "input_price_microunits_per_1k": 2_000,
                "output_price_microunits_per_1k": 4_000,
            },
            {
                "id": "verbose",
                "model": "replay-v2",
                "prompt_template": "Explain and answer: {input}",
                "input_price_microunits_per_1k": 3_000,
                "output_price_microunits_per_1k": 6_000,
            },
        ],
        "replay": {
            "concise": {
                "capital": samples("Paris", "Paris", 12),
                "structured": samples('{"ok": false}', '{"ok": true}', 15),
            },
            "verbose": {
                "capital": samples("The answer is Paris.", "The answer is Paris.", 20),
                "structured": samples('{"ok": true}', '{"ok": true}', 24),
            },
        },
    }


def _run_demo(workspace: str) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    suite_path = root / "suite.json"
    report_path = root / "report.json"
    suite_path.write_text(json.dumps(_demo_suite_dict(), indent=2) + "\n", encoding="utf-8")
    suite = BenchmarkSuite.from_dict(_read_json(str(suite_path)))
    report = BenchmarkHarness(suite).run()
    receipt = write_report(report, report_path)
    return {
        "suite_sha": suite.suite_sha,
        "report_sha": report.report_sha,
        "ranking": list(report.ranking),
        "metrics": [item.to_dict() for item in report.candidates],
        "failed_runs_preserved": sum(not item.passed for item in report.records),
        "report_receipt": receipt,
        "report_verified": verify_report(report_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            suite = _suite(args.suite)
            _emit({
                "valid": True,
                "suite_id": suite.suite_id,
                "version": suite.version,
                "suite_sha": suite.suite_sha,
                "scenarios": len(suite.scenarios),
                "candidates": len(suite.candidates),
                "repeats": suite.limits.repeats,
            })
            return 0
        if args.command == "run":
            if args.minimum_pass_rate is not None and not 0 <= args.minimum_pass_rate <= 1:
                raise ValidationError("minimum-pass-rate must be between 0 and 1")
            report = BenchmarkHarness(_suite(args.suite)).run()
            payload: dict[str, Any] = {"report": report.to_dict()}
            if args.output:
                payload["receipt"] = write_report(report, args.output)
            _emit(payload)
            if args.minimum_pass_rate is not None:
                best = max(item.pass_rate for item in report.candidates)
                return 3 if best < args.minimum_pass_rate else 0
            return 0
        if args.command == "verify":
            verified = verify_report(args.report)
            _emit({"report": str(Path(args.report).resolve()), "verified": verified})
            return 0 if verified else 4
        if args.command == "probe":
            result = {
                "liveness": liveness_probe,
                "readiness": readiness_probe,
                "functional": functional_probe,
            }[args.level]()
            _emit(result)
            return 0 if result["status"] in {"alive", "ready", "proven"} else 5
        if args.command == "inventory":
            _emit(inventory())
            return 0
        if args.command == "demo":
            _emit(_run_demo(args.workspace))
            return 0
        raise AssertionError("unreachable command")
    except (ValidationError, OSError) as exc:
        _emit({"error": str(exc)[:1_000], "type": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
