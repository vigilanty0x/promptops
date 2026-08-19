from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.generate_spdx_sbom import SbomError, build_sbom, main, verify_sbom


SOURCE_SHA = "a" * 40
CREATED_AT = "2026-08-18T17:01:53+00:00"
REPOSITORY = "vigilanty0x/promptops"


def write_wheel(
    directory: Path,
    *,
    name: str,
    version: str,
    requires: tuple[str, ...] = (),
    summary: str = "Synthetic test package",
) -> Path:
    normalized = name.replace("-", "_")
    path = directory / f"{normalized}-{version}-py3-none-any.whl"
    metadata = [
        "Metadata-Version: 2.4",
        f"Name: {name}",
        f"Version: {version}",
        f"Summary: {summary}",
        "License-Expression: Apache-2.0",
    ]
    metadata.extend(f"Requires-Dist: {requirement}" for requirement in requires)
    metadata.append("")
    metadata.append("")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{normalized}/__init__.py", f'__version__ = "{version}"\n')
        archive.writestr(f"{normalized}-{version}.dist-info/METADATA", "\n".join(metadata))
        archive.writestr(
            f"{normalized}-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: synthetic\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{normalized}-{version}.dist-info/RECORD", "")
    return path


class SpdxSbomTests(unittest.TestCase):
    def test_deterministic_sbom_binds_exact_wheels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(root, name="promptops-replay", version="0.6.0")
            write_wheel(root, name="answer-diff", version="0.1.0")
            first = build_sbom(
                root,
                repository=REPOSITORY,
                source_sha=SOURCE_SHA,
                created_at=CREATED_AT,
                expected_count=2,
            )
            second = build_sbom(
                root,
                repository=REPOSITORY,
                source_sha=SOURCE_SHA,
                created_at="2026-08-18T19:01:53+02:00",
                expected_count=2,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["spdxVersion"], "SPDX-2.3")
        self.assertEqual(first["creationInfo"]["created"], "2026-08-18T17:01:53Z")
        described = [
            relation
            for relation in first["relationships"]
            if relation["relationshipType"] == "DESCRIBES"
        ]
        self.assertEqual(len(described), 2)
        self.assertIn(SOURCE_SHA, first["documentNamespace"])

    def test_direct_dependencies_are_recorded_without_inventing_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(
                root,
                name="promptops-replay",
                version="0.6.0",
                requires=("answer-diff>=0.1", "external-lib; python_version >= '3.11'"),
            )
            write_wheel(root, name="answer-diff", version="0.1.0")
            sbom = build_sbom(
                root,
                repository=REPOSITORY,
                source_sha=SOURCE_SHA,
                created_at=CREATED_AT,
                expected_count=2,
            )
        package_ids = {item["SPDXID"] for item in sbom["packages"]}
        self.assertIn("SPDXRef-Package-answer-diff", package_ids)
        self.assertIn("SPDXRef-Dependency-external-lib", package_ids)
        dependencies = [
            relation
            for relation in sbom["relationships"]
            if relation["relationshipType"] == "DEPENDS_ON"
        ]
        self.assertEqual(len(dependencies), 2)

    def test_verifier_rejects_tampered_sbom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(root, name="promptops-replay", version="0.6.0")
            sbom = build_sbom(
                root,
                repository=REPOSITORY,
                source_sha=SOURCE_SHA,
                created_at=CREATED_AT,
                expected_count=1,
            )
            path = root / "SBOM.spdx.json"
            path.write_text(json.dumps(sbom), encoding="utf-8")
            observed = json.loads(path.read_text(encoding="utf-8"))
            observed["packages"][0]["versionInfo"] = "9.9.9"
            path.write_text(json.dumps(observed), encoding="utf-8")
            with self.assertRaises(SbomError):
                verify_sbom(
                    path,
                    root,
                    repository=REPOSITORY,
                    source_sha=SOURCE_SHA,
                    created_at=CREATED_AT,
                    expected_count=1,
                )

    def test_duplicate_canonical_distribution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(root, name="demo-pkg", version="1.0.0")
            first = root / "demo_pkg-1.0.0-py3-none-any.whl"
            second = root / "demo_pkg-2.0.0-py3-none-any.whl"
            second.write_bytes(first.read_bytes())
            with self.assertRaises(SbomError):
                build_sbom(
                    root,
                    repository=REPOSITORY,
                    source_sha=SOURCE_SHA,
                    created_at=CREATED_AT,
                    expected_count=2,
                )

    def test_cli_generate_then_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(root, name="promptops-replay", version="0.6.0")
            output = root / "SBOM.spdx.json"
            args = [
                "--wheel-dir",
                str(root),
                "--repository",
                REPOSITORY,
                "--source-sha",
                SOURCE_SHA,
                "--created-at",
                CREATED_AT,
                "--expected-count",
                "1",
                "--output",
                str(output),
            ]
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(args), 0)
            receipt = json.loads(stdout.getvalue())
            self.assertEqual(receipt["canonical_wheel_count"], 1)
            self.assertFalse(receipt["verified"])
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main([*args, "--verify"]), 0)
            verified = json.loads(stdout.getvalue())
            self.assertTrue(verified["verified"])

    def test_cli_fails_closed_on_wrong_expected_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_wheel(root, name="promptops-replay", version="0.6.0")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(
                    [
                        "--wheel-dir",
                        str(root),
                        "--repository",
                        REPOSITORY,
                        "--source-sha",
                        SOURCE_SHA,
                        "--created-at",
                        CREATED_AT,
                        "--expected-count",
                        "2",
                        "--output",
                        str(root / "SBOM.spdx.json"),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("expected exactly 2 wheel files", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
