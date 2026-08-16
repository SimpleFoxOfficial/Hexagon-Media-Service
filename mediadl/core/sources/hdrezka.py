"""HDRezka resolver.

HDRezka pages are not handled by yt-dlp, so this resolver uses HdRezkaApi to
turn a page URL into a direct stream URL (mp4 or m3u8), which is then handed
back to yt-dlp for the actual transfer. Movies resolve in one step; series
expose their translations, seasons and episodes so the UI can offer them in
bulk.

The site fronts its pages with an anti-bot interstitial. When that appears the
HTML contains none of the expected markup and every parser lookup returns None,
so this module checks for it explicitly and says so rather than letting a pile
of AttributeErrors surface as "this is a film".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ... import logs
from .base import ResolvedItem, Resolver, domain_of

log = logs.get("sources.hdrezka")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# The interstitial is served in Russian. Its two giveaway phrases read
# "checking" and "not a bot"; they are built from code points so this file stays
# ASCII. The length check below is the more reliable tell either way.
_RU_CHECKING = "".join(map(chr, (0x41F, 0x440, 0x43E, 0x432, 0x435, 0x440, 0x44F, 0x435, 0x43C)))
_RU_NOT_A_BOT = "".join(map(chr, (0x43D, 0x435, 0x20, 0x431, 0x43E, 0x442)))

_BOT_MARKERS = (
    "proverjaem",
    "cf-browser-verification",
    "challenge-platform",
    "captcha",
    _RU_CHECKING,
    _RU_NOT_A_BOT,
)
_REAL_PAGE_MARKERS = ("b-post__title", "b-translator__item", "initCDN", "b-simple_episode")
_MIN_REAL_PAGE_BYTES = 20_000


class HdRezkaUnavailable(RuntimeError):
    """HdRezkaApi is not installed."""


class HdRezkaBlocked(RuntimeError):
    """The site served its anti-bot page instead of the content."""


@dataclass
class EpisodeRef:
    season: int
    episode: int
    translator_id: str | int | None = None
    translator_name: str = ""


@dataclass
class SeriesInfo:
    """Everything the HDRezka panel needs to offer choices."""

    url: str
    name: str = ""
    is_series: bool = False
    thumbnail: str = ""
    translators: dict = field(default_factory=dict)
    # {translator_id: {season: [episode, ...]}}
    seasons: dict = field(default_factory=dict)
    default_translator: str = ""
    error: str = ""
    blocked: bool = False

    @property
    def ok(self) -> bool:
        return not self.error

    def episode_count(self, translator_id: str) -> int:
        return sum(len(v) for v in self.seasons.get(str(translator_id), {}).values())


def _import_api():
    try:
        from HdRezkaApi import HdRezkaApi  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - depends on install
        raise HdRezkaUnavailable(
            "HdRezkaApi is not installed. Run: pip install HdRezkaApi"
        ) from exc
    return HdRezkaApi


def browser_cookies(browser: str) -> dict:
    """Reuse cookies the user's browser already holds for HDRezka.

    Solving the site's bot check once in a normal browser leaves a cookie that
    makes subsequent requests pass. yt-dlp already knows how to read each
    browser's cookie store, so that machinery is reused here rather than
    reimplemented.
    """
    if not browser:
        return {}
    try:
        from yt_dlp.cookies import extract_cookies_from_browser

        jar = extract_cookies_from_browser(browser)
    except Exception as exc:
        log.warning("Could not read cookies from %s: %s", browser, exc)
        return {}

    cookies = {}
    for cookie in jar:
        if "rezka" in (cookie.domain or ""):
            cookies[cookie.name] = cookie.value
    log.info("Loaded %d HDRezka cookies from %s", len(cookies), browser)
    return cookies


def apply_mirror(url: str, mirror: str) -> str:
    """Swap the host for a configured mirror, keeping the path."""
    if not mirror:
        return url
    host = mirror.strip().replace("https://", "").replace("http://", "").strip("/")
    if not host:
        return url
    return re.sub(r"^(https?://)[^/]+", lambda m: m.group(1) + host, url, count=1)


def _client(url: str, behaviour, rezka=None):
    api_cls = _import_api()

    proxy = {}
    if getattr(behaviour, "proxy", ""):
        proxy = {"http": behaviour.proxy, "https": behaviour.proxy}

    cookies = browser_cookies(getattr(behaviour, "cookies_from_browser", ""))
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}

    if rezka is not None:
        url = apply_mirror(url, getattr(rezka, "mirror", ""))

    log.info("Fetching HDRezka page %s (cookies=%d)", url, len(cookies))
    api = api_cls(url, proxy=proxy, headers=headers, cookies=cookies)
    _guard_bot_page(api, url, bool(cookies))
    return api


def _guard_bot_page(api, url: str, had_cookies: bool) -> None:
    """Raise a clear error when the interstitial was served instead of the page."""
    page = getattr(api, "page", None)
    html = ""
    if page is not None:
        html = getattr(page, "text", "") or ""

    if not html:
        return

    lowered = html.lower()
    looks_real = any(marker.lower() in lowered for marker in _REAL_PAGE_MARKERS)
    if looks_real:
        return

    tripped = any(marker.lower() in lowered for marker in _BOT_MARKERS)
    if tripped or len(html) < _MIN_REAL_PAGE_BYTES:
        log.error(
            "HDRezka served an anti-bot page for %s (%d bytes, cookies=%s)",
            url,
            len(html),
            had_cookies,
        )
        hint = (
            "Open the page in your browser, complete its check, then set "
            "Settings > Network > Use cookies from to that browser."
        )
        if had_cookies:
            hint = (
                "The imported cookies did not satisfy it. Re-open the page in that "
                "browser, complete the check, and make sure you picked the same browser."
            )
        raise HdRezkaBlocked(f"HDRezka served its anti-bot page instead of the content. {hint}")


# --------------------------------------------------------------- stream picking


def _height_of(key: str) -> int:
    match = re.search(r"(\d{3,4})", str(key))
    return int(match.group(1)) if match else 0


def pick_resolution(videos: dict, wanted: str) -> str:
    """Choose the closest available stream to the requested quality."""
    available = list(videos.keys())
    if not available:
        return ""

    ranked = sorted(available, key=_height_of, reverse=True)
    if wanted == "best":
        return ranked[0]
    if wanted == "worst":
        return ranked[-1]

    try:
        target = int(wanted)
    except (TypeError, ValueError):
        return ranked[0]

    within = [k for k in ranked if _height_of(k) <= target]
    return within[0] if within else ranked[-1]


def _stream_url(stream, quality: str) -> str:
    videos = getattr(stream, "videos", {}) or {}
    key = pick_resolution(videos, quality)
    if not key:
        return ""
    try:
        value = stream(key)
    except Exception as exc:
        log.warning("stream(%r) failed, falling back to the raw mapping: %s", key, exc)
        value = videos.get(key)
    if isinstance(value, (list, tuple)):
        return str(value[-1]) if value else ""
    return str(value) if value else ""


def _subtitle_url(stream, wanted: str) -> str:
    subs = getattr(stream, "subtitles", None)
    if subs is None:
        return ""
    try:
        if wanted:
            value = subs(wanted)
        else:
            keys = list(getattr(subs, "subtitles", {}) or {})
            if not keys:
                return ""
            value = subs(keys[0])
    except Exception:
        return ""
    return str(value) if value else ""


def _sanitize(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "", str(text)).strip()
    return re.sub(r"\s+", " ", cleaned)[:150] or "HDRezka"


def _read(api, attribute: str, default=None, required: bool = False):
    """Read one HdRezkaApi property, logging rather than hiding failures.

    A plain getattr with a default is wrong here: every parse failure on this
    site raises AttributeError, which getattr would swallow, turning a blocked
    page into a silently empty result.
    """
    try:
        return getattr(api, attribute)
    except Exception as exc:
        log.warning("HDRezka property %r failed: %s: %s", attribute, type(exc).__name__, exc)
        if required:
            raise RuntimeError(f"Could not read {attribute} from the page") from exc
        return default


def _normalise_seasons(payload) -> dict:
    """Pull {season: [episodes]} out of whichever shape seriesInfo used."""
    episodes = payload
    if isinstance(payload, dict) and "episodes" in payload:
        episodes = payload.get("episodes") or {}
    if not isinstance(episodes, dict):
        return {}

    seasons: dict[int, list[int]] = {}
    for season, eps in episodes.items():
        try:
            season_no = int(season)
        except (TypeError, ValueError):
            continue
        numbers = []
        for ep in eps or []:
            try:
                numbers.append(int(ep))
            except (TypeError, ValueError):
                continue
        if numbers:
            seasons[season_no] = sorted(numbers)
    return seasons


class HdRezkaResolver(Resolver):
    name = "hdrezka"
    interactive = True

    def matches(self, url: str) -> bool:
        return "rezka" in domain_of(url)

    # ------------------------------------------------------------------ probe

    def probe(self, url: str, behaviour, rezka=None) -> SeriesInfo:
        """Read the page so the UI can offer translations, seasons and episodes."""
        info = SeriesInfo(url=url)
        try:
            api = _client(url, behaviour, rezka)
        except HdRezkaBlocked as exc:
            info.error, info.blocked = str(exc), True
            return info
        except HdRezkaUnavailable as exc:
            info.error = str(exc)
            return info
        except Exception as exc:
            logs.exception(log, "HDRezka page fetch failed", exc)
            info.error = f"Could not open the page: {exc}"
            return info

        info.name = str(_read(api, "name", "") or "")
        info.thumbnail = str(_read(api, "thumbnail", "") or "")

        media_type = _read(api, "type")
        type_name = getattr(media_type, "__name__", "") or str(media_type or "")
        info.is_series = "Series" in type_name

        if not info.name and not type_name:
            info.error = (
                "The page loaded but nothing could be read from it. "
                "It may be a mirror that serves different markup, or the layout changed."
            )
            return info

        raw_translators = _read(api, "translators", {}) or {}
        for key, value in raw_translators.items():
            if isinstance(value, dict):
                name = value.get("name") or str(key)
            else:
                name = str(value)
            info.translators[str(key)] = str(name)

        if info.is_series:
            series = _read(api, "seriesInfo", {}) or {}
            for tid, payload in series.items():
                seasons = _normalise_seasons(payload)
                if seasons:
                    info.seasons[str(tid)] = seasons
                if isinstance(payload, dict):
                    name = payload.get("translator_name") or payload.get("name")
                    if name:
                        info.translators.setdefault(str(tid), str(name))

            if not info.seasons:
                info.error = (
                    "No episode list was found. The page may require signing in, "
                    "or this title has no episodes listed."
                )
                return info

            info.default_translator = _best_translator(info)

        log.info(
            "Probed %r series=%s translators=%d seasons=%s",
            info.name,
            info.is_series,
            len(info.translators),
            {k: sorted(v) for k, v in info.seasons.items()},
        )
        return info

    # ---------------------------------------------------------------- resolve

    def resolve(self, url: str, behaviour, quality: str = "best", rezka=None) -> list[ResolvedItem]:
        """Resolve a film URL to a single downloadable item."""
        api = _client(url, behaviour, rezka)
        name = str(_read(api, "name", "") or "HDRezka")
        thumbnail = str(_read(api, "thumbnail", "") or "")

        translation = getattr(rezka, "translator_id", "") if rezka else ""
        try:
            stream = api.getStream(translation=translation or None)
        except Exception as exc:
            logs.exception(log, f"getStream failed for {url}", exc)
            raise RuntimeError(f"Could not open the stream: {exc}") from exc

        direct = _stream_url(stream, quality)
        if not direct:
            raise RuntimeError(f"No playable stream was offered for {name}")

        item = ResolvedItem(
            url=direct,
            title=name,
            source="HDRezka",
            thumbnail=thumbnail,
            filename_stem=_sanitize(name),
            extra_opts={"http_headers": {"User-Agent": USER_AGENT, "Referer": url}},
            metadata={"title": name, "comment": url},
        )
        if rezka is not None and getattr(rezka, "subtitles", False):
            subtitle = _subtitle_url(stream, getattr(rezka, "subtitle_lang", ""))
            if subtitle:
                item.extra_opts["_subtitle_url"] = subtitle
        log.info("Resolved film %r at %s", name, quality)
        return [item]

    def resolve_episodes(
        self,
        url: str,
        behaviour,
        episodes: list[EpisodeRef],
        quality: str = "best",
        rezka=None,
        progress=None,
    ) -> tuple[list[ResolvedItem], list[str]]:
        """Resolve chosen episodes. Returns the items plus per-episode failures."""
        api = _client(url, behaviour, rezka)
        show = str(_read(api, "name", "") or "HDRezka")
        thumbnail = str(_read(api, "thumbnail", "") or "")

        items: list[ResolvedItem] = []
        problems: list[str] = []

        for index, ref in enumerate(episodes, start=1):
            tag = f"S{ref.season:02d}E{ref.episode:02d}"
            if progress is not None:
                progress(index, len(episodes), tag)

            try:
                stream = api.getStream(
                    season=str(ref.season),
                    episode=str(ref.episode),
                    translation=ref.translator_id,
                )
                direct = _stream_url(stream, quality)
            except Exception as exc:
                log.warning("%s failed: %s: %s", tag, type(exc).__name__, exc)
                problems.append(f"{tag}: {exc}")
                continue

            if not direct:
                problems.append(f"{tag}: no stream offered at this quality")
                continue

            title = f"{show} {tag}"
            item = ResolvedItem(
                url=direct,
                title=title,
                source="HDRezka",
                thumbnail=thumbnail,
                filename_stem=_sanitize(f"{show} - {tag}"),
                extra_opts={
                    "http_headers": {"User-Agent": USER_AGENT, "Referer": url},
                    "_show": show,
                    "_season": ref.season,
                    "_episode": ref.episode,
                },
                metadata={
                    "title": title,
                    "album": show,
                    "season_number": ref.season,
                    "episode_number": ref.episode,
                    "comment": url,
                },
            )
            if rezka is not None and getattr(rezka, "subtitles", False):
                subtitle = _subtitle_url(stream, getattr(rezka, "subtitle_lang", ""))
                if subtitle:
                    item.extra_opts["_subtitle_url"] = subtitle
            items.append(item)

        log.info("Resolved %d/%d episodes of %r", len(items), len(episodes), show)
        return items, problems


def _best_translator(info: SeriesInfo) -> str:
    """Default to whichever translation carries the most episodes."""
    if not info.seasons:
        return ""
    return max(info.seasons, key=lambda tid: info.episode_count(tid))
