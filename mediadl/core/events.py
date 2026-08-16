"""A tiny synchronous event emitter.

The core used to lean on Qt signals, which tied the download engine to a GUI
toolkit and to Qt's thread affinity. It is now toolkit-free: emitters call their
subscribers directly, on whichever thread emitted.

That means subscribers are responsible for getting work onto the thread they
need. The daemon pushes onto a queue drained by its writer thread; a GUI would
marshal to its own loop. Nothing here touches widgets, so nothing here can
violate a toolkit's threading rules.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


class Emitter:
    """Keeps `.connect()` / `.emit()` so call sites read the same as before."""

    __slots__ = ("_subscribers", "_lock", "name")

    def __init__(self, name: str = ""):
        self.name = name
        self._subscribers: list[Callable[..., Any]] = []
        self._lock = threading.Lock()

    def connect(self, callback: Callable[..., Any]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, *args: Any) -> None:
        with self._lock:
            targets = list(self._subscribers)
        for callback in targets:
            try:
                callback(*args)
            except Exception:
                # A broken subscriber must never abort a download.
                import logging

                logging.getLogger("mediadl.events").exception(
                    "subscriber for %r failed", self.name or "event"
                )

    def __bool__(self) -> bool:
        return bool(self._subscribers)
