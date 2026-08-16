"""The queue screen: one card per job, plus batch controls."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.job import Job, JobState, human_size
from ...core.manager import DownloadManager
from .. import icons, theme
from ..widgets import (
    Card,
    Thumbnail,
    badge,
    button,
    label,
    set_prop,
    tool_button,
)

_BADGE_KIND = {
    JobState.QUEUED: "neutral",
    JobState.RESOLVING: "accent",
    JobState.DOWNLOADING: "accent",
    JobState.PROCESSING: "accent",
    JobState.DONE: "success",
    JobState.SKIPPED: "success",
    JobState.FAILED: "error",
    JobState.CANCELLED: "neutral",
    JobState.PAUSED: "neutral",
}

_CARD_STATE = {
    JobState.DOWNLOADING: "running",
    JobState.PROCESSING: "running",
    JobState.RESOLVING: "running",
    JobState.DONE: "done",
    JobState.SKIPPED: "done",
    JobState.FAILED: "error",
}


class JobCard(Card):
    """A single queue row."""

    action = Signal(str, int)  # verb, job id

    def __init__(self, job: Job, show_thumbnail: bool, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setObjectName("JobCard")
        self.job_id = job.id
        self._show_thumbnail = show_thumbnail

        body = self.body()
        body.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)

        self.thumb = Thumbnail()
        self.thumb.setVisible(show_thumbnail)
        top.addWidget(self.thumb, 0, Qt.AlignTop)

        text_column = QVBoxLayout()
        text_column.setSpacing(3)

        self.title = label("", "title")
        self.title.setWordWrap(False)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text_column.addWidget(self.title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        self.state_badge = badge("", "neutral")
        meta_row.addWidget(self.state_badge)
        self.source_badge = badge("", "neutral")
        meta_row.addWidget(self.source_badge)
        self.meta = label("", "caption")
        meta_row.addWidget(self.meta, 1)
        text_column.addLayout(meta_row)

        top.addLayout(text_column, 1)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(2)
        top.addLayout(self.buttons, 0)

        body.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        body.addWidget(self.progress)

        self.error = label("", "caption")
        self.error.setProperty("role", "caption")
        self.error.setVisible(False)
        body.addWidget(self.error)

        self._make_buttons()
        self.update_from(job)

    def _make_buttons(self) -> None:
        self._btn_pause = tool_button("pause", "Pause")
        self._btn_pause.clicked.connect(lambda: self.action.emit("pause", self.job_id))

        self._btn_resume = tool_button("play", "Resume")
        self._btn_resume.clicked.connect(lambda: self.action.emit("resume", self.job_id))

        self._btn_retry = tool_button("retry", "Retry")
        self._btn_retry.clicked.connect(lambda: self.action.emit("retry", self.job_id))

        self._btn_folder = tool_button("folder", "Show in folder")
        self._btn_folder.clicked.connect(lambda: self.action.emit("reveal", self.job_id))

        self._btn_more = tool_button("queue", "More")
        self._btn_more.clicked.connect(self._show_menu)

        self._btn_remove = tool_button("close", "Remove", "danger")
        self._btn_remove.clicked.connect(lambda: self.action.emit("remove", self.job_id))

        for widget in (
            self._btn_pause,
            self._btn_resume,
            self._btn_retry,
            self._btn_folder,
            self._btn_more,
            self._btn_remove,
        ):
            self.buttons.addWidget(widget, 0, Qt.AlignTop)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Copy source link", lambda: self.action.emit("copy", self.job_id))
        menu.addAction("Copy file path", lambda: self.action.emit("copy_path", self.job_id))
        menu.addAction("Open in browser", lambda: self.action.emit("open_url", self.job_id))
        menu.addSeparator()
        menu.addAction("Show log", lambda: self.action.emit("log", self.job_id))
        menu.exec(self._btn_more.mapToGlobal(self._btn_more.rect().bottomLeft()))

    # ---------------------------------------------------------------- update

    def update_from(self, job: Job) -> None:
        self.title.setText(_elide(job.display_title, 110))
        self.title.setToolTip(job.display_title + "\n" + job.url)

        self.state_badge.setText(job.state.label)
        set_prop(self.state_badge, "badge", _BADGE_KIND.get(job.state, "neutral"))

        self.source_badge.setText(job.source or "Link")
        set_prop(self.source_badge, "badge", "neutral")

        set_prop(self, "state", _CARD_STATE.get(job.state, ""))

        parts = [p for p in (job.size_text, job.speed_text, job.eta_text) if p]
        if job.fragment_text:
            parts.append(job.fragment_text)
        if job.state == JobState.DONE and job.filepath:
            parts = [Path(job.filepath).name]
            if job.total_bytes:
                parts.append(human_size(job.total_bytes))
        self.meta.setText("  ".join(parts))

        indeterminate = job.state in (JobState.PROCESSING, JobState.RESOLVING)
        if indeterminate:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(max(0.0, min(100.0, job.progress)) * 10))

        state_key = {
            JobState.FAILED: "error",
            JobState.DONE: "done",
            JobState.SKIPPED: "done",
            JobState.PAUSED: "paused",
            JobState.CANCELLED: "paused",
        }.get(job.state, "")
        set_prop(self.progress, "state", state_key)
        self.progress.setVisible(job.state != JobState.QUEUED or job.progress > 0)

        if job.error:
            self.error.setText(job.error)
            self.error.setStyleSheet(f"color:{theme.current().error};")
            self.error.setVisible(True)
        else:
            self.error.setVisible(False)

        if self._show_thumbnail and job.thumbnail_url:
            self.thumb.set_url(job.thumbnail_url)

        active = job.state.is_active
        self._btn_pause.setVisible(active)
        self._btn_resume.setVisible(job.state in (JobState.PAUSED, JobState.CANCELLED))
        self._btn_retry.setVisible(job.state == JobState.FAILED)
        self._btn_folder.setVisible(job.state in (JobState.DONE, JobState.SKIPPED))

    def set_thumbnail_visible(self, visible: bool) -> None:
        self._show_thumbnail = visible
        self.thumb.setVisible(visible)


class QueueView(QWidget):
    """Scrollable list of job cards with a toolbar and stats."""

    def __init__(self, manager: DownloadManager, settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.manager = manager
        self.settings = settings
        self._cards: dict[int, JobCard] = {}

        m = theme.current_metrics()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(m.pad + 6, m.pad, m.pad + 6, m.pad)
        outer.setSpacing(m.gap)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title_column.addWidget(label("Queue", "headline"))
        self.stats = label("Nothing queued", "caption")
        title_column.addWidget(self.stats)
        header.addLayout(title_column, 1)

        self.btn_toggle = button("Pause all", "outlined", "pause")
        self.btn_toggle.clicked.connect(self._toggle_all)
        header.addWidget(self.btn_toggle)

        self.btn_clear = button("Clear finished", "text", "trash")
        self.btn_clear.clicked.connect(manager.clear_finished)
        header.addWidget(self.btn_clear)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        self._list_host = QWidget()
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 6, 0)
        self._list.setSpacing(m.gap)
        self._list.addStretch(1)
        scroll.setWidget(self._list_host)

        self.empty = self._build_empty_state()
        self._list.insertWidget(0, self.empty)

        manager.jobsAdded.connect(self._on_added)
        manager.jobChanged.connect(self._on_changed)
        manager.jobsRemoved.connect(self._on_removed)
        manager.statsChanged.connect(self._on_stats)

    def _build_empty_state(self) -> QWidget:
        host = Card("flat")
        body = host.body()
        body.setSpacing(4)
        icon = label("", "body")
        icon.setPixmap(icons.icon("download", theme.current().outline, 40).pixmap(QSize(40, 40)))
        icon.setAlignment(Qt.AlignCenter)
        body.addWidget(icon)
        title = label("The queue is empty", "title")
        title.setAlignment(Qt.AlignCenter)
        body.addWidget(title)
        hint = label("Add links from the Download screen to get started.", "caption")
        hint.setAlignment(Qt.AlignCenter)
        body.addWidget(hint)
        return host

    # ---------------------------------------------------------------- events

    def _on_added(self, job_ids: list) -> None:
        for job_id in job_ids:
            job = self.manager.job(job_id)
            if job is None or job_id in self._cards:
                continue
            card = JobCard(job, self.settings.appearance.show_thumbnails)
            card.action.connect(self._on_action)
            self._cards[job_id] = card
            self._list.insertWidget(self._list.count() - 1, card)
        self._update_empty()

    def _on_changed(self, job_id: int) -> None:
        card = self._cards.get(job_id)
        job = self.manager.job(job_id)
        if card is not None and job is not None:
            card.update_from(job)

    def _on_removed(self, job_ids: list) -> None:
        for job_id in job_ids:
            card = self._cards.pop(job_id, None)
            if card is not None:
                self._list.removeWidget(card)
                card.deleteLater()
        self._update_empty()

    def _on_stats(self, stats: dict) -> None:
        if not stats.get("total"):
            self.stats.setText("Nothing queued")
        else:
            bits = [f"{stats['total']} total"]
            for key, word in (
                ("active", "running"),
                ("queued", "waiting"),
                ("done", "done"),
                ("failed", "failed"),
                ("paused", "paused"),
            ):
                if stats.get(key):
                    bits.append(f"{stats[key]} {word}")
            if stats.get("speed"):
                bits.append(f"{human_size(int(stats['speed']))}/s")
            self.stats.setText("   ".join(bits))

        paused = self.manager.is_paused
        self.btn_toggle.setText("Resume all" if paused else "Pause all")
        self.btn_toggle.setIcon(
            icons.icon("play" if paused else "pause", theme.current().primary, 18)
        )

    def _update_empty(self) -> None:
        self.empty.setVisible(not self._cards)

    def _toggle_all(self) -> None:
        if self.manager.is_paused:
            self.manager.start_all()
        else:
            self.manager.pause_all()

    def refresh_appearance(self) -> None:
        visible = self.settings.appearance.show_thumbnails
        for card in self._cards.values():
            card.set_thumbnail_visible(visible)

    # --------------------------------------------------------------- actions

    def _on_action(self, verb: str, job_id: int) -> None:
        job = self.manager.job(job_id)
        if job is None:
            return

        if verb == "pause":
            self.manager.pause(job_id)
        elif verb == "resume":
            self.manager.resume(job_id)
        elif verb == "retry":
            self.manager.retry(job_id)
        elif verb == "remove":
            self.manager.remove(job_id)
        elif verb == "reveal":
            reveal(job.filepath)
        elif verb == "copy":
            _clipboard(job.url)
        elif verb == "copy_path":
            _clipboard(job.filepath or "")
        elif verb == "open_url":
            QDesktopServices.openUrl(QUrl(job.url))
        elif verb == "log":
            self._show_log(job_id)

    def _show_log(self, job_id: int) -> None:
        from PySide6.QtWidgets import QDialog, QPlainTextEdit

        lines = self.manager.logs(job_id)
        job = self.manager.job(job_id)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Log: {job.display_title[:60] if job else job_id}")
        dialog.resize(760, 460)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit("\n".join(lines) or "Nothing logged yet.")
        view.setReadOnly(True)
        layout.addWidget(view)
        close = button("Close", "text")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.exec()


def _clipboard(text: str) -> None:
    from PySide6.QtWidgets import QApplication

    if text:
        QApplication.clipboard().setText(text)


def reveal(filepath: str) -> None:
    """Open the containing folder, selecting the file where the OS allows it."""
    if not filepath:
        return
    path = Path(filepath)
    if not path.exists():
        path = path.parent
        if not path.exists():
            return

    if sys.platform == "win32" and path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
        return

    folder = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _elide(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
