#!/usr/bin/env python3
"""Validate the consolidated portfolio compatibility/archive contract.

This checker is deliberately offline. External consumer-search and source-repo
redirect evidence are recorded in the manifest, while CI proves that the
recorded canonical package identity still matches the repository and that
archive readiness cannot become true unless every explicit gate is true.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "portfolio-compatibility.v1.json"
REHEARSAL = ROOT / ".portfolio-rehearsal.json"
EXPECTED = {
    "answer-diff",
    "benchmark-run-recorder",
    "consensus-engine",
    "eval-dataset-builder",
    "llm-jury",
    "model-scorecard",
    "multi-agent-failure-corpus",
    "prompt-package-manager",
    "prompt-regression",
}
REQUIRED_GATES = (
    "compatibility_verified",
    "consumer_scan_completed",
    "redirect_ready",
    "rollback_documented",
    "human_archive_approval",
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.name}: root must be an object")
    return value


def validate_redirect_evidence(name: str, item: dict) -> None:
    evidence = item.get("redirect_evidence")
    if item.get("redirect_ready") is not True:
        return
    if not isinstance(evidence, dict):
        fail(f"{name}: redirect_ready requires redirect_evidence")
    if not isinstance(evidence.get("pr"), int) or evidence["pr"] <= 0:
        fail(f"{name}: redirect PR must be a positive integer")
    if evidence.get("path") != "README.md":
        fail(f"{name}: redirect notice must be recorded on README.md")
    if evidence.get("ci") != "success":
        fail(f"{name}: redirect_ready requires successful source-repo CI evidence")
    merge_sha = evidence.get("merge_sha")
    if not isinstance(merge_sha, str) or SHA40.fullmatch(merge_sha) is None:
        fail(f"{name}: redirect merge_sha must be a 40-character lowercase SHA")


def main() -> int:
    manifest = load_json(MANIFEST)
    rehearsal = load_json(REHEARSAL)

    if manifest.get("schema_version") != "1.0":
        fail("unsupported portfolio compatibility schema")
    if manifest.get("canonical_repository") != "vigilanty0x/promptops":
        fail("canonical_repository must remain vigilanty0x/promptops")

    packages = manifest.get("packages")
    if not isinstance(packages, list) or len(packages) != len(EXPECTED):
        fail("manifest must contain exactly nine packages")

    rehearsal_sources = {
        item["repository"]: item
        for item in rehearsal.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("repository"), str)
    }
    seen: set[str] = set()

    for item in packages:
        if not isinstance(item, dict):
            fail("package entries must be objects")
        source = item.get("source_repository")
        if not isinstance(source, str) or not source.startswith("vigilanty0x/"):
            fail("source_repository must use the vigilanty0x owner")
        name = source.split("/", 1)[1]
        if name in seen:
            fail(f"duplicate package: {name}")
        seen.add(name)
        if name not in EXPECTED:
            fail(f"unexpected package: {name}")

        expected_path = f"packages/{name}"
        if item.get("canonical_path") != expected_path:
            fail(f"{name}: canonical path mismatch")
        pyproject_path = ROOT / expected_path / "pyproject.toml"
        if not pyproject_path.is_file():
            fail(f"{name}: missing pyproject.toml")
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
        if project.get("name") != item.get("distribution") or project.get("name") != name:
            fail(f"{name}: distribution identity changed")
        if project.get("version") != item.get("version"):
            fail(f"{name}: version evidence is stale")
        scripts = project.get("scripts", {})
        if not isinstance(scripts, dict) or item.get("cli") not in scripts:
            fail(f"{name}: recorded CLI is not installed by pyproject")
        if item.get("cli") != name:
            fail(f"{name}: CLI compatibility changed")

        source_evidence = rehearsal_sources.get(name)
        if source_evidence is None:
            fail(f"{name}: missing imported-history evidence")
        if source_evidence.get("headSha") != item.get("source_head_sha"):
            fail(f"{name}: source head evidence mismatch")
        if source_evidence.get("treeSha") != item.get("source_tree_sha"):
            fail(f"{name}: source tree evidence mismatch")
        if source_evidence.get("treeMatch") is not True or source_evidence.get("ancestor") is not True:
            fail(f"{name}: imported history/tree is not verified")

        if not isinstance(item.get("exact_reference_matches"), int) or item["exact_reference_matches"] < 0:
            fail(f"{name}: exact_reference_matches must be a non-negative integer")
        for gate in REQUIRED_GATES:
            if not isinstance(item.get(gate), bool):
                fail(f"{name}: {gate} must be explicit boolean")
        validate_redirect_evidence(name, item)
        computed_ready = all(item[gate] for gate in REQUIRED_GATES)
        if item.get("archive_ready") is not computed_ready:
            fail(f"{name}: archive_ready must equal all explicit gates")
        if item.get("archive_ready") is True and item.get("exact_reference_matches") != 0:
            fail(f"{name}: cannot archive with known exact repository consumers")

    if seen != EXPECTED:
        fail("manifest package set is incomplete")

    blocked = sorted(
        item["source_repository"]
        for item in packages
        if item["archive_ready"] is False
    )
    redirects = sum(1 for item in packages if item["redirect_ready"] is True)
    print(f"portfolio compatibility: {len(packages)} packages verified")
    print(f"redirect gate: {redirects}/{len(packages)} verified")
    print(f"archive gate: {'READY' if not blocked else 'BLOCKED'}")
    if blocked:
        print("blocked repositories: " + ", ".join(blocked))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"portfolio compatibility check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
