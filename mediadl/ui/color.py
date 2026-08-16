"""Colour maths for the Material 3 palette generator.

Material 3 derives a whole scheme from one seed colour by building "tonal
palettes": ramps of a fixed hue and chroma sampled at perceptual lightness
steps 0-100. Google's reference uses the HCT space; we use OkLCh, which is
also perceptually uniform, far smaller to implement, and visually very close
for this purpose.

Chroma is clamped per tone by bisection so that every generated tone lands
inside the sRGB gamut instead of clipping to a flat, washed-out colour.
"""

from __future__ import annotations

import math

# ------------------------------------------------------------------ sRGB <-> linear


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        value = "7C4DFF"
    try:
        r, g, b = (int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.486, 0.302, 1.0)
    return (r, g, b)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


# ------------------------------------------------------------------ OkLab / OkLCh


def rgb_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l, m, s = (v**3 for v in (l_, m_, s_))

    lr = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    return tuple(_linear_to_srgb(c) for c in (lr, lg, lb))  # type: ignore[return-value]


def rgb_to_oklch(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = rgb_to_oklab(rgb)
    chroma = math.hypot(a, b)
    hue = math.degrees(math.atan2(b, a)) % 360.0
    return (L, chroma, hue)


def oklch_to_rgb(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    L, chroma, hue = lch
    rad = math.radians(hue)
    return oklab_to_rgb((L, chroma * math.cos(rad), chroma * math.sin(rad)))


def _in_gamut(rgb: tuple[float, float, float], tol: float = 1e-4) -> bool:
    return all(-tol <= c <= 1 + tol for c in rgb)


def _clamp01(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(max(0.0, min(1.0, c)) for c in rgb)  # type: ignore[return-value]


def gamut_map(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    """Reduce chroma until the colour fits in sRGB, preserving lightness and hue."""
    L, chroma, hue = lch
    if chroma <= 0:
        return _clamp01(oklch_to_rgb((L, 0.0, hue)))

    rgb = oklch_to_rgb(lch)
    if _in_gamut(rgb):
        return _clamp01(rgb)

    lo, hi = 0.0, chroma
    for _ in range(24):
        mid = (lo + hi) / 2
        if _in_gamut(oklch_to_rgb((L, mid, hue))):
            lo = mid
        else:
            hi = mid
    return _clamp01(oklch_to_rgb((L, lo, hue)))


# ------------------------------------------------------------------ tonal palette


def _tone_to_oklab_l(tone: float) -> float:
    """Convert a Material tone (CIE L*) to OkLab lightness.

    For a neutral grey the OkLab transform collapses to L = Y**(1/3), and CIE
    L* defines Y = ((L*+16)/116)**3 above the linear knee, so the two spaces
    line up exactly as L = (L*+16)/116. Without this the ramp reads far too
    dark through the midtones.
    """
    if tone >= 8.0:
        return (tone + 16.0) / 116.0
    return (tone / 903.2962962) ** (1 / 3)


class TonalPalette:
    """A fixed hue/chroma ramp addressable by Material tone (0 = black, 100 = white)."""

    def __init__(self, hue: float, chroma: float):
        self.hue = hue
        self.chroma = chroma
        self._cache: dict[int, str] = {}

    @classmethod
    def from_hex(cls, value: str, chroma: float | None = None) -> "TonalPalette":
        _, seed_chroma, hue = rgb_to_oklch(hex_to_rgb(value))
        return cls(hue, seed_chroma if chroma is None else chroma)

    def tone(self, tone: int) -> str:
        tone = max(0, min(100, int(tone)))
        if tone not in self._cache:
            self._cache[tone] = rgb_to_hex(gamut_map((_tone_to_oklab_l(tone), self.chroma, self.hue)))
        return self._cache[tone]

    __call__ = tone


def relative_luminance(value: str) -> float:
    r, g, b = (_srgb_to_linear(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def best_on(background: str, *candidates: str) -> str:
    """Pick whichever candidate reads most clearly on the given background."""
    return max(candidates, key=lambda c: contrast_ratio(background, c))


def with_alpha(value: str, alpha: float) -> str:
    """Qt style sheets accept rgba(); use it for overlays and state layers."""
    r, g, b = hex_to_rgb(value)
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {alpha:.3f})"


def mix(a: str, b: str, ratio: float) -> str:
    """Blend two hex colours in linear light. ratio=0 returns a, 1 returns b."""
    ra, ga, ba = (_srgb_to_linear(c) for c in hex_to_rgb(a))
    rb, gb, bb = (_srgb_to_linear(c) for c in hex_to_rgb(b))
    blended = (
        ra + (rb - ra) * ratio,
        ga + (gb - ga) * ratio,
        ba + (bb - ba) * ratio,
    )
    return rgb_to_hex(tuple(_linear_to_srgb(c) for c in blended))  # type: ignore[arg-type]
