#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CleanUI - Linux System Cleanup Utility
360-style GUI for scanning and cleaning system junk files.
"""

import os
import sys
import shlex

# UTF-8 stdout/stderr & locale hints (helps subprocess / Tk on some distros)
os.environ.setdefault("PYTHONUTF8", "1")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import subprocess
import threading
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from pathlib import Path
from datetime import datetime

# Force Xft/fontconfig support for CJK fonts + smoother rendering on X11
os.environ.setdefault("TK_USE_XFT", "1")
os.environ.setdefault("XFT_ANTIALIAS", "true")
os.environ.setdefault("XFT_HINT_STYLE", "hintslight")
os.environ.setdefault("XFT_RGBA", "rgb")

import tkinter as tk
from tkinter import ttk, messagebox, font

from cleanui import __version__ as PACKAGE_VERSION

# ── Font Detection ──────────────────────────────────────────

def _font_family_index():
    """Tk returns families with inconsistent casing; build lookup indexes."""
    raw = font.families()
    exact = set(raw)
    lower_to_exact = {}
    for name in raw:
        lk = name.lower()
        if lk not in lower_to_exact:
            lower_to_exact[lk] = name
    return exact, lower_to_exact


def _resolve_family(preferred_name, exact, lower_to_exact):
    """Map a preferred font name to one Tk actually exposes."""
    if preferred_name in exact:
        return preferred_name
    lk = preferred_name.lower()
    if lk in lower_to_exact:
        return lower_to_exact[lk]
    return None


def _tk_font_works(family, size=10):
    try:
        test = font.Font(family=family, size=size)
        return test.metrics().get("ascent", 0) > 0
    except Exception:
        return False


def _fc_list_zh_families():
    """Ask fontconfig for fonts covering Chinese (ordered)."""
    env = {**os.environ, "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}
    try:
        r = subprocess.run(
            ["fc-list", ":lang=zh", "family"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            env=env,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        seen = []
        for line in r.stdout.splitlines():
            for part in line.split(","):
                name = part.strip()
                if name and name not in seen:
                    seen.append(name)
        return seen
    except Exception:
        return []


def _ui_sans_rank(family_name: str) -> int:
    """
    Lower = nicer for UI (modern neo-grotesque / humanist sans).
    Used when choosing among many :lang=zh fonts from fontconfig.
    """
    n = family_name.lower()
    if any(k in n for k in ("bitmap", "terminus", "courier", "mono")):
        return 80
    # Tier 1: screen-first CJK sans (usually best on Linux)
    if "source han sans" in n or "noto sans cjk" in n:
        return 0
    if "microsoft yahei" in n or "yahei" in n:
        return 2
    if "pingfang" in n:
        return 1
    if "wenquanyi zen hei" in n or "wqy zenhei" in n:
        return 5
    if "noto sans" in n and "cjk" not in n:
        return 8
    # Tier 2: okay but denser or older UI feel
    if "micro hei" in n or "microhei" in n:
        return 15
    if "droid sans fallback" in n or n == "droid sans fallback":
        return 12
    if "ar pl " in n or "uming" in n or "ukai" in n:
        return 25
    if "simhei" in n or "song ti" in n or "fangsong" in n:
        return 30
    # Serif: readable but heavier for widgets
    if "source han serif" in n or "noto serif cjk" in n:
        return 18
    if "mincho" in n or "gothic" in n or "ms gothic" in n:
        return 35
    return 20


def _detect_cjk_font():
    """Find an available CJK font that Tk can actually use (Linux-friendly)."""
    exact, lower_to_exact = _font_family_index()

    # Prefer modern UI sans first (思源 / Noto CJK 通常比点阵宋体、衬线体更适合界面)
    preferred = [
        "Source Han Sans SC",
        "Source Han Sans CN",
        "Source Han Sans HW SC",
        "Noto Sans CJK SC",
        "Noto Sans CJK TC",
        "Noto Sans CJK JP",
        "PingFang SC",
        "Microsoft YaHei",
        "WenQuanYi Zen Hei",
        "Noto Serif CJK SC",
        "Source Han Serif SC",
        "Droid Sans Fallback",
        "Noto Sans SC",
        "WenQuanYi Micro Hei",
        "AR PL UMing CN",
        "AR PL UKai CN",
        "SimHei",
        "Heiti SC",
        "Songti SC",
        "fangsong ti",
        "song ti",
        "Mincho",
        "MS Gothic",
        "WenQuanYi Bitmap Song",
    ]
    for name in preferred:
        resolved = _resolve_family(name, exact, lower_to_exact)
        if resolved and _tk_font_works(resolved):
            return resolved

    # Among fontconfig zh fonts, pick best-looking that Tk accepts
    candidates = []
    for name in _fc_list_zh_families():
        resolved = _resolve_family(name, exact, lower_to_exact)
        if resolved and _tk_font_works(resolved):
            candidates.append(( _ui_sans_rank(resolved), resolved))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][1]

    # fc-match primary family (may be comma-separated)
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{family}\n", "sans-serif:lang=zh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            env={**os.environ, "LC_ALL": "C.UTF-8"},
        )
        if result.returncode == 0 and result.stdout.strip():
            for chunk in result.stdout.strip().split(","):
                name = chunk.strip()
                resolved = _resolve_family(name, exact, lower_to_exact)
                if resolved and _tk_font_works(resolved):
                    return resolved
    except Exception:
        pass

    # Last resort: Tk built-in (better than generic sans-serif for mixing widgets)
    try:
        return font.nametofont("TkDefaultFont").cget("family")
    except Exception:
        return "sans-serif"


def _detect_cjk_mono_font(ui_font_family):
    """Monospace that still renders CJK in Text widgets; fallback to UI font."""
    exact, lower_to_exact = _font_family_index()
    for name in (
        "Source Han Mono SC",
        "Noto Sans Mono CJK SC",
        "Noto Sans Mono CJK JP",
        "WenQuanYi Zen Hei Mono",
        "Noto Sans Mono",
        "DejaVu Sans Mono",
    ):
        resolved = _resolve_family(name, exact, lower_to_exact)
        if resolved and _tk_font_works(resolved):
            return resolved
    return ui_font_family


CJK_FONT = None  # Will be initialized after Tk root is created
CJK_MONO_FONT = None
# Extra pt added to all UI fonts after Tk scaling detection (HiDPI)
_FONT_PT_EXTRA = 0


def _font(size=10, bold=False, mono=False):
    """Build a Tk font tuple using the detected CJK font."""
    fam = CJK_MONO_FONT if mono else CJK_FONT
    weight = "bold" if bold else "normal"
    try:
        sz = max(6, int(size) + _FONT_PT_EXTRA)
    except (TypeError, ValueError):
        sz = 10 + _FONT_PT_EXTRA
    return (fam, sz, weight)


def _apply_tk_named_fonts(ui_family, mono_family):
    """Point Tk logical fonts at CJK-capable families (messagebox, dialogs, etc.)."""
    body = 11 + _FONT_PT_EXTRA
    small = 10 + _FONT_PT_EXTRA
    mapping = [
        ("TkDefaultFont", ui_family, body),
        ("TkTextFont", ui_family, body),
        ("TkHeadingFont", ui_family, body + 1),
        ("TkCaptionFont", ui_family, body + 1),
        ("TkMenuFont", ui_family, body),
        ("TkFixedFont", mono_family, small),
    ]
    for logical, fam, sz in mapping:
        try:
            nf = font.nametofont(logical)
            nf.configure(family=fam, size=sz)
        except tk.TclError:
            continue


# ── Constants ──────────────────────────────────────────────

HOME = Path.home()
TMP = Path("/tmp")
VAR_TMP = Path("/var/tmp")

# Color scheme — 深色层级 + 轻微强调色
BG_ROOT = "#12121a"
BG_DARK = "#16161f"
BG_MID = "#242436"
BG_CARD = "#2a2a3e"
BG_HEADER = "#101018"
BORDER_SUBTLE = "#3d3d54"
ACCENT_BAR = "#3498db"
GREEN_SAFE = "#2ecc71"
GREEN_LIGHT = "#58d68d"
YELLOW_CAUTION = "#f4d03f"
RED_DANGER = "#ec7063"
TEXT_PRIMARY = "#ececf3"
TEXT_SECONDARY = "#a8a8c0"
TEXT_MUTED = "#6b6b82"
ACCENT_BLUE = "#5dade2"
PROGRESS_BG = "#32324a"
BTN_SCAN = "#27ae60"
BTN_SCAN_HOVER = "#2ecc71"
BTN_CLEAN = "#e74c3c"
BTN_CLEAN_HOVER = "#ff7979"
BTN_SECONDARY_HOVER = "#353550"


def _bind_btn_hover(btn, base_bg, hover_bg, active_bg=None):
    """主/次按钮悬停时背景微变（禁用时不变）。"""
    ab = active_bg or hover_bg

    def on_enter(_):
        if btn["state"] == tk.NORMAL:
            btn.config(bg=hover_bg, activebackground=ab)

    def on_leave(_):
        if btn["state"] == tk.NORMAL:
            btn.config(bg=base_bg, activebackground=ab)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)


def fmt_size(size_bytes):
    """Human-readable byte size."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    s = float(size_bytes)
    while s >= 1024 and i < len(units) - 1:
        s /= 1024
        i += 1
    if s < 10:
        return f"{s:.1f} {units[i]}"
    return f"{int(s)} {units[i]}"


