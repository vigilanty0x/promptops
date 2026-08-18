# GitHub release publication

PromptOps deliberately separates **candidate preparation** from **published release truth**.

- `release-policy.v1.json` describes the next candidate and whether publication is authorized.
- `published-release.v1.json` pins the independently verified release that actually exists.
- A package version in `pyproject.toml`, successful CI, or signed provenance is never sufficient by itself to claim publication.

## Prepared candidate

Current candidate:

- repository: `vigilanty0x/promptops`
- distribution: `promptops-replay`
- version: `0.6.0`
- proposed tag: `v0.6.0`
- `publish_enabled`: **false**
- prerequisite evidence groups: `verify`, `verify-consolidated-package`, `attest-wheels`
- rollback: verified published `v0.5.0`

Because publication is disabled, `.github/workflows/ci.yml` contains **no** `publish-release` job, no release `contents: write` permission, and no `gh release create` command. `scripts/check_release_publish_policy.py` fails if any of those authorities reappear while the policy remains disabled.

The candidate can still produce and verify signed wheel provenance. That proves the candidate bytes came from the expected GitHub Actions workflow and source SHA; it does not authorize a public release.

## Published release

The independently pinned published release remains:

- version: `0.5.0`
- tag: `v0.5.0`
- source: `c8c6d133e86a119338edbc7b4e9142ce1c525fb5`
- status: `VERIFIED_PUBLISHED`
- verification workflow: `.github/workflows/release-verify.yml`
- first verification run: `32094998702`

The read-only published-release workflow loads `published-release.v1.json`, not the 0.6 candidate policy. A new candidate therefore cannot silently redefine which historical release is considered published.

## Candidate evidence chain

1. Four root jobs and 36 consolidated-package jobs run on CPython 3.11-3.14.
2. Every producer builds its wheel twice and requires byte-identical SHA-256 output.
3. Every wheel is installed and checked in a clean virtual environment.
4. The root wheel must install as `promptops-replay` and expose canonical `promptops` plus legacy `promptbench` namespaces and CLIs at one version.
5. `attest-wheels` downloads all 40 retained wheels, proves they collapse to ten byte-identical canonical wheel names, generates GitHub/Sigstore SLSA provenance, and verifies all ten subjects with `gh attestation verify`.
6. With `publish_enabled=false`, the chain stops there. There is no publication step.

## Historical `v0.5.0` immutable assets

The published `v0.5.0` release contains exactly 13 uploaded assets:

- ten canonical `.whl` files;
- `SHA256SUMS` for those ten wheels;
- `promptops-0.5.0-provenance.zip` containing the GitHub/Sigstore provenance evidence from the publication workflow run;
- `RELEASE-RECEIPT.json` binding repository, version, tag, source commit, source ref, workflow run, wheel digests, checksum-file digest, and provenance-ZIP digest.

GitHub's automatically generated source archives are separate from these uploaded release assets.

## Consumer verification

The read-only verifier downloads the pinned published release, resolves its tag, verifies the source commit signature, recomputes the immutable asset contract, extracts the provenance bundle, and re-runs `gh attestation verify` for every published wheel.

The release receipt proves what bytes were published. The Sigstore/SLSA bundle proves the signed GitHub Actions provenance of the canonical wheel subjects. Neither should be substituted for the other.

## Re-authorizing a future publication

Publishing `v0.6.0` requires a separate reviewed change. At minimum it must:

1. switch `release-policy.v1.json` to `publish_enabled=true` for exactly `0.6.0` / `v0.6.0`;
2. restore an owner/main-only publisher after the 40 producer jobs and `attest-wheels`;
3. confine `contents: write` to that publisher job;
4. preserve one-time immutable asset semantics and read-back verification;
5. retain the rollback contract to `v0.5.0` until the new release is independently verified;
6. after successful publication, update `published-release.v1.json` only with observed release/tag/source evidence.

Until those steps happen, `PREPARED` must never be reported as `RELEASED`.

## Failure handling

- If the build matrix fails, no provenance is accepted.
- If provenance generation or verification fails, the candidate remains blocked.
- If a disabled policy coexists with release-write authority, CI fails closed.
- If candidate identity/version drifts from `pyproject.toml`, canonical/legacy namespaces, changelog, migration guide or README, root CI fails.
- If the pinned published release drifts, the read-only verifier fails independently of candidate status.
- Never delete a tag or published release merely to make CI green without reviewing whether external consumers may already have observed it.
- Any partially created release is a release incident and must be compared with the expected immutable asset/source contract before corrective mutation.

## Server-side limits

Release workflows do not replace branch protection. `repository-governance.v1.json` remains the source of truth for the separate `main` protection blocker. Historical source-repository archival also remains blocked until explicit human approval is recorded.
