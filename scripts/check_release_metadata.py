"""Fail-closed consistency gate for root release metadata.

The root package version is repeated intentionally in a few public surfaces:
``pyproject.toml``, ``promptbench.__version__``, the latest changelog entry, the
current migration guide, and README examples.  This checker makes that
redundancy auditable instead of allowing silent drift.

It uses only the Python standard library and never imports the package, so a
broken package import cannot hide version skew.
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


class ReleaseMetadataError(ValueError):
    """Raised when root release metadata is inconsistent or malformed."""


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    version: str
    major_minor: str
    changelog_date: str
    migration_path: str


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
    if project.get("name") != "promptbench-replay":
        raise ReleaseMetadataError("root project name must remain promptbench-replay")
    version = project.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ReleaseMetadataError("[project].version must be a plain SemVer X.Y.Z")
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        raise ReleaseMetadataError("pyproject.toml must contain [project.scripts]")
    expected_scripts = {
        "promptbench": "promptbench.cli:main",
        "promptops": "promptbench.ops_cli:main",
    }
    for name, target in expected_scripts.items():
        if scripts.get(name) != target:
            raise ReleaseMetadataError(f"console script {name} must resolve to {target}")
    return version


def _runtime_version(root: Path) -> str:
    path = root / "src" / "promptbench" / "__init__.py"
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError as exc:
        raise ReleaseMetadataError("src/promptbench/__init__.py is invalid Python") from exc
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
            raise ReleaseMetadataError("__version__ must be assigned a literal string")
    if len(values) != 1:
        raise ReleaseMetadataError("src/promptbench/__init__.py must define __version__ exactly once")
    if SEMVER.fullmatch(values[0]) is None:
        raise ReleaseMetadataError("__version__ must be a plain SemVer X.Y.Z")
    return values[0]


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
    """Validate root release surfaces and return the canonical version receipt."""

    root = Path(root)
    version = _pyproject_version(root)
    runtime = _runtime_version(root)
    if runtime != version:
        raise ReleaseMetadataError(
            f"runtime __version__ {runtime} does not match pyproject version {version}"
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

    readme = _read(root / "README.md")
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

    return ReleaseMetadata(
        version=version,
        major_minor=major_minor,
        changelog_date=changelog_date,
        migration_path=migration_name,
    )


def main() -> int:
    try:
        metadata = validate_release_metadata()
    except ReleaseMetadataError as exc:
        raise SystemExit(f"release metadata gate: {exc}") from exc
    print(
        "release metadata verified: "
        f"version={metadata.version} "
        f"changelog_date={metadata.changelog_date} "
        f"migration={metadata.migration_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
