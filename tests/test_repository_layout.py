"""Repository-layout tests: validation passes and the CLI runs in script mode."""
from __future__ import annotations

import os
import subprocess
import sys

from holo_zlib.validate import BANNED_NAMES, ROOT, SKILL_NAME, validate_all

SKILL_DIR = ROOT / "skills" / SKILL_NAME
ZLIB_PY = SKILL_DIR / "scripts" / "zlib.py"


def test_validate_all_passes():
    validate_all()


def test_skills_dir_has_only_holo_zlib():
    names = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    assert names == [SKILL_NAME]


def test_no_banned_files_in_skill():
    for path in SKILL_DIR.rglob("*"):
        assert path.name not in BANNED_NAMES, path


def test_requirements_txt_present():
    assert (SKILL_DIR / "scripts" / "requirements.txt").exists()


def test_zlib_cli_help_smoke():
    """The CLI --help works end to end (argument parsing).

    Note: --help short-circuits inside argparse before _load_client() runs, so this does
    NOT exercise the client import — test_zlib_cli_loads_client_in_script_mode does.
    """
    for argv in (["--help"], ["search", "--help"], ["download", "--help"]):
        result = subprocess.run(
            [sys.executable, str(ZLIB_PY), *argv],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_zlib_cli_loads_client_in_script_mode(tmp_path):
    """Run a real subcommand so _load_client() (the spec import of client.py) executes.

    Point credentials at a nonexistent file: the client loads, then raises ZlibError for
    the missing file (no network), which main() turns into a clean exit code 1 — proving
    the import seam works rather than a raw ImportError/traceback.
    """
    env = {**os.environ, "HOLO_ZLIB_CREDENTIALS_FILE": str(tmp_path / "nonexistent.json")}
    result = subprocess.run(
        [sys.executable, str(ZLIB_PY), "search", "anything"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Credentials file not found" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert "Traceback" not in result.stderr
