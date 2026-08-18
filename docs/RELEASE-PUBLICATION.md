# GitHub release publication

`release-policy.v1.json` is the explicit authorization boundary for automatic GitHub Release publication. A package version in `pyproject.toml` is not sufficient by itself.

## Current authorized release

- repository: `vigilanty0x/promptops`
- version: `0.5.0`
- tag: `v0.5.0`
- trigger: owner-authored push to `main`
- prerequisite jobs: `verify`, `verify-consolidated-package`, `attest-wheels`
- draft: false
- prerelease: false
- publication is one-time and immutable after creation

A later version must update the policy in review. The existing `0.5.0` authorization must never silently publish `0.6.0` or another version.

## Publication chain

1. Four root jobs and 36 consolidated-package jobs run on CPython 3.11-3.14.
2. Every producer builds its wheel twice and requires byte-identical SHA-256 output.
3. Every wheel is installed and checked in a clean virtual environment.
4. `attest-wheels` downloads all 40 retained wheels, proves they collapse to ten byte-identical canonical wheel names, generates GitHub/Sigstore SLSA provenance, and verifies all ten subjects with `gh attestation verify`.
5. Only on an owner push to `main`, `publish-release` runs after all three prerequisite job groups have succeeded.
6. If `v0.5.0` does not already exist, the publisher downloads the ten Python-3.11 wheel artifacts and the signed provenance artifact from the same workflow run.
7. The publisher verifies every wheel against the provenance `SHA256SUMS`, builds a deterministic provenance ZIP, writes `RELEASE-RECEIPT.json`, and creates the GitHub Release with all assets in one publication command.
8. The publisher then downloads the public release assets again and recomputes every recorded SHA-256. Publication is not considered successful merely because the create command returned zero.
9. If the release already exists, the job does not modify it. It only downloads and verifies the immutable published asset set.

## Expected immutable assets

A successful `v0.5.0` release contains exactly 13 uploaded assets:

- ten canonical `.whl` files;
- `SHA256SUMS` for those ten wheels;
- `promptops-0.5.0-provenance.zip` containing the GitHub/Sigstore provenance evidence from the publication workflow run;
- `RELEASE-RECEIPT.json` binding repository, version, tag, source commit, source ref, workflow run, wheel digests, checksum-file digest, and provenance-ZIP digest.

GitHub's automatically generated source archives are separate from these uploaded release assets.

## Consumer verification

After downloading the release assets, first verify the asset receipt and SHA-256 values. Then extract the provenance ZIP and verify an individual wheel with GitHub CLI using the repository and signer workflow constraints documented in `docs/GITHUB-ADMIN-GATES.md`.

The release receipt proves what bytes were published. The Sigstore/SLSA bundle proves the signed GitHub Actions provenance of the canonical wheel subjects. Neither should be substituted for the other.

## Failure handling

The publisher is deliberately fail-closed.

- If the build matrix fails, no provenance job runs and no release is published.
- If provenance generation or verification fails, no release is published.
- If the release policy drifts from `pyproject.toml`, the changelog, or the workflow contract, root CI fails before publication.
- If a release already exists, automation never replaces its assets.
- If first-time publication returns an error, inspect GitHub's release state before retrying. Do not delete a tag or published release merely to make CI green without reviewing whether external consumers may already have observed it.
- If a partially created release is ever observed, treat it as a release incident: compare its uploaded asset set with the expected 13 files and the source run before deciding whether any corrective mutation is appropriate.

## Server-side limits

This release workflow does not replace branch protection. `repository-governance.v1.json` remains the source of truth for the separate `main` protection blocker. The publisher's owner-only guard reduces exposure while that GitHub server-side setting remains unavailable to this session's connector.
