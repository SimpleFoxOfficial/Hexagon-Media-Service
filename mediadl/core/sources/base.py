"""Source resolver interface.

Most sites are handled by yt-dlp directly, so their resolver is a pass-through.
Sites yt-dlp does not know (HDRezka) get a resolver that turns a page URL into
a direct stream URL, which yt-dlp then downloads normally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class ResolvedItem:
    """One downloadable thing produced from a user-supplied URL."""

    url: str
    title: str = ""
    source: str = ""
    thumbnail: str = ""
    filename_stem: str = ""
    extra_opts: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class Resolver:
    name = "generic"
    #: Set when the resolver may need the user to choose seasons/episodes.
    interactive = False

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    def resolve(self, url: str, behaviour) -> list[ResolvedItem]:
        raise NotImplementedError


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


PRETTY_SOURCES = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "music.youtube.com": "YouTube Music",
    "reddit.com": "Reddit",
    "redd.it": "Reddit",
    "twitter.com": "Twitter",
    "x.com": "Twitter",
    "vimeo.com": "Vimeo",
    "soundcloud.com": "SoundCloud",
    "twitch.tv": "Twitch",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "bandcamp.com": "Bandcamp",
    "dailymotion.com": "Dailymotion",
    "vk.com": "VK",
}


def pretty_source(url: str) -> str:
    """A display name for a URL's site."""
    host = domain_of(url)
    if not host:
        return "Unknown"
    if "rezka" in host:
        return "HDRezka"
    if host in PRETTY_SOURCES:
        return PRETTY_SOURCES[host]
    # Match the registrable part so m.youtube.com and old.reddit.com collapse.
    parts = host.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in PRETTY_SOURCES:
            return PRETTY_SOURCES[candidate]
    base = parts[-2] if len(parts) >= 2 else host
    return base.capitalize()
