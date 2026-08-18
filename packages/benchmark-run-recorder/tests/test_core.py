import unittest

from benchmark_run_recorder import evaluate

GOOD = {"benchmark": "latency", "configuration": {"model": "local"}, "duration_ms": 120, "result": {"score": 0.9}, "artifacts": [{"path": "report.json", "sha256": "a" * 64}]}


class ContractTests(unittest.TestCase):
    def test_valid_record_is_explicitly_not_verified(self):
        result = evaluate(GOOD)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["run_manifest"]["kind"], "benchmark-record")
        self.assertEqual(result["run_manifest"]["verification"], "not-performed")

    def test_nonfinite_and_boolean_metrics_fail(self):
        self.assertEqual(evaluate({**GOOD, "duration_ms": float("nan")})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "result": {"score": True}})["status"], "failed")

    def test_duration_bound_is_enforced(self):
        self.assertEqual(evaluate({**GOOD, "duration_ms": 86_400_001})["status"], "failed")

    def test_artifacts_require_structured_digest(self):
        self.assertEqual(evaluate({**GOOD, "artifacts": ["report.json"]})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "artifacts": [{"path": "report.json", "sha256": "A" * 64}]})["status"], "failed")

    def test_result_metrics_are_bounded(self):
        self.assertEqual(evaluate({**GOOD, "result": {"score": 1e16}})["status"], "failed")

    def test_non_object_and_missing_field_fail_closed(self):
        self.assertEqual(evaluate([])["status"], "failed")
        self.assertEqual(evaluate({})["status"], "blocked")

    def test_result_is_deterministic(self):
        self.assertEqual(evaluate(GOOD), evaluate(dict(reversed(list(GOOD.items())))))


if __name__ == "__main__":
    unittest.main()
