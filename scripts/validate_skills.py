#!/usr/bin/env python3
"""Validate the portable skill packages advertised by DeepSkill."""

from pathlib import Path
import re
import sys

EXPECTED = (
    "deepwiki-harvester",
    "agent-skills-engineering",
    "agent-orchestration-patterns",
    "agent-memory-systems",
    "agent-security-sandboxing",
    "llm-finetuning-patterns",
    "rag-llm-serving-patterns",
    "backend-platform-patterns",
    "frontend-monorepo-patterns",
    "scraping-mcp-automation-patterns",
)
FRONTMATTER = re.compile(
    r"^---\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\n",
    re.MULTILINE,
)

def main() -> int:
    failures: list[str] = []
    root = Path(__file__).resolve().parents[1] / "skills"
    for name in EXPECTED:
        path = root / name / "SKILL.md"
        if not path.is_file():
            failures.append(f"missing {path.relative_to(root.parent)}")
            continue
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            failures.append(f"invalid frontmatter: {path.relative_to(root.parent)}")
            continue
        declared, description = (value.strip() for value in match.groups())
        if declared != name:
            failures.append(
                f"name mismatch: {path.relative_to(root.parent)} declares {declared!r}"
            )
        if not description.startswith("Use when "):
            failures.append(
                f"description must start with 'Use when ': {path.relative_to(root.parent)}"
            )
        if len(text.splitlines()) > 500:
            failures.append(f"over 500 lines: {path.relative_to(root.parent)}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"validated {len(EXPECTED)} skill packages")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
