"""Translate the user's preset and settings into yt-dlp options."""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Behaviour, Preset

# Height-only selection. Filtering on extension is deliberately avoided: it
# steers YouTube onto clients whose transfers are rejected partway through with
# HTTP 403, and the target container is reached by remuxing afterwards anyway.
_ANY_CHAIN = "bv*[height<={h}]+ba/b[height<={h}]"

# Only used when the user explicitly asks for a native container match.
_STRICT_CHAINS = {
    "mp4": "bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]",
    "webm": "bv*[height<={h}][ext=webm]+ba[ext=webm]/bv*[height<={h}]+ba/b[height<={h}]",
}

CATEGORY_DIRS = {
    "video": "Video",
    "video_only": "Video",
    "audio": "Audio",
}


def format_selector(preset: Preset, strict_container: bool = False) -> str:
    """Build the yt-dlp -f expression for a preset.

    `strict_container` filters on extension so no remux is needed. It is off by
    default because it triggers HTTP 403 failures on YouTube.
    """
    if preset.mode == "audio":
        return "ba/b"

    if preset.quality == "best":
        base = "bv*+ba/b"
    elif preset.quality == "worst":
        base = "wv*+wa/w"
    else:
        height = preset.quality
        if preset.mode == "video_only":
            return f"bv*[height<={height}]/bv*/b"
        chain = _ANY_CHAIN
        if strict_container:
            chain = _STRICT_CHAINS.get(preset.video_container, _ANY_CHAIN)
        base = chain.format(h=height)
        # Always leave a universal fallback so odd extractors still succeed.
        return f"{base}/bv*+ba/b"

    if preset.mode == "video_only":
        return "wv*/w" if preset.quality == "worst" else "bv*/b"
    return base


def target_dir(behaviour: Behaviour, preset: Preset, source: str = "") -> Path:
    """Destination folder after applying the organising options."""
    root = behaviour.resolved_download_dir()

    if behaviour.organize_by_category:
        root = root / CATEGORY_DIRS.get(preset.mode, "Video")
    if behaviour.organize_by_source and source:
        root = root / _safe_dir(source)

    return root


def output_template(behaviour: Behaviour, preset: Preset, source: str = "") -> str:
    """Absolute yt-dlp output template including any organising sub-folders."""
    template = behaviour.filename_template.strip() or "%(title).150B [%(id)s].%(ext)s"
    return str(target_dir(behaviour, preset, source) / template)


def output_template_for_stem(
    behaviour: Behaviour, preset: Preset, stem: str, source: str = ""
) -> str:
    """Template with a fixed filename, for resolvers that already know the title.

    Direct stream URLs carry no useful title of their own, so HDRezka items
    would otherwise land on disk named after a CDN path segment.
    """
    safe = _safe_file(stem)
    return str(target_dir(behaviour, preset, source) / f"{safe}.%(ext)s")


def _safe_file(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch not in '<>:"/\\|?*').strip()
    cleaned = " ".join(cleaned.split())
    return cleaned[:170] or "download"


def episode_paths(
    behaviour: Behaviour,
    preset: Preset,
    show: str,
    season: int,
    episode: int,
    source: str = "",
    dub: str = "",
) -> tuple[Path, str]:
    """Folder and filename stem for one episode of a series.

    With tv_folders on this produces Show/Season 06/Show 6x20 Dub, so a whole
    season lands sorted instead of dumped flat next to everything else.
    """
    root = target_dir(behaviour, preset, source)
    safe_show = _safe_file(show) or "Series"

    fields = {
        "show": safe_show,
        "season": season,
        "episode": episode,
        "dub": _safe_file(dub) if dub else "",
    }
    stem = _format_template(
        behaviour.tv_episode_template, fields, f"{safe_show} {season}x{episode:02d}"
    )

    if not behaviour.tv_folders:
        return root, _safe_file(stem)

    season_dir = _format_template(behaviour.tv_season_template, fields, f"Season {season:02d}")
    return root / safe_show / _safe_file(season_dir), _safe_file(stem)


def _format_template(template: str, fields: dict, fallback: str) -> str:
    """Render a %(name)s template, falling back if the user's template is broken.

    Optional fields such as the dub name are often empty, which would otherwise
    leave doubled or trailing separators in the name.
    """
    try:
        rendered = template % fields
    except (KeyError, ValueError, TypeError):
        rendered = fallback

    # An empty field leaves doubled separators ("Show -  - 6x20") and trailing
    # ones. Only runs of two or more collapse; a single " - " the user wrote on
    # purpose is left alone.
    rendered = re.sub(r"\s{2,}", " ", rendered)
    rendered = re.sub(r"(?:\s*[-_]\s*){2,}", " - ", rendered)
    rendered = re.sub(r"\[\s*\]|\(\s*\)", "", rendered)
    return re.sub(r"\s{2,}", " ", rendered).strip(" -_")


def output_template_for_episode(
    behaviour: Behaviour,
    preset: Preset,
    show: str,
    season: int,
    episode: int,
    source: str = "",
    dub: str = "",
) -> str:
    folder, stem = episode_paths(behaviour, preset, show, season, episode, source, dub)
    return str(folder / f"{stem}.%(ext)s")


