# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec.

    pyinstaller MediaDownloader.spec --noconfirm

Set MEDIADL_ONEDIR=1 to produce a folder build instead of a single file. The
folder build starts noticeably faster because nothing has to be unpacked to a
temporary directory on each launch.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(os.getcwd())
ONEDIR = os.environ.get("MEDIADL_ONEDIR") == "1"

# yt-dlp resolves extractors lazily, so they have to be pulled in explicitly or
# every site except the few imported at start-up would fail in the bundle.
hiddenimports = collect_submodules("yt_dlp")
hiddenimports += [
    "HdRezkaApi",
    "HdRezkaApi.api",
    "HdRezkaApi.search",
    "HdRezkaApi.session",
    "HdRezkaApi.stream",
    "HdRezkaApi.types",
    "HdRezkaApi.errors",
    "bs4",
    "mutagen",
    "mutagen.id3",
    "mutagen.mp4",
    "mutagen.flac",
    "mutagen.oggvorbis",
    "mutagen.oggopus",
]

datas = [(str(ROOT / "mediadl" / "resources"), "resources")]

# Trim the bundle: none of these Qt modules are used, and PyQt5 must not be
# collected alongside PySide6 or the two clash at import time.
excludes = [
    "PyQt5", "PyQt6", "tkinter", "test", "unittest",
    "matplotlib", "numpy", "PIL", "pandas", "scipy", "IPython",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtRemoteObjects", "PySide6.QtTextToSpeech", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtVirtualKeyboard", "PySide6.QtNetworkAuth",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtHttpServer",
]

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

ICON = str(ROOT / "mediadl" / "resources" / "app.ico")

if ONEDIR:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="MediaDownloader",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="MediaDownloader",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="MediaDownloader",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON,
    )
