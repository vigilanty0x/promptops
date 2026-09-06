# Rules, scoring and an explicit jury

PromptOps now evaluates the useful rules of the preserved `prompt-regression`,
`consensus-engine` and `llm-jury` cores inside its canonical engine. Runtime code
does not import those historical packages. Differential tests import their real
cores as independent oracles. The native scorecard and routing engine already
provide the `model-scorecard` calculation; tests compare them over the common
input domain instead of adding a second production scoring engine.

These operations consume **supplied records**. They do not contact models, launch
other programs, verify a juror's identity, or prove that recorded latency/cost was
measured. `provider_called=false`, `juror_identity_verified=false` and
`provenance=not-verified` remain explicit. No multi-model execution is implied.

## One workflow, explicit input

```sh
promptops run examples/suite.json --output assessment-with-jury --min-pass-rate 0.7 --jury examples/jury-input.json
promptops verify --run assessment-with-jury --suite examples/suite.json --jury examples/jury-input.json
```

The example votes/scores are synthetic. Their `suite_sha` is the canonical suite
identity produced by `promptbench validate --suite examples/suite.json`, not the
SHA-256 of the formatted input file. For another suite, supply that suite's
actual identity and candidate IDs. Never relabel old votes as a new measurement.
`--baseline-report previous/report.json` also works; verification must receive
that same baseline with its own `--baseline-report`.

The input is a strict JSON object (`promptops-jury-input/1`):

| Field | Contract |
| --- | --- |
| `schema`, `suite_sha`, `votes` | Required; the SHA is 64 lowercase hexadecimal characters. |
| `votes` | 1–1000 objects, each `choice` and optional `weight`; no other fields. |
| `choice` | A suite candidate ID or reserved `abstain`; bounded nonempty string. |
| `weight` | Finite JSON number, strictly greater than 0 and at most 100; default 1. |
| `quorum` | Integer 1–1000, default 2. It counts all supplied votes, including abstentions, exactly as the source engine does. It does not count authenticated distinct people. |
| `threshold` | Finite number 0–1, default 0.6. The winning weight share excludes abstentions. |
| `score_jury` | Optional object with required `candidate_id`, `scores`; optional `pass_score` and `max_spread`. |
| `scores` | 2–100 finite numbers 0–1, associated with one candidate; no identity verification. |
| `pass_score`, `max_spread` | Finite numbers 0–1, defaults 0.7 and 0.35. |

Insufficient quorum or no participating weight yields `blocked/quorum`. An exact
top-weight tie yields `blocked/split`; otherwise the winning share must reach the
threshold. Floating-point comparisons follow the original engine, with no new
epsilon. The optional score jury blocks if `max(scores)-min(scores)` exceeds the
spread limit; otherwise its median must reach `pass_score`. Its candidate must
match the weighted winner and the existing route. Unknown candidate IDs or a
different suite are input errors before any output directory is created.

The workflow writes the original five evidence artifacts plus optional
`regression.json` and **`jury.json`**, followed by `result.json` last. `jury.json`
contains the supplied input, its digest, computed vote/score decisions, refusal
reasons and context with exact `suite_sha`, `report_sha`, candidate IDs and the
selected route candidate. The existing receipt schema remains
`promptops-workflow/1`; its `artifacts` map includes the exact bytes of `jury.json`.
No jury-related receipt fields are added when `--jury` is absent.

**Routing decision and global gate are different.** `decision=route` means the
original scorecard policy selected a candidate. The final gate is:

```
route is not abstain AND baseline gate (if supplied) AND jury gate (if supplied)
```

Thus `decision=route` and `gate_passed=false` can coexist. A conflicting jury
never substitutes its own winner. A passing jury cannot rescue abstention or a
failed regression. Consumers must use `gate_passed`, not `decision` alone, to
require all requested checks. The jury is optional only before the run; it is
mandatory evidence when verifying a run that contains it. No CC UI/API change is
part of this module change; consumers must separately expose any user jury input.

## Three distinct jury/scoring operations

* `promptops jury REPORT...` keeps the existing Borda aggregation of report
  rankings and its existing tie rules, `kind=jury_consensus`.
* `promptops jury --votes INPUT -o ARTIFACT` evaluates supplied weighted votes and
  optional median/spread scores, `kind=jury_assessment`. It does not have an
  external suite/report context. Standalone success is not workflow approval.
* `promptops scorecard REPORT` and `promptops route SCORECARD ...` use the native
  verified report's pass rate, summed cost, mean latency and stable ordering.
  Parity with `model-scorecard` means identifying source `model` with native
  `candidate_id`, source `cost` with **microunits**, using the same cost/latency
  ceilings and `min_pass_rate=0` (the source has no pass-rate threshold).
  Native `scorecard.winner` is the raw best rank; the budget-filtered source
  winner corresponds to `route.selected_candidate`. Real harness records, not
  manually fabricated scorecard rows, exercise the parity tests.

