# holo-zlib

Claude Code skill：从 Z-Library 搜索并下载电子书。走 eAPI，Python 标准库，
Python ≥ 3.10 直接跑，无需三方依赖。

## 快速开始

```bash
# 1. 创建凭据文件（登录 https://z-library.sk 后从浏览器 Cookie 取两个值）
mkdir -p credentials
cat > credentials/zlib.json <<'EOF'
{"remix_userid": "YOUR_USERID", "remix_userkey": "YOUR_USERKEY"}
EOF

# 2. 试一下
bash scripts/zlib.sh search "三体" --ext epub --limit 3
```

> 装到 `<project>/.claude/skills/holo-zlib/` 时，把 `credentials/zlib.json`
> 放在项目根（`<project>/credentials/zlib.json`）即可，脚本会自己往上找。

## 仓库结构

```
holo-zlib/
├── SKILL.md                  # skill 入口（Claude 加载）
├── scripts/
│   ├── zlib.sh               # 入口脚本 → python3
│   └── zlib.py               # 核心实现（stdlib-only）
├── credentials/              # 凭据（.gitignore/.claudeignore）
├── private/                  # 本机技术笔记（.gitignore/.claudeignore）
├── evals/evals.json          # skill-creator 评测集
├── tests/                    # pytest 单元测试
├── tools/package_skill.py    # 打 .skill 分发包（stage-and-zip，按 .claudeignore 过滤）
├── pyproject.toml            # 仅 dev（pytest）；运行时不需要
└── uv.lock
```

## 环境变量

| 变量 | 作用 | 默认 |
|-----|-----|-----|
| `HOLO_ZLIB_CREDENTIALS_FILE` | 凭据文件路径 | skill 目录向上第一个 `credentials/zlib.json`；找不到回 `<skill>/credentials/zlib.json` |
| `HOLO_ZLIB_EBOOKS_DIR` | 下载目录（命令行 `--output` 仍会覆盖） | skill 目录向上第一个已存在的 `ebooks/`；找不到回 `<skill>/ebooks` |
| `PYTHON` | Python 解释器路径 | `python3` |

## 开发

跑测试需要 `pytest`，选一个方式拉起：

```bash
# 用 uv（推荐）
uv sync && uv run pytest tests/ -v

# 或 pip
pip install pytest && pytest tests/ -v
```

打 `.skill` 分发包：`python3 tools/package_skill.py`（按 `.claudeignore` 过滤，
默认输出 `dist/holo-zlib.skill`，含安全二闸防止凭据/私有笔记误打入）。

## License

MIT
