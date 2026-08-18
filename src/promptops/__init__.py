"""Canonical Python namespace for PromptOps.

The implementation continues to reuse the proven PromptBench replay engine.
``promptbench`` remains a compatibility namespace during the 0.6 migration.
"""

__version__ = "0.6.0"

from promptbench import BenchmarkHarness, BenchmarkReport, BenchmarkSuite, ValidationError

__all__ = [
    "BenchmarkHarness",
    "BenchmarkReport",
    "BenchmarkSuite",
    "ValidationError",
    "__version__",
]
