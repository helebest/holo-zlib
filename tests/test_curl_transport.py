"""Unit tests for the optional curl transport (HOLO_ZLIB_TRANSPORT=curl).

``subprocess.run`` is mocked; no real curl process or network is used.
"""

from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request

import pytest


class _FakeCurl:
    """Stands in for ``subprocess.run``: records configs and replays scripted results.

    Each scripted item is ``(returncode, http_code, body)``. On success the body is
    written to the ``output`` path named in the curl config, like real curl does.
    """

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, input=None, capture_output=False, **kwargs):
        config = input.decode()
        self.calls.append({"argv": argv, "config": config})
        returncode, http_code, body = self.results.pop(0)
        if body is not None:
            out = _config_value(config, "output")
            with open(out, "wb") as f:
                f.write(body)
        stderr = b"" if returncode == 0 else b"curl: simulated failure"
        return subprocess.CompletedProcess(argv, returncode, http_code.encode(), stderr)


def _config_value(config: str, key: str) -> str:
    for line in config.splitlines():
        if line.startswith(f"{key} = "):
            return line.split(" = ", 1)[1].strip('"')
    raise KeyError(key)


@pytest.fixture
def curl_opener(client, monkeypatch, tmp_path):
    monkeypatch.setattr(client, "_CURL_RETRY_DELAY", 0)
    return client._CurlOpener(cookie_jar=str(tmp_path / "cache" / "cookies.txt"))


def _install(client, monkeypatch, results):
    fake = _FakeCurl(results)
    monkeypatch.setattr(client.subprocess, "run", fake)
    return fake


# ---------- opener selection ----------


def test_default_transport_is_urllib(client, monkeypatch):
    monkeypatch.delenv("HOLO_ZLIB_TRANSPORT", raising=False)
    opener = client._get_opener()
    assert isinstance(opener, urllib.request.OpenerDirector)


def test_curl_transport_selected_by_env(client, monkeypatch):
    monkeypatch.setenv("HOLO_ZLIB_TRANSPORT", "curl")
    assert isinstance(client._get_opener(), client._CurlOpener)


def test_unknown_transport_falls_back_to_urllib(client, monkeypatch):
    monkeypatch.setenv("HOLO_ZLIB_TRANSPORT", "carrier-pigeon")
    assert isinstance(client._get_opener(), urllib.request.OpenerDirector)


# ---------- success path ----------


def test_post_success_returns_body_and_keeps_secrets_off_argv(
    client, curl_opener, monkeypatch, tmp_path
):
    fake = _install(client, monkeypatch, [(0, "200", b'{"success": 1}')])
    req = urllib.request.Request(
        "https://z-library.sk/eapi/book/search",
        data=b"message=x",
        headers={"remix-userid": "uid_test", "remix-userkey": "key_test"},
        method="POST",
    )
    with curl_opener.open(req, timeout=30) as resp:
        assert resp.read() == b'{"success": 1}'

    call = fake.calls[0]
    assert call["argv"] == ["curl", "--config", "-"]
    assert "key_test" not in " ".join(call["argv"])
    config = call["config"]
    assert 'url = "https://z-library.sk/eapi/book/search"' in config
    # POST with a body is inferred by curl; no forced method (which would stick across
    # redirects).
    assert "request = " not in config
    assert "max-time" not in config
    assert 'header = "Remix-userkey: key_test"' in config
    assert "cookie-jar = " in config
    # Temp files (response body + request body) are cleaned up.
    assert not os.path.exists(_config_value(config, "output"))
    assert not os.path.exists(_config_value(config, "data-binary").lstrip("@"))
    # The cookie jar is created up front.
    assert (tmp_path / "cache" / "cookies.txt").exists()


def test_make_request_through_curl_opener(client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOLO_ZLIB_TRANSPORT", "curl")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    _install(client, monkeypatch, [(0, "200", b'{"success": 1, "books": []}')])
    assert client.make_request("/eapi/book/search", {"message": "x"}) == {
        "success": 1,
        "books": [],
    }


def test_streamed_reads_in_chunks(client, curl_opener, monkeypatch):
    _install(client, monkeypatch, [(0, "200", b"abcdef")])
    req = urllib.request.Request("https://z-library.sk/dl/1")
    with curl_opener.open(req, timeout=120) as resp:
        assert resp.read(4) == b"abcd"
        assert resp.read(4) == b"ef"
        assert resp.read(4) == b""


# ---------- retries and errors ----------


def test_retries_tls_handshake_failure(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(35, "000", None), (35, "000", None), (0, "200", b"ok")])
    req = urllib.request.Request("https://z-library.sk/x")
    with curl_opener.open(req) as resp:
        assert resp.read() == b"ok"
    assert len(fake.calls) == 3


def test_gives_up_after_repeated_tls_failures(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(35, "000", None)] * client._CURL_TLS_RETRIES)
    with pytest.raises(urllib.error.URLError, match="curl exit 35"):
        curl_opener.open(urllib.request.Request("https://z-library.sk/x"))
    assert len(fake.calls) == client._CURL_TLS_RETRIES


