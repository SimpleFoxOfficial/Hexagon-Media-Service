"""Headless download engine, driven over stdio.

The Electron shell spawns this and talks newline-delimited JSON in both
directions. Requests carry an `id` and get exactly one `result` or `error`
back; events are unsolicited messages with no `id`.

    -> {"id": 1, "method": "queue.add", "params": {"urls": ["https://..."]}}
    <- {"id": 1, "result": {"accepted": 1}}
    <- {"event": "job.changed", "data": {...}}

stdout carries protocol only. Anything printed by a library would corrupt the
stream, so stdout is swapped for stderr as soon as this module takes over.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import traceback
from dataclasses import asdict

from . import __version__, logs, paths
from .config import Preset, Settings
from .core import presets
from .core.job import Job, JobState
from .core.manager import DownloadManager
from .core.sources import EpisodeRef, hdrezka, pretty_source

log = logs.get("daemon")

PROTOCOL_VERSION = 1


def job_payload(job: Job) -> dict:
    """The wire shape of a job. Kept flat so the renderer can use it directly."""
    return {
        "id": job.id,
        "url": job.url,
        "title": job.display_title,
        "uploader": job.uploader,
        "source": job.source,
        "thumbnail": job.thumbnail_url,
        "state": job.state.value,
        "stateLabel": job.state.label,
        "progress": round(float(job.progress), 2),
        "speed": float(job.speed),
        "eta": int(job.eta),
        "downloadedBytes": int(job.downloaded_bytes),
        "totalBytes": int(job.total_bytes),
        "sizeText": job.size_text,
        "speedText": job.speed_text,
        "etaText": job.eta_text,
        "note": job.fragment_text,
        "filepath": job.filepath,
        "error": job.error,
        "isTerminal": job.state.is_terminal,
        "isActive": job.state.is_active,
    }


class Daemon:
    def __init__(self) -> None:
        self.settings = Settings.load()
        logs.setup(self.settings.behaviour.verbose_logging)

        self.manager = DownloadManager(self.settings)
        self._out: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()

        self._wire_events()

        self._methods = {
            "app.info": self._app_info,
            "app.ping": lambda _p: {"pong": True},
            "settings.get": self._settings_get,
            "settings.patch": self._settings_patch,
            "queue.add": self._queue_add,
            "queue.list": lambda _p: {"jobs": [job_payload(j) for j in self.manager.jobs]},
            "queue.stats": lambda _p: self._stats(),
            "queue.pause": self._job_action(self.manager.pause),
            "queue.resume": self._job_action(self.manager.resume),
            "queue.retry": self._job_action(self.manager.retry),
            "queue.cancel": self._job_action(self.manager.cancel),
            "queue.remove": self._job_action(self.manager.remove),
            "queue.pauseAll": lambda _p: (self.manager.pause_all(), {"ok": True})[1],
            "queue.startAll": lambda _p: (self.manager.start_all(), {"ok": True})[1],
            "queue.clearFinished": lambda _p: (
                self.manager.clear_finished(),
                {"ok": True},
            )[1],
            "queue.logs": lambda p: {"lines": self.manager.logs(int(p.get("id", 0)))},
            "logs.tail": self._logs_tail,
            "rezka.probe": self._rezka_probe,
            "rezka.resolve": self._rezka_resolve,
            "rezka.queueCaptured": self._rezka_queue_captured,
            "bridge.info": lambda _p: self.bridge.info(),
            "bridge.describe": lambda _p: self._enqueue({"type": "describe"}),
            "bridge.episodes": lambda p: self._enqueue(
                {"type": "episodes", "translatorId": str(p.get("translatorId", ""))}
            ),
            "bridge.download": self._bridge_download,
            "bridge.estimate": self._bridge_estimate,
            "bridge.downloads": lambda _p: {
                "items": list(self._browser_downloads.values())
            },
            "paths.target": self._paths_target,
        }

        from .bridge_server import BridgeServer

        # The app is the single place anything is configured; the extension
        # pulls its settings from here rather than keeping its own copy.
        self.bridge = BridgeServer(
            self._on_capture,
            handlers={
                "/settings": self._bridge_settings,
                "/progress": self._bridge_progress,
                "/complete": self._bridge_complete,
                "/commands": self._bridge_commands,
                "/result": self._bridge_result,
            },
        )
        self.bridge.start()

        # Work queued for the extension. The app holds the UI, the extension
        # holds the browser session, so commands travel app -> extension and
        # results come back the other way.
        self._commands: list[dict] = []
        self._results: dict[int, dict] = {}
        self._command_seq = 0
        self._command_lock = threading.Lock()
        self._browser_downloads: dict[str, dict] = {}
        #: staging names already moved to their destination, so a batch can
        #: tell when it is safe to start the next one
        self._filed: set[str] = set()

    # ------------------------------------------------------------------ wiring

    def _wire_events(self) -> None:
        m = self.manager
        m.jobsAdded.connect(
            lambda ids: self._event(
                "job.added",
                {"jobs": [job_payload(j) for i in ids if (j := m.job(i))]},
            )
        )
        m.jobChanged.connect(
            lambda i: (j := m.job(i)) and self._event("job.changed", job_payload(j))
        )
        m.jobsRemoved.connect(lambda ids: self._event("job.removed", {"ids": list(ids)}))
        m.statsChanged.connect(lambda _s: self._event("queue.stats", self._stats()))
        m.expandStarted.connect(lambda: self._event("expand.started", {}))
        m.expandFinished.connect(lambda err: self._event("expand.finished", {"error": err}))
        m.busyMessage.connect(lambda text: self._event("busy", {"text": text}))

    def _stats(self) -> dict:
        raw = self.manager.stats()
        return {
            "total": raw["total"],
            "queued": raw["queued"],
            "active": raw["active"],
            "done": raw["done"],
            "failed": raw["failed"],
            "paused": raw["paused"],
            "speed": raw["speed"],
            "isPaused": self.manager.is_paused,
        }

    # ------------------------------------------------------------------ methods

    def _app_info(self, _params: dict) -> dict:
        return {
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
            "components": dict(logs.describe_environment()),
            "paths": {
                "config": str(paths.config_dir()),
                "log": str(paths.log_file()),
                "downloads": str(self.settings.behaviour.resolved_download_dir()),
            },
        }

    def _settings_get(self, _params: dict) -> dict:
        return {
            "appearance": asdict(self.settings.appearance),
            "behaviour": asdict(self.settings.behaviour),
            "preset": asdict(self.settings.preset),
            "rezka": asdict(self.settings.rezka),
            "activeService": self.settings.active_service,
        }

    def _settings_patch(self, params: dict) -> dict:
        """Apply a partial settings update. Unknown keys are ignored."""
        for section in ("appearance", "behaviour", "preset", "rezka"):
            values = params.get(section)
            if not isinstance(values, dict):
                continue
            target = getattr(self.settings, section)
            for key, value in values.items():
                if not hasattr(target, key):
                    continue
                current = getattr(target, key)
                if isinstance(current, bool) and not isinstance(value, bool):
                    continue
                if isinstance(current, int) and not isinstance(current, bool):
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        continue
                    value = int(value)
                setattr(target, key, value)

        if isinstance(params.get("activeService"), str):
            self.settings.active_service = params["activeService"]

        self.settings.save()
        return self._settings_get({})

    def _queue_add(self, params: dict) -> dict:
        urls = [str(u).strip() for u in (params.get("urls") or []) if str(u).strip()]
        if not urls:
            return {"accepted": 0}
        preset = self.settings.preset
        if isinstance(params.get("preset"), dict):
            preset = Preset(**{**asdict(self.settings.preset), **params["preset"]})
        self.manager.add_urls(urls, preset)
        return {"accepted": len(urls)}

    def _job_action(self, fn):
        def handler(params: dict) -> dict:
            job_id = int(params.get("id", 0))
            fn(job_id)
            return {"ok": True, "id": job_id}

        return handler

    def _logs_tail(self, params: dict) -> dict:
        level = str(params.get("level", "") or "")
        limit = int(params.get("limit", 500))
        lines = logs.ring().lines(level=level)
        return {"lines": lines[-limit:]}

    def _paths_target(self, _params: dict) -> dict:
        return {
            "dir": str(presets.target_dir(self.settings.behaviour, self.settings.preset)),
            "describe": presets.describe(self.settings.preset),
        }

    # -------------------------------------------------------------- hdrezka

    def _rezka_probe(self, params: dict) -> dict:
        url = str(params.get("url", "")).strip()
        info = hdrezka().probe(url, self.settings.behaviour, self.settings.rezka)
        return {
            "url": info.url,
            "name": info.name,
            "isSeries": info.is_series,
            "thumbnail": info.thumbnail,
            "translators": info.translators,
            "seasons": {
                tid: {str(season): eps for season, eps in seasons.items()}
                for tid, seasons in info.seasons.items()
            },
            "defaultTranslator": info.default_translator,
            "error": info.error,
            "blocked": info.blocked,
        }

    def _rezka_resolve(self, params: dict) -> dict:
        from .core.engine import job_from_resolved

        url = str(params.get("url", "")).strip()
        quality = str(params.get("quality") or self.settings.rezka.quality)
        raw_episodes = params.get("episodes") or []

        if not raw_episodes:
            items = hdrezka().resolve(
                url, self.settings.behaviour, quality, self.settings.rezka
            )
            problems: list[str] = []
        else:
            refs = [
                EpisodeRef(
                    season=int(e["season"]),
                    episode=int(e["episode"]),
                    translator_id=e.get("translator"),
                )
                for e in raw_episodes
            ]
            items, problems = hdrezka().resolve_episodes(
                url,
                self.settings.behaviour,
                refs,
                quality,
                self.settings.rezka,
                progress=lambda i, n, tag: self._event(
                    "rezka.progress", {"index": i, "total": n, "tag": tag}
                ),
            )

        jobs = [job_from_resolved(item, self.settings.preset) for item in items]
        self.manager.add_jobs(jobs)
        return {"queued": len(jobs), "problems": problems}

    # -------------------------------------------------- extension downloads

    def _bridge_settings(self, _payload: dict) -> dict:
        """What the extension needs to name and fetch files our way."""
        rezka, behaviour = self.settings.rezka, self.settings.behaviour
        return {
            "quality": rezka.quality,
            "subtitles": rezka.subtitles,
            "tagQuality": False,
            "overwrite": False,
            "seasonFolders": behaviour.tv_folders,
            "destination": str(
                presets.target_dir(behaviour, self.settings.preset, "HDRezka")
            ),
        }

    def _items_from(self, params: dict) -> list[dict]:
        from .core import text as textutil

        items = []
        for raw in params.get("items") or []:
            items.append(
                {
                    "translatorId": str(raw.get("translatorId") or ""),
                    "season": int(raw.get("season") or 0),
                    "episode": int(raw.get("episode") or 0),
                    # Names reach us mis-decoded often enough that repairing at
                    # the boundary is cheaper than chasing every source.
                    "show": textutil.clean_title(raw.get("show") or ""),
                    "dub": textutil.english_label(raw.get("dub") or ""),
                    "pageUrl": str(raw.get("pageUrl") or ""),
                }
            )
        return items

    def _bridge_estimate(self, params: dict) -> dict:
        """Rough total size for a selection, and whether it fits.

        One episode is measured and multiplied by the count. Episodes of a
        series are close enough in size for this to be useful, and measuring
        every one would mean a request per episode before anything starts.
        """
        from .core import filing

        items = self._items_from(params)
        if not items:
            return {"count": 0, "bytes": 0}

        per_item = int(params.get("perItem") or 0)
        if not per_item:
            try:
                probe = self._enqueue(
                    {"type": "measure", "item": items[0],
                     "quality": str(params.get("quality") or self.settings.rezka.quality)},
                    timeout=60.0,
                )
                per_item = int(probe.get("bytes") or 0)
            except Exception as exc:
                log.warning("Could not measure a sample episode: %s", exc)
                per_item = 0

        total = per_item * len(items)
        staging = filing.free_space(paths.default_download_dir())
        destination = filing.free_space(
            presets.target_dir(self.settings.behaviour, self.settings.preset, "HDRezka")
        )

        # Keep a margin so the drive is never filled to the last byte.
        usable = max(0, int(staging * 0.9))
        batch = len(items)
        if per_item and total > usable:
            batch = max(1, usable // per_item)

        return {
            "count": len(items),
            "perItem": per_item,
            "bytes": total,
            "text": filing.human_size(total) if total else "unknown",
            "freeStaging": staging,
            "freeDestination": destination,
            "fits": bool(per_item) and total <= usable,
            "batchSize": batch,
            "batches": (len(items) + batch - 1) // batch if batch else 1,
        }

    def _bridge_download(self, params: dict) -> dict:
        """Season and episode choices made in the app, executed in the browser.

        Runs on a worker thread and in batches: the browser stages files in the
        Downloads folder, so a whole season could fill that drive before
        anything is moved off it. Each batch waits for its files to be filed
        before the next starts.
        """
        items = self._items_from(params)
        if not items:
            return {"started": 0, "failed": ["nothing selected"]}

        settings = self._bridge_settings({})
        if params.get("quality"):
            settings["quality"] = str(params["quality"])
        if params.get("show"):
            settings["show"] = str(params["show"])

        batch_size = int(params.get("batchSize") or 0) or len(items)
        batch_size = max(1, min(batch_size, len(items)))

        threading.Thread(
            target=self._run_batches,
            args=(items, settings, batch_size),
            name="mediadl-batches",
            daemon=True,
        ).start()

        return {
            "accepted": len(items),
            "batchSize": batch_size,
            "batches": (len(items) + batch_size - 1) // batch_size,
        }

    def _run_batches(self, items: list, settings: dict, batch_size: int) -> None:
        chunks = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
        log.info("Downloading %d item(s) in %d batch(es)", len(items), len(chunks))

        for index, chunk in enumerate(chunks, start=1):
            self._event(
                "rezka.batch",
                {"batch": index, "batches": len(chunks), "size": len(chunk), "stage": "starting"},
            )
            try:
                result = self._enqueue(
                    {"type": "download", "items": chunk, "settings": settings},
                    timeout=300.0,
                )
            except Exception as exc:
                log.error("Batch %d failed: %s", index, exc)
                self._event(
                    "rezka.batch",
                    {"batch": index, "batches": len(chunks), "stage": "failed", "error": str(exc)},
                )
                return

            self._event(
                "rezka.batch",
                {
                    "batch": index,
                    "batches": len(chunks),
                    "stage": "downloading",
                    "started": result.get("started", 0),
                    "handedToApp": result.get("handedToApp", 0),
                    "failed": result.get("failed", []),
                },
            )

            if index < len(chunks):
                self._wait_for_batch(result.get("started", 0), index, len(chunks))

        self._event("rezka.batch", {"batches": len(chunks), "stage": "done"})

    def _wait_for_batch(self, expected: int, index: int, total: int) -> None:
        """Hold the next batch until this one has been moved off the staging drive."""
        if expected <= 0:
            return

        deadline = time.time() + 3600
        with self._command_lock:
            baseline = len(self._filed)

        while time.time() < deadline:
            with self._command_lock:
                done = len(self._filed) - baseline
            if done >= expected:
                log.info("Batch %d/%d filed; continuing", index, total)
                return
            self._event(
                "rezka.batch",
                {"batch": index, "batches": total, "stage": "waiting",
                 "filed": done, "expected": expected},
            )
            time.sleep(2.0)

        log.warning("Batch %d timed out waiting to be filed; continuing anyway", index)

    def _bridge_commands(self, _payload: dict) -> dict:
        """Hand the extension whatever the app has queued for it."""
        with self._command_lock:
            pending, self._commands = self._commands, []
        return {"commands": pending}

    def _bridge_result(self, payload: dict) -> dict:
        with self._command_lock:
            self._results[int(payload.get("id", 0))] = payload
        return {"ok": True}

    def _enqueue(self, command: dict, timeout: float = 90.0) -> dict:
        """Queue a command and wait for the extension to answer it."""
        with self._command_lock:
            self._command_seq += 1
            command_id = self._command_seq
            command["id"] = command_id
            self._commands.append(command)

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._command_lock:
                result = self._results.pop(command_id, None)
            if result is not None:
                if not result.get("ok"):
                    raise RuntimeError(result.get("error") or "the extension reported a failure")
                return result.get("result") or {}
            time.sleep(0.2)

        raise RuntimeError(
            "The browser extension did not answer. Check it is installed, paired, "
            "and that a HDRezka tab is open."
        )

    def _bridge_progress(self, payload: dict) -> dict:
        event = str(payload.get("event", ""))
        key = str(payload.get("filename") or payload.get("path") or "")

        if event == "failed":
            log.warning(
                "Browser download failed: %s (%s)", key, payload.get("error")
            )
            self._browser_downloads.pop(key, None)
        elif event == "progress":
            received = int(payload.get("received") or 0)
            total = int(payload.get("total") or 0)
            payload["percent"] = round(received / total * 100, 1) if total else 0.0
            self._browser_downloads[key] = payload
        else:
            log.info("Browser download started: %s", key)
            self._browser_downloads[key] = payload

        self._event("rezka.browserProgress", payload)
        return {"ok": True}

    def _bridge_complete(self, payload: dict) -> dict:
        """Accept a finished browser download and file it on a worker thread.

        Chrome reports completion before it has released the file, and the move
        is usually cross-volume and therefore slow, so this returns straight
        away and the real work reports progress through events.
        """
        key = str(payload.get("filename") or payload.get("path") or "")
        threading.Thread(
            target=self._file_download, args=(payload,), name="mediadl-filing", daemon=True
        ).start()
        return {"accepted": True, "filename": key}

    def _file_download(self, payload: dict) -> None:
        from pathlib import Path

        from .core import filing, metadata

        from .core import text as textutil

        key = str(payload.get("filename") or payload.get("path") or "")
        source = Path(str(payload.get("path") or ""))
        show = textutil.clean_title(payload.get("show") or "") or "HDRezka"
        season = int(payload.get("season") or 0)
        episode = int(payload.get("episode") or 0)
        dub = textutil.english_label(payload.get("dub") or "")
        expected = int(payload.get("bytes") or 0)

        def emit(stage, **extra):
            self._event(
                "rezka.filing",
                {
                    "filename": key,
                    "show": show,
                    "season": season,
                    "episode": episode,
                    "stage": stage,
                    **extra,
                },
            )

        emit("waiting")
        ok, reason = filing.wait_until_stable(source, expected)
        if not ok:
            log.error("Not filing %s: %s", source, reason)
            emit("failed", error=reason)
            self._event("rezka.filed", {"ok": False, "error": reason, "filename": key})
            return

        if season > 0 and episode > 0:
            folder, stem = presets.episode_paths(
                self.settings.behaviour,
                self.settings.preset,
                show,
                season,
                episode,
                "HDRezka",
                dub,
            )
        else:
            folder = presets.target_dir(
                self.settings.behaviour, self.settings.preset, "HDRezka"
            )
            stem = presets._safe_file(show)

        target = folder / f"{stem}{source.suffix}"
        last = [0.0]

        def on_progress(copied, total):
            percent = round(copied / total * 100, 1) if total else 0.0
            # Throttle: a multi-gigabyte copy would otherwise flood the pipe.
            if percent - last[0] >= 1.0 or percent >= 100.0:
                last[0] = percent
                emit("moving", percent=percent, copied=copied, total=total)

        try:
            final = filing.move_file(source, target, on_progress, expected)
        except OSError as exc:
            logs.exception(log, f"Could not file {source}", exc)
            emit("failed", error=str(exc))
            self._event("rezka.filed", {"ok": False, "error": str(exc), "filename": key})
            return

        emit("tagging")
        extra = {"title": f"{show} {season}x{episode:02d}" if season else show}
        if season:
            extra.update({"album": show, "season_number": season, "episode_number": episode})
        metadata.apply(final, source_url=str(payload.get("pageUrl") or ""), extra=extra)

        with self._command_lock:
            self._filed.add(key)
        emit("done", path=str(final))
        self._event(
            "rezka.filed",
            {"ok": True, "path": str(final), "show": show, "filename": key},
        )

    # -------------------------------------------------------------- capture

    def _on_capture(self, payload: dict) -> dict:
        """Called on a bridge thread when the extension sends a page's data.

        The extension has already done the part Python cannot: it read the
        resolved stream URLs out of the live page inside the user's browser.
        """
        title = str(payload.get("title") or "HDRezka")
        items = payload.get("items") or []
        capture = {
            "title": title,
            "pageUrl": str(payload.get("pageUrl") or ""),
            "isSeries": bool(payload.get("isSeries")),
            "episodes": [
                {
                    "season": int(it.get("season") or 0),
                    "episode": int(it.get("episode") or 0),
                    "url": str(it.get("url") or ""),
                    "quality": str(it.get("quality") or ""),
                    "translator": str(it.get("translator") or ""),
                }
                for it in items
                if it.get("url")
            ],
        }
        log.info("Captured %r from the browser: %d item(s)", title, len(capture["episodes"]))
        self._event("rezka.captured", capture)

        if payload.get("queue"):
            return self._rezka_queue_captured({"capture": capture})
        return {"received": len(capture["episodes"])}

    def _rezka_queue_captured(self, params: dict) -> dict:
        """Turn captured stream URLs into queued jobs."""
        from .core.engine import job_from_resolved
        from .core.sources import ResolvedItem
        from .core.sources.hdrezka import USER_AGENT

        capture = params.get("capture") or {}
        show = str(capture.get("title") or "HDRezka")
        page_url = str(capture.get("pageUrl") or "")
        jobs = []

        for item in capture.get("episodes") or []:
            season, episode = int(item.get("season") or 0), int(item.get("episode") or 0)
            is_episode = season > 0 and episode > 0
            tag = f"S{season:02d}E{episode:02d}" if is_episode else ""
            title = f"{show} {tag}".strip()

            resolved = ResolvedItem(
                url=str(item["url"]),
                title=title,
                source="HDRezka",
                filename_stem=f"{show} - {tag}" if is_episode else show,
                extra_opts={
                    "http_headers": {"User-Agent": USER_AGENT, "Referer": page_url or item["url"]}
                },
                metadata={"title": title, "comment": page_url},
            )
            if is_episode:
                resolved.extra_opts.update(
                    {"_show": show, "_season": season, "_episode": episode}
                )
                resolved.metadata.update(
                    {"album": show, "season_number": season, "episode_number": episode}
                )
            jobs.append(job_from_resolved(resolved, self.settings.preset))

        self.manager.add_jobs(jobs)
        return {"queued": len(jobs)}

    # ------------------------------------------------------------------- io

    def _event(self, name: str, data: dict) -> None:
        self._out.put(json.dumps({"event": name, "data": data}, default=str))

    def _reply(self, message: dict) -> None:
        self._out.put(json.dumps(message, default=str))

    def _writer(self, stream) -> None:
        while not self._stop.is_set():
            try:
                line = self._out.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                stream.write(line + "\n")
                stream.flush()
            except (BrokenPipeError, ValueError):
                self._stop.set()
                return

    def handle(self, message: dict) -> None:
        request_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params") or {}

        handler = self._methods.get(method)
        if handler is None:
            self._reply({"id": request_id, "error": f"unknown method {method!r}"})
            return

        try:
            result = handler(params)
        except Exception as exc:
            logs.exception(log, f"method {method} failed", exc)
            self._reply(
                {
                    "id": request_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=6),
                }
            )
            return

        if request_id is not None:
            self._reply({"id": request_id, "result": result})

    def run(self) -> int:
        # Protocol owns stdout; everything else is redirected so a stray print
        # from a dependency cannot corrupt the stream.
        protocol_out = sys.stdout
        sys.stdout = sys.stderr

        writer = threading.Thread(target=self._writer, args=(protocol_out,), daemon=True)
        writer.start()

        self._event("ready", self._app_info({}))
        log.info("Daemon ready (protocol %d)", PROTOCOL_VERSION)

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except ValueError:
                    self._reply({"id": None, "error": "malformed JSON"})
                    continue
                if message.get("method") == "app.shutdown":
                    break
                self.handle(message)
        except KeyboardInterrupt:
            pass
        finally:
            log.info("Daemon shutting down")
            self.manager.shutdown()
            self.settings.save()
            self._stop.set()
            writer.join(timeout=2.0)

        return 0


def main() -> int:
    return Daemon().run()


if __name__ == "__main__":
    raise SystemExit(main())
