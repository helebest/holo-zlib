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
    assert 'request = "POST"' in config
    assert "max-time = 30" in config
    assert 'header = "Remix-userkey: key_test"' in config
    assert "cookie-jar = " in config and "location" in config
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
