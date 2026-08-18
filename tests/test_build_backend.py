from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_build_backend import (
    BuildBackendError,
    SETUPTOOLS_PIN,
    validate_build_backends,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def pyproject(*, requires: str = SETUPTOOLS_PIN, backend: str = "setuptools.build_meta") -> str:
    return "\n".join(
        [
            "[build-system]",
            f'requires = ["{requires}"]',
            f'build-backend = "{backend}"',
            "",
            "[project]",
            'name = "fixture"',
            'version = "1.0.0"',
            'requires-python = ">=3.11"',
            "",
        ]
    )


def write_fixture(
    root: Path,
    *,
    root_requires: str = SETUPTOOLS_PIN,
    package_requires: str = SETUPTOOLS_PIN,
    package_backend: str = "setuptools.build_meta",
) -> None:
    (root / "packages" / "one").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        pyproject(requires=root_requires), encoding="utf-8"
    )
    (root / "packages" / "one" / "pyproject.toml").write_text(
        pyproject(requires=package_requires, backend=package_backend), encoding="utf-8"
    )
    (root / "portfolio-compatibility.v1.json").write_text(
        json.dumps({"packages": [{"canonical_path": "packages/one"}]}), encoding="utf-8"
    )


class BuildBackendTests(unittest.TestCase):
    def test_current_repository_build_backend_contract_is_consistent(self):
        receipt = validate_build_backends(REPO_ROOT)
        self.assertTrue(receipt.root_verified)
        self.assertEqual(receipt.consolidated_packages, 9)
        self.assertEqual(receipt.setuptools_pin, "setuptools==83.0.0")

    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            receipt = validate_build_backends(root)
            self.assertEqual(receipt.consolidated_packages, 1)

    def test_root_floating_setuptools_spec_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, root_requires="setuptools>=69")
            with self.assertRaisesRegex(BuildBackendError, "root package build-system.requires"):
                validate_build_backends(root)

    def test_historical_floating_setuptools_spec_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, package_requires="setuptools>=68")
            with self.assertRaisesRegex(BuildBackendError, "packages/one build-system.requires"):
                validate_build_backends(root)

    def test_backend_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, package_backend="other.backend")
            with self.assertRaisesRegex(BuildBackendError, "packages/one build-backend"):
                validate_build_backends(root)


if __name__ == "__main__":
    unittest.main()
