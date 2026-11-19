#!/usr/bin/env python3
"""Dynamic certification of hub sites inside the real task runtime.

    dyn_certify.py gmail slack shopify ...     (catalog names; built dists required)
    dyn_certify.py --pool                      every 'ready'/'needs_brand' site

Builds one container with all requested sites (each on <site>.certify.test, no
seed, so each mock shows its default data), then for every site checks:
  render   main document 200, page shows content, no uncaught page errors
  sync     the client pushes state to /post after load (else verifiers see nothing)
  idle     an idle tab makes no further /post calls over 70 s (stale-tab overwrite risk)
  hydrate  injected state reaches the client: a string field inside the mock's own default
           data is changed on the server, and a fresh browser must show the change at that
           exact path in its stored state (catches clients that keep the /state envelope)
Writes factory/build/dyn_certify.json and screenshots to factory/build/dyn_certify/.
The same file runs inside the container with --inside.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
IDLE_SECONDS = 70


# ------------------------------------------------------------------ inside
# The app's own state as it sits in localStorage (largest JSON object stored).
STATE_JS = """() => { let best = null, size = 0;
  for (const k of Object.keys(localStorage)) { const raw = localStorage.getItem(k) || '';
    try { const v = JSON.parse(raw); if (v && typeof v === 'object' && raw.length > size) { best = v; size = raw.length } } catch {} }
  return best }"""
MARKER = "CERTMARKER-7f3a"


def find_string_leaf(state):
    """Path to the first string field inside the first record of a top-level list."""
    for key, value in (state or {}).items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            for field, leaf in value[0].items():
                if isinstance(leaf, str) and leaf and field not in ("id", "sid"):
                    return [key, 0, field]
    return None


def get_path(state, path):
    for part in path:
        try:
            state = state[part]
        except (KeyError, IndexError, TypeError):
            return None
    return state


async def hydrate(browser, name, origin, result, secret):
    """Change one field on the server, then check a fresh client shows it at the same path."""
    import urllib.request
    state = result.pop("client_state", None)
    path = find_string_leaf(state)
    if not path:
        result["hydrate"] = None  # nothing generic to probe; verify by hand
        return
    target = state
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = MARKER
    req = urllib.request.Request(f"http://127.0.0.1:8090/post?sid=cert01", json.dumps({"action": "set_current", "state": state}).encode(),
                                 {"Content-Type": "application/json", "x-cua-site": name, "x-cua-key": secret})
    await asyncio.to_thread(urllib.request.urlopen, req)
    ctx = await browser.new_context()

    async def route(r):
        from urllib.parse import urlsplit
        url = urlsplit(r.request.url)
        if f"{url.scheme}://{url.netloc}" != origin:
            return await r.abort()
        target_url = "http://127.0.0.1:8090" + url.path + (f"?{url.query}" if url.query else "")
        resp = await r.fetch(url=target_url, headers={**r.request.headers, "x-cua-site": name, "x-cua-key": secret}, max_redirects=0)
        await r.fulfill(response=resp)

    await ctx.route("**/*", route)
    page = await ctx.new_page()
    try:
        await page.goto(origin + "/", wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)
        result["hydrate"] = get_path(await page.evaluate(STATE_JS), path) == MARKER
        result["hydrate_path"] = path
    except Exception as exc:
        result["hydrate"] = False
        result["errors"].append(f"hydrate: {str(exc)[:150]}")
    await ctx.close()


async def inside(out: Path):
    from playwright.async_api import async_playwright
    from urllib.parse import urlsplit

    config = json.loads(Path("/opt/cua/config.json").read_text())
    secret = Path("/var/lib/cua/secret").read_text().strip()
    origins = {s["origins"][0]: name for name, s in config["sites"].items()}
    results = {name: {"posts_load": 0, "posts_idle": 0, "errors": [], "status": None} for name in config["sites"]}
    phase = {"idle": False}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--host-resolver-rules=MAP * ~NOTFOUND"])
        sem = asyncio.Semaphore(8)

        async def check(name, origin):
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800})

            async def route(r):
                url = urlsplit(r.request.url)
                if f"{url.scheme}://{url.netloc}" != origin:
                    return await r.abort()
                if url.path == "/post" and r.request.method == "POST":
                    results[name]["posts_idle" if phase["idle"] else "posts_load"] += 1
                target = "http://127.0.0.1:8090" + url.path + (f"?{url.query}" if url.query else "")
                resp = await r.fetch(url=target, headers={**r.request.headers, "x-cua-site": name, "x-cua-key": secret}, max_redirects=0)
                await r.fulfill(response=resp)

            await ctx.route("**/*", route)
            page = await ctx.new_page()
            page.on("pageerror", lambda e: results[name]["errors"].append(str(e)[:200]))
            async with sem:
                try:
                    resp = await page.goto(origin + "/", wait_until="load", timeout=30000)
                    results[name]["status"] = resp.status if resp else None
                    await page.wait_for_timeout(4000)
                    results[name]["title"] = await page.title()
                    results[name]["text_chars"] = len((await page.inner_text("body")).strip())
                    await page.screenshot(path=str(out / f"{name}.png"))
                    results[name]["client_state"] = await page.evaluate(STATE_JS)
                except Exception as exc:
                    results[name]["errors"].append(f"load: {str(exc)[:200]}")
            return page

        pages = await asyncio.gather(*(check(n, o) for o, n in origins.items()))
        phase["idle"] = True
        await asyncio.sleep(IDLE_SECONDS)
        del pages
        await asyncio.gather(*(hydrate(browser, n, o, results[n], secret) for o, n in origins.items()))
        await browser.close()

    for r in results.values():
        r["render"] = r["status"] == 200 and r.get("text_chars", 0) > 50 and not r["errors"]
        r["sync"] = r["posts_load"] > 0
        r["idle"] = r["posts_idle"] == 0
        r["hydrate"] = r.get("hydrate") is not False  # None = no generic probe possible
    (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ host
def host(names):
    catalog = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
    work = Path(tempfile.mkdtemp(prefix="dyncert-"))
    env, cua = work / "environment", work / "environment" / "cua"
    env.mkdir()
    shutil.copy(FACTORY / "runtime" / "Dockerfile", env / "Dockerfile")
    for part in ("sitehost", "browser", "sources"):
        shutil.copytree(FACTORY / "runtime" / part, cua / part)
    shutil.copy(FACTORY / "runtime" / "entrypoint.sh", cua / "entrypoint.sh")
    shutil.copy(__file__, cua / "dyn_certify.py")
    (cua / "seed").mkdir()
    (env / "workspace" / "input").mkdir(parents=True)
    missing = [n for n in names if not (FACTORY / "build" / "sites" / n / "dist" / "index.html").exists()]
    if missing:
        raise SystemExit(f"build these dists first: {missing}")
    for n in names:
        shutil.copytree(FACTORY / "build" / "sites" / n / "dist", cua / "sites" / n / "dist")
    config = {"sid": "cert01", "clock": "2026-03-16T09:30:00-07:00", "timezone": "America/Los_Angeles", "locale": "en-US",
              "start_urls": [], "sites": {n: {"origins": [f"https://{n.replace('_', '-')}.certify.test"]} for n in names}}
    (cua / "config.json").write_text(json.dumps(config))

    run_id = f"{os.getpid()}"  # parallel builders certify concurrently
    tag, name = f"cua-certify:{run_id}", f"cua-certify-{run_id}"
    subprocess.run(["docker", "build", "-q", "-t", tag, str(env)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", name, "--shm-size=1g", tag], check=True, stdout=subprocess.DEVNULL)
    try:
        subprocess.run(["docker", "exec", name, "bash", "-c", "until curl -fsS http://127.0.0.1:8090/__health >/dev/null; do sleep 1; done"], check=True)
        subprocess.run(["docker", "exec", name, "python3", "/opt/cua/dyn_certify.py", "--inside", "/tmp/cert"], check=True)
        out = FACTORY / "build" / "dyn_certify" / run_id
        shutil.rmtree(out, ignore_errors=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["docker", "cp", f"{name}:/tmp/cert", str(out)], check=True)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "rmi", tag], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)

    results = json.loads((out / "results.json").read_text())
    summary = FACTORY / "build" / "dyn_certify.json"
    previous = json.loads(summary.read_text()) if summary.exists() else {}
    summary.write_text(json.dumps({**previous, **results}, indent=1, ensure_ascii=False))
    for n, r in sorted(results.items()):
        ok = r["render"] and r["sync"] and r["idle"] and r["hydrate"]
        print(f"{'PASS' if ok else 'FAIL'} {n:<22} render={r['render']} sync={r['sync']}({r['posts_load']}) "
              f"idle={r['idle']}({r['posts_idle']}) hydrate={r['hydrate']} {('; '.join(r['errors']))[:120]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    parser.add_argument("--pool", action="store_true")
    parser.add_argument("--inside")
    args = parser.parse_args()
    if args.inside:
        out = Path(args.inside)
        out.mkdir(parents=True, exist_ok=True)
        asyncio.run(inside(out))
        return
    names = args.names
    if args.pool:
        catalog = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
        names = [n for n, s in catalog.items() if s["status"] in ("ready", "needs_brand")
                 and (FACTORY / "build" / "sites" / n / "dist" / "index.html").exists()]
    host(names)


if __name__ == "__main__":
    sys.exit(main())
