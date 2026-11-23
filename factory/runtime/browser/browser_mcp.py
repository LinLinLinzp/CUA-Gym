#!/usr/bin/env python3
"""Stdio MCP server that gives the agent computer-use style browser tools.

Declared in task.toml as [[environment.mcp_servers]], so the agent harness
(e.g. Harbor's claude-code) registers it and the model sees self-describing
tools; nothing about the browser has to go into instruction.md. Each call is
forwarded to browserd (127.0.0.1:8079) and answered with a screenshot image.
"""

import base64
import json
import sys
import urllib.error
import urllib.request

DAEMON = "http://127.0.0.1:8079"
WIDTH, HEIGHT = 1280, 800

COORD = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}
TOOLS = [
    {
        "name": "computer",
        "description": (
            f"Use the mouse and keyboard in the web browser window ({WIDTH}x{HEIGHT}) and see the screen. "
            "Every call returns a screenshot of the current tab; coordinates are pixels from its top-left corner. "
            "Keys use names like Enter, Tab, Escape, Backspace, ArrowDown, ctrl+a, shift+Tab."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [
                    "screenshot", "left_click", "double_click", "triple_click", "right_click", "mouse_move",
                    "left_click_drag", "type", "key", "scroll", "wait"]},
                "coordinate": {**COORD, "description": "[x, y] for clicks, mouse_move, scroll and the end of a drag"},
                "start_coordinate": {**COORD, "description": "[x, y] where left_click_drag starts"},
                "text": {"type": "string", "description": "Text for type, or the key / key combination for key"},
                "repeat": {"type": "integer", "minimum": 1, "maximum": 50, "description": "How many times to press the key"},
                "scroll_direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "scroll_amount": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Wheel notches (default 3)"},
                "duration": {"type": "number", "minimum": 0, "maximum": 10, "description": "Seconds to wait"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Open a URL in the current tab, or go back / forward / reload. Returns a screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "action": {"type": "string", "enum": ["goto", "back", "forward", "reload"], "default": "goto"},
            },
        },
    },
    {
        "name": "browser_tabs",
        "description": "List, open, switch to or close browser tabs. Returns the tab list and a screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "new", "select", "close"]},
                "index": {"type": "integer", "description": "Tab index for select / close"},
                "url": {"type": "string", "description": "URL for a new tab"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "browser_upload",
        "description": "Click an upload button or file field at a coordinate and attach local files to it.",
        "inputSchema": {
            "type": "object",
            "properties": {"coordinate": COORD, "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
            "required": ["coordinate", "paths"],
        },
    },
]

KEY_NAMES = {"ctrl": "Control", "control": "Control", "cmd": "Meta", "super": "Meta", "meta": "Meta", "alt": "Alt",
             "shift": "Shift", "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape", "tab": "Tab",
             "backspace": "Backspace", "delete": "Delete", "space": "Space", "up": "ArrowUp", "down": "ArrowDown",
             "left": "ArrowLeft", "right": "ArrowRight", "pageup": "PageUp", "page_up": "PageUp", "pagedown": "PageDown",
             "page_down": "PageDown", "home": "Home", "end": "End"}


class ToolError(Exception):
    pass


def key_name(text: str) -> str:
    parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ToolError("key needs text, e.g. Enter or ctrl+a")
    return "+".join(KEY_NAMES.get(p.lower(), p) for p in parts)


def point(args, name="coordinate"):
    value = args.get(name)
    if not (isinstance(value, list) and len(value) == 2):
        raise ToolError(f"{name} [x, y] is required for this action")
    x, y = int(value[0]), int(value[1])
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        raise ToolError(f"{name} {value} is outside the {WIDTH}x{HEIGHT} screen")
    return x, y


def computer_action(args):
    action = args.get("action")
    if action == "screenshot":
        return {"kind": "view"}
    if action in ("left_click", "double_click", "triple_click", "right_click"):
        x, y = point(args)
        clicks = {"double_click": 2, "triple_click": 3}.get(action, 1)
        return {"kind": "click", "x": x, "y": y, "clicks": clicks, "button": "right" if action == "right_click" else "left"}
    if action == "mouse_move":
        x, y = point(args)
        return {"kind": "move", "x": x, "y": y}
    if action == "left_click_drag":
        (x, y), (tx, ty) = point(args, "start_coordinate"), point(args)
        return {"kind": "drag", "x": x, "y": y, "to_x": tx, "to_y": ty}
    if action == "type":
        if not isinstance(args.get("text"), str):
            raise ToolError("type needs text")
        return {"kind": "type", "text": args["text"]}
    if action == "key":
        return {"kind": "key", "key": key_name(args.get("text") or ""), "repeat": int(args.get("repeat", 1))}
    if action == "scroll":
        x, y = point(args) if args.get("coordinate") else (WIDTH // 2, HEIGHT // 2)
        step = 100 * int(args.get("scroll_amount", 3))
        direction = args.get("scroll_direction", "down")
        dx = {"left": -step, "right": step}.get(direction, 0)
        dy = {"up": -step, "down": step}.get(direction, 0)
        return {"kind": "scroll", "x": x, "y": y, "dx": dx, "dy": dy}
    if action == "wait":
        return {"kind": "wait", "ms": int(1000 * float(args.get("duration", 1)))}
    raise ToolError(f"unknown action {action!r}")


def to_actions(name, args):
    if name == "computer":
        return [computer_action(args)]
    if name == "browser_navigate":
        action = args.get("action", "goto")
        if action == "goto":
            if not args.get("url"):
                raise ToolError("url is required")
            return [{"kind": "goto", "url": args["url"]}]
        return [{"kind": action}]
    if name == "browser_tabs":
        action = args.get("action")
        if action == "list":
            return [{"kind": "view"}]
        if action == "new":
            return [{"kind": "new_tab", **({"url": args["url"]} if args.get("url") else {})}]
        if action in ("select", "close"):
            if "index" not in args:
                raise ToolError("index is required")
            return [{"kind": "switch_tab" if action == "select" else "close_tab", "index": int(args["index"])}]
        raise ToolError(f"unknown tabs action {action!r}")
    if name == "browser_upload":
        x, y = point(args)
        return [{"kind": "upload", "x": x, "y": y, "paths": list(args.get("paths") or [])}]
    raise ToolError(f"unknown tool {name!r}")


def call_tool(name, args):
    try:
        actions = to_actions(name, args or {})
        request = urllib.request.Request(f"{DAEMON}/act", json.dumps({"actions": actions}).encode(),
                                         {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ToolError(json.loads(exc.read() or b"{}").get("error", f"browser error {exc.code}"))
        except urllib.error.URLError as exc:
            raise ToolError(f"browser unavailable: {exc.reason}")
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    with open(result.pop("screenshot_path"), "rb") as f:
        image = base64.b64encode(f.read()).decode()
    info = {"url": result["url"], "tabs": result["tabs"]}
    if result.get("downloaded_files"):
        info["downloaded_files"] = result["downloaded_files"]
    return {"content": [{"type": "text", "text": json.dumps(info)},
                        {"type": "image", "data": image, "mimeType": "image/png"}]}


def handle(message):
    method, params = message.get("method"), message.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "browser", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params.get("name"), params.get("arguments"))
    raise LookupError(method)


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if "id" not in message:  # notification
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": handle(message)}
        except LookupError:
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}}
        except Exception as exc:
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32603, "message": str(exc)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
