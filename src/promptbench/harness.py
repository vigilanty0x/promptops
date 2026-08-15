"""Isolated harness that preserves every success, failure, cost, latency, and diff."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import math
import statistics

from . import __version__
from .judges import judge
from .models import (
    BenchmarkReport,
    BenchmarkSuite,
    Candidate,
    CandidateMetrics,
    RunRecord,
    digest,
)
from .runner import Producer, ReplayProducer


def _cost(candidate: Candidate, input_tokens: int, output_tokens: int) -> int:
    raw = (
        input_tokens * candidate.input_price_microunits_per_1k
        + output_tokens * candidate.output_price_microunits_per_1k
    ) / 1_000
    return int(round(raw))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


class BenchmarkHarness:
    def __init__(self, suite: BenchmarkSuite, producer: Producer | None = None) -> None:
        self.suite = suite
        self.producer = producer or ReplayProducer(suite)

    def run(self) -> BenchmarkReport:
        records: list[RunRecord] = []
        for candidate in self.suite.candidates:
            for scenario in self.suite.scenarios:
                prompt = candidate.prompt_template.replace("{input}", scenario.input_text)
                prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                for attempt in range(1, self.suite.limits.repeats + 1):
                    run_id = f"{candidate.candidate_id}:{scenario.scenario_id}:{attempt}"
                    try:
                        sample = self.producer.generate(candidate, scenario, attempt, prompt)
                        cost = _cost(candidate, sample.input_tokens, sample.output_tokens)
                        if sample.error is not None:
                            records.append(RunRecord(
                                run_id, candidate.candidate_id, candidate.model, scenario.scenario_id,
                                scenario.difficulty, attempt, prompt_sha, None, None, "error", sample.error,
                                False, 0.0, "producer error", "", sample.latency_ms,
                                sample.input_tokens, sample.output_tokens, cost,
                            ))
                            continue
                        assert sample.output is not None
                        if len(sample.output) > self.suite.limits.max_output_chars:
                            records.append(RunRecord(
                                run_id, candidate.candidate_id, candidate.model, scenario.scenario_id,
                                scenario.difficulty, attempt, prompt_sha, None,
                                hashlib.sha256(sample.output.encode("utf-8")).hexdigest(),
                                "error", "output_limit_exceeded", False, 0.0,
                                "output exceeded the shared limit", "", sample.latency_ms,
                                sample.input_tokens, sample.output_tokens, cost,
                            ))
                            continue
                        result = judge(scenario.judge, scenario.expected, sample.output)
                        records.append(RunRecord(
                            run_id, candidate.candidate_id, candidate.model, scenario.scenario_id,
                            scenario.difficulty, attempt, prompt_sha, sample.output,
                            hashlib.sha256(sample.output.encode("utf-8")).hexdigest(),
                            "success", None, result.passed, result.score, result.reason, result.diff,
                            sample.latency_ms, sample.input_tokens, sample.output_tokens, cost,
                        ))
                    except Exception as exc:  # Producer boundary: keep the failure in the report.
                        records.append(RunRecord(
                            run_id, candidate.candidate_id, candidate.model, scenario.scenario_id,
                            scenario.difficulty, attempt, prompt_sha, None, None, "error",
                            f"{type(exc).__name__}: {exc}"[:1_000], False, 0.0,
                            "producer exception", "", 0.0, 0, 0, 0,
                        ))

        metrics = tuple(self._metrics(candidate, records) for candidate in self.suite.candidates)
        ranking = tuple(item.candidate_id for item in sorted(
            metrics,
            key=lambda item: (-item.pass_rate, item.total_cost_microunits, item.mean_latency_ms, item.candidate_id),
        ))
        report = BenchmarkReport(
            schema_version="1.0",
            tool_version=__version__,
            suite_id=self.suite.suite_id,
            suite_version=self.suite.version,
            suite_sha=self.suite.suite_sha,
            records=tuple(records),
            candidates=metrics,
            ranking=ranking,
            methodology=(
                "Every candidate receives the same versioned scenarios, order, repeat count, and output limit.",
                "Recorded replay samples remove network, wall-clock, cache, and provider-account variance.",
                "Judges are explicit deterministic rules separated from response producers.",
                "Ranking uses pass rate, then total cost, mean latency, and candidate id.",
            ),
            limitations=(
                "Replay results describe the recorded samples, not current hosted-model behavior.",
                "Exact deterministic judges can miss semantic quality and can reward benchmark-specific wording.",
                "Token and price fields are supplied evidence and are not independently metered.",
                "A benchmark supports human evaluation but cannot establish universal model quality.",
            ),
            report_sha="",
        )
        return replace(report, report_sha=digest(report.unsigned_dict()))

    def _metrics(self, candidate: Candidate, records: list[RunRecord]) -> CandidateMetrics:
        chosen = [item for item in records if item.candidate_id == candidate.candidate_id]
        passed = sum(item.passed for item in chosen)
        first = [item for item in chosen if item.attempt == 1]
        recoverable = 0
        recovered = 0
        for first_record in first:
            if not first_record.passed:
                recoverable += 1
                if any(
                    item.scenario_id == first_record.scenario_id and item.attempt > 1 and item.passed
                    for item in chosen
                ):
                    recovered += 1
        scores = [item.score for item in chosen]
        latencies = [item.latency_ms for item in chosen]
        tokens = [item.input_tokens + item.output_tokens for item in chosen]
        total = len(chosen)
        return CandidateMetrics(
            candidate_id=candidate.candidate_id,
            model=candidate.model,
            total_runs=total,
            passed_runs=passed,
            failed_runs=total - passed,
            pass_rate=round(passed / total, 6) if total else 0.0,
            pass_at_1=round(sum(item.passed for item in first) / len(first), 6) if first else 0.0,
            score_variance=round(statistics.pvariance(scores), 6) if len(scores) > 1 else 0.0,
            mean_latency_ms=round(statistics.fmean(latencies), 3) if latencies else 0.0,
            p95_latency_ms=_percentile(latencies, 0.95),
            total_cost_microunits=sum(item.cost_microunits for item in chosen),
            mean_tokens_per_run=round(statistics.fmean(tokens), 3) if tokens else 0.0,
            recovery_rate=round(recovered / recoverable, 6) if recoverable else 0.0,
        )
