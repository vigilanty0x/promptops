"""Generate and verify a deterministic SPDX 2.3 SBOM for exact wheel subjects.

The SBOM is intentionally scoped to the release-candidate Python wheels and the
direct ``Requires-Dist`` metadata embedded in those wheels. It does not claim to
inventory an operating system, container image, or resolved transitive runtime.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import compat32
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import quote
import zipfile

MAX_WHEEL_BYTES = 100_000_000
MAX_ZIP_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 250_000_000
MAX_METADATA_BYTES = 1_000_000
MAX_SBOM_BYTES = 4_000_000
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class SbomError(ValueError):
    """Raised when wheel evidence or the generated SBOM is invalid."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _spdx_token(value: str) -> str:
    normalized = _normalize_name(value)
    token = re.sub(r"[^A-Za-z0-9.-]+", "-", normalized).strip("-.")
    if not token:
        raise SbomError(f"cannot derive SPDX identifier from package name {value!r}")
    return token


def _created_at(value: str) -> str:
    text = value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SbomError("created-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SbomError("created-at must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _safe_zip_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _wheel_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.suffix != ".whl":
        raise SbomError(f"not a wheel file: {path}")
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise SbomError(f"wheel exceeds {MAX_WHEEL_BYTES} bytes: {path.name}")
    digest = _sha256_bytes(path.read_bytes())
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise SbomError(f"wheel has too many ZIP entries: {path.name}")
            total_uncompressed = 0
            for entry in entries:
                if not _safe_zip_name(entry.filename):
                    raise SbomError(f"wheel contains unsafe ZIP path: {path.name}")
                total_uncompressed += entry.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise SbomError(f"wheel exceeds uncompressed scan bound: {path.name}")
            metadata_names = [
                entry.filename
                for entry in entries
                if entry.filename.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise SbomError(
                    f"wheel must contain exactly one dist-info/METADATA file: {path.name}"
                )
            info = archive.getinfo(metadata_names[0])
            if info.file_size > MAX_METADATA_BYTES:
                raise SbomError(f"wheel metadata exceeds scan bound: {path.name}")
            raw_metadata = archive.read(metadata_names[0])
    except zipfile.BadZipFile as exc:
        raise SbomError(f"invalid wheel ZIP: {path.name}") from exc

    message = BytesParser(policy=compat32).parsebytes(raw_metadata)
    name = message.get("Name")
    version = message.get("Version")
    if not isinstance(name, str) or not name.strip():
        raise SbomError(f"wheel metadata has no Name: {path.name}")
    if not isinstance(version, str) or not version.strip():
        raise SbomError(f"wheel metadata has no Version: {path.name}")
    requirements = message.get_all("Requires-Dist") or []
    parsed_requirements: list[dict[str, str]] = []
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement)
        if match is None:
            raise SbomError(
                f"cannot parse Requires-Dist name in {path.name}: {requirement!r}"
            )
        parsed_requirements.append(
            {"name": _normalize_name(match.group(1)), "raw": requirement.strip()}
        )
    parsed_requirements.sort(key=lambda item: (item["name"], item["raw"]))
    license_expression = message.get("License-Expression")
    summary = message.get("Summary")
    return {
        "filename": path.name,
        "sha256": digest,
        "name": name.strip(),
        "normalized_name": _normalize_name(name),
        "version": version.strip(),
        "license_expression": license_expression.strip()
        if isinstance(license_expression, str) and license_expression.strip()
        else "NOASSERTION",
        "summary": summary.strip()
        if isinstance(summary, str) and summary.strip()
        else None,
        "requirements": parsed_requirements,
    }


def _canonical_package(item: dict[str, Any]) -> dict[str, Any]:
    package = {
        "SPDXID": f"SPDXRef-Package-{_spdx_token(item['normalized_name'])}",
        "name": item["name"],
        "versionInfo": item["version"],
        "packageFileName": item["filename"],
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": item["license_expression"],
        "copyrightText": "NOASSERTION",
        "checksums": [
            {"algorithm": "SHA256", "checksumValue": item["sha256"]}
        ],
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": (
                    f"pkg:pypi/{quote(item['normalized_name'], safe='-')}@"
                    f"{quote(item['version'], safe='.+-_')}"
                ),
            }
        ],
    }
    if item["summary"] is not None:
        package["summary"] = item["summary"]
    if item["requirements"]:
        package["packageComment"] = "Direct Core Metadata requirements: " + "; ".join(
            requirement["raw"] for requirement in item["requirements"]
        )
    return package


def _external_dependency(name: str) -> dict[str, Any]:
    return {
        "SPDXID": f"SPDXRef-Dependency-{_spdx_token(name)}",
        "name": name,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{quote(name, safe='-')}",
            }
        ],
    }


