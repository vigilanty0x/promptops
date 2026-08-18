# PromptBench

PromptBench is a deterministic, offline harness for comparing prompt/model candidates on the same versioned scenarios and limits. It reports pass rate, pass@1, score variance, tokens, latency, cost, recovery, and bounded diffs while preserving failures instead of showing only winning runs.

The replay samples are versioned. That makes every example reproducible without a provider account, API key, network call, cache, or wall-clock dependency.

## Quick start

```bash
python -m pip install -e .
promptbench validate --suite examples/suite.json
promptbench run --suite examples/suite.json --output /tmp/promptbench-report.json
promptbench verify --report /tmp/promptbench-report.json
```

Run the fully synthetic demonstration:

```bash
promptbench demo --workspace /tmp/promptbench-demo
```

## PromptOps

The repository includes an offline PromptOps layer on top of verified PromptBench reports. It adds content-addressed scorecards, regression gates, deterministic multi-report jury consensus, versioned dataset manifests, bounded failure corpora, deterministic scorecard routing, stored-artifact verification, explicit release-bundle verification, and release evidence manifests.

```bash
promptops scorecard report.json -o scorecard.json
promptops failures report.json -o failures.json
promptops regress baseline.json current.json --pass-rate-drop 0.02 -o regression.json
promptops jury report-a.json report-b.json report-c.json -o jury.json
promptops datasets suite-v1.json suite-v2.json -o datasets.json
promptops verify scorecard.json --kind scorecard
promptops verify-bundle release.json --artifact datasets.json --artifact scorecard.json --artifact regression.json
promptops route scorecard.json --min-pass-rate 0.9 --max-latency-ms 500 --max-cost-microunits 10000 --fallbacks 1 -o route.json
promptops release --version 0.5.1 --dataset datasets.json --scorecard scorecard.json --regression regression.json -o release.json
```

`promptops verify` recomputes the stored artifact SHA and checks kind-specific internal invariants for `scorecard`, `regression`, `failure_corpus`, `jury_consensus`, `dataset_manifest`, `route_decision`, and `release_manifest`. A successful receipt reports integrity and contract verification while explicitly keeping `provenance=not-verified`; it does not claim a signature or remote attestation. For historical pre-0.3 release manifests that never recorded the later source-evidence-integrity field, the receipt reports `source_evidence_integrity=not-recorded` instead of inventing a newer guarantee.

`promptops verify-bundle` verifies a release manifest plus an explicit list of local dataset, scorecard, and regression artifacts. It does not scan directories or fetch remote evidence. Every supplied artifact must verify independently, the unique kind/SHA reference set must exactly match the release manifest, and the observed red-regression count must agree with the release gate. Repeated identical SHA references need only one local file, while their multiplicity remains significant for release counters. A coherent release whose quality gate is red is still a valid bundle and returns exit code `0` with `release_gate_passed=false`; missing, extra, duplicate-supplied, tampered, or contradictory evidence returns `2`.

`promptops route` verifies the scorecard SHA before making a decision. It preserves scorecard rank order, applies only the explicit quality/latency/cost/allowlist constraints supplied by the operator, and emits `decision=abstain` when no candidate satisfies them. It never calls a provider or guesses missing capabilities.

`promptops regress` returns exit code `3` when a configured quality, latency, or cost tolerance is breached. `promptops route` returns `3` on a valid abstention. `promptops release` returns `3` when supplied regression evidence is red. Invalid, tampered, contract-inconsistent, or bundle-inconsistent input returns exit code `2`.

The PromptOps layer does not call providers. It consumes versioned local JSON artifacts, verifies source evidence before use, preserves failed attempts, and emits its own SHA-256-bound evidence artifacts.

## Python support

The root package and all nine consolidated packages declare `requires-python >=3.11`. The current stable support gate runs the full root and package matrix on **CPython 3.11, 3.12, 3.13, and 3.14**. Root package classifiers advertise those four tested series. Future or pre-release Python series beyond 3.14 are not part of the CI guarantee until they are added to the explicit support contract and pass the same gates.

## Build reproducibility

All ten PEP 517 projects use the same exact build backend contract: `setuptools==83.0.0` with `setuptools.build_meta`. The pin is intentional: CI reproducibility must not silently change because a future setuptools release satisfies an open-ended minimum version. Every matrix job performs two independent wheel builds under a fixed `SOURCE_DATE_EPOCH` and requires identical SHA-256 output before clean-venv installation and evidence retention.

