"""Fail-closed consistency gate for the PEP 517 build backend contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SETUPTOOLS_PIN = "setuptools==83.0.0"
BUILD_BACKEND = "setuptools.build_meta"


class BuildBackendError(ValueError):
    """Raised when a package build-system contract drifts."""


@dataclass(frozen=True, slots=True)
class BuildBackendReceipt:
    root_verified: bool
    consolidated_packages: int
    setuptools_pin: str


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise BuildBackendError(f"required file is missing: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BuildBackendError(f"cannot read {path}") from exc


def _read_toml(path: Path) -> dict:
    try:
        value = tomllib.loads(_read_text(path))
    except tomllib.TOMLDecodeError as exc:
        raise BuildBackendError(f"invalid TOML: {path}") from exc
    if not isinstance(value, dict):
        raise BuildBackendError(f"TOML root must be an object: {path}")
    return value


def _verify_pyproject(path: Path, *, label: str) -> None:
    data = _read_toml(path)
    build_system = data.get("build-system")
    if not isinstance(build_system, dict):
        raise BuildBackendError(f"{label} must contain [build-system]")
    requires = build_system.get("requires")
    if requires != [SETUPTOOLS_PIN]:
        raise BuildBackendError(
            f"{label} build-system.requires must be exactly [{SETUPTOOLS_PIN!r}]; got {requires!r}"
        )
    backend = build_system.get("build-backend")
    if backend != BUILD_BACKEND:
        raise BuildBackendError(
            f"{label} build-backend must be {BUILD_BACKEND!r}; got {backend!r}"
        )


def _manifest_paths(root: Path) -> list[str]:
    manifest_path = root / "portfolio-compatibility.v1.json"
    try:
        value = json.loads(_read_text(manifest_path))
    except json.JSONDecodeError as exc:
        raise BuildBackendError("portfolio compatibility manifest is invalid JSON") from exc
    packages = value.get("packages") if isinstance(value, dict) else None
    if not isinstance(packages, list) or not packages:
        raise BuildBackendError("portfolio compatibility manifest must contain packages")
    paths: list[str] = []
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            raise BuildBackendError(f"manifest packages[{index}] must be an object")
        canonical_path = item.get("canonical_path")
        if not isinstance(canonical_path, str) or not canonical_path.startswith("packages/"):
            raise BuildBackendError(f"manifest packages[{index}].canonical_path is invalid")
        paths.append(canonical_path)
    if len(paths) != len(set(paths)):
        raise BuildBackendError("portfolio compatibility manifest contains duplicate canonical_path values")
    return paths


def validate_build_backends(root: Path = ROOT) -> BuildBackendReceipt:
    root = Path(root)
    _verify_pyproject(root / "pyproject.toml", label="root package")
    paths = _manifest_paths(root)
    for canonical_path in paths:
        _verify_pyproject(
            root / canonical_path / "pyproject.toml",
            label=canonical_path,
        )
    return BuildBackendReceipt(
        root_verified=True,
        consolidated_packages=len(paths),
        setuptools_pin=SETUPTOOLS_PIN,
    )


def main() -> int:
    try:
        receipt = validate_build_backends()
    except BuildBackendError as exc:
        raise SystemExit(f"build backend gate: {exc}") from exc
    print(
        "build backend verified: "
        f"root={receipt.root_verified} packages={receipt.consolidated_packages} "
        f"pin={receipt.setuptools_pin}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