`--votes` cannot be combined with report positional arguments. The existing
`release` / `verify-bundle` interface remains unchanged; it does not accept jury
evidence or claim a jury veto. Use the workflow receipt plus `verify --run` for a
decision that includes a jury.

## Case regression through the native judges

```sh
promptops regress --cases examples/cases-input.json -o case-regression.json
promptops verify case-regression.json --kind case_regression
```

Input schema `promptops-cases-input/1` requires only `schema` and `cases`. Each
case requires a unique nonempty `id`, `baseline` and `candidate` response strings,
and `expected`; optional `mode` is `exact` (default), `contains` or `json`.
Text modes require a string expected value. Exact and contains comparisons are
case-sensitive and preserve whitespace, matching `prompt-regression`; the
normalization defaults for existing benchmark suites are unchanged. JSON mode
uses native parsed equality, including Python's inherited boolean/numeric
equality semantics; it is not a JSON Schema validator.

A case is `regression` only when baseline passes and candidate fails;
`improvement` means the reverse, otherwise `unchanged`. The artifact contains
all case statuses, the regression count and a gate requiring zero regressions.
`--cases` cannot be combined with baseline/current report operands or nondefault
report thresholds. Report regression mode and its tolerances are unchanged.

Input files and their serialized JSON are capped at 2 MiB; there are at most
1000 cases, each response at most 8192 UTF-8 bytes, and identifiers/choices at
most 200 UTF-8 bytes without control characters. All new inputs reject duplicate
JSON keys, NaN/Infinity, bool/string numeric coercion, unknown fields/modes and
invalid JSON responses. These are intentional stricter boundaries than some
historical cores (which allowed 10000 cases or permissive coercion). Parity is
claimed on the documented finite typed common domain, not those unsafe inputs.

Jury and case artifacts retain **raw supplied input** for replay, including case
text. They do not anonymize it; do not submit secrets or data you cannot export.
The existing failure-corpus behavior remains separate and unchanged.

## Replays, exports and failures

Copy the complete workflow directory and retain its original suite, optional
baseline and jury input. `verify --run DIR --suite SUITE [--jury INPUT]
[--baseline-report REPORT]` reads only the eight fixed canonical artifact names,
requires the matching optional originals, reruns the actual harness and rules,
and checks every object and exact canonical byte sequence, including `result.json`.
It uses the routing policy recorded in the verified `route.json`; it does not
authenticate an independently remembered operator policy. An altered vote,
report link, result gate, inventory or encoding fails even if the modified
artifact's digest was recomputed. Standalone `verify ARTIFACT` replays embedded
rules and checks their integrity, but cannot authenticate external input authors
or prove historical origin. SHA-256 is not a signature.

Verification is read-only and preserves `provenance=not-verified`. Each artifact
read is bounded at 64 MiB, with at most eight files. Linked input files/directories
and nonregular input files are refused; an input must retain its observed file
identity while being read. This is a local-file integrity check, not an OS
sandbox guarantee against an attacker controlling all ancestor directories.

Codes are `0` for a valid passing operation, `3` for a valid negative business
gate, and `2` for invalid input or I/O failure. A coherent exported run with a
negative gate verifies with `0`, returning `gate_passed=false`: verification
success proves integrity, not quality. This matches existing bundle semantics.

The run output must be a new directory. Input validation precedes its creation.
A write failure leaves completed evidence files intact, without a success
receipt; retry into a new directory. Existing standalone `-o FILE` behavior can
replace that explicitly selected file and is retained for compatibility.

## Source links and verification

The preserved source cores retain their original Apache-2.0 licenses:

* `packages/consensus-engine/src/consensus_engine/core.py` → `weighted_vote`;
* `packages/llm-jury/src/llm_jury/core.py` → `score_jury`;
* `packages/prompt-regression/src/prompt_regression/core.py` → `compare_cases`
  through native `judges.judge`;
* `packages/model-scorecard/src/model_scorecard/core.py` → existing native
  scorecard plus route comparison on aligned units.

`tests/test_judgment_parity.py` exercises their real implementations, boundaries
and deterministic varied inputs. `tests/test_jury_workflow.py` exercises actual
CLI/workflow execution, route/regression vetoes, original-input binding,
rehashed tampering, export, partial writes and input refusal. Existing root tests
remain in place. The optional before-snapshot byte comparison skips when that
review fixture is unavailable; it is not a runtime dependency. No installation,
publication, provider call, remote CI or production execution is implied by
these local tests.
