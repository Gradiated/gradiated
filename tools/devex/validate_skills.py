#!/usr/bin/env python3
"""Validate repo-local Codex skills without external dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing frontmatter") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    name = path.parent.name
    if not NAME_RE.fullmatch(name):
        errors.append(f"invalid directory name {name!r}")
    try:
        metadata = frontmatter(path.read_text())
    except (OSError, ValueError) as exc:
        return [f"{path}: {exc}"]
    if metadata.get("name") != name:
        errors.append(f"frontmatter name must be {name!r}")
    if not metadata.get("description"):
        errors.append("frontmatter description is empty")
    ui = path.parent / "agents" / "openai.yaml"
    if not ui.is_file():
        errors.append("missing agents/openai.yaml")
    else:
        ui_text = ui.read_text()
        for field in ("display_name", "short_description", "default_prompt"):
            if f"  {field}:" not in ui_text:
                errors.append(f"openai.yaml missing interface.{field}")
        if f"$${name}" in ui_text or f"${name}" not in ui_text:
            errors.append(f"openai.yaml default_prompt must mention ${name}")
    return [f"{path}: {error}" for error in errors]


def main() -> int:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    if not skills:
        print(f"no skills found under {SKILLS}", file=sys.stderr)
        return 1
    errors = [error for path in skills for error in validate(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {len(skills)} repo-local skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
