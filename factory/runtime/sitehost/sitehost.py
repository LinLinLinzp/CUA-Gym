#!/usr/bin/env python3
"""Single-process host for every mock site in a task container.

Serves each site's prebuilt Vite dist and re-implements the CUA-Gym-Hub state
API (/state, /post, /go, /upload, /files) against root-only files, so the
verifier can read final state straight from disk.

Only the browser daemon can reach it: every request must carry the shared
secret (x-cua-key) and the target site (x-cua-site). The agent user can open a
TCP connection to the port but cannot read the secret.

Layout (all root-only):
  /opt/cua/config.json            {"sid": ..., "clock": ..., "sites": {name: {...}}}
  /opt/cua/sites/<site>/dist/     prebuilt static bundle
  /var/lib/cua/secret             random key shared with browserd
  /var/lib/cua/state/<site>/initial.json, current.json
  /var/lib/cua/files/<site>/<sid>/<name>
  /opt/cua/oracle.sha256          hash of the oracle token (plaintext only in solution/)
  /opt/cua/triggers.json          optional reactive world (lever L14), see fire_triggers()

The oracle (solution/solve.sh) runs as the unprivileged agent user, so it
applies golden state through POST /__oracle/apply with that token.
"""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

CONFIG_PATH = Path(os.environ.get("CUA_CONFIG", "/opt/cua/config.json"))
SITES_DIR = Path(os.environ.get("CUA_SITES_DIR", "/opt/cua/sites"))
VAR_DIR = Path(os.environ.get("CUA_VAR_DIR", "/var/lib/cua"))

CONFIG = json.loads(CONFIG_PATH.read_text())
SID = CONFIG["sid"]
SECRET = (VAR_DIR / "secret").read_text().strip()
ORACLE_HASH_PATH = CONFIG_PATH.parent / "oracle.sha256"
ORACLE_HASH = ORACLE_HASH_PATH.read_text().strip() if ORACLE_HASH_PATH.exists() else None
LOCK = threading.Lock()
# Task clock: fixed at boot so "now" advances in real time and stays consistent across
# page loads and sites (the page shim and trigger timestamps share this offset).
CLOCK_OFFSET_MS = None
if CONFIG.get("clock"):
    from datetime import datetime, timezone
    CLOCK_OFFSET_MS = int(datetime.fromisoformat(CONFIG["clock"]).timestamp() * 1000 - time.time() * 1000)
TRIGGERS_PATH = CONFIG_PATH.parent / "triggers.json"
TRIGGERS = json.loads(TRIGGERS_PATH.read_text()) if TRIGGERS_PATH.exists() else []
FIRED_PATH = VAR_DIR / "triggers_fired.json"
# Once the oracle has written the golden state nothing else may change it: tabs opened
# before the apply hold the baseline in memory/localStorage and post it back whole
# (Gmail on load and on reload, BambooHR on first load), which undid the golden on the
# platform. The flag survives a sitehost restart.
ORACLE_FLAG = VAR_DIR / "oracle_applied"
# One line per state write, copied into the verifier logs so a bad grade can be traced.
WRITES_LOG = VAR_DIR / "writes.log"


def safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)


def state_dir(site: str) -> Path:
    path = VAR_DIR / "state" / site
    path.mkdir(parents=True, exist_ok=True)
    return path


def files_dir(site: str) -> Path:
    path = VAR_DIR / "files" / site / safe(SID)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def log_write(kind: str, site: str, body: bytes = b"", note: str = "") -> None:
    try:
        line = {"t": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z",
                "kind": kind, "site": site, "bytes": len(body), "sha": hashlib.sha256(body).hexdigest()[:12]}
        if note:
            line["note"] = note
        with WRITES_LOG.open("a") as fh:
            fh.write(json.dumps(line) + "\n")
    except OSError:
        pass


def write_json(path: Path, value) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def deep_merge(target, source):
    result = dict(target)
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def flat_diff(initial, current):
    """Same top-level {key: {added|modified}} shape the hub's /go returns."""
    diff = {}
    for key, value in (current or {}).items():
        if not initial or json.dumps(value, sort_keys=True) != json.dumps(initial.get(key), sort_keys=True):
            diff[key] = {"added" if not initial or key not in initial else "modified": value}
    return diff


