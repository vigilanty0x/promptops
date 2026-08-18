# Architecture

PromptOps is the canonical product. Its architecture has two layers that remain deliberately separable:

1. **Replay/evaluation engine** — the historical `promptbench` namespace validates versioned benchmark suites, executes bounded offline replay producers, applies independent deterministic judges, retains every attempt, calculates comparative metrics, and emits SHA-bound reports.
2. **PromptOps quality layer** — the `promptops` CLI consumes verified local evidence to build scorecards, regressions, failure corpora, jury decisions, dataset manifests, route decisions, release manifests, and bundle-verification receipts.

The prepared 0.6 distribution is `promptops-replay`. New Python integrations use `import promptops`; `import promptbench` and the `promptbench` CLI remain compatibility surfaces for the replay engine. Both namespaces expose the same package version, and the canonical namespace re-exports the proven benchmark model/harness types rather than duplicating their implementation.

## Replay engine responsibilities

1. `BenchmarkSuite` validates the versioned scenario, candidate, limit, price, and replay contracts.
2. A `Producer` returns a bounded sample. The built-in public producer is the offline `ReplayProducer`.
3. Independent judges score exact, contains, or JSON-equality expectations.
4. `BenchmarkHarness` retains every run, calculates comparative metrics, ranks candidates, and emits content-addressed evidence.

Report output is written to a temporary file, flushed, atomically replaced, and verified from its embedded SHA. A failed or oversized producer output becomes an error record rather than a successful partial run.

## Quality/release responsibilities

PromptOps operations never infer remote truth from a local artifact. Stored artifacts are re-hashed and contract-checked before use; release bundles require explicit evidence files; routing can abstain; red regressions remain visible; and candidate provenance is kept distinct from publication authority.

For 0.6, the build/attestation chain can reach verified candidate provenance while publication remains disabled. `published-release.v1.json` separately pins the independently verified `v0.5.0` public release, so changing the next candidate cannot rewrite published history.

## Compatibility boundary

The canonical product inventory is available through the existing replay-engine `promptbench inventory` command during the 0.6 compatibility window. Removing or renaming that surface requires a separate migration with consumer evidence; it is not part of the current identity normalization.
