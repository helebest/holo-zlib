# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in
this repository.

## Common commands

Dependency and script management uses `uv` — not `pip` or a bare `python`. Run project
commands as `uv run ...`.

```bash
uv sync                                       # install the pinned dev environment
uv run holo-zlib-validate                     # validate skill layout + frontmatter + banned names
uv run ruff check .                           # lint
uv run ruff format .                          # format (use --check to verify only)
uv run python -m pytest -p no:cacheprovider   # full test suite
uv run python -m pytest tests/test_client.py -k name  # a single test
uv run holo-zlib-package                       # build dist/holo-zlib.skill
```

There is no CI workflow in this repository; run the lint, validate, and test steps
locally before committing.

## Architecture

This repo packages a single Claude Code skill from one canonical source. It is not a
runtime application.

### Single source of truth

- `skills/holo-zlib/` is the canonical, self-contained skill: `SKILL.md` with YAML
  frontmatter, `scripts/` (with its own `requirements.txt`), and `references/`. It is
  the only thing that ships to an agent.
- The skill runtime is **standard library only** (Python >= 3.10), zero third-party
  dependencies — keep it that way so the skill stays portable. `uv` / `pytest` / `ruff`
  are dev-time only.
- `scripts/zlib.py` is the CLI (argument parsing + output). `scripts/client.py` is the
  eAPI client (requests, auth, credential/path resolution). The CLI loads the client via
  `_load_client()`, which imports `client.py` by file spec rather than mutating
  `sys.path` — that avoids shadowing the standard-library `zlib` with the skill's
  `zlib.py`.
- Expected failures raise `client.ZlibError`; the CLI's `main()` catches it and returns
  a non-zero exit code. Do not reintroduce `sys.exit` inside the client.

### Repo-level tooling

`src/holo_zlib/` is the dev harness, **not** runtime code shipped to agents:

- `validate.py` — schema checks; defines `SKILL_NAME`, `BANNED_NAMES`, and the
  kebab-case `NAME_RE`. `validate_all()` asserts `skills/` contains exactly `holo-zlib`
  and that the skill is well-formed.
- `package.py` — zips `skills/holo-zlib/` into `dist/holo-zlib.skill`.

Both are exposed as console scripts in `pyproject.toml` (`holo-zlib-validate`,
`holo-zlib-package`).

### Safety contracts

- Credentials (`credentials/zlib.json`), local notes (`private/`), and downloads
  (`ebooks/`) live at the **repo root**, gitignored, and never inside the skill
  directory. Packaging only the skill directory means they cannot leak by construction.
- `package.py` keeps a danger gate that aborts if a credential-like path is ever about
  to be packaged; `validate.py` bans those same names inside the skill directory. Both
  are intentional defense-in-depth — preserve them.

### Test infrastructure

`tests/conftest.py` overrides pytest's built-in `tmp_path` fixture. On Windows under the
Codex sandbox, pytest creates basetemp with mode `0o700`, which can make directories
unreadable even to the creating process — the custom fixture uses platform-default ACLs
under `.tmp/pytest-local/`. The `client` / `zlib_cli` modules are loaded by file spec
(fresh per test) so module-level caches don't leak. The `mock_opener` fixture patches
`client._get_opener` to avoid real HTTP.

## Releasing

Driven by `pyproject.toml`'s `version` field. Bump it, update `CHANGELOG.md`, run
validate + tests, build the artifact with `holo-zlib-package`, and tag `vX.Y.Z`.
