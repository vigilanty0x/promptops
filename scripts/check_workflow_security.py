"""Fail-closed static security checks for GitHub Actions workflows.

This checker intentionally uses only the Python standard library.  It is not a
full YAML parser; instead it enforces a small, explicit workflow policy over the
repository's workflow text.  If a future workflow needs broader permissions or
new trigger semantics, this policy must be changed in the same review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USE = re.compile(r"^(?P<indent>\s*)-?\s*uses:\s*(?P<value>[^\s#]+)")
JOB = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$")
TIMEOUT = re.compile(r"^    timeout-minutes:\s*(?P<minutes>\d+)\s*(?:#.*)?$")
PERMISSION_ENTRY = re.compile(r"^(?P<indent>\s+)(?P<name>[A-Za-z0-9_-]+):\s*(?P<value>[^\s#]+)")


class WorkflowSecurityError(ValueError):
    """Raised when a workflow violates the repository security policy."""


@dataclass(frozen=True, slots=True)
class WorkflowSecurityReceipt:
    workflows: int
    jobs: int
    external_actions: int
    checkout_steps: int


def _workflow_paths(root: Path) -> list[Path]:
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        raise WorkflowSecurityError(".github/workflows is missing")
    paths = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    if not paths:
        raise WorkflowSecurityError("no GitHub Actions workflow files found")
    return paths


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _permission_blocks(lines: list[str], *, path: Path) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        if not re.match(r"^\s*permissions:\s*$", line):
            continue
        parent_indent = _indent(line)
        values: dict[str, str] = {}
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                cursor += 1
                continue
            if _indent(candidate) <= parent_indent:
                break
            match = PERMISSION_ENTRY.match(candidate)
            if not match:
                raise WorkflowSecurityError(
                    f"{path.name}: unsupported permissions syntax on line {cursor + 1}"
                )
            values[match.group("name")] = match.group("value")
            cursor += 1
        blocks.append(values)
    return blocks


def _step_block(lines: list[str], start: int) -> list[str]:
    base_indent = _indent(lines[start])
    block = [lines[start]]
    cursor = start + 1
    while cursor < len(lines):
        line = lines[cursor]
        stripped = line.lstrip()
        if _indent(line) == base_indent and stripped.startswith("- "):
            break
        if _indent(line) < base_indent:
            break
        block.append(line)
        cursor += 1
    return block


def validate_workflow_text(text: str, *, path: Path) -> tuple[int, int, int]:
    if "\t" in text:
        raise WorkflowSecurityError(f"{path.name}: tabs are not allowed in workflow YAML")
    lines = text.splitlines()

    forbidden_triggers = ("pull_request_target:", "workflow_run:")
    for trigger in forbidden_triggers:
        if any(line.strip().startswith(trigger) for line in lines):
            raise WorkflowSecurityError(f"{path.name}: forbidden privileged trigger {trigger[:-1]}")

    permission_blocks = _permission_blocks(lines, path=path)
    if not permission_blocks:
        raise WorkflowSecurityError(f"{path.name}: explicit permissions block is required")
    for block in permission_blocks:
        if block != {"contents": "read"}:
            raise WorkflowSecurityError(
                f"{path.name}: permissions must be exactly contents: read; got {block}"
            )

    jobs: list[tuple[str, int, int]] = []
    in_jobs = False
    current: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        if line == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" "):
            if current is not None:
                jobs.append((current[0], current[1], index))
                current = None
            break
        match = JOB.match(line)
        if match:
            if current is not None:
                jobs.append((current[0], current[1], index))
            current = (match.group("name"), index)
    if current is not None:
        jobs.append((current[0], current[1], len(lines)))
    if not jobs:
        raise WorkflowSecurityError(f"{path.name}: workflow must contain at least one job")
    for name, start, end in jobs:
        timeouts = [TIMEOUT.match(line) for line in lines[start + 1 : end]]
        timeouts = [match for match in timeouts if match]
        if len(timeouts) != 1:
            raise WorkflowSecurityError(
                f"{path.name}: job {name} must define timeout-minutes exactly once"
            )
        minutes = int(timeouts[0].group("minutes"))
        if not 1 <= minutes <= 60:
            raise WorkflowSecurityError(
                f"{path.name}: job {name} timeout-minutes must be between 1 and 60"
            )

    external_actions = 0
    checkout_steps = 0
    for index, line in enumerate(lines):
        match = USE.match(line)
        if not match:
            continue
        value = match.group("value")
        if value.startswith("./"):
            continue
        if "@" not in value:
            raise WorkflowSecurityError(
                f"{path.name}: external action on line {index + 1} must be pinned by commit SHA"
            )
        action, ref = value.rsplit("@", 1)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?", action):
            raise WorkflowSecurityError(
                f"{path.name}: unsupported external action reference {value!r}"
            )
        if FULL_SHA.fullmatch(ref) is None:
            raise WorkflowSecurityError(
                f"{path.name}: external action {action} must use a full 40-hex commit SHA"
            )
        external_actions += 1
        if action == "actions/checkout":
            checkout_steps += 1
            block = _step_block(lines, index)
            if not any(re.match(r"^\s+persist-credentials:\s*false\s*(?:#.*)?$", item) for item in block):
                raise WorkflowSecurityError(
                    f"{path.name}: actions/checkout must set persist-credentials: false"
                )

    if external_actions == 0:
        raise WorkflowSecurityError(f"{path.name}: workflow has no external action references to verify")
    if checkout_steps == 0:
        raise WorkflowSecurityError(f"{path.name}: workflow must contain an actions/checkout step")
    return len(jobs), external_actions, checkout_steps


def validate_workflows(root: Path = ROOT) -> WorkflowSecurityReceipt:
    workflows = _workflow_paths(Path(root))
    job_count = 0
    action_count = 0
    checkout_count = 0
    for path in workflows:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise WorkflowSecurityError(f"cannot read workflow: {path.name}") from exc
        jobs, actions, checkouts = validate_workflow_text(text, path=path)
        job_count += jobs
        action_count += actions
        checkout_count += checkouts
    return WorkflowSecurityReceipt(
        workflows=len(workflows),
        jobs=job_count,
        external_actions=action_count,
        checkout_steps=checkout_count,
    )


def main() -> int:
    try:
        receipt = validate_workflows()
    except WorkflowSecurityError as exc:
        raise SystemExit(f"workflow security gate: {exc}") from exc
    print(
        "workflow security verified: "
        f"workflows={receipt.workflows} jobs={receipt.jobs} "
        f"external_actions={receipt.external_actions} checkout_steps={receipt.checkout_steps}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
