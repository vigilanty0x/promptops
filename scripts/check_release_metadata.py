"""Fail-closed consistency gate for PromptOps root release metadata.

PromptOps 0.6 separates the canonical product identity from legacy PromptBench
compatibility. The distribution, canonical Python namespace, legacy namespace,
CLIs, changelog, migration guide, and README must all describe one versioned
product without silently dropping existing consumers.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_HEADING = re.compile(
    r"^##\s+((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\s+-\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
CANONICAL_DISTRIBUTION = "promptops-replay"
LEGACY_DISTRIBUTION = "promptbench-replay"


class ReleaseMetadataError(ValueError):
    """A release identity or version surface is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    version: str
    major_minor: str
    changelog_date: str
    migration_path: str
    distribution: str
    canonical_namespace: str
    legacy_namespace: str


def _read(path: Path) -> str:
    if not path.is_file():
        raise ReleaseMetadataError(f"required release metadata file is missing: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseMetadataError(f"cannot read release metadata file: {path.name}") from exc


def _pyproject_version(root: Path) -> str:
    path = root / "pyproject.toml"
    try:
        data = tomllib.loads(_read(path))
    except tomllib.TOMLDecodeError as exc:
        raise ReleaseMetadataError("pyproject.toml is invalid TOML") from exc
    project = data.get("project")
    if not isinstance(project, dict):
        raise ReleaseMetadataError("pyproject.toml must contain [project]")
    if project.get("name") != CANONICAL_DISTRIBUTION:
        raise ReleaseMetadataError(
            f"root project name must be {CANONICAL_DISTRIBUTION}; "
            f"{LEGACY_DISTRIBUTION} is a legacy 0.5 distribution identity"
        )
    description = project.get("description")
    if not isinstance(description, str) or not description.startswith("PromptOps:"):
        raise ReleaseMetadataError("root project description must identify PromptOps")
    version = project.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ReleaseMetadataError("[project].version must be a plain SemVer X.Y.Z")
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        raise ReleaseMetadataError("pyproject.toml must contain [project.scripts]")
    expected_scripts = {
        "promptops": "promptbench.ops_cli:main",
        "promptbench": "promptbench.cli:main",
    }
    if scripts != expected_scripts:
        raise ReleaseMetadataError(
            "console scripts must expose canonical promptops plus legacy promptbench compatibility"
        )
    return version


def _literal_version(path: Path, *, label: str) -> str:
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError as exc:
        raise ReleaseMetadataError(f"{label} is invalid Python") from exc
    values: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
        else:
            raise ReleaseMetadataError(f"{label} __version__ must be a literal string")
    if len(values) != 1:
        raise ReleaseMetadataError(f"{label} must define __version__ exactly once")
    if SEMVER.fullmatch(values[0]) is None:
        raise ReleaseMetadataError(f"{label} __version__ must be plain SemVer X.Y.Z")
    return values[0]


def _runtime_versions(root: Path) -> tuple[str, str]:
    canonical = _literal_version(
        root / "src" / "promptops" / "__init__.py",
        label="src/promptops/__init__.py",
    )
    legacy = _literal_version(
        root / "src" / "promptbench" / "__init__.py",
        label="src/promptbench/__init__.py",
    )
    return canonical, legacy


def _latest_changelog(root: Path) -> tuple[str, str]:
    text = _read(root / "CHANGELOG.md")
    matches = list(CHANGELOG_HEADING.finditer(text))
    if not matches:
        raise ReleaseMetadataError("CHANGELOG.md has no SemVer release heading")
    first = matches[0]
    version = first.group(1)
    released = first.group(2)
    try:
        date.fromisoformat(released)
    except ValueError as exc:
        raise ReleaseMetadataError("latest changelog date must be a valid ISO date") from exc
    return version, released


def validate_release_metadata(root: Path = ROOT) -> ReleaseMetadata:
    """Validate canonical PromptOps identity and compatibility surfaces."""

    root = Path(root)
    version = _pyproject_version(root)
    canonical_runtime, legacy_runtime = _runtime_versions(root)
    if canonical_runtime != version:
        raise ReleaseMetadataError(
            f"canonical promptops __version__ {canonical_runtime} does not match pyproject version {version}"
        )
    if legacy_runtime != version:
        raise ReleaseMetadataError(
            f"legacy promptbench __version__ {legacy_runtime} does not match pyproject version {version}"
        )

    changelog_version, changelog_date = _latest_changelog(root)
    if changelog_version != version:
        raise ReleaseMetadataError(
            f"latest changelog version {changelog_version} does not match pyproject version {version}"
        )

    major, minor, _patch = version.split(".")
    major_minor = f"{major}.{minor}"
    migration_name = f"MIGRATION-{major_minor}.md"
    migration = _read(root / migration_name)
    if not re.search(
        rf"^#\s+Migration\s+vers\s+PromptOps\s+{re.escape(version)}\s*$",
        migration,
        re.MULTILINE,
    ):
        raise ReleaseMetadataError(
            f"{migration_name} must identify PromptOps {version} in its H1"
        )
    for phrase in (
        CANONICAL_DISTRIBUTION,
        LEGACY_DISTRIBUTION,
        "import promptops",
        "import promptbench",
        "Rollback",
    ):
        if phrase not in migration:
            raise ReleaseMetadataError(
                f"{migration_name} must document identity compatibility: missing {phrase!r}"
            )

    readme = _read(root / "README.md")
    if not readme.startswith("# PromptOps\n"):
        raise ReleaseMetadataError("README.md H1 must be PromptOps")
    release_example = f"promptops release --version {version}"
    if release_example not in readme:
        raise ReleaseMetadataError(
            f"README.md must contain the current release example: {release_example}"
        )
    migration_link = f"[Migration to {major_minor}]({migration_name})"
    if migration_link not in readme:
        raise ReleaseMetadataError(
            f"README.md must link the current migration guide: {migration_link}"
        )
    for phrase in (
        "promptops-replay",
        "legacy `promptbench`",
        "latest published release remains `v0.5.0`",
    ):
        if phrase not in readme:
            raise ReleaseMetadataError(f"README.md identity contract is missing {phrase!r}")

    return ReleaseMetadata(
        version=version,
        major_minor=major_minor,
        changelog_date=changelog_date,
        migration_path=migration_name,
        distribution=CANONICAL_DISTRIBUTION,
        canonical_namespace="promptops",
        legacy_namespace="promptbench",
    )


def main() -> int:
    try:
        metadata = validate_release_metadata()
    except ReleaseMetadataError as exc:
        raise SystemExit(f"release metadata gate: {exc}") from exc
    print(
        "release metadata verified: "
        f"version={metadata.version} distribution={metadata.distribution} "
        f"canonical_namespace={metadata.canonical_namespace} legacy_namespace={metadata.legacy_namespace} "
        f"changelog_date={metadata.changelog_date} migration={metadata.migration_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
