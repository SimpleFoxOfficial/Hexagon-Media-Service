"""User settings: typed dataclasses with JSON persistence and forward-compatible loading."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from . import paths

# ---------------------------------------------------------------- enumerations

THEME_MODES = ("system", "light", "dark")
DENSITIES = ("comfortable", "compact")

# "studio" matches the restrained look of the sibling Modpack-Utility app:
# neutral surfaces, muted accents, small radii. "vibrant" is the saturated
# Material 3 treatment.
DESIGNS = ("studio", "vibrant")

MODES = ("video", "audio", "video_only")
QUALITIES = ("best", "2160", "1440", "1080", "720", "480", "360", "worst")
VIDEO_CONTAINERS = ("auto", "mp4", "mkv", "webm")
AUDIO_CODECS = ("mp3", "m4a", "opus", "flac", "wav", "vorbis", "best")
AUDIO_BITRATES = ("best", "320", "256", "192", "128", "96")
BROWSERS = ("", "chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium")

# Saturated seeds for the "vibrant" design.
VIBRANT_ACCENTS = [
    ("Electric Violet", "#7C4DFF"),
    ("Hot Magenta", "#E5399B"),
    ("Cyber Teal", "#00BFA5"),
    ("Solar Orange", "#FF6D00"),
    ("Azure", "#2979FF"),
    ("Lime Punch", "#64DD17"),
    ("Crimson", "#FF1744"),
    ("Amber", "#FFC400"),
]

# Muted seeds matching Modpack-Utility's accent set. Stored as the light-mode
# hex; the tonal machinery derives the dark-mode counterpart.
STUDIO_ACCENTS = [
    ("Red", "#A03F3F"),
    ("Green", "#3B6350"),
    ("Blue", "#33597F"),
    ("Violet", "#564B84"),
    ("Amber", "#856226"),
    ("Slate", "#4C5661"),
]

# Kept as the default listing so existing call sites keep working.
ACCENT_PRESETS = STUDIO_ACCENTS


def accents_for(design: str) -> list[tuple[str, str]]:
    return VIBRANT_ACCENTS if design == "vibrant" else STUDIO_ACCENTS


def default_seed_for(design: str) -> str:
    # Blue rather than Modpack-Utility's red default: in a downloader the accent
    # sits next to genuine error states, and a red "Downloading" badge reads as
    # a failure.
    return "#7C4DFF" if design == "vibrant" else "#33597F"


# ------------------------------------------------------------------ dataclasses


@dataclass
class Appearance:
    design: str = "studio"
    theme_mode: str = "system"
    seed_color: str = "#33597F"
    corner_radius: int = 7
    density: str = "comfortable"
    font_family: str = "Segoe UI"
    logo_font: str = "Comfortaa"
    font_size: int = 10
    animations: bool = True
    show_thumbnails: bool = True
    vibrant_cards: bool = True


@dataclass
class Preset:
    """The download options the user picks per batch."""

    mode: str = "video"
    quality: str = "1080"
    video_container: str = "mp4"
    audio_codec: str = "mp3"
    audio_bitrate: str = "192"


@dataclass
class Behaviour:
    download_dir: str = ""
    organize_by_category: bool = True
    organize_by_source: bool = False
    filename_template: str = "%(title).150B [%(id)s].%(ext)s"

    max_concurrent: int = 3
    rate_limit_kbps: int = 0
    retries: int = 5
    socket_timeout: int = 30

    embed_metadata: bool = True
    embed_thumbnail: bool = True
    embed_chapters: bool = True
    write_subtitles: bool = False
    embed_subtitles: bool = True
    subtitle_langs: str = "en,ru"
    skip_sponsors: bool = False

    expand_playlists: bool = True
    playlist_limit: int = 0

    # Series get Show/Season NN/Show - SxxEyy instead of one flat folder.
    tv_folders: bool = True
    tv_season_template: str = "Season %(season)02d"
    # Fields: show, season, episode, dub. An empty dub collapses away, so the
    # name stays "Show 6x20" rather than trailing a space.
    tv_episode_template: str = "%(show)s %(season)dx%(episode)02d %(dub)s"

    cookies_from_browser: str = ""
    proxy: str = ""
    use_archive: bool = False
    ffmpeg_path: str = ""

    # Selecting formats by extension steers YouTube onto clients that reject the
    # transfer partway through with HTTP 403. Choosing by height and remuxing
    # afterwards produces the same container without that failure.
    strict_container_match: bool = False
    http_chunk_size_mb: int = 10
    extractor_retries: int = 3
    verbose_logging: bool = False

    notify_on_complete: bool = True
    open_folder_on_complete: bool = False
    clear_completed_on_exit: bool = False

    def resolved_download_dir(self) -> Path:
        return Path(self.download_dir) if self.download_dir else paths.default_download_dir()


@dataclass
class Rezka:
    """HDRezka-specific choices, kept separate because they do not apply to yt-dlp sites."""

    mirror: str = ""
    translator_id: str = ""
    prefer_translator_name: str = ""
    quality: str = "1080"
    subtitles: bool = True
    subtitle_lang: str = ""
    embed_metadata: bool = True
    season_folders: bool = True
    last_url: str = ""


@dataclass
class Settings:
    appearance: Appearance = field(default_factory=Appearance)
    behaviour: Behaviour = field(default_factory=Behaviour)
    preset: Preset = field(default_factory=Preset)
    rezka: Rezka = field(default_factory=Rezka)
    window_geometry: str = ""
    active_service: str = "auto"

    # ------------------------------------------------------------- persistence

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or paths.settings_file()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return _from_dict(cls, raw)

    def save(self, path: Path | None = None) -> None:
        path = path or paths.settings_file()
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass


def _from_dict(cls: type, raw: Any) -> Any:
    """Overlay JSON onto a default instance.

    Unknown keys are dropped and missing keys keep their defaults, so settings
    files written by older or newer builds still load. Values whose type does
    not match the default are ignored rather than crashing the app on startup.
    """
    obj = cls()
    if not isinstance(raw, dict):
        return obj

    for f in fields(cls):
        if f.name not in raw:
            continue
        value = raw[f.name]
        current = getattr(obj, f.name)

        if is_dataclass(current):
            if isinstance(value, dict):
                setattr(obj, f.name, _from_dict(type(current), value))
        elif isinstance(current, bool):
            if isinstance(value, bool):
                setattr(obj, f.name, value)
        elif isinstance(current, int):
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(obj, f.name, value)
        elif isinstance(value, type(current)):
            setattr(obj, f.name, value)

    return obj
