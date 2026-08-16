"""Pass-through resolver: yt-dlp already understands the URL."""

from __future__ import annotations

from .base import ResolvedItem, Resolver, pretty_source


class GenericResolver(Resolver):
    name = "generic"

    def matches(self, url: str) -> bool:
        return url.lower().startswith(("http://", "https://"))

    def resolve(self, url: str, behaviour) -> list[ResolvedItem]:
        return [ResolvedItem(url=url, source=pretty_source(url))]
