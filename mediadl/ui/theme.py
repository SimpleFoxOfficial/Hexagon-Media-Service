"""Material 3 scheme generation and the Qt style sheet built from it."""

from __future__ import annotations

from dataclasses import dataclass, fields

from ..config import Appearance
from .color import TonalPalette, mix, with_alpha

# Chroma constants, expressed in OkLab chroma. Material specifies these in HCT
# chroma (16 secondary, 24 tertiary, 4 neutral, 8 neutral-variant); these are
# the OkLab equivalents for the same visual weight.
CHROMA_SECONDARY = 0.048
CHROMA_TERTIARY = 0.070
CHROMA_NEUTRAL = 0.008
CHROMA_NEUTRAL_VARIANT = 0.020
CHROMA_ERROR = 0.190
HUE_ERROR = 27.0
HUE_SUCCESS = 150.0
CHROMA_SUCCESS = 0.130

# Keep vibrancy even if the user picks a muted seed.
MIN_PRIMARY_CHROMA = 0.110


@dataclass(frozen=True)
class Scheme:
    """A full Material 3 colour role set, all values as #RRGGBB."""

    dark: bool

    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str

    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str

    tertiary: str
    on_tertiary: str
    tertiary_container: str
    on_tertiary_container: str

    error: str
    on_error: str
    error_container: str
    on_error_container: str

    success: str
    on_success: str
    success_container: str
    on_success_container: str

    background: str
    on_background: str
    surface: str
    on_surface: str
    surface_variant: str
    on_surface_variant: str
    surface_dim: str
    surface_bright: str
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str

    outline: str
    outline_variant: str
    inverse_surface: str
    inverse_on_surface: str
    inverse_primary: str
    scrim: str

    def as_dict(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "dark"}


# ---------------------------------------------------------------- studio design
#
# Matches the sibling Modpack-Utility app: flat neutral surfaces, a muted
# accent, thin dividers. The greys are taken from its theme directly rather
# than generated, because they are deliberately chosen neutrals.

STUDIO_SURFACES = {
    True: {  # dark
        "background": "#121212",
        "surface": "#121212",
        "paper": "#1A1A1A",
        "raised": "#202020",
        "high": "#262626",
        "on": "#E8E8E6",
        "on_muted": "#A3A39E",
        "outline": "#3A3A3A",
        "outline_variant": "#2A2A2A",
    },
    False: {  # light
        "background": "#F4F4F3",
        "surface": "#F4F4F3",
        "paper": "#FFFFFF",
        "raised": "#FAFAF9",
        "high": "#ECECEA",
        "on": "#151514",
        "on_muted": "#5C5B57",
        "outline": "#C9C8C4",
        "outline_variant": "#E2E1DD",
    },
}

# Chroma ceiling that keeps a seed looking restrained rather than saturated.
STUDIO_CHROMA = 0.075
STUDIO_TONE_LIGHT = 42
STUDIO_TONE_DARK = 72


def _studio_scheme(seed: str, dark: bool) -> Scheme:
    base = TonalPalette.from_hex(seed)
    accent = TonalPalette(base.hue, min(base.chroma, STUDIO_CHROMA))
    tone = STUDIO_TONE_DARK if dark else STUDIO_TONE_LIGHT

    s = STUDIO_SURFACES[dark]
    primary = accent(tone)
    container = accent(28 if dark else 90)
    on_container = accent(92 if dark else 18)

    error_pal = TonalPalette(HUE_ERROR, 0.11)
    success_pal = TonalPalette(HUE_SUCCESS, 0.085)
    neutral_accent = TonalPalette(base.hue, 0.012)

    return Scheme(
        dark=dark,
        primary=primary,
        on_primary=s["paper"] if dark else "#FFFFFF",
        primary_container=container,
        on_primary_container=on_container,
        secondary=s["on_muted"],
        on_secondary=s["paper"],
        secondary_container=neutral_accent(26 if dark else 90),
        on_secondary_container=neutral_accent(92 if dark else 20),
        tertiary=primary,
        on_tertiary=s["paper"],
        tertiary_container=container,
        on_tertiary_container=on_container,
        error=error_pal(72 if dark else 42),
        on_error="#FFFFFF",
        error_container=error_pal(26 if dark else 90),
        on_error_container=error_pal(92 if dark else 20),
        success=success_pal(70 if dark else 40),
        on_success="#FFFFFF",
        success_container=success_pal(24 if dark else 90),
        on_success_container=success_pal(92 if dark else 18),
        background=s["background"],
        on_background=s["on"],
        surface=s["surface"],
        on_surface=s["on"],
        surface_variant=s["high"],
        on_surface_variant=s["on_muted"],
        surface_dim=s["background"],
        surface_bright=s["high"],
        surface_container_lowest=s["background"],
        surface_container_low=s["paper"],
        surface_container=s["paper"],
        surface_container_high=s["raised"],
        surface_container_highest=s["high"],
        outline=s["outline"],
        outline_variant=s["outline_variant"],
        inverse_surface=s["on"],
        inverse_on_surface=s["background"],
        inverse_primary=accent(STUDIO_TONE_LIGHT if dark else STUDIO_TONE_DARK),
        scrim="#000000",
    )


