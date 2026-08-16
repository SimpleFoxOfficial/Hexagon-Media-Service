"""Main window: navigation rail, view stack and live re-theming."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, logs
from ..config import Settings
from ..core.manager import DownloadManager
from ..core.sources import resolver_for
from ..core.sources.hdrezka import HdRezkaResolver
from . import fonts, icons, theme
from .views.about_view import AboutView
from .views.download_view import DownloadView
from .views.logs_view import LogsView
from .views.queue_view import QueueView
from .views.settings_view import SettingsView
from .widgets import Toast, label

log = logs.get("ui")

NAV_ITEMS = [
    ("download", "Download"),
    ("queue", "Queue"),
    ("settings", "Settings"),
    ("file", "Logs"),
    ("info", "About"),
]


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.manager = DownloadManager(settings, self)
        #: Completion count already announced, so the toast fires once per batch.
        self._notified_for: int | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(980, 680)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.rail = self._build_rail()
        layout.addWidget(self.rail)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.download_view = DownloadView(settings)
        self.queue_view = QueueView(self.manager, settings)
        self.settings_view = SettingsView(settings)
        self.logs_view = LogsView(settings)
        self.about_view = AboutView(settings)

        for view in (
            self.download_view,
            self.queue_view,
            self.settings_view,
            self.logs_view,
            self.about_view,
        ):
            self.stack.addWidget(view)

        self.toast = Toast(root)

        self.download_view.submitted.connect(self._on_submit)
        self.download_view.jobsReady.connect(self._on_jobs_ready)
        self.download_view.message.connect(self._on_message)
        self.download_view.settingsChanged.connect(self._save_soon)
        self.settings_view.appearanceChanged.connect(self._on_appearance_changed)
        self.settings_view.behaviourChanged.connect(self._on_behaviour_changed)

        self.manager.expandStarted.connect(self._on_expand_started)
        self.manager.expandFinished.connect(self._on_expand_finished)
        self.manager.busyMessage.connect(self._on_busy)
        self.manager.statsChanged.connect(self._on_stats)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_now)

        self._install_shortcuts()
        self.apply_theme()
        self._restore_geometry()
        self._select(0)

    # ------------------------------------------------------------------ rail

    def _build_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(theme.current_metrics().nav_w)
        rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(6)

        self.logo_mark = QLabel()
        self.logo_mark.setAlignment(Qt.AlignCenter)
        self.logo_mark.setFixedHeight(44)
        layout.addWidget(self.logo_mark)

        self.logo_text = label("MD", "logo")
        self.logo_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_text)
        layout.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QToolButton] = []

        for index, (icon_name, text) in enumerate(NAV_ITEMS):
            btn = QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(22, 22))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setProperty("_icon_name", icon_name)
            btn.clicked.connect(lambda _=False, i=index: self._select(i))
            self.nav_group.addButton(btn, index)
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

            if index == 1:
                self.queue_badge = label("", "caption")
                self.queue_badge.setAlignment(Qt.AlignCenter)
                layout.addWidget(self.queue_badge)

        layout.addStretch(1)

        self.version_label = label(f"v{__version__}", "caption")
        self.version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.version_label)
        return rail

    def _select(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._select(0))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._select(1))
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self._select(2))
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self._select(3))
        QShortcut(QKeySequence("Ctrl+Return"), self, self.download_view._submit)
        QShortcut(QKeySequence("Ctrl+V"), self.download_view, self.download_view._paste)

    # ----------------------------------------------------------------- theme

    def resolve_dark(self) -> bool:
        mode = self.settings.appearance.theme_mode
        if mode == "dark":
            return True
        if mode == "light":
            return False
        try:
            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            return False

    def apply_theme(self) -> None:
        appearance = self.settings.appearance
        appearance.font_family = fonts.body_family(appearance.font_family)
        appearance.logo_font = fonts.logo_family()

        scheme = theme.build_scheme(
            appearance.seed_color, self.resolve_dark(), appearance.design
        )
        metrics = theme.Metrics.build(appearance)
        theme.set_current(scheme, metrics)
        icons.clear_cache()

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.stylesheet(scheme, metrics, appearance))
            base = QFont(appearance.font_family)
            base.setPointSize(metrics.font_pt)
            app.setFont(base)

        self.rail.setFixedWidth(metrics.nav_w)
        self._refresh_icons(scheme)
        self._refresh_logo(scheme, metrics)
        self.queue_view.refresh_appearance()
        self.download_view.refresh()

    def _refresh_icons(self, scheme) -> None:
        for button in self.nav_buttons:
            name = button.property("_icon_name")
            colour = scheme.on_secondary_container if button.isChecked() else scheme.on_surface_variant
            button.setIcon(icons.icon(name, colour, 22))

        for widget in self.findChildren(QToolButton):
            name = widget.property("_icon_name")
            if not name or widget in self.nav_buttons:
                continue
            variant = widget.property("variant")
            colour = {
                "accent": scheme.primary,
                "danger": scheme.error,
            }.get(variant, scheme.on_surface_variant)
            widget.setIcon(icons.icon(name, colour, 20))

    def _refresh_logo(self, scheme, metrics) -> None:
        self.logo_mark.setPixmap(logo_pixmap(36, scheme, metrics.radius_sm + 4))

        font = QFont(fonts.logo_family())
        font.setPointSize(metrics.font_pt + 4)
        font.setWeight(QFont.Bold)
        self.logo_text.setFont(font)
        self.logo_text.setStyleSheet(f"color:{scheme.primary}; background:transparent;")

        self.setWindowIcon(QIcon(logo_pixmap(64, scheme, 14)))

    def _on_appearance_changed(self) -> None:
        self.apply_theme()
        # Selection state colours the nav icons, so refresh after the switch.
        self._refresh_icons(theme.current())
        self._save_soon()

    def _on_behaviour_changed(self) -> None:
        self.download_view.refresh()
        self._save_soon()

    # -------------------------------------------------------------- download

    def _on_submit(self, urls: list) -> None:
        plain: list[str] = []
        rezka: list[str] = []
        for url in urls:
            if isinstance(resolver_for(url), HdRezkaResolver):
                rezka.append(url)
            else:
                plain.append(url)

        # An HDRezka link needs translation and episode choices, so it goes to
        # its own tab rather than being queued blind.
        if rezka:
            log.info("Routing %d HDRezka link(s) to the HDRezka tab", len(rezka))
            self.download_view.open_rezka(rezka[0])
            if len(rezka) > 1:
                self.toast.show_message(
                    f"Loaded the first HDRezka link. {len(rezka) - 1} more were left in the box.",
                    "info",
                )

        if plain:
            self.manager.add_urls(plain, self.settings.preset)
            self.download_view.clear_input()
            self._select(1)

    def _on_jobs_ready(self, jobs: list) -> None:
        self.manager.add_jobs(list(jobs))
        self._select(1)

    def _on_message(self, text: str, kind: str) -> None:
        self.toast.show_message(text, kind)

    def _on_expand_started(self) -> None:
        self.toast.show_message("Reading links...", "info", 60000)

    def _on_expand_finished(self, error: str) -> None:
        if error:
            self.toast.show_message(f"Some links failed: {error}", "error", 6000)
        else:
            self.toast.show_message("Links added to the queue", "success", 2200)

    def _on_busy(self, message: str) -> None:
        self.toast.show_message(message, "info", 60000)

    def _on_stats(self, stats: dict) -> None:
        pending = stats.get("active", 0) + stats.get("queued", 0)
        self.queue_badge.setText(str(pending) if pending else "")

        title = APP_NAME
        if stats.get("active"):
            title = f"{APP_NAME} - {stats['active']} downloading"
        self.setWindowTitle(title)

        if (
            pending == 0
            and stats.get("done")
            and self.settings.behaviour.notify_on_complete
            and self._notified_for != stats.get("done")
        ):
            self._notified_for = stats.get("done")
            self.toast.show_message(
                f"Finished. {stats['done']} item(s) downloaded.", "success", 4000
            )
            if self.settings.behaviour.open_folder_on_complete:
                from ..core import presets
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices

                target = presets.target_dir(self.settings.behaviour, self.settings.preset)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        elif pending:
            self._notified_for = None

    # ----------------------------------------------------------- persistence

    def _save_soon(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        self.settings.save()

    def _restore_geometry(self) -> None:
        raw = self.settings.window_geometry
        if raw:
            try:
                from PySide6.QtCore import QByteArray

                self.restoreGeometry(QByteArray.fromBase64(raw.encode("ascii")))
                return
            except Exception:
                pass
        self.resize(1120, 760)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast._reposition()

    def closeEvent(self, event) -> None:
        try:
            self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        except Exception:
            self.settings.window_geometry = ""

        if self.settings.behaviour.clear_completed_on_exit:
            self.manager.clear_finished()

        self.settings.save()
        self.manager.shutdown()
        super().closeEvent(event)


def logo_pixmap(size: int, scheme, radius: int) -> QPixmap:
    """The app mark: a rounded tile in the accent colour with a download glyph."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QLinearGradient

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor(scheme.primary))
    gradient.setColorAt(1.0, QColor(scheme.tertiary))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    glyph = icons.icon("download", scheme.on_primary, int(size * 0.62))
    inner = int(size * 0.62)
    glyph.paint(painter, int((size - inner) / 2), int((size - inner) / 2), inner, inner)
    painter.end()
    return pixmap
