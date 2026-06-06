#!/usr/bin/env python3
"""Z-Library eAPI client (standard library only, Python 3.10+).

Wraps credential loading, path resolution, and eAPI requests. Expected errors are
raised as ``ZlibError`` and handled by the CLI layer (``zlib.py``). The module-level
``_get_opener`` cache is the seam tests use to inject a fake opener.

Environment variables:
  HOLO_ZLIB_CREDENTIALS_FILE  Path to the credentials file. When unset, walk up from
                              the skill directory looking for credentials/zlib.json;
                              fall back to <skill>/credentials/zlib.json.
  HOLO_ZLIB_EBOOKS_DIR        Download directory. When unset, walk up from the skill
                              directory looking for an existing ebooks/ directory;
                              fall back to <skill>/ebooks. The CLI --output still
                              overrides this value.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ZlibError(RuntimeError):
    """An expected client-layer error (missing credentials / network / parsing).

    The CLI catches it and exits with a non-zero status.
    """


# The skill directory is the parent of scripts/. As a standalone repo it is
# skills/holo-zlib/; when installed under <proj>/.claude/skills/holo-zlib/ the real
# "project root" is higher up. So credentials/ebooks are located by walking upward
# from here until a match is found or the filesystem root is reached.
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CRED_FILENAME = "zlib.json"

BASE_URL = "https://z-library.sk"
_USER_AGENT = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"

# Module-level caches.
_credentials = None
_opener = None


def _walk_up(start: str):
    """Yield each directory from ``start`` upward, including ``start`` itself."""
    cur = os.path.abspath(start)
    while True:
        yield cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return
        cur = parent


def _resolve_credentials_file() -> str:
    env = os.environ.get("HOLO_ZLIB_CREDENTIALS_FILE")
    if env:
        return os.path.expanduser(env)
    for base in _walk_up(_SKILL_DIR):
        cand = os.path.join(base, "credentials", _CRED_FILENAME)
        if os.path.exists(cand):
            return cand
    # Not found: fall back to the default path under the skill dir; load_credentials
    # will raise a clear error.
    return os.path.join(_SKILL_DIR, "credentials", _CRED_FILENAME)


def _resolve_download_dir() -> str:
    env = os.environ.get("HOLO_ZLIB_EBOOKS_DIR")
    if env:
        return os.path.expanduser(env)
    # Prefer an existing ebooks/ directory; otherwise fall back under the skill dir
    # (the first download creates it).
    for base in _walk_up(_SKILL_DIR):
        cand = os.path.join(base, "ebooks")
        if os.path.isdir(cand):
            return cand
    return os.path.join(_SKILL_DIR, "ebooks")


CREDENTIALS_FILE = _resolve_credentials_file()
DOWNLOAD_DIR = _resolve_download_dir()


def load_credentials():
    """Load and cache credentials; raise ZlibError if the file is missing."""
    global _credentials
    if _credentials is not None:
        return _credentials
    if not os.path.exists(CREDENTIALS_FILE):
        raise ZlibError(
            f"Credentials file not found: {CREDENTIALS_FILE}\n"
            'Create it with: {"remix_userid": "...", "remix_userkey": "..."}'
        )
    with open(CREDENTIALS_FILE, encoding="utf-8") as f:
        _credentials = json.load(f)
    return _credentials


def _get_opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener()
    return _opener


def make_request(path, data=None, method="POST"):
    """Send an eAPI request (POST uses header auth, GET uses cookie auth).

    Raises ZlibError on network, timeout, or non-JSON responses.
    """
    creds = load_credentials()
    url = f"{BASE_URL}{path}"

    if method == "GET":
        headers = {
            "User-Agent": _USER_AGENT,
            "Cookie": (
                f"remix_userid={creds['remix_userid']}; "
                f"remix_userkey={creds['remix_userkey']}"
            ),
        }
        body = None
    else:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
            "remix-userid": creds["remix_userid"],
            "remix-userkey": creds["remix_userkey"],
        }
        body = urllib.parse.urlencode(data).encode() if data else None

    opener = _get_opener()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise ZlibError(
            f"Network request failed: {e.reason}\n"
            "Check that your proxy (e.g. mihomo) is running and the network is reachable."
        ) from e
    except TimeoutError as e:
        raise ZlibError("Request timed out (30s); check your network connection.") from e
    except json.JSONDecodeError as e:
        raise ZlibError(
            "API returned a non-JSON response; Z-Library may be temporarily unavailable."
        ) from e


def _unique_filepath(filepath):
    """If the file already exists, append a numeric suffix: (1), (2), ..."""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1
