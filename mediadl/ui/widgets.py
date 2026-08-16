"""Reusable widgets: cards, switches, chips, thumbnails and toasts."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme


def repolish(widget: QWidget) -> None:
    """Re-apply the style sheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value) -> None:
    widget.setProperty(name, value)
    repolish(widget)


# ------------------------------------------------------------------ containers


class Card(QFrame):
    def __init__(self, tone: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        if tone:
            self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        m = theme.current_metrics()
        layout.setContentsMargins(m.pad, m.pad, m.pad, m.pad)
        layout.setSpacing(m.gap)

    def body(self) -> QVBoxLayout:
        return self.layout()  # type: ignore[return-value]


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


def label(text: str, role: str = "body", parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setProperty("role", role)
    if role in ("body", "caption"):
        widget.setWordWrap(True)
    return widget


def badge(text: str, kind: str = "neutral") -> QLabel:
    widget = QLabel(text)
    widget.setProperty("badge", kind)
    widget.setAlignment(Qt.AlignCenter)
    widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return widget


def button(text: str, variant: str = "filled", icon_name: str = "") -> QPushButton:
    widget = QPushButton(text)
    if variant != "filled":
        widget.setProperty("variant", variant)
    widget.setCursor(Qt.PointingHandCursor)
    if icon_name:
        scheme = theme.current()
        colour = {
            "filled": scheme.on_primary,
            "tonal": scheme.on_secondary_container,
            "danger": scheme.on_error,
        }.get(variant, scheme.primary)
        widget.setIcon(icons.icon(icon_name, colour, 18))
        widget.setIconSize(QSize(18, 18))
    return widget


def tool_button(icon_name: str, tooltip: str, variant: str = "") -> QToolButton:
    widget = QToolButton()
    widget.setToolTip(tooltip)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setAutoRaise(True)
    if variant:
        widget.setProperty("variant", variant)
    scheme = theme.current()
    colour = {"accent": scheme.primary, "danger": scheme.error}.get(
        variant, scheme.on_surface_variant
    )
    widget.setIcon(icons.icon(icon_name, colour, 20))
    widget.setIconSize(QSize(20, 20))
    widget.setProperty("_icon_name", icon_name)
    return widget


class Chip(QPushButton):
    def __init__(self, text: str, value=None, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.value = value if value is not None else text
        self.setProperty("variant", "chip")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class SegmentedTabs(QWidget):
    """A row of exclusive buttons used to switch service panels."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ServiceTabs")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._buttons: list[QToolButton] = []
        for key, text, icon_name in options:
            btn = QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setProperty("_key", key)
            if icon_name:
                btn.setProperty("_icon_name", icon_name)
                btn.setIcon(icons.icon(icon_name, theme.current().on_surface_variant, 16))
                btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda _=False, b=btn: self._select(b, emit=True))
            layout.addWidget(btn)
            self._buttons.append(btn)

    def _select(self, chosen: QToolButton, emit: bool) -> None:
        scheme = theme.current()
        for btn in self._buttons:
            active = btn is chosen
            btn.setChecked(active)
            name = btn.property("_icon_name")
            if name:
                colour = scheme.primary if active else scheme.on_surface_variant
                btn.setIcon(icons.icon(name, colour, 16))
        if emit:
            self.changed.emit(str(chosen.property("_key")))

    def set_value(self, key: str) -> None:
        for btn in self._buttons:
            if btn.property("_key") == key:
                self._select(btn, emit=False)
                return
        if self._buttons:
            self._select(self._buttons[0], emit=False)

    def value(self) -> str:
        for btn in self._buttons:
            if btn.isChecked():
                return str(btn.property("_key"))
        return ""

    def refresh_icons(self) -> None:
        for btn in self._buttons:
            if btn.isChecked():
                self._select(btn, emit=False)
                return


class ChipGroup(QWidget):
    """A row of mutually exclusive chips, used instead of radio buttons."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[str, object]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._chips: list[Chip] = []
        for text, value in options:
            chip = Chip(text, value)
            chip.clicked.connect(lambda _=False, c=chip: self._select(c, emit=True))
            layout.addWidget(chip)
            self._chips.append(chip)
        layout.addStretch(1)

    def _select(self, chosen: Chip, emit: bool) -> None:
        for chip in self._chips:
            chip.setChecked(chip is chosen)
        if emit:
            self.changed.emit(chosen.value)

    def set_value(self, value) -> None:
        for chip in self._chips:
            if chip.value == value:
                self._select(chip, emit=False)
                return
        if self._chips:
            self._select(self._chips[0], emit=False)

    def value(self):
        for chip in self._chips:
            if chip.isChecked():
                return chip.value
        return None


# --------------------------------------------------------------------- switch


class Switch(QWidget):
    """A Material-style toggle. Qt has no native one."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self.setFixedSize(46, 28)
        self.setCursor(Qt.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"handle_pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_handle_pos(self) -> float:
        return self._pos

    def set_handle_pos(self, value: float) -> None:
        self._pos = value
        self.update()

    handle_pos = Property(float, get_handle_pos, set_handle_pos)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool, animate: bool = True) -> None:
        value = bool(value)
        if value == self._checked:
            return
        self._checked = value
        target = 1.0 if value else 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.set_handle_pos(target)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        scheme = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        track = QRectF(2, 5, self.width() - 4, self.height() - 10)
        on, off = QColor(scheme.primary), QColor(scheme.surface_variant)
        blend = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(blend)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        radius = 9.0
        travel = self.width() - 4 - radius * 2 - 4
        cx = 4 + radius + travel * self._pos
        painter.setBrush(QColor(scheme.on_primary if self._checked else scheme.outline))
        painter.drawEllipse(QRectF(cx - radius, self.height() / 2 - radius, radius * 2, radius * 2))
        painter.end()


class SettingRow(QWidget):
    """Title, description and a control on the right."""

    def __init__(
        self,
        title: str,
        description: str = "",
        control: QWidget | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(16)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title, "body"))
        if description:
            text.addWidget(label(description, "caption"))
        layout.addLayout(text, 1)

        if control is not None:
            control.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.control = control


# ----------------------------------------------------------------- thumbnails


class _FetchTask(QRunnable):
    def __init__(self, url: str, sink):
        super().__init__()
        self.url = url
        self.sink = sink

    def run(self) -> None:
        data = b""
        try:
            import requests

            response = requests.get(self.url, timeout=12)
            if response.ok and len(response.content) < 8_000_000:
                data = response.content
        except Exception:
            data = b""
        self.sink.deliver(self.url, data)


class _ThumbnailSink(QWidget):
    arrived = Signal(str, bytes)

    def deliver(self, url: str, data: bytes) -> None:
        self.arrived.emit(url, data)


class Thumbnail(QLabel):
    """Rounded thumbnail that loads its image off the GUI thread."""

    _cache: dict[str, QPixmap] = {}
    _pool = QThreadPool()

    def __init__(self, width: int = 108, height: int = 62, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Thumb")
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignCenter)
        self._url = ""
        self._sink = _ThumbnailSink(self)
        self._sink.arrived.connect(self._on_arrived)
        self._placeholder()

    def _placeholder(self) -> None:
        scheme = theme.current()
        self.setPixmap(icons.icon("video", scheme.on_surface_variant, 26).pixmap(26, 26))

    def set_url(self, url: str) -> None:
        if not url or url == self._url:
            return
        self._url = url
        cached = Thumbnail._cache.get(url)
        if cached is not None:
            self._apply(cached)
            return
        Thumbnail._pool.start(_FetchTask(url, self._sink))

    def _on_arrived(self, url: str, data: bytes) -> None:
        if not data or url != self._url:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        if len(Thumbnail._cache) > 200:
            Thumbnail._cache.clear()
        Thumbnail._cache[url] = pixmap
        self._apply(pixmap)

    def _apply(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        rounded = QPixmap(self.size())
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        radius = max(4, theme.current_metrics().radius_sm)
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)
        painter.setClipPath(path)
        offset_x = (self.width() - scaled.width()) // 2
        offset_y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(offset_x, offset_y, scaled)
        painter.end()

        self.setPixmap(rounded)


# --------------------------------------------------------------------- toasts


class Toast(QWidget):
    """Transient message anchored to the bottom of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(180)
        # Connected once. QAbstractAnimation.stop() does not emit finished, so
        # connecting per fade-out would leave a stale slot that fires at the end
        # of the next fade-in and hides a toast the moment it appears.
        self._fade.finished.connect(self._on_fade_done)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)
        self.hide()

    def show_message(self, text: str, kind: str = "info", msec: int = 3200) -> None:
        scheme = theme.current()
        background, foreground = {
            "info": (scheme.inverse_surface, scheme.inverse_on_surface),
            "success": (scheme.success_container, scheme.on_success_container),
            "error": (scheme.error_container, scheme.on_error_container),
        }.get(kind, (scheme.inverse_surface, scheme.inverse_on_surface))

        radius = theme.current_metrics().radius_sm + 4
        self.setStyleSheet(f"background:{background}; border-radius:{radius}px;")
        self._label.setStyleSheet(f"color:{foreground}; background:transparent;")
        self._label.setText(text)

        self.adjustSize()
        self.setFixedWidth(min(max(320, self.sizeHint().width()), self.parent().width() - 80))
        self._reposition()

        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(msec)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        self.move(max(20, x), parent.height() - self.height() - 28)

    def _hide(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_done(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()
