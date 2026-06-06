"""Validation for the canonical holo-zlib skill repository.

Single-skill variant: there is exactly one canonical source, skills/holo-zlib/, with no
multi-platform plugins/marketplace. Checks the skill directory name, SKILL.md
frontmatter, the presence of scripts/requirements.txt, and that the skill contains none
of the banned names (dev tooling / credentials / data).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"
SKILL_NAME = "holo-zlib"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Names that must never appear inside the skill directory: dev tooling, secrets, local
# data. This is the backstop to structural isolation and makes validation fail early in
# CI / locally.
BANNED_NAMES = {
    ".env",
    ".venv",
    ".claudeignore",
    "CHANGELOG.md",
    "README.md",
    "dist",
    "pyproject.toml",
    "uv.lock",
    "credentials",
    "private",
    "ebooks",
    "zlib.json",
}
# Compared case-insensitively: Windows preserves on-disk case, so an `Ebooks` dir or
# `README.MD` would otherwise slip past an exact-match check.
_BANNED_LOWER = {name.lower() for name in BANNED_NAMES}


class ValidationError(Exception):
    """Raised when repository validation fails."""


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if match is None:
        raise ValidationError("pyproject.toml is missing project version")
    return match.group(1)


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse a SKILL.md YAML frontmatter block (tolerant of LF / CRLF line endings)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError(f"{path} is missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(f"{path} has unterminated YAML frontmatter") from exc

    data: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValidationError(f"{path} has invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def validate_skill(skill_dir: Path) -> None:
    name = skill_dir.name
    if not NAME_RE.match(name):
        raise ValidationError(f"Invalid skill directory name: {name}")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValidationError(f"Missing {skill_md}")

    frontmatter = parse_frontmatter(skill_md)
    if frontmatter.get("name") != name:
        raise ValidationError(f"{skill_md} name must match directory name")
    if not frontmatter.get("description"):
        raise ValidationError(f"{skill_md} description is required")

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists() and not (scripts_dir / "requirements.txt").exists():
        raise ValidationError(f"{scripts_dir} must contain requirements.txt")

    for path in skill_dir.rglob("*"):
        if path.name.lower() in _BANNED_LOWER:
            raise ValidationError(f"Banned file or directory in skill package: {path}")


def validate_all() -> None:
    if not SKILLS_DIR.exists():
        raise ValidationError("Missing skills directory")

    actual = sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())
    if actual != [SKILL_NAME]:
        raise ValidationError(f"Unexpected skills: {actual}")

    validate_skill(SKILLS_DIR / SKILL_NAME)


def main() -> int:
    try:
        validate_all()
    except Exception as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print("validation ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
