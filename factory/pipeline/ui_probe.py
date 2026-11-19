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
"""

import json
import subprocess
import sys
from pathlib import Path

SHOTS = Path("/tmp/ui_probe")


def name(task: str) -> str:
    return "probe-" + Path(task).name


def sh(*cmd, capture=True):
    return subprocess.run(cmd, check=True, capture_output=capture, text=True).stdout


def start(task_dir: str):
    tag = f"{name(task_dir)}:dev"
    sh("docker", "build", "-q", "-t", tag, str(Path(task_dir) / "environment"))
    subprocess.run(["docker", "rm", "-f", name(task_dir)], capture_output=True)
    sh("docker", "run", "-d", "--name", name(task_dir), "--shm-size=1g", tag)
    sh("docker", "exec", name(task_dir), "bash", "-c",
       "for i in $(seq 1 120); do curl -fsS http://127.0.0.1:8079/health >/dev/null 2>&1 && exit 0; sleep 0.5; done; exit 1")
    print("ready", name(task_dir))


def act(task: str, actions: str):
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
