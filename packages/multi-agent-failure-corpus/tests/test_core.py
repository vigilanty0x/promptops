import json
import unittest

from multi_agent_failure_corpus import evaluate

GOOD = {"scenario_id": "failure-1", "category": "timeout", "reproduction": ["start worker", "advance clock"], "expected_failure": "TIMEOUT"}


def assert_secret_rejected_without_echo(test: unittest.TestCase, secret: str, *, field: str = "reproduction") -> None:
    record = {**GOOD, field: [f"observed {secret}"] if field == "reproduction" else f"observed {secret}"}
    result = evaluate(record)
    rendered = json.dumps(result, sort_keys=True)
    test.assertEqual(result["status"], "failed")
    test.assertGreater(result["corpus_entry"]["redactions"], 0)
    test.assertNotIn(secret, rendered)
    test.assertNotIn("record", result)


class ContractTests(unittest.TestCase):
    def test_valid_entry_passes_with_zero_redactions_and_limit_label(self):
        result = evaluate(GOOD)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["corpus_entry"]["redactions"], 0)
        self.assertIn("not an anonymity guarantee", result["corpus_entry"]["anonymization"])
        self.assertNotIn("record", result)

    def test_slack_tokens_fail_without_echo(self):
        for secret in (
            "xoxb-" + "1234567890-abcdefghijklmnop",
            "xoxp-" + "1234567890-abcdefghijklmnop",
        ):
            with self.subTest(secret=secret[:4]):
                assert_secret_rejected_without_echo(self, secret)

    def test_stripe_tokens_fail_without_echo(self):
        for secret in (
            "sk_" + "live_" + "1234567890abcdefghij",
            "pk_" + "live_" + "abcdefghij1234567890",
        ):
            with self.subTest(secret=secret[:7]):
                assert_secret_rejected_without_echo(self, secret)

    def test_jwt_fails_without_echo(self):
        candidate = "eyJ" + "hbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        assert_secret_rejected_without_echo(self, candidate)

    def test_aws_access_and_session_keys_fail_without_echo(self):
        for prefix in ("AKIA", "ASIA"):
            assert_secret_rejected_without_echo(self, prefix + "1234567890ABCDEF")

    def test_bearer_and_generic_assignments_fail_without_echo(self):
        for secret in (
            "Bearer " + "abcdefghijklmnop123456",
            "api_key=" + "abcdEFGH1234567890ijklmnop",
            "client_secret=" + "ZYXW9876vuts5432rqpo",
        ):
            assert_secret_rejected_without_echo(self, secret)

    def test_unlabeled_high_entropy_token_fails_without_echo(self):
        assert_secret_rejected_without_echo(self, "aB3dE5fG7hJ9kL2mN4pQ6rS8tV0xYz")

    def test_private_key_email_and_ip_fail_without_echo(self):
        private_key = "-----BEGIN " + "PRIVATE KEY-----\nabc123\n-----END " + "PRIVATE KEY-----"
        for secret in (private_key, "alice@example.com", "192.168.1.4"):
            assert_secret_rejected_without_echo(self, secret, field="expected_failure")

    def test_secret_in_scenario_id_is_not_reemitted(self):
        candidate = "ab3de5fg7hj9kl2mn4pq6rs8tv0xyz"
        result = evaluate({**GOOD, "scenario_id": candidate})
        rendered = json.dumps(result, sort_keys=True)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn(candidate, rendered)

    def test_extra_invalid_and_missing_fields_fail_without_input_echo(self):
        self.assertEqual(evaluate({**GOOD, "notes": "extra"})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "scenario_id": "Alice Smith"})["status"], "failed")
        self.assertEqual(evaluate({**GOOD, "reproduction": ["x"] * 51})["status"], "failed")
        self.assertEqual(evaluate(None)["status"], "failed")
        self.assertEqual(evaluate({})["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
