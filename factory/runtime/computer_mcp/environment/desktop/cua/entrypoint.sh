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
if [ -x /usr/local/bin/cua-workspace-shell ]; then
    chgrp agent /workspace/output
    chmod 2775 /workspace/output
fi
runuser -u agent -- openbox --config-file /usr/local/lib/cua-smoke/openbox.xml > "$runtime/openbox.log" 2>&1 &

if [ -f /opt/cua/enable-audio ]; then
    export XDG_RUNTIME_DIR="$runtime/audio-session"
    install -d -m 700 -o agent -g agent "$XDG_RUNTIME_DIR"
    if [ -d /dev/snd ]; then
        runuser -u agent -- pulseaudio --start --exit-idle-time=-1
    else
        # A clocked stereo playback sink drives the editor's transport and meters.
        runuser -u agent -- pulseaudio -n --daemonize=yes --exit-idle-time=-1 \
            -L module-native-protocol-unix -L "module-null-sink sink_name=desktop channels=2 rate=48000"
    fi
    export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
    runuser -u agent -- pactl info > "$runtime/audio.log"
fi

if [ -f /opt/cua/zotero-library-name ]; then
    library_name=$(cat /opt/cua/zotero-library-name)
    install -d -m 700 -o agent -g agent /home/agent/Zotero /home/agent/.zotero-cua
    if [ ! -e /home/agent/Zotero/zotero.sqlite ]; then
        install -m 600 -o agent -g agent "/workspace/input/$library_name" /home/agent/Zotero/zotero.sqlite
    fi
    # Keep one native profile and skip the already-installed OXT setup wizard.
    cat > /home/agent/.zotero-cua/user.js <<'ZOTERO_PREFS'
user_pref("extensions.zotero.dataDir", "/home/agent/Zotero");
user_pref("extensions.zotero.useDataDir", true);
user_pref("extensions.zotero.firstRun2", false);
user_pref("extensions.zotero.firstRun.skipFirefoxProfileAccessCheck", true);
user_pref("extensions.zoteroOpenOfficeIntegration.skipInstallation", true);
user_pref("extensions.zotero.sync.autoSync", false);
user_pref("extensions.zotero.sync.reminder.setUp.enabled", false);
user_pref("extensions.zotero.sync.reminder.autoSync.enabled", false);
user_pref("extensions.zotero.firstRunGuidance", false);
user_pref("app.update.enabled", false);
user_pref("app.update.auto", false);
ZOTERO_PREFS
    chown agent:agent /home/agent/.zotero-cua/user.js
    chmod 600 /home/agent/.zotero-cua/user.js
    runuser -u agent -- zotero > "$runtime/zotero.log" 2>&1 &
fi

if command -v mousepad >/dev/null; then
    runuser -u agent -- mousepad > "$runtime/mousepad.log" 2>&1 &
    timeout 20 xdotool search --sync --onlyvisible --class mousepad >/dev/null
fi

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
    timeout 20 xdotool search --sync --onlyvisible --name 'LibreOffice Calc$' >/dev/null
fi

if command -v drawio >/dev/null; then
    runuser -u agent -- drawio --no-sandbox --disable-gpu > "$runtime/drawio.log" 2>&1 &
    timeout 45 xdotool search --sync --onlyvisible --name '[Dd]raw.io|[Dd]iagrams.net|[Uu]ntitled' >/dev/null
fi

if [ -f /opt/cua/web-entrypoint.sh ]; then
    exec /opt/cua/web-entrypoint.sh "$@"
fi
[ $# -gt 0 ] || set -- sleep infinity
exec "$@"
