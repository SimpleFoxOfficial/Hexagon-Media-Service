"""Vector icon set.

Icons are authored here as stroke-based SVG on a 24x24 grid so they can be
tinted to any theme colour at any DPI without shipping image assets. Rendered
results are cached per (name, colour, size).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Each entry is the inner markup of a 24x24 SVG. "CURRENT" is replaced by the
# requested colour at render time.
_SHAPES: dict[str, str] = {
    "download": '<path d="M12 3v11M7.5 10.5 12 15l4.5-4.5M4 20h16"/>',
    "queue": (
        '<path d="M9 6h11M9 12h11M9 18h11"/>'
        '<circle cx="4.5" cy="6" r="1.2" fill="CURRENT" stroke="none"/>'
        '<circle cx="4.5" cy="12" r="1.2" fill="CURRENT" stroke="none"/>'
        '<circle cx="4.5" cy="18" r="1.2" fill="CURRENT" stroke="none"/>'
    ),
    "settings": (
        '<path d="M3.5 7.5h4M12.5 7.5H20.5M3.5 16.5h8.5M17.5 16.5h3"/>'
        '<circle cx="10" cy="7.5" r="2.5"/><circle cx="15" cy="16.5" r="2.5"/>'
    ),
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11.5v5"/>'
    '<circle cx="12" cy="8" r="1.1" fill="CURRENT" stroke="none"/>',
    "play": '<path d="M9 6.2 18 12l-9 5.8z" fill="CURRENT" stroke="CURRENT" stroke-linejoin="round"/>',
    "pause": '<path d="M9.5 6v12M14.5 6v12"/>',
    "close": '<path d="M7 7l10 10M17 7 7 17"/>',
    "retry": '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20.5 3.5v4h-4"/>',
    "folder": '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h3.6l2 2h7.4A1.5 1.5 0 0 1 20 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/>',
    "trash": '<path d="M5 7h14M10 7V5h4v2M7.5 7l.9 12h7.2l.9-12M10.5 10.5v6M13.5 10.5v6"/>',
    "check": '<path d="M5 12.5 9.5 17 19 7.5"/>',
    "alert": '<path d="M12 4 2.8 20h18.4z" stroke-linejoin="round"/><path d="M12 10v4.5"/>'
    '<circle cx="12" cy="17.4" r="1.1" fill="CURRENT" stroke="none"/>',
    "link": (
        '<path d="M10.6 13.4a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 1 0-5.7-5.7l-1 1"/>'
        '<path d="M13.4 10.6a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 1 0 5.7 5.7l1-1"/>'
    ),
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.4 15.4 20 20"/>',
    "chevron_down": '<path d="M6 9.5 12 15.5 18 9.5"/>',
    "chevron_right": '<path d="M9.5 6 15.5 12 9.5 18"/>',
    "copy": '<path d="M9 8.5h9.5a.5.5 0 0 1 .5.5v9.5a.5.5 0 0 1-.5.5H9a.5.5 0 0 1-.5-.5V9a.5.5 0 0 1 .5-.5z"/>'
    '<path d="M5.5 15.5V5.5a1 1 0 0 1 1-1h9"/>',
    "external": '<path d="M14 4.5h5.5V10M19.5 4.5 12 12"/>'
    '<path d="M17 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1H10"/>',
    "music": '<path d="M9 18V6l10-2v12"/><ellipse cx="6.5" cy="18" rx="2.5" ry="2.2"/>'
    '<ellipse cx="16.5" cy="16" rx="2.5" ry="2.2"/>',
    "video": '<path d="M3.5 7.5a1 1 0 0 1 1-1H15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1z"/>'
    '<path d="M16 10.5 20.5 7.5v9L16 13.5z" stroke-linejoin="round"/>',
    "palette": (
        '<path d="M12 3.5c-4.7 0-8.5 3.8-8.5 8.5s3.8 8.5 8.5 8.5a1.9 1.9 0 0 0 1.9-1.9c0-.5-.2-.9-.5-1.3'
        'a1.9 1.9 0 0 1 1.4-3.2h2.2A5 5 0 0 0 22 9.3C21.3 6 17 3.5 12 3.5z"/>'
        '<circle cx="7.5" cy="11" r="1.1" fill="CURRENT" stroke="none"/>'
        '<circle cx="11" cy="7.5" r="1.1" fill="CURRENT" stroke="none"/>'
        '<circle cx="15.5" cy="8.5" r="1.1" fill="CURRENT" stroke="none"/>'
    ),
    "paste": '<path d="M8 5.5H6.5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-12a1 1 0 0 0-1-1H16"/>'
    '<path d="M9 4.2h6v3H9z" stroke-linejoin="round"/>',
    "file": '<path d="M13 4.5H7a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5z"/><path d="M13 4.5v5h5"/>',
    "up": '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>',
    "down": '<path d="M12 5v13M6.5 12.5 12 18l5.5-5.5"/>',
    "moon": '<path d="M20 14.2A8.2 8.2 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6'
    'M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6"/>',
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def _svg(name: str, color: str) -> bytes:
    shape = _SHAPES.get(name, _SHAPES["info"]).replace("CURRENT", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.9" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{shape}</svg>"
    ).encode("utf-8")


def icon(name: str, color: str, size: int = 24) -> QIcon:
    """A themed icon. `color` is any CSS colour string, usually a scheme role."""
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    renderer = QSvgRenderer(_svg(name, color))
    pixmap = QPixmap(QSize(size, size))
    pixmap.setDevicePixelRatio(1.0)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    result = QIcon(pixmap)
    _cache[key] = result
    return result


def clear_cache() -> None:
    """Called when the theme changes so icons pick up the new colours."""
    _cache.clear()


def available() -> list[str]:
    return sorted(_SHAPES)
