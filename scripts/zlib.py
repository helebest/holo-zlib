#!/usr/bin/env python3
"""Z-Library 书籍搜索与下载脚本（仅依赖标准库，Python 3.10+）。

用法:
  python3 scripts/zlib.py search <关键词> [--ext epub|pdf|mobi] [--limit N]
  python3 scripts/zlib.py download <book_id> <hash> [--output DIR]

环境变量:
  HOLO_ZLIB_CREDENTIALS_FILE  凭据文件路径。未设置时从 skill 目录逐级向上查找
                              credentials/zlib.json，命中即用；未找到时回到
                              <skill>/credentials/zlib.json。
  HOLO_ZLIB_EBOOKS_DIR        下载目录。未设置时从 skill 目录逐级向上查找已存在
                              的 ebooks/ 目录；未找到时回到 <skill>/ebooks。
                              命令行 --output 仍然会覆盖此值。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# 当 skill 作为独立 repo 使用时，scripts/zlib.py 父目录就是仓库根；
# 当 skill 被安装到 <proj>/.claude/skills/holo-zlib/scripts/ 时，真正的"项目根"在更上层。
# 因此查找 credentials/ebooks 时从脚本位置逐级向上搜索，直到找到目标或抵达文件系统根。
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CRED_FILENAME = "zlib.json"


def _walk_up(start: str):
    """从 start 开始，yield 逐级向上的每个目录（包含 start 自身）。"""
    cur = os.path.abspath(start)
    while True:
        yield cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return
        cur = parent


def _resolve_credentials_file() -> str:
    env = os.environ.get("HOLO_ZLIB_CREDENTIALS_FILE")
    if env:
        return os.path.expanduser(env)
    for base in _walk_up(_SKILL_DIR):
        cand = os.path.join(base, "credentials", _CRED_FILENAME)
        if os.path.exists(cand):
            return cand
    # 未找到：回到 skill 自己目录下的默认路径，load_credentials 会给出明确错误
    return os.path.join(_SKILL_DIR, "credentials", _CRED_FILENAME)


def _resolve_download_dir() -> str:
    env = os.environ.get("HOLO_ZLIB_EBOOKS_DIR")
    if env:
        return os.path.expanduser(env)
    # 优先选已存在的 ebooks/ 目录；否则回到 skill 目录下（首次下载会自动创建）
    for base in _walk_up(_SKILL_DIR):
        cand = os.path.join(base, "ebooks")
        if os.path.isdir(cand):
            return cand
    return os.path.join(_SKILL_DIR, "ebooks")


CREDENTIALS_FILE = _resolve_credentials_file()
DOWNLOAD_DIR = _resolve_download_dir()
BASE_URL = "https://z-library.sk"

# 模块级缓存
_credentials = None
_opener = None


def load_credentials():
    global _credentials
    if _credentials is not None:
        return _credentials
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: 凭据文件不存在: {CREDENTIALS_FILE}")
        print("请创建文件，内容格式:")
        print('{"remix_userid": "...", "remix_userkey": "..."}')
        sys.exit(1)
    with open(CREDENTIALS_FILE, encoding="utf-8") as f:
        _credentials = json.load(f)
    return _credentials


def _get_opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener()
    return _opener


def make_request(path, data=None, method="POST"):
    """发送 eAPI 请求（POST 用 header 认证，GET 用 cookie 认证）"""
    creds = load_credentials()
    url = f"{BASE_URL}{path}"
    ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"

    if method == "GET":
        headers = {
            "User-Agent": ua,
            "Cookie": f"remix_userid={creds['remix_userid']}; remix_userkey={creds['remix_userkey']}",
        }
        body = None
    else:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": ua,
            "remix-userid": creds["remix_userid"],
            "remix-userkey": creds["remix_userkey"],
        }
        body = urllib.parse.urlencode(data).encode() if data else None

    opener = _get_opener()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"ERROR: 网络请求失败: {e.reason}")
        print("请检查代理 (mihomo) 是否运行中，以及网络连接是否正常。")
        sys.exit(1)
    except TimeoutError:
        print("ERROR: 请求超时（30s），请检查网络连接。")
        sys.exit(1)
    except json.JSONDecodeError:
        print("ERROR: API 返回了非 JSON 响应，Z-Library 可能暂时不可用。")
        sys.exit(1)


def _unique_filepath(filepath):
    """如果文件已存在，添加数字后缀 (1)、(2) 等"""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def cmd_search(args):
    params = {"message": args.query, "limit": str(args.limit)}
    if args.ext:
        params["extensions[]"] = args.ext

    result = make_request("/eapi/book/search", params)

    if not result.get("success"):
        print("搜索失败:", json.dumps(result, ensure_ascii=False))
        return

    books = result.get("books", [])
    books.sort(key=lambda b: float(b.get("qualityScore", 0)), reverse=True)
    total = result.get("exactBooksCount", 0)

    if not books:
        print(f"未找到与 \"{args.query}\" 相关的书籍")
        return

    print(f"搜索: \"{args.query}\"  共 {total} 个结果，显示前 {len(books)} 个:\n")
    for i, b in enumerate(books, 1):
        print(f"{i}. 《{b['title']}》")
        print(f"   作者: {b.get('author', '未知').strip()}")
        print(f"   年份: {b.get('year', '?')}  格式: {b['extension']}  大小: {b['filesizeString']}")
        print(f"   评分: {b.get('interestScore', '?')}  语言: {b.get('language', '?')}")
        print(f"   book_id: {b['id']}  hash: {b['hash']}")
        print()


def cmd_download(args):
    # 通过 eAPI 获取 CDN 直链（绕过 Cloudflare）
    file_info = make_request(
        f"/eapi/book/{args.book_id}/{args.hash}/file", method="GET"
    )

    if not file_info.get("success"):
        print("获取下载链接失败:", json.dumps(file_info, ensure_ascii=False))
        return

    f = file_info["file"]
    dl_url = f["downloadLink"]
    title = f.get("description", "unknown").split(" (")[0]
    ext = f.get("extension", "epub")

    if not f.get("allowDownload"):
        print(f"下载被限制（今日额度可能已用完）")
        return

    output_dir = args.output or DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip()
    filename = f"{safe_title}.{ext}"
    filepath = _unique_filepath(os.path.join(output_dir, filename))

    print(f"下载: 《{title}》 ({ext})")
    print(f"保存到: {filepath}")

    opener = _get_opener()
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
                    print(f"\r  已下载: {mb:.2f} MB", end="", flush=True)
            print()  # 换行
    except urllib.error.URLError as e:
        print(f"\nERROR: 下载失败: {e.reason}")
        if os.path.exists(filepath):
            os.remove(filepath)
        sys.exit(1)
    except TimeoutError:
        print("\nERROR: 下载超时（120s）")
        if os.path.exists(filepath):
            os.remove(filepath)
        sys.exit(1)

    size_mb = downloaded / (1024 * 1024)
    print(f"下载完成! ({size_mb:.2f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Z-Library 书籍搜索与下载")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    sp = sub.add_parser("search", help="搜索书籍")
    sp.add_argument("query", help="搜索关键词")
    sp.add_argument("--ext", help="文件格式过滤 (epub/pdf/mobi)")
    sp.add_argument("--limit", type=int, default=10, help="结果数量 (默认10)")

    # download
    dp = sub.add_parser("download", help="下载书籍")
    dp.add_argument("book_id", help="书籍 ID")
    dp.add_argument("hash", help="书籍 hash")
    dp.add_argument("--output", help="下载目录 (默认 $HOLO_ZLIB_EBOOKS_DIR 或祖先目录中第一个已存在的 ebooks/)")

    args = parser.parse_args()
    if args.command == "search":
        cmd_search(args)
    elif args.command == "download":
        cmd_download(args)


if __name__ == "__main__":
    main()
