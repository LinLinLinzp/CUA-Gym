"""Serve the existing site runtime on private HTTPS desktop origins."""

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit


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
            return site, url
        cached = CACHE.get(f"https://{self.headers.get('Host', '')}{self.path}")
        if cached and self.command in {"GET", "HEAD"}:
            self.send(200, (ASSETS / cached["file"]).read_bytes(), cached["type"],
                      {"Access-Control-Allow-Origin": "*"})
            return None
        self.send(404, b"Not found", "text/plain")
        return None


with ThreadingHTTPServer(("127.0.0.1", 443), OfflineBrowserHandler) as server:
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(RUNTIME / "offline.crt", RUNTIME / "offline.key")
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