def _safe_dir(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
    return cleaned or "Other"


def postprocessors(behaviour: Behaviour, preset: Preset) -> list[dict]:
    """Assemble the post-processing chain.

    Order matters: audio extraction or remuxing has to settle the container
    before subtitles, tags and artwork are written into it.
    """
    chain: list[dict] = []

    if behaviour.skip_sponsors:
        categories = ["sponsor", "selfpromo", "interaction"]
        chain.append({"key": "SponsorBlock", "categories": categories, "when": "after_filter"})
        chain.append({"key": "ModifyChapters", "remove_sponsor_segments": categories})

    if preset.mode == "audio":
        codec = preset.audio_codec if preset.audio_codec != "best" else "best"
        chain.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": (
                    None if preset.audio_bitrate == "best" else preset.audio_bitrate
                ),
                "nopostoverwrites": False,
            }
        )
    elif preset.video_container in ("mp4", "mkv", "webm"):
        chain.append({"key": "FFmpegVideoRemuxer", "preferedformat": preset.video_container})

    if behaviour.embed_subtitles and preset.mode != "audio":
        chain.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

    if behaviour.embed_metadata:
        chain.append(
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
                "add_chapters": behaviour.embed_chapters,
                "add_infojson": False,
            }
        )

    if behaviour.embed_thumbnail:
        chain.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

    return chain


def build_opts(
    behaviour: Behaviour,
    preset: Preset,
    *,
    ffmpeg: Path | None,
    source: str = "",
    extra: dict | None = None,
) -> dict:
    """The complete ydl_opts dictionary, minus hooks and logger."""
    opts: dict = {
        "format": format_selector(preset, behaviour.strict_container_match),
        "outtmpl": {"default": output_template(behaviour, preset, source)},
        "postprocessors": postprocessors(behaviour, preset),
        "noprogress": True,
        "quiet": True,
        "no_warnings": False,
        "consoletitle": False,
        "ignoreerrors": False,
        "retries": max(0, behaviour.retries),
        "fragment_retries": max(0, behaviour.retries),
        "socket_timeout": max(5, behaviour.socket_timeout),
        "continuedl": True,
        "windowsfilenames": True,
        "trim_file_name": 180,
        "restrictfilenames": False,
        "overwrites": False,
        "noplaylist": not behaviour.expand_playlists,
        "extract_flat": False,
        "writethumbnail": behaviour.embed_thumbnail,
        "postprocessor_args": {"default": []},
    }

    if preset.mode != "audio" and preset.video_container in ("mp4", "mkv", "webm"):
        opts["merge_output_format"] = preset.video_container
    elif preset.mode != "audio":
        opts["merge_output_format"] = "mkv"

    if behaviour.write_subtitles or behaviour.embed_subtitles:
        langs = [s.strip() for s in behaviour.subtitle_langs.split(",") if s.strip()]
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = behaviour.write_subtitles
        opts["subtitleslangs"] = langs or ["en"]
        opts["keepvideo"] = False

    if behaviour.rate_limit_kbps > 0:
        opts["ratelimit"] = behaviour.rate_limit_kbps * 1024

    # Long transfers outlive the signed URL they started with. Requesting the
    # file in chunks makes each range a fresh request, which is what keeps a
    # multi-gigabyte download from dying partway through with HTTP 403.
    if behaviour.http_chunk_size_mb > 0:
        opts["http_chunk_size"] = behaviour.http_chunk_size_mb * 1024 * 1024

    if behaviour.extractor_retries > 0:
        opts["extractor_retries"] = behaviour.extractor_retries

    if behaviour.playlist_limit > 0:
        opts["playlistend"] = behaviour.playlist_limit

    if behaviour.proxy.strip():
        opts["proxy"] = behaviour.proxy.strip()

    # Deliberately not `cookiesfrombrowser`: that reads the locked browser
    # database mid-extraction and a failure there aborts every download.
    if behaviour.cookies_from_browser:
        from .cookies import cookie_file

        path, problem = cookie_file(behaviour.cookies_from_browser)
        if path is not None:
            opts["cookiefile"] = str(path)
        elif problem:
            opts["_cookie_problem"] = problem

    if behaviour.use_archive:
        from .. import paths

        opts["download_archive"] = str(paths.archive_file())

    if ffmpeg is not None:
        opts["ffmpeg_location"] = str(ffmpeg)

    if extra:
        opts.update(extra)

    return opts


def describe(preset: Preset) -> str:
    """Short human summary shown on the download button and in job cards."""
    if preset.mode == "audio":
        codec = preset.audio_codec.upper()
        rate = "best" if preset.audio_bitrate == "best" else f"{preset.audio_bitrate}k"
        return f"Audio {codec} {rate}"

    quality = {
        "best": "Best",
        "worst": "Lowest",
        "2160": "4K",
        "1440": "1440p",
        "1080": "1080p",
        "720": "720p",
        "480": "480p",
        "360": "360p",
    }.get(preset.quality, preset.quality)

    container = "auto" if preset.video_container == "auto" else preset.video_container.upper()
    suffix = " (no audio)" if preset.mode == "video_only" else ""
    return f"Video {quality} {container}{suffix}"
