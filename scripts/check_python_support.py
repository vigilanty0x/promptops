"""Fail-closed consistency gate for the repository Python support contract.

The project metadata intentionally uses a lower bound (>=3.11).  This checker
binds the currently tested stable CPython series to the root classifiers, both
CI matrices, and every consolidated package's lower-bound metadata.  Future
stable versions can be added by changing this explicit contract in one review.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
TESTED_PYTHONS = ("3.11", "3.12", "3.13", "3.14")
REQUIRES_PYTHON = ">=3.11"
MATRIX_LINE = re.compile(r'^\s*python-version:\s*\[(?P<values>[^\]]+)\]\s*(?:#.*)?$')
QUOTED = re.compile(r'"([^"]+)"')


class PythonSupportError(ValueError):
    """Raised when package metadata and CI Python coverage drift apart."""


@dataclass(frozen=True, slots=True)
class PythonSupportReceipt:
    tested_versions: tuple[str, ...]
    consolidated_packages: int
    ci_matrices: int


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise PythonSupportError(f"required file is missing: {path.relative_to(path.parents[1]) if len(path.parents) > 1 else path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PythonSupportError(f"cannot read {path}") from exc


def _read_toml(path: Path) -> dict:
    try:
        value = tomllib.loads(_read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise PythonSupportError(f"invalid TOML: {path}") from exc
    if not isinstance(value, dict):
        raise PythonSupportError(f"TOML root must be an object: {path}")
    return value


def _project(path: Path) -> dict:
    value = _read_toml(path).get("project")
    if not isinstance(value, dict):
        raise PythonSupportError(f"missing [project] table: {path}")
    return value


def _require_lower_bound(project: dict, *, label: str) -> None:
    actual = project.get("requires-python")
    if actual != REQUIRES_PYTHON:
        raise PythonSupportError(
            f"{label} requires-python must be {REQUIRES_PYTHON!r}; got {actual!r}"
        )


def _verify_root_metadata(root: Path) -> None:
    project = _project(root / "pyproject.toml")
    _require_lower_bound(project, label="root package")
    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list):
        raise PythonSupportError("root classifiers must be an array")
    expected = {f"Programming Language :: Python :: {version}" for version in TESTED_PYTHONS}
    present = {item for item in classifiers if isinstance(item, str) and item.startswith("Programming Language :: Python :: 3.")}
    if present != expected:
        missing = sorted(expected - present)
        extra = sorted(present - expected)
        raise PythonSupportError(
            f"root Python classifiers must match tested versions; missing={missing} extra={extra}"
        )


def _manifest_packages(root: Path) -> list[dict]:
    path = root / "portfolio-compatibility.v1.json"
    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise PythonSupportError("portfolio compatibility manifest is invalid JSON") from exc
    packages = value.get("packages") if isinstance(value, dict) else None
    if not isinstance(packages, list) or not packages:
        raise PythonSupportError("portfolio compatibility manifest must contain packages")
    return packages


def _verify_consolidated_metadata(root: Path) -> int:
    packages = _manifest_packages(root)
    seen_paths: set[str] = set()
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            raise PythonSupportError(f"manifest packages[{index}] must be an object")
        canonical_path = item.get("canonical_path")
        if not isinstance(canonical_path, str) or not canonical_path.startswith("packages/"):
            raise PythonSupportError(f"manifest packages[{index}].canonical_path is invalid")
        if canonical_path in seen_paths:
            raise PythonSupportError(f"duplicate canonical_path in manifest: {canonical_path}")
        seen_paths.add(canonical_path)
        project = _project(root / canonical_path / "pyproject.toml")
        _require_lower_bound(project, label=canonical_path)
    return len(packages)


def _verify_ci_matrices(root: Path) -> int:
    workflow = _read_text(root / ".github" / "workflows" / "ci.yml")
    matrices: list[tuple[str, ...]] = []
    for line in workflow.splitlines():
        match = MATRIX_LINE.match(line)
        if not match:
            continue
        versions = tuple(QUOTED.findall(match.group("values")))
        matrices.append(versions)
    if len(matrices) != 2:
        raise PythonSupportError(
            f"ci.yml must contain exactly two explicit python-version matrices; found {len(matrices)}"
        )
    for index, versions in enumerate(matrices):
        if versions != TESTED_PYTHONS:
            raise PythonSupportError(
                f"CI Python matrix {index + 1} must be {TESTED_PYTHONS}; got {versions}"
            )
    return len(matrices)


def validate_python_support(root: Path = ROOT) -> PythonSupportReceipt:
    root = Path(root)
    _verify_root_metadata(root)
    packages = _verify_consolidated_metadata(root)
    matrices = _verify_ci_matrices(root)
    return PythonSupportReceipt(
        tested_versions=TESTED_PYTHONS,
        consolidated_packages=packages,
        ci_matrices=matrices,
    )


def main() -> int:
    try:
        receipt = validate_python_support()
    except PythonSupportError as exc:
        raise SystemExit(f"python support gate: {exc}") from exc
    print(
        "python support verified: "
        f"versions={','.join(receipt.tested_versions)} "
        f"packages={receipt.consolidated_packages} ci_matrices={receipt.ci_matrices}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
