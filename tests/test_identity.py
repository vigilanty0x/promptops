from __future__ import annotations

import importlib.metadata as metadata
import unittest

import promptbench
import promptops


class IdentityContractTests(unittest.TestCase):
    def test_canonical_and_legacy_namespaces_share_version(self):
        self.assertEqual(promptops.__version__, "0.6.0")
        self.assertEqual(promptbench.__version__, "0.6.0")
        self.assertEqual(promptops.__version__, promptbench.__version__)

    def test_canonical_namespace_reexports_legacy_engine_types(self):
        self.assertIs(promptops.BenchmarkHarness, promptbench.BenchmarkHarness)
        self.assertIs(promptops.BenchmarkReport, promptbench.BenchmarkReport)
        self.assertIs(promptops.BenchmarkSuite, promptbench.BenchmarkSuite)
        self.assertIs(promptops.ValidationError, promptbench.ValidationError)

    def test_installed_distribution_uses_canonical_promptops_name(self):
        self.assertEqual(metadata.version("promptops-replay"), promptops.__version__)

    def test_legacy_distribution_is_not_required_for_canonical_import(self):
        names = {
            (dist.metadata.get("Name") or "").lower()
            for dist in metadata.distributions()
        }
        self.assertIn("promptops-replay", names)


if __name__ == "__main__":
    unittest.main()