def count_files(path, max_depth=3):
    """Count files in a directory up to max_depth. Returns (count, total_size)."""
    count = 0
    total_size = 0
    try:
        if max_depth <= 0:
            return 0, 0
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    count += 1
                    total_size += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    c, s = count_files(entry.path, max_depth - 1)
                    count += c
                    total_size += s
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return count, total_size


def count_files_atime_old(
    root: Path,
    age_seconds: float = 86400.0,
    max_depth: int = 128,
):
    """
    统计「访问时间早于 age_seconds 之前」的普通文件体积与数量；
    与 GNU find「-type f -atime +1」口径接近（连续时间近似，非按日历日对齐）。
    不跟随符号链接。
    """
    cutoff = time.time() - age_seconds
    count = 0
    total_size = 0
    stack = [(str(root), 0)]
    while stack:
        path, depth = stack.pop()
        if depth > max_depth:
            continue
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            st = entry.stat()
                            if st.st_atime < cutoff:
                                count += 1
                                total_size += st.st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append((entry.path, depth + 1))
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    return count, total_size


def run_cmd(cmd, timeout=30):
    """
    执行命令。cmd 为 str 时使用 shell；为 list 时使用无 shell 调用（更安全）。
    返回 (success, message)；失败时优先返回 stderr。
    """
    shell = isinstance(cmd, str)
    try:
        r = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = (r.stdout or "").strip()
        stderr = (r.stderr or "").strip()
        if r.returncode == 0:
            merged = stdout + (("\n" + stderr) if stderr else "")
            return True, merged
        detail = stderr or stdout or "(无输出)"
        return False, detail
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except Exception as e:
        return False, str(e)


# ── Scanner ─────────────────────────────────────────────────