def build_sbom(
    wheel_dir: Path,
    *,
    repository: str,
    source_sha: str,
    created_at: str,
    expected_count: int,
) -> dict[str, Any]:
    wheel_dir = Path(wheel_dir)
    if not wheel_dir.is_dir():
        raise SbomError(f"wheel directory is missing: {wheel_dir}")
    if REPOSITORY.fullmatch(repository) is None:
        raise SbomError("repository must have owner/name form")
    if GIT_SHA.fullmatch(source_sha) is None:
        raise SbomError("source-sha must be a lowercase 40-character Git SHA")
    if not 1 <= expected_count <= 100:
        raise SbomError("expected-count must be between 1 and 100")
    created = _created_at(created_at)
    wheels = sorted(wheel_dir.glob("*.whl"), key=lambda path: path.name)
    if len(wheels) != expected_count:
        raise SbomError(
            f"expected exactly {expected_count} wheel files; found {len(wheels)}"
        )

    inventory = [_wheel_metadata(path) for path in wheels]
    names = [item["normalized_name"] for item in inventory]
    if len(names) != len(set(names)):
        raise SbomError("canonical wheel distribution names must be unique")
    canonical_ids = {
        item["normalized_name"]: f"SPDXRef-Package-{_spdx_token(item['normalized_name'])}"
        for item in inventory
    }
    inventory_digest = sha256(
        "\n".join(f"{item['filename']}:{item['sha256']}" for item in inventory).encode("utf-8")
    ).hexdigest()

    packages = [_canonical_package(item) for item in inventory]
    external_names = sorted(
        {
            requirement["name"]
            for item in inventory
            for requirement in item["requirements"]
            if requirement["name"] not in canonical_ids
        }
    )
    packages.extend(_external_dependency(name) for name in external_names)
    packages.sort(key=lambda item: item["SPDXID"])

    relationships: list[dict[str, str]] = []
    for item in inventory:
        package_id = canonical_ids[item["normalized_name"]]
        relationships.append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": package_id,
            }
        )
        for requirement in item["requirements"]:
            dependency_id = canonical_ids.get(
                requirement["name"],
                f"SPDXRef-Dependency-{_spdx_token(requirement['name'])}",
            )
            relationships.append(
                {
                    "spdxElementId": package_id,
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": dependency_id,
                }
            )
    relationships.sort(
        key=lambda item: (
            item["spdxElementId"],
            item["relationshipType"],
            item["relatedSpdxElement"],
        )
    )

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"promptops-release-candidate-{source_sha[:12]}",
        "documentNamespace": (
            f"https://github.com/{repository}/sbom/{source_sha}/{inventory_digest}"
        ),
        "creationInfo": {
            "created": created,
            "creators": ["Tool: promptops-spdx-sbom/1.0"],
        },
        "documentComment": (
            "Generated from exact release-candidate wheel subjects and their direct "
            "Core Metadata Requires-Dist declarations. This is not an OS/container "
            "inventory or a resolved transitive-environment SBOM."
        ),
        "packages": packages,
        "relationships": relationships,
    }


def _read_sbom(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SbomError(f"SBOM file is missing: {path}")
    if path.stat().st_size > MAX_SBOM_BYTES:
        raise SbomError(f"SBOM exceeds {MAX_SBOM_BYTES} bytes")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SbomError("SBOM is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise SbomError("SBOM root must be a JSON object")
    return value


def verify_sbom(
    path: Path,
    wheel_dir: Path,
    *,
    repository: str,
    source_sha: str,
    created_at: str,
    expected_count: int,
) -> dict[str, Any]:
    observed = _read_sbom(path)
    expected = build_sbom(
        wheel_dir,
        repository=repository,
        source_sha=source_sha,
        created_at=created_at,
        expected_count=expected_count,
    )
    if observed != expected:
        raise SbomError("SBOM does not match the exact wheel subjects and metadata")
    return expected


def _summary(sbom: dict[str, Any], *, verified: bool) -> dict[str, Any]:
    canonical_packages = [
        item
        for item in sbom["packages"]
        if str(item["SPDXID"]).startswith("SPDXRef-Package-")
    ]
    dependency_packages = [
        item
        for item in sbom["packages"]
        if str(item["SPDXID"]).startswith("SPDXRef-Dependency-")
    ]
    return {
        "status": "passed",
        "verified": verified,
        "canonical_wheel_count": len(canonical_packages),
        "external_direct_dependency_count": len(dependency_packages),
        "document_namespace": sbom["documentNamespace"],
        "sbom_sha256": sha256((_canonical(sbom) + "\n").encode("utf-8")).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SPDX 2.3 evidence for exact PromptOps wheels."
    )
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--expected-count", type=int, default=10)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            sbom = verify_sbom(
                Path(args.output),
                Path(args.wheel_dir),
                repository=args.repository,
                source_sha=args.source_sha,
                created_at=args.created_at,
                expected_count=args.expected_count,
            )
        else:
            sbom = build_sbom(
                Path(args.wheel_dir),
                repository=args.repository,
                source_sha=args.source_sha,
                created_at=args.created_at,
                expected_count=args.expected_count,
            )
            rendered = json.dumps(sbom, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
            Path(args.output).write_text(rendered, encoding="utf-8", newline="\n")
        print(_canonical(_summary(sbom, verified=args.verify)))
        return 0
    except (OSError, SbomError, TypeError, ValueError) as exc:
        print(f"SPDX SBOM gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
