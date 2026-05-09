#!/usr/bin/env bash
# 在本仓库启用 .githooks（提交前自动递增 VERSION）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
git config core.hooksPath .githooks
echo "已设置 core.hooksPath=.githooks（提交时将递增 VERSION 补丁号）。"
echo "跳过某次递增可执行: SKIP_VERSION_BUMP=1 git commit ..."
