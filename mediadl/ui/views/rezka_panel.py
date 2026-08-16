"""HDRezka panel: load a title, then pick translation, seasons and episodes in bulk."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import logs
from ...config import QUALITIES, Settings
from ...core.engine import job_from_resolved
from ...core.sources import EpisodeRef, SeriesInfo, hdrezka
from .. import theme
from ..widgets import Card, Switch, button, label, tool_button

log = logs.get("ui.rezka")

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


class _ProbeSignals(QObject):
    done = Signal(object)


class _ProbeTask(QRunnable):
    def __init__(self, url, behaviour, rezka):
        super().__init__()
        self.url, self.behaviour, self.rezka = url, behaviour, rezka
        self.signals = _ProbeSignals()

    def run(self) -> None:
        self.signals.done.emit(hdrezka().probe(self.url, self.behaviour, self.rezka))


class _ResolveSignals(QObject):
    done = Signal(list, list, str)
    progress = Signal(int, int, str)


class _ResolveTask(QRunnable):
    def __init__(self, url, behaviour, rezka, refs, quality, is_series):
        super().__init__()
        self.url, self.behaviour, self.rezka = url, behaviour, rezka
        self.refs, self.quality, self.is_series = refs, quality, is_series
        self.signals = _ResolveSignals()

    def run(self) -> None:
        try:
            if not self.is_series:
                items = hdrezka().resolve(self.url, self.behaviour, self.quality, self.rezka)
                self.signals.done.emit(items, [], "")
                return
            items, problems = hdrezka().resolve_episodes(
                self.url,
                self.behaviour,
                self.refs,
                self.quality,
                self.rezka,
                progress=lambda i, n, tag: self.signals.progress.emit(i, n, tag),
            )
            self.signals.done.emit(items, problems, "")
        except Exception as exc:
            logs.exception(log, "HDRezka resolve failed", exc)
            self.signals.done.emit([], [], str(exc))


class RezkaPanel(QWidget):
    jobsReady = Signal(list)
    message = Signal(str, str)  # text, kind

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.info: SeriesInfo | None = None
        self._pool = QThreadPool(self)
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

        layout.addWidget(self._address_card())
        self.options_card = self._options_card()
        layout.addWidget(self.options_card)
        self.episodes_card = self._episodes_card()
        layout.addWidget(self.episodes_card, 1)
        layout.addStretch(0)

        outer.addWidget(self._action_bar())

        self.options_card.setVisible(False)
        self.episodes_card.setVisible(False)
        self._load_settings()

    # ----------------------------------------------------------- address card

    def _address_card(self) -> Card:
        card = Card()
        body = card.body()

        header = QHBoxLayout()
        header.addWidget(label("HDRezka title", "title"))
        header.addStretch(1)
        paste = tool_button("paste", "Paste from clipboard")
        paste.clicked.connect(self._paste)
        header.addWidget(paste)
        body.addLayout(header)

        body.addWidget(
            label(
                "Paste a film or series page, then load it to choose translation, "
                "seasons and episodes.",
                "caption",
            )
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://rezka.ag/series/.../....html")
        self.url_edit.returnPressed.connect(self._load)
        row.addWidget(self.url_edit, 1)
        self.load_btn = button("Load", "filled", "search")
        self.load_btn.clicked.connect(self._load)
        row.addWidget(self.load_btn)
        body.addLayout(row)

        self.status = label("", "caption")
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        return card

    # ----------------------------------------------------------- options card

    def _options_card(self) -> Card:
        card = Card()
        body = card.body()

        self.title_label = label("", "title")
        body.addWidget(self.title_label)

        grid = QHBoxLayout()
        grid.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(label("Translation / dub", "caption"))
        self.translator = QComboBox()
        self.translator.currentIndexChanged.connect(self._on_translator)
        left.addWidget(self.translator)
        grid.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(label("Quality", "caption"))
        self.quality = QComboBox()
        for value in QUALITIES:
            self.quality.addItem(QUALITY_LABELS.get(value, value), value)
        self.quality.currentIndexChanged.connect(self._commit)
        right.addWidget(self.quality)
        grid.addLayout(right, 1)
        body.addLayout(grid)

        self.subs_switch = Switch(True)
        self.subs_switch.toggled.connect(self._commit)
        body.addWidget(_switch_row("Download subtitles", self.subs_switch))

        self.meta_switch = Switch(True)
        self.meta_switch.toggled.connect(self._commit)
        body.addWidget(_switch_row("Write show, season and episode tags", self.meta_switch))

        self.folders_switch = Switch(True)
        self.folders_switch.toggled.connect(self._commit)
        body.addWidget(
            _switch_row("Sort into Show / Season folders", self.folders_switch)
        )

        self.layout_hint = label("", "caption")
        body.addWidget(self.layout_hint)
        return card

    # ---------------------------------------------------------- episodes card

    def _episodes_card(self) -> Card:
        card = Card()
        body = card.body()

        header = QHBoxLayout()
        header.addWidget(label("Episodes", "title"))
        header.addStretch(1)
        self.selection_label = label("", "caption")
        header.addWidget(self.selection_label)
        body.addLayout(header)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        for text, handler in (
            ("All", lambda: self._set_all(True)),
            ("None", lambda: self._set_all(False)),
            ("Latest season", self._select_latest),
        ):
            btn = button(text, "text")
            btn.clicked.connect(handler)
            tools.addWidget(btn)

        tools.addStretch(1)
        tools.addWidget(label("Range", "caption"))
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("e.g. 1-10 or 3,5,7")
        self.range_edit.setMaximumWidth(160)
        self.range_edit.returnPressed.connect(self._apply_range)
        tools.addWidget(self.range_edit)
        apply_btn = button("Apply", "outlined")
        apply_btn.clicked.connect(self._apply_range)
        tools.addWidget(apply_btn)
        body.addLayout(tools)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(240)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tree.itemChanged.connect(self._on_item_changed)
        body.addWidget(self.tree, 1)
        return card

    # ------------------------------------------------------------- action bar

    def _action_bar(self) -> QWidget:
        bar = QWidget()
        m = theme.current_metrics()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, m.gap, 0, 0)

        self.summary = label("", "caption")
        layout.addWidget(self.summary, 1)

        self.add_btn = button("Add to queue", "filled", "download")
        self.add_btn.setMinimumWidth(170)
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._add)
        layout.addWidget(self.add_btn)
        return bar

    # ------------------------------------------------------------------ load

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)

    def set_url(self, url: str, autoload: bool = True) -> None:
        self.url_edit.setText(url)
        if autoload:
            self._load()

    def _load(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self._set_status("Paste a HDRezka link first.", error=True)
            return

        self.settings.rezka.last_url = url
        self.load_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self._set_status("Loading the page...")
        self.options_card.setVisible(False)
        self.episodes_card.setVisible(False)

        task = _ProbeTask(url, self.settings.behaviour, self.settings.rezka)
        task.signals.done.connect(self._on_probed)
        self._pool.start(task)

    def _on_probed(self, info: SeriesInfo) -> None:
        self.load_btn.setEnabled(True)
        self.info = info

        if info.error:
            self._set_status(info.error, error=True)
            if info.blocked:
                self.message.emit("HDRezka served its anti-bot page", "error")
            return

        self.title_label.setText(info.name or "HDRezka")
        self.options_card.setVisible(True)

        self._loading = True
        self.translator.clear()
        source = info.seasons if info.is_series else {}
        for tid, name in info.translators.items():
            if not info.is_series or tid in source:
                count = info.episode_count(tid) if info.is_series else 0
                text = f"{name} ({count} episodes)" if count else name
                self.translator.addItem(text, tid)
        if self.translator.count() == 0:
            self.translator.addItem("Default", info.default_translator or "")
        preferred = self.settings.rezka.translator_id or info.default_translator
        index = self.translator.findData(preferred)
        self.translator.setCurrentIndex(max(0, index))
        self._loading = False

        self.episodes_card.setVisible(info.is_series)
        if info.is_series:
            self._populate_tree()
            self._set_status(
                f"{len(info.translators)} translations available. "
                "Tick the episodes you want."
            )
        else:
            self._set_status("This is a film. Set the quality, then add it to the queue.")
            self.add_btn.setEnabled(True)
            self._update_summary()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{theme.current().error};" if error else "")

    # ------------------------------------------------------------------ tree

    def _populate_tree(self) -> None:
        if self.info is None:
            return
        tid = str(self.translator.currentData() or "")
        seasons = self.info.seasons.get(tid, {})

        self._loading = True
        self.tree.clear()
        for season in sorted(seasons):
            parent = QTreeWidgetItem(self.tree, [f"Season {season}"])
            parent.setFlags(parent.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            parent.setCheckState(0, Qt.Unchecked)
            parent.setData(0, Qt.UserRole, ("season", season))
            for episode in seasons[season]:
                child = QTreeWidgetItem(parent, [f"Episode {episode}"])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, Qt.UserRole, ("episode", season, episode))
        self.tree.expandAll()
        self._loading = False
        self._update_summary()

    def _on_translator(self) -> None:
        if self._loading or self.info is None:
            return
        self.settings.rezka.translator_id = str(self.translator.currentData() or "")
        if self.info.is_series:
            self._populate_tree()

    def _on_item_changed(self, *_args) -> None:
        if not self._loading:
            self._update_summary()

    def _iter_episodes(self):
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                yield parent.child(j)

    def selected_refs(self) -> list[EpisodeRef]:
        tid = str(self.translator.currentData() or "")
        refs = []
        for item in self._iter_episodes():
            if item.checkState(0) != Qt.Checked:
                continue
            payload = item.data(0, Qt.UserRole)
            refs.append(EpisodeRef(season=payload[1], episode=payload[2], translator_id=tid))
        return refs

    def _set_all(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        self._loading = True
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)
        self._loading = False
        self._update_summary()

    def _select_latest(self) -> None:
        self._set_all(False)
        if self.tree.topLevelItemCount():
            self._loading = True
            self.tree.topLevelItem(self.tree.topLevelItemCount() - 1).setCheckState(0, Qt.Checked)
            self._loading = False
            self._update_summary()

    def _apply_range(self) -> None:
        wanted = parse_range(self.range_edit.text())
        if not wanted:
            self._set_status("Could not read that range. Use 1-10 or 3,5,7.", error=True)
            return
        self._loading = True
        for item in self._iter_episodes():
            _, _season, episode = item.data(0, Qt.UserRole)
            item.setCheckState(0, Qt.Checked if episode in wanted else Qt.Unchecked)
        self._loading = False
        self._update_summary()
        self._set_status(f"Selected episodes matching {self.range_edit.text().strip()}.")

    def _update_summary(self) -> None:
        if self.info is None:
            return
        if not self.info.is_series:
            self.selection_label.setText("")
            self.summary.setText(f"Film at {self.quality.currentText()}")
            self._update_layout_hint(None)
            return

        refs = self.selected_refs()
        seasons = sorted({r.season for r in refs})
        self.selection_label.setText(f"{len(refs)} selected")
        self.add_btn.setEnabled(bool(refs))

        if refs:
            span = f"season {seasons[0]}" if len(seasons) == 1 else f"{len(seasons)} seasons"
            self.summary.setText(
                f"{len(refs)} episodes from {span} at {self.quality.currentText()}"
            )
        else:
            self.summary.setText("Nothing selected")
        self._update_layout_hint(refs[0] if refs else None)

    def _update_layout_hint(self, ref) -> None:
        from ...core import presets

        show = (self.info.name if self.info else "") or "Show"
        if ref is None:
            self.layout_hint.setText("")
            return
        folder, stem = presets.episode_paths(
            self.settings.behaviour, self.settings.preset, show, ref.season, ref.episode, "HDRezka"
        )
        self.layout_hint.setText(f"Files land as {folder}\\{stem}.mp4")

    # ------------------------------------------------------------------- add

    def _commit(self) -> None:
        if self._loading:
            return
        rezka = self.settings.rezka
        rezka.quality = self.quality.currentData() or "1080"
        rezka.subtitles = self.subs_switch.isChecked()
        rezka.embed_metadata = self.meta_switch.isChecked()
        rezka.season_folders = self.folders_switch.isChecked()
        self.settings.behaviour.tv_folders = rezka.season_folders
        self._update_summary()

    def _load_settings(self) -> None:
        self._loading = True
        rezka = self.settings.rezka
        index = self.quality.findData(rezka.quality)
        if index >= 0:
            self.quality.setCurrentIndex(index)
        self.subs_switch.setChecked(rezka.subtitles, animate=False)
        self.meta_switch.setChecked(rezka.embed_metadata, animate=False)
        self.folders_switch.setChecked(rezka.season_folders, animate=False)
        if rezka.last_url:
            self.url_edit.setText(rezka.last_url)
        self._loading = False

    def _add(self) -> None:
        if self.info is None:
            return
        refs = self.selected_refs() if self.info.is_series else []
        if self.info.is_series and not refs:
            self._set_status("Tick at least one episode first.", error=True)
            return

        self._commit()
        self.add_btn.setEnabled(False)
        self._set_status(f"Resolving {len(refs) or 1} stream(s). This can take a while...")

        task = _ResolveTask(
            self.url_edit.text().strip(),
            self.settings.behaviour,
            self.settings.rezka,
            refs,
            self.settings.rezka.quality,
            self.info.is_series,
        )
        task.signals.progress.connect(self._on_resolve_progress)
        task.signals.done.connect(self._on_resolved)
        self._pool.start(task)

    def _on_resolve_progress(self, index: int, total: int, tag: str) -> None:
        self._set_status(f"Resolving {tag} ({index} of {total})...")

    def _on_resolved(self, items: list, problems: list, error: str) -> None:
        self.add_btn.setEnabled(True)

        if error:
            self._set_status(error, error=True)
            self.message.emit(error, "error")
            return
        if not items:
            detail = "; ".join(problems[:3]) if problems else "no streams were offered"
            self._set_status(f"Nothing could be resolved: {detail}", error=True)
            return

        jobs = [job_from_resolved(item, self.settings.preset) for item in items]
        self.jobsReady.emit(jobs)

        if problems:
            self._set_status(
                f"Queued {len(jobs)}, skipped {len(problems)}: {problems[0]}", error=True
            )
        else:
            self._set_status(f"Queued {len(jobs)} item(s).")
        self.message.emit(f"Added {len(jobs)} item(s) from HDRezka", "success")

    def refresh(self) -> None:
        self._update_summary()


def parse_range(text: str) -> set[int]:
    """Read '1-10', '3,5,7' or a mix of both into a set of episode numbers."""
    wanted: set[int] = set()
    for chunk in str(text).replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            try:
                low, high = int(start), int(end)
            except ValueError:
                continue
            if low > high:
                low, high = high, low
            wanted.update(range(low, high + 1))
        else:
            try:
                wanted.add(int(chunk))
            except ValueError:
                continue
    return wanted


def _switch_row(text: str, switch: Switch) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label(text, "body"), 1)
    layout.addWidget(switch, 0, Qt.AlignRight)
    return row
