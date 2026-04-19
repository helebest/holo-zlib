"""zlib.py 的单元测试：全程 mock HTTP，不发真实请求。"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error

import pytest


def _search_args(query: str, ext: str | None = None, limit: int = 10) -> argparse.Namespace:
    return argparse.Namespace(query=query, ext=ext, limit=limit)


def _download_args(book_id: str, book_hash: str, output: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(book_id=book_id, hash=book_hash, output=output)


# ---------- load_credentials ----------

def test_load_credentials_reads_json(zlib_module):
    creds = zlib_module.load_credentials()
    assert creds == {"remix_userid": "uid_test", "remix_userkey": "key_test"}


def test_load_credentials_missing_file_exits(zlib_module, monkeypatch, tmp_path):
    monkeypatch.setattr(zlib_module, "CREDENTIALS_FILE", str(tmp_path / "nope.json"))
    zlib_module._credentials = None
    with pytest.raises(SystemExit) as excinfo:
        zlib_module.load_credentials()
    assert excinfo.value.code == 1


# ---------- make_request / POST header auth ----------

def test_make_request_post_uses_header_auth(zlib_module, mock_opener):
    mock_opener.queue = [b'{"success": 1, "books": []}']
    result = zlib_module.make_request("/eapi/book/search", {"message": "x", "limit": "5"})
    assert result == {"success": 1, "books": []}
    call = mock_opener.calls[0]
    assert call["url"] == "https://z-library.sk/eapi/book/search"
    assert call["method"] == "POST"


def test_make_request_get_uses_cookie_auth(zlib_module, mock_opener):
    mock_opener.queue = [b'{"success": 1, "file": {}}']
    result = zlib_module.make_request("/eapi/book/1/abc/file", method="GET")
    assert result == {"success": 1, "file": {}}
    assert mock_opener.calls[0]["method"] == "GET"


def test_make_request_network_error_exits(zlib_module, mock_opener):
    mock_opener.queue = [urllib.error.URLError("unreachable")]
    with pytest.raises(SystemExit) as excinfo:
        zlib_module.make_request("/eapi/book/search", {"message": "x"})
    assert excinfo.value.code == 1


def test_make_request_timeout_exits(zlib_module, mock_opener):
    mock_opener.queue = [TimeoutError("slow")]
    with pytest.raises(SystemExit) as excinfo:
        zlib_module.make_request("/eapi/book/search", {"message": "x"})
    assert excinfo.value.code == 1


def test_make_request_non_json_exits(zlib_module, mock_opener):
    mock_opener.queue = [b"<html>cloudflare</html>"]
    with pytest.raises(SystemExit) as excinfo:
        zlib_module.make_request("/eapi/book/search", {"message": "x"})
    assert excinfo.value.code == 1


# ---------- cmd_search ----------

def test_cmd_search_prints_sorted_results(zlib_module, mock_opener, capsys):
    payload = {
        "success": 1,
        "exactBooksCount": 2,
        "books": [
            {"id": "1", "hash": "h1", "title": "Low", "author": "a",
             "year": "2020", "extension": "epub", "filesizeString": "1 MB",
             "qualityScore": "3.0", "interestScore": "1.0", "language": "en"},
            {"id": "2", "hash": "h2", "title": "High", "author": "b",
             "year": "2024", "extension": "epub", "filesizeString": "2 MB",
             "qualityScore": "9.0", "interestScore": "4.0", "language": "en"},
        ],
    }
    mock_opener.queue = [json.dumps(payload).encode()]
    zlib_module.cmd_search(_search_args("x", ext="epub", limit=5))
    out = capsys.readouterr().out
    # 高分在前
    assert out.index("《High》") < out.index("《Low》")
    assert "book_id: 2  hash: h2" in out


def test_cmd_search_failure(zlib_module, mock_opener, capsys):
    mock_opener.queue = [b'{"success": 0, "error": "nope"}']
    zlib_module.cmd_search(_search_args("x"))
    out = capsys.readouterr().out
    assert "搜索失败" in out


def test_cmd_search_empty(zlib_module, mock_opener, capsys):
    mock_opener.queue = [b'{"success": 1, "exactBooksCount": 0, "books": []}']
    zlib_module.cmd_search(_search_args("nothing here"))
    out = capsys.readouterr().out
    assert "未找到" in out


# ---------- cmd_download ----------

def _download_metadata(url: str = "https://cdn.example/file.epub", allow: bool = True):
    return json.dumps({
        "success": 1,
        "file": {
            "downloadLink": url,
            "description": "《测试书》 (author, 2024)",
            "extension": "epub",
            "allowDownload": allow,
        },
    }).encode()


def test_cmd_download_writes_file(zlib_module, mock_opener, tmp_path, capsys):
    mock_opener.queue = [_download_metadata(), b"EPUB-BYTES"]
    out_dir = tmp_path / "out"
    zlib_module.cmd_download(_download_args("1", "h", output=str(out_dir)))
    written = list(out_dir.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == b"EPUB-BYTES"
    assert written[0].suffix == ".epub"
    assert "下载完成" in capsys.readouterr().out


def test_cmd_download_rejected_when_disallowed(zlib_module, mock_opener, tmp_path, capsys):
    mock_opener.queue = [_download_metadata(allow=False)]
    out_dir = tmp_path / "out"
    zlib_module.cmd_download(_download_args("1", "h", output=str(out_dir)))
    # 不应写出任何文件
    assert not out_dir.exists() or not any(out_dir.iterdir())
    assert "限制" in capsys.readouterr().out


def test_cmd_download_unique_suffix_on_collision(zlib_module, mock_opener, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "_________.epub").write_bytes(b"old")  # 预占默认 sanitize 后的文件名
    # 覆盖安全化函数的结果不用动；只需让目标名相同即可触发 _unique_filepath
    mock_opener.queue = [_download_metadata(), b"NEW-BYTES"]
    zlib_module.cmd_download(_download_args("1", "h", output=str(out_dir)))
    files = sorted(p.name for p in out_dir.iterdir())
    assert len(files) == 2  # 原文件 + 新文件带后缀
    assert any(f != "_________.epub" and f.endswith(".epub") for f in files)


# ---------- _unique_filepath ----------

def test_unique_filepath_no_collision(zlib_module, tmp_path):
    target = tmp_path / "book.epub"
    assert zlib_module._unique_filepath(str(target)) == str(target)


def test_unique_filepath_with_collision(zlib_module, tmp_path):
    target = tmp_path / "book.epub"
    target.write_text("x")
    result = zlib_module._unique_filepath(str(target))
    assert result.endswith("book (1).epub")


# ---------- 凭据路径解析（walk-up） ----------

def test_resolve_credentials_env_override(zlib_module, monkeypatch, tmp_path):
    explicit = tmp_path / "custom.json"
    monkeypatch.setenv("HOLO_ZLIB_CREDENTIALS_FILE", str(explicit))
    assert zlib_module._resolve_credentials_file() == str(explicit)


def test_resolve_credentials_walks_up(zlib_module, monkeypatch, tmp_path):
    """凭据文件放在祖先目录的 credentials/zlib.json，应当被找到。"""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    project_root = tmp_path
    skill_dir = project_root / "deep" / "nested" / ".claude" / "skills" / "holo-zlib"
    skill_dir.mkdir(parents=True)
    creds_dir = project_root / "credentials"
    creds_dir.mkdir()
    creds_file = creds_dir / "zlib.json"
    creds_file.write_text('{"remix_userid": "x", "remix_userkey": "y"}')

    monkeypatch.setattr(zlib_module, "_SKILL_DIR", str(skill_dir))
    assert zlib_module._resolve_credentials_file() == str(creds_file)


def test_resolve_credentials_fallback_when_missing(zlib_module, monkeypatch, tmp_path):
    """祖先里找不到凭据时回 <skill>/credentials/zlib.json。"""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    monkeypatch.setattr(zlib_module, "_SKILL_DIR", str(skill_dir))
    expected = str(skill_dir / "credentials" / "zlib.json")
    assert zlib_module._resolve_credentials_file() == expected


def test_resolve_credentials_does_not_match_legacy_name(zlib_module, monkeypatch, tmp_path):
    """祖先里只有老名 zlibrary_credentials.json 时不应命中（兼容已丢弃）。"""
    monkeypatch.delenv("HOLO_ZLIB_CREDENTIALS_FILE", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / "zlibrary_credentials.json").write_text('{"remix_userid": "x", "remix_userkey": "y"}')

    monkeypatch.setattr(zlib_module, "_SKILL_DIR", str(skill_dir))
    # 走到根都没找到 zlib.json，回退到 <skill>/credentials/zlib.json
    expected = str(skill_dir / "credentials" / "zlib.json")
    assert zlib_module._resolve_credentials_file() == expected


# ---------- 下载目录解析（walk-up） ----------

def test_resolve_download_dir_env_override(zlib_module, monkeypatch, tmp_path):
    monkeypatch.setenv("HOLO_ZLIB_EBOOKS_DIR", str(tmp_path))
    assert zlib_module._resolve_download_dir() == str(tmp_path)


def test_resolve_download_dir_walks_up(zlib_module, monkeypatch, tmp_path):
    """祖先里有已存在的 ebooks/ 目录时应被命中。"""
    monkeypatch.delenv("HOLO_ZLIB_EBOOKS_DIR", raising=False)
    project_root = tmp_path
    skill_dir = project_root / "a" / "b" / "skill"
    skill_dir.mkdir(parents=True)
    ebooks_dir = project_root / "ebooks"
    ebooks_dir.mkdir()

    monkeypatch.setattr(zlib_module, "_SKILL_DIR", str(skill_dir))
    assert zlib_module._resolve_download_dir() == str(ebooks_dir)


def test_resolve_download_dir_fallback_when_missing(zlib_module, monkeypatch, tmp_path):
    """没有任何祖先 ebooks/ 时回 <skill>/ebooks。"""
    monkeypatch.delenv("HOLO_ZLIB_EBOOKS_DIR", raising=False)
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    monkeypatch.setattr(zlib_module, "_SKILL_DIR", str(skill_dir))
    expected = str(skill_dir / "ebooks")
    assert zlib_module._resolve_download_dir() == expected


