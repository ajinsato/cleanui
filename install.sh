#!/usr/bin/env bash
# CleanUI 一键安装：用户级 pip 安装、可选系统依赖、PATH 与桌面菜单入口。
set -euo pipefail

usage() {
  sed -n '1,80p' <<'EOF'
用法: ./install.sh [选项]

默认：在当前用户下可编辑安装（pip --user -e），并写入 PATH 提示与桌面快捷方式。

选项:
  -h, --help           显示本说明
  -y, --yes            非交互：假设对 apt 等问题回答「是」（需已配置 sudo 免密或已在终端登录）
  --install-deps       在检测到 apt-get 时尝试安装 python3-pip、python3-tk、fontconfig（需 sudo）
  --system             系统级安装（sudo pip），仅供多用户共享；部分发行版需 PEP 668 额外参数
  --no-desktop         不安装 ~/.local/share/applications 下的桌面入口
  --no-path            不向 ~/.profile 追加 PATH（仍可手动配置）
  --git-hooks          为本仓库设置 git hooks（提交前自动递增 VERSION）

环境变量:
  PYTHON=python3       使用的 Python 解释器

示例:
  ./install.sh                          # 仅 pip 用户安装 + PATH + 菜单
  ./install.sh --install-deps -y        # 顺带 apt 装 Tk/pip 等（自动化脚本）
  ./install.sh --system                 # 安装到系统 Python（需 root）
  ./install.sh --git-hooks              # 仅启用提交前自动递增版本号
EOF
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
INSTALL_DEPS=0
ASSUME_YES=0
SYSTEM_INSTALL=0
INSTALL_DESKTOP=1
INSTALL_PATH=1
INSTALL_GIT_HOOKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    --system) SYSTEM_INSTALL=1; shift ;;
    --no-desktop) INSTALL_DESKTOP=0; shift ;;
    --no-path) INSTALL_PATH=0; shift ;;
    --git-hooks) INSTALL_GIT_HOOKS=1; shift ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -f "$REPO_ROOT/pyproject.toml" ]]; then
  echo "错误: 未在 $REPO_ROOT 找到 pyproject.toml，请在仓库根目录运行本脚本。" >&2
  exit 1
fi

if ! command -v "$PYTHON" &>/dev/null; then
  echo "错误: 未找到解释器: $PYTHON" >&2
  exit 1
fi

py_major="$("$PYTHON" -c 'import sys; print(sys.version_info[0])')"
py_minor="$("$PYTHON" -c 'import sys; print(sys.version_info[1])')"
if [[ "$py_major" -lt 3 ]] || { [[ "$py_major" -eq 3 ]] && [[ "$py_minor" -lt 9 ]]; }; then
  echo "错误: 需要 Python 3.9+，当前为 $($PYTHON -V 2>&1)" >&2
  exit 1
fi

confirm() {
  local msg="$1"
  [[ "$ASSUME_YES" -eq 1 ]] && return 0
  read -r -p "$msg [y/N] " ans || true
  [[ "$ans" == [yY] || "$ans" == [yY][eE][sS] ]]
}

run_apt_deps() {
  command -v apt-get &>/dev/null || return 0
  echo "检测到 apt-get，可安装: python3-pip python3-tk fontconfig"
  if ! confirm "是否使用 sudo 执行 apt-get install？"; then
    echo "已跳过 apt。若缺少 Tk，请手动安装 python3-tk（见 README）。"
    return 0
  fi
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-pip python3-tk fontconfig
}

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
  run_apt_deps
fi

echo "使用 $($PYTHON -V) 在仓库目录安装 CleanUI …"
cd "$REPO_ROOT"

if [[ "$SYSTEM_INSTALL" -eq 1 ]]; then
  if ! confirm "将使用 sudo 进行系统级 pip 安装，是否继续？"; then
    exit 1
  fi
  set +e
  sudo "$PYTHON" -m pip install -e "$REPO_ROOT"
  pip_rc=$?
  if [[ "$pip_rc" -ne 0 ]]; then
    echo "首次安装失败，尝试 --break-system-packages（PEP 668 发行版）…" >&2
    sudo "$PYTHON" -m pip install --break-system-packages -e "$REPO_ROOT"
    pip_rc=$?
  fi
  set -e
  [[ "$pip_rc" -eq 0 ]] || exit "$pip_rc"
  CLEANUI_EXEC="$(command -v cleanui || true)"
