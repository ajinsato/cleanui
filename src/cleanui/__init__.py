"""CleanUI — Linux 系统清理图形工具。"""

from pathlib import Path


def _read_version() -> str:
    """优先读取源码树中的 VERSION；否则使用已安装包的元数据。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        vf = parent / "VERSION"
        if vf.is_file():
            text = vf.read_text(encoding="utf-8").strip()
            if text:
                return text
    try:
        from importlib.metadata import version

        return version("cleanui")
    except Exception:
        return "0.0.0"


__version__ = _read_version()
