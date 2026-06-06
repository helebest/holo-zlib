---
name: holo-zlib
description: Search and download published ebooks from Z-Library. Use this skill whenever the user wants to find or obtain a specific book or ebook (in formats like epub, pdf, mobi, or djvu) — whether they ask directly (find, grab, fetch, download) or indirectly (get me a copy of a title, I need this textbook as a file, do you have this book?). Trigger even when the user names no source, and when they mention Z-Library / zlibrary / zlib or name a different book library. Not for academic papers/preprints (e.g. arXiv), non-book media (movies, music, software), or operating on a file the user already has (converting, extracting text, summarizing) — though an ebook that happens to be a PDF still counts.
---

# Z-Library Book Search & Download

Search and download ebooks through Z-Library's eAPI, filtering by format and result
count. Standard library only (Python >= 3.10) — no third-party packages. The machine
must be able to reach `https://z-library.sk` (network connectivity is your
responsibility).

Paths below are relative to this skill's directory — run the commands from here. Examples
use `python`; on Linux/macOS where only `python3` exists, substitute it. On Windows,
`python` from a venv or the Microsoft Store works; the `py` launcher is not always
installed, so don't rely on `py -3`.

## Prerequisites

**Credentials file** `credentials/zlib.json`
```json
{"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
```
Take `remix_userid` / `remix_userkey` from your browser cookies after logging in to
Z-Library.

The script uses the nearest `credentials/zlib.json` found while walking up from the skill
directory. When installed under `<project>/.claude/skills/holo-zlib/`, put it at the
project root (`<project>/credentials/zlib.json`) — the `.claude` sibling counts as an
ancestor. Set an explicit path with `HOLO_ZLIB_CREDENTIALS_FILE=/abs/path/to/zlib.json`.

## Workflow

Two steps: (1) run `search` to get a result's `book_id` and `hash`; (2) pass those two
values to `download`. The identifiers come only from search output — don't guess them.

## Usage

### Search for books

```bash
# Basic search
python scripts/zlib.py search "title"

# Filter by format
python scripts/zlib.py search "title" --ext epub

# Limit the number of results
python scripts/zlib.py search "title" --ext epub --limit 5
```

`--ext` is passed straight to the API (not validated), so any format Z-Library supports
works — commonly epub, pdf, mobi, djvu, fb2, txt, rtf, azw3, doc, docx.

### Choosing a result

Each result prints two numbers: `Quality` (qualityScore) and `Popularity`
(interestScore). In practice these are often null/0 or tied at the top — every popular
edition tends to show the same value — so they rarely separate the best match. Results are
listed in the API's relevance order, so for a generic "best" / "most popular" request,
prefer the top result whose **title actually matches** what the user asked for, then break
ties by completeness (a full edition over a sample/companion volume), file size, year, and
language. Tell the user which one you picked and why.

### Download a book

Take the `book_id` and `hash` from the chosen result line and pass them to `download`
(book_id first, then hash):

```bash
python scripts/zlib.py download <book_id> <hash>

# Specify a download directory
python scripts/zlib.py download <book_id> <hash> --output /some/other/dir
```

**End-to-end example** (values are illustrative — use real ones from your own search):

```bash
python scripts/zlib.py search "the pragmatic programmer" --ext epub --limit 3
# a result line looks like:
#   1. The Pragmatic Programmer
#      ...
#      book_id: 123456  hash: abc123def
python scripts/zlib.py download 123456 abc123def
```

By default files are saved to the nearest existing `ebooks/` directory found while walking
up from the skill directory (e.g. `<project>/ebooks/`, or `<repo>/ebooks/` in a dev
checkout). Override globally with `HOLO_ZLIB_EBOOKS_DIR=...`, or per call with
`--output ...`.

Free accounts are limited to roughly 10 downloads per day. There is no API to check
remaining quota, so when asked for several books at once, download the highest-priority
titles first (or confirm scope) rather than firing a large batch that may exhaust midway.

## Troubleshooting

- **"Credentials file not found"**: create `credentials/zlib.json` as described in
  Prerequisites and fill in both fields.
- **"Network request failed" / "Request timed out (30s)" / "Download timed out (120s)"**:
  a connectivity problem — confirm your network (and proxy, e.g. mihomo) can reach
  `https://z-library.sk`, then retry. Large files can legitimately need the full window.
- **"Failed to get download link"**: the `book_id`/`hash` is likely stale or invalid
  (hashes can change between searches) — re-run the search to get fresh identifiers and
  retry. This is not a quota problem, so don't wait for the next day.
- **"Download not allowed"**: a link came back but downloading is blocked — almost always
  the daily quota is exhausted (resets about once a day). Less commonly the specific title
  is restricted for your account; if quota clearly isn't the issue, try a different
  edition/result.
- **Endpoint / auth / field details**: see `references/eapi.md`.

## Notes

- Credentials stay valid until you log out in the browser.
- This is deliberately a small, two-command surface (search + download). Supply the
  orchestration — which result to pick, when to download — yourself; there is no
  interactive picker or download-by-rank flag.