def at_path(state, path: str):
    for part in [p for p in path.split(".") if p]:
        state = state.get(part) if isinstance(state, dict) else None
    return state


def matches(record, match: dict) -> bool:
    """Field equality, or {"contains": text} for a case-insensitive substring."""
    def ok(value, want):
        if isinstance(want, dict) and "contains" in want:
            return want["contains"].lower() in str(value or "").lower()
        return value == want
    return isinstance(record, dict) and all(ok(at_path(record, k), v) for k, v in match.items())


def fire_triggers(site: str, state):
    """Reactive world: when a record matching `when` appears on `site`, apply `then` after `delay_s`.

    triggers.json: [{"id", "when": {"site", "path", "match": {field: value | {"contains": text}}},
                     "then": [{"site", "path", "append": {...}}], "delay_s": 20}]
    In `append`, "__NOW__" becomes the task-clock time of firing and "__SID__" the session id.
    Each trigger fires once. Target sites' browser tabs are refreshed so they show it.
    """
    fired = set(json.loads(FIRED_PATH.read_text())) if FIRED_PATH.exists() else set()
    for trig in TRIGGERS:
        when = trig["when"]
        if trig["id"] in fired or when["site"] != site:
            continue
        records = at_path(state, when["path"])
        if not any(matches(r, when.get("match", {})) for r in (records if isinstance(records, list) else [])):
            continue
        fired.add(trig["id"])
        FIRED_PATH.write_text(json.dumps(sorted(fired)))
        threading.Timer(float(trig.get("delay_s", 15)), apply_trigger, args=(trig,)).start()


def browser_refresh(sites, phase=None):
    """Ask browserd to drop/unload/reopen the tabs of `sites` (see its refresh())."""
    origins = [o for site in sites for o in CONFIG["sites"][site]["origins"]]
    try:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:8079/__refresh", json.dumps({"origins": origins, "phase": phase}).encode(),
            {"Content-Type": "application/json", "x-cua-key": SECRET}), timeout=60)
    except Exception:
        pass


def write_from_outside(sites, write):
    """Server-side state write the open tabs don't know about: unload them first so a
    stale client copy can't be posted over it, then reopen them on the new state."""
    browser_refresh(sites, "park")
    try:
        with LOCK:
            write()
    finally:
        browser_refresh(sites, "restore")


def apply_trigger(trig):
    def write():
        for step in trig["then"]:
            path = state_dir(step["site"]) / "current.json"
            state = read_json(path) or {}
            parent, _, key = step["path"].rpartition(".")
            holder = at_path(state, parent) if parent else state
            now_ms = time.time() * 1000 + (CLOCK_OFFSET_MS or 0)
            now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now_ms / 1000)) + f".{int(now_ms % 1000):03d}Z"
            item = json.loads(json.dumps(step["append"]).replace("__SID__", SID).replace("__NOW__", now))
            holder.setdefault(key, []).append(item)
            write_json(path, state)
            log_write("trigger", step["site"], json.dumps(item).encode(), trig["id"])
    write_from_outside(sorted({step["site"] for step in trig["then"]}), write)


