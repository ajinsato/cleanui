#!/usr/bin/env bash
# CleanUI 一键安装：默认检测并安装系统依赖，再进行 pip 安装、PATH 与桌面菜单。
set -euo pipefail

usage() {
  sed -n '1,95p' <<'EOF'
用法: ./install.sh [选项]

默认行为：
  - 检测 Python 3.9+、pip、Tkinter（图形界面必需）；缺则用系统包管理器尝试安装（需 sudo）
  - 用户级可编辑安装 pip install --user -e .
  - 按需写入 ~/.profile 中的 PATH、安装桌面菜单项

选项:
  -h, --help           显示本说明
  -y, --yes            非交互：自动同意 sudo 安装系统依赖等
  --no-install-deps    不安装系统依赖（仅靠当前环境；缺 Tk/pip 时会报错）
  --install-deps       与默认相同（显式开启），便于脚本可读性
  --system             系统级 pip 安装（sudo）；部分发行版需 PEP 668 回退参数
  --no-desktop         不写入 ~/.local/share/applications/cleanui.desktop
  --no-path            不修改 ~/.profile 中的 PATH
  --git-hooks          设置 core.hooksPath=.githooks（提交前递增 VERSION）

环境变量:
  PYTHON=python3       首选的解释器命令名（须在 PATH 中，或安装依赖后会可用）

示例:
  ./install.sh              # 自动检查依赖 + 安装（交互确认 sudo）
  ./install.sh -y           # CI / 无人值守
  ./install.sh --no-install-deps   # 已知环境已齐备
EOF
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD="${PYTHON:-python3}"
INSTALL_DEPS=1
ASSUME_YES=0
SYSTEM_INSTALL=0
INSTALL_DESKTOP=1
INSTALL_PATH=1
INSTALL_GIT_HOOKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --no-install-deps) INSTALL_DEPS=0; shift ;;
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

confirm() {
  local msg="$1"
  [[ "$ASSUME_YES" -eq 1 ]] && return 0
  read -r -p "$msg [y/N] " ans || true
  [[ "$ans" == [yY] || "$ans" == [yY][eE][sS] ]]
}

resolve_python_bin() {
  if command -v "$PYTHON_CMD" &>/dev/null; then
    PYTHON="$(command -v "$PYTHON_CMD")"
    return 0
  fi
  return 1
}

py_version_ok() {
  local ma mi
  ma="$("$PYTHON" -c 'import sys; print(sys.version_info[0])')"
  mi="$("$PYTHON" -c 'import sys; print(sys.version_info[1])')"
  [[ "$ma" -gt 3 ]] || { [[ "$ma" -eq 3 ]] && [[ "$mi" -ge 9 ]]; }
}

py_has_pip() {
  "$PYTHON" -m pip --version &>/dev/null
}

py_has_tk() {
  "$PYTHON" -c "import tkinter" &>/dev/null
}

print_missing_runtime() {
  echo "运行时检测结果 ($PYTHON):" >&2
  py_version_ok && echo "  Python 版本: OK ($("$PYTHON" -V 2>&1))" >&2 || echo "  Python 版本: 需要 3.9+" >&2
  py_has_pip && echo "  pip: OK" >&2 || echo "  pip: 缺失" >&2
  py_has_tk && echo "  tkinter: OK" >&2 || echo "  tkinter: 缺失（需安装 python3-tk 等）" >&2
}

install_deps_apt() {
  command -v apt-get &>/dev/null || return 1
  echo "[依赖] 使用 apt-get 安装: python3 python3-pip python3-tk fontconfig …"
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-pip python3-tk fontconfig
  return 0
}

install_deps_dnf() {
  command -v dnf &>/dev/null || return 1
  echo "[依赖] 使用 dnf 安装: python3 python3-pip python3-tkinter …"
  sudo dnf install -y python3 python3-pip python3-tkinter fontconfig
  return 0
}

install_deps_yum() {
  command -v yum &>/dev/null || return 1
  echo "[依赖] 使用 yum 安装: python3 python3-pip python3-tkinter …"
  sudo yum install -y python3 python3-pip python3-tkinter fontconfig
  return 0
}

install_deps_pacman() {
  command -v pacman &>/dev/null || return 1
  echo "[依赖] 使用 pacman 安装: python python-pip tk …"
  sudo pacman -S --needed --noconfirm python python-pip tk fontconfig
  return 0
}

run_os_dependency_install() {
  if [[ "$INSTALL_DEPS" -ne 1 ]]; then
    return 1
  fi
  echo "检测到缺少 Python 运行时组件，尝试通过系统包管理器安装（需要管理员权限）。"
  if ! confirm "是否继续？"; then
    echo "已跳过系统依赖安装。"
    return 1
  fi
  if install_deps_apt; then return 0; fi
  if install_deps_dnf; then return 0; fi
  if install_deps_yum; then return 0; fi
  if install_deps_pacman; then return 0; fi
  echo "错误: 未识别到支持的包管理器（apt-get / dnf / yum / pacman）。请手动安装 Python3.9+、pip、python3-tk。" >&2
  return 1
}

ensure_runtime() {
  local round=0
  while [[ "$round" -lt 3 ]]; do
    round=$((round + 1))

    if ! resolve_python_bin; then
      echo "未找到命令: $PYTHON_CMD" >&2
      if [[ "$INSTALL_DEPS" -eq 1 ]] && run_os_dependency_install; then
        continue
      fi
      echo "错误: 请先安装 Python 3.9+，或将 PYTHON 指向可用的 python3。" >&2
      exit 1
    fi

    echo "使用解释器: $PYTHON ($("$PYTHON" -V 2>&1))"

    if ! py_version_ok; then
      echo "错误: 需要 Python 3.9+，当前为 $($PYTHON -V 2>&1)" >&2
      if [[ "$INSTALL_DEPS" -eq 1 ]] && [[ "$round" -eq 1 ]] && run_os_dependency_install; then
        continue
      fi
      exit 1
    fi

    local need_install=0
    py_has_pip || need_install=1
    py_has_tk || need_install=1

    if [[ "$need_install" -eq 0 ]]; then
      echo "[依赖] Python / pip / tkinter 检测通过。"
      return 0
    fi

    print_missing_runtime
    if [[ "$INSTALL_DEPS" -ne 1 ]]; then
      echo "错误: 当前环境缺少 pip 或 tkinter，请去掉 --no-install-deps 或手动安装后重试。" >&2
      exit 1
    fi

    if run_os_dependency_install; then
      continue
    fi
    exit 1
  done

  echo "错误: 依赖安装后仍无法通过检测。" >&2
  print_missing_runtime
  exit 1
}

ensure_runtime

echo ""
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