def test_timeout_maps_to_timeout_error(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(28, "000", None)])
    with pytest.raises(TimeoutError):
        curl_opener.open(urllib.request.Request("https://z-library.sk/x"), timeout=5)
    assert len(fake.calls) == 1  # timeouts are not retried


def test_timeout_maps_to_zlib_error_in_make_request(client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOLO_ZLIB_TRANSPORT", "curl")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    _install(client, monkeypatch, [(28, "000", None)])
    with pytest.raises(client.ZlibError, match="timed out"):
        client.make_request("/eapi/book/search", {"message": "x"})


def test_other_curl_error_maps_to_url_error(client, curl_opener, monkeypatch):
    _install(client, monkeypatch, [(6, "000", None)])
    with pytest.raises(urllib.error.URLError, match="curl exit 6"):
        curl_opener.open(urllib.request.Request("https://z-library.sk/x"))


@pytest.mark.parametrize("status", ["403", "500"])
def test_http_error_status_maps_to_url_error(client, curl_opener, monkeypatch, status):
    fake = _install(client, monkeypatch, [(0, status, b"denied")])
    with pytest.raises(urllib.error.URLError, match=f"HTTP {status}"):
        curl_opener.open(urllib.request.Request("https://z-library.sk/x"))
    out = _config_value(fake.calls[0]["config"], "output")
    assert not os.path.exists(out)


def test_missing_curl_binary_maps_to_url_error(client, curl_opener, monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(client.subprocess, "run", boom)
    with pytest.raises(urllib.error.URLError, match="curl not found"):
        curl_opener.open(urllib.request.Request("https://z-library.sk/x"))


def test_curl_quote_escapes_specials(client):
    assert client._curl_quote('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'


# ---------- timeouts: stall detection, not a total cap ----------


def test_timeout_is_stall_based_not_total(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(0, "200", b"ok")])
    with curl_opener.open(urllib.request.Request("https://z-library.sk/dl"), timeout=120) as r:
        r.read()
    config = fake.calls[0]["config"].splitlines()
    assert "connect-timeout = 120" in config
    assert "speed-limit = 1" in config
    assert "speed-time = 120" in config
    assert not any(line.startswith("max-time") for line in config)


# ---------- redirects ----------


def _post(url="https://z-library.sk/eapi/book/search"):
    return urllib.request.Request(
        url,
        data=b"message=x",
        headers={"remix-userid": "uid_test", "remix-userkey": "key_test"},
        method="POST",
    )


def test_redirects_followed_in_process_https_only(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(0, "200", b"ok")])
    with curl_opener.open(_post()) as resp:
        resp.read()
    config = fake.calls[0]["config"].splitlines()
    # The cookie wall needs redirects followed on the same connection (one curl process).
    assert "location" in config
    assert f"max-redirs = {client._MAX_REDIRECTS}" in config
    assert 'proto-redir = "=https"' in config


def test_post_method_is_inferred_not_forced(client, curl_opener, monkeypatch):
    """A forced `request = POST` would stick across 301/302/303 redirects."""
    fake = _install(client, monkeypatch, [(0, "200", b"ok")])
    with curl_opener.open(_post()) as resp:
        resp.read()
    assert "request = " not in fake.calls[0]["config"]


def test_get_method_is_inferred_not_forced(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(0, "200", b"ok")])
    with curl_opener.open(urllib.request.Request("https://z-library.sk/x")) as resp:
        resp.read()
    assert "request = " not in fake.calls[0]["config"]


def test_unusual_method_is_forced(client, curl_opener, monkeypatch):
    fake = _install(client, monkeypatch, [(0, "200", b"ok")])
    req = urllib.request.Request("https://z-library.sk/x", method="POST")  # no body
    with curl_opener.open(req) as resp:
        resp.read()
    assert 'request = "POST"' in fake.calls[0]["config"]


def test_same_origin_helper(client):
    assert client._same_origin("https://z-library.sk/a", "https://Z-LIBRARY.sk:443/b")
    assert not client._same_origin("https://z-library.sk/a", "http://z-library.sk/a")
    assert not client._same_origin("https://z-library.sk/a", "https://dl.z-library.sk/a")


# ---------- urllib transport applies the same cross-origin policy ----------


def test_urllib_redirect_handler_drops_credentials_cross_origin(client):
    handler = client._SameOriginRedirectHandler()
    req = urllib.request.Request(
        "https://z-library.sk/eapi/book/1/abc/file",
        headers={"Cookie": "remix_userid=u; remix_userkey=k", "remix-userkey": "k"},
    )
    cross = handler.redirect_request(req, None, 302, "Found", {}, "https://other.example/x")
    assert {k.lower() for k in cross.headers} & client._CREDENTIAL_HEADERS == set()
    same = handler.redirect_request(req, None, 302, "Found", {}, "https://z-library.sk/y")
    assert "Cookie" in same.headers


def test_default_opener_uses_same_origin_redirect_handler(client, monkeypatch):
    monkeypatch.delenv("HOLO_ZLIB_TRANSPORT", raising=False)
    opener = client._get_opener()
    assert any(isinstance(h, client._SameOriginRedirectHandler) for h in opener.handlers)
