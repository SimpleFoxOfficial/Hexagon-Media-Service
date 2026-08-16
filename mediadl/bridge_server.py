"""Local bridge the browser extension talks to.

HDRezka gates its pages behind a bot check that a Python HTTP client cannot
pass, and should not try to. The browser already passes it, so the page is read
there: an extension running on the tab hands the resolved player data to this
server, which queues it like any other download.

Hardening, because a local port is reachable by any page in the browser:

* bound to 127.0.0.1 only, never a routable interface
* every request must carry the pairing token, which is generated per install
  and shown in the app
* CORS is granted only to extension origins, so a web page cannot read replies
* request bodies are size-capped and must be JSON objects
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import logs, paths

log = logs.get("bridge")

HOST = "127.0.0.1"
DEFAULT_PORT = 47615
MAX_BODY = 4 * 1024 * 1024


def _token_path():
    return paths.config_dir() / "bridge-token.txt"


def load_or_create_token() -> str:
    path = _token_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except OSError:
        pass

    token = secrets.token_urlsafe(24)
    try:
        path.write_text(token, encoding="utf-8")
    except OSError:
        log.warning("Could not persist the bridge token; it will change on restart")
    return token


class BridgeServer:
    def __init__(self, on_capture, port: int = DEFAULT_PORT, handlers: dict | None = None):
        self.on_capture = on_capture
        #: path -> callable(payload) -> dict, for the extension's other calls
        self.handlers = handlers or {}
        self.port = port
        self.token = load_or_create_token()
        self.connected = False
        self._httpd = None
        self._thread = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> bool:
        handler = _make_handler(self)

        # On Windows SO_REUSEADDR lets a second server bind a port that is
        # already listening, and requests then go to whichever one the OS
        # picks. A stale instance would silently keep answering, so refuse to
        # share the port and move to the next one instead.
        class _ExclusiveServer(ThreadingHTTPServer):
            allow_reuse_address = False
            daemon_threads = True

        for candidate in range(self.port, self.port + 12):
            try:
                self._httpd = _ExclusiveServer((HOST, candidate), handler)
                self.port = candidate
                break
            except OSError:
                continue
        else:
            log.error("No free port for the bridge in %d..%d", self.port, self.port + 11)
            return False

        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="mediadl-bridge", daemon=True
        )
        self._thread.start()
        log.info("Bridge listening on %s", self.url)
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass

    def info(self) -> dict:
        return {
            "url": self.url,
            "token": self.token,
            "connected": self.connected,
            "extensionDir": str(paths.bundle_dir().parent / "extension"),
        }


def _make_handler(bridge: BridgeServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "MediaDownloaderBridge/1"

        def log_message(self, fmt, *args):  # noqa: A003 - silence stderr spam
            log.debug("bridge %s", fmt % args)

        # Only an extension may read our replies. A page on any site can still
        # send a request, but without the token it gets nowhere, and without
        # this header it cannot see the response either.
        def _cors(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin.startswith(("chrome-extension://", "moz-extension://")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge-Token")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self) -> bool:
            return secrets.compare_digest(
                self.headers.get("X-Bridge-Token", ""), bridge.token
            )

        def do_OPTIONS(self):  # noqa: N802
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):  # noqa: N802
            if not self._authorised():
                self._send(401, {"error": "bad token"})
                return
            bridge.connected = True

            if self.path == "/ping":
                self._send(200, {"ok": True, "app": "Media Downloader"})
                return

            handler = bridge.handlers.get(self.path)
            if handler is None:
                self._send(404, {"error": "not found"})
                return
            try:
                self._send(200, handler({}) or {})
            except Exception as exc:
                logs.exception(log, f"GET {self.path} failed", exc)
                self._send(500, {"error": str(exc)})

        def do_POST(self):  # noqa: N802
            if self.path != "/capture" and self.path not in bridge.handlers:
                self._send(404, {"error": "not found"})
                return
            if not self._authorised():
                log.warning("Rejected an unauthorised capture from %s", self.client_address[0])
                self._send(401, {"error": "bad token"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY:
                self._send(413, {"error": "bad body size"})
                return

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "malformed JSON"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "expected an object"})
                return

            bridge.connected = True
            handler = bridge.handlers.get(self.path) or (
                bridge.on_capture if self.path == "/capture" else None
            )
            try:
                result = handler(payload)
            except Exception as exc:
                logs.exception(log, f"POST {self.path} failed", exc)
                self._send(500, {"error": str(exc)})
                return

            self._send(200, {"ok": True, **(result or {})})

    return Handler
