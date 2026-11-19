#!/usr/bin/env bash
set -euo pipefail

runtime=/run/cua-desktop
profile=/home/agent/.config/cua-libreoffice
workbook=/workspace/output/result.xlsx

install -d -m 750 -g agent "$runtime"
install -d -m 755 -o agent -g agent /logs/agent/desktop
install -m 640 -g agent /dev/null "$XAUTHORITY"
xauth -f "$XAUTHORITY" add "$DISPLAY" . "$(mcookie)"
chgrp agent "$XAUTHORITY"
chmod 640 "$XAUTHORITY"
# The private display can leave a socket and lock after a container restart.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp -auth "$XAUTHORITY" > "$runtime/xvfb.log" 2>&1 &
for _ in $(seq 1 50); do
    if xdotool getdisplaygeometry >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
xdotool getdisplaygeometry >/dev/null
runuser -u agent -- openbox --config-file /usr/local/lib/cua-smoke/openbox.xml > "$runtime/openbox.log" 2>&1 &

if [ -f /opt/cua/sources/registrymodifications.xcu ]; then
    install -d -o agent -g agent /home/agent/.config "$profile" "$profile/user"
    install -m 600 -o agent -g agent /opt/cua/sources/registrymodifications.xcu "$profile/user/registrymodifications.xcu"
    calc_args=(--calc --nologo --norestore)
    if [ ! -f /opt/cua/web-entrypoint.sh ]; then
        if [ ! -e "$workbook" ]; then
            install -m 644 -o agent -g agent /workspace/input/start.xlsx "$workbook"
        fi
        calc_args+=("$workbook")
    fi
    runuser -u agent -- soffice "-env:UserInstallation=file://$profile" \
        "${calc_args[@]}" > "$runtime/calc.log" 2>&1 &
    if [ -f /opt/cua/web-entrypoint.sh ]; then
        timeout 20 xdotool search --sync --onlyvisible --name 'LibreOffice Calc$' >/dev/null
    fi
fi

if [ -f /opt/cua/web-entrypoint.sh ]; then
    exec /opt/cua/web-entrypoint.sh "$@"
fi
[ $# -gt 0 ] || set -- sleep infinity
exec "$@"
