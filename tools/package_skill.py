#!/usr/bin/env python3
"""把当前仓库打成 .skill 分发包（本质是 .skill 后缀的 zip）。

规则：
  - 仓库根（脚本父目录的父目录）即 skill 根，必须含 SKILL.md。
  - 排除清单读 <repo>/.claudeignore，gitignore 风格的子集（注释/空行/精确名/
    glob/目录/锚定根）。
  - 安全二闸：最终入包文件名扫一遍敏感词（credentials/private/ebooks/
    *credentials*/*.creds.json），命中即中止——防止 .claudeignore 写漏时
    把本机凭据打进分发包。

用法:
  python3 tools/package_skill.py [--out PATH]

默认输出 dist/<skill_name>.skill；--out 可指定文件路径。
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
import zipfile
from pathlib import Path


# 安全二闸：这些词/模式在最终入包路径里出现就报错并中止
_DANGER_PATTERNS = (
    "credentials/",
    "private/",
    "ebooks/",
    "*credentials*.json",
    "zlib.json",
    "*.creds.json",
)


class IgnoreRule:
    """单条 .claudeignore 规则的预编译结果。"""

    def __init__(self, pattern: str):
        self.raw = pattern
        # 锚定根：以 / 开头则只在 skill 根下匹配；否则任意层级都匹配
        anchored = pattern.startswith("/")
        if anchored:
            pattern = pattern[1:]
        # 目录规则：以 / 结尾，匹配该名目录的整棵子树
        is_dir = pattern.endswith("/")
        if is_dir:
            pattern = pattern[:-1]
        self.anchored = anchored
        self.is_dir = is_dir
        self.pattern = pattern

    def matches(self, rel_path: str) -> bool:
        """rel_path 是用 / 分隔的相对 skill 根的路径。"""
        parts = rel_path.split("/")
        if self.is_dir:
            # 命中条件：路径里有一段（锚定时仅第一段）等于该目录名
            if self.anchored:
                return len(parts) > 1 and parts[0] == self.pattern
            return self.pattern in parts
        # 文件/glob 规则
        if self.anchored:
            return fnmatch.fnmatch(rel_path, self.pattern)
        # 非锚定：basename 匹配 OR 任意子段匹配 OR 整路径匹配
        if fnmatch.fnmatch(parts[-1], self.pattern):
            return True
        if fnmatch.fnmatch(rel_path, self.pattern):
            return True
        return False


def load_ignore_rules(claudeignore_path: Path) -> list[IgnoreRule]:
    if not claudeignore_path.exists():
        return []
    rules: list[IgnoreRule] = []
    for line in claudeignore_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rules.append(IgnoreRule(line))
    return rules


def is_excluded(rel_path: str, rules: list[IgnoreRule]) -> bool:
    return any(r.matches(rel_path) for r in rules)


def is_dangerous(rel_path: str) -> str | None:
    """返回触发的危险模式名，或 None。"""
    for pat in _DANGER_PATTERNS:
        if pat.endswith("/"):
            seg = pat[:-1]
            if seg in rel_path.split("/"):
                return pat
        elif fnmatch.fnmatch(os.path.basename(rel_path), pat):
            return pat
    return None


def parse_skill_name(skill_md: Path) -> str:
    """从 SKILL.md 的 YAML frontmatter 里读 name 字段。"""
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        sys.exit(f"❌ SKILL.md 缺少 frontmatter (--- ... ---): {skill_md}")
    fm = m.group(1)
    name_m = re.search(r"^name:\s*(\S+)", fm, re.MULTILINE)
    desc_m = re.search(r"^description:\s*\S", fm, re.MULTILINE)
    if not name_m:
        sys.exit("❌ SKILL.md frontmatter 缺少 name 字段")
    if not desc_m:
        sys.exit("❌ SKILL.md frontmatter 缺少 description 字段")
    return name_m.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-and-zip 打包 skill")
    parser.add_argument("--out", help="输出文件路径（默认 dist/<skill_name>.skill）")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    skill_md = repo_root / "SKILL.md"
    if not skill_md.exists():
        sys.exit(f"❌ 仓库根缺少 SKILL.md: {repo_root}")

    skill_name = parse_skill_name(skill_md)
    rules = load_ignore_rules(repo_root / ".claudeignore")

    # 收集要入包的文件（相对路径）
    included: list[tuple[Path, str]] = []  # (abs_path, rel_path)
    skipped: list[str] = []
    for fp in sorted(repo_root.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(repo_root).as_posix()
        if is_excluded(rel, rules):
            skipped.append(rel)
            continue
        included.append((fp, rel))

    # 安全二闸
    danger_hits = [(rel, is_dangerous(rel)) for _, rel in included]
    danger_hits = [(rel, pat) for rel, pat in danger_hits if pat]
    if danger_hits:
        print("❌ 安全二闸命中——以下文件不应入包，请检查 .claudeignore：", file=sys.stderr)
        for rel, pat in danger_hits:
            print(f"   {rel}   [触发 {pat}]", file=sys.stderr)
        return 1

    # 决定输出路径
    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = repo_root / "dist" / f"{skill_name}.skill"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 打包
    print(f"📦 打包 skill: {skill_name}")
    print(f"   源: {repo_root}")
    print(f"   出: {out_path}\n")

    if out_path.exists():
        out_path.unlink()

    total_size = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp, rel in included:
            arc = f"{skill_name}/{rel}"
            zf.write(fp, arc)
            size = fp.stat().st_size
            total_size += size
            print(f"  + {arc}  ({size} B)")

    print(f"\n✅ 完成: {out_path}")
    print(f"   {len(included)} 个文件，未压缩 {total_size} B，"
          f"压缩后 {out_path.stat().st_size} B")
    if skipped:
        print(f"   跳过 {len(skipped)} 个（按 .claudeignore）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
