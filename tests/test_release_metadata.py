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
    runtime_version: str | None = None,
    changelog_version: str | None = None,
    migration_heading_version: str | None = None,
    include_readme_migration_link: bool = True,
) -> None:
    runtime_version = runtime_version or version
    changelog_version = changelog_version or version
    migration_heading_version = migration_heading_version or version
    major_minor = ".".join(version.split(".")[:2])
    (root / "src" / "promptbench").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "promptbench-replay"',
                f'version = "{version}"',
                "",
                "[project.scripts]",
                'promptbench = "promptbench.cli:main"',
                'promptops = "promptbench.ops_cli:main"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "src" / "promptbench" / "__init__.py").write_text(
        f'__version__ = "{runtime_version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {changelog_version} - 2026-08-18\n\n- test release\n",
        encoding="utf-8",
    )
    (root / f"MIGRATION-{major_minor}.md").write_text(
        f"# Migration vers PromptOps {migration_heading_version}\n",
        encoding="utf-8",
    )
    migration_link = (
        f"[Migration to {major_minor}](MIGRATION-{major_minor}.md)"
        if include_readme_migration_link
        else "migration link intentionally missing"
    )
    (root / "README.md").write_text(
        f"promptops release --version {version}\n\n{migration_link}\n",
        encoding="utf-8",
    )


class ReleaseMetadataTests(unittest.TestCase):
    def test_current_repository_release_metadata_is_consistent(self):
        metadata = validate_release_metadata(REPO_ROOT)
        self.assertEqual(metadata.version, "0.5.0")
        self.assertEqual(metadata.major_minor, "0.5")
        self.assertEqual(metadata.migration_path, "MIGRATION-0.5.md")

    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root)
            metadata = validate_release_metadata(root)
            self.assertEqual(metadata.version, "1.2.3")
            self.assertEqual(metadata.changelog_date, "2026-08-18")

    def test_runtime_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, runtime_version="1.2.4")
            with self.assertRaisesRegex(ReleaseMetadataError, "runtime __version__"):
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