class Scanner:
    """Scans system for junk files and returns categorized results."""

    def __init__(self, progress_callback=None):
        self.progress = progress_callback or (lambda p, msg: None)
        self.results = []

    def scan_all(self):
        self.results = []
        scanners = [
            ("APT Cache", self.scan_apt_cache),
            ("Old Kernels", self.scan_old_kernels),
            ("Journal Logs", self.scan_journal_logs),
            ("Trash", self.scan_trash),
            ("Thumbnail Cache", self.scan_thumbnail_cache),
            ("User Cache", self.scan_user_cache),
            ("Temp Files", self.scan_temp_files),
            ("pip Cache", self.scan_pip_cache),
            ("npm Cache", self.scan_npm_cache),
            ("Snap Cache", self.scan_snap_cache),
            ("Old System Logs", self.scan_old_logs),
            ("Browser Caches", self.scan_browser_caches),
        ]
        total = len(scanners)
        if not total:
            self.progress(100, "扫描完成")
            return self.results

        max_workers = min(6, total)
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_name = {pool.submit(fn): name for name, fn in scanners}
            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                try:
                    self.results.extend(fut.result() or [])
                except Exception:
                    pass
                done += 1
                pct = int(done / total * 100)
                self.progress(pct, f"扫描进度 {done}/{total}（{name}）")

        self.progress(100, "扫描完成")
        return self.results

    def scan_apt_cache(self):
        items = []
        apt_cache = Path("/var/cache/apt/archives")
        if apt_cache.exists():
            try:
                count, size = count_files(apt_cache, max_depth=2)
            except (OSError, PermissionError):
                count, size = 0, 0
            if size > 0:
                items.append({
                    "id": "apt-cache",
                    "name": "APT 软件包缓存",
                    "description": "已下载的 .deb 安装包缓存",
                    "size": size,
                    "count": count,
                    "safe_level": "caution",
                    "icon": "📦",
                    "clean_type": "command",
                    "clean_cmd": "sudo apt-get clean",
                    "clean_desc": "将运行: sudo apt-get clean"
                })
        return items

    def scan_old_kernels(self):
        items = []
        ok_u, current_ver = run_cmd(["uname", "-r"], timeout=5)
        if not ok_u:
            return items
        current_ver = current_ver.strip()
        ok, out = run_cmd(
            "dpkg -l 'linux-*' 2>/dev/null | grep -E '^ii' | grep -E 'linux-(image|headers)-[0-9]'",
            timeout=45,
        )
        if not (ok and out):
            return items
        lines = out.strip().split("\n")
        old_pkgs = []
        for line in lines:
            parts = line.split()
            if len(parts) < 2:
                continue
            pkg = parts[1]
            if current_ver in pkg:
                continue
            if re.search(r"linux-(image|headers)-\d+\.\d+\.\d+", pkg):
                old_pkgs.append(pkg)
        if not old_pkgs:
            return items
        old_count = len(old_pkgs)
        size_bytes = old_count * 80 * 1024 * 1024
        ok_sz, sz_out = run_cmd(
            ["dpkg-query", "-W", "-f", "${Installed-Size}\n"] + old_pkgs,
            timeout=60,
        )
        if ok_sz and sz_out.strip():
            total_kb = 0
            for line in sz_out.splitlines():
                line = line.strip()
                if line.isdigit():
                    total_kb += int(line)
            if total_kb > 0:
                size_bytes = total_kb * 1024
        items.append({
            "id": "old-kernels",
            "name": "旧内核文件",
            "description": f"检测到 {old_count} 个旧内核相关包（体积来自 dpkg 登记大小）",
            "size": size_bytes,
            "count": old_count,
            "safe_level": "danger",
            "icon": "🐧",
            "clean_type": "command",
            "clean_cmd": "sudo apt-get autoremove --purge -y",
            "clean_desc": "将运行: sudo apt-get autoremove --purge -y",
        })
        return items

    def scan_journal_logs(self):
        items = []
        ok, out = run_cmd(["journalctl", "--disk-usage"], timeout=15)
        if ok and out:
            m = re.search(r'(\d+\.?\d*)\s*([GMKBgm])', out)
            if m:
                val = float(m.group(1))
                unit = m.group(2).upper()
                if unit == 'G':
                    size = int(val * 1024 * 1024 * 1024)
                elif unit == 'M':
                    size = int(val * 1024 * 1024)
                elif unit == 'K':
                    size = int(val * 1024)
                else:
                    size = int(val)
                if size > 10 * 1024 * 1024:  # > 10MB
                    items.append({
                        "id": "journal-logs",
                        "name": "Systemd 日志",
                        "description": f"当前日志占用 {fmt_size(size)}",
                        "size": size,
                        "count": 0,
                        "safe_level": "caution",
                        "icon": "📋",
                        "clean_type": "command",
                        "clean_cmd": "sudo journalctl --vacuum-size=50M 2>/dev/null",
                        "clean_desc": "将保留最近50MB日志 (sudo journalctl --vacuum-size=50M)"
                    })
        return items

    def scan_trash(self):
        items = []
        for trash_base in [HOME / ".local/share/Trash", HOME / ".trash"]:
            trash_files = trash_base / "files"
            if trash_files.exists():
                count, size = count_files(trash_files, max_depth=5)
                if size > 0:
                    items.append({
                        "id": f"trash-{trash_base.name}",
                        "name": "回收站",
                        "description": str(trash_files),
                        "size": size,
                        "count": count,
                        "safe_level": "safe",
                        "icon": "🗑️",
                        "clean_type": "delete",
                        "clean_path": str(trash_files),
                        "clean_desc": "将清空回收站"
                    })
        return items

    def scan_thumbnail_cache(self):
        items = []
        thumb_dir = HOME / ".cache/thumbnails"
        if thumb_dir.exists():
            count, size = count_files(thumb_dir, max_depth=4)
            if size > 0:
                items.append({
                    "id": "thumbnails",
                    "name": "缩略图缓存",
                    "description": str(thumb_dir),
                    "size": size,
                    "count": count,
                    "safe_level": "safe",
                    "icon": "🖼️",
                    "clean_type": "delete",
                    "clean_path": str(thumb_dir),
                    "clean_desc": "将删除缩略图缓存目录内容"
                })
        return items

    def scan_user_cache(self):
        items = []
        cache_dir = HOME / ".cache"
        if cache_dir.exists():
            total_size = 0
            total_count = 0
            # List top-level cache dirs (exclude things we handle separately)
            exclude = {"thumbnails", "pip", "npm", "mozilla", "google-chrome", "chromium"}
            try:
                for entry in os.scandir(cache_dir):
                    if entry.name in exclude:
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            c, s = count_files(entry.path, max_depth=3)
                            total_count += c
                            total_size += s
                    except (OSError, PermissionError):
                        pass
            except (OSError, PermissionError):
                pass
            if total_size > 10 * 1024 * 1024:  # > 10MB
                items.append({
                    "id": "user-cache",
                    "name": "用户缓存目录",
                    "description": f"~/.cache/ (排除浏览器和包管理器)",
                    "size": total_size,
                    "count": total_count,
                    "safe_level": "safe",
                    "icon": "📁",
                    "clean_type": "delete_dir_contents",
                    "clean_path": str(cache_dir),
                    "clean_exclude": list(exclude),
                    "clean_desc": "将清理 ~/.cache 目录(保留浏览器缓存)"
                })
        return items

    def scan_temp_files(self):
        items = []
        for tmp_path, name in [(TMP, "系统临时文件 /tmp"), (VAR_TMP, "系统临时文件 /var/tmp")]:
            if tmp_path.exists():
                try:
                    count, total_size = count_files_atime_old(tmp_path)
                except (OSError, PermissionError):
                    count, total_size = 0, 0
                if total_size > 0:
                    q = shlex.quote(str(tmp_path))
                    items.append({
                        "id": f"temp-{tmp_path.name}",
                        "name": name,
                        "description": "访问时间早于约 24 小时的临时文件（与 find -atime +1 口径接近）",
                        "size": total_size,
                        "count": count,
                        "safe_level": "safe",
                        "icon": "🌡️",
                        "clean_type": "command",
                        "clean_cmd": (
                            f"find {q} -type f -atime +1 -delete 2>/dev/null; "
                            f"find {q} -type d -empty -delete 2>/dev/null"
                        ),
                        "clean_desc": f"将删除 {tmp_path} 下长时间未访问的临时文件",
                    })
        return items

    def scan_pip_cache(self):
        items = []
        pip_cache = HOME / ".cache/pip"
        if pip_cache.exists():
            count, size = count_files(pip_cache, max_depth=4)
            if size > 0:
                items.append({
                    "id": "pip-cache",
                    "name": "pip 缓存",
                    "description": str(pip_cache),
                    "size": size,
                    "count": count,
                    "safe_level": "caution",
                    "icon": "🐍",
                    "clean_type": "delete_dir_contents",
                    "clean_path": str(pip_cache),
                    "clean_desc": "将清除 pip 下载缓存"
                })
        return items

    def scan_npm_cache(self):
        items = []
        npm_cache = HOME / ".npm"
        if npm_cache.exists():
            count, size = count_files(npm_cache, max_depth=4)
            if size > 0:
                items.append({
                    "id": "npm-cache",
                    "name": "npm 缓存",
                    "description": str(npm_cache),
                    "size": size,
                    "count": count,
                    "safe_level": "caution",
                    "icon": "📦",
                    "clean_type": "command",
                    "clean_cmd": "npm cache clean --force 2>/dev/null",
                    "clean_desc": "将运行: npm cache clean --force"
                })
        return items

    def scan_snap_cache(self):
        items = []
        snap_cache = Path("/var/lib/snapd/cache")
        if snap_cache.exists():
            try:
                count, size = count_files(snap_cache, max_depth=2)
            except (OSError, PermissionError):
                count, size = 0, 0
            if size > 0:
                items.append({
                    "id": "snap-cache",
                    "name": "Snap 缓存",
                    "description": "Snap 软件包缓存文件",
                    "size": size,
                    "count": count,
                    "safe_level": "danger",
                    "icon": "📌",
                    "clean_type": "command",
                    "clean_cmd": "sudo rm -f /var/lib/snapd/cache/* 2>/dev/null",
                    "clean_desc": "将删除 Snap 缓存 (需 sudo)"
                })
        return items

    def scan_old_logs(self):
        items = []
        log_dir = Path("/var/log")
        if log_dir.exists():
            total_size = 0
            count = 0
            try:
                for entry in os.scandir(log_dir):
                    try:
                        if entry.is_file(follow_symlinks=False):
                            name = entry.name
                            st = entry.stat()
                            sz = st.st_size
                            if (
                                name.endswith((".gz", ".old", ".1", ".2", ".3", ".4", ".5"))
                                or re.search(r"\.\d{8}$", name)
                                or (name.endswith(".log") and sz > 50 * 1024 * 1024)
                            ):
                                total_size += sz
                                count += 1
                    except (OSError, PermissionError):
                        pass
            except (OSError, PermissionError):
                pass
            if total_size > 0:
                items.append({
                    "id": "old-logs",
                    "name": "旧系统日志",
                    "description": "压缩和轮转的旧日志文件",
                    "size": total_size,
                    "count": count,
                    "safe_level": "caution",
                    "icon": "📜",
                    "clean_type": "command",
                    "clean_cmd": "sudo find /var/log -type f \\( -name '*.gz' -o -name '*.old' -o -name '*.1' -o -name '*.2' -o -name '*.3' \\) -delete 2>/dev/null",
                    "clean_desc": "将删除旧的压缩日志 (需 sudo)"
                })
        return items

    def scan_browser_caches(self):
        items = []
        browsers = [
            ("Google Chrome", HOME / ".cache/google-chrome"),
            ("Chromium", HOME / ".cache/chromium"),
            ("Firefox", HOME / ".cache/mozilla/firefox"),
            ("Chrome Config", HOME / ".config/google-chrome/Default/Service Worker/CacheStorage"),
            ("Chromium Config", HOME / ".config/chromium/Default/Service Worker/CacheStorage"),
        ]
        for bname, bpath in browsers:
            if bpath.exists():
                count, size = count_files(bpath, max_depth=4)
                if size > 0:
                    items.append({
                        "id": f"browser-{bname.lower().replace(' ', '-')}",
                        "name": f"{bname} 缓存",
                        "description": str(bpath),
                        "size": size,
                        "count": count,
                        "safe_level": "safe",
                        "icon": "🌐",
                        "clean_type": "delete_dir_contents",
                        "clean_path": str(bpath),
                        "clean_desc": f"将清理 {bname} 缓存"
                    })
        return items


