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
  mkdir -p "$VAR/state" "$VAR/files"
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
  chmod 755 /logs/agent
  touch "$VAR/.booted"
fi

mapfile -t urls < <(/usr/bin/python3 -c 'import json; print(*json.load(open("/opt/cua/config.json"))["start_urls"], sep="\n")')
health_host=$(/usr/bin/python3 -c 'import sys; from urllib.parse import urlsplit; print(urlsplit(sys.argv[1]).hostname)' "${urls[0]}")
export TZ
TZ=$(/usr/bin/python3 -c 'import json; print(json.load(open("/opt/cua/config.json"))["timezone"])')
if [ -f /opt/native/site-id ]; then
  bash /opt/native/runtime/start.sh >> "$VAR/sitehost.log" 2>&1
else
  nohup /usr/bin/python3 -u /usr/local/lib/cua-smoke/offline_web.py >> "$VAR/sitehost.log" 2>&1 &
fi
for _ in $(seq 1 50); do
  curl -kfsS --resolve "$health_host:443:127.0.0.1" "https://$health_host/__health" >/dev/null 2>&1 && break
  sleep 0.2
done
curl -kfsS --resolve "$health_host:443:127.0.0.1" "https://$health_host/__health" >/dev/null

pin=$(openssl x509 -in "$CUA/offline.crt" -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | openssl base64 -A)
nohup runuser -u agent -- /usr/bin/chromium --no-sandbox --disable-gpu --no-first-run \
  --disable-background-networking --disable-search-engine-choice-screen --start-maximized \
  --user-data-dir=/home/agent/.cua-chromium \
  '--host-resolver-rules=MAP * 127.0.0.1, EXCLUDE localhost' \
  "--ignore-certificate-errors-spki-list=$pin" "${urls[@]}" >> "$VAR/browser.log" 2>&1 &

for attempt in $(seq 1 100); do
    if xdotool search --onlyvisible --class chromium >/dev/null 2>&1; then break; fi
    sleep .25
done
if ! xdotool search --onlyvisible --class chromium >/dev/null 2>&1; then
  tail -30 "$VAR/browser.log" >&2
  exit 1
fi
# Focus the first of the pre-opened browser tabs.
xdotool key Ctrl+1

[ $# -gt 0 ] || set -- sleep infinity
exec "$@"
