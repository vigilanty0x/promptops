"""Operational probes and a functional counter-proof."""

from __future__ import annotations

from typing import Any

from . import __version__
from .harness import BenchmarkHarness
from .models import BenchmarkSuite


def inventory() -> dict[str, Any]:
    return {
        "tool": "promptbench",
        "version": __version__,
        "runtime_dependencies": [],
        "producer": "versioned-replay",
        "judges": ["exact", "contains", "json_equal"],
        "metrics": [
            "pass_rate", "pass_at_1", "score_variance", "mean_latency_ms",
            "p95_latency_ms", "total_cost_microunits", "mean_tokens_per_run",
            "recovery_rate",
        ],
        "schema_versions": {"suite": "1.0", "report": "1.0"},
    }


def liveness_probe() -> dict[str, Any]:
    return {"probe": "liveness", "status": "alive", "version": __version__}


def readiness_probe() -> dict[str, Any]:
    current = inventory()
    ready = current["producer"] == "versioned-replay" and len(current["judges"]) == 3
    return {"probe": "readiness", "status": "ready" if ready else "blocked", "inventory": current}


def counter_proof_suite() -> BenchmarkSuite:
    samples = lambda output: [
        {"output": output, "latency_ms": 10, "input_tokens": 4, "output_tokens": 1},
        {"output": output, "latency_ms": 11, "input_tokens": 4, "output_tokens": 1},
    ]
    return BenchmarkSuite.from_dict({
        "schema_version": "1.0",
        "suite_id": "functional-counter-proof",
        "version": "1.0.0",
        "limits": {"repeats": 2, "max_output_chars": 100},
        "scenarios": [{
            "id": "known-answer",
            "difficulty": "easy",
            "input": "Return the word blue.",
            "expected": "blue",
            "judge": {"type": "exact", "case_sensitive": False, "normalize_whitespace": True}
        }],
        "candidates": [
            {"id": "control", "model": "replay-control", "prompt_template": "{input}"},
            {"id": "counter-example", "model": "replay-counter", "prompt_template": "{input}"},
        ],
        "replay": {
            "control": {"known-answer": samples("blue")},
            "counter-example": {"known-answer": samples("green")},
        },
    })


def functional_probe() -> dict[str, Any]:
    report = BenchmarkHarness(counter_proof_suite()).run()
    by_id = {item.candidate_id: item for item in report.candidates}
    proven = (
        by_id["control"].pass_rate == 1.0
        and by_id["counter-example"].pass_rate == 0.0
        and report.ranking[0] == "control"
        and any(not record.passed for record in report.records)
    )
    return {
        "probe": "functional",
        "status": "proven" if proven else "blocked",
        "control_pass_rate": by_id["control"].pass_rate,
        "counter_example_pass_rate": by_id["counter-example"].pass_rate,
        "failures_preserved": sum(not item.passed for item in report.records),
        "report_sha": report.report_sha,
    }
