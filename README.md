# holo-zlib

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue.svg)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib--only-brightgreen.svg)
![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-8A2BE2.svg)

A Claude Code skill that searches and downloads ebooks from Z-Library via the eAPI.
It uses the Python standard library only — runs on Python >= 3.10 with no third-party
dependencies.

## Repository layout

```
holo-zlib/
├── skills/
│   └── holo-zlib/              # canonical, self-contained skill (this is what ships)
│       ├── SKILL.md            # skill entry point (loaded by the agent)
│       ├── scripts/
│       │   ├── client.py       # eAPI client (requests / auth / path resolution)
│       │   ├── zlib.py         # CLI (search / download)
│       │   └── requirements.txt# stdlib-only marker (no runtime deps)
│       └── references/
│           └── eapi.md         # eAPI endpoints / fields reference
├── src/holo_zlib/             # dev harness (validation + packaging; not shipped)
├── tests/                     # pytest unit + layout tests
├── evals/evals.json           # skill-creator eval set
├── CLAUDE.md                  # guidance for Claude Code
├── pyproject.toml             # dev tooling only (pytest, ruff); runtime needs none
└── uv.lock
```

## Installation & usage

The skill is portable and dependency-free at runtime. Credentials and downloads live
outside the skill directory (at your project root) so they never ship with the skill.

Invocation uses `python`; on Linux/macOS where only `python3` exists, substitute it. On
Windows, `python` (from a venv or the Microsoft Store) works; the `py` launcher is not
always installed, so don't rely on `py -3`.

### Claude Code

Claude Code discovers skills as **directories** — there is no install command and no
`.skill` import step. Place the skill folder in one of these locations and it is picked up
automatically (Claude consults it based on the `description` in its `SKILL.md`
frontmatter, or you can invoke it by name):

- **Project** (commit it to share with the repo): `<project>/.claude/skills/holo-zlib/`
- **Personal** (available in all your projects): `~/.claude/skills/holo-zlib/`

```bash
git clone <repo-url>
mkdir -p .claude/skills
cp -r holo-zlib/skills/holo-zlib .claude/skills/holo-zlib   # or symlink it
```

**Credentials**: create `credentials/zlib.json` at your **project root** (the script walks
upward to find it; the `.claude` sibling counts as an ancestor).

### claude.ai / Claude API

The packaged `.skill` (a zip built by `uv run holo-zlib-package` → `dist/holo-zlib.skill`)
is for these platforms — **not** Claude Code:

- **claude.ai**: upload the `.skill` in settings (the Capabilities/Features area, on a
  plan with code execution enabled).
- **Claude API**: upload via the `/v1/skills` endpoints (currently beta — header
  `skills-2025-10-02`).

### Codex / direct CLI

`git clone <repo-url>`; work inside the repo or place `skills/holo-zlib/` where the agent
can see it, then call the CLI directly — stdlib only, nothing to install:

```bash
python skills/holo-zlib/scripts/zlib.py search "title" --ext epub --limit 5
```

**Credentials**: same as above — `credentials/zlib.json` at the repo/project root.

### Copy-paste prompt for an agent

Paste this to Claude Code or Codex to set it up and use it end to end:

```text
Install and use the holo-zlib skill (Z-Library ebook search/download, pure Python stdlib):
1. If .claude/skills/holo-zlib/ does not exist in this project, git clone <repo-url> and
   copy its skills/holo-zlib/ into .claude/skills/holo-zlib/.
2. Create credentials/zlib.json at the project root:
   {"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
   (log in at https://z-library.sk and take remix_userid / remix_userkey from cookies).
3. Search Z-Library for an epub of "The Three-Body Problem", top 5, pick the best
   match, and show me its book_id and hash.
4. Ensure an ebooks/ directory exists at the project root (create it if missing — that is
   where the default download location resolves), then after I confirm, download the one
   I pick into it and tell me the final file path.
(Invocation: python skills/holo-zlib/scripts/zlib.py search/download … — on Linux/macOS
substitute python3 if needed.)
```

> Replace `<repo-url>` with the actual repository URL once it is pushed.

## Quick start (local)

```bash
# 1. Create the credentials file (log in to https://z-library.sk, copy two cookie values)
mkdir -p credentials
cat > credentials/zlib.json <<'EOF'
{"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
EOF

# 2. (optional) create ebooks/ here so downloads default to the project root
mkdir -p ebooks

# 3. Try it (use python; on Linux/macOS substitute python3 if needed)
python skills/holo-zlib/scripts/zlib.py search "The Three-Body Problem" --ext epub --limit 3
```

> The download default resolves to the first existing `ebooks/` found while walking up
> from the skill directory. If none exists, it falls back to `<skill>/ebooks/` inside the
> skill itself — create an `ebooks/` at your project root (as above) to keep downloads out
> of the skill, or pass `--output <dir>` per call.

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `HOLO_ZLIB_CREDENTIALS_FILE` | Credentials file path | first `credentials/zlib.json` found walking up from the skill dir; else `<skill>/credentials/zlib.json` |
| `HOLO_ZLIB_EBOOKS_DIR` | Download directory (CLI `--output` still overrides) | first existing `ebooks/` walking up from the skill dir; else `<skill>/ebooks` |

## Development

Dependency and script management uses `uv` (dev only; the skill runtime needs none):

```bash
uv sync                                  # install the pinned dev environment
uv run holo-zlib-validate                # validate skill layout + frontmatter + banned names
uv run ruff check .                      # lint
uv run python -m pytest -p no:cacheprovider  # run the test suite
uv run holo-zlib-package                 # build dist/holo-zlib.skill (with a credential danger gate)
```

## License

MIT — see [LICENSE](./LICENSE).
