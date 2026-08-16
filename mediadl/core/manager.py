"""Queue orchestration: holds every job and decides what runs next."""

from __future__ import annotations

import json
import threading
import time
from collections import deque

from concurrent.futures import ThreadPoolExecutor

from .. import paths
from ..config import Preset, Settings
from .engine import DownloadSignals, DownloadTask, ExpandTask
from .events import Emitter
from .job import Job, JobState

MAX_LOG_LINES = 200
MAX_HISTORY = 500


class DownloadManager:
    """Owns the job list and feeds a thread pool.

    Concurrency is enforced here rather than by the pool size so the limit can
    change while downloads are in flight. Toolkit-free: subscribers receive
    events on whichever worker thread produced them and are responsible for
    hopping to their own loop.
    """

    def __init__(self, settings: Settings, parent=None):
        self.settings = settings

        self.jobsAdded = Emitter("jobsAdded")
        self.jobChanged = Emitter("jobChanged")
        self.jobFinished = Emitter("jobFinished")
        self.jobsRemoved = Emitter("jobsRemoved")
        self.statsChanged = Emitter("statsChanged")
        self.expandStarted = Emitter("expandStarted")
        self.expandFinished = Emitter("expandFinished")
        self.busyMessage = Emitter("busyMessage")

        self._jobs: dict[int, Job] = {}
        self._order: list[int] = []
        self._logs: dict[int, deque[str]] = {}
        self._running: set[int] = set()
        self._lock = threading.RLock()

        self._pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="mediadl-dl")
        self._expand_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mediadl-ex")

        self._signals = DownloadSignals()
        self._signals.updated.connect(self._on_updated)
        self._signals.finished.connect(self._on_finished)
        self._signals.log.connect(self._on_log)

        self._paused = False

    # ------------------------------------------------------------- accessors

    @property
    def jobs(self) -> list[Job]:
        return [self._jobs[i] for i in self._order if i in self._jobs]

    def job(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def logs(self, job_id: int) -> list[str]:
        return list(self._logs.get(job_id, ()))

    @property
    def is_paused(self) -> bool:
        return self._paused

    def stats(self) -> dict:
        counts = {state: 0 for state in JobState}
        for job in self._jobs.values():
            counts[job.state] += 1
        active = counts[JobState.DOWNLOADING] + counts[JobState.PROCESSING]
        return {
            "total": len(self._jobs),
            "queued": counts[JobState.QUEUED],
            "active": active,
            "done": counts[JobState.DONE] + counts[JobState.SKIPPED],
            "failed": counts[JobState.FAILED],
            "paused": counts[JobState.PAUSED],
            "speed": sum(
                self._jobs[i].speed for i in self._running if i in self._jobs
            ),
        }

    # ----------------------------------------------------------------- adding

    def add_urls(self, urls: list[str], preset: Preset) -> None:
        """Expand user input on a background thread, then queue the results."""
        cleaned = [u.strip() for u in urls if u.strip()]
        if not cleaned:
            return

        self.expandStarted.emit()
        task = ExpandTask(cleaned, self.settings.behaviour, preset)
        task.signals.ready.connect(self._on_expanded)
        task.signals.progress.connect(self.busyMessage.emit)
        self._expand_pool.submit(task.run)

    def add_jobs(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        added: list[int] = []
        for job in jobs:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._logs[job.id] = deque(maxlen=MAX_LOG_LINES)
            added.append(job.id)

        self.jobsAdded.emit(added)
        self._pump()
        self._emit_stats()

    def _on_expanded(self, jobs: list, error: str) -> None:
        self.add_jobs(list(jobs))
        self.expandFinished.emit(error)

    # ---------------------------------------------------------------- control

    def start_all(self) -> None:
        self._paused = False
        for job in self.jobs:
            if job.state == JobState.PAUSED:
                job.state = JobState.QUEUED
                self.jobChanged.emit(job.id)
        self._pump()
        self._emit_stats()

    def pause_all(self) -> None:
        """Stop feeding new work and cancel what is running, keeping partials."""
        self._paused = True
        for job in self.jobs:
            if job.state == JobState.QUEUED:
                job.state = JobState.PAUSED
                self.jobChanged.emit(job.id)
            elif job.state.is_active:
                job.request_cancel()
                job.state = JobState.PAUSED
                self.jobChanged.emit(job.id)
        self._emit_stats()

    def cancel(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.state.is_terminal:
            return
        job.request_cancel()
        if job.state in (JobState.QUEUED, JobState.PAUSED):
            job.state = JobState.CANCELLED
            self.jobChanged.emit(job_id)
            self._emit_stats()

    def pause(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.state.is_terminal:
            return
        job.request_cancel()
        job.state = JobState.PAUSED
        self.jobChanged.emit(job_id)
        self._emit_stats()

    def resume(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        if job.state in (JobState.PAUSED, JobState.CANCELLED, JobState.FAILED):
            job.clear_cancel()
            job.state = JobState.QUEUED
            job.error = ""
            self.jobChanged.emit(job_id)
            self._pump()
            self._emit_stats()

    def retry(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.clear_cancel()
        job.state = JobState.QUEUED
        job.error = ""
        job.progress = 0.0
        job.downloaded_bytes = 0
        self._logs[job_id] = deque(maxlen=MAX_LOG_LINES)
        self.jobChanged.emit(job_id)
        self._pump()
        self._emit_stats()

    def remove(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.request_cancel()
        self._jobs.pop(job_id, None)
        self._logs.pop(job_id, None)
        self._running.discard(job_id)
        if job_id in self._order:
            self._order.remove(job_id)
        self.jobsRemoved.emit([job_id])
        self._pump()
        self._emit_stats()

    def clear_finished(self) -> None:
        removed = [i for i, job in self._jobs.items() if job.state.is_terminal]
        for job_id in removed:
            self._jobs.pop(job_id, None)
            self._logs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)
        if removed:
            self.jobsRemoved.emit(removed)
            self._emit_stats()

    def clear_all(self) -> None:
        for job in self._jobs.values():
            job.request_cancel()
        removed = list(self._jobs)
        self._jobs.clear()
        self._logs.clear()
        self._order.clear()
        self._running.clear()
        if removed:
            self.jobsRemoved.emit(removed)
            self._emit_stats()

    def shutdown(self) -> None:
        for job in self._jobs.values():
            job.request_cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._expand_pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------- pump

    def _pump(self) -> None:
        if self._paused:
            return
        limit = max(1, self.settings.behaviour.max_concurrent)

        for job_id in list(self._order):
            if len(self._running) >= limit:
                return
            job = self._jobs.get(job_id)
            if job is None or job.state != JobState.QUEUED:
                continue

            job.clear_cancel()
            job.state = JobState.DOWNLOADING
            self._running.add(job_id)
            self.jobChanged.emit(job_id)
            task = DownloadTask(job, self.settings.behaviour, self._signals)
            self._pool.submit(task.run)

    # ---------------------------------------------------------------- signals

    @staticmethod
    def _apply_fields(job: Job, fields: dict) -> None:
        """Copy an update dict onto a job, restoring the JobState enum.

        These dicts arrive over a queued connection from a worker thread, and
        Qt converts the str-based JobState back into a plain str on the way.
        """
        for key, value in fields.items():
            if key == "state":
                try:
                    value = JobState(value)
                except ValueError:
                    continue
            setattr(job, key, value)

    def _on_updated(self, job_id: int, fields: dict) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        # A pause request can land while an update is already in flight.
        if job.state == JobState.PAUSED and fields.get("state") != JobState.PAUSED:
            return
        self._apply_fields(job, fields)
        self.jobChanged.emit(job_id)

    def _on_finished(self, job_id: int, fields: dict) -> None:
        self._running.discard(job_id)
        job = self._jobs.get(job_id)
        if job is not None:
            paused = job.state == JobState.PAUSED
            self._apply_fields(job, fields)
            if paused and fields.get("state") == JobState.CANCELLED:
                job.state = JobState.PAUSED  # user paused, not cancelled
            job.speed = 0.0
            if job.state == JobState.DONE:
                self._record_history(job)
            self.jobChanged.emit(job_id)
            self.jobFinished.emit(job_id)

        self._pump()
        self._emit_stats()

    def _on_log(self, job_id: int, line: str) -> None:
        bucket = self._logs.get(job_id)
        if bucket is not None:
            bucket.append(line)

    def _emit_stats(self) -> None:
        self.statsChanged.emit(self.stats())

    # ---------------------------------------------------------------- history

    def _record_history(self, job: Job) -> None:
        entry = {
            "title": job.display_title,
            "url": job.url,
            "source": job.source,
            "filepath": job.filepath,
            "bytes": job.total_bytes or job.downloaded_bytes,
            "at": time.time(),
        }
        path = paths.history_file()
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(existing, list):
                existing = []
        except (OSError, ValueError):
            existing = []

        existing.append(entry)
        try:
            path.write_text(
                json.dumps(existing[-MAX_HISTORY:], indent=1), encoding="utf-8"
            )
        except OSError:
            pass
