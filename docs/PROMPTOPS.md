# PromptOps evidence layer

PromptOps extends PromptBench without changing the benchmark producer/judge contract. The layer consumes already-generated, hash-verified reports and emits deterministic operations artifacts.

## Artifacts

| Kind | Input | Purpose | Gate |
|---|---|---|---|
| `scorecard` | one verified report | compact ranked evidence | no |
| `regression` | baseline + current report | detect quality/latency/cost regressions | yes |
| `failure_corpus` | one verified report | retain failed attempts and reasons | no |
| `jury_consensus` | 1..256 verified reports | deterministic Borda-style consensus | no |
| `dataset_manifest` | versioned suites | bind datasets and versions | no |
| `release_manifest` | dataset + scorecards + regressions | bind release evidence | yes |

Every artifact carries `schema_version=1.0`, a `kind`, and an `artifact_sha` computed over canonical JSON before the digest field is added.

## Regression contract

Three explicit tolerances are supported:

- `pass_rate_drop`: absolute pass-rate decrease tolerated;
- `latency_increase`: relative mean-latency increase tolerated;
- `cost_increase`: relative total-cost increase tolerated.

A candidate is regressed when any configured tolerance is breached. The regression artifact lists per-candidate deltas and reasons. The CLI exits `3` when the aggregate regression gate is red.

## Jury contract

Each verified report is one ballot. For a ballot of `N` candidates, rank 1 receives `N` points, rank 2 receives `N-1`, and so on. Missing candidates receive no points.

Tie-break order is deterministic:

1. more Borda points;
2. higher mean pass rate;
3. lower mean cost;
4. lower mean latency;
5. lexicographically smaller candidate id.

The jury does not call a model and does not reinterpret outputs. It aggregates already-judged reports only.

## Failure corpus

Failure corpora keep bounded failure metadata: run id, candidate, scenario, difficulty, attempt, status, error, reason, bounded diff, and output hash. Raw output text is intentionally omitted from the corpus artifact so the operations layer can preserve evidence without duplicating potentially sensitive output content.

## Release gate

A release manifest binds one dataset manifest, one or more scorecards, and zero or more regression artifacts. It fails closed when any supplied regression artifact has `passed=false`.

This is an evidence gate, not a deployment mechanism. It does not publish packages, call provider APIs, or change GitHub settings.
