"""Source resolver registry."""

from __future__ import annotations

from .base import ResolvedItem, Resolver, domain_of, pretty_source
from .generic import GenericResolver
from .hdrezka import (
    EpisodeRef,
    HdRezkaBlocked,
    HdRezkaResolver,
    HdRezkaUnavailable,
    SeriesInfo,
)

_GENERIC = GenericResolver()
_SPECIFIC: list[Resolver] = [HdRezkaResolver()]

__all__ = [
    "EpisodeRef",
    "ResolvedItem",
    "Resolver",
    "SeriesInfo",
    "HdRezkaBlocked",
    "HdRezkaResolver",
    "HdRezkaUnavailable",
    "domain_of",
    "pretty_source",
    "resolver_for",
    "hdrezka",
]


def resolver_for(url: str) -> Resolver:
    """The most specific resolver that claims this URL, else the pass-through."""
    for resolver in _SPECIFIC:
        if resolver.matches(url):
            return resolver
    return _GENERIC


def hdrezka() -> HdRezkaResolver:
    return _SPECIFIC[0]  # type: ignore[return-value]
