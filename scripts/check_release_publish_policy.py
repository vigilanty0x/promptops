"""Validate the explicit GitHub release publication policy.

`release-policy.v1.json` is the next/current publication authorization, while
`published-release.v1.json` records the latest immutable release that has already
been independently read back and verified.  Keeping those roles separate lets a
release PR prepare N+1 without pretending N+1 is already public.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "release-policy.v1.json"
PUBLISHED_PATH = ROOT / "published-release.v1.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EXPECTED_REPOSITORY = "vigilanty0x/promptops"
EXPECTED_REQUIRES = ["verify", "verify-consolidated-package", "attest-wheels"]
EXPECTED_ASSETS = {
    "canonical_wheel_count": 10,
    "canonical_wheel_python_source": "3.11",
    "include_sha256sums": True,
    "include_sigstore_provenance_bundle": True,
    "include_release_receipt": True,
}


class ReleasePublishPolicyError(ValueError):
    """Raised when release publication metadata is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class ReleasePublishReceipt:
    version: str
    tag: str
    latest_verified_version: str
    latest_verified_tag: str
    required_jobs: int
    canonical_wheels: int
    release_note_lines: int


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise ReleasePublishPolicyError(f"required file is missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleasePublishPolicyError(f"cannot parse {path.name}") from exc
    if not isinstance(value, dict):
        raise ReleasePublishPolicyError(f"{path.name} root must be an object")
    return value


def _require(value: object, expected: object, field: str) -> None:
    if value != expected:
        raise ReleasePublishPolicyError(f"{field} must equal {expected!r}; got {value!r}")


def _version_tuple(value: object, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or SEMVER.fullmatch(value) is None:
        raise ReleasePublishPolicyError(f"{field} must be stable SemVer X.Y.Z")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _release_notes(changelog: str, version: str) -> list[str]:
    lines = changelog.splitlines()
    header = re.compile(rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$")
    starts = [index for index, line in enumerate(lines) if header.fullmatch(line)]
    if len(starts) != 1:
        raise ReleasePublishPolicyError(
            f"CHANGELOG.md must contain exactly one dated section for {version}; found {len(starts)}"
        )
    start = starts[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    notes = [line for line in lines[start:end] if line.strip()]
    if not notes:
        raise ReleasePublishPolicyError(f"CHANGELOG.md release notes for {version} are empty")
    return notes


def _validate_published_record(record: dict) -> tuple[str, str, tuple[int, int, int]]:
    _require(record.get("schema_version"), "1.0", "published-release schema_version")
    _require(record.get("repository"), EXPECTED_REPOSITORY, "published-release repository")
    version = record.get("version")
    version_tuple = _version_tuple(version, "published-release version")
    tag = record.get("tag")
    _require(tag, f"v{version}", "published-release tag")
    _require(record.get("source_ref"), "refs/heads/main", "published-release source_ref")
    source_digest = record.get("source_digest")
    if not isinstance(source_digest, str) or re.fullmatch(r"[0-9a-f]{40}", source_digest) is None:
        raise ReleasePublishPolicyError("published-release source_digest must be lowercase 40-hex")
    _require(record.get("release_asset_count"), 13, "published-release release_asset_count")
    _require(record.get("canonical_wheel_count"), 10, "published-release canonical_wheel_count")
    attestation_id = record.get("attestation_id")
    if not isinstance(attestation_id, str) or not attestation_id.isdigit():
        raise ReleasePublishPolicyError("published-release attestation_id must be numeric text")
    for field in (
        "source_commit_signature_verified",
        "release_integrity_verified",
        "wheel_provenance_verified",
        "immutable",
    ):
        _require(record.get(field), True, f"published-release {field}")
    return version, tag, version_tuple


def validate_release_publish_policy(root: Path = ROOT) -> ReleasePublishReceipt:
    root = Path(root)
    policy = _load_json(root / POLICY_PATH.name)
    published = _load_json(root / PUBLISHED_PATH.name)
    try:
        pyproject = tomllib.loads((root / PYPROJECT_PATH.name).read_text(encoding="utf-8"))
        changelog = (root / CHANGELOG_PATH.name).read_text(encoding="utf-8")
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleasePublishPolicyError("cannot read release publication inputs") from exc

    _require(policy.get("schema_version"), "1.0", "schema_version")
    _require(policy.get("repository"), EXPECTED_REPOSITORY, "repository")
    version = policy.get("version")
    version_tuple = _version_tuple(version, "version")
    tag = policy.get("tag")
    _require(tag, f"v{version}", "tag")

    latest_version, latest_tag, latest_tuple = _validate_published_record(published)
    if version_tuple < latest_tuple:
        raise ReleasePublishPolicyError(
            f"candidate version {version} must not be older than latest verified release {latest_version}"
        )
    if version_tuple == latest_tuple and tag != latest_tag:
        raise ReleasePublishPolicyError(
            "candidate at the latest verified version must use the exact verified tag"
        )

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ReleasePublishPolicyError("pyproject.toml [project] is missing")
    _require(project.get("version"), version, "pyproject project.version")

    exact = {
        "publish_enabled": True,
        "publish_event": "push",
        "publish_branch": "main",
        "publisher": "repository-owner",
        "requires_jobs": EXPECTED_REQUIRES,
        "release_notes_source": "CHANGELOG.md",
        "draft": False,
        "prerelease": False,
        "idempotent": True,
        "publish_once_per_version": True,
        "assets": EXPECTED_ASSETS,
    }
    for field, expected in exact.items():
        _require(policy.get(field), expected, field)

    notes = _release_notes(changelog, version)
    note_text = "\n".join(notes)
    if "20-job CI matrix" in note_text:
        raise ReleasePublishPolicyError(
            "current release notes still describe the obsolete 20-job CI matrix"
        )
    for phrase in ("40 wheel-producing jobs", "SLSA provenance", f"`{tag}`"):
        if phrase not in note_text:
            raise ReleasePublishPolicyError(
                f"current release notes must describe final release evidence: missing {phrase!r}"
            )

    required_workflow_fragments = (
        "publish-release:",
        "needs: [verify, verify-consolidated-package, attest-wheels]",
        "github.event_name == 'push'",
        "github.ref == 'refs/heads/main'",
        "github.actor == github.repository_owner",
        "release-policy.v1.json",
        'pattern: "*-wheel-py3.11"',
        'name: wheel-provenance-${{ github.run_id }}',
        "gh release create",
        "gh release view",
        "gh release download",
        "RELEASE-RECEIPT.json",
        'find /tmp/release-wheels -maxdepth 1 -name \'*.whl\' | wc -l',
    )
    for fragment in required_workflow_fragments:
        if fragment not in workflow:
            raise ReleasePublishPolicyError(
                f"CI release publisher is missing required fragment {fragment!r}"
            )

    return ReleasePublishReceipt(
        version=version,
        tag=tag,
        latest_verified_version=latest_version,
        latest_verified_tag=latest_tag,
        required_jobs=len(EXPECTED_REQUIRES),
        canonical_wheels=EXPECTED_ASSETS["canonical_wheel_count"],
        release_note_lines=len(notes),
    )


def main() -> int:
    try:
        receipt = validate_release_publish_policy()
    except ReleasePublishPolicyError as exc:
        raise SystemExit(f"release publish policy gate: {exc}") from exc
    print(
        "release publish policy verified: "
        f"candidate={receipt.version}@{receipt.tag} "
        f"latest_verified={receipt.latest_verified_version}@{receipt.latest_verified_tag} "
        f"required_jobs={receipt.required_jobs} canonical_wheels={receipt.canonical_wheels} "
        f"release_note_lines={receipt.release_note_lines}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
