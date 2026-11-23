"""Stateless Streamable HTTP MCP exposing only desktop screenshot and input."""

import base64
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess

import desktop_mcp


AUDIT = Path("/var/lib/cua-mcp-audit")
FIELDS = {
    "screenshot": set(),
    "left_click": {"coordinate"},
    "double_click": {"coordinate"},
    "triple_click": {"coordinate"},
    "right_click": {"coordinate"},
    "mouse_move": {"coordinate"},
    "left_click_drag": {"start_coordinate", "coordinate"},
    "type": {"text"},
    "key": {"text", "repeat"},
    "scroll": {"coordinate", "scroll_direction", "scroll_amount"},
    "wait": {"duration"},
}
TOOL = {**desktop_mcp.TOOL}
TOOL["inputSchema"] = {**desktop_mcp.TOOL["inputSchema"], "additionalProperties": False}


def act(params):
    if params.get("name") != "computer":
        raise ValueError("Only computer is available")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("Expected an action object")
    action = arguments.get("action")
    if not isinstance(action, str) or action not in FIELDS or arguments.keys() - {"action"} - FIELDS[action]:
        raise ValueError("Action or parameters outside the GUI interface")
    with (AUDIT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        desktop_mcp.perform(arguments)
        png = desktop_mcp.screenshot()
        with (AUDIT / "actions.jsonl").open("a") as stream:
            stream.write(json.dumps({"arguments": arguments, "png_sha256": hashlib.sha256(png).hexdigest()}) + "\n")
    return {"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}]}


def handle(method, params):
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        try:
            return act(params)
        except (ValueError, OSError, subprocess.SubprocessError):
            return {"content": [{"type": "text", "text": "Invalid GUI action or desktop input failed"}], "isError": True}
    return desktop_mcp.handle(method, params)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, value=None):
        body = json.dumps(value, separators=(",", ":")).encode() if value is not None else b""
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 405)

    def do_POST(self):
        if self.path != "/mcp":
            return self.respond(404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 96 * 1024:
                return self.respond(413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
                raise ValueError("invalid request")
        except (ValueError, UnicodeError):
            return self.respond(400)
        if "id" not in data:
            return self.respond(202)
        try:
            result = {"result": handle(data.get("method"), data.get("params") or {})}
        except LookupError:
            result = {"error": {"code": -32601, "message": "Method not found"}}
        self.respond(200, {"jsonrpc": "2.0", "id": data["id"], **result})


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
