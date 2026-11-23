"""Serve the existing site runtime on private HTTPS desktop origins."""

from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import ssl
import sys
from threading import Lock
from urllib.parse import parse_qs, urlsplit


RUNTIME = Path("/opt/cua")
sys.path.insert(0, str(RUNTIME / "sitehost"))
from sitehost import CONFIG, Handler  # noqa: E402


ORIGINS = {
    urlsplit(origin).netloc: site
    for site, settings in CONFIG["sites"].items()
    for origin in settings["origins"]
}
ASSETS = RUNTIME / "assets"
CACHE = json.loads((ASSETS / "index.json").read_text())


class OfflineBrowserHandler(Handler):
    def authorize(self):
        site = ORIGINS.get(self.headers.get("Host", "").lower())
        url = urlsplit(self.path)
        if url.path == "/__health" and site:
            self.send_json({"ok": True})
            return None
        if site:
            if url.path.startswith("/__") or (
                url.path in {"/go", "/state", "/post", "/upload"}
                and self.headers.get("Sec-Fetch-Mode") == "navigate"
            ):
                self.send(404, b"Not found", "text/plain")
                return None
            if (CONFIG.get("reactive_slack") and site == "slack" and url.path == "/state"
                    and parse_qs(url.query).get("live") == ["1"]
                    and self.headers.get("Sec-Fetch-Site") != "same-origin"):
                self.send(404, b"Not found", "text/plain")
                return None
            return site, url
        cached = CACHE.get(f"https://{self.headers.get('Host', '')}{self.path}")
        if cached and self.command in {"GET", "HEAD"}:
            self.send(200, (ASSETS / cached["file"]).read_bytes(), cached["type"],
                      {"Access-Control-Allow-Origin": "*"})
            return None
        self.send(404, b"Not found", "text/plain")
        return None


def task_owned_handler(site):
    app_dir = RUNTIME / "sites" / site / "app"
    os.environ["CUA_STATE_FILE"] = f"/var/lib/cua/state/{site}/current.json"
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location("task_browser_app", app_dir / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    writes = Lock()

    class TaskBrowserHandler(module.Handler):
        def do_POST(self):
            # Each business write reads, modifies and atomically replaces the site's snapshot.
            with writes:
                super().do_POST()

        def parse_request(self):
            if not super().parse_request():
                return False
            path = urlsplit(self.path).path
            if ORIGINS.get(self.headers.get("Host", "").lower()) != site:
                self.send_error(404)
                return False
            if path == "/__health":
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
            if path.startswith("/__") or path in {"/state", "/post", "/go", "/upload"}:
                self.send_error(404)
                return False
            return True

    return TaskBrowserHandler


handler = task_owned_handler(CONFIG["python_site"]) if CONFIG.get("python_site") else OfflineBrowserHandler
with ThreadingHTTPServer(("127.0.0.1", 443), handler) as server:
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(RUNTIME / "offline.crt", RUNTIME / "offline.key")
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
