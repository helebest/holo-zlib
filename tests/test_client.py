"""Unit tests for client.py: credentials, requests, path resolution. HTTP is mocked."""

from __future__ import annotations

import urllib.error

import pytest


# ---------- load_credentials ----------


def test_load_credentials_reads_json(client):
    creds = client.load_credentials()
    assert creds == {"remix_userid": "uid_test", "remix_userkey": "key_test"}


def test_load_credentials_missing_file_raises(client, monkeypatch, tmp_path):
    monkeypatch.setattr(client, "CREDENTIALS_FILE", str(tmp_path / "nope.json"))
    client._credentials = None
    with pytest.raises(client.ZlibError):
        client.load_credentials()


# ---------- make_request / auth ----------


def test_make_request_post_uses_header_auth(client, mock_opener):
    mock_opener.queue = [b'{"success": 1, "books": []}']
    result = client.make_request("/eapi/book/search", {"message": "x", "limit": "5"})
    assert result == {"success": 1, "books": []}
    call = mock_opener.calls[0]
    assert call["url"] == "https://z-library.sk/eapi/book/search"
    assert call["method"] == "POST"
    # POST authenticates via remix-* headers (urllib capitalizes the keys), not cookies.
    assert call["headers"]["Remix-userid"] == "uid_test"
    assert call["headers"]["Remix-userkey"] == "key_test"
    assert "Cookie" not in call["headers"]
    assert call["body"] == b"message=x&limit=5"


def test_make_request_get_uses_cookie_auth(client, mock_opener):
    mock_opener.queue = [b'{"success": 1, "file": {}}']
    result = client.make_request("/eapi/book/1/abc/file", method="GET")
    assert result == {"success": 1, "file": {}}
    call = mock_opener.calls[0]
    assert call["method"] == "GET"
    # GET authenticates via the Cookie header, not remix-* headers.
    assert call["headers"]["Cookie"] == "remix_userid=uid_test; remix_userkey=key_test"
    assert "Remix-userid" not in call["headers"]
    assert call["body"] is None


def test_make_request_network_error_raises(client, mock_opener):
    mock_opener.queue = [urllib.error.URLError("unreachable")]
    with pytest.raises(client.ZlibError):
        client.make_request("/eapi/book/search", {"message": "x"})


def test_make_request_timeout_raises(client, mock_opener):
    mock_opener.queue = [TimeoutError("slow")]
    with pytest.raises(client.ZlibError):
        client.make_request("/eapi/book/search", {"message": "x"})


def test_make_request_non_json_raises(client, mock_opener):
    mock_opener.queue = [b"<html>cloudflare</html>"]
    with pytest.raises(client.ZlibError):
        client.make_request("/eapi/book/search", {"message": "x"})


# ---------- _unique_filepath ----------


def test_unique_filepath_no_collision(client, tmp_path):
    target = tmp_path / "book.epub"
    assert client._unique_filepath(str(target)) == str(target)


def test_unique_filepath_with_collision(client, tmp_path):
    target = tmp_path / "book.epub"
    target.write_text("x")
    result = client._unique_filepath(str(target))
    assert result.endswith("book (1).epub")


# ---------- credentials path resolution (walk-up) ----------


def test_resolve_credentials_env_override(client, monkeypatch, tmp_path):
    explicit = tmp_path / "custom.json"
    monkeypatch.setenv("HOLO_ZLIB_CREDENTIALS_FILE", str(explicit))
    assert client._resolve_credentials_file() == str(explicit)


def test_resolve_credentials_walks_up(client, monkeypatch, tmp_path):
    """Credentials at an ancestor's credentials/zlib.json should be found."""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    project_root = tmp_path
    skill_dir = project_root / "deep" / "nested" / ".claude" / "skills" / "holo-zlib"
    skill_dir.mkdir(parents=True)
    creds_dir = project_root / "credentials"
    creds_dir.mkdir()
    creds_file = creds_dir / "zlib.json"
    creds_file.write_text('{"remix_userid": "x", "remix_userkey": "y"}')

    monkeypatch.setattr(client, "_SKILL_DIR", str(skill_dir))
    # Scope the walk to the controlled dirs so it cannot climb to the real repo's
    # credentials/ (the Windows-safe tmp_path fixture lives inside the repo).
    monkeypatch.setattr(client, "_walk_up", lambda start: iter([str(skill_dir), str(project_root)]))
    assert client._resolve_credentials_file() == str(creds_file)


def test_resolve_credentials_fallback_when_missing(client, monkeypatch, tmp_path):
    """With no ancestor credentials, fall back to <skill>/credentials/zlib.json."""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    monkeypatch.setattr(client, "_SKILL_DIR", str(skill_dir))
    # Search only the skill dir so the real repo's credentials/ cannot interfere
    # (the Windows-safe tmp_path fixture lives inside the repo).
    monkeypatch.setattr(client, "_walk_up", lambda start: iter([start]))
    expected = str(skill_dir / "credentials" / "zlib.json")
    assert client._resolve_credentials_file() == expected


def test_resolve_credentials_does_not_match_legacy_name(client, monkeypatch, tmp_path):
    """A legacy-named zlibrary_credentials.json must not match (compat dropped)."""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / "zlibrary_credentials.json").write_text(
        '{"remix_userid": "x", "remix_userkey": "y"}'
    )

    monkeypatch.setattr(client, "_SKILL_DIR", str(skill_dir))
    # Search only the controlled dirs (skill dir + its parent), not the real repo root.
    monkeypatch.setattr(client, "_walk_up", lambda start: iter([str(skill_dir), str(tmp_path)]))
    expected = str(skill_dir / "credentials" / "zlib.json")
    assert client._resolve_credentials_file() == expected


# ---------- download dir resolution (walk-up) ----------


def test_resolve_download_dir_env_override(client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOLO_ZLIB_EBOOKS_DIR", str(tmp_path))
    assert client._resolve_download_dir() == str(tmp_path)


def test_resolve_download_dir_walks_up(client, monkeypatch, tmp_path):
    """An existing ancestor ebooks/ directory should be matched."""
    monkeypatch.delenv("HOLO_ZLIB_EBOOKS_DIR", raising=False)
    project_root = tmp_path
    skill_dir = project_root / "a" / "b" / "skill"
    skill_dir.mkdir(parents=True)
    ebooks_dir = project_root / "ebooks"
    ebooks_dir.mkdir()

    monkeypatch.setattr(client, "_SKILL_DIR", str(skill_dir))
    # Scope the walk to the controlled dirs so it cannot climb to the real repo's ebooks/.
    monkeypatch.setattr(client, "_walk_up", lambda start: iter([str(skill_dir), str(project_root)]))
    assert client._resolve_download_dir() == str(ebooks_dir)


def test_resolve_download_dir_fallback_when_missing(client, monkeypatch, tmp_path):
    """With no ancestor ebooks/, fall back to <skill>/ebooks."""
    monkeypatch.delenv("HOLO_ZLIB_EBOOKS_DIR", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    monkeypatch.setattr(client, "_SKILL_DIR", str(skill_dir))
    # Search only the skill dir so the real repo's ebooks/ cannot interfere.
    monkeypatch.setattr(client, "_walk_up", lambda start: iter([start]))
    expected = str(skill_dir / "ebooks")
    assert client._resolve_download_dir() == expected
