import unittest

from promptbench.judges import judge
from promptbench.models import JudgeSpec


class JudgeTests(unittest.TestCase):
    def test_exact_passes(self):
        result = judge(JudgeSpec("exact"), "Paris", "Paris")
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)

    def test_exact_normalizes_case_and_whitespace(self):
        result = judge(JudgeSpec("exact", case_sensitive=False), "Hello world", "  HELLO   WORLD ")
        self.assertTrue(result.passed)

    def test_exact_failure_has_bounded_diff(self):
        result = judge(JudgeSpec("exact"), "Paris", "Lyon")
        self.assertFalse(result.passed)
        self.assertIn("expected", result.diff)
        self.assertLessEqual(len(result.diff), 4_000)

    def test_contains_passes(self):
        result = judge(JudgeSpec("contains", case_sensitive=False), "blue", "The color is BLUE.")
        self.assertTrue(result.passed)

    def test_contains_failure_is_explicit(self):
        result = judge(JudgeSpec("contains"), "blue", "green")
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "required text missing")

    def test_json_equal_ignores_key_order(self):
        result = judge(JudgeSpec("json_equal"), {"a": 1, "b": 2}, '{"b":2,"a":1}')
        self.assertTrue(result.passed)

    def test_json_mismatch_has_diff(self):
        result = judge(JudgeSpec("json_equal"), {"ok": True}, '{"ok":false}')
        self.assertFalse(result.passed)
        self.assertIn("JSON mismatch", result.reason)
        self.assertTrue(result.diff)

    def test_invalid_json_fails_without_exception(self):
        result = judge(JudgeSpec("json_equal"), {"ok": True}, "not-json")
        self.assertFalse(result.passed)
        self.assertIn("invalid JSON", result.reason)


if __name__ == "__main__":
    unittest.main()
