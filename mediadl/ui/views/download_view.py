"""The compose screen.

One tab per service. Auto and YouTube share the link-based panel; HDRezka gets
its own because a series needs translation, season and episode choices that no
other source has.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...config import (
    AUDIO_BITRATES,
    AUDIO_CODECS,
    QUALITIES,
    VIDEO_CONTAINERS,
    Settings,
)
from ...core import presets
from .. import theme
from ..widgets import Card, ChipGroup, SegmentedTabs, Switch, button, label, tool_button
from .rezka_panel import RezkaPanel

URL_RE = re.compile(r"https?://\S+")

# Punctuation to trim from the end of a pasted link. chr(0xBB) is the closing
# guillemet, which Cyrillic and French text wraps links in; it is spelled as a
# code point so this file stays ASCII.
TRAILING_JUNK = ".,;)\"'" + chr(0xBB)

QUALITY_LABELS = {
    "best": "Best available",
    "2160": "2160p (4K)",
    "1440": "1440p",
    "1080": "1080p",
    "720": "720p",
    "480": "480p",
    "360": "360p",
    "worst": "Smallest file",
}

SERVICES = [
    ("auto", "Auto detect", "search"),
    ("youtube", "YouTube", "video"),
    ("hdrezka", "HDRezka", "music"),
]

PLACEHOLDERS = {
    "auto": (
        "https://www.youtube.com/watch?v=...\n"
        "https://www.reddit.com/r/videos/comments/...\n"
        "https://x.com/user/status/...\n"
        "https://vimeo.com/..."
    ),
    "youtube": (
        "https://www.youtube.com/watch?v=...\n"
        "https://www.youtube.com/playlist?list=...\n"
        "https://www.youtube.com/@channel/videos"
    ),
}


class LinkPanel(QWidget):
    """Paste links, choose a format, choose a destination."""

    submitted = Signal(list)
    changed = Signal()

    def __init__(self, settings: Settings, service: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.service = service
        self._loading = False

        m = theme.current_metrics()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.gap)

        layout.addWidget(self._input_card())
        layout.addWidget(self._format_card())
        if service == "youtube":
            layout.addWidget(self._youtube_card())
        layout.addWidget(self._destination_card())
        layout.addStretch(1)

        outer.addWidget(self._action_bar())
        self._load_from_settings()
        self._sync_mode_controls()

    # ------------------------------------------------------------ input card

    def _input_card(self) -> Card:
        card = Card()
        body = card.body()

        header = QHBoxLayout()
        header.addWidget(label("Links", "title"))
        header.addStretch(1)
        paste = tool_button("paste", "Paste from clipboard")
        paste.clicked.connect(self._paste)
        header.addWidget(paste)
        from_file = tool_button("file", "Import a .txt list of links")
        from_file.clicked.connect(self._import_file)
        header.addWidget(from_file)
        clear = tool_button("trash", "Clear", "danger")
        clear.clicked.connect(lambda: self.input.clear())
        header.addWidget(clear)
        body.addLayout(header)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(PLACEHOLDERS.get(self.service, PLACEHOLDERS["auto"]))
        self.input.setMinimumHeight(120)
        self.input.textChanged.connect(self._update_count)
        body.addWidget(self.input)

        self.count_label = label("No links yet", "caption")
        body.addWidget(self.count_label)
        return card

    # ----------------------------------------------------------- format card

    def _format_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Format", "title"))

        self.mode_chips = ChipGroup(
            [("Video + audio", "video"), ("Audio only", "audio"), ("Video only", "video_only")]
        )
        self.mode_chips.changed.connect(self._on_mode_changed)
        body.addWidget(self.mode_chips)

        form = QFormLayout()
        form.setSpacing(theme.current_metrics().gap)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.quality = QComboBox()
        for value in QUALITIES:
            self.quality.addItem(QUALITY_LABELS.get(value, value), value)
        self.quality.currentIndexChanged.connect(self._commit)
        self.quality_label = label("Quality", "body")
        form.addRow(self.quality_label, self.quality)

        self.container = QComboBox()
        for value in VIDEO_CONTAINERS:
            self.container.addItem("Keep original" if value == "auto" else value.upper(), value)
        self.container.currentIndexChanged.connect(self._commit)
        self.container_label = label("Container", "body")
        form.addRow(self.container_label, self.container)

        self.codec = QComboBox()
        for value in AUDIO_CODECS:
            self.codec.addItem("Best available" if value == "best" else value.upper(), value)
        self.codec.currentIndexChanged.connect(self._commit)
        self.codec_label = label("Audio format", "body")
        form.addRow(self.codec_label, self.codec)

        self.bitrate = QComboBox()
        for value in AUDIO_BITRATES:
            self.bitrate.addItem("Best available" if value == "best" else f"{value} kbps", value)
        self.bitrate.currentIndexChanged.connect(self._commit)
        self.bitrate_label = label("Bitrate", "body")
        form.addRow(self.bitrate_label, self.bitrate)

        body.addLayout(form)
        return card

    # ---------------------------------------------------------- youtube card

    def _youtube_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("YouTube options", "title"))

        self.expand_switch = Switch(self.settings.behaviour.expand_playlists)
        self.expand_switch.toggled.connect(self._on_expand)
        body.addWidget(
            _switch_row("Expand playlists and channels into separate items", self.expand_switch)
        )

        self.sponsor_switch = Switch(self.settings.behaviour.skip_sponsors)
        self.sponsor_switch.toggled.connect(self._on_sponsors)
        body.addWidget(_switch_row("Skip sponsor segments (SponsorBlock)", self.sponsor_switch))

        self.chapters_switch = Switch(self.settings.behaviour.embed_chapters)
        self.chapters_switch.toggled.connect(self._on_chapters)
        body.addWidget(_switch_row("Keep chapter markers", self.chapters_switch))

        body.addWidget(
            label(
                "Age-restricted or members-only videos need cookies. Set them in "
                "Settings > Network.",
                "caption",
            )
        )
        return card

    # ------------------------------------------------------ destination card

    def _destination_card(self) -> Card:
        card = Card()
        body = card.body()

        header = QHBoxLayout()
        header.addWidget(label("Destination", "title"))
        header.addStretch(1)
        open_btn = tool_button("external", "Open this folder")
        open_btn.clicked.connect(self._open_folder)
        header.addWidget(open_btn)
        body.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(str(self.settings.behaviour.resolved_download_dir()))
        self.path_edit.editingFinished.connect(self._commit_path)
        row.addWidget(self.path_edit, 1)
        browse = button("Browse", "outlined", "folder")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        body.addLayout(row)

        self.category_switch = Switch(self.settings.behaviour.organize_by_category)
        self.category_switch.toggled.connect(self._on_category_toggled)
        body.addWidget(_switch_row("Sort into Video and Audio folders", self.category_switch))

        self.source_switch = Switch(self.settings.behaviour.organize_by_source)
        self.source_switch.toggled.connect(self._on_source_toggled)
        body.addWidget(_switch_row("Add a sub-folder per site", self.source_switch))

        self.target_hint = label("", "caption")
        body.addWidget(self.target_hint)
        return card

    # ------------------------------------------------------------ action bar

    def _action_bar(self) -> QWidget:
        bar = QWidget()
        m = theme.current_metrics()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, m.gap, 0, 0)

        self.summary = label("", "caption")
        layout.addWidget(self.summary, 1)

        self.go = button("Add to queue", "filled", "download")
        self.go.setMinimumWidth(170)
        self.go.clicked.connect(self._submit)
        layout.addWidget(self.go)
        return bar

    # --------------------------------------------------------------- helpers

    def urls(self) -> list[str]:
        text = self.input.toPlainText()
        found = URL_RE.findall(text)
        if found:
            seen, unique = set(), []
            for url in found:
                url = url.rstrip(TRAILING_JUNK)
                if url not in seen:
                    seen.add(url)
                    unique.append(url)
            return unique
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _update_count(self) -> None:
        count = len(self.urls())
        self.count_label.setText(
            "No links yet" if not count else f"{count} link{'s' if count != 1 else ''} detected"
        )
        self.go.setEnabled(count > 0)
        self._update_summary()

    def _update_summary(self) -> None:
        preset = self.settings.preset
        target = presets.target_dir(self.settings.behaviour, preset)
        self.summary.setText(f"{presets.describe(preset)}  to  {target}")
        self.target_hint.setText(f"Files land in {target}")

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text().strip()
        if not text:
            return
        current = self.input.toPlainText()
        self.input.setPlainText(f"{current.rstrip()}\n{text}" if current.strip() else text)

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import links", "", "Text files (*.txt *.csv);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        current = self.input.toPlainText()
        self.input.setPlainText(f"{current.rstrip()}\n{text}" if current.strip() else text)

    def _browse(self) -> None:
        start = str(self.settings.behaviour.resolved_download_dir())
        chosen = QFileDialog.getExistingDirectory(self, "Choose a download folder", start)
        if chosen:
            self.path_edit.setText(chosen)
            self._commit_path()

    def _open_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = presets.target_dir(self.settings.behaviour, self.settings.preset)
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _submit(self) -> None:
        found = self.urls()
        if found:
            self.submitted.emit(found)

    def clear_input(self) -> None:
        self.input.clear()

    # ----------------------------------------------------------- persistence

    def _load_from_settings(self) -> None:
        # Populating a combo fires currentIndexChanged, and _commit writes every
        # control back into the shared Preset, so the values are read up front
        # and writes are suppressed while loading.
        preset = self.settings.preset
        mode, quality = preset.mode, preset.quality
        container, codec, bitrate = (
            preset.video_container,
            preset.audio_codec,
            preset.audio_bitrate,
        )

        self._loading = True
        try:
            self.mode_chips.set_value(mode)
            _select(self.quality, quality)
            _select(self.container, container)
            _select(self.codec, codec)
            _select(self.bitrate, bitrate)
            if self.settings.behaviour.download_dir:
                self.path_edit.setText(self.settings.behaviour.download_dir)
        finally:
            self._loading = False

        self._update_count()

    def _on_mode_changed(self, _value) -> None:
        self._commit()
        self._sync_mode_controls()

    def _sync_mode_controls(self) -> None:
        audio = self.settings.preset.mode == "audio"
        for widget in (self.codec, self.codec_label, self.bitrate, self.bitrate_label):
            widget.setVisible(audio)
        for widget in (self.container, self.container_label):
            widget.setVisible(not audio)
        self.quality.setEnabled(not audio)
        self.quality_label.setEnabled(not audio)

    def _commit(self) -> None:
        if self._loading:
            return
        preset = self.settings.preset
        preset.mode = self.mode_chips.value() or "video"
        preset.quality = self.quality.currentData() or "1080"
        preset.video_container = self.container.currentData() or "mp4"
        preset.audio_codec = self.codec.currentData() or "mp3"
        preset.audio_bitrate = self.bitrate.currentData() or "192"
        self._update_summary()
        self.changed.emit()

    def _commit_path(self) -> None:
        self.settings.behaviour.download_dir = self.path_edit.text().strip()
        self._update_summary()
        self.changed.emit()

    def _behaviour(self, **kwargs) -> None:
        if self._loading:
            return
        for key, value in kwargs.items():
            setattr(self.settings.behaviour, key, value)
        self._update_summary()
        self.changed.emit()

    def _on_category_toggled(self, value: bool) -> None:
        self._behaviour(organize_by_category=value)

    def _on_source_toggled(self, value: bool) -> None:
        self._behaviour(organize_by_source=value)

    def _on_expand(self, value: bool) -> None:
        self._behaviour(expand_playlists=value)

    def _on_sponsors(self, value: bool) -> None:
        self._behaviour(skip_sponsors=value)

    def _on_chapters(self, value: bool) -> None:
        self._behaviour(embed_chapters=value)

    def refresh(self) -> None:
        self._loading = True
        try:
            self.category_switch.setChecked(
                self.settings.behaviour.organize_by_category, animate=False
            )
            self.source_switch.setChecked(
                self.settings.behaviour.organize_by_source, animate=False
            )
            self.path_edit.setText(self.settings.behaviour.download_dir)
        finally:
            self._loading = False
        self._update_summary()


class DownloadView(QWidget):
    """Tab host for the per-service panels."""

    submitted = Signal(list)
    jobsReady = Signal(list)
    settingsChanged = Signal()
    message = Signal(str, str)

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings

        m = theme.current_metrics()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.pad + 6, m.pad, m.pad + 6, m.pad)
        layout.setSpacing(m.gap)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title_column.addWidget(label("Download", "headline"))
        title_column.addWidget(
            label("Pick a service, or let Auto detect work it out from the link.", "caption")
        )
        header.addLayout(title_column, 1)
        layout.addLayout(header)

        self.tabs = SegmentedTabs(SERVICES)
        self.tabs.changed.connect(self._on_tab)
        layout.addWidget(self.tabs, 0, Qt.AlignLeft)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.auto_panel = LinkPanel(settings, "auto")
        self.youtube_panel = LinkPanel(settings, "youtube")
        self.rezka_panel = RezkaPanel(settings)

        for panel in (self.auto_panel, self.youtube_panel, self.rezka_panel):
            self.stack.addWidget(panel)

        for panel in (self.auto_panel, self.youtube_panel):
            panel.submitted.connect(self.submitted)
            panel.changed.connect(self.settingsChanged)

        self.rezka_panel.jobsReady.connect(self.jobsReady)
        self.rezka_panel.message.connect(self.message)

        self._keys = [key for key, _text, _icon in SERVICES]
        self.set_service(settings.active_service or "auto")

    # ------------------------------------------------------------------ tabs

    def _on_tab(self, key: str) -> None:
        self.settings.active_service = key
        self.stack.setCurrentIndex(self._keys.index(key) if key in self._keys else 0)
        self.settingsChanged.emit()

    def set_service(self, key: str) -> None:
        if key not in self._keys:
            key = "auto"
        self.tabs.set_value(key)
        self.settings.active_service = key
        self.stack.setCurrentIndex(self._keys.index(key))

    def open_rezka(self, url: str) -> None:
        """Route a pasted HDRezka link to its own panel instead of a modal."""
        self.set_service("hdrezka")
        self.rezka_panel.set_url(url)

    # --------------------------------------------------------------- passthru

    @property
    def input(self):
        """The active link box, used by the command line and paste shortcut."""
        panel = self.stack.currentWidget()
        return getattr(panel, "input", self.auto_panel.input)

    def clear_input(self) -> None:
        for panel in (self.auto_panel, self.youtube_panel):
            panel.clear_input()

    def _submit(self) -> None:
        panel = self.stack.currentWidget()
        if hasattr(panel, "_submit"):
            panel._submit()
        elif hasattr(panel, "_add"):
            panel._add()

    def _paste(self) -> None:
        panel = self.stack.currentWidget()
        if hasattr(panel, "_paste"):
            panel._paste()

    def refresh(self) -> None:
        self.auto_panel.refresh()
        self.youtube_panel.refresh()
        self.rezka_panel.refresh()
        self.tabs.refresh_icons()


def _switch_row(text: str, switch: Switch) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label(text, "body"), 1)
    layout.addWidget(switch, 0, Qt.AlignRight)
    return row


def _select(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
