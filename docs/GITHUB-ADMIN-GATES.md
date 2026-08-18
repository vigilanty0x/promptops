# GitHub administration gates

This document records repository-level gates that cannot honestly be closed by source-code changes alone.

The repository-owned CI, package, artifact, compatibility, and reproducibility work is fail-closed. The items below depend on GitHub server administration, external attestation readback, or explicit human approval. A blocked item must not be described as completed merely because the source tree is green.

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

## 2. Signed artifact provenance

The CI retains verified wheel artifacts after source tests, metadata gates, build-backend checks, reproducible double builds, and clean-virtual-environment smoke tests.

GitHub supports artifact attestations and signed provenance, but this session deliberately did **not** grant extra attestation/OIDC write permissions because the available connector could not read back the repository attestation endpoint needed for an independent post-write verification.

**Target state:** retained release artifacts have signed provenance that can be independently read and verified against the expected repository/workflow/commit.

**Closure proof:** produce an attestation, read it back through a supported verifier, and verify the subject digest and repository/workflow identity. Merely adding an attestation step to YAML is not sufficient proof.

## 3. Historical source-repository archival

Nine historical repositories were consolidated under `packages/` and received canonical-development redirects. Their compatibility, consumer scan, redirect evidence, rollback documentation, CI, wheel builds, and installed-wheel contracts have been verified.

Archival remains intentionally blocked. `portfolio-compatibility.v1.json` records `human_archive_approval=false` and `archive_ready=false` for every source repository.

No archive/delete action may be taken until explicit human approval is recorded. The absence of visible exact GitHub URL consumers is not proof that no private/local/external consumer exists.

**Closure proof:** explicit human approval plus a fresh portfolio compatibility check showing every required archive-policy field true for the selected repositories.

## Current source-owned evidence

The repository currently enforces source-owned contracts for:

- release metadata consistency;
- tested Python support;
- exact PEP 517 build-backend pinning;
- GitHub workflow security policy;
- portfolio compatibility and archive policy;
- full root and historical-package tests;
- deterministic double wheel builds under a fixed `SOURCE_DATE_EPOCH`;
- clean-venv wheel installation and CLI/metadata checks;
- retained GitHub Actions wheel evidence.

Those controls reduce the amount of trust placed on repository convention. They do **not** replace GitHub server-side branch protection, signed provenance, or human approval.

## Machine-readable register

`repository-governance.v1.json` mirrors these three external gates using explicit blocked status values and closure conditions. It exists to prevent handoffs or future automation from silently turning an external blocker into a green source-code claim.
