"""Logs screen: what the app and yt-dlp actually did, without leaving the app."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ... import logs, paths
from ..widgets import Switch, button, label
from .. import theme

LEVELS = ("All", "INFO", "WARNING", "ERROR", "DEBUG")


class LogsView(QWidget):
    def __init__(self, settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings

        m = theme.current_metrics()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.pad + 6, m.pad, m.pad + 6, m.pad)
        layout.setSpacing(m.gap)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(1)
        column.addWidget(label("Logs", "headline"))
        self.subtitle = label(str(paths.log_file()), "caption")
        self.subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column.addWidget(self.subtitle)
        header.addLayout(column, 1)

        open_btn = button("Open log folder", "outlined", "folder")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.config_dir())))
        )
        header.addWidget(open_btn)

        copy_btn = button("Copy", "outlined", "copy")
        copy_btn.clicked.connect(self._copy)
        header.addWidget(copy_btn)

        clear_btn = button("Clear", "text", "trash")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        controls.addWidget(label("Level", "caption"))
        self.level = QComboBox()
        self.level.addItems(LEVELS)
        self.level.setMaximumWidth(140)
        self.level.currentIndexChanged.connect(self.reload)
        controls.addWidget(self.level)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter, for example 403 or hdrezka")
        self.filter.textChanged.connect(self.reload)
        controls.addWidget(self.filter, 1)

        controls.addWidget(label("Verbose", "caption"))
        self.verbose = Switch(settings.behaviour.verbose_logging)
        self.verbose.toggled.connect(self._on_verbose)
        controls.addWidget(self.verbose)

        controls.addWidget(label("Follow", "caption"))
        self.follow = Switch(True)
        controls.addWidget(self.follow)
        layout.addLayout(controls)

        self.view = QPlainTextEdit()
        self.view.setObjectName("LogView")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setMaximumBlockCount(6000)
        layout.addWidget(self.view, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._tick)
        self._last_count = 0

        self.reload()

    # ------------------------------------------------------------------ data

    def _lines(self) -> list[str]:
        level = self.level.currentText()
        raw = logs.ring().lines(level="" if level == "All" else level)
        needle = self.filter.text().strip().lower()
        if needle:
            raw = [line for line in raw if needle in line.lower()]
        return raw

    def reload(self) -> None:
        lines = self._lines()
        self._last_count = len(logs.ring().lines())
        self.view.setPlainText("\n".join(lines))
        if self.follow.isChecked():
            self._scroll_to_end()

    def _tick(self) -> None:
        total = len(logs.ring().lines())
        if total != self._last_count:
            self.reload()

    def _scroll_to_end(self) -> None:
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # --------------------------------------------------------------- actions

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.view.toPlainText())

    def _clear(self) -> None:
        logs.ring().clear()
        self.reload()

    def _on_verbose(self, value: bool) -> None:
        self.settings.behaviour.verbose_logging = value
        logs.setup(value)

    # --------------------------------------------------------------- visibility

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload()
        self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
