"""Legacy PromptBench compatibility namespace for PromptOps.

New integrations should prefer ``import promptops``.  The ``promptbench``
namespace remains supported so existing benchmark and replay consumers do not
break during the PromptOps identity migration.
"""

__version__ = "0.6.0"

from .harness import BenchmarkHarness
from .models import BenchmarkReport, BenchmarkSuite, ValidationError

__all__ = ["BenchmarkHarness", "BenchmarkReport", "BenchmarkSuite", "ValidationError"]
