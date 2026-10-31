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
  HOLO_ZLIB_TRANSPORT         HTTP transport. Unset (default) uses urllib. Set to
                              "curl" to send requests through the curl binary
                              instead (HTTP/2 capable, persistent cookie jar) for
                              networks that reject urllib's HTTP/1.1-only TLS.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
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


# ---------- optional curl transport (HOLO_ZLIB_TRANSPORT=curl) ----------

# curl exit codes (see `man curl`).
_CURL_TLS_HANDSHAKE_FAILED = 35
_CURL_TIMEOUT = 28
_CURL_TLS_RETRIES = 5
_CURL_RETRY_DELAY = 2.0
_MAX_REDIRECTS = 10
# Headers that carry Z-Library credentials; never forwarded to another origin.
_CREDENTIAL_HEADERS = frozenset({"remix-userid", "remix-userkey", "cookie", "authorization"})


def _origin(url: str):
    parts = urllib.parse.urlsplit(url)
    default_port = {"http": 80, "https": 443}.get(parts.scheme)
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or default_port


def _same_origin(a: str, b: str) -> bool:
    return _origin(a) == _origin(b)


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """urllib redirect handler that drops credential headers on cross-origin hops."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _same_origin(req.full_url, new.full_url):
            for name in list(new.headers):
                if name.lower() in _CREDENTIAL_HEADERS:
                    del new.headers[name]
            for name in list(new.unredirected_hdrs):
                if name.lower() in _CREDENTIAL_HEADERS:
                    del new.unredirected_hdrs[name]
        return new


def _cookie_jar_path() -> str:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(cache, "holo-zlib-cookies.txt")


def _curl_quote(value) -> str:
    """Quote a value for a curl config file (``-K``)."""
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


class _CurlResponse:
    """File-like response that streams the body curl wrote to a temp file.

    The temp file is removed when the response is closed.
    """

    def __init__(self, path: str):
        self._path = path
        self._fh = open(path, "rb")

    def read(self, size=-1):
        return self._fh.read(size)

    def close(self):
        if not self._fh.closed:
            self._fh.close()
        if os.path.exists(self._path):
            os.remove(self._path)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _CurlOpener:
    """Drop-in replacement for the urllib opener that shells out to ``curl``.

    Why: some networks / egress proxies only let HTTP/2 TLS handshakes through to
    z-library.sk, and urllib only speaks HTTP/1.1 (the handshake fails with EOF). The
    site also sets a cookie on a redirect wall, so a persistent cookie jar is kept to
    avoid redirect loops.

    The whole request (URL, headers including credentials, body path) is passed to curl
    as a config file on stdin, never on argv, so credentials don't show up in ``ps``.
    Errors are mapped onto the exceptions urllib raises (``TimeoutError`` /
    ``urllib.error.URLError``) so callers' existing handling keeps working.
    """

    def __init__(self, curl: str = "curl", cookie_jar: str | None = None):
        self.curl = curl
        self.cookie_jar = cookie_jar or _cookie_jar_path()

    def _ensure_cookie_jar(self):
        os.makedirs(os.path.dirname(self.cookie_jar), exist_ok=True)
        if not os.path.exists(self.cookie_jar):
            # Pre-create with owner-only permissions; it holds session cookies.
            os.close(os.open(self.cookie_jar, os.O_CREAT | os.O_WRONLY, 0o600))

    def _config(self, req, data_path, out_path, timeout):
        cfg = [
            f"url = {_curl_quote(req.full_url)}",
            f"output = {_curl_quote(out_path)}",
            f"cookie = {_curl_quote(self.cookie_jar)}",
            f"cookie-jar = {_curl_quote(self.cookie_jar)}",
            # The site's cookie wall (__diamwall) redirects and expects the cookie back on
            # the same connection, so redirects must be followed inside one curl process.
            "location",
            f"max-redirs = {_MAX_REDIRECTS}",
            'proto-redir = "=https"',
            # Match urllib's timeout semantics (per blocking operation, no total cap):
            # bound connection setup, and abort only if the transfer stalls (< 1 byte/s
            # for `timeout` seconds). A total `max-time` would kill long downloads.
            f"connect-timeout = {int(timeout)}",
            "speed-limit = 1",
            f"speed-time = {int(timeout)}",
            'write-out = "%{http_code}"',
            "silent",
            "show-error",
        ]
        # Don't force the method when curl infers it (GET, or POST with a body): a forced
        # method sticks across redirects, while an inferred POST becomes GET on
        # 301/302/303 like urllib does.
        method = req.get_method()
        if method != ("POST" if data_path else "GET"):
            cfg.append(f"request = {_curl_quote(method)}")
        for key, value in req.header_items():
            cfg.append(f"header = {_curl_quote(f'{key}: {value}')}")
        if data_path:
            cfg.append(f"data-binary = {_curl_quote('@' + data_path)}")
        return ("\n".join(cfg) + "\n").encode()

    def open(self, req, timeout=30):
        self._ensure_cookie_jar()
        fd, out_path = tempfile.mkstemp(prefix="holo-zlib-")
        os.close(fd)
        data_path = None
        try:
            if req.data is not None:
                fd, data_path = tempfile.mkstemp(prefix="holo-zlib-body-")
                with os.fdopen(fd, "wb") as f:
                    f.write(req.data)
            result = self._run(self._config(req, data_path, out_path, timeout))
            if result.returncode == _CURL_TIMEOUT:
                raise TimeoutError(f"curl timed out (no progress for {int(timeout)}s)")
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace").strip()
                raise urllib.error.URLError(f"curl exit {result.returncode}: {stderr}")
            status = result.stdout.decode(errors="replace").strip()
            code = int(status) if status.isdigit() else 0
            if code >= 400:
                raise urllib.error.URLError(f"HTTP {code}")
            response = _CurlResponse(out_path)
            out_path = None  # ownership moves to the response
            return response
        finally:
            for path in (out_path, data_path):
                if path and os.path.exists(path):
                    os.remove(path)

    def _run(self, config: bytes):
        """Run curl, retrying TLS handshake failures (flaky on some egress paths)."""
        for attempt in range(_CURL_TLS_RETRIES):
            try:
                result = subprocess.run(
                    [self.curl, "--config", "-"], input=config, capture_output=True
                )
            except FileNotFoundError as e:
                raise urllib.error.URLError(
                    "curl not found; install curl or unset HOLO_ZLIB_TRANSPORT"
                ) from e
            if result.returncode != _CURL_TLS_HANDSHAKE_FAILED:
                return result
            if attempt < _CURL_TLS_RETRIES - 1:
                time.sleep(_CURL_RETRY_DELAY)
        return result


def _get_opener():
    global _opener
    if _opener is None:
        if os.environ.get("HOLO_ZLIB_TRANSPORT", "").strip().lower() == "curl":
            _opener = _CurlOpener()
        else:
            _opener = urllib.request.build_opener(_SameOriginRedirectHandler)
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
                f"remix_userid={creds['remix_userid']}; remix_userkey={creds['remix_userkey']}"
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
