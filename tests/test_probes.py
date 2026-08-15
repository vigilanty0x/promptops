import unittest

from promptbench.probes import functional_probe, inventory, liveness_probe, readiness_probe


class ProbeTests(unittest.TestCase):
    def test_liveness_proves_version(self):
        result = liveness_probe()
        self.assertEqual(result, {"probe": "liveness", "status": "alive", "version": "0.1.0"})

    def test_readiness_proves_inventory(self):
        result = readiness_probe()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["inventory"]["producer"], "versioned-replay")

    def test_functional_counter_proof_falls(self):
        result = functional_probe()
        self.assertEqual(result["status"], "proven")
        self.assertEqual(result["control_pass_rate"], 1.0)
        self.assertEqual(result["counter_example_pass_rate"], 0.0)
        self.assertGreater(result["failures_preserved"], 0)

    def test_inventory_has_no_runtime_dependencies(self):
        result = inventory()
        self.assertEqual(result["runtime_dependencies"], [])
        self.assertIn("score_variance", result["metrics"])


if __name__ == "__main__":
    unittest.main()
