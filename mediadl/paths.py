"""Filesystem locations. Everything user-writable lives under %APPDATA%\\MediaDownloader."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import shutil
import sys
import uuid
from pathlib import Path

from . import APP_ID


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Directory that read-only resources are loaded from."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resource(*parts: str) -> Path:
    return bundle_dir().joinpath("resources", *parts)


def config_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    path = root / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return config_dir() / "settings.json"


def history_file() -> Path:
    return config_dir() / "history.json"


def archive_file() -> Path:
    return config_dir() / "download-archive.txt"


def log_file() -> Path:
    return config_dir() / "mediadl.log"


def cache_dir() -> Path:
    path = config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Windows knows where Downloads actually is; it is not always ~/Downloads.
_FOLDERID_DOWNLOADS = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, value: uuid.UUID):
        super().__init__()
        raw = value.bytes_le
        self.Data1 = int.from_bytes(raw[0:4], "little")
        self.Data2 = int.from_bytes(raw[4:6], "little")
        self.Data3 = int.from_bytes(raw[6:8], "little")
        for i in range(8):
            self.Data4[i] = raw[8 + i]


def default_download_dir() -> Path:
    """The real Downloads folder, falling back to ~/Downloads."""
    if sys.platform == "win32":
        try:
            buf = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(_GUID(_FOLDERID_DOWNLOADS)), 0, None, ctypes.byref(buf)
            )
            if res == 0 and buf.value:
                path = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return path
        except Exception:
            pass
    return Path.home() / "Downloads"


def find_ffmpeg(hint: str = "") -> Path | None:
    """Locate ffmpeg: explicit setting, then bundled copy, then PATH."""
    if hint:
        candidate = Path(hint)
        if candidate.is_dir():
            candidate = candidate / "ffmpeg.exe"
        if candidate.exists():
            return candidate

    # Packaged layout is resources/engine/mediadl-engine.exe alongside
    # resources/ffmpeg/, so the sibling directory is checked as well as our own.
    root = bundle_dir()
    for candidate in (
        root / "ffmpeg" / "ffmpeg.exe",
        root.parent / "ffmpeg" / "ffmpeg.exe",
        root.parent.parent / "ffmpeg" / "ffmpeg.exe",
    ):
        if candidate.exists():
            return candidate

    found = shutil.which("ffmpeg")
    return Path(found) if found else None
