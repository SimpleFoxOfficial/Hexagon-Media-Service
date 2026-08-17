"""yt-dlp execution: URL expansion and the per-job download worker.

Both are plain callables run on a thread pool, and report progress through the
toolkit-free emitters in `events`. Nothing here knows what the frontend is.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .. import logs, paths
from ..config import Behaviour, Preset
from . import metadata, presets, sources
from .events import Emitter
from .job import Job, JobState

log = logs.get("engine")

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# A signed media URL can expire mid-transfer, which surfaces as a 403 well into
# an otherwise healthy download. Re-extracting gets a fresh URL, and yt-dlp
# resumes from the partial file, so the transfer is not restarted from zero.
_RETRYABLE = ("403", "forbidden", "unable to download video data", "connection reset")
MAX_URL_REFRESH = 2


class Cancelled(Exception):
    """Raised inside a progress hook to abort a download."""


def _clean(message: str) -> str:
    text = _ANSI.sub("", str(message)).strip()
    text = text.replace("ERROR: ", "").replace("\n", " ")
    return re.sub(r"\s+", " ", text)[:400]


class _Logger:
    """Routes yt-dlp's own logging into the job's log signal."""

    def __init__(self, emit):
        self._emit = emit

    def debug(self, msg: str) -> None:
        if not str(msg).startswith("[debug] "):
            self._emit(_clean(msg))

    def info(self, msg: str) -> None:
        self._emit(_clean(msg))

    def warning(self, msg: str) -> None:
        self._emit("Warning: " + _clean(msg))

    def error(self, msg: str) -> None:
        self._emit("Error: " + _clean(msg))


# --------------------------------------------------------------------- signals


class ExpandSignals:
    def __init__(self) -> None:
        self.ready = Emitter("expand.ready")  # list[Job], error message
        self.progress = Emitter("expand.progress")


class DownloadSignals:
    def __init__(self) -> None:
        self.updated = Emitter("job.updated")  # job id, changed fields
        self.finished = Emitter("job.finished")
        self.log = Emitter("job.log")


# ------------------------------------------------------------------- expansion


class ExpandTask:
    """Turn raw user input into concrete jobs.

    Playlists are flattened into one job per entry so each gets its own row and
    its own retry. HDRezka movie pages are resolved to a direct stream here;
    HDRezka series are handled by the picker dialog instead.
    """

    def __init__(self, urls: list[str], behaviour: Behaviour, preset: Preset):
        self.urls = urls
        self.behaviour = behaviour
        self.preset = preset
        self.signals = ExpandSignals()

    def run(self) -> None:  # noqa: C901 - a flat dispatch reads better here
        jobs: list[Job] = []
        problems: list[str] = []

        for url in self.urls:
            url = url.strip()
            if not url:
                continue
            try:
                self.signals.progress.emit(f"Reading {url[:60]}")
                jobs.extend(self._expand_one(url))
            except Exception as exc:
                problems.append(f"{url[:60]}: {_clean(str(exc))}")

        self.signals.ready.emit(jobs, "; ".join(problems))

    def _expand_one(self, url: str) -> list[Job]:
        resolver = sources.resolver_for(url)

        if isinstance(resolver, sources.HdRezkaResolver):
            items = resolver.resolve(url, self.behaviour, self.preset.quality)
            return [self._job_from_item(item, page_url=url) for item in items]

        if not self.behaviour.expand_playlists:
            return [Job(url=url, preset=self.preset, source=sources.pretty_source(url))]

        return self._expand_playlist(url)

    def _expand_playlist(self, url: str) -> list[Job]:
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "socket_timeout": max(5, self.behaviour.socket_timeout),
        }
        if self.behaviour.proxy.strip():
            opts["proxy"] = self.behaviour.proxy.strip()
        if self.behaviour.cookies_from_browser:
            from .cookies import cookie_file

            path, problem = cookie_file(self.behaviour.cookies_from_browser)
            if path is not None:
                opts["cookiefile"] = str(path)
            elif problem:
                log.warning("Continuing without cookies: %s", problem)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)

        if not info:
            raise RuntimeError("nothing found at this URL")

        if info.get("_type") not in ("playlist", "multi_video"):
            return [self._job_from_info(info, fallback_url=url)]

        entries = info.get("entries") or []
        limit = self.behaviour.playlist_limit
        jobs: list[Job] = []
        for index, entry in enumerate(entries):
            if limit and index >= limit:
                break
            if not entry:
                continue
            jobs.append(self._job_from_info(entry, fallback_url=url))

        if not jobs:
            raise RuntimeError("playlist is empty or unavailable")
        return jobs

    def _job_from_info(self, info: dict, fallback_url: str) -> Job:
        url = info.get("url") or info.get("webpage_url") or fallback_url
        if info.get("ie_key") == "Youtube" and not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={info.get('id')}"

        job = Job(url=str(url), preset=self.preset)
        job.title = str(info.get("title") or "")
        job.uploader = str(info.get("uploader") or info.get("channel") or "")
        job.duration = float(info.get("duration") or 0)
        job.source = sources.pretty_source(str(url))
        thumbs = info.get("thumbnails") or []
        if thumbs:
            job.thumbnail_url = str(thumbs[-1].get("url", ""))
        elif info.get("thumbnail"):
            job.thumbnail_url = str(info["thumbnail"])
        return job

    def _job_from_item(self, item: sources.ResolvedItem, page_url: str) -> Job:
        job = Job(url=item.url, preset=self.preset)
        job.title = item.title
        job.source = item.source or sources.pretty_source(page_url)
        job.thumbnail_url = item.thumbnail
        job.extra_opts = dict(item.extra_opts)
        job.forced_metadata = dict(item.metadata)
        if item.filename_stem:
            job.extra_opts["_filename_stem"] = item.filename_stem
        return job


def job_from_resolved(item: sources.ResolvedItem, preset: Preset) -> Job:
    """Build a job from a resolver result (used by the HDRezka picker)."""
    job = Job(url=item.url, preset=preset)
    job.title = item.title
    job.source = item.source
    job.thumbnail_url = item.thumbnail
    job.extra_opts = dict(item.extra_opts)
    job.forced_metadata = dict(item.metadata)
    if item.filename_stem:
        job.extra_opts["_filename_stem"] = item.filename_stem
    return job


# -------------------------------------------------------------------- download


class DownloadTask:
    """Download one job and post-process it."""

    EMIT_INTERVAL = 0.12

    def __init__(self, job: Job, behaviour: Behaviour, signals: DownloadSignals):
        self.job = job
        self.behaviour = behaviour
        self.signals = signals
        self._last_emit = 0.0

    # ------------------------------------------------------------------ hooks

    def _log(self, message: str) -> None:
        if message:
            self.signals.log.emit(self.job.id, message)

    def _emit(self, fields: dict, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < self.EMIT_INTERVAL:
            return
        self._last_emit = now
        self.signals.updated.emit(self.job.id, fields)

    def _progress_hook(self, data: dict) -> None:
        if self.job.cancel_requested:
            raise Cancelled()

        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            fragment = ""
            index, count = data.get("fragment_index"), data.get("fragment_count")
            if index and count:
                fragment = f"segment {index}/{count}"

            self._emit(
                {
                    "state": JobState.DOWNLOADING,
                    "progress": (done / total * 100.0) if total else 0.0,
                    "speed": float(data.get("speed") or 0.0),
                    "eta": int(data.get("eta") or 0),
                    "downloaded_bytes": int(done),
                    "total_bytes": int(total),
                    "fragment_text": fragment,
                }
            )
        elif status == "finished":
            self._emit(
                {"state": JobState.PROCESSING, "progress": 100.0, "speed": 0.0, "eta": 0},
                force=True,
            )

    def _postprocessor_hook(self, data: dict) -> None:
        if self.job.cancel_requested:
            raise Cancelled()
        if data.get("status") == "started":
            name = str(data.get("postprocessor", "")).replace("FFmpeg", "")
            self._emit(
                {"state": JobState.PROCESSING, "fragment_text": _pp_label(name)}, force=True
            )

    # -------------------------------------------------------------------- run

    def run(self) -> None:
        """Run the job, and report a finish no matter how it ends.

        Nothing reads the Future this is submitted to, so an exception escaping
        here is swallowed by the pool and simply never heard from again. The
        manager would then keep the job in its running set for ever: the queue
        quietly loses a concurrency slot each time it happens, and after a few
        it stops starting anything at all. Every exit path must emit.
        """
        try:
            self._run()
        except Exception as exc:
            logs.exception(log, f"Job {self.job.id} crashed", exc, job_id=self.job.id)
            self.signals.finished.emit(
                self.job.id,
                {
                    "state": JobState.FAILED,
                    "error": _explain(_clean(str(exc))),
                    "speed": 0.0,
                    "fragment_text": "",
                },
            )

    def _run(self) -> None:
        import yt_dlp

        job = self.job
        job.clear_cancel()
        self._emit({"state": JobState.DOWNLOADING, "error": ""}, force=True)
        log.info("Job %s starting: %s", job.id, job.url, extra={"job_id": job.id})

        info = None
        last_error = ""
        for attempt in range(MAX_URL_REFRESH + 1):
            try:
                info = self._download(yt_dlp)
                break
            except Cancelled:
                log.info("Job %s cancelled", job.id, extra={"job_id": job.id})
                self.signals.finished.emit(
                    job.id, {"state": JobState.CANCELLED, "speed": 0.0, "eta": 0}
                )
                return
            except Exception as exc:
                last_error = _clean(str(exc))
                retryable = any(token in last_error.lower() for token in _RETRYABLE)

                if retryable and attempt < MAX_URL_REFRESH and not job.cancel_requested:
                    log.warning(
                        "Job %s hit a recoverable error (attempt %d/%d): %s",
                        job.id,
                        attempt + 1,
                        MAX_URL_REFRESH + 1,
                        last_error,
                        extra={"job_id": job.id},
                    )
                    self._log(f"Retrying with a fresh URL: {last_error}")
                    self._emit(
                        {"fragment_text": f"retrying ({attempt + 1})"}, force=True
                    )
                    time.sleep(2.0 * (attempt + 1))
                    continue

                logs.exception(log, f"Job {job.id} failed", exc, job_id=job.id)
                self.signals.finished.emit(
                    job.id,
                    {
                        "state": JobState.FAILED,
                        "error": _explain(last_error),
                        "speed": 0.0,
                        "fragment_text": "",
                    },
                )
                return

        if info is None:
            # yt-dlp returns nothing when the archive says it is already done.
            self.signals.finished.emit(job.id, {"state": JobState.SKIPPED, "progress": 100.0})
            return

        filepath = _final_path(info)
        if filepath:
            # Tagging is a finishing touch, not the download. The file is
            # already on disk and complete, so a mutagen failure on an unusual
            # container is worth a warning and nothing more - reporting the
            # whole job as failed would be a lie about a file the user has.
            try:
                metadata.apply(
                    filepath,
                    source_url=job.forced_metadata.get("comment") or job.url,
                    extra=job.forced_metadata,
                )
            except Exception as exc:
                log.warning(
                    "Job %s downloaded but could not be tagged: %s",
                    job.id,
                    exc,
                    extra={"job_id": job.id},
                )
                self._log(f"Downloaded, but tagging failed: {_clean(str(exc))}")

        self.signals.finished.emit(
            job.id,
            {
                "state": JobState.DONE,
                "progress": 100.0,
                "speed": 0.0,
                "eta": 0,
                "fragment_text": "",
                "filepath": filepath,
                "title": job.title or str(info.get("title") or ""),
                "finished_at": time.time(),
            },
        )

    def _download(self, yt_dlp):
        job = self.job
        ffmpeg = paths.find_ffmpeg(self.behaviour.ffmpeg_path)

        extra = {k: v for k, v in job.extra_opts.items() if not k.startswith("_")}
        opts = presets.build_opts(
            self.behaviour,
            job.preset,
            ffmpeg=ffmpeg,
            source=job.source,
            extra=extra,
        )

        # An episode knows its show, season and number, so it can be filed into
        # Show/Season NN/ instead of landing flat with everything else.
        show = job.extra_opts.get("_show")
        season = job.extra_opts.get("_season")
        episode = job.extra_opts.get("_episode")
        stem = job.extra_opts.get("_filename_stem")

        if show and season is not None and episode is not None:
            opts["outtmpl"] = {
                "default": presets.output_template_for_episode(
                    self.behaviour, job.preset, str(show), int(season), int(episode), job.source
                )
            }
        elif stem:
            opts["outtmpl"] = {
                "default": presets.output_template_for_stem(
                    self.behaviour, job.preset, stem, job.source
                )
            }

        problem = opts.pop("_cookie_problem", "")
        if problem:
            log.warning("Job %s: %s", job.id, problem, extra={"job_id": job.id})
            self._log(problem)

        opts["progress_hooks"] = [self._progress_hook]
        opts["postprocessor_hooks"] = [self._postprocessor_hook]
        opts["logger"] = _Logger(self._log)

        target = Path(opts["outtmpl"]["default"]).parent
        target.mkdir(parents=True, exist_ok=True)

        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(job.url, download=True)


def _explain(message: str) -> str:
    """Turn a raw yt-dlp error into something that says what to do about it."""
    lowered = message.lower()

    if "403" in lowered or "forbidden" in lowered:
        return (
            f"{message} - the media URL expired or the site refused the transfer. "
            "Retry; if it keeps happening, update yt-dlp or set cookies in Settings."
        )
    if "requested format is not available" in lowered:
        return (
            f"{message} - usually an outdated yt-dlp. Update it, or pick "
            "Best available quality."
        )
    if "sign in" in lowered or "age" in lowered and "restrict" in lowered:
        return f"{message} - set Settings > Network > Use cookies from to your browser."
    if "ffmpeg" in lowered:
        return f"{message} - check the ffmpeg location in Settings > Advanced."
    if "unavailable" in lowered or "private" in lowered or "removed" in lowered:
        return f"{message} - the item is not downloadable any more."
    return message


def _pp_label(name: str) -> str:
    return {
        "ExtractAudio": "converting audio",
        "VideoRemuxer": "remuxing",
        "VideoConvertor": "converting video",
        "Metadata": "writing tags",
        "EmbedSubtitle": "embedding subtitles",
        "EmbedThumbnail": "embedding artwork",
        "Merger": "merging streams",
        "ModifyChapters": "trimming chapters",
        "SponsorBlock": "checking segments",
    }.get(name, "processing")


def _final_path(info: dict) -> str:
    """The path on disk after post-processing, not the intermediate download."""
    if not isinstance(info, dict):
        return ""

    if info.get("_type") in ("playlist", "multi_video"):
        for entry in info.get("entries") or []:
            found = _final_path(entry or {})
            if found:
                return found
        return ""

    downloads = info.get("requested_downloads") or []
    for item in downloads:
        path = item.get("filepath") or item.get("_filename")
        if path and Path(path).exists():
            return str(path)

    path = info.get("filepath") or info.get("_filename") or ""
    return str(path) if path and Path(path).exists() else ""
