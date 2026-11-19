#!/usr/bin/python3
"""Stdio MCP for the task's private X11 display."""

import base64
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from io import BytesIO

from PIL import ImageGrab


WIDTH, HEIGHT = 1280, 800
LOG_DIR = "/logs/agent/desktop"
POINT = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}
CLICKS = {"left_click": ("1", 1), "double_click": ("1", 2), "triple_click": ("1", 3), "right_click": ("3", 1)}
WHEEL = {"up": "4", "down": "5", "left": "6", "right": "7"}
TOOL = {
    "name": "computer",
    "description": (f"Operate the {WIDTH}×{HEIGHT} Linux desktop, including browser controls and file dialogs. "
                    "Every action returns a full-desktop PNG. Coordinates start at the top-left corner. "
                    "Use X11 keys such as Return, Right, Ctrl+l and Alt+Tab. "
                    "Super+e opens the workspace in the desktop file manager."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [
                "screenshot", *CLICKS, "mouse_move", "left_click_drag", "type", "key", "scroll", "wait",
            ]},
            "coordinate": POINT,
            "start_coordinate": POINT,
            "text": {"type": "string", "maxLength": 10000},
            "repeat": {"type": "integer", "minimum": 1, "maximum": 50},
            "scroll_direction": {"type": "string", "enum": list(WHEEL)},
            "scroll_amount": {"type": "integer", "minimum": 1, "maximum": 30},
            "duration": {"type": "number", "minimum": 0, "maximum": 10},
        },
        "required": ["action"],
    },
}


def xdotool(*args):
    result = subprocess.run(["xdotool", *args], capture_output=True, check=True, timeout=10)
    return result.stdout.decode().strip()


def screenshot():
    with BytesIO() as stream, ImageGrab.grab(xdisplay=os.environ["DISPLAY"]) as desktop:
        desktop.save(stream, format="PNG")
        return stream.getvalue()


def active_window():
    return xdotool("getactivewindow", "getwindowname")


def point(args, field="coordinate"):
    coords = args.get(field)
    if (not isinstance(coords, list) or len(coords) != 2
            or any(type(value) is not int for value in coords)
            or not (0 <= coords[0] < WIDTH and 0 <= coords[1] < HEIGHT)):
        raise ValueError(f"{field} must be two integers inside the {WIDTH}×{HEIGHT} desktop")
    return coords


def bounded_int(args, field, default, maximum):
    value = args.get(field, default)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be an integer from 1 to {maximum}")
    return str(value)


def move(coords):
    xdotool("mousemove", *map(str, coords))


def drag(start, end):
    move(start)
    xdotool("mousedown", "1")
    try:
        for step in range(1, 13):
            move([round(a + (b - a) * step / 12) for a, b in zip(start, end)])
            time.sleep(0.025)
    finally:
        xdotool("mouseup", "1")


def type_text(chars):
    if not isinstance(chars, str) or not 0 < len(chars) <= 10000 or "\x00" in chars:
        raise ValueError("type needs 1–10000 text characters")
    if len(chars) <= 250 and chars.isascii() and chars.isprintable():
        xdotool("type", "--clearmodifiers", "--delay", "2", "--", chars)
        return
    subprocess.run(["xclip", "-selection", "clipboard", "-in"], input=chars.encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=5)
    xdotool("key", "--clearmodifiers", "Ctrl+v")


def perform(args):
    action, chars = args.get("action"), args.get("text")
    if not isinstance(action, str):
        raise ValueError("action must be a string")
    if action in CLICKS:
        button, count = CLICKS[action]
        move(point(args))
        xdotool("click", "--repeat", str(count), "--delay", "50", button)
    elif action == "mouse_move":
        move(point(args))
    elif action == "left_click_drag":
        drag(point(args, "start_coordinate"), point(args))
    elif action == "type":
        type_text(chars)
    elif action == "key":
        if not isinstance(chars, str) or not re.fullmatch(r"[a-zA-Z0-9_]+(\+[a-zA-Z0-9_]+){0,4}", chars):
            raise ValueError("key needs a key or combination such as Ctrl+s")
        xdotool("key", "--clearmodifiers", "--repeat", bounded_int(args, "repeat", 1, 50), chars)
    elif action == "scroll":
        direction = args.get("scroll_direction")
        if not isinstance(direction, str) or direction not in WHEEL:
            raise ValueError("scroll_direction must be up, down, left or right")
        amount = bounded_int(args, "scroll_amount", 3, 30)
        if "coordinate" in args:
            move(point(args))
        xdotool("click", "--repeat", amount, "--delay", "40", WHEEL[direction])
    elif action == "wait":
        duration = args.get("duration", 1)
        if type(duration) not in (int, float) or not 0 <= duration <= 10:
            raise ValueError("duration must be 0–10 seconds")
        time.sleep(duration)
    elif action != "screenshot":
        raise ValueError(f"unknown desktop action {action!r}")
    if action not in ("screenshot", "wait"):
        time.sleep(0.2)


def computer(args):
    with open(f"{LOG_DIR}/.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        perform(args)
        png = screenshot()
        with tempfile.NamedTemporaryFile(dir=LOG_DIR, suffix=".png", delete=False) as evidence:
            evidence.write(png)
    return {"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}]}


def handle(method, params):
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "desktop", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        try:
            if params.get("name") != TOOL["name"]:
                raise ValueError("unknown desktop tool")
            return computer(params.get("arguments") or {})
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    raise LookupError(method)


def serve():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700, "message": "Invalid JSON"}}), flush=True)
            continue
        if "id" not in message:
            continue
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        try:
            reply["result"] = handle(message.get("method"), message.get("params") or {})
        except LookupError:
            reply["error"] = {"code": -32601, "message": "Method not found"}
        print(json.dumps(reply), flush=True)


def ready(mode):
    try:
        if mode == "--ready-browser":
            return bool(xdotool("search", "--onlyvisible", "--name", "Google Chrome for Testing$")) and bool(screenshot())
        title = active_window()
        return title.endswith("LibreOffice Calc") and title.startswith("result") and bool(screenshot())
    except (OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    if sys.argv[1:] in (["--ready-browser"], ["--ready-workbook"]):
        sys.exit(0 if ready(sys.argv[1]) else 1)
    serve()
