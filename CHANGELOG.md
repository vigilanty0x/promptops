# Changelog

## 0.2.0 - 2026-08-17

- Add the offline `promptops` CLI alongside `promptbench`.
- Add SHA-bound scorecards from verified PromptBench reports.
- Add deterministic quality/latency/cost regression gates.
- Add deterministic multi-report jury consensus.
- Add versioned dataset manifests and bounded failure corpora.
- Add fail-closed release evidence manifests.
- Add PromptOps contract documentation and migration/rollback guidance.

Release candidate verification remains the repository CI matrix on Python 3.11 and 3.12: install, checks, tests, suite validation, functional probe, demo, and wheel build.

## 0.1.0 - 2026-08-15

- Add bounded, versioned scenario/candidate/replay schemas.
- Add deterministic replay producer and three independent judges.
- Add complete run records, comparative metrics, rankings, diffs, and limitations.
- Add atomic report output with SHA verification.
- Add liveness, readiness, and functional counter-proof probes.
- Add synthetic suite, reproducible demo, CI, tests, and documentation.
