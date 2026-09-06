"""Validate the explicit PromptOps candidate publication policy.

A prepared package version is not permission to publish it. The policy can be
``publish_enabled=false`` while a candidate is under review. In that state the
CI workflow must contain no release publisher at all. Re-enabling publication
therefore requires a reviewed policy + workflow change instead of inheriting an
old release decision.

The candidate supply-chain contract also requires a deterministic SPDX SBOM
workflow. Generating SBOM evidence does not authorize publication.
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
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EXPECTED_REPOSITORY = "vigilanty0x/promptops"
EXPECTED_DISTRIBUTION = "promptops-replay"
EXPECTED_REQUIRES = ["verify", "verify-consolidated-package", "attest-wheels"]
EXPECTED_ASSETS = {
    "canonical_wheel_count": 10,
    "canonical_wheel_python_source": "3.11",
    "include_sha256sums": True,
    "include_sigstore_provenance_bundle": True,
    "include_spdx_sbom": True,
    "include_release_receipt": True,
}


class ReleasePublishPolicyError(ValueError):
    """Raised when release publication metadata is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class ReleasePublishReceipt:
    version: str
    tag: str
    publish_enabled: bool
    required_jobs: int
    canonical_wheels: int
    release_note_lines: int
    spdx_sbom_required: bool


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


def _verify_sbom_workflow_contract(workflow: str) -> None:
    required_fragments = (
        "name: Candidate SPDX SBOM",
        "runs-on: ubuntu-24.04",
        "permissions:\n  contents: read",
        "scripts/generate_spdx_sbom.py",
        "--expected-count 10",
        "SBOM.spdx.json",
        "Verify SBOM against exact wheel subjects",
        "--verify",
        "name: promptops-candidate-sbom-${{ github.run_id }}",
    )
    for fragment in required_fragments:
        if fragment not in workflow:
            raise ReleasePublishPolicyError(
                f"candidate SBOM workflow is missing required fragment {fragment!r}"
            )
    forbidden = ("contents: write", "gh release create", "pull_request_target:")
    for fragment in forbidden:
        if fragment in workflow:
            raise ReleasePublishPolicyError(
                f"candidate SBOM workflow contains forbidden authority {fragment!r}"
            )


def _verify_workflow_contract(workflow: str, *, publish_enabled: bool) -> None:
    if publish_enabled:
        required_workflow_fragments = (
            "publish-release:",
            "needs: [verify, verify-consolidated-package, attest-wheels]",
            "github.event_name == 'push'",
            "github.ref == 'refs/heads/main'",
            "github.actor == github.repository_owner",
            "release-policy.v1.json",
            'pattern: "*-wheel-py3.11"',
            'name: wheel-provenance-${{ github.run_id }}',
            "SBOM.spdx.json",
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
        return

    forbidden = (
        "publish-release:",
        "gh release create",
        "contents: write",
    )
    for fragment in forbidden:
        if fragment in workflow:
            raise ReleasePublishPolicyError(
                f"publication is disabled but CI still contains release authority {fragment!r}"
            )


def validate_release_publish_policy(root: Path = ROOT) -> ReleasePublishReceipt:
    root = Path(root)
    policy = _load_json(root / POLICY_PATH.name)
    try:
        pyproject = tomllib.loads((root / PYPROJECT_PATH.name).read_text(encoding="utf-8"))
        changelog = (root / CHANGELOG_PATH.name).read_text(encoding="utf-8")
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        sbom_workflow = (root / ".github" / "workflows" / "sbom.yml").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleasePublishPolicyError("cannot read release publication inputs") from exc

    _require(policy.get("schema_version"), "1.0", "schema_version")
    _require(policy.get("repository"), EXPECTED_REPOSITORY, "repository")
    version = policy.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ReleasePublishPolicyError("version must be stable SemVer X.Y.Z")
    tag = policy.get("tag")
    _require(tag, f"v{version}", "tag")
    publish_enabled = policy.get("publish_enabled")
    if not isinstance(publish_enabled, bool):
        raise ReleasePublishPolicyError("publish_enabled must be boolean")

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ReleasePublishPolicyError("pyproject.toml [project] is missing")
    _require(project.get("name"), EXPECTED_DISTRIBUTION, "pyproject project.name")
    _require(project.get("version"), version, "pyproject project.version")

    exact = {
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
    for phrase in ("40 wheel-producing jobs", "SLSA provenance", "SPDX SBOM", f"`{tag}`"):
        if phrase not in note_text:
            raise ReleasePublishPolicyError(
                f"current release notes must describe candidate evidence: missing {phrase!r}"
            )
    if not publish_enabled and "publication disabled" not in note_text.lower():
        raise ReleasePublishPolicyError(
            "disabled candidate release notes must explicitly say publication disabled"
        )

    _verify_workflow_contract(workflow, publish_enabled=publish_enabled)
    _verify_sbom_workflow_contract(sbom_workflow)

    return ReleasePublishReceipt(
        version=version,
        tag=tag,
        publish_enabled=publish_enabled,
        required_jobs=len(EXPECTED_REQUIRES),
        canonical_wheels=EXPECTED_ASSETS["canonical_wheel_count"],
        release_note_lines=len(notes),
        spdx_sbom_required=EXPECTED_ASSETS["include_spdx_sbom"],
    )


def main() -> int:
    try:
        receipt = validate_release_publish_policy()
    except ReleasePublishPolicyError as exc:
        raise SystemExit(f"release publish policy gate: {exc}") from exc
    print(
        "release publish policy verified: "
        f"version={receipt.version} tag={receipt.tag} publish_enabled={str(receipt.publish_enabled).lower()} "
        f"required_jobs={receipt.required_jobs} canonical_wheels={receipt.canonical_wheels} "
        f"spdx_sbom_required={str(receipt.spdx_sbom_required).lower()} "
        f"release_note_lines={receipt.release_note_lines}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
