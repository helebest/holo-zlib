"""Package skills/holo-zlib/ into a .skill distribution archive (a .skill-suffixed zip).

Only the skill directory is packaged, which keeps the repo's dev tooling out. But
isolation is NOT a full guarantee for secrets: the skill's own runtime fallback can place
credentials/downloads *inside* the skill directory (<skill>/credentials/zlib.json,
<skill>/ebooks/) when no project-root copy exists. So two layered guards run on every
build and both are load-bearing:

  1. validate_all() runs first and rejects BANNED_NAMES (.env, .venv, credentials,
     private, ebooks, zlib.json, ...) anywhere in the skill directory.
  2. The danger gate re-scans the exact paths about to be packaged (case-insensitively)
     and aborts on any credential-like match.

Usage:
  python3 -m holo_zlib.package [--out PATH]
  # after install: holo-zlib-package [--out PATH]
Default output is dist/holo-zlib.skill; --out sets an explicit file path.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import zipfile
from pathlib import Path

from .validate import ValidationError, parse_frontmatter, validate_all

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "holo-zlib"

# Cache/junk files that must not be packaged (basename globs; plus the __pycache__ dir).
_EXCLUDE_GLOBS = ("*.pyc", "*.pyo", "*.swp", ".DS_Store", "Thumbs.db")

# Danger gate: if these words/patterns appear in a packaged path, abort.
_DANGER_PATTERNS = (
    "credentials/",
    "private/",
    "ebooks/",
    "*credentials*.json",
    "zlib.json",
    "*.creds.json",
)


def _is_excluded(rel_path: str) -> bool:
    parts = rel_path.split("/")
    if "__pycache__" in parts:
        return True
    return any(fnmatch.fnmatch(parts[-1], pat) for pat in _EXCLUDE_GLOBS)


def _is_dangerous(rel_path: str) -> str | None:
    """Return the triggered danger pattern, or None. Case-insensitive (Windows-safe)."""
    lowered = rel_path.lower()
    parts = lowered.split("/")
    base = os.path.basename(lowered)
    for pat in _DANGER_PATTERNS:
        low_pat = pat.lower()
        if low_pat.endswith("/"):
            if low_pat[:-1] in parts:
                return pat
        elif fnmatch.fnmatch(base, low_pat):
            return pat
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the holo-zlib skill into a .skill")
    parser.add_argument("--out", help="Output file path (default dist/<skill_name>.skill)")
    args = parser.parse_args()

    # Validate the skill layout first — this rejects BANNED_NAMES (.env, .venv, etc.) that
    # the danger gate below does not list, so packaging never ships them.
    try:
        validate_all()
    except ValidationError as exc:
        print(f"ERROR: validation failed: {exc}", file=sys.stderr)
        return 1

    skill_md = SKILL_DIR / "SKILL.md"
    if not skill_md.exists():
        print(f"ERROR: missing {skill_md}", file=sys.stderr)
        return 1

    try:
        skill_name = parse_frontmatter(skill_md).get("name")
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not skill_name:
        print("ERROR: SKILL.md frontmatter is missing the name field", file=sys.stderr)
        return 1

    # Collect files to include (relative to the skill root).
    included: list[tuple[Path, str]] = []
    skipped: list[str] = []
    for fp in sorted(SKILL_DIR.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(SKILL_DIR).as_posix()
        if _is_excluded(rel):
            skipped.append(rel)
            continue
        included.append((fp, rel))

    # Danger gate.
    danger_hits = [(rel, _is_dangerous(rel)) for _, rel in included]
    danger_hits = [(rel, pat) for rel, pat in danger_hits if pat]
    if danger_hits:
        print(
            "ERROR: danger gate triggered — these files must not be packaged; "
            "check the skill directory:",
            file=sys.stderr,
        )
        for rel, pat in danger_hits:
            print(f"   {rel}   [matched {pat}]", file=sys.stderr)
        return 1

    out_path = Path(args.out).resolve() if args.out else ROOT / "dist" / f"{skill_name}.skill"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    print(f"Packaging skill: {skill_name}")
    print(f"   source: {SKILL_DIR}")
    print(f"   output: {out_path}\n")

    total_size = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp, rel in included:
            arc = f"{skill_name}/{rel}"
            zf.write(fp, arc)
            size = fp.stat().st_size
            total_size += size
            print(f"  + {arc}  ({size} B)")

    print(f"\nDone: {out_path}")
    print(
        f"   {len(included)} files, {total_size} B uncompressed, "
        f"{out_path.stat().st_size} B compressed"
    )
    if skipped:
        print(f"   skipped {len(skipped)} (cache/junk files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