else
  "$PYTHON" -m pip install --user -q --upgrade pip setuptools wheel 2>/dev/null || true
  "$PYTHON" -m pip install --user -e "$REPO_ROOT"
  USER_BASE="$("$PYTHON" -m site --user-base)"
  CLEANUI_EXEC="$USER_BASE/bin/cleanui"
fi

if [[ -x "$CLEANUI_EXEC" ]]; then
  :
elif command -v cleanui &>/dev/null; then
  CLEANUI_EXEC="$(command -v cleanui)"
fi

if [[ ! -x "$CLEANUI_EXEC" ]]; then
  echo "警告: 未找到可执行的 cleanui（请先确认 pip 已成功安装）。预期路径示例: ${USER_BASE:-$HOME/.local}/bin/cleanui" >&2
else
  echo "入口: $CLEANUI_EXEC"
  "$CLEANUI_EXEC" --version || true
fi

if [[ -n "${CLEANUI_EXEC:-}" && -x "$CLEANUI_EXEC" ]]; then
  BIN_DIR="$(dirname "$CLEANUI_EXEC")"
elif [[ "$SYSTEM_INSTALL" -eq 1 ]] && command -v cleanui &>/dev/null; then
  BIN_DIR="$(dirname "$(command -v cleanui)")"
else
  BIN_DIR="$("$PYTHON" -m site --user-base)/bin"
fi

append_path_profile() {
  local profile="$HOME/.profile"
  local marker="# cleanui: begin PATH"
  local endmk="# cleanui: end PATH"
  [[ -f "$profile" ]] || touch "$profile"
  if grep -qF "$marker" "$profile" 2>/dev/null; then
    echo "PATH 片段已存在于 $profile"
    return 0
  fi
  {
    echo ""
    echo "$marker"
    echo "export PATH=\"$BIN_DIR:\$PATH\""
    echo "$endmk"
  } >>"$profile"
  echo "已写入 $profile ：将 $BIN_DIR 加入 PATH（重新登录终端或 source ~/.profile 后生效）。"
}

if [[ "$INSTALL_PATH" -eq 1 ]] && [[ "$SYSTEM_INSTALL" -eq 0 ]]; then
  case ":${PATH:-}:" in
    *:"$BIN_DIR":*) echo "当前 PATH 已包含 $BIN_DIR" ;;
    *) append_path_profile ;;
  esac
fi

if [[ "$INSTALL_DESKTOP" -eq 1 ]] && [[ -x "${CLEANUI_EXEC:-}" ]]; then
  APP_DIR="$HOME/.local/share/applications"
  mkdir -p "$APP_DIR"
  DESKTOP_FILE="$APP_DIR/cleanui.desktop"
  cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=CleanUI 系统清理
Comment=扫描并清理 Linux 磁盘垃圾（Tkinter）
Exec=$CLEANUI_EXEC
TryExec=$CLEANUI_EXEC
Icon=preferences-system
Terminal=false
Categories=System;Filesystem;
Keywords=cleanup;disk;temp;cache;
StartupNotify=true
EOF
  chmod 0644 "$DESKTOP_FILE"
  echo "已安装桌面菜单项: $DESKTOP_FILE"
  command -v update-desktop-database &>/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

if [[ "$INSTALL_GIT_HOOKS" -eq 1 ]]; then
  if [[ -d "$REPO_ROOT/.git" ]]; then
    git -C "$REPO_ROOT" config core.hooksPath .githooks
    echo "已启用 git hooks：提交前将自动递增仓库根目录 VERSION 的补丁号。"
  else
    echo "提示: $REPO_ROOT 不是 git 克隆目录，已跳过 --git-hooks。"
  fi
fi

echo ""
echo "安装完成。新开终端后执行: cleanui"
echo "若命令未找到，请执行: source ~/.profile  或检查 PATH 是否包含 $BIN_DIR"
