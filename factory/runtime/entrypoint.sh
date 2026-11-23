#!/bin/bash
# Starts the task websites and the browser, then runs whatever command the
# runner passes (Harbor uses `sleep infinity`). Services are started from the
# entrypoint so they come up whether or not the runner overrides CMD.
set -euo pipefail
shopt -s nullglob

CUA=/opt/cua
VAR=/var/lib/cua

if [ ! -f "$VAR/.booted" ]; then
  umask 077
  mkdir -p "$VAR/state" "$VAR/files" /logs/agent/browser
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$VAR/secret"
  sid=$(python3 -c "import json;print(json.load(open('$CUA/config.json'))['sid'])")
  # Fresh world for this trial: copy every site's seed in as initial + current;
  # seeds reference attachments as /files/__SID__/<name>.
  for seed in "$CUA"/seed/*.json; do
    site=$(basename "$seed" .json)
    mkdir -p "$VAR/state/$site"
    sed "s/__SID__/$sid/g" "$seed" > "$VAR/state/$site/initial.json"
    cp "$VAR/state/$site/initial.json" "$VAR/state/$site/current.json"
  done
  # Seeded attachments, referenced from state as /files/<sid>/<name>.
  if [ -d "$CUA/seed/files" ]; then
    for dir in "$CUA"/seed/files/*/; do
      [ -d "$dir" ] || continue
      site=$(basename "$dir")
      mkdir -p "$VAR/files/$site/$sid"
      cp -R "$dir". "$VAR/files/$site/$sid/"
    done
  fi
  chown -R agent:agent /logs/agent /workspace/output /workspace/downloads
  chmod 755 /logs/agent /logs/agent/browser
  touch "$VAR/.booted"
fi

nohup python3 "$CUA/sitehost/sitehost.py" >> "$VAR/sitehost.log" 2>&1 &
for _ in $(seq 1 50); do curl -fsS http://127.0.0.1:8090/__health >/dev/null 2>&1 && break; sleep 0.2; done
nohup python3 "$CUA/browser/browserd.py" >> "$VAR/browserd.log" 2>&1 &
for _ in $(seq 1 100); do curl -fsS http://127.0.0.1:8079/health >/dev/null 2>&1 && break; sleep 0.3; done

[ $# -gt 0 ] || set -- sleep infinity
exec "$@"
