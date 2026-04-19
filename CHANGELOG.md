# Changelog

All notable changes to this project will be documented in this file.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- 初始工程仓库骨架：`pyproject.toml` + `uv.lock`（仅 dev 依赖 `pytest`）、
  `tools/package_skill.sh`。
- 单元测试 17 条（覆盖 search / download / 凭据缺失 / 路径解析）。
- 评测集 `evals/evals.json`（3 条触发场景，assertions 待补）。

## [0.1.0] - 原型

- `SKILL.md` + `scripts/zlib.py` + `scripts/zlib.sh` 三件套，能搜能下。
