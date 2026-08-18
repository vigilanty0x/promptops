# PromptOps evidence layer

PromptOps extends PromptBench without changing the benchmark producer/judge contract. The layer consumes already-generated, hash-verified reports and scorecards and emits deterministic operations artifacts.

## Artifacts

| Kind | Input | Purpose | Gate |
|---|---|---|---|
| `scorecard` | one verified report | compact ranked evidence | no |
| `regression` | baseline + current report | detect quality/latency/cost regressions | yes |
| `failure_corpus` | one verified report | retain failed attempts and reasons | no |
| `jury_consensus` | 1..256 verified reports | deterministic Borda-style consensus | no |
| `dataset_manifest` | versioned suites | bind datasets and versions | no |
| `route_decision` | one verified scorecard + explicit policy | choose an eligible candidate or abstain | yes |
| `release_manifest` | verified dataset + scorecards + regressions | bind release evidence | yes |

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

## Routing contract

Routing consumes exactly one content-addressed `scorecard`. Before evaluating any candidate, PromptOps recomputes and verifies the scorecard `artifact_sha`, validates the scorecard schema, requires a complete unique rank sequence, requires the declared winner to equal rank 1, and validates finite pass-rate, latency, and cost metrics.

A routing policy may specify:

- `min_pass_rate` between `0` and `1`;
- optional maximum mean latency in milliseconds;
- optional maximum total cost in microunits;
- an optional explicit candidate allowlist;
- `fallback_count` from `0` to `64`.

Candidates are evaluated in the verified scorecard rank order. A candidate is eligible only when it satisfies every supplied policy constraint. The first eligible candidate becomes `selected_candidate`; subsequent eligible candidates may be emitted as bounded fallbacks.

If no candidate is eligible, the route artifact contains `decision=abstain`, `selected_candidate=null`, and no fallbacks. Abstention is a valid evidence result rather than an input error, and the CLI exits `3` so automation can fail closed.

Every considered candidate retains explicit rejection reasons drawn from `not_allowed`, `pass_rate`, `latency`, and `cost`. The router never calls a model, never retries a provider, never infers missing capabilities, and never changes scorecard ranking.

## Failure corpus

Failure corpora keep bounded failure metadata: run id, candidate, scenario, difficulty, attempt, status, error, reason, bounded diff, and output hash. Raw output text is intentionally omitted from the corpus artifact so the operations layer can preserve evidence without duplicating potentially sensitive output content.

## Release gate

A release manifest binds one dataset manifest, one or more scorecards, and zero or more regression artifacts. Before reading any regression `passed` field, the 0.3 release path recomputes every supplied artifact SHA and validates its expected kind/schema. Scorecards additionally pass the full routing scorecard validator.

This prevents a stale SHA from being reused after changing a winner, dataset content, or regression verdict. A tampered release input is an invalid input and the CLI exits `2`; a genuine, hash-valid regression with `passed=false` keeps the release gate red and returns `3`.

Successful release manifests record `evidence_hashes_verified=true`. This is integrity validation of the supplied local evidence, not cryptographic provenance or remote attestation.

This remains an evidence gate, not a deployment mechanism. It does not publish packages, call provider APIs, or change GitHub settings.
