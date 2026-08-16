import unittest

from prompt_package_manager import evaluate

GOOD = {"name": "summarize", "version": "1.0.0", "prompt": "Summarize {text}", "variables": ["text"], "output_schema": {"type": "string"}, "tests": [{"variables": {"text": "x"}, "expected_prompt": "Summarize x", "output": "summary"}]}


class ContractTests(unittest.TestCase):
    def test_executes_deterministic_local_cases(self):
        result = evaluate(GOOD)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["package_manifest"]["tests"][0]["passed"])
        self.assertFalse(result["package_manifest"]["installed"])
        self.assertFalse(result["package_manifest"]["stored"])

    def test_strict_semver_rejects_leading_zero_and_accepts_prerelease(self):
        self.assertEqual(evaluate({**GOOD, "version": "01.0.0"})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "version": "1.0.0-rc.1+build.5"})["status"], "passed")

    def test_prompt_fields_are_simple_and_exact(self):
        self.assertEqual(evaluate({**GOOD, "prompt": "{text.__class__}"})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "variables": ["text", "missing"]})["status"], "failed")

    def test_expected_substitution_is_actually_checked(self):
        tests = [{"variables": {"text": "x"}, "expected_prompt": "not rendered", "output": "summary"}]
        self.assertEqual(evaluate({**GOOD, "tests": tests})["status"], "failed")

    def test_output_schema_is_actually_checked(self):
        tests = [{"variables": {"text": "x"}, "expected_prompt": "Summarize x", "output": 3}]
        self.assertEqual(evaluate({**GOOD, "tests": tests})["status"], "failed")

    def test_prompt_and_test_bounds_fail(self):
        self.assertEqual(evaluate({**GOOD, "prompt": "x" * 16_385})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "tests": GOOD["tests"] * 101})["status"], "failed")

    def test_non_object_and_missing_field_fail_closed(self):
        self.assertEqual(evaluate([])["status"], "failed")
        self.assertEqual(evaluate({})["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
