"""Drive the same screenshot and input surface used by the rollout agent."""

from base64 import b64decode
import json
from urllib.request import Request, urlopen


def act(action, **arguments):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "computer", "arguments": {"action": action, **arguments}},
    }
    request = Request("http://desktop:8000/mcp", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        reply = json.load(response)
    result = reply.get("result", {})
    content = result.get("content", [])
    if result.get("isError") or len(content) != 1 or content[0].get("mimeType") != "image/png":
        raise RuntimeError(f"Desktop GUI action failed: {action} {arguments}")
    return b64decode(content[0]["data"], validate=True)


def key(value, repeat=None):
    options = {"text": value}
    if repeat is not None:
        options["repeat"] = repeat
    return act("key", **options)


def click(x, y):
    return act("left_click", coordinate=[x, y])


def type_text(value):
    return act("type", text=value)


def wait(seconds):
    return act("wait", duration=seconds)
