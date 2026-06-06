# Z-Library eAPI Reference

This file documents the eAPI endpoints, auth scheme, and response fields actually used
by `scripts/client.py`, for troubleshooting and maintenance. Everything here is derived
from the existing implementation and SKILL.md — it contains no credentials or private
reverse-engineering details.

## Base URL

```
https://z-library.sk
```

May be reached through a proxy; connectivity problems (e.g. the mihomo proxy not
running) surface as "Network request failed".

## Authentication

Credentials are two values from the browser cookies after login: `remix_userid` and
`remix_userkey`, stored in `credentials/zlib.json`. The two request methods authenticate
differently:

| Method | Auth location | Header / field |
|--------|---------------|----------------|
| POST   | Request headers | `remix-userid: <userid>`, `remix-userkey: <userkey>` (note the hyphens) |
| GET    | Cookie | `Cookie: remix_userid=<userid>; remix_userkey=<userkey>` (note the underscores) |

Both requests send `User-Agent: Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36`.
POST bodies are `application/x-www-form-urlencoded`.

## Endpoints

### 1. Search — `POST /eapi/book/search`

Form parameters:

| Parameter | Description |
|-----------|-------------|
| `message` | Search query |
| `limit` | Number of results (string) |
| `extensions[]` | Optional format filter, e.g. `epub` / `pdf` / `mobi` |

Key response (JSON) fields:

- `success`: truthy on success.
- `exactBooksCount`: total number of matches.
- `books[]`: result list; each item has `id`, `hash`, `title`, `author`, `year`,
  `extension`, `filesizeString`, `qualityScore`, `interestScore`, `language`.

The client sorts by `qualityScore` descending and prints `book_id` (= `id`) and `hash`
for use when downloading.

### 2. Get download link — `GET /eapi/book/{book_id}/{hash}/file`

Key response (JSON) fields:

- `success`: truthy on success.
- `file.downloadLink`: CDN direct link (bypasses Cloudflare).
- `file.allowDownload`: whether downloading is permitted; false usually means the daily
  quota is exhausted.
- `file.extension`: file extension.
- `file.description`: shaped like `Title (author, year)`; the client takes the part
  before ` (` as the title.

The client then GETs `downloadLink` directly with the same `User-Agent` and streams it
to disk (120s timeout). The filename is sanitized from the title, with ` (1)`, ` (2)`
suffixes appended on collision.

## Limits

- Free accounts have a limited daily download quota (about 10), resetting at 00:00 UTC.
- Credentials stay valid until you log out in the browser.
