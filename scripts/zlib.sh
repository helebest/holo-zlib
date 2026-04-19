#!/bin/bash
# Z-Library 搜索与下载入口
# 用法: bash zlib.sh search <关键词> [--ext epub] [--limit 10]
#       bash zlib.sh download <book_id> <hash> [--output DIR]
#
# 仅依赖 Python 3.10+（标准库即可）。如需指定解释器：
#   PYTHON=/path/to/python3.12 bash zlib.sh ...
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$SCRIPT_DIR/zlib.py" "$@"
