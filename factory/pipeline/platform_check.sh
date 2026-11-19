#!/usr/bin/env bash
# Platform-like validation of a packaged task, on an x86_64 Docker host if DOCKER_HOST points at one:
# oracle runs the moment the environment is healthy (no warm-up), then every tab reloads
# (the platform failure mode), and nop runs in a fresh container.
# Prints "oracle=<r> nop=<r>" and exits 0 only for oracle 1.0 and nop 0.0.
#   DOCKER_HOST=ssh://natura-116 factory/pipeline/platform_check.sh output/harbor/tasks/<task> [--reset]
set -u
T=${1:?task dir}
if [[ -f "$T/environment/docker-compose.yaml" && -f "$T/tests/snapshot.json" ]]; then
  exec python3 "$(dirname "$0")/check_computer_mcp.py" "$T"
fi
N=pc-$(basename "$T" | tr '[:upper:]' '[:lower:]')-$RANDOM
docker build -q -t "$N:dev" "$T/environment" >/dev/null || { echo "build failed"; exit 2; }
trap 'docker rm -f "$N-o" "$N-n" >/dev/null 2>&1; docker rmi "$N:dev" >/dev/null 2>&1' EXIT

boot() {
  docker run -d --name "$1" "$N:dev" >/dev/null
  for _ in $(seq 1 240); do
    docker exec "$1" curl -fsS http://127.0.0.1:8079/health >/dev/null 2>&1 &&
      docker exec "$1" curl -fsS http://127.0.0.1:8090/__health >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 1
}
reward() {
  docker cp "$T/tests" "$1:/tests" >/dev/null
  docker exec "$1" bash -c 'mkdir -p /logs/verifier; bash /tests/test.sh >/tmp/verifier.out 2>&1; cat /logs/verifier/reward.txt 2>/dev/null || echo none'
}

boot "$N-o" || { echo "oracle env never became healthy"; exit 2; }
docker cp "$T/solution" "$N-o:/solution" >/dev/null
docker exec "$N-o" chown -R agent:agent /solution
docker exec -u agent "$N-o" bash /solution/solve.sh >/dev/null 2>&1
# Reproduce the platform failure mode: every open tab reloads after the oracle (stale client
# copies used to be pushed back over the golden state).
docker exec "$N-o" bash -c 'python3 - <<PY
import json, urllib.request
cfg = json.load(open("/opt/cua/config.json"))
origins = [o for s in cfg["sites"].values() for o in s["origins"]]
key = open("/var/lib/cua/secret").read().strip()
urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8079/__refresh", json.dumps({"origins": origins}).encode(),
    {"Content-Type": "application/json", "x-cua-key": key}), timeout=120)
PY' >/dev/null 2>&1
sleep 3
oracle=$(reward "$N-o")
[ "$oracle" = "1.0" ] || docker exec "$N-o" cat /tmp/verifier.out | grep -E "score=0|CAP|REWARD|Error" | head -8

boot "$N-n" || { echo "nop env never became healthy"; exit 2; }
nop=$(reward "$N-n")
echo "oracle=$oracle nop=$nop"
[ "$oracle" = "1.0" ] && [ "$nop" = "0.0" ] || exit 1

if [ "${2:-}" = "--reset" ]; then
  docker cp "$T/solution/golden" "$N-n:/var/lib/cua/reset-check-golden" || exit 2
  docker exec -i "$N-n" python3 - <<'PY' || exit 2
import json
from pathlib import Path
from urllib.request import Request, urlopen

root = Path("/var/lib/cua")
config = json.loads(Path("/opt/cua/config.json").read_text())
secret = (root / "secret").read_text().strip()
origins = [origin for site in config["sites"].values() for origin in site["origins"]]

def request(port, path, body, site=None):
    headers = {"x-cua-key": secret, "Content-Type": "application/json"}
    if site is not None:
        headers["x-cua-site"] = site
    with urlopen(Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(), headers),
                 timeout=120) as response:
        return json.load(response)

request(8079, "/__refresh", {"origins": origins, "phase": "park"})
try:
    for site in config["sites"]:
        state = root / "state" / site
        initial = json.loads((state / "initial.json").read_text())
        golden = (root / "reset-check-golden" / f"{site}.json").read_text()
        changed = json.loads(golden.replace("__SID__", config["sid"]))
        changed["__reset_check__"] = True
        request(8090, "/post", {"action": "set_current", "state": changed}, site)
        if json.loads((state / "current.json").read_text()) != changed:
            raise SystemExit(f"{site}: pre-reset state was not written")
        request(8090, "/post", {"action": "reset"}, site)
        if json.loads((state / "current.json").read_text()) != initial:
            raise SystemExit(f"{site}: reset did not restore the initial snapshot")
        print(f"reset {site}: initial snapshot restored")
finally:
    request(8079, "/__refresh", {"origins": origins, "phase": "restore"})
PY
  reset_reward=$(reward "$N-n")
  echo "reset reward=$reset_reward"
  [ "$reset_reward" = "0.0" ] || exit 1
  docker exec -i -u agent "$N-n" python3 - <<'PY' || exit 2
import base64
import json
import subprocess

requests = [
    {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
    {"id": 2, "method": "tools/list"},
    {"id": 3, "method": "tools/call", "params": {"name": "browser_tabs", "arguments": {"action": "list"}}},
]
result = subprocess.run(
    ["/usr/local/bin/browser-mcp"],
    input="".join(json.dumps({"jsonrpc": "2.0", **request}) + "\n" for request in requests),
    text=True, capture_output=True, timeout=45, check=True,
)
init, tools, observation = (json.loads(line)["result"] for line in result.stdout.splitlines())
if not init["capabilities"].get("tools") == {} or not any(tool["name"] == "computer" for tool in tools["tools"]):
    raise SystemExit("Browser MCP did not advertise the interaction tools")
content = observation["content"]
tabs = json.loads(content[0]["text"])["tabs"]
image = base64.b64decode(content[1]["data"], validate=True)
if not tabs or content[1]["mimeType"] != "image/png" or not image.startswith(b"\x89PNG\r\n\x1a\n"):
    raise SystemExit("Browser MCP did not return open tabs and a PNG screenshot")
print(f"browser MCP: {len(tabs)} tabs and valid PNG observation")
PY
fi