def boot_script() -> bytes:
    """Injected ahead of the app bundle: pins the session id and the task clock.

    The clock shim shifts Date so "now" starts at the task's frozen timestamp
    and advances in real time.
    """
    shim = ""
    if CLOCK_OFFSET_MS is not None:
        shim = (
            "(()=>{const R=Date,off=%d;"
            "function D(...a){const d=a.length?new R(...a):new R(R.now()+off);return new.target?d:d.toString()}"
            "D.prototype=R.prototype;D.now=()=>R.now()+off;D.parse=R.parse;D.UTC=R.UTC;"
            "globalThis.Date=D})();" % CLOCK_OFFSET_MS
        )
    # Every hub mock honours ?sid= in the URL (not all fall back to
    # sessionStorage), so add it in place before the app reads location.
    sid_url = (
        "if(!new URLSearchParams(location.search).has('sid')){const u=new URL(location.href);"
        "u.searchParams.set('sid',%s);history.replaceState(history.state,'',u)}" % json.dumps(SID)
    )
    # Some mocks (quickbooks, workday) post full-state snapshots with fetch keepalive.
    # Under browserd's request interception Chromium never releases the 64 KiB
    # keepalive budget, so after ~64 KiB of posts per page load every save throws.
    # The mocks post on each change while the page is alive, so keepalive is not needed.
    nokeep = (
        "(()=>{const F=globalThis.fetch;if(!F)return;"
        "globalThis.fetch=function(u,o){if(o&&o.keepalive){o=Object.assign({},o,{keepalive:false})}"
        "return F.call(this,u,o)}})();"
    )
    script = "try{sessionStorage.setItem('mock_sid',%s);%s}catch(e){}%s%s" % (json.dumps(SID), sid_url, nokeep, shim)
    return f"<script>{script}</script>".encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nginx"
    sys_version = ""

    def log_message(self, fmt, *args):  # quiet; audit trail lives in browserd
        pass

    # --- plumbing -------------------------------------------------------
    def send(self, status: int, body: bytes, ctype: str = "application/json", extra=None):
        self.send_response(status)
        headers = {"Content-Type": ctype, "Content-Length": str(len(body)), "Cache-Control": "no-cache, no-store"}
        for key, value in {**headers, **(extra or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, value, status: int = 200):
        self.send(status, json.dumps(value, ensure_ascii=False).encode())

    def body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def authorize(self):
        url = urlsplit(self.path)
        if url.path == "/__health":
            self.send_json({"ok": True})
            return None
        if url.path == "/__oracle/apply" and self.command == "POST":
            self.oracle_apply()
            return None
        key = self.headers.get("x-cua-key", "")
        site = self.headers.get("x-cua-site", "")
        if not hmac.compare_digest(key, SECRET) or site not in CONFIG["sites"]:
            self.send(403, b"Forbidden", "text/plain")
            return None
        return site, url

    # --- verbs ----------------------------------------------------------
    def do_GET(self):
        auth = self.authorize()
        if not auth:
            return
        site, url = auth
        if url.path == "/state":
            current = read_json(state_dir(site) / "current.json")
            return self.send_json({"stored_state": current, "has_custom_state": current is not None, "sid": SID})
        if url.path == "/go":
            initial = read_json(state_dir(site) / "initial.json")
            current = read_json(state_dir(site) / "current.json") or initial
            return self.send_json({"initial_state": initial, "current_state": current, "state_diff": flat_diff(initial, current)})
        if url.path.startswith("/files/"):
            return self.serve_upload(site, url.path)
        return self.serve_static(site, url.path)

    do_HEAD = do_GET

    def do_POST(self):
        auth = self.authorize()
        if not auth:
            return
        site, url = auth
        if url.path == "/post":
            return self.handle_post(site)
        if url.path == "/upload":
            return self.handle_upload(site)
        self.send(404, b"Not found", "text/plain")

    def oracle_apply(self):
        token = self.headers.get("x-cua-oracle", "").encode()
        if not ORACLE_HASH or not hmac.compare_digest(hashlib.sha256(token).hexdigest(), ORACLE_HASH):
            return self.send(403, b"Forbidden", "text/plain")
        # Golden states reference attachments as /files/__SID__/... just like seeds do.
        states = json.loads((self.body() or b"{}").decode().replace("__SID__", SID))
        unknown = set(states) - set(CONFIG["sites"])
        if unknown:
            return self.send_json({"error": f"unknown sites {sorted(unknown)}"}, 400)
        def write():
            for site, state in states.items():
                write_json(state_dir(site) / "current.json", state)
                log_write("oracle", site, json.dumps(state).encode())
            ORACLE_FLAG.write_text("1")
        write_from_outside(sorted(states), write)
        self.send_json({"success": True, "sites": sorted(states)})

    # --- state API ------------------------------------------------------
    def handle_post(self, site: str):
        raw = self.body() or b"{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return self.send_json({"error": str(exc)}, 400)
        action = data.get("action", "set")
        folder = state_dir(site)
        if ORACLE_FLAG.exists():  # golden state is final; tell the page its save worked
            log_write("post-ignored", site, raw, action)
            return self.send_json({"success": True, "state": read_json(folder / "current.json")})
        log_write("post", site, raw, action)
        with LOCK:
            if action == "reset":
                write_json(folder / "current.json", read_json(folder / "initial.json"))
                return self.send_json({"success": True, "message": "State reset."})
            if action not in ("set", "set_current"):
                return self.send_json({"error": "Unknown action"}, 400)
            current = read_json(folder / "current.json") or {}
            new_state = deep_merge(current, data.get("state") or {}) if data.get("merge") else data.get("state")
            write_json(folder / "current.json", new_state)
            if not (folder / "initial.json").exists():
                write_json(folder / "initial.json", data.get("initial_state") or new_state)
        if TRIGGERS:
            fire_triggers(site, new_state)
        self.send_json({"success": True, "state": new_state})

    def handle_upload(self, site: str):
        match = re.search(r"boundary=([^;]+)", self.headers.get("Content-Type", ""))
        if not match:
            return self.send_json({"error": "Content-Type must be multipart/form-data"}, 400)
        boundary = b"--" + match.group(1).strip('"').encode()
        uploaded = []
        for part in self.body().split(boundary)[1:-1]:
            # Strip exactly the multipart framing; the payload's own trailing CR/LF is data.
            if not part.startswith(b"\r\n") or not part.endswith(b"\r\n"):
                continue
            head, separator, data = part[2:-2].partition(b"\r\n\r\n")
            if not separator:
                continue
            name = re.search(rb'filename="([^"]*)"', head)
            if not name or not name.group(1):
                continue
            ctype = re.search(rb"Content-Type:\s*([^\r\n]+)", head, re.I)
            original = name.group(1).decode(errors="replace")
            stored = f"{uuid.uuid4().hex[:8]}_{safe(original)}"
            (files_dir(site) / stored).write_bytes(data)
            uploaded.append({
                "original_name": original, "stored_name": stored, "size": len(data),
                "content_type": ctype.group(1).decode() if ctype else "application/octet-stream",
                "url": f"/files/{safe(SID)}/{stored}",
            })
        if not uploaded:
            return self.send_json({"error": "No files found in request"}, 400)
        log_write("upload", site, note=",".join(u["stored_name"] for u in uploaded))
        self.send_json({"success": True, "files": uploaded})

    def serve_upload(self, site: str, path: str):
        parts = [p for p in path.split("/") if p][1:]
        if len(parts) < 2:
            return self.send(404, b"Not found", "text/plain")
        name = safe(unquote("/".join(parts[1:])))
        file = VAR_DIR / "files" / site / safe(parts[0]) / name
        if not file.is_file():
            return self.send(404, b"File not found", "text/plain")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        display = re.sub(r"^[0-9a-f]{8}_", "", name)
        self.send(200, file.read_bytes(), ctype, {"Content-Disposition": f'attachment; filename="{display}"'})

    # --- static ---------------------------------------------------------
    def serve_static(self, site: str, path: str):
        dist = (SITES_DIR / site / "dist").resolve()
        file = (dist / unquote(path).lstrip("/")).resolve()
        if dist not in file.parents and file != dist:
            return self.send(404, b"Not found", "text/plain")
        if file.is_file() and file.name != "index.html":
            ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            return self.send(200, file.read_bytes(), ctype, {"Cache-Control": "max-age=3600"})
        if Path(path).suffix and not file.is_file():
            return self.send(404, b"Not found", "text/plain")
        # SPA route: hand back index.html with the boot script ahead of the bundle.
        html = (dist / "index.html").read_bytes()
        html = html.replace(b"<head>", b"<head>" + boot_script(), 1)
        self.send(200, html, "text/html; charset=utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
