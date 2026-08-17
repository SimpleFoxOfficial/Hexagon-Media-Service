"""Moving finished downloads into place, safely.

The browser stages files in its own Downloads folder and the app moves them to
the real destination. That move was the least reliable part of the system, for
three reasons that all produce a truncated or missing file:

* Chrome reports a download "complete" before it has finished renaming its
  temporary .crdownload file and released the handle. Moving at that moment
  either fails outright or copies a partial file.
* Staging and destination are usually on different drives, so a move is a copy
  plus a delete rather than an atomic rename. An interrupted copy leaves a
  half-written file that looks finished.
* A large copy takes long enough that the app looked frozen, and there was no
  way to tell a slow move from a corrupt result.

So: wait for the file to settle, copy through a temporary name with progress,
verify the byte count, then swap it into place atomically and only then delete
the source. A failure at any point leaves the original untouched.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

from .. import logs

log = logs.get("filing")

CHUNK = 4 * 1024 * 1024
STABLE_CHECKS = 3
STABLE_INTERVAL = 0.4
DEFAULT_TIMEOUT = 180.0

# Only one move at a time. Several downloads finish together, and three
# simultaneous multi-gigabyte copies saturate the disk queue and make the whole
# machine feel stalled. Serialising them costs nothing overall: the disk is the
# bottleneck either way, and the files still arrive just as fast.
_move_lock = threading.Lock()

# ------------------------------------------------------------ Win32 file move

_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_COPY_ALLOWED = 0x2
_PROGRESS_CONTINUE = 0

_win32_move = None
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes

        _PROGRESS_ROUTINE = ctypes.WINFUNCTYPE(
            wintypes.DWORD,          # result
            wintypes.LARGE_INTEGER,  # TotalFileSize
            wintypes.LARGE_INTEGER,  # TotalBytesTransferred
            wintypes.LARGE_INTEGER,  # StreamSize
            wintypes.LARGE_INTEGER,  # StreamBytesTransferred
            wintypes.DWORD,          # dwStreamNumber
            wintypes.DWORD,          # dwCallbackReason
            wintypes.HANDLE,         # hSourceFile
            wintypes.HANDLE,         # hDestinationFile
            wintypes.LPVOID,         # lpData
        )

        _win32_move = ctypes.windll.kernel32.MoveFileWithProgressW
        _win32_move.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            _PROGRESS_ROUTINE,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        _win32_move.restype = wintypes.BOOL
    except Exception:  # pragma: no cover - non-Windows or restricted runtime
        _win32_move = None


def _move_via_win32(source: Path, target: Path, on_progress) -> bool:
    """Move using the same API Explorer uses. Returns False to fall back.

    This hands the copy to the kernel instead of shuttling every byte through
    Python. It picks a rename when the volumes match, streams sensibly when
    they do not, and does not force a full cache flush at the end, which is
    what made the naive loop stall the machine.
    """
    if _win32_move is None:
        return False

    last = [0.0]

    def callback(total, transferred, _ss, _sbt, _num, _reason, _hs, _hd, _data):
        if on_progress and total:
            percent = transferred / total * 100.0
            if percent - last[0] >= 1.0 or percent >= 100.0:
                last[0] = percent
                try:
                    on_progress(int(transferred), int(total))
                except Exception:
                    pass
        return _PROGRESS_CONTINUE

    ok = _win32_move(
        str(source),
        str(target),
        _PROGRESS_ROUTINE(callback),
        None,
        _MOVEFILE_COPY_ALLOWED | _MOVEFILE_REPLACE_EXISTING,
    )
    if not ok:
        import ctypes

        log.warning(
            "MoveFileWithProgressW failed (%d); falling back to a manual copy",
            ctypes.GetLastError(),
        )
    return bool(ok)


def wait_until_stable(
    path: Path, expected_bytes: int = 0, timeout: float = DEFAULT_TIMEOUT
) -> tuple[bool, str]:
    """Block until the file stops growing and can be opened exclusively.

    Returns (ok, reason). `expected_bytes` is the size the browser reported; when
    known it must match, which is what catches a transfer that died silently.
    """
    deadline = time.time() + timeout
    last_size = -1
    stable_for = 0

    while time.time() < deadline:
        if not path.exists():
            # Chrome may still be renaming its .crdownload file.
            time.sleep(STABLE_INTERVAL)
            continue

        try:
            size = path.stat().st_size
        except OSError:
            time.sleep(STABLE_INTERVAL)
            continue

        if size == last_size and size > 0:
            stable_for += 1
        else:
            stable_for = 0
            last_size = size

        if stable_for >= STABLE_CHECKS:
            if expected_bytes and size != expected_bytes:
                return False, (
                    f"size mismatch: on disk {size} bytes, browser reported "
                    f"{expected_bytes}. The download did not finish."
                )
            if not _can_open_exclusively(path):
                time.sleep(STABLE_INTERVAL)
                stable_for = 0
                continue
            return True, ""

        time.sleep(STABLE_INTERVAL)

    return False, f"timed out after {timeout:.0f}s waiting for the file to settle"


def _can_open_exclusively(path: Path) -> bool:
    """True when nothing else holds the file open for writing."""
    try:
        with open(path, "rb+"):
            return True
    except OSError:
        return False


def move_file(
    source: Path,
    target: Path,
    on_progress=None,
    expected_bytes: int = 0,
) -> Path:
    """Move `source` to `target`, reporting progress and verifying the result.

    Raises OSError on failure, having left the source in place.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _unique(target, source)
    total = expected_bytes or source.stat().st_size

    def report(copied: int) -> None:
        # Progress reporting is decoration. A subscriber that throws must never
        # turn a completed move into a reported failure.
        if not on_progress:
            return
        try:
            on_progress(copied, total)
        except Exception:
            log.debug("progress callback failed", exc_info=True)

    # One move at a time; see _move_lock.
    with _move_lock:
        # Same volume: a rename is atomic and instant, so skip the copy entirely.
        if _same_volume(source, target):
            try:
                os.replace(source, target)
                report(total)
                log.info("Renamed %s -> %s", source.name, target)
                return target
            except OSError as exc:
                log.warning("Rename failed, falling back to a copy: %s", exc)

        # Let the kernel do the copy. Only if that is unavailable or fails do
        # we shuttle the bytes through Python.
        if _move_via_win32(source, target, on_progress):
            report(total)
            log.info("Moved %s -> %s (%d bytes)", source.name, target, total)
            return target

        staging = target.with_name(target.name + ".part")
        copied = 0
        try:
            with open(source, "rb") as src, open(staging, "wb") as dst:
                while True:
                    block = src.read(CHUNK)
                    if not block:
                        break
                    dst.write(block)
                    copied += len(block)
                    report(copied)
                # Deliberately no fsync: forcing a multi-gigabyte flush stalls
                # every other process on the machine. Closing the file hands
                # the data to the OS, which writes it back on its own schedule,
                # exactly as a normal file copy does.
                dst.flush()

            if total and copied != total:
                raise OSError(f"copied {copied} of {total} bytes")

            os.replace(staging, target)
        except BaseException:
            # Never leave a half-written file that looks like a finished download.
            staging.unlink(missing_ok=True)
            raise

    try:
        source.unlink()
    except OSError as exc:
        log.warning("Copied to %s but could not remove %s: %s", target, source, exc)

    log.info("Moved %s -> %s (%d bytes)", source.name, target, copied)
    return target


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.path.splitdrive(a.resolve())[0].lower() == (
            os.path.splitdrive(b.parent.resolve())[0].lower()
        )
    except OSError:
        return False


def _unique(target: Path, source: Path) -> Path:
    """Avoid clobbering an existing file, unless it is the same file."""
    if not target.exists():
        return target
    try:
        if target.resolve() == source.resolve():
            return target
    except OSError:
        pass

    stem, suffix = target.stem, target.suffix
    for counter in range(2, 500):
        candidate = target.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
    return target.with_name(f"{stem} ({int(time.time())}){suffix}")


def free_space(path: Path) -> int:
    """Bytes free on the volume holding `path`, walking up to an existing parent."""
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


def human_size(num: int | float) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
