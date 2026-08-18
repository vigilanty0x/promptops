# Changelog

## 0.3.0 - 2026-08-18

- Add deterministic offline scorecard routing with explicit quality, latency, cost, allowlist, and fallback constraints.
- Verify scorecard schema, rank sequence, winner, finite metrics, and SHA-256 content before routing.
- Add fail-closed `decision=abstain` routing output and CLI exit code `3` when no candidate qualifies.
- Preserve per-candidate rejection evidence and content-address every route decision.
- Harden `promptops release` to recompute dataset, scorecard, and regression artifact hashes before trusting release evidence or regression verdicts.
- Add counter-proof tests showing a red regression cannot be flipped green while retaining its old artifact SHA.
- Consolidate nine audited PromptOps-adjacent repositories under `packages/` with imported-history evidence.
- Expand CI to verify the root package plus all nine consolidated packages on Python 3.11 and 3.12.
- Add machine-readable compatibility, consumer-scan, redirect, rollback, and human-approval archive gates.
- Add verified canonical-development notices to all nine source repositories while leaving them public and unarchived.

Release candidate verification is the full repository CI matrix: root install/checks/portfolio gate/tests/suite validation/functional probe/demo/wheel on Python 3.11 and 3.12, plus install/checks/tests/wheel for each consolidated package on both Python versions.

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
