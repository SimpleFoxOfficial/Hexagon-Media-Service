# -*- mode: python ; coding: utf-8 -*-
"""Freezes the Python engine for the Electron shell.

    pyinstaller Engine.spec --noconfirm

Produces dist-engine/mediadl-engine.exe, which electron-builder copies into the
packaged app's resources/engine folder. It is a console-less stdio program: the
shell spawns it and speaks newline-delimited JSON, so no Qt is involved.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(os.getcwd())

# yt-dlp resolves extractors lazily, so they must be named explicitly or every
# site except the few imported at start-up fails only in the frozen build.
hiddenimports = collect_submodules("yt_dlp")
hiddenimports += [
    "HdRezkaApi", "HdRezkaApi.api", "HdRezkaApi.search", "HdRezkaApi.session",
    "HdRezkaApi.stream", "HdRezkaApi.types", "HdRezkaApi.errors",
    "bs4", "mutagen", "mutagen.id3", "mutagen.mp4", "mutagen.flac",
    "mutagen.oggvorbis", "mutagen.oggopus",
]

# The engine is headless: no Qt, no GUI toolkit of any kind.
excludes = [
    "PySide6", "PyQt5", "PyQt6", "shiboken6",
    "tkinter", "test", "unittest",
    "matplotlib", "numpy", "PIL", "pandas", "scipy", "IPython",
]

a = Analysis(
    ["engine_main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mediadl-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,          # stdio is the protocol
    hide_console="hide-early",
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
