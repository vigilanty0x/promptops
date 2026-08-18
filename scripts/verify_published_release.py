"""Verify downloaded GitHub Release assets against the release policy and receipt.

Cryptographic attestation verification is deliberately performed by the CI job
with `gh attestation verify`; this module validates the downloaded release
metadata, immutable asset set, hashes, and embedded provenance receipt using
only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile


EXPECTED_REPOSITORY = "vigilanty0x/promptops"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class PublishedReleaseError(ValueError):
    """Raised when downloaded published-release evidence is inconsistent."""


@dataclass(frozen=True, slots=True)
class PublishedReleaseReceipt:
    version: str
    tag: str
    source_digest: str
    wheels: int
    assets: int
    attestation_id: str


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublishedReleaseError(f"cannot parse {label}") from exc
    if not isinstance(value, dict):
        raise PublishedReleaseError(f"{label} root must be an object")
    return value


def _digest(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PublishedReleaseError(f"cannot hash release asset: {path.name}") from exc


def validate_published_release(
    assets_dir: Path,
    view_json: Path,
    policy_path: Path,
    tag_sha_path: Path,
) -> PublishedReleaseReceipt:
    assets_dir = Path(assets_dir)
    if not assets_dir.is_dir():
        raise PublishedReleaseError("release assets directory is missing")
    policy = _load_json(Path(policy_path), "release policy")
    view = _load_json(Path(view_json), "release view")
    receipt_path = assets_dir / "RELEASE-RECEIPT.json"
    if not receipt_path.is_file():
        raise PublishedReleaseError("RELEASE-RECEIPT.json is missing")
    receipt = _load_json(receipt_path, "release receipt")

    version = policy.get("version")
    tag = policy.get("tag")
    if not isinstance(version, str) or not isinstance(tag, str):
        raise PublishedReleaseError("release policy version/tag are invalid")
    if receipt.get("repository") != EXPECTED_REPOSITORY:
        raise PublishedReleaseError("release receipt repository mismatch")
    if receipt.get("version") != version or receipt.get("tag") != tag:
        raise PublishedReleaseError("release receipt version/tag mismatch")
    if view.get("tagName") != tag:
        raise PublishedReleaseError("GitHub Release tag mismatch")
    if view.get("isDraft") is not False or view.get("isPrerelease") is not False:
        raise PublishedReleaseError("published release must be non-draft and non-prerelease")

    source_digest = receipt.get("source_digest")
    if not isinstance(source_digest, str) or HEX40.fullmatch(source_digest) is None:
        raise PublishedReleaseError("release receipt source_digest must be lowercase 40-hex")
    try:
        tag_sha = Path(tag_sha_path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise PublishedReleaseError("cannot read resolved tag SHA") from exc
    if tag_sha != source_digest:
        raise PublishedReleaseError(
            f"tag target {tag_sha!r} does not match release source {source_digest!r}"
        )
    if receipt.get("source_ref") != "refs/heads/main":
        raise PublishedReleaseError("release receipt source_ref must be refs/heads/main")
    if receipt.get("publication") != "github-release-owner-main-after-signed-provenance":
        raise PublishedReleaseError("release receipt publication contract mismatch")
    if receipt.get("canonical_wheel_count") != 10:
        raise PublishedReleaseError("release receipt must record ten canonical wheels")
    if receipt.get("canonical_wheel_python_source") != "3.11":
        raise PublishedReleaseError("release receipt wheel source must be Python 3.11")

    wheel_sha256 = receipt.get("wheel_sha256")
    if not isinstance(wheel_sha256, dict) or len(wheel_sha256) != 10:
        raise PublishedReleaseError("release receipt wheel_sha256 must contain ten entries")
    if any(not isinstance(name, str) or not name.endswith(".whl") for name in wheel_sha256):
        raise PublishedReleaseError("release receipt contains invalid wheel names")
    for name, expected in wheel_sha256.items():
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise PublishedReleaseError(f"invalid SHA-256 for {name}")
        path = assets_dir / name
        if not path.is_file():
            raise PublishedReleaseError(f"release wheel is missing: {name}")
        if _digest(path) != expected:
            raise PublishedReleaseError(f"release wheel digest mismatch: {name}")

    sums = assets_dir / "SHA256SUMS"
    if not sums.is_file():
        raise PublishedReleaseError("SHA256SUMS is missing")
    if _digest(sums) != receipt.get("sha256sums_sha256"):
        raise PublishedReleaseError("SHA256SUMS digest mismatch")
    try:
        parsed = {}
        for raw in sums.read_text(encoding="utf-8").splitlines():
            digest, name = raw.split("  ", 1)
            if name in parsed:
                raise PublishedReleaseError(f"duplicate SHA256SUMS entry: {name}")
            parsed[name] = digest
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, PublishedReleaseError):
            raise
        raise PublishedReleaseError("cannot parse SHA256SUMS") from exc
    if parsed != wheel_sha256:
        raise PublishedReleaseError("SHA256SUMS differs from release receipt")

    provenance_name = receipt.get("provenance_zip")
    if not isinstance(provenance_name, str) or provenance_name != f"promptops-{version}-provenance.zip":
        raise PublishedReleaseError("provenance ZIP name mismatch")
    provenance_zip = assets_dir / provenance_name
    if not provenance_zip.is_file():
        raise PublishedReleaseError("provenance ZIP is missing")
    if _digest(provenance_zip) != receipt.get("provenance_zip_sha256"):
        raise PublishedReleaseError("provenance ZIP digest mismatch")

    try:
        with ZipFile(provenance_zip) as archive:
            names = archive.namelist()
            provenance_receipts = [name for name in names if name.endswith("PROVENANCE-RECEIPT.json")]
            bundles = [name for name in names if name.endswith("attestation.json")]
            embedded_sums = [name for name in names if name.endswith("SHA256SUMS")]
            if len(provenance_receipts) != 1 or len(bundles) != 1 or len(embedded_sums) != 1:
                raise PublishedReleaseError("provenance ZIP must contain exactly one bundle, receipt, and checksum file")
            embedded = json.loads(archive.read(provenance_receipts[0]).decode("utf-8"))
            embedded_checksum_text = archive.read(embedded_sums[0]).decode("utf-8")
    except (OSError, BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, PublishedReleaseError):
            raise
        raise PublishedReleaseError("cannot validate provenance ZIP") from exc
    if embedded_checksum_text != sums.read_text(encoding="utf-8"):
        raise PublishedReleaseError("embedded provenance SHA256SUMS differs from release SHA256SUMS")
    expected_provenance = {
        "repository": EXPECTED_REPOSITORY,
        "workflow": ".github/workflows/ci.yml",
        "event": "push",
        "source_ref": "refs/heads/main",
        "source_digest": source_digest,
        "runner_environment": "github-hosted",
        "canonical_subject_count": 10,
        "verified_with_gh_cli": True,
        "provenance": "sigstore-slsa-github-actions",
    }
    for field, expected in expected_provenance.items():
        if embedded.get(field) != expected:
            raise PublishedReleaseError(
                f"embedded provenance receipt {field} mismatch: expected {expected!r}, got {embedded.get(field)!r}"
            )
    attestation_id = embedded.get("attestation_id")
    if not isinstance(attestation_id, str) or not attestation_id.isdigit():
        raise PublishedReleaseError("embedded provenance receipt attestation_id is invalid")

    expected_names = set(wheel_sha256) | {
        "SHA256SUMS",
        provenance_name,
        "RELEASE-RECEIPT.json",
    }
    observed_names = {path.name for path in assets_dir.iterdir() if path.is_file()}
    if observed_names != expected_names:
        raise PublishedReleaseError(
            f"release asset set mismatch: expected={sorted(expected_names)} observed={sorted(observed_names)}"
        )

    return PublishedReleaseReceipt(
        version=version,
        tag=tag,
        source_digest=source_digest,
        wheels=len(wheel_sha256),
        assets=len(observed_names),
        attestation_id=attestation_id,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--view-json", required=True, type=Path)
    parser.add_argument("--policy", default=Path("release-policy.v1.json"), type=Path)
    parser.add_argument("--tag-sha", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = validate_published_release(
            args.assets_dir, args.view_json, args.policy, args.tag_sha
        )
    except PublishedReleaseError as exc:
        raise SystemExit(f"published release verification: {exc}") from exc
    print(
        "published release verified: "
        f"version={receipt.version} tag={receipt.tag} source={receipt.source_digest} "
        f"wheels={receipt.wheels} assets={receipt.assets} attestation_id={receipt.attestation_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
