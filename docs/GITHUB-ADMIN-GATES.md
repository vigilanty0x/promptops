# GitHub administration gates

This document records repository-level gates that cannot honestly be closed by source-code changes alone, plus the signed-provenance control that was originally blocked but has now been implemented and independently verified inside CI.

The repository-owned CI, package, artifact, compatibility, reproducibility, and provenance work is fail-closed. A blocked item must not be described as completed merely because the source tree is green.

## 1. Protect `main`

**Observed state on 2026-08-18:** GitHub's `branches/main` API reported `protected=false`, protection disabled, and no required status checks.

**Target state:**

- changes to `main` go through a pull request;
- the CI workflow must succeed before merge;
- force-push to `main` is disabled;
- deletion of `main` is disabled;
- the protection applies to repository administrators as well, where the selected GitHub ruleset model supports it.

**Why this remains blocked here:** the connected GitHub tool can read branch state and mutate repository contents/PRs, but it exposes no branch-protection or repository-ruleset write action. No compatible installable plugin was available during the 2026-08-18 audit. The setting therefore was not fabricated through repository files.

**Closure proof:** re-read GitHub server state and require `main` to report protection/rules enabled with the CI requirement active.

## 2. Signed wheel provenance — implemented and verified

The CI first produces 40 wheel artifacts: ten package identities across CPython 3.11, 3.12, 3.13, and 3.14. Every producer job runs tests, reproducible double builds, clean-virtual-environment installation, and package/CLI contract checks before upload.

The `attest-wheels` job then runs only after both producer matrices succeed. For pull requests, its elevated OIDC/attestation permissions are restricted to owner-operated same-repository PRs. External fork PRs cannot execute the attestation path. Main pushes use the same provenance job.

The provenance job:

1. downloads all 40 verified wheel artifacts with artifact-digest mismatch configured as an error;
2. requires exactly 40 wheels and groups them into exactly ten canonical wheel names;
3. requires the four Python-matrix copies of each canonical wheel to be byte-identical;
4. signs the ten canonical wheels with GitHub artifact attestation / Sigstore SLSA provenance;
5. verifies each signed wheel using `gh attestation verify`, requiring the expected repository, signer workflow, source ref, source commit digest, and GitHub-hosted runner policy;
6. retains the Sigstore bundle, `SHA256SUMS`, and a provenance receipt as a separate Actions artifact.

### Executed verification proof

Owner same-repository PR #25 produced an end-to-end verified attestation:

- workflow run: `32091517015`;
- event: `pull_request`;
- source ref: `refs/pull/25/merge`;
- source git commit: `336ed6c2290ff28af0e127b3aa6378b33898ef8f`;
- runner: `github-hosted`;
- canonical subjects: 10 wheels;
- GitHub attestation id: `41255136`;
- retained provenance artifact id: `9308496511`;
- retained artifact digest: `sha256:991659a6086eb65167870d51b5b8a0df7cb5a52e81dfa4bec87af24c1fc2729e`;
- Sigstore bundle media type: `application/vnd.dev.sigstore.bundle.v0.3+json`;
- predicate type: `https://slsa.dev/provenance/v1`;
- local policy verification: all ten subjects passed `gh attestation verify`.

The downloaded Sigstore bundle was inspected after the run. Its in-toto statement contains the ten exact wheel subjects and their SHA-256 digests, a SLSA v1 provenance predicate, the expected workflow path, `pull_request` event, `github-hosted` runner environment, and the resolved git dependency at the source commit above.

**Remaining tooling limitation:** the connector used in this session does not expose a reliable listing/readback endpoint for the subsequent `main` push run. The main-push provenance path is configured identically, but this document does not claim observation of a post-merge push attestation that the tool could not read.

**Consumer verification rule:** do not trust an attestation merely because it exists. Verification must constrain repository, signer workflow, source ref/digest, and runner policy.

## 3. Historical source-repository archival

Nine historical repositories were consolidated under `packages/` and received canonical-development redirects. Their compatibility, consumer scan, redirect evidence, rollback documentation, CI, wheel builds, installed-wheel contracts, and canonical wheel provenance have been verified.

Archival remains intentionally blocked. `portfolio-compatibility.v1.json` records `human_archive_approval=false` and `archive_ready=false` for every source repository.

No archive/delete action may be taken until explicit human approval is recorded. The absence of visible exact GitHub URL consumers is not proof that no private/local/external consumer exists.

**Closure proof:** explicit human approval plus a fresh portfolio compatibility check showing every required archive-policy field true for the selected repositories.

## Current source-owned evidence

The repository currently enforces source-owned contracts for:

- release metadata consistency;
- tested Python 3.11–3.14 support;
- exact PEP 517 build-backend pinning;
- GitHub workflow security policy;
- portfolio compatibility and archive policy;
- full root and historical-package tests;
- deterministic double wheel builds under a fixed `SOURCE_DATE_EPOCH`;
- clean-venv wheel installation and CLI/metadata checks;
- retained GitHub Actions wheel evidence;
- owner/same-repository guarded signed SLSA provenance for ten canonical wheels;
- strict local provenance verification before provenance evidence is retained.

Those controls reduce the amount of trust placed on repository convention. They still do **not** replace GitHub server-side branch protection or explicit human archive approval.

## Machine-readable register

`repository-governance.v1.json` records branch protection and historical archival as blocked, while recording signed artifact provenance as implemented with its executed verification proof. `scripts/check_governance_manifest.py` makes that distinction fail-closed so a future handoff cannot silently turn an unverified server/human blocker into a green source-code claim or erase the executed provenance proof.