def build_scheme(seed: str, dark: bool, design: str = "studio") -> Scheme:
    """Generate the colour roles for a seed. `design` picks the visual language."""
    if design != "vibrant":
        return _studio_scheme(seed, dark)
    return _material_scheme(seed, dark)


def _material_scheme(seed: str, dark: bool) -> Scheme:
    primary_pal = TonalPalette.from_hex(seed)
    primary_pal = TonalPalette(primary_pal.hue, max(primary_pal.chroma, MIN_PRIMARY_CHROMA))

    hue = primary_pal.hue
    secondary_pal = TonalPalette(hue, CHROMA_SECONDARY)
    tertiary_pal = TonalPalette((hue + 60.0) % 360.0, CHROMA_TERTIARY)
    neutral_pal = TonalPalette(hue, CHROMA_NEUTRAL)
    variant_pal = TonalPalette(hue, CHROMA_NEUTRAL_VARIANT)
    error_pal = TonalPalette(HUE_ERROR, CHROMA_ERROR)
    success_pal = TonalPalette(HUE_SUCCESS, CHROMA_SUCCESS)

    if dark:
        return Scheme(
            dark=True,
            primary=primary_pal(80),
            on_primary=primary_pal(20),
            primary_container=primary_pal(30),
            on_primary_container=primary_pal(90),
            secondary=secondary_pal(80),
            on_secondary=secondary_pal(20),
            secondary_container=secondary_pal(30),
            on_secondary_container=secondary_pal(90),
            tertiary=tertiary_pal(80),
            on_tertiary=tertiary_pal(20),
            tertiary_container=tertiary_pal(30),
            on_tertiary_container=tertiary_pal(90),
            error=error_pal(80),
            on_error=error_pal(20),
            error_container=error_pal(30),
            on_error_container=error_pal(90),
            success=success_pal(80),
            on_success=success_pal(20),
            success_container=success_pal(30),
            on_success_container=success_pal(90),
            background=neutral_pal(6),
            on_background=neutral_pal(90),
            surface=neutral_pal(6),
            on_surface=neutral_pal(90),
            surface_variant=variant_pal(30),
            on_surface_variant=variant_pal(80),
            surface_dim=neutral_pal(6),
            surface_bright=neutral_pal(24),
            surface_container_lowest=neutral_pal(4),
            surface_container_low=neutral_pal(10),
            surface_container=neutral_pal(12),
            surface_container_high=neutral_pal(17),
            surface_container_highest=neutral_pal(22),
            outline=variant_pal(60),
            outline_variant=variant_pal(30),
            inverse_surface=neutral_pal(90),
            inverse_on_surface=neutral_pal(20),
            inverse_primary=primary_pal(40),
            scrim="#000000",
        )

    return Scheme(
        dark=False,
        primary=primary_pal(40),
        on_primary=primary_pal(100),
        primary_container=primary_pal(90),
        on_primary_container=primary_pal(10),
        secondary=secondary_pal(40),
        on_secondary=secondary_pal(100),
        secondary_container=secondary_pal(90),
        on_secondary_container=secondary_pal(10),
        tertiary=tertiary_pal(40),
        on_tertiary=tertiary_pal(100),
        tertiary_container=tertiary_pal(90),
        on_tertiary_container=tertiary_pal(10),
        error=error_pal(40),
        on_error=error_pal(100),
        error_container=error_pal(90),
        on_error_container=error_pal(10),
        success=success_pal(40),
        on_success=success_pal(100),
        success_container=success_pal(90),
        on_success_container=success_pal(10),
        background=neutral_pal(98),
        on_background=neutral_pal(10),
        surface=neutral_pal(98),
        on_surface=neutral_pal(10),
        surface_variant=variant_pal(90),
        on_surface_variant=variant_pal(30),
        surface_dim=neutral_pal(87),
        surface_bright=neutral_pal(98),
        surface_container_lowest=neutral_pal(100),
        surface_container_low=neutral_pal(96),
        surface_container=neutral_pal(94),
        surface_container_high=neutral_pal(92),
        surface_container_highest=neutral_pal(90),
        outline=variant_pal(50),
        outline_variant=variant_pal(80),
        inverse_surface=neutral_pal(20),
        inverse_on_surface=neutral_pal(95),
        inverse_primary=primary_pal(80),
        scrim="#000000",
    )


