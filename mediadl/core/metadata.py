"""Post-download tagging.

yt-dlp's FFmpegMetadata post-processor already copies the obvious fields. This
module adds what it cannot know: the originating page URL, the download date,
and any metadata a source resolver supplied by hand (HDRezka show and episode
numbers, for instance). Failures here never fail the download.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

AUDIO_SUFFIXES = {".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".opus", ".wav", ".aac"}


def apply(path: str | Path, *, source_url: str = "", extra: dict | None = None) -> bool:
    """Write extra tags onto a finished file. Returns True when something changed."""
    target = Path(path)
    if not target.exists():
        return False

    suffix = target.suffix.lower()
    extra = dict(extra or {})

    try:
        if suffix == ".mp3":
            return _tag_mp3(target, source_url, extra)
        if suffix in (".m4a", ".mp4", ".m4v", ".mov"):
            return _tag_mp4(target, source_url, extra)
        if suffix in (".flac", ".ogg", ".opus"):
            return _tag_vorbis(target, source_url, extra)
        if suffix in (".mkv", ".webm"):
            # Matroska tags are written by ffmpeg during post-processing;
            # mutagen has no writer for them.
            return False
    except Exception:
        return False

    return False


def _today() -> str:
    return _dt.date.today().isoformat()


def _tag_mp3(target: Path, source_url: str, extra: dict) -> bool:
    from mutagen.id3 import COMM, ID3, TALB, TDRC, TIT2, TPE1, TXXX, WOAS
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = ID3(target)
    except ID3NoHeaderError:
        tags = ID3()

    if extra.get("title"):
        tags.setall("TIT2", [TIT2(encoding=3, text=str(extra["title"]))])
    if extra.get("artist"):
        tags.setall("TPE1", [TPE1(encoding=3, text=str(extra["artist"]))])
    if extra.get("album"):
        tags.setall("TALB", [TALB(encoding=3, text=str(extra["album"]))])
    if extra.get("year"):
        tags.setall("TDRC", [TDRC(encoding=3, text=str(extra["year"]))])

    if source_url:
        tags.setall("WOAS", [WOAS(url=source_url)])
        tags.add(TXXX(encoding=3, desc="SOURCE_URL", text=source_url))
    tags.add(TXXX(encoding=3, desc="DOWNLOAD_DATE", text=_today()))

    if extra.get("comment"):
        tags.setall("COMM", [COMM(encoding=3, lang="eng", desc="", text=str(extra["comment"]))])

    tags.save(target, v2_version=3)
    return True


def _tag_mp4(target: Path, source_url: str, extra: dict) -> bool:
    from mutagen.mp4 import MP4, MP4FreeForm

    audio = MP4(target)
    tags = audio.tags
    if tags is None:
        audio.add_tags()
        tags = audio.tags

    if extra.get("title"):
        tags["\xa9nam"] = [str(extra["title"])]
    if extra.get("artist"):
        tags["\xa9ART"] = [str(extra["artist"])]
    if extra.get("album"):
        tags["\xa9alb"] = [str(extra["album"])]
    if extra.get("year"):
        tags["\xa9day"] = [str(extra["year"])]
    if extra.get("comment"):
        tags["\xa9cmt"] = [str(extra["comment"])]

    if extra.get("season_number") is not None:
        tags["tvsn"] = [int(extra["season_number"])]
    if extra.get("episode_number") is not None:
        tags["tves"] = [int(extra["episode_number"])]
    if extra.get("album") and extra.get("season_number") is not None:
        tags["tvsh"] = [str(extra["album"])]

    def freeform(name: str, value: str) -> None:
        tags[f"----:com.apple.iTunes:{name}"] = [MP4FreeForm(value.encode("utf-8"))]

    if source_url:
        freeform("SOURCE_URL", source_url)
    freeform("DOWNLOAD_DATE", _today())

    audio.save()
    return True


def _tag_vorbis(target: Path, source_url: str, extra: dict) -> bool:
    from mutagen import File as MutagenFile

    audio = MutagenFile(target)
    if audio is None:
        return False
    if audio.tags is None:
        audio.add_tags()

    mapping = {
        "title": "title",
        "artist": "artist",
        "album": "album",
        "year": "date",
        "comment": "comment",
    }
    for key, tag in mapping.items():
        if extra.get(key):
            audio[tag] = [str(extra[key])]

    if source_url:
        audio["source_url"] = [source_url]
    audio["download_date"] = [_today()]

    audio.save()
    return True
