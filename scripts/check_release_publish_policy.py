"""Validate the explicit GitHub release publication policy.

The policy intentionally separates a prepared package version from permission to
publish a GitHub Release. A future version bump therefore cannot silently reuse
an old automatic publication decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "release-policy.v1.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EXPECTED_REPOSITORY = "vigilanty0x/promptops"
EXPECTED_REQUIRES = ["verify", "verify-consolidated-package", "attest-wheels"]


class ReleasePublishPolicyError(ValueError):
    """Raised when release publication metadata is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class ReleasePublishReceipt:
    version: str
    tag: str
    required_jobs: int
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


def validate_release_publish_policy(root: Path = ROOT) -> ReleasePublishReceipt:
    root = Path(root)
    policy = _load_json(root / POLICY_PATH.name)
    try:
        pyproject = tomllib.loads((root / PYPROJECT_PATH.name).read_text(encoding="utf-8"))
        changelog = (root / CHANGELOG_PATH.name).read_text(encoding="utf-8")
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleasePublishPolicyError("cannot read release publication inputs") from exc

    _require(policy.get("schema_version"), "1.0", "schema_version")
    _require(policy.get("repository"), EXPECTED_REPOSITORY, "repository")
    version = policy.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ReleasePublishPolicyError("version must be stable SemVer X.Y.Z")
    tag = policy.get("tag")
    _require(tag, f"v{version}", "tag")

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
    }
    for field, expected in exact.items():
        _require(policy.get(field), expected, field)

    notes = _release_notes(changelog, version)
    if "20-job CI matrix" in "\n".join(notes):
        raise ReleasePublishPolicyError(
            "current release notes still describe the obsolete 20-job CI matrix"
        )

    required_workflow_fragments = (
        "publish-release:",
        "needs: [verify, verify-consolidated-package, attest-wheels]",
        "github.event_name == 'push'",
        "github.ref == 'refs/heads/main'",
        "github.actor == github.repository_owner",
        "release-policy.v1.json",
        "gh release create",
        "gh release view",
    )
    for fragment in required_workflow_fragments:
        if fragment not in workflow:
            raise ReleasePublishPolicyError(
                f"CI release publisher is missing required fragment {fragment!r}"
            )

    return ReleasePublishReceipt(
        version=version,
        tag=tag,
        required_jobs=len(EXPECTED_REQUIRES),
        release_note_lines=len(notes),
    )


def main() -> int:
    try:
        receipt = validate_release_publish_policy()
    except ReleasePublishPolicyError as exc:
        raise SystemExit(f"release publish policy gate: {exc}") from exc
    print(
        "release publish policy verified: "
        f"version={receipt.version} tag={receipt.tag} "
        f"required_jobs={receipt.required_jobs} release_note_lines={receipt.release_note_lines}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
