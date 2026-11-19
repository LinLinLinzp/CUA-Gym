#!/usr/bin/env python3
"""Drive a packaged task's environment by hand (for authoring agents and humans).

    ui_probe.py start <task-dir>            build + run the task image (container name: probe-<task>)
    ui_probe.py act <task> '<actions-json>' run browser actions; prints url/tabs and a host screenshot path
    ui_probe.py state <task> <site>         print current server state of a site (as the verifier sees it)
    ui_probe.py diff <task> <site>          top-level keys that changed since the seed
    ui_probe.py stop <task>

Actions are browserd's: goto/click/type/key/scroll/drag/upload/wait/new_tab/
switch_tab/close_tab/view (see runtime/browser/browserd.py). Use it to prove each
write action a task needs exists in the UI and lands in server state.
For computer MCP packages, use computer actions such as {"action":"screenshot"}.
"""

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SHOTS = Path("/tmp/ui_probe")


def name(task: str) -> str:
    return "probe-" + Path(task).name


def sh(*cmd, capture=True):
    return subprocess.run(cmd, check=True, capture_output=capture, text=True).stdout


def start(task_dir: str):
    tag = f"{name(task_dir)}:dev"
    directory = Path(task_dir)
    env = directory / "environment"
    computer_mcp = (directory / "tests" / "snapshot.json").is_file()
    context = env / "desktop" if computer_mcp else env
    sh("docker", "build", "-q", "-t", tag, str(context))
    subprocess.run(["docker", "rm", "-f", name(task_dir)], capture_output=True)
    if computer_mcp:
        sh("docker", "run", "-d", "--name", name(task_dir), "--shm-size=512m",
           "--label", "cua.computer-mcp=true", "--network", "none",
           "--tmpfs", "/run/cua-grading:mode=0700", tag)
        check = "python3 /usr/local/lib/cua-smoke/ready.py --check"
    else:
        sh("docker", "run", "-d", "--name", name(task_dir), "--shm-size=1g", tag)
        check = "curl -fsS http://127.0.0.1:8079/health"
    sh("docker", "exec", name(task_dir), "bash", "-c",
       'for i in $(seq 1 120); do bash -c "$1" >/dev/null 2>&1 && exit 0; sleep 0.5; done; exit 1',
       "check", check)
    print("ready", name(task_dir))


def act_desktop(task, actions):
    SHOTS.mkdir(exist_ok=True)
    screenshots = []
    for args in actions:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "computer", "arguments": args}})
        result = json.loads(sh("docker", "exec", "-u", "agent", name(task), "curl", "-fsS", "-m", "30",
                               "-H", "Content-Type: application/json", "--data-binary", payload,
                               "http://127.0.0.1:8000/mcp"))["result"]
        content, = result["content"]
        if result.get("isError") or content.get("mimeType") != "image/png":
            raise SystemExit(content.get("text", "Desktop MCP did not return a screenshot"))
        with tempfile.NamedTemporaryFile(dir=SHOTS, prefix=f"{name(task)}-", suffix=".png", delete=False) as shot:
            shot.write(base64.b64decode(content["data"], validate=True))
            screenshots.append(shot.name)
    print(json.dumps({"screenshots": screenshots}, indent=1))


def act(task: str, actions: str):
    runtime = sh("docker", "inspect", "--format", '{{index .Config.Labels "cua.computer-mcp"}}', name(task))
    if runtime.strip() == "true":
        return act_desktop(task, json.loads(actions))
    payload = json.dumps({"actions": json.loads(actions)})
    out = sh("docker", "exec", name(task), "curl", "-sS", "-X", "POST", "-H", "content-type: application/json",
             "--data-binary", payload, "http://127.0.0.1:8079/act")
    result = json.loads(out)
    if "screenshot_path" in result:
        SHOTS.mkdir(exist_ok=True)
        local = SHOTS / f"{name(task)}-{Path(result['screenshot_path']).name}"
        sh("docker", "cp", f"{name(task)}:{result['screenshot_path']}", str(local))
        result["screenshot_path"] = str(local)
    print(json.dumps(result, indent=1))


def state(task: str, site: str, which="current"):
    return json.loads(sh("docker", "exec", name(task), "cat", f"/var/lib/cua/state/{site}/{which}.json"))


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "start":
        start(args[0])
    elif cmd == "act":
        act(args[0], args[1])
    elif cmd == "state":
        print(json.dumps(state(args[0], args[1]), indent=1, ensure_ascii=False))
    elif cmd == "diff":
        before, after = state(args[0], args[1], "initial"), state(args[0], args[1])
        for key in sorted(set(before) | set(after)):
            if json.dumps(before.get(key), sort_keys=True) != json.dumps(after.get(key), sort_keys=True):
                print(f"changed: {key}")
    elif cmd == "stop":
        subprocess.run(["docker", "rm", "-f", name(args[0])], capture_output=True)
        subprocess.run(["docker", "rmi", f"{name(args[0])}:dev"], capture_output=True)  # disk is shared
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
