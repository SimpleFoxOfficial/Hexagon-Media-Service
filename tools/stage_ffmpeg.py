"""Copy ffmpeg into vendor/ffmpeg so the installer can bundle it.

    python tools/stage_ffmpeg.py

The app needs ffmpeg to merge video with audio and to convert audio, and an
installer that leaves the user to find it themselves is not finished. This
resolves the real binaries (not a package-manager shim, which is only a
pointer and useless once copied) and stages them for electron-builder.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "ffmpeg"

# A shim is a few hundred KB; a real build is tens of megabytes.
MIN_REAL_BYTES = 5 * 1024 * 1024

SEARCH_ROOTS = [
    Path("C:/ProgramData/chocolatey/lib/ffmpeg"),
    Path("C:/ProgramData/chocolatey/lib/ffmpeg-full"),
    Path("C:/Program Files/ffmpeg"),
    Path("C:/ffmpeg"),
]


def resolve(name: str) -> Path | None:
    """Find a real binary, ignoring shims."""
    found = shutil.which(name)
    if found:
        path = Path(found)
        if path.stat().st_size >= MIN_REAL_BYTES:
            return path
        print(f"  {name}: {path} looks like a shim ({path.stat().st_size // 1024} KB)")

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for candidate in root.rglob(f"{name}.exe"):
            if candidate.stat().st_size >= MIN_REAL_BYTES:
                return candidate
    return None


def main() -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    missing = []

    for name in ("ffmpeg", "ffprobe"):
        target = VENDOR / f"{name}.exe"
        if target.exists() and target.stat().st_size >= MIN_REAL_BYTES:
            print(f"  {name}: already staged ({target.stat().st_size // 1024 // 1024} MB)")
            continue

        source = resolve(name)
        if source is None:
            missing.append(name)
            continue

        shutil.copy2(source, target)
        print(f"  {name}: {source} -> {target} ({target.stat().st_size // 1024 // 1024} MB)")

    if missing:
        print(
            f"\nCould not find: {', '.join(missing)}.\n"
            "Install ffmpeg (for example 'choco install ffmpeg') or drop the\n"
            f"executables into {VENDOR} by hand, then run this again.\n"
            "The build continues without them, but the installed app will not be\n"
            "able to merge or convert until ffmpeg is available."
        )
        return 1

    try:
        out = subprocess.run(
            [str(VENDOR / "ffmpeg.exe"), "-version"],
            capture_output=True, text=True, timeout=20,
        )
        print("\nStaged:", out.stdout.splitlines()[0] if out.stdout else "(no version output)")
    except Exception as exc:
        print(f"\nStaged, but could not run it: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
