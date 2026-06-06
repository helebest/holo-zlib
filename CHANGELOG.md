# Changelog

All notable changes to this project will be documented in this file.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0]

### Changed
- Restructured the repository to match the `holo-wechat-mpskills` engineering layout:
  the skill now lives in `skills/holo-zlib/` (self-contained: `SKILL.md` + `scripts/` +
  `references/`).
- Split the monolithic `scripts/zlib.py` into `client.py` (eAPI client) and `zlib.py`
  (CLI), wired with a spec-based dynamic import. Client errors now raise `ZlibError`
  instead of calling `sys.exit`; the CLI's `main()` returns the exit code.
- Moved the packager into the new dev harness `src/holo_zlib/` and added a single-skill
  `validate.py`. Both are exposed as console scripts: `holo-zlib-validate`,
  `holo-zlib-package`.
- Removed the `zlib.sh` wrapper; the skill is invoked directly with
  `python3 skills/holo-zlib/scripts/zlib.py …`.
- Switched all documentation and source comments to English.

### Added
- `references/eapi.md` (public eAPI reference), `CLAUDE.md`, `scripts/requirements.txt`,
  and `tests/test_repository_layout.py` (layout validation + CLI `--help` smoke test).
- README badges, an MIT License section, and an "Installation & usage" section with a
  copy-paste setup prompt for Claude Code and Codex.
- Windows-safe `tmp_path` pytest fixture; tests split into `test_client.py` /
  `test_cli.py`; `ruff` added as a dev dependency.

### Removed
- `tools/package_skill.py` (moved to `src/holo_zlib/package.py`), `.claudeignore`, and
  `scripts/zlib.sh` (obsoleted by structural isolation and direct Python invocation).

## [0.1.0] - prototype

- The original `SKILL.md` + `scripts/zlib.py` + `scripts/zlib.sh` trio — search and
  download working end to end.
