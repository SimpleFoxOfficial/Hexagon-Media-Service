"""About screen: identity, capabilities and where things live on disk."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ... import __version__, paths
from ...config import Settings
from .. import fonts, theme
from ..widgets import Card, button, label

SOURCES = [
    ("YouTube", "Videos, playlists, channels, live archives, YouTube Music"),
    ("HDRezka", "Films and series, with translator, season and episode picking"),
    ("Reddit", "v.redd.it posts including the separate audio track"),
    ("Twitter / X", "Videos and GIFs from posts"),
    ("Everything else", "Around 1800 sites handled by yt-dlp, including Vimeo, "
     "SoundCloud, Twitch, TikTok, Instagram and Bandcamp"),
]


class AboutView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings

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

        layout.addWidget(self._identity_card())
        layout.addWidget(self._sources_card())
        layout.addWidget(self._locations_card())
        layout.addWidget(self._versions_card())
        layout.addStretch(1)

    def _identity_card(self) -> Card:
        card = Card("accent")
        body = card.body()

        logo = label("Media Downloader", "logo")
        logo.setFont(_logo_font())
        body.addWidget(logo)

        body.addWidget(
            label(
                "A private, offline-first downloader. Nothing is uploaded, "
                "no account is needed, and every setting lives on this machine.",
                "body",
            )
        )
        body.addWidget(label(f"Version {__version__}", "caption"))
        return card

    def _sources_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Where it can download from", "title"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        for row, (name, description) in enumerate(SOURCES):
            name_label = label(name, "body")
            name_label.setStyleSheet(f"color:{theme.current().primary}; font-weight:600;")
            grid.addWidget(name_label, row, 0, Qt.AlignTop)
            grid.addWidget(label(description, "caption"), row, 1)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)
        return card

    def _locations_card(self) -> Card:
        card = Card()
        body = card.body()
        body.addWidget(label("Files and folders", "title"))

        rows = [
            ("Downloads", str(self.settings.behaviour.resolved_download_dir())),
            ("Settings", str(paths.settings_file())),
            ("History", str(paths.history_file())),
            ("Download archive", str(paths.archive_file())),
        ]
        for name, value in rows:
            row = QHBoxLayout()
            title = label(name, "body")
            title.setMinimumWidth(150)
            row.addWidget(title)
            path_label = label(value, "caption")
            path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(path_label, 1)
            body.addLayout(row)

        actions = QHBoxLayout()
        open_downloads = button("Open downloads folder", "tonal", "folder")
        open_downloads.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.settings.behaviour.resolved_download_dir()))
            )
        )
        actions.addWidget(open_downloads)

        open_config = button("Open settings folder", "outlined", "folder")
        open_config.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.config_dir())))
        )
        actions.addWidget(open_config)
        actions.addStretch(1)
        body.addLayout(actions)
        return card

    def _versions_card(self) -> Card:
        card = Card("flat")
        body = card.body()
        body.addWidget(label("Built on", "title"))
        for name, version in _component_versions():
            row = QHBoxLayout()
            name_label = label(name, "body")
            name_label.setMinimumWidth(150)
            row.addWidget(name_label)
            row.addWidget(label(version, "caption"), 1)
            body.addLayout(row)
        return card


def _logo_font():
    from PySide6.QtGui import QFont

    font = QFont(fonts.logo_family())
    font.setPointSize(theme.current_metrics().font_pt + 12)
    font.setWeight(QFont.Bold)
    return font


def _component_versions() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    try:
        import yt_dlp

        rows.append(("yt-dlp", getattr(yt_dlp.version, "__version__", "unknown")))
    except Exception:
        rows.append(("yt-dlp", "not installed"))

    try:
        import HdRezkaApi

        rows.append(("HdRezkaApi", getattr(HdRezkaApi, "__version__", "installed")))
    except Exception:
        rows.append(("HdRezkaApi", "not installed"))

    try:
        import mutagen

        rows.append(("mutagen", mutagen.version_string))
    except Exception:
        rows.append(("mutagen", "not installed"))

    try:
        from PySide6 import __version__ as pyside_version

        rows.append(("PySide6 / Qt", pyside_version))
    except Exception:
        pass

    ffmpeg = paths.find_ffmpeg("")
    rows.append(("ffmpeg", str(ffmpeg) if ffmpeg else "not found"))

    import sys

    rows.append(("Python", sys.version.split()[0]))
    return rows