## Signed wheel provenance

After all **40** root/historical Python-matrix jobs succeed, an owner/same-repository guarded provenance job downloads the verified wheel artifacts, requires the four Python copies of each package wheel to be byte-identical, and reduces them to exactly **10 canonical wheel subjects**. Those wheels are signed with GitHub/Sigstore SLSA provenance.

The CI does not trust the attestation simply because it was created. Before retaining provenance evidence, it runs `gh attestation verify` for every canonical wheel and constrains verification to the expected repository, signer workflow, source ref, source commit digest, and GitHub-hosted runner policy. External fork PRs cannot execute the elevated attestation job. The Sigstore bundle, canonical `SHA256SUMS`, and a machine-readable provenance receipt are retained for 30 days.

The mechanism was first executed end-to-end on owner same-repository PR #25: ten canonical wheels were attested, all ten passed strict `gh attestation verify`, and the retained Sigstore bundle was downloaded and inspected.

## Candidate versus published release

The repository deliberately separates two machine-readable release roles:

- `release-policy.v1.json` is the **candidate/current publication authorization**. It currently authorizes the root package version `0.5.1` and tag `v0.5.1` after the complete build/provenance gate.
- `published-release.v1.json` is the **latest immutable publication already independently read back and verified**. During the 0.5.1 candidate PR it remains pinned to `v0.5.0`, so CI never pretends an unpublished candidate already exists.

This separation fixes the version-identity problem discovered after `v0.5.0`: source-owned CI, release-verification, and governance code changed after that immutable tag while the root package still declared `0.5.0`. The post-tag root wheel could therefore have been rebuilt under the same version with different bytes. The root package is now `0.5.1`, so new bytes have a new identity while `v0.5.0` remains immutable.

## Verified `v0.5.0` publication

The recorded latest independently verified publication is `v0.5.0`, bound to source commit `c8c6d133e86a119338edbc7b4e9142ce1c525fb5`. Its GitHub Release contains exactly **13 immutable uploaded assets**:

- ten canonical wheel files;
- `SHA256SUMS` for those ten wheels;
- `promptops-0.5.0-provenance.zip` containing the published GitHub/Sigstore SLSA evidence;
- `RELEASE-RECEIPT.json` binding repository, version, tag, source commit/ref, workflow run, wheel digests, checksum digest, and provenance-ZIP digest.

The first independent read-only verification, workflow run `32094998702`, reported:

`published release verified: version=0.5.0 tag=v0.5.0 source=c8c6d133e86a119338edbc7b4e9142ce1c525fb5 wheels=10 assets=13 attestation_id=41262298`

It then extracted the provenance ZIP and successfully re-ran `gh attestation verify` for all ten published wheels using `refs/heads/main`, the published source digest, the expected signer workflow, and the no-self-hosted-runner policy. The read-only workflow continues to verify the publication named by `published-release.v1.json` on every PR/push.

## 0.5.1 publication contract

`v0.5.1` can be created only from an owner push to `main`, after all 40 wheel-producer jobs and `attest-wheels` succeed. Publication keeps the same immutable 13-asset contract: ten canonical wheels, `SHA256SUMS`, deterministic provenance ZIP, and `RELEASE-RECEIPT.json`, followed by immediate download/readback and digest verification.

The publication writer never replaces an existing release. After `v0.5.1` is created, a separate read-only verification proof must succeed before `published-release.v1.json` and the governance evidence are advanced from `v0.5.0` to `v0.5.1`.

See [Release publication and verification](docs/RELEASE-PUBLICATION.md), [GitHub administration gates](docs/GITHUB-ADMIN-GATES.md), `release-policy.v1.json`, `published-release.v1.json`, and `repository-governance.v1.json` for the complete evidence chain.

## Fair comparison contract

- every candidate receives the same scenario version, order, repeat count, and output limit;
- the dataset contains explicit difficulty and expected results;
- response producers are separate from deterministic judges;
- errors, invalid output, mismatches, and later recovery remain in the report;
- ranking uses pass rate, then cost, mean latency, and candidate id;
- the report binds the full suite and result through SHA-256 evidence.

