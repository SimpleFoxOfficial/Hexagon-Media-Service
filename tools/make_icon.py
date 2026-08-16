"""Generate mediadl/resources/app.ico.

    python tools/make_icon.py

The mark is a strip of film with a download arrow through it, tilted two
degrees clockwise so it does not sit dead square against the interface.

Self-contained on purpose: it draws with QtGui alone rather than importing the
old Qt interface, so removing that interface cannot break the icon build.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIZES = (16, 24, 32, 48, 64, 128, 256)

# Brand green from the interface tokens, on a dark tile.
TILE_TOP = "#1F2329"
TILE_BOTTOM = "#13161A"
FILM = "#E8EAED"
ACCENT = "#09DE78"
TILT_DEGREES = 2.0


def draw(size: int):
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
    )

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing, True)

    # Rounded tile.
    tile = QLinearGradient(0, 0, 0, size)
    tile.setColorAt(0.0, QColor(TILE_TOP))
    tile.setColorAt(1.0, QColor(TILE_BOTTOM))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(tile))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    # Everything inside is drawn on a 24x24 grid, then scaled and tilted.
    p.translate(size / 2.0, size / 2.0)
    p.rotate(TILT_DEGREES)
    p.scale(size / 24.0, size / 24.0)
    p.translate(-12.0, -12.0)

    # Film body.
    body = QRectF(3.0, 4.6, 18.0, 14.8)
    p.setBrush(QColor(FILM))
    p.drawRoundedRect(body, 1.9, 1.9)

    # Sprocket holes along both edges, punched out of the film.
    p.setBrush(QColor(TILE_TOP))
    hole_w, hole_h = 1.7, 1.5
    for i in range(5):
        x = 4.3 + i * 3.35
        p.drawRoundedRect(QRectF(x, 5.5, hole_w, hole_h), 0.45, 0.45)
        p.drawRoundedRect(QRectF(x, 17.0, hole_w, hole_h), 0.45, 0.45)

    # The frame window between the sprockets, so the arrow reads on green.
    window = QRectF(4.6, 8.1, 14.8, 7.8)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(window, 1.1, 1.1)

    # Download arrow through the frame.
    stroke = QPen(QColor(TILE_BOTTOM))
    stroke.setWidthF(1.5)
    stroke.setCapStyle(Qt.RoundCap)
    stroke.setJoinStyle(Qt.RoundJoin)
    p.setPen(stroke)
    p.setBrush(Qt.NoBrush)

    p.drawLine(QPointF(12.0, 9.2), QPointF(12.0, 13.4))
    head = QPainterPath()
    head.moveTo(9.9, 11.5)
    head.lineTo(12.0, 13.7)
    head.lineTo(14.1, 11.5)
    p.drawPath(head)
    p.drawLine(QPointF(9.4, 14.9), QPointF(14.6, 14.9))

    p.end()
    return pixmap


def png_bytes(size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray

    # The QByteArray must outlive the QBuffer wrapping it, or QBuffer writes
    # through a dangling pointer and the process dies without a traceback.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.WriteOnly)
    draw(size).save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def build_ico(images: dict[int, bytes]) -> bytes:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)

    offset = 6 + 16 * count
    entries, blobs = b"", b""
    for size in sorted(images):
        data = images[size]
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # 0 encodes 256
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        blobs += data
        offset += len(data)

    return header + entries + blobs


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication([])  # noqa: F841 - QPixmap needs a live application

    images = {size: png_bytes(size) for size in SIZES}
    target = ROOT / "mediadl" / "resources" / "app.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_ico(images))

    preview = ROOT / "docs" / "icon-preview.png"
    preview.parent.mkdir(exist_ok=True)
    draw(256).save(str(preview), "PNG")

    print(f"Wrote {target} ({target.stat().st_size // 1024} KB, {len(images)} sizes)")
    print(f"Wrote {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
