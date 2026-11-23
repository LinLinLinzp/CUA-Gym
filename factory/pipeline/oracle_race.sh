#!/usr/bin/env bash
# Oracle under a fast runner: start the task container, run solve.sh the moment
# GATE answers (sitehost: tabs not opened yet / still booting; browserd: all tabs
# loaded but maybe still flushing their first save), wait, then grade. Harbor locally leaves enough slack to hide this race;
# the platform does not.
#
# RELOAD=1 reloads every tab after solve (a reload must not undo the golden state).
#
#   [GATE=sitehost|browserd] [RELOAD=1] factory/pipeline/oracle_race.sh output/harbor/tasks/exp1-l02 [delay_before_solve_s=0] [wait_after_s=15]
set -euo pipefail
task=$(cd "$1" && pwd); delay=${2:-0}; wait_after=${3:-15}
name=race-$(basename "$task")
port=8079; [ "${GATE:-browserd}" = sitehost ] && port=8090
health=health; [ "$port" = 8090 ] && health=__health
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
docker build -q -t "$name:latest" "$task/environment" >/dev/null
docker rm -f "$name" >/dev/null 2>&1 || true
docker create --name "$name" "$name:latest" >/dev/null
docker cp "$task/solution" "$name:/solution"
docker cp "$task/tests" "$name:/tests"
docker start "$name" >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
until docker exec "$name" curl -fsS http://127.0.0.1:$port/$health >/dev/null 2>&1; do sleep 0.1; done
sleep "$delay"
docker exec -u agent "$name" bash /solution/solve.sh >/dev/null
if [ "${RELOAD:-0}" = 1 ]; then
  sleep 2
  tabs=$(docker exec "$name" curl -fsS http://127.0.0.1:8079/health | python3 -c 'import json,sys;print(json.load(sys.stdin)["tabs"])')
  for i in $(seq 0 $((tabs - 1))); do
    docker exec "$name" curl -fsS -H 'Content-Type: application/json' http://127.0.0.1:8079/act \
      -d "{\"actions\":[{\"kind\":\"switch_tab\",\"index\":$i},{\"kind\":\"reload\"}]}" >/dev/null || echo "reload tab $i failed"
  done
fi
sleep "$wait_after"
docker exec "$name" mkdir -p /logs/verifier
docker exec "$name" bash /tests/test.sh >/dev/null 2>&1 || true
docker exec "$name" cat /logs/verifier/report.json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("reward", d.get("reward"), d.get("status"))
for c in d.get("checks", []):
    if c["score"] < 1:
        print("  FAIL", c["id"], c["detail"][:140])'
