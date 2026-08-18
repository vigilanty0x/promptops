# GitHub administration gates

This document records repository-level gates that cannot honestly be closed by source-code changes alone, plus the signed-provenance and release controls that were originally blocked but have now been implemented and independently verified.

The repository-owned CI, package, artifact, compatibility, reproducibility, provenance, and published-release verification work is fail-closed. A blocked item must not be described as completed merely because the source tree is green.

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

## 2. Signed wheel provenance and published release — implemented and verified

The CI produces 40 wheel artifacts: ten package identities across CPython 3.11, 3.12, 3.13, and 3.14. Every producer job runs tests, reproducible double builds, clean-virtual-environment installation, and package/CLI contract checks before upload.

The `attest-wheels` job runs only after both producer matrices succeed. For pull requests, its elevated OIDC/attestation permissions are restricted to owner-operated same-repository PRs. External fork PRs cannot execute the attestation path. The main-push path is restricted to `refs/heads/main` and the repository owner.

The provenance job:

1. downloads all 40 verified wheel artifacts with artifact-digest mismatch configured as an error;
2. requires exactly 40 wheels and groups them into exactly ten canonical wheel names;
3. requires the four Python-matrix copies of each canonical wheel to be byte-identical;
4. signs the ten canonical wheels with GitHub artifact attestation / Sigstore SLSA provenance;
5. verifies each signed wheel using `gh attestation verify`, requiring the expected repository, signer workflow, source ref, source commit digest, and GitHub-hosted runner policy;
6. retains the Sigstore bundle, `SHA256SUMS`, and a provenance receipt as a separate Actions artifact.

### Owner same-repository PR proof

PR #25 produced the first end-to-end verified attestation:

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

The downloaded Sigstore bundle was inspected after the run. Its in-toto statement contains the ten exact wheel subjects and their SHA-256 digests, a SLSA v1 provenance predicate, the expected workflow path, PR merge ref, resolved git commit, and `github-hosted` runner environment.

### Main-push and immutable GitHub Release proof

The main-push path is no longer only configured; it has been independently read back through the published `v0.5.0` GitHub Release.

Publication source and tag:

- published version: `0.5.0`;
- tag: `v0.5.0`;
- source ref: `refs/heads/main`;
- source git commit: `c8c6d133e86a119338edbc7b4e9142ce1c525fb5`;
- the live tag resolved to that exact commit;
- the source commit's GitHub signature verification was true.

Independent release-verification proof:

- verification workflow: `.github/workflows/release-verify.yml`;
- verification run: `32094998702`;
- verification PR: #27;
- verification token permissions: `contents: read`, `metadata: read`;
- uploaded release assets: exactly 13;
- canonical wheel assets: exactly 10;
- published main-push attestation id: `41262298`;
- release receipt source digest: `c8c6d133e86a119338edbc7b4e9142ce1c525fb5`;
- every published wheel SHA-256 matched `RELEASE-RECEIPT.json` and `SHA256SUMS`;
- the deterministic provenance ZIP digest matched the release receipt;
- the embedded provenance receipt recorded event `push`, ref `refs/heads/main`, the same source digest, `github-hosted`, ten subjects, and prior successful `gh` verification;
- the published Sigstore bundle was extracted from the release and all ten downloaded wheel assets passed `gh attestation verify` again with repository, signer workflow, source ref, source digest, and no-self-hosted-runner constraints.

The successful read-only job emitted:

`published release verified: version=0.5.0 tag=v0.5.0 source=c8c6d133e86a119338edbc7b4e9142ce1c525fb5 wheels=10 assets=13 attestation_id=41262298`

followed by:

`published release provenance verified for 10 canonical wheels`

The release verifier is intentionally a separate read-only workflow from the write-capable publisher. It runs on future PRs and pushes, so deletion, replacement, corruption, tag drift, receipt drift, or failed provenance verification turns the verification workflow red rather than silently trusting publication history.

**Consumer verification rule:** do not trust an attestation or release merely because it exists. Verification must constrain repository, signer workflow, source ref/digest, runner policy, and the immutable release receipt/checksum set.

## 3. Historical source-repository archival

Nine historical repositories were consolidated under `packages/` and received canonical-development redirects. Their compatibility, consumer scan, redirect evidence, rollback documentation, CI, wheel builds, installed-wheel contracts, canonical wheel provenance, and published canonical release evidence have been verified.

Archival remains intentionally blocked. `portfolio-compatibility.v1.json` records `human_archive_approval=false` and `archive_ready=false` for every source repository.

No archive/delete action may be taken until explicit human approval is recorded. The absence of visible exact GitHub URL consumers is not proof that no private/local/external consumer exists.

**Closure proof:** explicit human approval plus a fresh portfolio compatibility check showing every required archive-policy field true for the selected repositories.

## Current source-owned evidence

The repository currently enforces source-owned contracts for:

- release metadata consistency;
- explicit one-version GitHub Release publication policy;
- tested Python 3.11–3.14 support;
- exact PEP 517 build-backend pinning;
- GitHub workflow security policy;
- portfolio compatibility and archive policy;
- full root and historical-package tests;
- deterministic double wheel builds under a fixed `SOURCE_DATE_EPOCH`;
- clean-venv wheel installation and CLI/metadata checks;
- retained GitHub Actions wheel evidence;
- owner/same-repository guarded signed SLSA provenance for ten canonical wheels;
- strict provenance verification before provenance evidence is retained;
- immutable `v0.5.0` publication with ten wheels, `SHA256SUMS`, provenance ZIP, and `RELEASE-RECEIPT.json`;
- continuous read-only verification of the published release's exact asset set, hashes, tag target, commit signature, and ten wheel attestations.

Those controls reduce the amount of trust placed on repository convention. They still do **not** replace GitHub server-side branch protection or explicit human archive approval.

## Machine-readable register

`repository-governance.v1.json` records branch protection and historical archival as blocked, while recording signed artifact provenance and the published main release as implemented with executed verification proofs. `scripts/check_governance_manifest.py` cross-checks the published version/tag against `release-policy.v1.json` and makes the distinction fail-closed so a future handoff cannot silently turn an unverified server/human blocker into a green source-code claim or erase the executed provenance/release proof.
