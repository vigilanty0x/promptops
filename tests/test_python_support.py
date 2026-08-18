from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_python_support import (
    PythonSupportError,
    TESTED_PYTHONS,
    validate_python_support,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def project_toml(*, name: str, requires_python: str = ">=3.11", classifiers: bool = False) -> str:
    lines = [
        "[project]",
        f'name = "{name}"',
        'version = "1.0.0"',
        f'requires-python = "{requires_python}"',
    ]
    if classifiers:
        lines.append("classifiers = [")
        lines.extend(
            f'  "Programming Language :: Python :: {version}",'
            for version in TESTED_PYTHONS
        )
        lines.append("]")
    return "\n".join(lines) + "\n"


def write_fixture(
    root: Path,
    *,
    root_requires: str = ">=3.11",
    package_requires: str = ">=3.11",
    matrix_versions: tuple[str, ...] = TESTED_PYTHONS,
) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "packages" / "one").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        project_toml(name="promptbench-replay", requires_python=root_requires, classifiers=True),
        encoding="utf-8",
    )
    (root / "packages" / "one" / "pyproject.toml").write_text(
        project_toml(name="one", requires_python=package_requires),
        encoding="utf-8",
    )
    (root / "portfolio-compatibility.v1.json").write_text(
        json.dumps({"packages": [{"canonical_path": "packages/one"}]}),
        encoding="utf-8",
    )
    quoted = ", ".join(f'"{version}"' for version in matrix_versions)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "\n".join(
            [
                "jobs:",
                "  root:",
                "    strategy:",
                "      matrix:",
                f"        python-version: [{quoted}]",
                "  packages:",
                "    strategy:",
                "      matrix:",
                f"        python-version: [{quoted}]",
                "",
            ]
        ),
        encoding="utf-8",
    )


class PythonSupportTests(unittest.TestCase):
    def test_current_repository_support_contract_is_consistent(self):
        receipt = validate_python_support(REPO_ROOT)
        self.assertEqual(receipt.tested_versions, ("3.11", "3.12", "3.13", "3.14"))
        self.assertEqual(receipt.consolidated_packages, 9)
        self.assertEqual(receipt.ci_matrices, 2)

    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            receipt = validate_python_support(root)
            self.assertEqual(receipt.consolidated_packages, 1)

    def test_root_lower_bound_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, root_requires=">=3.12")
            with self.assertRaisesRegex(PythonSupportError, "root package requires-python"):
                validate_python_support(root)

    def test_consolidated_lower_bound_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, package_requires=">=3.12")
            with self.assertRaisesRegex(PythonSupportError, "packages/one requires-python"):
                validate_python_support(root)

    def test_ci_matrix_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, matrix_versions=("3.11", "3.12", "3.13"))
            with self.assertRaisesRegex(PythonSupportError, "CI Python matrix"):
                validate_python_support(root)

    def test_missing_root_classifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            text = (root / "pyproject.toml").read_text(encoding="utf-8")
            text = text.replace('  "Programming Language :: Python :: 3.14",\n', "")
            (root / "pyproject.toml").write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(PythonSupportError, "root Python classifiers"):
                validate_python_support(root)


if __name__ == "__main__":
    unittest.main()
