"""Producer boundary and deterministic replay implementation."""

from __future__ import annotations

from typing import Protocol

from .models import BenchmarkSuite, Candidate, ReplaySample, Scenario


class Producer(Protocol):
    def generate(self, candidate: Candidate, scenario: Scenario, attempt: int, prompt: str) -> ReplaySample: ...


class ReplayProducer:
    """Returns versioned recorded samples without network, clock, cache, or model calls."""

    def __init__(self, suite: BenchmarkSuite) -> None:
        self.suite = suite

    def generate(self, candidate: Candidate, scenario: Scenario, attempt: int, prompt: str) -> ReplaySample:
        if attempt < 1:
            raise IndexError("attempts are one-based")
        return self.suite.replay[candidate.candidate_id][scenario.scenario_id][attempt - 1]
