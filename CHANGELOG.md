# Changelog

## 0.6.0 - 2026-08-18

- Make **PromptOps** the canonical product, package and README identity while retaining the proven PromptBench replay engine as a compatibility layer.
- Rename the candidate root distribution from `promptbench-replay` to `promptops-replay`; add the canonical `promptops` Python namespace and `python -m promptops` entry point.
- Preserve legacy `import promptbench` and the `promptbench` CLI at the same `0.6.0` version so existing benchmark/replay consumers do not break during the identity transition.
- Keep the nine consolidated package distributions, CLIs and versions unchanged; the identity migration applies only to the root PromptOps distribution.
- Separate the prepared `v0.6.0` candidate policy from the independently verified published `v0.5.0` record.
- Mark `v0.6.0` **publication disabled** with `publish_enabled=false`; a disabled candidate must have no `publish-release` job, no `contents: write` release authority and no `gh release create` path in normal CI.
- Continue the 40 wheel-producing jobs across CPython 3.11, 3.12, 3.13 and 3.14, deterministic double builds, clean-venv installed-wheel smoke tests, and SLSA provenance generation/verification for the candidate wheels.
- Add a deterministic **SPDX SBOM** gate over the ten exact candidate wheel subjects, including direct `Requires-Dist` relationships, byte-for-byte regeneration checks, exact-wheel verification, and retained SHA-256 evidence without enabling publication.
- Add fail-closed identity gates that require README, distribution metadata, canonical/legacy Python namespaces, CLIs, changelog, migration guide and rollback story to agree.
- Add explicit migration and Rollback guidance to the verified published `v0.5.0` / `promptbench-replay` artifacts.

`v0.6.0` is a PREPARED candidate only. The 40 wheel-producing jobs, SLSA provenance and SPDX SBOM can establish build and supply-chain evidence, but they do not authorize publication. Publication remains disabled until a separate reviewed policy/workflow change restores an owner/main publisher and the resulting release is independently read back and verified.

## 0.5.0 - 2026-08-18

- Add explicit `promptops verify-bundle` release-evidence linkage verification.
- Verify the release manifest and every caller-supplied dataset, scorecard, and regression artifact before linkage checks.
- Require the unique `(kind, artifact_sha)` evidence set to exactly match the release manifest without scanning directories or fetching remote evidence.
- Reconcile actual hash-valid red regressions with `failed_regression_count` and `regression_gate_passed`, catching re-hashed release manifests that are internally consistent but false relative to their referenced evidence.
- Preserve producer semantics for repeated identical evidence SHA references: one local file satisfies the repeated SHA while reference multiplicity still contributes to release gate counts.
- Reject missing, unexpected, duplicate-supplied, tampered, unsupported, or contradictory bundle evidence with exit code `2`.
- Keep verification separate from deployment authorization: a coherent red release bundle verifies successfully with `release_gate_passed=false`.
- Preserve legacy release-manifest source-evidence semantics and explicit `provenance=not-verified` receipts.
- Expand the release gate to CPython 3.11, 3.12, 3.13, and 3.14 across the root project and all nine consolidated packages: 40 wheel-producing jobs.
- Require deterministic double wheel builds, exact `setuptools==83.0.0`, clean-venv installed-wheel verification, retained wheel evidence, and fail-closed workflow/release policy checks.
- Generate GitHub/Sigstore SLSA provenance over the ten canonical wheels after the complete matrix and verify every subject with repository, workflow, source-ref, source-SHA, and runner policy constraints.
- Publish the GitHub `v0.5.0` release only from an owner-triggered `main` push after the complete build and signed-provenance gates succeed.

Release candidate verification is the 40-job wheel-producing matrix plus the signed provenance aggregation/verification job. The GitHub Release publisher is a separate owner-only post-gate job and does not run on pull requests.

## 0.4.0 - 2026-08-18

- Add generic `promptops verify` support for all seven PromptOps artifact kinds: scorecards, regressions, failure corpora, jury consensus, dataset manifests, route decisions, and release manifests.
- Recompute each stored artifact SHA before applying kind-specific contract invariants.
- Reject internally contradictory artifacts even when a caller recomputes a fresh matching SHA after tampering.
- Reconstruct route eligibility and rejection reasons from the stored routing policy and candidate metrics instead of trusting stored routing claims.
- Return verification receipts that distinguish `integrity=verified` and `contract=verified` from `provenance=not-verified`.
- Preserve verification compatibility for pre-0.3 release manifests without retroactively inventing source-evidence integrity: absent evidence is reported as `not-recorded`, explicit `true` as `verified`, and explicit `false` remains invalid.
- Keep the full 20-job CI matrix as the release gate: root PromptOps on Python 3.11/3.12 plus all nine consolidated packages on both versions.

Release candidate verification includes editable install, static checks, portfolio compatibility gate, full unit tests, suite validation, functional counter-proof, demo, root wheel build, and install/check/test/wheel for every consolidated package.

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
