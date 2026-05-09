#!/usr/bin/env python3
"""将仓库根目录 VERSION 的补丁号 +1（语义化 x.y.z）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    vf = repo_root() / "VERSION"
    if not vf.is_file():
        print(f"错误: 缺少 {vf}", file=sys.stderr)
        return 1
    raw = vf.read_text(encoding="utf-8").strip()
    m = SEMVER.match(raw)
    if not m:
        print(f"错误: VERSION 须为 x.y.z，当前为 {raw!r}", file=sys.stderr)
        return 1
    major, minor, patch = m.group(1), m.group(2), int(m.group(3)) + 1
    new_v = f"{major}.{minor}.{patch}"
    vf.write_text(new_v + "\n", encoding="utf-8")
    print(f"版本已更新: {raw} → {new_v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
