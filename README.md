# PromptBench

PromptBench is a deterministic, offline harness for comparing prompt/model candidates on the same versioned scenarios and limits. It reports pass rate, pass@1, score variance, tokens, latency, cost, recovery, and bounded diffs while preserving failures instead of showing only winning runs.

Version 0.1.0 uses versioned replay samples. That makes every example reproducible without a provider account, API key, network call, cache, or wall-clock dependency.

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
promptops release --version 0.5.0 --dataset datasets.json --scorecard scorecard.json --regression regression.json -o release.json
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

The mechanism was executed end-to-end on owner same-repository PR #25: ten canonical wheels were attested, all ten passed strict `gh attestation verify`, and the retained Sigstore bundle was downloaded and inspected. The bundle contains a SLSA v1 in-toto statement with the exact wheel subjects, workflow identity, PR merge ref, resolved git commit, and `github-hosted` runner environment. See [GitHub administration gates](docs/GITHUB-ADMIN-GATES.md) and `repository-governance.v1.json` for the recorded proof and the remaining server/human blockers.

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
python scripts/check_python_support.py
python scripts/check_build_backend.py
python scripts/check_workflow_security.py
python scripts/check_governance_manifest.py
python scripts/check_portfolio_compat.py
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m promptbench probe --level functional
python -m compileall -q src tests scripts
```

`check_release_metadata.py` fails closed when the root package version drifts between `pyproject.toml`, `promptbench.__version__`, the newest SemVer changelog entry, the current migration guide, or the README release example/link. `check_python_support.py` binds the root and nine historical `requires-python` declarations to the root classifiers and both explicit CI Python matrices. `check_build_backend.py` requires every root/historical `pyproject.toml` named by the portfolio manifest to use exactly `setuptools==83.0.0` and `setuptools.build_meta`. `check_workflow_security.py` keeps workflow-wide permissions read-only and permits elevated OIDC/attestation permissions only in the owner/same-repository guarded `attest-wheels` job; it also enforces bounded timeouts, immutable 40-hex action pins, non-persistent checkout credentials, and the matrix dependencies required before attestation. `check_governance_manifest.py` requires the executed signed-provenance proof to remain recorded while preserving branch protection and historical archival as blocked until their live server/human closure proofs exist. The general static checker parses every root `scripts/*.py` file so guard scripts are part of the public CI boundary too.

CI repeats the complete root and consolidated-package gates on Python 3.11 through 3.14: **4 root jobs + 36 historical-package jobs = 40 wheel-producer jobs**, followed by the signed-provenance job for owner/same-repository runs. Every producer builds its wheel twice under a fixed `SOURCE_DATE_EPOCH` and requires the two SHA-256 digests to be identical before continuing. The verified wheel is then installed into a fresh virtual environment and only after successful smoke verification uploaded as a uniquely named GitHub Actions artifact retained for 14 days. Historical wheel metadata/version/CLI checks are resolved from `portfolio-compatibility.v1.json`; the root wheel checks installed metadata against `promptbench.__version__` and runs a liveness probe. A backend-drifted, non-reproducible, broken, mismatched, unsigned-at-provenance-stage, or missing wheel therefore fails before the full evidence chain is considered green.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Suite and report schemas](docs/SCHEMA.md)
- [PromptOps evidence contracts](docs/PROMPTOPS.md)
- [Migration to 0.5](MIGRATION-0.5.md)
- [Portfolio compatibility/archive gate](docs/PORTFOLIO-COMPATIBILITY-AND-ARCHIVE-GATE.md)
- [GitHub administration gates](docs/GITHUB-ADMIN-GATES.md)
- [Methodology and limits](docs/METHODOLOGY.md)
- [Safety](docs/SAFETY.md)
- [Contributing](CONTRIBUTING.md)
- [AI assistance disclosure](AI_ASSISTANCE.md)

## License

Apache License 2.0.
