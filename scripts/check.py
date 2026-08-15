"""Fast syntax, fixture, and public-boundary checks."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
TOKEN = re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}")


def main() -> int:
    python_files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))
    python_files += [ROOT / "scripts" / "check.py"]
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in sorted((ROOT / "examples").glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", "build", "dist", "__pycache__"} for part in path.parts):
            continue
        if path.suffix in {".pyc", ".whl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PRIVATE_KEY.search(text) or TOKEN.search(text):
            raise SystemExit(f"secret-shaped content found in {path.relative_to(ROOT)}")
    print(f"checked {len(python_files)} Python files and public JSON fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
