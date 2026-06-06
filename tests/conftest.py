"""Shared pytest fixtures.

The client module keeps `_credentials` / `_opener` as module-level caches. Loading a
fresh copy per test (via importlib spec) keeps those caches from leaking between tests
and avoids touching sys.path (which could shadow the standard-library `zlib`).
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import uuid
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "holo-zlib" / "scripts"


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Create temp dirs without pytest's Windows 0o700 ACL handling.

    In the Codex Windows sandbox, directories created with mode 0o700 can become
    unreadable even to the creating process. Pytest's built-in tmp_path uses that mode
    for basetemp, so keep this repository's temp dirs local and create them with the
    platform default ACL instead.
    """
    root = Path(request.config.rootpath) / ".tmp" / "pytest-local"
    root.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name).strip("_")
    path = root / f"{safe_name}-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _load_module(module_name: str, filename: str):
    """Load a script module by file path (not via sys.path)."""
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A clean copy of the client module with credentials pointed at a temp file.

    `client.py` has no stdlib name collision (unlike `zlib.py`), but it is still loaded
    by spec for per-test cache isolation.
    """
    module = _load_module("zlib_client", "client.py")

    creds_file = tmp_path / "zlib.json"
    creds_file.write_text(json.dumps({"remix_userid": "uid_test", "remix_userkey": "key_test"}))
    monkeypatch.setattr(module, "CREDENTIALS_FILE", str(creds_file))
    monkeypatch.setattr(module, "DOWNLOAD_DIR", str(tmp_path / "books"))

    module._credentials = None
    module._opener = None
    return module


@pytest.fixture
def zlib_cli():
    """The CLI module. Its cmd_* functions take a `client` argument; tests pass the
    `client` fixture so the CLI exercises the same patched module the test set up."""
    return _load_module("zlib_script", "zlib.py")


@pytest.fixture
def mock_opener(monkeypatch, client):
    """A programmable opener that replaces real urllib requests.

    Usage:
        mock_opener.queue = [b'{"success": 1, "books": []}']
        # or queue an exception to simulate failure:
        mock_opener.queue = [URLError("unreachable")]
    """

    class _MockResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self, size=-1):
            if size == -1 or size >= len(self._payload):
                chunk, self._payload = self._payload, b""
                return chunk
            chunk, self._payload = self._payload[:size], self._payload[size:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _MockOpener:
        def __init__(self):
            self.queue: list = []
            self.calls: list = []

        def open(self, req, timeout=None):
            self.calls.append(
                {
                    "url": req.full_url,
                    "method": req.get_method(),
                    "timeout": timeout,
                    # urllib capitalizes header keys (e.g. "Remix-userid", "Cookie").
                    "headers": dict(req.header_items()),
                    "body": req.data,
                }
            )
            if not self.queue:
                raise AssertionError("mock opener queue exhausted")
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return _MockResponse(item)

    opener = _MockOpener()
    monkeypatch.setattr(client, "_get_opener", lambda: opener)
    return opener
