# Optional local workflow bundles

`promptops run suite.json --bundle bundle-input.json --output new-report`
extends the existing replay workflow. It does not install, publish, call a
provider, create a dataset store or train a model. Omit `--bundle` to preserve
the existing receipt fields and output bytes, including jury behavior.

The Python entry points are:

```python
run_workflow(suite_path, output, *, baseline=None, policy=None,
             jury_path=None, bundle_path=None)
verify_workflow(output, suite_path, *, baseline=None,
                jury_path=None, bundle_path=None)
```

`bundle_path` names one explicit regular JSON file. The existing bounded reader
rejects links, duplicate JSON keys, non-finite values and changed file identity.
The output must be new. Input/schema/package/pattern/budget refusals happen
before output creation. A later filesystem write failure can leave a partial
directory without a completed receipt; retry into a new directory.

## Input

The exact schema is `promptops-bundle-input/1`. Unknown fields are refused.
Required fields are:

- `suite_sha`: identity returned by `BenchmarkSuite.from_dict(data).suite_sha`,
  tied to this exact normalized suite contract.
- `release_version`: bounded strict SemVer; this is a local bundle label, not
  publication authorization or the installed product version.
- `split`: exactly `{"algorithm":"source-sha256-pair-v1","test_percent":20}`;
  the percentage must be an integer from 1 through 99.
- `packages`: exactly one entry per native candidate, with `candidate_id` and
  `record`. Duplicate, absent or unknown candidates are refused.
- `provenance`: exactly `source_id`, `declared_at`, `duration_ms`.

Each package record has the historical fields `name`, `version`, `prompt`,
`variables`, `output_schema`, `tests`. The prompt must equal the candidate's
template byte for byte after UTF-8 decoding; variables must be exactly
`["input"]`. For example:

```json
{
  "candidate_id": "good",
  "record": {
    "name": "package-good", "version": "1.0.0",
    "prompt": "Answer: {input}", "variables": ["input"],
    "output_schema": {"type": "string"},
    "tests": [{
      "variables": {"input": "fixture"},
      "expected_prompt": "Answer: fixture", "output": "sample"
    }]
  }
}
```

The native port executes every deterministic substitution/schema case once.
It does not accept a supplied `passed` field. The sample output is supplied
data, not output from an AI call. The historical Formatter and native replay's
literal `{input}` replacement must agree on every case; escaped-brace or
formatting differences are refused. This is the supported intersection of
the two rendering contracts, not a change to existing replay rendering.

Names/versions, 1–100 tests, 64-variable historical cap, 16,384-character prompt,
32,768-character rendered prompt and 4,096-character variable values retain
the source bounds. The workflow uses only its one `input` variable. Packages
are capped at 128 KiB. Schema support is deliberately small: string, integer,
number, boolean, array, object; only object accepts `required` and `properties`.
Array item schemas and other JSON Schema keywords are refused, not silently
claimed as checked. Schema depth is capped at 12, JSON depth at 20.

`source_id` is a 1–100-character identifier. `declared_at` is null or an ISO
timestamp with an explicit offset. It is never replaced with a read timestamp
and never called observed; even a supplied future timestamp remains explicitly
declared and unverified. `duration_ms` is null or a finite positive supplied
number at most 86,400,000. Absence becomes `not_supplied`, not zero. There is no
claim that this replay duration was measured locally.

The full bundle input is capped at 2 MiB, its suite at 8 MiB, structure at
250,000 nodes and export at 64 MiB. Native suite/scenario/candidate/repeat
bounds remain active. No free paths or artifact lists are accepted in the
bundle declaration.

## Partition semantics

The real eval-dataset-builder algorithm hashes the canonical JSON pair
`input`/`expected`, removes exact duplicate pairs, sorts by digest and chooses
`test` if `int(digest[:8], 16) % 100 < test_percent`. There is no random seed in
that source contract. The versioned algorithm name is explicit; a seed field
or another algorithm is refused. Canonicalization preserves the source's
Unicode/CRLF semantics and does not normalize distinct strings together.

`split.json` exports pair digests and associated scenario IDs, not duplicate
raw examples. A same-input/different-expected conflict is refused as a stricter
workflow boundary. Identical pairs cannot appear in both partitions. Their
associated scenario/judge records remain in the original replay suite.

