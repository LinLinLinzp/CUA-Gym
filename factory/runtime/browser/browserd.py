#!/usr/bin/env python3
"""Root-owned browser daemon: the agent's only way onto the task websites.

The agent reaches it through the browser MCP server (browser_mcp.py, POST /act
on 127.0.0.1:8079) and gets screenshots back; it never sees the DOM,
selectors, or site APIs. At boot one tab per task site is opened, like a
desktop where the apps are already up.

Every page request is intercepted:
  * origins listed in config.json are forwarded to sitehost with the secret
    header, so real-looking URLs (https://mail.google.com/...) work offline;
  * other URLs are served from the offline asset cache when present;
  * everything else is aborted (no internet at rollout time).
"""

import asyncio
import json
import os
import pwd
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from playwright.async_api import async_playwright

CONFIG = json.loads(Path(os.environ.get("CUA_CONFIG", "/opt/cua/config.json")).read_text())
VAR_DIR = Path(os.environ.get("CUA_VAR_DIR", "/var/lib/cua"))
ASSET_DIR = Path(os.environ.get("CUA_ASSET_DIR", "/opt/cua/assets"))
SHOT_DIR = Path(os.environ.get("CUA_SHOT_DIR", "/logs/agent/browser"))
DOWNLOAD_DIR = Path(os.environ.get("CUA_DOWNLOAD_DIR", "/workspace/downloads"))
UPLOAD_ROOT = Path(os.environ.get("CUA_UPLOAD_ROOT", "/workspace"))
SITEHOST = "http://127.0.0.1:8090"
SECRET = (VAR_DIR / "secret").read_text().strip()
AGENT = pwd.getpwnam(os.environ.get("CUA_AGENT_USER", "agent"))
VIEWPORT = {"width": 1280, "height": 800}
MAX_ACTIONS = 12
# Debounced mocks flush state ~300-500 ms after a change; leave them time
# before anything that unloads the page.
SETTLE_MS = 700

ORIGINS = {
    origin.rstrip("/"): name
    for name, site in CONFIG["sites"].items()
    for origin in site["origins"]
}
# Chromium sends <a download href="http..."> straight to its download manager,
# bypassing request interception, so the file request leaks to the (dead)
# network. Dropping the attribute at click time turns it into a normal routed
# navigation; sitehost's Content-Disposition: attachment still makes it a
# download with the right filename. blob:/data: links keep the attribute.
STRIP_DOWNLOAD_ATTR = """
document.addEventListener('click', (e) => {
  const a = e.target && e.target.closest && e.target.closest('a[download][href]');
  if (a && /^https?:$/.test(a.protocol)) a.removeAttribute('download');
}, true);
"""
ASSETS = json.loads((ASSET_DIR / "index.json").read_text()) if (ASSET_DIR / "index.json").exists() else {}