## Judges

The public harness includes three explicit rule-based judges:

- `exact` with optional case and whitespace normalization;
- `contains` for required bounded text;
- `json_equal` for parsed JSON equality independent of key order.

Judges return pass/fail, a numeric score, a reason, and a bounded diff. They never call the response producer or another model.

## Probes

```bash
promptbench probe --level liveness
promptbench probe --level readiness
promptbench probe --level functional
```

The functional probe contains a control that must pass and a counter-example that must fail. The probe succeeds only when both behaviors are observed and the failed records remain present.

## CI gate

`--minimum-pass-rate` returns exit code 3 when the best candidate is below a chosen threshold:

```bash
promptbench run --suite examples/suite.json --minimum-pass-rate 0.8
```

Operational input or schema errors use exit code 2; report verification failure uses exit code 4.

## Development

```bash
python scripts/check.py
python scripts/check_release_metadata.py
python scripts/check_release_publish_policy.py
python scripts/check_python_support.py
python scripts/check_build_backend.py
python scripts/check_workflow_security.py
python scripts/check_governance_manifest.py
python scripts/check_portfolio_compat.py
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m promptbench probe --level functional
python -m compileall -q src tests scripts
```

`check_release_metadata.py` fails closed when the root package version drifts between `pyproject.toml`, `promptbench.__version__`, the newest SemVer changelog entry, the current migration guide, or the README release example/link. `check_release_publish_policy.py` validates both the candidate authorization and the latest independently verified published record, prevents candidate rollback below that publication, and binds the candidate to the immutable release asset policy. `check_python_support.py` binds the root and nine historical `requires-python` declarations to the root classifiers and both explicit CI Python matrices. `check_build_backend.py` requires every root/historical `pyproject.toml` named by the portfolio manifest to use exactly `setuptools==83.0.0` and `setuptools.build_meta`. `check_workflow_security.py` keeps workflow-wide permissions read-only and permits elevated OIDC/attestation or release-write permissions only in their exact guarded jobs; it also enforces bounded timeouts, immutable 40-hex action pins, non-persistent checkout credentials, and required job dependencies. `check_governance_manifest.py` binds the executed published-main proof to `published-release.v1.json` instead of to a future candidate policy, while preserving branch protection and historical archival as blocked until their live server/human closure proofs exist. `verify_published_release.py` validates the exact publication named by `published-release.v1.json`; it is the offline half of the networked read-only release-verification workflow. The general static checker parses every root `scripts/*.py` file so guard scripts are part of the public CI boundary too.

CI repeats the complete root and consolidated-package gates on Python 3.11 through 3.14: **4 root jobs + 36 historical-package jobs = 40 wheel-producer jobs**, followed by the signed-provenance job for guarded owner/same-repository runs. Separately, the read-only published-release workflow downloads and verifies the immutable publication recorded in `published-release.v1.json`. Every producer builds its wheel twice under a fixed `SOURCE_DATE_EPOCH` and requires the two SHA-256 digests to be identical before continuing. The verified wheel is then installed into a fresh virtual environment and only after successful smoke verification uploaded as a uniquely named GitHub Actions artifact retained for 14 days. Historical wheel metadata/version/CLI checks are resolved from `portfolio-compatibility.v1.json`; the root wheel checks installed metadata against `promptbench.__version__` and runs a liveness probe. A backend-drifted, non-reproducible, broken, mismatched, unsigned-at-provenance-stage, missing, or post-publication-corrupted wheel therefore makes the corresponding evidence chain fail.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Suite and report schemas](docs/SCHEMA.md)
- [PromptOps evidence contracts](docs/PROMPTOPS.md)
- [Migration to 0.5](MIGRATION-0.5.md)
- [Portfolio compatibility/archive gate](docs/PORTFOLIO-COMPATIBILITY-AND-ARCHIVE-GATE.md)
- [Release publication and verification](docs/RELEASE-PUBLICATION.md)
- [GitHub administration gates](docs/GITHUB-ADMIN-GATES.md)
- [Methodology and limits](docs/METHODOLOGY.md)
- [Safety](docs/SAFETY.md)
- [Contributing](CONTRIBUTING.md)
- [AI assistance disclosure](AI_ASSISTANCE.md)

## License

Apache License 2.0.
