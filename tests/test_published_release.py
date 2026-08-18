from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.verify_published_release import (
    PublishedReleaseError,
    validate_published_release,
)


SOURCE = "a" * 40


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def build_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    assets = root / "assets"
    assets.mkdir()
    wheel_hashes: dict[str, str] = {}
    for index in range(10):
        name = f"pkg{index}-0.1.0-py3-none-any.whl"
        data = f"wheel-{index}".encode()
        (assets / name).write_bytes(data)
        wheel_hashes[name] = digest(data)
    sums_text = "".join(f"{value}  {name}\n" for name, value in sorted(wheel_hashes.items()))
    (assets / "SHA256SUMS").write_text(sums_text, encoding="utf-8")

    embedded = {
        "repository": "vigilanty0x/promptops",
        "workflow": ".github/workflows/ci.yml",
        "event": "push",
        "source_ref": "refs/heads/main",
        "source_digest": SOURCE,
        "runner_environment": "github-hosted",
        "canonical_subject_count": 10,
        "attestation_id": "123456",
        "verified_with_gh_cli": True,
        "provenance": "sigstore-slsa-github-actions",
    }
    provenance = assets / "promptops-0.5.0-provenance.zip"
    with ZipFile(provenance, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("attestation.json", "{}")
        archive.writestr("SHA256SUMS", sums_text)
        archive.writestr("PROVENANCE-RECEIPT.json", json.dumps(embedded))

    receipt = {
        "repository": "vigilanty0x/promptops",
        "version": "0.5.0",
        "tag": "v0.5.0",
        "source_digest": SOURCE,
        "source_ref": "refs/heads/main",
        "canonical_wheel_count": 10,
        "canonical_wheel_python_source": "3.11",
        "wheel_sha256": wheel_hashes,
        "sha256sums_sha256": digest((assets / "SHA256SUMS").read_bytes()),
        "provenance_zip": provenance.name,
        "provenance_zip_sha256": digest(provenance.read_bytes()),
        "publication": "github-release-owner-main-after-signed-provenance",
    }
    (assets / "RELEASE-RECEIPT.json").write_text(json.dumps(receipt), encoding="utf-8")

    view = root / "view.json"
    view.write_text(json.dumps({"tagName": "v0.5.0", "isDraft": False, "isPrerelease": False}), encoding="utf-8")
    policy = root / "release-policy.v1.json"
    policy.write_text(json.dumps({"version": "0.5.0", "tag": "v0.5.0"}), encoding="utf-8")
    tag_sha = root / "tag-sha.txt"
    tag_sha.write_text(SOURCE + "\n", encoding="utf-8")
    return assets, view, policy, tag_sha


class PublishedReleaseTests(unittest.TestCase):
    def test_valid_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = build_fixture(Path(tmp))
            receipt = validate_published_release(*args)
            self.assertEqual(receipt.version, "0.5.0")
            self.assertEqual(receipt.wheels, 10)
            self.assertEqual(receipt.assets, 13)

    def test_tampered_wheel_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = build_fixture(Path(tmp))
            wheel = next(args[0].glob("*.whl"))
            wheel.write_bytes(b"tampered")
            with self.assertRaisesRegex(PublishedReleaseError, "wheel digest mismatch"):
                validate_published_release(*args)

    def test_wrong_tag_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = build_fixture(Path(tmp))
            args[3].write_text("b" * 40 + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PublishedReleaseError, "does not match release source"):
                validate_published_release(*args)


if __name__ == "__main__":
    unittest.main()