class Browser:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.pages = []
        self.active = 0
        self.shot_index = 0
        self.downloads = []
        self.pending = []
        self.parked = []  # (page, url) unloaded while sitehost rewrites state

    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            # Fail closed: anything that escapes request interception can't resolve.
            "--host-resolver-rules=MAP * ~NOTFOUND",
        ])
        self.context = await self.browser.new_context(
            viewport=VIEWPORT,
            locale=CONFIG.get("locale", "en-US"),
            timezone_id=CONFIG.get("timezone", "America/Los_Angeles"),
            accept_downloads=True,
            service_workers="block",
        )
        await self.context.route("**/*", self.route)
        await self.context.add_init_script(STRIP_DOWNLOAD_ATTR)
        self.context.on("page", self.adopt)
        for url in CONFIG.get("start_urls") or ["about:blank"]:
            page = await self.context.new_page()
            if url != "about:blank":
                await page.goto(url, wait_until="load")
        self.active = 0
        await self.pages[0].bring_to_front()

    # --- network --------------------------------------------------------
    async def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        site = ORIGINS.get(f"{url.scheme}://{url.netloc}")
        if site:
            target = SITEHOST + (url.path or "/") + (f"?{url.query}" if url.query else "")
            headers = {**request.headers, "x-cua-site": site, "x-cua-key": SECRET}
            try:
                response = await route.fetch(url=target, headers=headers, max_redirects=0)
                await route.fulfill(response=response)
            except Exception:
                await route.fulfill(status=502, body="Site unavailable")
            return
        cached = ASSETS.get(request.url)
        if cached:
            await route.fulfill(
                status=200,
                path=str(ASSET_DIR / cached["file"]),
                headers={"Content-Type": cached["type"], "Access-Control-Allow-Origin": "*"},
            )
            return
        await route.abort("internetdisconnected")

    def adopt(self, page):
        if page in self.pages:
            return
        self.pages.append(page)
        self.active = len(self.pages) - 1
        page.on("download", lambda d, p=page: self.pending.append(asyncio.ensure_future(self.save_download(d, p))))
        page.on("close", lambda p: self.forget(p))

    def forget(self, page):
        if page in self.pages:
            self.pages.remove(page)
            self.active = min(self.active, len(self.pages) - 1)

    async def save_download(self, download, source=None):
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        name = Path(download.suggested_filename).name or "download"
        target = DOWNLOAD_DIR / name
        stem, suffix, n = target.stem, target.suffix, 1
        while target.exists():
            target = DOWNLOAD_DIR / f"{stem} ({n}){suffix}"
            n += 1
        await download.save_as(target)
        os.chown(target, AGENT.pw_uid, AGENT.pw_gid)
        self.downloads.append(str(target))
        # A target=_blank link to a file opens a popup that stays blank while
        # the download is attributed to the opener (screenshots of the blank
        # popup hang). Close such popups and go back to the opener.
        if source is not None:
            for page in list(self.pages):
                if page is source or page.url not in ("", "about:blank"):
                    continue
                try:
                    opener = await page.opener()
                except Exception:
                    opener = None
                if opener is source:
                    await page.close()
            if source in self.pages:
                self.active = self.pages.index(source)

    @property
    def page(self):
        if not self.pages:
            raise ActionError("No open tab; use new_tab.")
        return self.pages[self.active]

    # --- actions --------------------------------------------------------
    async def act(self, actions):
        if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
            raise ActionError(f"Send 1-{MAX_ACTIONS} actions.")
        async with self.lock:
            self.downloads = []
            for action in actions:
                await self.perform(action)
            await asyncio.sleep(0.4)
            if self.pending:
                await asyncio.gather(*self.pending, return_exceptions=True)
                self.pending = []
            try:
                await self.page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            return await self.observe()

    async def perform(self, a):
        kind = a.get("kind")
        page = self.page if kind not in ("new_tab", "switch_tab", "close_tab") else None
        mouse = page.mouse if page else None
        if kind == "goto":
            await self.settle()
            await self.page.goto(check_url(a["url"]), wait_until="load")
        elif kind == "click":
            await mouse.click(a["x"], a["y"], button=a.get("button", "left"), click_count=int(a.get("clicks", 1)))
        elif kind == "move":
            await mouse.move(a["x"], a["y"])
        elif kind == "drag":
            await mouse.move(a["x"], a["y"])
            await mouse.down()
            await mouse.move(a["to_x"], a["to_y"], steps=12)
            await mouse.up()
        elif kind == "type":
            await page.keyboard.type(str(a["text"]), delay=5)
        elif kind == "key":
            for _ in range(int(a.get("repeat", 1))):
                await page.keyboard.press(a["key"])
        elif kind == "scroll":
            await mouse.move(a.get("x", VIEWPORT["width"] // 2), a.get("y", VIEWPORT["height"] // 2))
            await mouse.wheel(a.get("dx", 0), a.get("dy", 0))
            await asyncio.sleep(0.2)
        elif kind == "upload":
            paths = [check_upload(p) for p in a["paths"]]
            async with page.expect_file_chooser(timeout=10000) as chooser:
                await mouse.click(a["x"], a["y"])
            await (await chooser.value).set_files(paths)
        elif kind == "wait":
            await asyncio.sleep(min(int(a.get("ms", 1000)), 10000) / 1000)
        elif kind in ("back", "forward", "reload"):
            await self.settle()
            await getattr(page, "go_back" if kind == "back" else "go_forward" if kind == "forward" else "reload")()
        elif kind == "new_tab":
            await self.settle()
            new = await self.context.new_page()
            if a.get("url"):
                await new.goto(check_url(a["url"]), wait_until="load")
        elif kind == "switch_tab":
            index = int(a["index"])
            if not 0 <= index < len(self.pages):
                raise ActionError("No such tab.")
            self.active = index
            target = self.pages[index]
            await target.bring_to_front()
            # Mocks keep state client-side and push full snapshots; a second tab
            # on the same site would push stale data. localStorage is shared, so
            # reloading picks up the other tab's latest state.
            origin = origin_of(target.url)
            if origin in ORIGINS and any(origin_of(p.url) == origin for p in self.pages if p is not target):
                await asyncio.sleep(SETTLE_MS / 1000)
                await target.reload(wait_until="load")
        elif kind == "close_tab":
            await self.settle()
            await self.pages[int(a.get("index", self.active))].close()
        elif kind == "view":
            pass
        else:
            raise ActionError(f"Unknown action kind: {kind!r}")

    async def settle(self):
        if self.pages:
            await asyncio.sleep(SETTLE_MS / 1000)

    async def observe(self):
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        self.shot_index += 1
        path = SHOT_DIR / f"{self.shot_index:04d}.png"
        await self.page.screenshot(path=str(path))
        os.chmod(path, 0o644)
        tabs = []
        for i, page in enumerate(self.pages):
            try:
                title = await page.title()
            except Exception:
                title = ""
            tabs.append({"index": i, "title": title, "url": page.url, "active": i == self.active})
        return {"url": self.page.url, "tabs": tabs, "screenshot_path": str(path), "downloaded_files": self.downloads}


class ActionError(Exception):
    pass


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def check_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ActionError("Only http(s) URLs can be opened.")
    return url


def check_upload(path: str) -> str:
    real = Path(path).resolve()
    if UPLOAD_ROOT.resolve() not in real.parents or not real.is_file():
        raise ActionError(f"Uploads must be existing files under {UPLOAD_ROOT}.")
    return str(real)


async def main():
    browser = Browser()
    await browser.start()

    async def act(request):
        try:
            payload = await request.json()
            result = await browser.act(payload.get("actions"))
            return web.json_response(result)
        except ActionError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # surface Playwright errors (timeouts etc.) to the agent
            message = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
            return web.json_response({"error": message}, status=400)

    async def refresh(request):
        """sitehost is rewriting server state (oracle apply, lever L14 triggers).

        Mocks keep a client copy (memory + localStorage) and post it back whole,
        so a tab still holding the old state would undo the write. sitehost
        calls phase "park" before writing (flush pending saves, drop the client
        copy, unload the tab) and "restore" after (reopen the tab on the new
        state). No phase: drop the client copy and reload in place.
        """
        if request.headers.get("x-cua-key") != SECRET:
            return web.json_response({"error": "forbidden"}, status=403)
        payload = await request.json()
        origins, phase = payload.get("origins", []), payload.get("phase")
        async with browser.lock:
            if phase == "restore":
                parked, browser.parked = browser.parked, []
                for p, url in parked:
                    if p in browser.pages:
                        await p.goto(url, wait_until="load")
                return web.json_response({"ok": True})
            await asyncio.sleep(SETTLE_MS / 1000)
            for origin in origins:
                tabs = [p for p in browser.pages if origin_of(p.url) == origin]
                if phase == "park":  # unload first so nothing rewrites localStorage after the clear
                    for p in tabs:
                        browser.parked.append((p, p.url))
                        await p.goto("about:blank")
                page = browser.pages[0] if browser.pages else await browser.context.new_page()
                cdp = await browser.context.new_cdp_session(page)
                await cdp.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "local_storage"})
                await cdp.detach()
                if phase != "park":
                    for p in tabs:
                        await p.reload(wait_until="load")
        return web.json_response({"ok": True})

    async def park(request):
        """Oracle only: let pending client writes land, then blank every tab so no page can
        push stale state over the golden state that is about to be written."""
        if request.headers.get("x-cua-key") != SECRET:
            return web.json_response({"error": "forbidden"}, status=403)
        async with browser.lock:
            await asyncio.sleep(3)
            for p in list(browser.pages):
                await p.goto("about:blank")
        return web.json_response({"ok": True})

    async def health(_request):
        return web.json_response({"ok": True, "tabs": len(browser.pages)})

    app = web.Application()
    app.add_routes([web.post("/act", act), web.post("/__refresh", refresh), web.post("/__park", park), web.get("/health", health)])
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8079).start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