_CURRENT: Scheme | None = None
_CURRENT_METRICS: "Metrics | None" = None


def set_current(scheme: Scheme, metrics: "Metrics") -> None:
    """Publish the active theme for widgets that paint themselves."""
    global _CURRENT, _CURRENT_METRICS
    _CURRENT, _CURRENT_METRICS = scheme, metrics


def current() -> Scheme:
    return _CURRENT if _CURRENT is not None else build_scheme("#7C4DFF", False)


def current_metrics() -> "Metrics":
    return _CURRENT_METRICS if _CURRENT_METRICS is not None else Metrics.build(Appearance())


@dataclass(frozen=True)
class Metrics:
    """Sizes derived from the design, density and corner-radius settings."""

    radius: int
    radius_sm: int
    radius_lg: int
    control_h: int
    field_h: int
    gap: int
    pad: int
    nav_w: int
    font_pt: int
    design: str = "studio"
    button_radius: int = 7
    chip_radius: int = 5
    progress_h: int = 5

    @classmethod
    def build(cls, appearance: Appearance) -> "Metrics":
        compact = appearance.density == "compact"
        studio = appearance.design != "vibrant"
        radius = max(0, min(28, appearance.corner_radius))

        control_h = (32 if compact else 36) if studio else (36 if compact else 44)
        field_h = (34 if compact else 38) if studio else (44 if compact else 52)

        return cls(
            radius=radius,
            radius_sm=max(0, radius // 2) if not studio else max(3, radius - 2),
            radius_lg=min(32, radius + 8) if not studio else radius,
            control_h=control_h,
            field_h=field_h,
            gap=8 if compact else 12,
            pad=12 if compact else 16,
            nav_w=76 if compact else 88,
            font_pt=max(8, min(16, appearance.font_size)),
            design="studio" if studio else "vibrant",
            # Vibrant uses pill-shaped buttons; studio keeps one small radius.
            button_radius=radius if studio else min(control_h // 2, radius + 8),
            chip_radius=max(3, radius - 2) if studio else 16,
            progress_h=5 if studio else 8,
        )


def stylesheet(scheme: Scheme, metrics: Metrics, appearance: Appearance) -> str:
    """Render the whole application style sheet for a scheme."""
    c = scheme
    m = metrics

    # State layers, per Material's 8%/12%/16% opacity guidance.
    hover_on_primary = with_alpha(c.on_primary, 0.10)
    press_on_primary = with_alpha(c.on_primary, 0.18)
    hover_on_surface = with_alpha(c.on_surface, 0.06)
    press_on_surface = with_alpha(c.on_surface, 0.12)
    hover_primary = with_alpha(c.primary, 0.10)
    press_primary = with_alpha(c.primary, 0.18)
    disabled_fg = with_alpha(c.on_surface, 0.38)
    disabled_bg = with_alpha(c.on_surface, 0.12)

    # Studio inputs sit slightly recessed against the card; vibrant fills them.
    studio = m.design == "studio"
    field_bg = c.surface_container_lowest if studio else c.surface_container_highest

    font = appearance.font_family or "Segoe UI"

    return f"""
/* ---------------------------------------------------------------- base */
QWidget {{
    background: transparent;
    color: {c.on_surface};
    font-family: "{font}", "Segoe UI", sans-serif;
    font-size: {m.font_pt}pt;
}}
QMainWindow, QDialog, #Root {{
    background: {c.background};
}}
QWidget:disabled {{
    color: {disabled_fg};
}}

/* ------------------------------------------------------------ typography */
QLabel[role="display"] {{
    font-size: {m.font_pt + 14}pt;
    font-weight: 600;
    color: {c.on_surface};
}}
QLabel[role="headline"] {{
    font-size: {m.font_pt + 7}pt;
    font-weight: 600;
    color: {c.on_surface};
}}
QLabel[role="title"] {{
    font-size: {m.font_pt + 2}pt;
    font-weight: 600;
    color: {c.on_surface};
}}
QLabel[role="body"] {{
    color: {c.on_surface};
}}
QLabel[role="caption"] {{
    font-size: {max(7, m.font_pt - 1)}pt;
    color: {c.on_surface_variant};
}}
QLabel[role="logo"] {{
    font-family: "{appearance.logo_font}", "{font}", sans-serif;
    font-size: {m.font_pt + 8}pt;
    font-weight: 700;
    color: {c.primary};
}}
QLabel[role="error"] {{
    color: {c.error};
}}

/* ----------------------------------------------------------------- cards */
#Card {{
    background: {c.surface_container_low};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius}px;
}}
#Card[tone="elevated"] {{
    background: {c.surface_container};
    border: 1px solid transparent;
}}
#Card[tone="accent"] {{
    background: {c.primary_container};
    border: 1px solid transparent;
}}
#Card[tone="flat"] {{
    background: transparent;
    border: 1px solid {c.outline_variant};
}}
#Divider {{
    background: {c.outline_variant};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* --------------------------------------------------------------- buttons */
QPushButton {{
    background: {c.primary};
    color: {c.on_primary};
    border: none;
    border-radius: {m.button_radius}px;
    padding: 0 18px;
    min-height: {m.control_h}px;
    font-weight: 500;
}}
QPushButton:hover  {{ background: {mix(c.primary, c.on_primary, 0.10)}; }}
QPushButton:pressed {{ background: {mix(c.primary, c.on_primary, 0.20)}; }}
QPushButton:disabled {{ background: {disabled_bg}; color: {disabled_fg}; }}

QPushButton[variant="tonal"] {{
    background: {c.secondary_container};
    color: {c.on_secondary_container};
}}
QPushButton[variant="tonal"]:hover {{ background: {mix(c.secondary_container, c.on_secondary_container, 0.10)}; }}
QPushButton[variant="tonal"]:pressed {{ background: {mix(c.secondary_container, c.on_secondary_container, 0.20)}; }}

QPushButton[variant="outlined"] {{
    background: transparent;
    color: {c.primary};
    border: 1px solid {c.outline};
}}
QPushButton[variant="outlined"]:hover {{ background: {hover_primary}; }}
QPushButton[variant="outlined"]:pressed {{ background: {press_primary}; }}
QPushButton[variant="outlined"]:disabled {{ background: transparent; border-color: {disabled_bg}; }}

QPushButton[variant="text"] {{
    background: transparent;
    color: {c.primary};
    padding: 0 14px;
}}
QPushButton[variant="text"]:hover {{ background: {hover_primary}; }}
QPushButton[variant="text"]:pressed {{ background: {press_primary}; }}
QPushButton[variant="text"]:disabled {{ background: transparent; }}

QPushButton[variant="danger"] {{
    background: {c.error};
    color: {c.on_error};
}}
QPushButton[variant="danger"]:hover {{ background: {mix(c.error, c.on_error, 0.12)}; }}

/* Small square icon buttons */
QToolButton {{
    background: transparent;
    color: {c.on_surface_variant};
    border: none;
    border-radius: {m.radius_sm + 4}px;
    padding: 6px;
}}
QToolButton:hover  {{ background: {hover_on_surface}; color: {c.on_surface}; }}
QToolButton:pressed {{ background: {press_on_surface}; }}
QToolButton:disabled {{ color: {disabled_fg}; }}
QToolButton[variant="accent"] {{ color: {c.primary}; }}
QToolButton[variant="danger"]:hover {{ background: {with_alpha(c.error, 0.12)}; color: {c.error}; }}

/* ------------------------------------------------------------- nav rail */
#NavRail {{
    background: {c.surface_container};
    border: none;
}}
#NavRail QToolButton {{
    background: transparent;
    color: {c.on_surface_variant};
    border-radius: {m.radius}px;
    padding: 10px 4px;
    font-size: {max(7, m.font_pt - 2)}pt;
    font-weight: 600;
}}
#NavRail QToolButton:hover {{ background: {hover_on_surface}; }}
#NavRail QToolButton:checked {{
    background: {c.secondary_container};
    color: {c.on_secondary_container};
}}

/* ----------------------------------------------------------- text fields */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {field_bg};
    color: {c.on_surface};
    border: 1px solid {c.outline};
    border-radius: {m.radius_sm}px;
    padding: 0 12px;
    min-height: {m.field_h}px;
    selection-background-color: {c.primary};
    selection-color: {c.on_primary};
}}
QPlainTextEdit, QTextEdit {{
    padding: 10px 12px;
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
    border-color: {c.on_surface_variant};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {c.primary};
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{
    background: {disabled_bg};
    border-color: {c.outline_variant};
}}

/* ------------------------------------------------------------- combo box */
QComboBox {{
    background: {c.surface_container_highest};
    color: {c.on_surface};
    border: 1px solid {c.outline};
    border-radius: {m.radius_sm}px;
    padding: 0 12px;
    min-height: {m.control_h}px;
}}
QComboBox:hover {{ background: {mix(c.surface_container_highest, c.on_surface, 0.05)}; }}
QComboBox:focus {{ border: 2px solid {c.primary}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c.on_surface_variant};
    width: 0; height: 0;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {c.surface_container_high};
    color: {c.on_surface};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius_sm}px;
    padding: 6px;
    outline: none;
    selection-background-color: {c.secondary_container};
    selection-color: {c.on_secondary_container};
}}

/* -------------------------------------------------------------- spin box */
QSpinBox, QDoubleSpinBox {{
    background: {c.surface_container_highest};
    color: {c.on_surface};
    border: 1px solid {c.outline};
    border-radius: {m.radius_sm}px;
    padding: 0 8px;
    min-height: {m.control_h}px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 2px solid {c.primary}; }}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {c.on_surface_variant};
    width: 0; height: 0;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c.on_surface_variant};
    width: 0; height: 0;
}}

/* ---------------------------------------------------------------- chips */
QPushButton[variant="chip"] {{
    background: transparent;
    color: {c.on_surface_variant};
    border: 1px solid {c.outline};
    border-radius: {m.chip_radius}px;
    padding: 0 14px;
    min-height: 28px;
    font-weight: 500;
}}
QPushButton[variant="chip"]:hover {{ background: {hover_on_surface}; }}
QPushButton[variant="chip"]:checked {{
    background: {c.secondary_container};
    color: {c.on_secondary_container};
    border-color: transparent;
}}

/* ------------------------------------------------------ checks & radios */
QCheckBox, QRadioButton {{
    spacing: 10px;
    color: {c.on_surface};
    background: transparent;
    padding: 4px 0;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 2px solid {c.on_surface_variant};
    background: transparent;
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c.primary}; }}
QCheckBox::indicator:checked {{
    background: {c.primary};
    border-color: {c.primary};
    image: none;
}}
QRadioButton::indicator:checked {{
    background: {c.surface};
    border: 5px solid {c.primary};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {disabled_fg}; }}

/* --------------------------------------------------------------- slider */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.surface_variant};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c.primary};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c.primary};
    width: 16px;
    height: 16px;
    margin: -7px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {mix(c.primary, c.on_surface, 0.15)}; }}

/* ------------------------------------------------------------- progress */
QProgressBar {{
    background: {c.surface_variant};
    border: none;
    border-radius: {m.progress_h // 2}px;
    height: {m.progress_h}px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {c.primary};
    border-radius: {m.progress_h // 2}px;
}}
QProgressBar[state="error"]::chunk {{ background: {c.error}; }}
QProgressBar[state="done"]::chunk  {{ background: {c.success}; }}
QProgressBar[state="paused"]::chunk {{ background: {c.on_surface_variant}; }}

/* --------------------------------------------------------------- scroll */
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {with_alpha(c.on_surface, 0.22)};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {with_alpha(c.on_surface, 0.38)}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {with_alpha(c.on_surface, 0.22)};
    border-radius: 4px;
    min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---------------------------------------------------------- group boxes */
QGroupBox {{
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius}px;
    margin-top: 14px;
    padding: {m.pad}px;
    background: {c.surface_container_low};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {m.pad}px;
    padding: 0 6px;
    color: {c.primary};
    font-weight: 600;
}}

/* ---------------------------------------------------- menus and tooltips */
QMenu {{
    background: {c.surface_container_high};
    color: {c.on_surface};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius_sm}px;
    padding: 6px;
}}
QMenu::item {{ padding: 8px 22px; border-radius: {max(4, m.radius_sm - 2)}px; }}
QMenu::item:selected {{ background: {c.secondary_container}; color: {c.on_secondary_container}; }}
QMenu::separator {{ height: 1px; background: {c.outline_variant}; margin: 6px 4px; }}

QToolTip {{
    background: {c.inverse_surface};
    color: {c.inverse_on_surface};
    border: none;
    border-radius: {m.radius_sm}px;
    padding: 6px 10px;
}}

/* ------------------------------------------------------------ job cards */
#JobCard {{
    background: {c.surface_container_low};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius}px;
}}
#JobCard[state="running"] {{ border-color: {c.primary}; background: {c.surface_container}; }}
#JobCard[state="done"]    {{ border-color: {with_alpha(c.success, 0.55)}; }}
#JobCard[state="error"]   {{ border-color: {c.error}; background: {mix(c.surface_container_low, c.error_container, 0.35)}; }}
#JobCard #Thumb {{
    background: {c.surface_variant};
    border-radius: {m.radius_sm}px;
}}

/* --------------------------------------------------------------- badges */
QLabel[badge="neutral"] {{
    background: {c.surface_variant};
    color: {c.on_surface_variant};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {max(7, m.font_pt - 2)}pt;
    font-weight: 600;
}}
QLabel[badge="accent"] {{
    background: {c.primary_container};
    color: {c.on_primary_container};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {max(7, m.font_pt - 2)}pt;
    font-weight: 600;
}}
QLabel[badge="success"] {{
    background: {c.success_container};
    color: {c.on_success_container};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {max(7, m.font_pt - 2)}pt;
    font-weight: 600;
}}
QLabel[badge="error"] {{
    background: {c.error_container};
    color: {c.on_error_container};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {max(7, m.font_pt - 2)}pt;
    font-weight: 600;
}}

/* ----------------------------------------------------------- service tabs */
#ServiceTabs {{
    background: {c.surface_container_low};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius}px;
    padding: 4px;
}}
#ServiceTabs QToolButton {{
    background: transparent;
    color: {c.on_surface_variant};
    border: none;
    border-radius: {max(3, m.radius - 3)}px;
    padding: 7px 16px;
    font-weight: 500;
}}
#ServiceTabs QToolButton:hover {{ background: {hover_on_surface}; color: {c.on_surface}; }}
#ServiceTabs QToolButton:checked {{
    background: {c.surface_container_high if m.design == "studio" else c.secondary_container};
    color: {c.primary};
    font-weight: 600;
}}

/* ------------------------------------------------------------- log output */
#LogView {{
    background: {c.surface_container_lowest};
    color: {c.on_surface_variant};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius_sm}px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: {max(7, m.font_pt - 1)}pt;
    padding: 10px;
}}

/* --------------------------------------------------------------- lists */
QListWidget, QTreeWidget {{
    background: {c.surface_container_low};
    border: 1px solid {c.outline_variant};
    border-radius: {m.radius_sm}px;
    outline: none;
    padding: 4px;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 8px;
    border-radius: {max(4, m.radius_sm - 2)}px;
    color: {c.on_surface};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {c.secondary_container};
    color: {c.on_secondary_container};
}}
QHeaderView::section {{
    background: {c.surface_container};
    color: {c.on_surface_variant};
    border: none;
    padding: 6px;
}}
"""
