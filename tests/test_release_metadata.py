from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.check_release_metadata import ReleaseMetadataError, validate_release_metadata


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_fixture(
    root: Path,
    *,
    version: str = "1.2.3",
    canonical_version: str | None = None,
    legacy_version: str | None = None,
    project_name: str = "promptops-replay",
    changelog_version: str | None = None,
    migration_heading_version: str | None = None,
    include_readme_migration_link: bool = True,
) -> None:
    canonical_version = canonical_version or version
    legacy_version = legacy_version or version
    changelog_version = changelog_version or version
    migration_heading_version = migration_heading_version or version
    major_minor = ".".join(version.split(".")[:2])
    (root / "src" / "promptops").mkdir(parents=True)
    (root / "src" / "promptbench").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                f'name = "{project_name}"',
                f'version = "{version}"',
                'description = "PromptOps: deterministic test fixture."',
                "",
                "[project.scripts]",
                'promptops = "promptbench.ops_cli:main"',
                'promptbench = "promptbench.cli:main"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "src" / "promptops" / "__init__.py").write_text(
        f'__version__ = "{canonical_version}"\n', encoding="utf-8"
    )
    (root / "src" / "promptbench" / "__init__.py").write_text(
        f'__version__ = "{legacy_version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {changelog_version} - 2026-08-18\n\n- test release\n",
        encoding="utf-8",
    )
    (root / f"MIGRATION-{major_minor}.md").write_text(
        "\n".join(
            [
                f"# Migration vers PromptOps {migration_heading_version}",
                "",
                "Install promptops-replay.",
                "The old promptbench-replay distribution remains the published 0.5 identity.",
                "Use import promptops for new code and import promptbench for compatibility.",
                "## Rollback",
                "Rollback to 0.5.0.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    migration_link = (
        f"[Migration to {major_minor}](MIGRATION-{major_minor}.md)"
        if include_readme_migration_link
        else "migration link intentionally missing"
    )
    (root / "README.md").write_text(
        "\n".join(
            [
                "# PromptOps",
                "",
                "The candidate distribution is promptops-replay; legacy `promptbench` remains supported.",
                "The latest published release remains `v0.5.0`.",
                f"promptops release --version {version}",
                "",
                migration_link,
                "",
            ]
        ),
        encoding="utf-8",
    )


class ReleaseMetadataTests(unittest.TestCase):
    def test_current_repository_release_metadata_is_consistent(self):
        metadata = validate_release_metadata(REPO_ROOT)
        self.assertEqual(metadata.version, "0.6.0")
        self.assertEqual(metadata.major_minor, "0.6")
        self.assertEqual(metadata.migration_path, "MIGRATION-0.6.md")
        self.assertEqual(metadata.distribution, "promptops-replay")
        self.assertEqual(metadata.canonical_namespace, "promptops")
        self.assertEqual(metadata.legacy_namespace, "promptbench")

    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            metadata = validate_release_metadata(root)
            self.assertEqual(metadata.version, "1.2.3")
            self.assertEqual(metadata.changelog_date, "2026-08-18")

    def test_legacy_distribution_name_is_rejected_for_new_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, project_name="promptbench-replay")
            with self.assertRaisesRegex(ReleaseMetadataError, "legacy 0.5 distribution"):
                validate_release_metadata(root)

    def test_canonical_runtime_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, canonical_version="1.2.4")
            with self.assertRaisesRegex(ReleaseMetadataError, "canonical promptops __version__"):
                validate_release_metadata(root)

    def test_legacy_runtime_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, legacy_version="1.2.4")
            with self.assertRaisesRegex(ReleaseMetadataError, "legacy promptbench __version__"):
                validate_release_metadata(root)

    def test_changelog_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, changelog_version="1.2.2")
            with self.assertRaisesRegex(ReleaseMetadataError, "latest changelog version"):
                validate_release_metadata(root)

    def test_migration_heading_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, migration_heading_version="1.2.2")
            with self.assertRaisesRegex(ReleaseMetadataError, "must identify PromptOps 1.2.3"):
                validate_release_metadata(root)

    def test_missing_current_readme_migration_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, include_readme_migration_link=False)
            with self.assertRaisesRegex(ReleaseMetadataError, "README.md must link"):
                validate_release_metadata(root)


if __name__ == "__main__":
    unittest.main()
