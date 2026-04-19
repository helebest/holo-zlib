---
name: holo-zlib
description: Search and download ebooks from Z-Library via the eAPI. Use this skill whenever the user asks to find, grab, fetch, or download a book / ebook / epub / pdf / mobi / djvu, or mentions Z-Library / zlibrary / zlib / libgen-style book lookups, even if they don't explicitly name the source.
---

# Z-Library 书籍搜索与下载

## 描述

通过 Z-Library 的 eAPI 搜索并下载电子书，支持按格式和数量筛选。脚本纯 Python
标准库（Python ≥ 3.10），无需安装任何三方包。本机需能访问
`https://z-library.sk`（网络连通性自行解决）。

## 前置条件

**凭据文件** `credentials/zlib.json`
```json
{"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
```
从浏览器登录 Z-Library 后的 Cookie 中取 `remix_userid` / `remix_userkey`。

脚本会从 skill 目录逐级向上查找 `credentials/zlib.json`，命中即用。安装到
`<project>/.claude/skills/holo-zlib/` 时，把凭据放在项目根的
`<project>/credentials/zlib.json` 即可——`.claude` 同级也算祖先。

显式指定路径用 `HOLO_ZLIB_CREDENTIALS_FILE=/abs/path/to/zlib.json`。
下载目录可设 `HOLO_ZLIB_EBOOKS_DIR=/path/to/dir`（命令行 `--output` 仍会覆盖此值）。
如需指定 Python 解释器，设 `PYTHON=/path/to/python3.12`。

## 使用方法

### 搜索书籍

```bash
# 基本搜索
bash {baseDir}/scripts/zlib.sh search "书名"

# 按格式筛选
bash {baseDir}/scripts/zlib.sh search "书名" --ext epub

# 限制结果数量
bash {baseDir}/scripts/zlib.sh search "书名" --ext epub --limit 5
```

### 下载书籍

从搜索结果里挑一本，用它的 `book_id` 和 `hash` 下载：

```bash
bash {baseDir}/scripts/zlib.sh download <book_id> <hash>

# 指定下载目录
bash {baseDir}/scripts/zlib.sh download <book_id> <hash> --output /some/other/dir
```

默认保存到 skill 目录向上第一个已存在的 `ebooks/`：dev repo 里就是
`<repo>/ebooks/`；安装到 `<project>/.claude/skills/holo-zlib/` 后，只要
`<project>/ebooks/` 已存在就会落进去。整体换地方用
`export HOLO_ZLIB_EBOOKS_DIR=...`，单次换用 `--output ...`。

## 支持的格式

epub, pdf, mobi, djvu, fb2, txt, rtf, azw3, doc, docx

## 故障排查

- **"凭据文件不存在"**：按前置条件创建该 JSON 文件并填好两个字段。
- **"网络请求失败"**：网络连通性问题，自行排查。
- **"下载被限制"**：免费账户每日 10 次下载额度用完了，次日 UTC 0 点重置。
- **端点/字段细节**：见 `{baseDir}/private/eapi-notes.md`（本机笔记，未入仓）。
- **更完整的环境搭建**：见 `{baseDir}/README.md`。

## 注意事项

- Z-Library 每日有下载次数限制（免费账户 10 次）。
- POST 用 `remix-userid` / `remix-userkey` header 认证；GET 用 Cookie 认证（详见
  `private/eapi-notes.md`）。
- 凭据长期有效，除非在浏览器端登出。
