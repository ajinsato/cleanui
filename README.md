# CleanUI

面向 Linux 桌面的系统垃圾扫描与清理工具，使用 Python 标准库 **Tkinter** 提供图形界面，风格接近常见「安全卫士」类一键清理体验。

## 功能概要

- 扫描：APT 缓存、旧内核、systemd 日志、回收站、缩略图、`~/.cache`（可排除项）、临时目录、pip/npm、Snap、旧 `/var/log`、常见浏览器缓存等。
- 清理：支持删除目录、清空目录内容（可排除子目录名）以及执行预置命令（如 `apt-get clean`、`journalctl --vacuum` 等，部分需 root）。
- 界面：深色主题、中文界面字体探测（fontconfig / 思源 / Noto CJK 等）、HiDPI 字体微调。

## 环境要求

- Python **3.9+**
- Linux 桌面（需要 Tk / X11 或 Wayland 下可用的 Tk）
- 可选：`fc-list`、`fc-match`（用于中文字体选择）

## 安装

```bash
cd /path/to/cleanui
python3 -m pip install --user -e .
```

安装后可直接运行：

```bash
cleanui
# 或
python3 -m cleanui
```

若命令不在 `PATH` 中，可将 Python 用户脚本目录加入环境变量（通常为 `~/.local/bin`）。

## 从旧版路径迁移

若你此前使用 `~/.local/share/cleanui/cleanui.py` 与 `~/.local/bin/cleanui` 包装脚本，可在本仓库安装后，将 `~/.local/bin/cleanui` 改为由 pip 安装的入口，或删除包装脚本改为使用 `pip install --user` 生成的 `cleanui`。

## 权限说明

部分扫描项位于系统目录；清理项若涉及 `sudo`，需在终端用有足够权限的方式启动本程序（或以 root 运行），否则命令会失败并在日志中提示。

## 开发与版本

- 源码布局：`src/cleanui/`（setuptools 包）。
- 当前版本见 `pyproject.toml` / `cleanui.__version__`。

## 许可证

MIT（见 `pyproject.toml` 中声明）。
