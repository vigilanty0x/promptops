"""Canonical Python namespace for PromptOps.

The implementation continues to reuse the proven PromptBench replay engine.
``promptbench`` remains a compatibility namespace during the 0.6 migration.
"""

__version__ = "0.6.0"

from promptbench import BenchmarkHarness, BenchmarkReport, BenchmarkSuite, ValidationError
from promptbench.workflow import run_workflow

__all__ = [
    "BenchmarkHarness",
    "BenchmarkReport",
    "BenchmarkSuite",
    "ValidationError",
    "run_workflow",
    "__version__",
]
