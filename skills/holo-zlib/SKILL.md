---
name: holo-zlib
description: Search and download ebooks from Z-Library via the eAPI. Use this skill whenever the user asks to find, grab, fetch, or download a book / ebook / epub / pdf / mobi / djvu, or mentions Z-Library / zlibrary / zlib / libgen-style book lookups, even if they don't explicitly name the source.
---

# Z-Library Book Search & Download

## Description

Search and download ebooks through Z-Library's eAPI, with filtering by format and
result count. The scripts use only the Python standard library (Python >= 3.10) — no
third-party packages required. The machine must be able to reach
`https://z-library.sk` (network connectivity is your responsibility).

## Prerequisites

**Credentials file** `credentials/zlib.json`
```json
{"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
```
Take `remix_userid` / `remix_userkey` from your browser cookies after logging in to
Z-Library.

The script walks up from the skill directory looking for `credentials/zlib.json` and
uses the first match. When installed under `<project>/.claude/skills/holo-zlib/`, put
the credentials at the project root (`<project>/credentials/zlib.json`) — the `.claude`
sibling counts as an ancestor.

To set an explicit path, use `HOLO_ZLIB_CREDENTIALS_FILE=/abs/path/to/zlib.json`.
The download directory can be set with `HOLO_ZLIB_EBOOKS_DIR=/path/to/dir` (the
command-line `--output` still overrides it).

## Usage

Run the Python script directly (on Windows use `python` or `py -3` instead of
`python3`):

### Search for books

```bash
# Basic search
python3 {baseDir}/scripts/zlib.py search "title"

# Filter by format
python3 {baseDir}/scripts/zlib.py search "title" --ext epub

# Limit the number of results
python3 {baseDir}/scripts/zlib.py search "title" --ext epub --limit 5
```

### Download a book

Pick a result and download it by its `book_id` and `hash`:

```bash
python3 {baseDir}/scripts/zlib.py download <book_id> <hash>

# Specify a download directory
python3 {baseDir}/scripts/zlib.py download <book_id> <hash> --output /some/other/dir
```

By default files are saved to the first existing `ebooks/` found while walking up
from the skill directory: in a dev repo that is `<repo>/ebooks/`; when installed under
`<project>/.claude/skills/holo-zlib/`, files land in `<project>/ebooks/` as long as it
already exists. Change it globally with `export HOLO_ZLIB_EBOOKS_DIR=...`, or per call
with `--output ...`.

## Supported formats

epub, pdf, mobi, djvu, fb2, txt, rtf, azw3, doc, docx

## Troubleshooting

- **"Credentials file not found"**: create the JSON file as described in Prerequisites
  and fill in both fields.
- **"Network request failed"**: a connectivity problem — investigate your network.
- **"Download not allowed"**: the free-account daily download quota (10) is used up; it
  resets at 00:00 UTC the next day.
- **Endpoint / field details**: see `{baseDir}/references/eapi.md`.

## Notes

- Z-Library enforces a daily download limit (10 for free accounts).
- POST uses `remix-userid` / `remix-userkey` header auth; GET uses Cookie auth (see
  `{baseDir}/references/eapi.md`).
- Credentials stay valid until you log out in the browser.
