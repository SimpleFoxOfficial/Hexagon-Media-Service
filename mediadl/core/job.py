"""The unit of work: one job downloads one media item."""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum

from ..config import Preset

_counter = itertools.count(1)


class JobState(str, Enum):
    QUEUED = "queued"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in (
            JobState.DONE,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.SKIPPED,
        )

    @property
    def is_active(self) -> bool:
        return self in (JobState.RESOLVING, JobState.DOWNLOADING, JobState.PROCESSING)

    @property
    def label(self) -> str:
        return {
            JobState.QUEUED: "Queued",
            JobState.RESOLVING: "Resolving",
            JobState.DOWNLOADING: "Downloading",
            JobState.PROCESSING: "Processing",
            JobState.DONE: "Completed",
            JobState.FAILED: "Failed",
            JobState.CANCELLED: "Cancelled",
            JobState.PAUSED: "Paused",
            JobState.SKIPPED: "Already downloaded",
        }[self]


@dataclass
class Job:
    """One download.

    Worker threads mutate progress fields; the UI only ever reads snapshots
    delivered through queued signals, so no locking is needed on the read side.
    """

    url: str
    preset: Preset
    id: int = field(default_factory=lambda: next(_counter))

    title: str = ""
    uploader: str = ""
    source: str = ""
    thumbnail_url: str = ""
    duration: float = 0.0

    state: JobState = JobState.QUEUED
    progress: float = 0.0
    speed: float = 0.0
    eta: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    fragment_text: str = ""

    filepath: str = ""
    error: str = ""
    added_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    # Extra yt-dlp options contributed by a source resolver (headers, referer).
    extra_opts: dict = field(default_factory=dict)
    # Metadata a resolver knows but yt-dlp cannot infer (HDRezka titles etc).
    forced_metadata: dict = field(default_factory=dict)

    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    # ----------------------------------------------------------- control flags

    def request_cancel(self) -> None:
        self._cancel.set()

    def clear_cancel(self) -> None:
        self._cancel.clear()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    # ---------------------------------------------------------------- display

    @property
    def display_title(self) -> str:
        return self.title or self.url

    @property
    def size_text(self) -> str:
        if self.total_bytes:
            return f"{human_size(self.downloaded_bytes)} / {human_size(self.total_bytes)}"
        if self.downloaded_bytes:
            return human_size(self.downloaded_bytes)
        return ""

    @property
    def speed_text(self) -> str:
        return f"{human_size(int(self.speed))}/s" if self.speed else ""

    @property
    def eta_text(self) -> str:
        return human_duration(self.eta) + " left" if self.eta else ""

    def snapshot(self) -> "Job":
        """A shallow copy safe to hand to the UI thread."""
        return replace(self)


def human_size(num: int | float) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: int | float) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
