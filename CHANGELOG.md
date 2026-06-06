# Changelog

All notable changes to this project will be documented in this file.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] - 2026-06-06

### Changed
- Search output now shows both score fields under honest labels — `Quality`
  (`qualityScore`) and `Popularity` (`interestScore`) — instead of a single ambiguous
  `Score` that printed `interestScore` while results were sorted by `qualityScore`. A
  `null` score renders as `?`.
- Rewrote the skill `description` for sharper triggering: dropped the misleading "libgen"
  reference (the skill only queries Z-Library), added intent-based phrasings, and added an
  explicit negative scope (not for academic papers, non-book media, or local-file tasks).
- SKILL.md overhaul: replaced the undefined `{baseDir}` placeholder with skill-relative
  paths; switched examples from `python3` to `python` with an accurate cross-platform note;
  added a Workflow section, an end-to-end search→download example, and result-selection
  guidance; split download troubleshooting into stale-hash vs. quota cases and added
  timeout and batch-quota guidance.
- Broadened the `--ext` help text to reflect that the value is passed through to the API
  unvalidated (any format Z-Library supports works).
- Softened the daily-quota docs (the API reports neither the count nor the reset time).

### Fixed
- Corrected the README installation instructions: Claude Code discovers skills as
  directories under `.claude/skills/` (project) or `~/.claude/skills/` (personal) with no
  install/import step; the packaged `.skill` zip is for claude.ai and the Claude API
  (`/v1/skills`), not Claude Code.

### Added
- Tests asserting the new `Quality`/`Popularity` output labels and `null`-score rendering.

## [0.2.0]

### Changed
- Restructured the repository into a single-source skill layout: the skill now lives in
  `skills/holo-zlib/` (self-contained: `SKILL.md` + `scripts/` + `references/`).
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