Small datasets can have an empty partition. The actual counts and
`partition_status=single_nonempty` make that visible; no rebalance changes the
historical algorithm. `both_nonempty` only describes the assignment.

**The benchmark still replays the complete supplied suite.** Neither partition
is used for training or an independent held-out evaluation. Both
`training_executed` and `holdout_evaluation_executed` remain false. The native
routing decision, regression veto and optional jury veto retain their
semantics. This split is reproducible organization of supplied cases, not a
new estimate of generalization or protection against all forms of leakage.

## Outputs and verification

Five files join the old artifacts:

| Artifact | Meaning |
| --- | --- |
| `split.json` | Source pair identities, duplicate count, assignment and explicit evaluation limits |
| `packages.json` | Results from actual local template/schema tests, linked to every candidate/template |
| `release.json` | Existing `release_manifest()` output from this run's dataset/scorecard/regression |
| `metrics-origin.json` | Supplied latency, costs calculated from supplied tokens/prices, optional declared duration |
| `bundle.json` | Exact hashes for the preceding artifacts plus all legacy artifacts and optional jury |

The existing `verify_release_bundle()` is actually called over the native
release's exact evidence set. The legacy `result.json` hashes `bundle.json`
and every other artifact; the bundle does not hash itself or create a circular
claim over `result.json`. Package success cannot authorize an abstaining or
vetoed route. The release's regression gate alone is not the overall route gate.

The optional benchmark record retains the source's
`verification=not-performed` for supplied measurements. Its fixed artifact
paths/hashes are computed from the actual local output values, and the enclosing
workflow checks their bytes. These two facts do not authenticate a measurement
source or convert supplied metrics into observed latency/cost. Global
`provider_called=false` and `provenance=not-verified` are preserved.

Export by copying the completed directory, then run:

```text
promptops verify --run copied-report --suite suite.json --bundle bundle-input.json
```

Include the original `--baseline-report` and `--jury` exactly when used. The
verifier replays all native computations from these explicit inputs, requires
the exact artifact inventory and compares every artifact's canonical bytes.
Changed input, modified bytes (even whitespace), missing/extra artifacts or
omitted original bundle input fail. Existing `verify-bundle` remains available
for `release.json` and its dataset/scorecard/regression evidence. The new
workflow-only artifacts are verified through `verify --run`, not accepted as
standalone legacy artifact kinds by `verify artifact.json`.

## Sensitive-pattern refusal

Bundle mode examines supplied suite content, package tests, provenance and jury
before export, using the patterns/entropy primitive from
multi-agent-failure-corpus. A detected pattern raises a fixed error without
printing the value or writing an output directory. No sanitized derivative is
mixed with an unsanitized raw report. The baseline report is read to calculate
regression but is not exported; its actual exported regression fields are
examined. This is not a claim to have secret-audited every unused baseline field.

Renaming a user-controlled field to `schema`, `suite_sha`, `report_sha`,
`prompt_sha` or `output_sha` provides no exemption. Only an exact structural
path and value already validated/generated by the native caller can avoid
an entropy false positive: the root input schema/suite identity and the
verified/generated regression hashes. The two long price-field names are
recognized only at their validated candidate positions. No payload parameter
can provide an exemption list or disable the policy.

Pattern detection is best effort and can both miss sensitive content and
refuse innocent high-entropy text. It does not prove anonymity, credential
validity or exhaustive secret absence. For example, the historical policy
does not recognize every short password. Omitted bundle mode deliberately
preserves the old raw report/failure behavior; its output is not silently
advertised as sanitized by this change.

## Provenance of the port

Preserved Apache-2.0 source functions are compared directly in tests:

- eval-dataset-builder `build`, commit `7bbef9d75115ccc406cc47554cc77e22300c1385`;
- prompt-package-manager `build_prompt_package` and rendering/schema helpers,
  commit `cff0de7a8a37d992d0079341955f79ca8801ce77`;
- benchmark-run-recorder `record_benchmark`, commit
  `c0bfff75d2237bb48b95efa3389fdb6b4c45ccdc`;
- multi-agent-failure-corpus `_redact`, commit
  `b541a772943d63d5a37a0dccf3d4631f843885f4`.

Commit associations come from the supplied consolidation matrix; exact copied
source bytes/hashes are recorded by the delivery manifest. Tests import these
preserved public functions as oracles. Production imports only the native
`promptbench` port, never a historical package or target repository code.
