"""Settings: how the app looks and how downloading behaves."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ... import paths
from ...config import BROWSERS, Settings, accents_for
from .. import fonts, theme
from ..widgets import (
    Card,
    ChipGroup,
    SettingRow,
    Switch,
    button,
    label,
    tool_button,
)


class Swatch(QWidget):
    """A round colour chip used to pick the accent seed."""

    picked = Signal(str)

    def __init__(self, name: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.value = value
        self.setFixedSize(38, 38)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)
        self._selected = False

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.picked.emit(self.value)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.value))
        inset = 4 if self._selected else 2
        painter.drawEllipse(self.rect().adjusted(inset, inset, -inset, -inset))
        if self._selected:
            pen = painter.pen()
            pen.setColor(QColor(theme.current().on_surface))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        painter.end()


class SettingsView(QWidget):
    appearanceChanged = Signal()
    behaviourChanged = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)

        m = theme.current_metrics()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(m.pad + 6, m.pad, m.pad + 6, m.pad)
        layout.setSpacing(m.gap + 2)

        layout.addWidget(label("Settings", "headline"))
        layout.addWidget(self._appearance_card())
        layout.addWidget(self._downloads_card())
        layout.addWidget(self._processing_card())
        layout.addWidget(self._network_card())
        layout.addWidget(self._advanced_card())
        layout.addStretch(1)

        self._load()

    # ------------------------------------------------------------ appearance

    def _appearance_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Appearance", "title"))

        self.design_chips = ChipGroup([("Studio", "studio"), ("Vibrant", "vibrant")])
        self.design_chips.changed.connect(self._on_design)
        body.addWidget(
            SettingRow(
                "Design",
                "Studio matches Modpack-Utility: neutral surfaces, muted accents, "
                "small radii. Vibrant is the saturated Material treatment.",
                None,
            )
        )
        body.addWidget(self.design_chips)

        self.theme_chips = ChipGroup(
            [("Follow Windows", "system"), ("Light", "light"), ("Dark", "dark")]
        )
        self.theme_chips.changed.connect(self._on_theme_mode)
        body.addWidget(SettingRow("Theme", "Which colour scheme to use", None))
        body.addWidget(self.theme_chips)

        body.addWidget(label("Accent colour", "body"))
        self.swatch_row = QHBoxLayout()
        self.swatch_row.setSpacing(6)
        self.swatches: list[Swatch] = []
        self._build_swatches()

        custom = tool_button("palette", "Pick a custom colour", "accent")
        custom.clicked.connect(self._pick_custom_accent)
        self.swatch_row.addWidget(custom)
        self.swatch_row.addStretch(1)
        body.addLayout(self.swatch_row)

        self.radius = QSlider(Qt.Horizontal)
        self.radius.setRange(0, 28)
        self.radius.setFixedWidth(200)
        self.radius.valueChanged.connect(self._on_radius)
        body.addWidget(SettingRow("Corner rounding", "0 is square, 28 is fully rounded", self.radius))

        self.density_chips = ChipGroup([("Comfortable", "comfortable"), ("Compact", "compact")])
        self.density_chips.changed.connect(self._on_density)
        body.addWidget(SettingRow("Density", "Spacing and control height", None))
        body.addWidget(self.density_chips)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 16)
        self.font_size.setSuffix(" pt")
        self.font_size.setFixedWidth(110)
        self.font_size.valueChanged.connect(self._on_font_size)
        body.addWidget(SettingRow("Text size", "Base font size for the interface", self.font_size))

        self.font_family = QComboBox()
        self.font_family.setFixedWidth(200)
        for family in ("Segoe UI", "Segoe UI Variable Text", "Inter", "Roboto", "Verdana", "Tahoma"):
            if fonts.has_family(family):
                self.font_family.addItem(family, family)
        if self.font_family.count() == 0:
            self.font_family.addItem("Segoe UI", "Segoe UI")
        self.font_family.currentIndexChanged.connect(self._on_font_family)
        body.addWidget(SettingRow("Interface font", "Body text typeface", self.font_family))

        self.animations = Switch()
        self.animations.toggled.connect(self._on_animations)
        body.addWidget(
            SettingRow("Animations", "Animate toggles and transitions", self.animations)
        )

        self.thumbs = Switch()
        self.thumbs.toggled.connect(self._on_thumbs)
        body.addWidget(
            SettingRow("Thumbnails in queue", "Fetch preview images for each item", self.thumbs)
        )

        logo_state = (
            "Comfortaa is loaded"
            if fonts.has_family(fonts.LOGO_FAMILY)
            else "Comfortaa not found, using the interface font for the logo"
        )
        body.addWidget(label(logo_state, "caption"))
        return card

    # ------------------------------------------------------------- downloads

    def _downloads_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Downloads", "title"))

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.download_dir = QLineEdit()
        self.download_dir.setMinimumWidth(240)
        self.download_dir.editingFinished.connect(self._on_dir)
        path_layout.addWidget(self.download_dir)
        browse = button("Browse", "outlined")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        body.addWidget(SettingRow("Save to", "Where finished files are written", path_row))

        self.template = QLineEdit()
        self.template.setMinimumWidth(300)
        self.template.editingFinished.connect(self._on_template)
        body.addWidget(
            SettingRow(
                "Filename template",
                "yt-dlp output template, for example %(title)s.%(ext)s",
                self.template,
            )
        )

        self.by_category = Switch()
        self.by_category.toggled.connect(self._on_by_category)
        body.addWidget(
            SettingRow("Sort by media type", "Separate Video and Audio folders", self.by_category)
        )

        self.by_source = Switch()
        self.by_source.toggled.connect(self._on_by_source)
        body.addWidget(
            SettingRow("Sort by site", "Add a sub-folder per source site", self.by_source)
        )

        self.expand = Switch()
        self.expand.toggled.connect(self._on_expand)
        body.addWidget(
            SettingRow(
                "Expand playlists",
                "Add each playlist entry as its own queue item",
                self.expand,
            )
        )

        self.playlist_limit = QSpinBox()
        self.playlist_limit.setRange(0, 5000)
        self.playlist_limit.setSpecialValueText("No limit")
        self.playlist_limit.setFixedWidth(130)
        self.playlist_limit.valueChanged.connect(self._on_playlist_limit)
        body.addWidget(
            SettingRow("Playlist limit", "Stop after this many entries", self.playlist_limit)
        )

        self.tv_folders = Switch()
        self.tv_folders.toggled.connect(self._on_tv_folders)
        body.addWidget(
            SettingRow(
                "Series get season folders",
                "Episodes land as Show / Season 06 / Show - S06E20",
                self.tv_folders,
            )
        )

        self.open_folder = Switch()
        self.open_folder.toggled.connect(self._on_open_folder)
        body.addWidget(
            SettingRow(
                "Open folder when done",
                "Reveal the folder once the queue finishes",
                self.open_folder,
            )
        )
        return card

    # ------------------------------------------------------------ processing

    def _processing_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Metadata and processing", "title"))

        self.meta = Switch()
        self.meta.toggled.connect(self._on_meta)
        body.addWidget(
            SettingRow("Embed metadata", "Write title, artist and description tags", self.meta)
        )

        self.thumb_embed = Switch()
        self.thumb_embed.toggled.connect(self._on_thumb_embed)
        body.addWidget(
            SettingRow("Embed cover art", "Attach the thumbnail to the file", self.thumb_embed)
        )

        self.chapters = Switch()
        self.chapters.toggled.connect(self._on_chapters)
        body.addWidget(SettingRow("Embed chapters", "Keep chapter markers", self.chapters))

        self.embed_subs = Switch()
        self.embed_subs.toggled.connect(self._on_embed_subs)
        body.addWidget(
            SettingRow("Embed subtitles", "Mux subtitles into the video", self.embed_subs)
        )

        self.write_subs = Switch()
        self.write_subs.toggled.connect(self._on_write_subs)
        body.addWidget(
            SettingRow(
                "Include auto-generated subtitles",
                "Also fetch machine transcripts where offered",
                self.write_subs,
            )
        )

        self.sub_langs = QLineEdit()
        self.sub_langs.setFixedWidth(200)
        self.sub_langs.editingFinished.connect(self._on_sub_langs)
        body.addWidget(
            SettingRow("Subtitle languages", "Comma separated, for example en,ru", self.sub_langs)
        )

        self.sponsors = Switch()
        self.sponsors.toggled.connect(self._on_sponsors)
        body.addWidget(
            SettingRow(
                "Skip sponsor segments",
                "Use SponsorBlock to cut sponsor and self-promo sections",
                self.sponsors,
            )
        )
        return card

    # --------------------------------------------------------------- network

    def _network_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Network", "title"))

        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 8)
        self.concurrent.setFixedWidth(110)
        self.concurrent.valueChanged.connect(self._on_concurrent)
        body.addWidget(
            SettingRow("Simultaneous downloads", "How many run at once", self.concurrent)
        )

        self.rate = QSpinBox()
        self.rate.setRange(0, 200000)
        self.rate.setSingleStep(256)
        self.rate.setSuffix(" KB/s")
        self.rate.setSpecialValueText("Unlimited")
        self.rate.setFixedWidth(150)
        self.rate.valueChanged.connect(self._on_rate)
        body.addWidget(SettingRow("Speed limit", "Cap total transfer rate", self.rate))

        self.retries = QSpinBox()
        self.retries.setRange(0, 50)
        self.retries.setFixedWidth(110)
        self.retries.valueChanged.connect(self._on_retries)
        body.addWidget(SettingRow("Retries", "Attempts before giving up", self.retries))

        self.proxy = QLineEdit()
        self.proxy.setPlaceholderText("http://host:port")
        self.proxy.setMinimumWidth(240)
        self.proxy.editingFinished.connect(self._on_proxy)
        body.addWidget(SettingRow("Proxy", "Leave blank for a direct connection", self.proxy))

        self.cookies = QComboBox()
        self.cookies.setFixedWidth(180)
        for value in BROWSERS:
            self.cookies.addItem("None" if not value else value.capitalize(), value)
        self.cookies.currentIndexChanged.connect(self._on_cookies)
        body.addWidget(
            SettingRow(
                "Use cookies from",
                "Needed for age-restricted or private media",
                self.cookies,
            )
        )
        return card

    # -------------------------------------------------------------- advanced

    def _advanced_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Advanced", "title"))

        ffmpeg_row = QWidget()
        ffmpeg_layout = QHBoxLayout(ffmpeg_row)
        ffmpeg_layout.setContentsMargins(0, 0, 0, 0)
        self.ffmpeg = QLineEdit()
        self.ffmpeg.setMinimumWidth(240)
        self.ffmpeg.editingFinished.connect(self._on_ffmpeg)
        ffmpeg_layout.addWidget(self.ffmpeg)
        pick = button("Browse", "outlined")
        pick.clicked.connect(self._browse_ffmpeg)
        ffmpeg_layout.addWidget(pick)
        body.addWidget(
            SettingRow("ffmpeg location", _ffmpeg_status(self.settings), ffmpeg_row)
        )

        self.mirror = QLineEdit()
        self.mirror.setPlaceholderText("rezka.ag")
        self.mirror.setMinimumWidth(200)
        self.mirror.editingFinished.connect(self._on_mirror)
        body.addWidget(
            SettingRow(
                "HDRezka mirror",
                "Use a different host if the usual one is unreachable",
                self.mirror,
            )
        )

        self.chunk = QSpinBox()
        self.chunk.setRange(0, 100)
        self.chunk.setSuffix(" MB")
        self.chunk.setSpecialValueText("Off")
        self.chunk.setFixedWidth(120)
        self.chunk.valueChanged.connect(self._on_chunk)
        body.addWidget(
            SettingRow(
                "Download in chunks",
                "Requests the file in ranges. Keeps long transfers from failing "
                "with HTTP 403 when the media URL expires.",
                self.chunk,
            )
        )

        self.strict = Switch()
        self.strict.toggled.connect(self._on_strict)
        body.addWidget(
            SettingRow(
                "Strict container matching",
                "Pick streams already in the chosen container instead of remuxing. "
                "Faster, but a known cause of HTTP 403 on YouTube.",
                self.strict,
            )
        )

        self.archive = Switch()
        self.archive.toggled.connect(self._on_archive)
        body.addWidget(
            SettingRow(
                "Remember finished downloads",
                "Skip anything already downloaded before",
                self.archive,
            )
        )

        self.notify = Switch()
        self.notify.toggled.connect(self._on_notify)
        body.addWidget(
            SettingRow("Notify on completion", "Show a message when the queue empties", self.notify)
        )

        actions = QHBoxLayout()
        open_config = button("Open settings folder", "outlined", "folder")
        open_config.clicked.connect(self._open_config)
        actions.addWidget(open_config)

        reset = button("Reset to defaults", "text")
        reset.clicked.connect(self._reset)
        actions.addWidget(reset)
        actions.addStretch(1)
        body.addLayout(actions)
        return card

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        self._loading = True
        a, b = self.settings.appearance, self.settings.behaviour

        self.design_chips.set_value(a.design)
        self.theme_chips.set_value(a.theme_mode)
        self.density_chips.set_value(a.density)
        self.radius.setValue(a.corner_radius)
        self.font_size.setValue(a.font_size)
        index = self.font_family.findData(a.font_family)
        if index >= 0:
            self.font_family.setCurrentIndex(index)
        self.animations.setChecked(a.animations, animate=False)
        self.thumbs.setChecked(a.show_thumbnails, animate=False)
        self._sync_swatches()

        self.download_dir.setText(b.download_dir or str(paths.default_download_dir()))
        self.template.setText(b.filename_template)
        self.by_category.setChecked(b.organize_by_category, animate=False)
        self.by_source.setChecked(b.organize_by_source, animate=False)
        self.expand.setChecked(b.expand_playlists, animate=False)
        self.playlist_limit.setValue(b.playlist_limit)
        self.open_folder.setChecked(b.open_folder_on_complete, animate=False)

        self.meta.setChecked(b.embed_metadata, animate=False)
        self.thumb_embed.setChecked(b.embed_thumbnail, animate=False)
        self.chapters.setChecked(b.embed_chapters, animate=False)
        self.embed_subs.setChecked(b.embed_subtitles, animate=False)
        self.write_subs.setChecked(b.write_subtitles, animate=False)
        self.sub_langs.setText(b.subtitle_langs)
        self.sponsors.setChecked(b.skip_sponsors, animate=False)

        self.concurrent.setValue(b.max_concurrent)
        self.rate.setValue(b.rate_limit_kbps)
        self.retries.setValue(b.retries)
        self.proxy.setText(b.proxy)
        index = self.cookies.findData(b.cookies_from_browser)
        if index >= 0:
            self.cookies.setCurrentIndex(index)

        self.ffmpeg.setText(b.ffmpeg_path)
        self.archive.setChecked(b.use_archive, animate=False)
        self.notify.setChecked(b.notify_on_complete, animate=False)

        self.tv_folders.setChecked(b.tv_folders, animate=False)
        self.strict.setChecked(b.strict_container_match, animate=False)
        self.chunk.setValue(b.http_chunk_size_mb)
        self.mirror.setText(self.settings.rezka.mirror)
        self._loading = False

    def _build_swatches(self) -> None:
        """Rebuild the accent row: each design ships its own set of seeds."""
        for swatch in self.swatches:
            self.swatch_row.removeWidget(swatch)
            swatch.deleteLater()
        self.swatches = []

        for index, (name, value) in enumerate(accents_for(self.settings.appearance.design)):
            swatch = Swatch(name, value)
            swatch.picked.connect(self._on_accent)
            self.swatch_row.insertWidget(index, swatch)
            self.swatches.append(swatch)
        self._sync_swatches()

    def _sync_swatches(self) -> None:
        current = self.settings.appearance.seed_color.upper()
        for swatch in self.swatches:
            swatch.set_selected(swatch.value.upper() == current)

    def _on_design(self, value) -> None:
        from ...config import accents_for as _accents, default_seed_for

        self.settings.appearance.design = value
        # Move to that design's default seed unless the current one belongs to it.
        known = {hex_value.upper() for _n, hex_value in _accents(value)}
        if self.settings.appearance.seed_color.upper() not in known:
            self.settings.appearance.seed_color = default_seed_for(value)
        self.settings.appearance.corner_radius = 7 if value == "studio" else 16
        self._build_swatches()
        self._loading = True
        self.radius.setValue(self.settings.appearance.corner_radius)
        self._loading = False
        self.appearanceChanged.emit()

    # -------------------------------------------------------------- handlers

    def _appearance(self, **kwargs) -> None:
        if self._loading:
            return
        for key, value in kwargs.items():
            setattr(self.settings.appearance, key, value)
        self.appearanceChanged.emit()

    def _behaviour(self, **kwargs) -> None:
        if self._loading:
            return
        for key, value in kwargs.items():
            setattr(self.settings.behaviour, key, value)
        self.behaviourChanged.emit()

    def _on_theme_mode(self, value) -> None:
        self._appearance(theme_mode=value)

    def _on_accent(self, value: str) -> None:
        self._appearance(seed_color=value)
        self._sync_swatches()

    def _pick_custom_accent(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        initial = QColor(self.settings.appearance.seed_color)
        chosen = QColorDialog.getColor(initial, self, "Pick an accent colour")
        if chosen.isValid():
            self._on_accent(chosen.name().upper())

    def _on_radius(self, value: int) -> None:
        self._appearance(corner_radius=value)

    def _on_density(self, value) -> None:
        self._appearance(density=value)

    def _on_font_size(self, value: int) -> None:
        self._appearance(font_size=value)

    def _on_font_family(self) -> None:
        self._appearance(font_family=self.font_family.currentData() or "Segoe UI")

    def _on_animations(self, value: bool) -> None:
        self._appearance(animations=value)

    def _on_thumbs(self, value: bool) -> None:
        self._appearance(show_thumbnails=value)

    def _on_dir(self) -> None:
        self._behaviour(download_dir=self.download_dir.text().strip())

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a download folder", self.download_dir.text()
        )
        if chosen:
            self.download_dir.setText(chosen)
            self._on_dir()

    def _on_template(self) -> None:
        self._behaviour(filename_template=self.template.text().strip())

    def _on_by_category(self, value: bool) -> None:
        self._behaviour(organize_by_category=value)

    def _on_by_source(self, value: bool) -> None:
        self._behaviour(organize_by_source=value)

    def _on_expand(self, value: bool) -> None:
        self._behaviour(expand_playlists=value)

    def _on_playlist_limit(self, value: int) -> None:
        self._behaviour(playlist_limit=value)

    def _on_open_folder(self, value: bool) -> None:
        self._behaviour(open_folder_on_complete=value)

    def _on_meta(self, value: bool) -> None:
        self._behaviour(embed_metadata=value)

    def _on_thumb_embed(self, value: bool) -> None:
        self._behaviour(embed_thumbnail=value)

    def _on_chapters(self, value: bool) -> None:
        self._behaviour(embed_chapters=value)

    def _on_embed_subs(self, value: bool) -> None:
        self._behaviour(embed_subtitles=value)

    def _on_write_subs(self, value: bool) -> None:
        self._behaviour(write_subtitles=value)

    def _on_sub_langs(self) -> None:
        self._behaviour(subtitle_langs=self.sub_langs.text().strip())

    def _on_sponsors(self, value: bool) -> None:
        self._behaviour(skip_sponsors=value)

    def _on_concurrent(self, value: int) -> None:
        self._behaviour(max_concurrent=value)

    def _on_rate(self, value: int) -> None:
        self._behaviour(rate_limit_kbps=value)

    def _on_retries(self, value: int) -> None:
        self._behaviour(retries=value)

    def _on_proxy(self) -> None:
        self._behaviour(proxy=self.proxy.text().strip())

    def _on_cookies(self) -> None:
        self._behaviour(cookies_from_browser=self.cookies.currentData() or "")

    def _on_ffmpeg(self) -> None:
        self._behaviour(ffmpeg_path=self.ffmpeg.text().strip())

    def _browse_ffmpeg(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Locate ffmpeg", "", "ffmpeg (ffmpeg.exe);;All files (*)"
        )
        if chosen:
            self.ffmpeg.setText(chosen)
            self._on_ffmpeg()

    def _on_tv_folders(self, value: bool) -> None:
        self._behaviour(tv_folders=value)
        self.settings.rezka.season_folders = value

    def _on_chunk(self, value: int) -> None:
        self._behaviour(http_chunk_size_mb=value)

    def _on_strict(self, value: bool) -> None:
        self._behaviour(strict_container_match=value)

    def _on_mirror(self) -> None:
        if self._loading:
            return
        self.settings.rezka.mirror = self.mirror.text().strip()
        self.behaviourChanged.emit()

    def _on_archive(self, value: bool) -> None:
        self._behaviour(use_archive=value)

    def _on_notify(self, value: bool) -> None:
        self._behaviour(notify_on_complete=value)

    def _open_config(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.config_dir())))

    def _reset(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        confirm = QMessageBox.question(
            self,
            "Reset settings",
            "Restore every setting to its default value?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        from ...config import Appearance, Behaviour, Preset

        self.settings.appearance = Appearance()
        self.settings.behaviour = Behaviour()
        self.settings.preset = Preset()
        self._load()
        self.appearanceChanged.emit()
        self.behaviourChanged.emit()


def _ffmpeg_status(settings: Settings) -> str:
    found = paths.find_ffmpeg(settings.behaviour.ffmpeg_path)
    if found:
        return f"Found at {found}"
    return "Not found. Merging and audio conversion will fail without it."
