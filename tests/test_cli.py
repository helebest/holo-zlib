"""Unit tests for zlib.py (CLI): search, download, and main(). HTTP is mocked.

cmd_* take an explicit `client` argument, so tests pass the patched `client` fixture.
"""
from __future__ import annotations

import argparse
import json
import urllib.error


def _search_args(query: str, ext: str | None = None, limit: int = 10) -> argparse.Namespace:
    return argparse.Namespace(query=query, ext=ext, limit=limit)


def _download_args(book_id: str, book_hash: str, output: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(book_id=book_id, hash=book_hash, output=output)


def _download_metadata(url: str = "https://cdn.example/file.epub", allow: bool = True) -> bytes:
    return json.dumps(
        {
            "success": 1,
            "file": {
                "downloadLink": url,
                "description": "Test Book (author, 2024)",
                "extension": "epub",
                "allowDownload": allow,
            },
        }
    ).encode()


# ---------- cmd_search ----------

def test_cmd_search_prints_sorted_results(zlib_cli, client, mock_opener, capsys):
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
    zlib_cli.cmd_search(_search_args("x", ext="epub", limit=5), client)
    out = capsys.readouterr().out
    # Higher score first.
    assert out.index("High") < out.index("Low")
    assert "book_id: 2  hash: h2" in out


def test_cmd_search_failure(zlib_cli, client, mock_opener, capsys):
    mock_opener.queue = [b'{"success": 0, "error": "nope"}']
    zlib_cli.cmd_search(_search_args("x"), client)
    out = capsys.readouterr().out
    assert "Search failed" in out


def test_cmd_search_empty(zlib_cli, client, mock_opener, capsys):
    mock_opener.queue = [b'{"success": 1, "exactBooksCount": 0, "books": []}']
    zlib_cli.cmd_search(_search_args("nothing here"), client)
    out = capsys.readouterr().out
    assert "No books found" in out


# ---------- cmd_download ----------

def test_cmd_download_writes_file(zlib_cli, client, mock_opener, tmp_path, capsys):
    mock_opener.queue = [_download_metadata(), b"EPUB-BYTES"]
    out_dir = tmp_path / "out"
    zlib_cli.cmd_download(_download_args("1", "h", output=str(out_dir)), client)
    written = list(out_dir.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == b"EPUB-BYTES"
    assert written[0].suffix == ".epub"
    assert "Download complete" in capsys.readouterr().out


def test_cmd_download_rejected_when_disallowed(zlib_cli, client, mock_opener, tmp_path, capsys):
    mock_opener.queue = [_download_metadata(allow=False)]
    out_dir = tmp_path / "out"
    zlib_cli.cmd_download(_download_args("1", "h", output=str(out_dir)), client)
    # Nothing should be written.
    assert not out_dir.exists() or not any(out_dir.iterdir())
    assert "not allowed" in capsys.readouterr().out


def test_cmd_download_unique_suffix_on_collision(zlib_cli, client, mock_opener, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Pre-create the exact sanitized target name ("Test Book" -> "Test Book.epub").
    (out_dir / "Test Book.epub").write_bytes(b"old")
    mock_opener.queue = [_download_metadata(), b"NEW-BYTES"]
    zlib_cli.cmd_download(_download_args("1", "h", output=str(out_dir)), client)
    files = sorted(p.name for p in out_dir.iterdir())
    assert "Test Book.epub" in files
    assert any(f.endswith("Test Book (1).epub") for f in files)


# ---------- main() ----------

def test_main_search_returns_zero(zlib_cli, client, mock_opener, capsys):
    mock_opener.queue = [b'{"success": 1, "exactBooksCount": 0, "books": []}']
    rc = zlib_cli.main(["search", "nothing"], client=client)
    assert rc == 0
    assert "No books found" in capsys.readouterr().out


def test_main_returns_one_on_error(zlib_cli, client, mock_opener, capsys):
    mock_opener.queue = [urllib.error.URLError("unreachable")]
    rc = zlib_cli.main(["search", "x"], client=client)
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_main_returns_one_on_api_failure(zlib_cli, client, mock_opener, capsys):
    # eAPI success:0 (e.g. bad hash) must not look like success to a caller checking $?.
    mock_opener.queue = [b'{"success": 0, "error": "bad hash"}']
    rc = zlib_cli.main(["download", "1", "badhash"], client=client)
    assert rc == 1
    assert "Failed to get download link" in capsys.readouterr().out


def test_main_returns_one_when_download_not_allowed(zlib_cli, client, mock_opener, capsys):
    mock_opener.queue = [_download_metadata(allow=False)]
    rc = zlib_cli.main(["download", "1", "h"], client=client)
    assert rc == 1
    assert "not allowed" in capsys.readouterr().out


def test_cmd_search_handles_null_quality_score(zlib_cli, client, mock_opener, capsys):
    # An explicit JSON null score must not crash the sort (float(None) -> TypeError).
    payload = {
        "success": 1,
        "exactBooksCount": 1,
        "books": [
            {"id": "1", "hash": "h", "title": "T", "author": "a", "year": "2024",
             "extension": "epub", "filesizeString": "1 MB", "qualityScore": None,
             "interestScore": "1.0", "language": "en"},
        ],
    }
    mock_opener.queue = [json.dumps(payload).encode()]
    assert zlib_cli.cmd_search(_search_args("x"), client) is True
    assert "book_id: 1" in capsys.readouterr().out
