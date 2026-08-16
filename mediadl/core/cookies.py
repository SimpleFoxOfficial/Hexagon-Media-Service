"""Browser cookie import that cannot take the app down with it.

yt-dlp's `cookiesfrombrowser` option reads the browser's cookie database at
download time, and Chrome holds an exclusive lock on that file while it is
running. The read then fails with "Could not copy Chrome cookie database", and
because it happens inside extraction it aborts the whole operation: every
download for every site fails, not just the one that wanted cookies.

So cookies are resolved here instead, once, into a Netscape cookie file that
yt-dlp consumes with the far less fragile `cookiefile` option. If the browser
will not give them up, the app carries on without cookies and says so.
"""

from __future__ import annotations

import threading
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from .. import logs, paths

log = logs.get("cookies")

# Re-reading the browser store on every download is wasteful and racy.
CACHE_SECONDS = 300

_lock = threading.Lock()
_cache: dict[str, tuple[float, Path | None, str]] = {}


def cookie_file(browser: str) -> tuple[Path | None, str]:
    """Return (path, problem). `path` is None when cookies are unavailable.

    `problem` is an empty string on success, otherwise a sentence fit to show
    the user.
    """
    browser = (browser or "").strip().lower()
    if not browser:
        return None, ""

    with _lock:
        cached = _cache.get(browser)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1], cached[2]

        path, problem = _extract(browser)
        _cache[browser] = (time.time(), path, problem)
        return path, problem


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _extract(browser: str) -> tuple[Path | None, str]:
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except ImportError:
        return None, "yt-dlp is not available, so browser cookies cannot be read."

    try:
        jar = extract_cookies_from_browser(browser)
    except Exception as exc:
        message = str(exc)
        log.warning("Could not read cookies from %s: %s", browser, message)
        return None, _explain(browser, message)

    target = paths.cache_dir() / f"cookies-{browser}.txt"
    try:
        out = MozillaCookieJar(str(target))
        count = 0
        for cookie in jar:
            # A session cookie with no expiry cannot be written to this format;
            # give it a far-future one so it survives the round trip.
            if not cookie.expires:
                cookie.expires = int(time.time()) + 30 * 24 * 3600
            out.set_cookie(cookie)
            count += 1
        out.save(ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        log.warning("Could not write the cookie file: %s", exc)
        return None, f"Cookies were read from {browser} but could not be saved: {exc}"

    if count == 0:
        return None, f"{browser.capitalize()} returned no cookies."

    log.info("Exported %d cookies from %s to %s", count, browser, target)
    return target, ""


def _explain(browser: str, message: str) -> str:
    lowered = message.lower()
    if "could not copy" in lowered or "database" in lowered or "permission" in lowered:
        return (
            f"{browser.capitalize()} is holding its cookie database open. "
            f"Close {browser.capitalize()} completely and try again, or pick a "
            "different browser. Downloads continue without cookies for now."
        )
    if "unsupported" in lowered or "not find" in lowered or "no such" in lowered:
        return (
            f"No {browser.capitalize()} profile was found on this machine. "
            "Downloads continue without cookies."
        )
    return f"Cookies could not be read from {browser.capitalize()}: {message}"
