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

## Stored artifact verification

`promptops verify artifact.json` verifies a stored PromptOps artifact after generation. `--kind` can optionally pin the expected kind and fail if the artifact identifies itself differently.

Supported kinds are all seven PromptOps artifact families listed above. Verification first recomputes `artifact_sha`, verifies `schema_version=1.0` and the declared kind, then applies kind-specific invariants. Examples include:

- scorecard rank/winner/metric consistency;
- regression row/count/pass consistency;
- failure-corpus count bounds and raw-output exclusion;
- jury ballot/ranking/winner consistency;
- dataset uniqueness and bounded entry structure;
- route policy reconstruction from stored metrics, rejection reasons, selected candidate and fallbacks;
- release gate/count/SHA-array consistency.

This means simply recomputing a SHA after changing an internally contradictory field is not enough to pass verification.

A successful verification receipt reports:

- `valid=true`;
- `integrity=verified`;
- `contract=verified`;
- `provenance=not-verified`.

The last field is intentional. Local hash and contract verification does **not** prove who created the artifact, that it came from a trusted machine, or that its source evidence is remotely attested. Invalid/tampered/contract-inconsistent artifacts return CLI exit code `2`.

## Release bundle verification

`promptops verify-bundle release.json --artifact ...` verifies that a stored release manifest is actually backed by the explicit local evidence supplied with it.

The command deliberately does not scan a directory and does not fetch remote files. Callers explicitly name each dataset manifest, scorecard, and regression artifact. The verifier:

1. verifies the release manifest itself with `promptops verify` semantics;
2. verifies every supplied evidence artifact independently;
3. requires the unique `(kind, artifact_sha)` evidence set to exactly match the dataset, scorecard, and regression SHA references in the release manifest;
4. rejects duplicate supplied evidence and evidence kinds that a release does not reference;
5. counts the supplied hash-valid regressions whose `passed=false` and requires that count to equal `failed_regression_count` and the release gate.

This catches a release manifest that has been re-hashed into internal consistency while no longer telling the truth about the evidence files it references.

Bundle verification is bounded to 1024 explicitly supplied evidence artifacts. A successful receipt reports `integrity=verified`, `contract=verified`, `linkage=verified`, and `provenance=not-verified`.

A coherent bundle may intentionally contain a red release gate. Verification answers whether the bundle is internally linked and truthful, not whether it should be deployed. Therefore a coherent red bundle returns exit code `0` with `release_gate_passed=false`. Missing, extra, duplicate, tampered, or contradictory evidence returns `2`.

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

A release manifest binds one dataset manifest, one or more scorecards, and zero or more regression artifacts. Before reading any regression `passed` field, the current release path recomputes every supplied artifact SHA and validates its expected kind/schema. Scorecards additionally pass the full routing scorecard validator.

This prevents a stale SHA from being reused after changing a winner, dataset content, or regression verdict. A tampered release input is an invalid input and the CLI exits `2`; a genuine, hash-valid regression with `passed=false` keeps the release gate red and returns `3`.

Successful release manifests record `evidence_hashes_verified=true`. This is integrity validation of the supplied local evidence, not cryptographic provenance or remote attestation. Historical pre-0.3 manifests that never recorded the field remain verifiable as `source_evidence_integrity=not-recorded` rather than being assigned a newer guarantee retroactively.

This remains an evidence gate, not a deployment mechanism. It does not publish packages, call provider APIs, or change GitHub settings.
