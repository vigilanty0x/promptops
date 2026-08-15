import copy
import unittest

from fixtures import suite_data
from promptbench.models import (
    BenchmarkSuite,
    Candidate,
    Difficulty,
    JudgeSpec,
    Limits,
    ReplaySample,
    Scenario,
    ValidationError,
    digest,
)


class LimitsTests(unittest.TestCase):
    def test_defaults_are_bounded(self):
        self.assertEqual(Limits.from_dict(None), Limits(3, 8_000))

    def test_repeats_are_bounded(self):
        for value in (0, 21, "2"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Limits.from_dict({"repeats": value})

    def test_output_limit_is_bounded(self):
        with self.assertRaises(ValidationError):
            Limits.from_dict({"max_output_chars": 0})


class ContractTests(unittest.TestCase):
    def test_candidate_requires_one_input_placeholder(self):
        for template in ("no placeholder", "{input} and {input}"):
            with self.subTest(template=template), self.assertRaises(ValidationError):
                Candidate.from_dict({"id": "candidate", "model": "m", "prompt_template": template})

    def test_candidate_prices_are_bounded(self):
        with self.assertRaises(ValidationError):
            Candidate.from_dict({
                "id": "candidate", "model": "m", "prompt_template": "{input}",
                "input_price_microunits_per_1k": -1,
            })

    def test_scenario_difficulty_is_required(self):
        with self.assertRaisesRegex(ValidationError, "difficulty"):
            Scenario.from_dict({
                "id": "s", "difficulty": "impossible", "input": "x", "expected": "x",
                "judge": {"type": "exact"},
            })

    def test_judge_type_is_explicit(self):
        with self.assertRaisesRegex(ValidationError, "judge type"):
            JudgeSpec.from_dict({"type": "model-opinion"})

    def test_replay_requires_output_xor_error(self):
        for data in ({}, {"output": "x", "error": "e"}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                ReplaySample.from_dict(data)

    def test_error_replay_is_valid(self):
        sample = ReplaySample.from_dict({"error": "timeout", "latency_ms": 50, "input_tokens": 4, "output_tokens": 0})
        self.assertEqual(sample.error, "timeout")
        self.assertIsNone(sample.output)

    def test_latency_and_tokens_are_bounded(self):
        with self.assertRaises(ValidationError):
            ReplaySample.from_dict({"output": "x", "latency_ms": -1})
        with self.assertRaises(ValidationError):
            ReplaySample.from_dict({"output": "x", "input_tokens": -1})


class SuiteTests(unittest.TestCase):
    def test_suite_round_trip_contract(self):
        suite = BenchmarkSuite.from_dict(suite_data())
        self.assertEqual(suite.suite_id, "test-suite")
        self.assertEqual(suite.scenarios[0].difficulty, Difficulty.EASY)
        self.assertEqual(len(suite.replay["good"]["exact"]), 2)

    def test_suite_sha_is_deterministic(self):
        first = BenchmarkSuite.from_dict(suite_data())
        second = BenchmarkSuite.from_dict(suite_data())
        self.assertEqual(first.suite_sha, second.suite_sha)

    def test_schema_version_is_enforced(self):
        data = suite_data()
        data["schema_version"] = "2.0"
        with self.assertRaisesRegex(ValidationError, "1.0"):
            BenchmarkSuite.from_dict(data)

    def test_semver_is_enforced(self):
        data = suite_data()
        data["version"] = "latest"
        with self.assertRaisesRegex(ValidationError, "semantic"):
            BenchmarkSuite.from_dict(data)

    def test_duplicate_scenario_ids_are_rejected(self):
        data = suite_data()
        data["scenarios"].append(copy.deepcopy(data["scenarios"][0]))
        for candidate in data["candidates"]:
            data["replay"][candidate["id"]]["exact-copy"] = data["replay"][candidate["id"]]["exact"]
        with self.assertRaisesRegex(ValidationError, "unique"):
            BenchmarkSuite.from_dict(data)

    def test_replay_candidate_keys_must_match(self):
        data = suite_data()
        data["replay"].pop("bad")
        with self.assertRaisesRegex(ValidationError, "candidate keys"):
            BenchmarkSuite.from_dict(data)

    def test_replay_scenario_keys_must_match(self):
        data = suite_data()
        data["replay"]["good"].pop("json")
        with self.assertRaisesRegex(ValidationError, "scenario keys"):
            BenchmarkSuite.from_dict(data)

    def test_replay_series_must_match_repeat_count(self):
        data = suite_data()
        data["replay"]["good"]["exact"].pop()
        with self.assertRaisesRegex(ValidationError, "limits.repeats"):
            BenchmarkSuite.from_dict(data)

    def test_identifier_format_is_enforced(self):
        data = suite_data()
        data["suite_id"] = "Has Spaces"
        with self.assertRaisesRegex(ValidationError, "lowercase"):
            BenchmarkSuite.from_dict(data)

    def test_digest_is_mapping_order_independent(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
