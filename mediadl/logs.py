"""Application logging.

Everything goes to a rotating file in the settings folder, and the last few
thousand records are also kept in memory so the Logs screen can show them
without reading the file back. Job-scoped messages carry their job id so a
single download can be filtered out of the stream.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import traceback
from collections import deque

from . import paths

MAX_MEMORY_RECORDS = 4000
FILE_BYTES = 2_000_000
FILE_BACKUPS = 3

FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False
_lock = threading.Lock()


class RingBuffer(logging.Handler):
    """Keeps recent records in memory for the Logs view."""

    def __init__(self, capacity: int = MAX_MEMORY_RECORDS):
        super().__init__()
        self._records: deque[tuple[int, str, str]] = deque(maxlen=capacity)
        self._listeners: list = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except Exception:
            return
        job_id = int(getattr(record, "job_id", 0) or 0)
        entry = (job_id, record.levelname, text)
        self._records.append(entry)
        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:
                pass

    def lines(self, job_id: int | None = None, level: str = "") -> list[str]:
        out = []
        for entry_job, entry_level, text in self._records:
            if job_id is not None and entry_job != job_id:
                continue
            if level and entry_level != level:
                continue
            out.append(text)
        return out

    def clear(self) -> None:
        self._records.clear()

    def subscribe(self, callback) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)


_ring = RingBuffer()


def ring() -> RingBuffer:
    return _ring


def setup(verbose: bool = False) -> None:
    """Install handlers once. Safe to call repeatedly."""
    global _configured
    with _lock:
        if _configured:
            _set_level(verbose)
            return

        formatter = logging.Formatter(FORMAT, datefmt=DATEFMT)
        root = logging.getLogger("mediadl")
        root.propagate = False

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                paths.log_file(),
                maxBytes=FILE_BYTES,
                backupCount=FILE_BACKUPS,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            pass  # A read-only settings folder must not stop the app.

        _ring.setFormatter(formatter)
        root.addHandler(_ring)

        # Only useful when launched from a terminal; the windowed exe has no
        # console and sys.stderr can be None there.
        if sys.stderr is not None:
            stream = logging.StreamHandler(sys.stderr)
            stream.setFormatter(formatter)
            root.addHandler(stream)

        _configured = True
        _set_level(verbose)

        root.info("=" * 60)
        root.info("Media Downloader starting")
        root.info("python %s", sys.version.split()[0])
        root.info("frozen=%s log=%s", paths.is_frozen(), paths.log_file())


def _set_level(verbose: bool) -> None:
    logging.getLogger("mediadl").setLevel(logging.DEBUG if verbose else logging.INFO)


def get(name: str) -> logging.Logger:
    """A child logger. `name` is appended to the mediadl root."""
    return logging.getLogger(f"mediadl.{name}")


def exception(logger: logging.Logger, message: str, exc: BaseException, **kwargs) -> None:
    """Log an error with its full traceback, which is what makes bugs findable."""
    logger.error("%s: %s: %s", message, type(exc).__name__, exc, extra=kwargs)
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    for line in detail.rstrip().splitlines():
        logger.debug("    %s", line, extra=kwargs)


def describe_environment() -> list[tuple[str, str]]:
    """Version table used by the About and Logs screens and written at startup."""
    rows: list[tuple[str, str]] = []
    try:
        import yt_dlp

        rows.append(("yt-dlp", getattr(yt_dlp.version, "__version__", "unknown")))
    except Exception:
        rows.append(("yt-dlp", "not installed"))
    try:
        import HdRezkaApi

        rows.append(("HdRezkaApi", getattr(HdRezkaApi, "__version__", "installed")))
    except Exception:
        rows.append(("HdRezkaApi", "not installed"))
    ffmpeg = paths.find_ffmpeg("")
    rows.append(("ffmpeg", str(ffmpeg) if ffmpeg else "NOT FOUND"))
    return rows
