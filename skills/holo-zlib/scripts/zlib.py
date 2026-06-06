#!/usr/bin/env python3
"""Z-Library book search & download CLI (standard library only, Python 3.10+).

Usage:
  python3 zlib.py search <query> [--ext FORMAT] [--limit N]
  python3 zlib.py download <book_id> <hash> [--output DIR]

eAPI requests, auth, and credential resolution live in client.py (same directory);
this file only handles argument parsing and output formatting. See client.py and
SKILL.md for environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _load_client():
    """Load the sibling ``client`` module, for both direct-run and package import.

    Loads by spec/file path instead of mutating sys.path, so the directory holding
    zlib.py is never prepended to sys.path where it could shadow the standard-library
    ``zlib`` module (urllib/gzip may import it).
    """
    if __package__:
        from . import client  # pragma: no cover - scripts/ has no __init__.py

        return client
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "zlib_client", Path(__file__).resolve().parent / "client.py"
    )
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    return client


def _quality_score(book) -> float:
    """Sort key for search results, tolerant of missing/null/non-numeric scores.

    The eAPI may return ``qualityScore`` as a string, missing, or explicit JSON null;
    ``float(None)`` would otherwise crash the whole search.
    """
    try:
        return float(book.get("qualityScore") or 0)
    except (TypeError, ValueError):
        return 0.0


def cmd_search(args, client) -> bool:
    """Return True on a successful search (including zero matches), False on API error."""
    params = {"message": args.query, "limit": str(args.limit)}
    if args.ext:
        params["extensions[]"] = args.ext

    result = client.make_request("/eapi/book/search", params)

    if not result.get("success"):
        print("Search failed:", json.dumps(result, ensure_ascii=False))
        return False

    books = result.get("books", [])
    books.sort(key=_quality_score, reverse=True)
    total = result.get("exactBooksCount", 0)

    if not books:
        print(f'No books found for "{args.query}"')
        return True

    print(f'Search: "{args.query}"  {total} results, showing top {len(books)}:\n')
    for i, b in enumerate(books, 1):
        print(f"{i}. {b['title']}")
        print(f"   Author: {b.get('author', 'Unknown').strip()}")
        print(
            f"   Year: {b.get('year', '?')}  Format: {b['extension']}  Size: {b['filesizeString']}"
        )
        # Show both score fields under their real names: the list is sorted by qualityScore
        # but qualityScore is often null/0 and interestScore is often uniformly high, so a
        # single ambiguous "Score" would mislead the agent into ranking by the wrong field.
        qs = b.get("qualityScore")
        print(
            f"   Quality: {qs if qs is not None else '?'}  "
            f"Popularity: {b.get('interestScore', '?')}  "
            f"Language: {b.get('language', '?')}"
        )
        print(f"   book_id: {b['id']}  hash: {b['hash']}")
        print()
    return True


def cmd_download(args, client) -> bool:
    """Return True on a successful download, False on API error / quota block."""
    # Fetch the CDN direct link via the eAPI (bypasses Cloudflare).
    file_info = client.make_request(f"/eapi/book/{args.book_id}/{args.hash}/file", method="GET")

    if not file_info.get("success"):
        print("Failed to get download link:", json.dumps(file_info, ensure_ascii=False))
        return False

    f = file_info["file"]
    dl_url = f["downloadLink"]
    title = f.get("description", "unknown").split(" (")[0]
    ext = f.get("extension", "epub")

    if not f.get("allowDownload"):
        print("Download not allowed (daily quota may be exhausted)")
        return False

    output_dir = args.output or client.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip()
    filename = f"{safe_title}.{ext}"
    filepath = client._unique_filepath(os.path.join(output_dir, filename))

    print(f'Downloading: "{title}" ({ext})')
    print(f"Saving to: {filepath}")

    opener = client._get_opener()
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"}
    req = urllib.request.Request(dl_url, headers=headers)
    try:
        with opener.open(req, timeout=120) as resp:
            downloaded = 0
            with open(filepath, "wb") as out:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    mb = downloaded / (1024 * 1024)
                    print(f"\r  Downloaded: {mb:.2f} MB", end="", flush=True)
            print()  # newline
    except urllib.error.URLError as e:
        print(f"\nERROR: download failed: {e.reason}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise client.ZlibError(f"Download failed: {e.reason}") from e
    except TimeoutError as e:
        print("\nERROR: download timed out (120s)")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise client.ZlibError("Download timed out (120s)") from e

    size_mb = downloaded / (1024 * 1024)
    print(f"Download complete! ({size_mb:.2f} MB)")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Z-Library book search & download")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="Search for books")
    sp.add_argument("query", help="Search query")
    sp.add_argument(
        "--ext",
        help="Format filter, e.g. epub/pdf/mobi (passed through to the API unvalidated; "
        "any format Z-Library supports works)",
    )
    sp.add_argument("--limit", type=int, default=10, help="Number of results (default 10)")

    dp = sub.add_parser("download", help="Download a book")
    dp.add_argument("book_id", help="Book ID")
    dp.add_argument("hash", help="Book hash")
    dp.add_argument(
        "--output",
        help="Download directory (default: $HOLO_ZLIB_EBOOKS_DIR or the first existing "
        "ebooks/ in an ancestor directory)",
    )
    return parser


def main(argv=None, client=None) -> int:
    args = build_parser().parse_args(argv)
    if client is None:
        client = _load_client()
    ok = False
    try:
        if args.command == "search":
            ok = cmd_search(args, client)
        elif args.command == "download":
            ok = cmd_download(args, client)
    except client.ZlibError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # API-reported failures (success:0, quota-blocked) return a non-zero exit code too,
    # so a caller checking the exit status does not treat them as success.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
