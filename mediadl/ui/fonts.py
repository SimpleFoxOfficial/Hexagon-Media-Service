"""Application fonts.

Body text uses Segoe UI, which ships with Windows. The logo uses Comfortaa,
which does not, so any .ttf dropped into mediadl/resources/fonts is registered
at startup. When Comfortaa is missing the logo silently falls back to the body
font rather than rendering in a default serif.
"""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase

from .. import paths

LOGO_FAMILY = "Comfortaa"
BODY_FALLBACKS = ("Segoe UI Variable Text", "Segoe UI", "Inter", "Roboto", "sans-serif")

_loaded: list[str] = []


def load_bundled_fonts() -> list[str]:
    """Register every font file under resources/fonts. Returns the families added."""
    global _loaded
    if _loaded:
        return _loaded

    families: list[str] = []
    font_dir = paths.resource("fonts")
    if font_dir.is_dir():
        for path in sorted(font_dir.iterdir()):
            if path.suffix.lower() not in (".ttf", ".otf"):
                continue
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id != -1:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))

    _loaded = sorted(set(families))
    return _loaded


def has_family(family: str) -> bool:
    return family in QFontDatabase.families()


def logo_family() -> str:
    """Comfortaa when available, otherwise the best installed body font."""
    if has_family(LOGO_FAMILY):
        return LOGO_FAMILY
    return body_family()


def body_family(preferred: str = "") -> str:
    if preferred and has_family(preferred):
        return preferred
    for candidate in BODY_FALLBACKS:
        if has_family(candidate):
            return candidate
    # Never hand QFont the generic CSS keyword; it is not a real family.
    return "Segoe UI"
