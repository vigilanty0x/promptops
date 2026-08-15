import copy
import unittest

from fixtures import suite_data
from promptbench.harness import BenchmarkHarness
from promptbench.models import BenchmarkSuite, ReplaySample
from promptbench.runner import ReplayProducer


class RaisingProducer:
    def generate(self, candidate, scenario, attempt, prompt):
        raise RuntimeError("synthetic producer failure")


class CapturingProducer:
    def __init__(self, suite):
        self.delegate = ReplayProducer(suite)
        self.calls = []

    def generate(self, candidate, scenario, attempt, prompt):
        self.calls.append((candidate.candidate_id, scenario.scenario_id, attempt, prompt))
        return self.delegate.generate(candidate, scenario, attempt, prompt)


class HarnessTests(unittest.TestCase):
    def test_runs_full_cartesian_matrix(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        self.assertEqual(len(report.records), 8)
        self.assertEqual({item.attempt for item in report.records}, {1, 2})

    def test_failures_are_preserved_not_filtered(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        failures = [item for item in report.records if not item.passed]
        self.assertEqual(len(failures), 4)
        self.assertTrue(all(item.diff for item in failures))

    def test_ranking_prefers_pass_rate(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        self.assertEqual(report.ranking, ("good", "bad"))

    def test_candidate_metrics_include_cost_latency_tokens_and_variance(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        good = report.candidates[0]
        self.assertEqual(good.pass_rate, 1.0)
        self.assertGreater(good.total_cost_microunits, 0)
        self.assertGreater(good.mean_latency_ms, 0)
        self.assertEqual(good.mean_tokens_per_run, 12.0)
        self.assertEqual(good.score_variance, 0.0)

    def test_recovery_rate_tracks_later_success(self):
        data = suite_data()
        data["replay"]["bad"]["exact"][1]["output"] = "Paris"
        report = BenchmarkHarness(BenchmarkSuite.from_dict(data)).run()
        bad = next(item for item in report.candidates if item.candidate_id == "bad")
        self.assertEqual(bad.recovery_rate, 0.5)
        self.assertEqual(bad.pass_at_1, 0.0)

    def test_producer_errors_are_records(self):
        suite = BenchmarkSuite.from_dict(suite_data())
        report = BenchmarkHarness(suite, RaisingProducer()).run()
        self.assertTrue(all(item.status == "error" for item in report.records))
        self.assertTrue(all("RuntimeError" in item.error for item in report.records))
        self.assertEqual(report.candidates[0].pass_rate, 0.0)

    def test_replay_error_is_preserved(self):
        data = suite_data()
        data["replay"]["good"]["exact"][0] = {
            "error": "timeout", "latency_ms": 50, "input_tokens": 10, "output_tokens": 0,
        }
        report = BenchmarkHarness(BenchmarkSuite.from_dict(data)).run()
        record = next(item for item in report.records if item.run_id == "good:exact:1")
        self.assertEqual(record.status, "error")
        self.assertEqual(record.error, "timeout")
        self.assertFalse(record.passed)

    def test_output_limit_failure_hides_oversized_output(self):
        data = suite_data()
        data["limits"]["max_output_chars"] = 3
        report = BenchmarkHarness(BenchmarkSuite.from_dict(data)).run()
        record = next(item for item in report.records if item.run_id == "good:exact:1")
        self.assertEqual(record.error, "output_limit_exceeded")
        self.assertIsNone(record.output)
        self.assertIsNotNone(record.output_sha)

    def test_prompt_is_stable_across_repeats(self):
        suite = BenchmarkSuite.from_dict(suite_data())
        producer = CapturingProducer(suite)
        report = BenchmarkHarness(suite, producer).run()
        selected = [item.prompt_sha for item in report.records if item.candidate_id == "good" and item.scenario_id == "exact"]
        self.assertEqual(len(set(selected)), 1)
        prompts = [call[3] for call in producer.calls if call[:2] == ("good", "exact")]
        self.assertEqual(prompts, ["Answer: Say Paris", "Answer: Say Paris"])

    def test_report_sha_is_deterministic(self):
        suite = BenchmarkSuite.from_dict(suite_data())
        first = BenchmarkHarness(suite).run()
        second = BenchmarkHarness(suite).run()
        self.assertEqual(first.report_sha, second.report_sha)

    def test_methodology_and_limits_are_reported(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        self.assertGreaterEqual(len(report.methodology), 4)
        self.assertGreaterEqual(len(report.limitations), 4)
        self.assertTrue(any("same versioned scenarios" in item for item in report.methodology))

    def test_p95_uses_observed_tail(self):
        report = BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        good = report.candidates[0]
        self.assertEqual(good.p95_latency_ms, 13.0)


if __name__ == "__main__":
    unittest.main()
