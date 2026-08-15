# Architecture

PromptBench separates four responsibilities:

1. `BenchmarkSuite` validates the versioned scenario, candidate, limit, price, and replay contracts.
2. A `Producer` returns a bounded sample. Version 0.1.0 ships only the offline `ReplayProducer`.
3. Independent judges score exact, contains, or JSON-equality expectations.
4. `BenchmarkHarness` retains every run, calculates comparative metrics, ranks candidates, and emits content-addressed evidence.

Report output is written to a temporary file, flushed, atomically replaced, and verified from its embedded SHA. A failed or oversized producer output becomes an error record rather than a successful partial run.

The canonical component inventory is available through `promptbench inventory`.