# ── Cleaner ─────────────────────────────────────────────────

class Cleaner:
    """Executes cleanup operations."""

    @staticmethod
    def clean_item(item, log_callback=None):
        """Clean a single item. Returns (success, message)."""
        log = log_callback or (lambda msg: None)

        ct = item.get("clean_type", "")
        try:
            if ct == "delete":
                path = item.get("clean_path", "")
                if path and os.path.exists(path):
                    log(f"删除: {path}")
                    shutil.rmtree(path)
                    return True, f"已删除 {path}"

            elif ct == "delete_dir_contents":
                path = item.get("clean_path", "")
                exclude = item.get("clean_exclude", [])
                if path and os.path.exists(path):
                    for entry in os.listdir(path):
                        if entry in exclude:
                            continue
                        full_path = os.path.join(path, entry)
                        try:
                            log(f"删除: {full_path}")
                            if os.path.isdir(full_path):
                                shutil.rmtree(full_path)
                            else:
                                os.unlink(full_path)
                        except PermissionError:
                            log(f"权限不足: {full_path}")
                        except Exception as e:
                            log(f"错误: {full_path} - {e}")
                    return True, f"已清理 {path}"

            elif ct == "command":
                cmd = item.get("clean_cmd", "")
                if cmd:
                    log(f"执行: {cmd}")
                    ok, out = run_cmd(cmd, timeout=120)
                    if ok:
                        return True, "命令执行成功"
                    tail = out.strip()
                    if len(tail) > 600:
                        tail = tail[:600] + "…"
                    return False, f"命令失败: {tail}"

        except PermissionError:
            return False, "权限不足，请使用 sudo 运行此应用"
        except Exception as e:
            return False, str(e)

        return False, "未知清理类型"


