"""Application bootstrap."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, logs
from .config import Settings
from .ui import fonts
from .ui.main_window import MainWindow


def _set_windows_app_id() -> None:
    """Give the app its own taskbar identity instead of grouping under python.exe."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"Simplefox.{APP_ID}.{APP_NAME.replace(' ', '')}.1"
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _set_windows_app_id()

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setStyle("Fusion")

    fonts.load_bundled_fonts()

    settings = Settings.load()

    logs.setup(settings.behaviour.verbose_logging)
    startup = logs.get("app")
    for name, version in logs.describe_environment():
        startup.info("%s: %s", name, version)

    # A crash in a Qt slot otherwise vanishes with no trace at all.
    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logs.exception(startup, "Unhandled exception", exc)

    sys.excepthook = _hook

    window = MainWindow(settings)

    # Follow the OS light/dark switch while "Follow Windows" is selected.
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _scheme: window.apply_theme()
            if settings.appearance.theme_mode == "system"
            else None
        )
    except (AttributeError, RuntimeError):
        pass

    window.show()

    # Anything passed on the command line is treated as a link to queue.
    links = [arg for arg in argv[1:] if arg.startswith(("http://", "https://"))]
    if links:
        window.download_view.input.setPlainText("\n".join(links))
        window._select(0)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
