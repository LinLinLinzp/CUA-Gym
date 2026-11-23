#!/usr/bin/env python3
"""Collect every external asset a task's pages reference, for offline replay.

Scans site dists and seed states for absolute http(s) URLs on asset hosts
(fonts, avatars, placeholder images, CDNs), downloads them (following CSS
url(...) references), and writes <out>/index.json mapping URL -> file. browserd
fulfils matching requests from this cache; anything else is blocked.
"""

import hashlib
import json
import mimetypes
import os
import re
import sys
import urllib.request
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
CACHE = FACTORY / "build" / "asset_cache"
URL = re.compile(r"""https?://[^\s"'`()<>\\]+""")
ASSET_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com", "ssl.gstatic.com", "www.gstatic.com", "picsum.photos",
    "fastly.picsum.photos", "i.pravatar.cc", "ui-avatars.com", "api.dicebear.com", "placehold.co",
    "upload.wikimedia.org", "unpkg.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "images.unsplash.com",
    "lh3.googleusercontent.com", "a.slack-edge.com", "cdn.shopify.com",
)
for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
    os.environ.pop(var, None)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OPENER.addheaders = [("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")]


def candidates(paths):
    urls = set()
    for root in paths:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.suffix in (".html", ".js", ".css", ".json")]
        for file in files:
            for url in URL.findall(file.read_text(errors="ignore")):
                url = url.rstrip(".,;")
                if url.split("/")[2].split(":")[0] in ASSET_HOSTS and "${" not in url:
                    urls.add(url)
    return urls


def fetch(url):
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    meta = CACHE / f"{key}.json"
    if meta.exists():
        return json.loads(meta.read_text())
    try:
        with OPENER.open(url, timeout=30) as response:
            body = response.read()
            ctype = response.headers.get_content_type()
    except Exception as exc:  # unreachable asset: page renders without it
        print(f"skip {url}: {exc}", file=sys.stderr)
        return None
    ext = mimetypes.guess_extension(ctype) or ""
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key}{ext}").write_bytes(body)
    entry = {"file": f"{key}{ext}", "type": ctype}
    meta.write_text(json.dumps(entry))
    return entry


def collect(paths, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    index, queue = {}, sorted(candidates(paths))
    while queue:
        url = queue.pop()
        if url in index:
            continue
        entry = fetch(url)
        if not entry:
            continue
        index[url] = entry
        (out / entry["file"]).write_bytes((CACHE / entry["file"]).read_bytes())
        if entry["type"] == "text/css":  # Google Fonts CSS points at font files
            queue += [u for u in URL.findall((CACHE / entry["file"]).read_text(errors="ignore")) if u not in index]
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return index


if __name__ == "__main__":
    result = collect([Path(p) for p in sys.argv[2:]], Path(sys.argv[1]))
    print(f"{len(result)} assets")