# ── GUI Application ─────────────────────────────────────────

class CleanUIApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"CleanUI · v{PACKAGE_VERSION}")
        self.root.geometry("900x720")
        self.root.minsize(640, 520)
        self.root.configure(bg=BG_ROOT)

        # Initialize CJK font after Tk root is created (needs Display for font.families)
        global CJK_FONT, CJK_MONO_FONT
        if CJK_FONT is None:
            CJK_FONT = _detect_cjk_font()
        if CJK_MONO_FONT is None:
            CJK_MONO_FONT = _detect_cjk_mono_font(CJK_FONT)

        global _FONT_PT_EXTRA
        try:
            sc = float(self.root.tk.call("tk", "scaling"))
            # scaling≈2 on many 200% fractional desktops → slightly larger type
            _FONT_PT_EXTRA = 1 if sc >= 1.45 else 0
        except Exception:
            _FONT_PT_EXTRA = 0

        _apply_tk_named_fonts(CJK_FONT, CJK_MONO_FONT)

        base_pt = 11 + _FONT_PT_EXTRA
        small_pt = 10 + _FONT_PT_EXTRA

        # Global default font for CJK support
        # Method: Use ttk.Style to set font, which works better with fontconfig
        try:
            style = ttk.Style()
            style.configure(".", font=(CJK_FONT, base_pt))
            style.configure("TProgressbar", font=(CJK_FONT, small_pt))
        except Exception:
            pass

        # Also set via option_add as fallback
        self.root.option_add("*Font", (CJK_FONT, base_pt))
        self.root.option_add("*TButton.Font", (CJK_FONT, base_pt))
        self.root.option_add("*TLabel.Font", (CJK_FONT, base_pt))
        self.root.option_add("*TkFixedFont.Font", (CJK_MONO_FONT, small_pt))

        # Set app icon (use default for now)
        try:
            self.root.iconphoto(True, tk.PhotoImage(width=1, height=1))
        except tk.TclError:
            pass

        # State
        self.scan_results = []
        self.check_vars = {}  # id -> tk.BooleanVar
        self.scanning = False
        self.cleaning = False

        # Build UI
        self._build_ui()

        # Center window
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # ── Header ──
        header_wrap = tk.Frame(self.root, bg=BG_HEADER)
        header_wrap.pack(fill=tk.X)

        header = tk.Frame(header_wrap, bg=BG_HEADER, height=86)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=BG_HEADER)
        title_frame.pack(expand=True)

        tk.Label(
            title_frame, text="🛡️", font=_font(26),
            bg=BG_HEADER, fg=GREEN_SAFE
        ).pack(side=tk.LEFT, padx=(0, 10))

        title_col = tk.Frame(title_frame, bg=BG_HEADER)
        title_col.pack(side=tk.LEFT)
        tk.Label(
            title_col, text="CleanUI 系统清理",
            font=_font(19, bold=True), bg=BG_HEADER, fg=TEXT_PRIMARY
        ).pack(anchor=tk.W)
        tk.Label(
            title_col, text=f"版本 {PACKAGE_VERSION}",
            font=_font(9), bg=BG_HEADER, fg=TEXT_MUTED
        ).pack(anchor=tk.W)

        accent = tk.Frame(header_wrap, bg=ACCENT_BAR, height=3)
        accent.pack(fill=tk.X)

        # Subtitle
        tk.Label(
            self.root, text="一键扫描 · 安全清理 · 释放磁盘空间",
            font=_font(11), bg=BG_ROOT, fg=TEXT_SECONDARY
        ).pack(pady=(12, 0))

        # ── Stats Bar ──
        self.stats_frame = tk.Frame(
            self.root,
            bg=BG_MID,
            highlightbackground=BORDER_SUBTLE,
            highlightthickness=1,
        )
        self.stats_frame.pack(fill=tk.X, padx=28, pady=(14, 0), ipady=8)

        self.stats_disk_label = tk.Label(
            self.stats_frame, text="", font=_font(11),
            bg=BG_MID, fg=TEXT_SECONDARY
        )
        self.stats_disk_label.pack(side=tk.LEFT, padx=(16, 8))

        self.stats_found_label = tk.Label(
            self.stats_frame, text="", font=_font(11),
            bg=BG_MID, fg=ACCENT_BLUE
        )
        self.stats_found_label.pack(side=tk.RIGHT, padx=(8, 16))
        self.stats_found_label.config(text="可清理: —")

        self._update_disk_info()

        # ── Control Buttons ──
        btn_frame = tk.Frame(self.root, bg=BG_ROOT)
        btn_frame.pack(pady=(18, 12))

        self.scan_btn = tk.Button(
            btn_frame, text="🔍  开始扫描", font=_font(12, bold=True),
            bg=BTN_SCAN, fg="white", activebackground=BTN_SCAN_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=28, pady=11,
            cursor="hand2", bd=0, command=self._start_scan
        )
        self.scan_btn.pack(side=tk.LEFT, padx=6)
        _bind_btn_hover(self.scan_btn, BTN_SCAN, BTN_SCAN_HOVER, BTN_SCAN_HOVER)

        self.select_all_btn = tk.Button(
            btn_frame, text="全选", font=_font(11),
            bg=BG_MID, fg=TEXT_PRIMARY, activebackground=BTN_SECONDARY_HOVER,
            activeforeground=TEXT_PRIMARY, relief=tk.FLAT, padx=18, pady=9,
            cursor="hand2", bd=0, state=tk.DISABLED, command=self._select_all
        )
        self.select_all_btn.pack(side=tk.LEFT, padx=4)
        _bind_btn_hover(self.select_all_btn, BG_MID, BTN_SECONDARY_HOVER, BTN_SECONDARY_HOVER)

        self.deselect_all_btn = tk.Button(
            btn_frame, text="取消全选", font=_font(11),
            bg=BG_MID, fg=TEXT_PRIMARY, activebackground=BTN_SECONDARY_HOVER,
            activeforeground=TEXT_PRIMARY, relief=tk.FLAT, padx=18, pady=9,
            cursor="hand2", bd=0, state=tk.DISABLED, command=self._deselect_all
        )
        self.deselect_all_btn.pack(side=tk.LEFT, padx=4)
        _bind_btn_hover(self.deselect_all_btn, BG_MID, BTN_SECONDARY_HOVER, BTN_SECONDARY_HOVER)

        self.clean_btn = tk.Button(
            btn_frame, text="🧹  立即清理", font=_font(12, bold=True),
            bg=BG_MID, fg=TEXT_MUTED, activebackground=BG_MID,
            activeforeground=TEXT_MUTED, relief=tk.FLAT, padx=28, pady=11,
            cursor="hand2", bd=0, state=tk.DISABLED, command=self._start_clean
        )
        self.clean_btn.pack(side=tk.LEFT, padx=6)

        # ── Progress Bar ──
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.root, variable=self.progress_var, maximum=100,
            style="green.Horizontal.TProgressbar"
        )
        # Hidden initially

        self.progress_label = tk.Label(
            self.root, text="", font=_font(11),
            bg=BG_ROOT, fg=TEXT_SECONDARY
        )

        # ── Results Area ──
        results_header = tk.Frame(self.root, bg=BG_DARK)
        results_header.pack(fill=tk.X, padx=28, pady=(18, 0))

        tk.Label(
            results_header, text="扫描结果",
            font=_font(13, bold=True), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(side=tk.LEFT)

        self.result_count_label = tk.Label(
            results_header, text="", font=_font(11),
            bg=BG_DARK, fg=TEXT_MUTED
        )
        self.result_count_label.pack(side=tk.RIGHT)

        # Canvas + scrollbar for results
        self.canvas_frame = tk.Frame(self.root, bg=BG_DARK)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=28, pady=(8, 12))

        self.canvas = tk.Canvas(
            self.canvas_frame, bg=BG_DARK, bd=0,
            highlightthickness=0, relief=tk.FLAT
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(
            self.canvas_frame,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg=BG_MID,
            troughcolor=BG_DARK,
            activebackground=BG_CARD,
            bd=0,
            highlightthickness=0,
            width=12,
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.results_inner = tk.Frame(self.canvas, bg=BG_DARK)
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.results_inner, anchor="nw", tags="inner"
        )

        self.results_inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel scrolling
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self.canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())

        # Placeholder
        self.placeholder_label = tk.Label(
            self.results_inner,
            text="点击「开始扫描」检测系统中的垃圾文件",
            font=_font(12), bg=BG_DARK, fg=TEXT_MUTED, pady=48
        )
        self.placeholder_label.pack()

        # ── Log area (hidden by default) ──
        self.log_frame = tk.Frame(self.root, bg=BORDER_SUBTLE)
        self.log_inner = tk.Frame(self.log_frame, bg=BG_HEADER)
        self.log_inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))
        self.log_text = tk.Text(
            self.log_inner, height=6, bg="#0b0b14", fg=TEXT_SECONDARY,
            font=_font(10, mono=True), bd=0, padx=12, pady=10,
            insertbackground=TEXT_PRIMARY, state=tk.DISABLED,
            selectbackground=BG_CARD,
        )
        self.log_scrollbar = tk.Scrollbar(
            self.log_inner, orient=tk.VERTICAL, command=self.log_text.yview,
            bg=BG_MID, troughcolor="#0b0b14", activebackground=BG_CARD,
            bd=0, highlightthickness=0, width=11,
        )
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)

        # ── Status Bar ──
        self.status_var = tk.StringVar(value="就绪")
        self._bottom_frame = tk.Frame(self.root, bg=BG_HEADER)
        tk.Frame(self._bottom_frame, height=1, bg=BORDER_SUBTLE).pack(fill=tk.X)
        tk.Label(
            self._bottom_frame, textvariable=self.status_var, font=_font(10),
            bg=BG_HEADER, fg=TEXT_MUTED, anchor=tk.W, padx=18, pady=8,
        ).pack(fill=tk.X)
        self._bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Configure ttk styles
        self._setup_styles()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "green.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG,
            background=GREEN_SAFE,
            bordercolor=BG_ROOT,
            lightcolor=GREEN_SAFE,
            darkcolor=GREEN_SAFE,
            thickness=10,
        )

    def _bind_mousewheel(self):
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self):
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        n = 3
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-n, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(n, "units")

    def _on_inner_configure(self, event):
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _update_disk_info(self):
        """Update disk usage info."""
        try:
            usage = shutil.disk_usage(HOME)
            free = usage.free
            total = usage.total
            pct = (1 - free / total) * 100
            self.stats_disk_label.config(
                text=f"💾 磁盘: {fmt_size(free)} 可用 / {fmt_size(total)} ({pct:.0f}% 已用)"
            )
        except OSError:
            self.stats_disk_label.config(text="💾 磁盘信息不可用")

    # ── Scan ──

    def _start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_results = []
        self.check_vars.clear()

        # Reset UI
        for widget in self.results_inner.winfo_children():
            widget.destroy()

        self.scan_btn.config(text="⏳ 扫描中...", bg=BG_MID, state=tk.DISABLED)
        self.clean_btn.config(state=tk.DISABLED, bg=BG_MID, fg=TEXT_MUTED)
        self.select_all_btn.config(state=tk.DISABLED)
        self.deselect_all_btn.config(state=tk.DISABLED)
        self.result_count_label.config(text="")

        # Show progress
        self.progress_bar.pack(fill=tk.X, padx=28, pady=(5, 0))
        self.progress_label.pack(pady=(2, 0))
        self.progress_var.set(0)
        self.progress_label.config(text="正在初始化扫描...")
        self.status_var.set("扫描中...")
        self.stats_found_label.config(text="可清理: 扫描中…")

        # Run scan in thread
        t = threading.Thread(target=self._run_scan, daemon=True)
        t.start()

    def _run_scan(self):
        scanner = Scanner(progress_callback=self._scan_progress)
        try:
            results = scanner.scan_all()
        except Exception as e:
            results = []
            self.root.after(0, lambda: messagebox.showerror("扫描错误", str(e)))

        self.scan_results = results
        self.root.after(0, self._on_scan_done)

    def _scan_progress(self, pct, msg):
        self.root.after(0, lambda: self._update_progress(pct, msg))

    def _update_progress(self, pct, msg):
        self.progress_var.set(pct)
        self.progress_label.config(text=msg)

    def _on_scan_done(self):
        self.scanning = False
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()

        self.scan_btn.config(
            text="🔍  重新扫描",
            bg=BTN_SCAN,
            state=tk.NORMAL,
            activebackground=BTN_SCAN_HOVER,
        )

        if not self.scan_results:
            self.placeholder_label = tk.Label(
                self.results_inner,
                text="🎉 太棒了！没有发现需要清理的垃圾文件",
                font=_font(13), bg=BG_DARK, fg=GREEN_SAFE, pady=60
            )
            self.placeholder_label.pack()
            self.status_var.set("扫描完成 - 系统很干净")
            self.result_count_label.config(text="发现 0 项")
            self.stats_found_label.config(text="可清理: 0 项")
            self._update_disk_info()
            return

        total_size = sum(item["size"] for item in self.scan_results)
        self.stats_found_label.config(
            text=f"可清理: {len(self.scan_results)} 项 · {fmt_size(total_size)}"
        )
        self.result_count_label.config(
            text=f"发现 {len(self.scan_results)} 项，共 {fmt_size(total_size)}"
        )

        self._render_results()
        self._update_clean_btn()
        self.status_var.set(f"扫描完成 - 发现 {len(self.scan_results)} 项可清理")
        self._update_disk_info()

    # ── Render Results ──

    def _render_results(self):
        # Clear
        for widget in self.results_inner.winfo_children():
            widget.destroy()

        # Summary card（Frame 不允许构造参数 padx/pady，须用内层 + pack）
        total_size = sum(item["size"] for item in self.scan_results)
        summary = tk.Frame(
            self.results_inner,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER_SUBTLE,
        )
        summary.pack(fill=tk.X, pady=(0, 12))
        summary_body = tk.Frame(summary, bg=BG_CARD)
        summary_body.pack(fill=tk.X, padx=16, pady=14)

        tk.Label(
            summary_body, text=f"共发现 {len(self.scan_results)} 项可清理",
            font=_font(13, bold=True), bg=BG_CARD, fg=TEXT_PRIMARY
        ).pack(anchor=tk.W)

        tk.Label(
            summary_body, text=f"预计可释放约 {fmt_size(total_size)}",
            font=_font(11), bg=BG_CARD, fg=GREEN_LIGHT
        ).pack(anchor=tk.W, pady=(6, 0))

        # Legend（胶囊标签）
        legend = tk.Frame(self.results_inner, bg=BG_DARK)
        legend.pack(fill=tk.X, pady=(0, 10))
        for text, color in [
            ("●  安全", GREEN_SAFE),
            ("●  建议", YELLOW_CAUTION),
            ("●  注意", RED_DANGER),
        ]:
            pill = tk.Frame(legend, bg=BG_MID, highlightthickness=0)
            pill.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(
                pill, text=text, font=_font(10), bg=BG_MID, fg=color
            ).pack(padx=12, pady=6)

        # Category items
        for item in self.scan_results:
            self._render_item(item)

        self.canvas.yview_moveto(0)
        self.results_inner.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)

    def _render_item(self, item):
        item_id = item["id"]
        var = tk.BooleanVar(value=True)
        self.check_vars[item_id] = var

        safe_level = item["safe_level"]
        color_map = {
            "safe": GREEN_SAFE,
            "caution": YELLOW_CAUTION,
            "danger": RED_DANGER,
        }
        level_color = color_map.get(safe_level, TEXT_SECONDARY)

        row = tk.Frame(self.results_inner, bg=BG_DARK)
        row.pack(fill=tk.X, pady=5)

        stripe = tk.Frame(row, bg=level_color, width=4)
        stripe.pack(side=tk.LEFT, fill=tk.Y)
        stripe.pack_propagate(False)

        card = tk.Frame(
            row,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER_SUBTLE,
        )
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        card_body = tk.Frame(card, bg=BG_CARD)
        card_body.pack(fill=tk.BOTH, expand=True, padx=(12, 14), pady=12)

        cb = tk.Checkbutton(
            card_body,
            variable=var,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            selectcolor=BG_ROOT,
            activebackground=BG_CARD,
            activeforeground=TEXT_PRIMARY,
            command=self._update_clean_btn,
            bd=0,
            highlightthickness=0,
        )
        cb.pack(side=tk.LEFT)

        tk.Label(
            card_body, text=item.get("icon", "📄"), font=_font(17),
            bg=BG_CARD
        ).pack(side=tk.LEFT, padx=(4, 12))

        info_frame = tk.Frame(card_body, bg=BG_CARD)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            info_frame, text=item["name"], font=_font(12, bold=True),
            bg=BG_CARD, fg=TEXT_PRIMARY
        ).pack(anchor=tk.W)

        desc = item.get("description", "")
        if desc:
            tk.Label(
                info_frame, text=desc, font=_font(10),
                bg=BG_CARD, fg=TEXT_SECONDARY,
                wraplength=520,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)

        right_frame = tk.Frame(card_body, bg=BG_CARD)
        right_frame.pack(side=tk.RIGHT, padx=(8, 0))

        tk.Label(
            right_frame, text=fmt_size(item["size"]),
            font=_font(13, bold=True), bg=BG_CARD, fg=level_color
        ).pack(anchor=tk.E)

        level_labels = {"safe": "安全", "caution": "建议", "danger": "注意"}
        tk.Label(
            right_frame, text=level_labels.get(safe_level, ""),
            font=_font(9), bg=BG_CARD, fg=level_color
        ).pack(anchor=tk.E)

    # ── Actions ──

    def _sync_clean_btn_hover(self):
        for ev in ("<Enter>", "<Leave>"):
            self.clean_btn.unbind(ev)
        if self.clean_btn["state"] != tk.NORMAL:
            return
        try:
            bg = self.clean_btn.cget("bg")
        except tk.TclError:
            return
        if bg == BTN_CLEAN:
            _bind_btn_hover(
                self.clean_btn, BTN_CLEAN, BTN_CLEAN_HOVER, BTN_CLEAN_HOVER
            )
        elif bg == GREEN_SAFE:
            _bind_btn_hover(
                self.clean_btn, GREEN_SAFE, GREEN_LIGHT, GREEN_LIGHT
            )

    def _select_all(self):
        for var in self.check_vars.values():
            var.set(True)
        self._update_clean_btn()

    def _deselect_all(self):
        for var in self.check_vars.values():
            var.set(False)
        self._update_clean_btn()

    def _update_clean_btn(self):
        if self.scanning:
            return

        has_results = len(self.scan_results) > 0
        any_checked = any(v.get() for v in self.check_vars.values())

        if has_results:
            self.select_all_btn.config(state=tk.NORMAL)
            self.deselect_all_btn.config(state=tk.NORMAL)
        else:
            self.select_all_btn.config(state=tk.DISABLED)
            self.deselect_all_btn.config(state=tk.DISABLED)

        if any_checked:
            selected_size = sum(
                item["size"] for item in self.scan_results
                if self.check_vars.get(item["id"], tk.BooleanVar(value=False)).get()
            )
            self.clean_btn.config(
                text=f"🧹  清理选中 ({fmt_size(selected_size)})",
                state=tk.NORMAL,
                bg=BTN_CLEAN,
                fg="white",
                activebackground=BTN_CLEAN_HOVER,
                activeforeground="white",
            )
        else:
            self.clean_btn.config(
                text="🧹  立即清理",
                state=tk.DISABLED,
                bg=BG_MID,
                fg=TEXT_MUTED,
                activebackground=BG_MID,
                activeforeground=TEXT_MUTED,
            )
        self._sync_clean_btn_hover()

    # ── Clean ──

    def _start_clean(self):
        if self.cleaning:
            return

        selected = [
            item for item in self.scan_results
            if self.check_vars.get(item["id"], tk.BooleanVar(value=False)).get()
        ]

        if not selected:
            return

        # Show confirmation
        total = sum(item["size"] for item in selected)
        has_danger = any(item["safe_level"] == "danger" for item in selected)

        msg = f"确认清理 {len(selected)} 项，释放 {fmt_size(total)} 空间？"
        if has_danger:
            msg += "\n\n⚠️  包含高风险项目，请确认后再操作"

        if not messagebox.askyesno("确认清理", msg, parent=self.root):
            return

        self.cleaning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.clean_btn.config(text="⏳ 清理中...", state=tk.DISABLED)
        self.select_all_btn.config(state=tk.DISABLED)
        self.deselect_all_btn.config(state=tk.DISABLED)
        self.status_var.set("正在清理...")

        # Show log
        self.log_frame.pack(fill=tk.X, padx=28, pady=(6, 8))
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 开始清理 {len(selected)} 项...\n")
        self.log_text.see(tk.END)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.selected_items = selected
        self.clean_index = 0
        self.clean_success = 0
        self.clean_failed = 0

        t = threading.Thread(target=self._run_clean, daemon=True)
        t.start()

    def _log(self, msg):
        self.root.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _run_clean(self):
        for item in self.selected_items:
            self._log(f"正在处理: {item['name']}...")
            success, msg = Cleaner.clean_item(item, log_callback=self._log)
            if success:
                self.clean_success += 1
                self._log(f"  ✓ {msg}")
            else:
                self.clean_failed += 1
                self._log(f"  ✗ {msg}")

        self._log(f"\n清理完成! 成功: {self.clean_success}, 失败: {self.clean_failed}")
        self.root.after(0, self._on_clean_done)

    def _on_clean_done(self):
        self.cleaning = False
        self.scan_btn.config(state=tk.NORMAL)
        self.status_var.set(
            f"清理完成 - 成功 {self.clean_success} 项, 失败 {self.clean_failed} 项"
        )

        if self.clean_failed == 0:
            self.clean_btn.config(
                text="✅ 清理完成",
                state=tk.DISABLED,
                bg=GREEN_SAFE,
                fg="white",
                activebackground=GREEN_SAFE,
            )
            self._sync_clean_btn_hover()
        else:
            self._update_clean_btn()

        self._update_disk_info()

        # Prompt re-scan
        if self.clean_success > 0:
            self.root.after(500, lambda: messagebox.showinfo(
                "清理完成",
                f"成功清理 {self.clean_success} 项\n失败 {self.clean_failed} 项\n\n建议重新扫描确认结果",
                parent=self.root
            ))


def _gui_environment_ready():
    """在无 DISPLAY / WAYLAND_DISPLAY 时无法弹出 Tk 窗口（--version / --help 仍可用）。"""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="cleanui",
        description="Linux 系统垃圾扫描与清理（图形界面）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {PACKAGE_VERSION}",
    )
    parser.parse_args()

    if not _gui_environment_ready():
        print(
            "CleanUI 需要图形桌面会话（请设置 DISPLAY 或 WAYLAND_DISPLAY）。",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        app = CleanUIApp()
    except tk.TclError as e:
        print(f"无法初始化图形界面: {e}", file=sys.stderr)
        sys.exit(1)
    app.root.mainloop()


if __name__ == "__main__":
    main()
