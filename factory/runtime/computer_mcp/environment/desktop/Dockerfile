ARG DESKTOP_BASE_IMAGE=ghcr.io/trycua/linux:24.04-slim@sha256:c1f832a2616896a1571d3ed0be6c0f0de95a1ca8a6b9fb4329d8e7347bfac7a2
FROM ${DESKTOP_BASE_IMAGE}

ARG DESKTOP_APPS=
ARG DRAWIO_DESKTOP=0
ARG PDF4QT_DESKTOP=0
ARG ZOTERO_DESKTOP=0
ARG WORKSPACE_CLI=0
COPY cua/sources/ubuntu.sources /etc/apt/sources.list.d/cua-aliyun.sources
RUN rm -f /etc/apt/sources.list \
 && find /etc/apt/sources.list.d -maxdepth 1 \( -name '*.list' -o -name '*.sources' \) ! -name cua-aliyun.sources -delete \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends libreoffice-calc openbox python3-pil ristretto xauth xclip xdotool xvfb ${DESKTOP_APPS} \
 && if [ "$DRAWIO_DESKTOP" = "1" ]; then \
      curl -fLsS --retry 3 https://github.com/jgraph/drawio-desktop/releases/download/v32.6.10/drawio-amd64-32.6.10.deb -o /tmp/drawio.deb \
      && echo 'fc96faafe68cb4e06c0b7116779891592b20fce2cde7907adec504f23c5af83c  /tmp/drawio.deb' | sha256sum -c - \
      && apt-get install -y --no-install-recommends /tmp/drawio.deb \
      && rm /tmp/drawio.deb; \
    fi \
 && if [ "$PDF4QT_DESKTOP" = "1" ]; then \
      apt-get install -y --no-install-recommends libgl1 libxcb-cursor0 libxkbcommon-x11-0 \
      && curl -fLsS --retry 3 https://github.com/JakubMelka/PDF4QT/releases/download/v1.7.1.0/PDF4QT-1.7.1.0-x86_64.AppImage -o /tmp/pdf4qt.AppImage \
      && echo '290c7453e349e16a99e48397ac111fcec22ca4d60a6660389f127e8d9592c5a4  /tmp/pdf4qt.AppImage' | sha256sum -c - \
      && chmod 755 /tmp/pdf4qt.AppImage \
      && (cd /tmp && ./pdf4qt.AppImage --appimage-extract >/dev/null) \
      && mv /tmp/squashfs-root /opt/pdf4qt && chmod -R a+rX /opt/pdf4qt \
      && ln -s /opt/pdf4qt/usr/bin/Pdf4QtEditor /usr/local/bin/pdf4qt \
      && printf '[Desktop Entry]\nType=Application\nName=PDF4QT Editor\nExec=/usr/local/bin/pdf4qt %%f\nMimeType=application/pdf;\n' > /usr/share/applications/pdf4qt-editor.desktop \
      && rm /tmp/pdf4qt.AppImage; \
    fi \
 && if [ "$ZOTERO_DESKTOP" = "1" ]; then \
      apt-get install -y --no-install-recommends bzip2 libdbus-glib-1-2 libgtk-3-0t64 default-jre-headless libreoffice-java-common \
      && curl -fLsS --retry 3 https://download.zotero.org/client/release/7.0.32/Zotero-7.0.32_linux-x86_64.tar.bz2 -o /tmp/zotero.tar.bz2 \
      && echo '8ddd78ffcdb2fee4f4e4b40b4e9444fb356bed01ca37a5565835f9b6f32db1ee  /tmp/zotero.tar.bz2' | sha256sum -c - \
      && mkdir /opt/zotero && tar -xjf /tmp/zotero.tar.bz2 --strip-components=1 -C /opt/zotero \
      && mkdir -p /opt/zotero/distribution \
      && printf '%s\n' '{"policies":{"DisableAppUpdate":true}}' > /opt/zotero/distribution/policies.json \
      && printf '%s\n' '#!/bin/sh' \
           'if [ "$#" -eq 0 ]; then' \
           '  window="$(xdotool search --onlyvisible --class Zotero 2>/dev/null | head -n 1)"' \
           '  if [ -n "$window" ]; then' \
           '    xdotool windowactivate "$window" 2>/dev/null || xdotool windowraise "$window" windowfocus "$window" 2>/dev/null' \
           '    exit 0' \
           '  fi' \
           'fi' \
           'exec /opt/zotero/zotero -profile /home/agent/.zotero-cua "$@"' \
           > /usr/local/bin/zotero \
      && chmod 755 /usr/local/bin/zotero \
      && printf '[Desktop Entry]\nType=Application\nName=Zotero\nExec=/usr/local/bin/zotero %%U\nTerminal=false\n' > /usr/share/applications/zotero.desktop \
      && /usr/lib/libreoffice/program/unopkg add --shared --force --suppress-license /opt/zotero/integration/libreoffice/Zotero_LibreOffice_Integration.oxt \
      && rm /tmp/zotero.tar.bz2; \
    fi \
 && apt-get purge -y xfce4-appfinder \
 && if [ "$WORKSPACE_CLI" = "1" ]; then \
      apt-get install -y --no-install-recommends xfce4-terminal libseccomp2 sudo; \
    else apt-get purge -y xfce4-terminal; fi \
 && printf '<actions/>\n' > /etc/xdg/Thunar/uca.xml \
 && rm -rf /var/lib/apt/lists/*
ENV DISPLAY=:99 XAUTHORITY=/run/cua-desktop/Xauthority SAL_USE_VCLPLUGIN=gen

COPY cua/ /opt/cua/
COPY workspace/ /workspace/
COPY gui_server.py snapshot_server.py zotero_snapshot.py ready.py offline_web.py openbox.xml /usr/local/lib/cua-smoke/
RUN useradd -m -s /usr/sbin/nologin agent \
 && useradd -M -s /usr/sbin/nologin -G agent desktop-driver \
 && if [ "$WORKSPACE_CLI" = "1" ]; then \
      useradd -m -g agent -s /usr/sbin/nologin workspace-cli \
      && chmod 700 /home/agent \
      && install -m 755 /opt/cua/workspace_cli.py /usr/local/bin/cua-workspace-shell \
      && printf 'agent ALL=(workspace-cli) NOPASSWD: /usr/local/bin/cua-workspace-shell ""\n' > /etc/sudoers.d/cua-workspace \
      && chmod 440 /etc/sudoers.d/cua-workspace; \
    fi \
 && viewer=$(dpkg -L ristretto | sed -n 's@^/usr/share/applications/\(.*\.desktop\)$@\1@p') \
 && test -n "$viewer" \
 && runuser -u agent -- xdg-mime default "$viewer" image/png image/jpeg \
 && if [ "$PDF4QT_DESKTOP" = "1" ]; then runuser -u agent -- xdg-mime default pdf4qt-editor.desktop application/pdf; \
    elif command -v evince >/dev/null; then runuser -u agent -- xdg-mime default org.gnome.Evince.desktop application/pdf; fi \
 && install -d -m 700 -o desktop-driver -g desktop-driver /var/lib/cua-mcp-audit \
 && install -d -m 700 /var/lib/cua \
 && install -d -m 755 -o agent -g agent /workspace/output /workspace/downloads \
 && install -D -m 644 /opt/cua/sources/chromium-policy.json /etc/chromium/policies/managed/cua.json \
 && install -m 644 /opt/cua/desktop_mcp.py /usr/local/lib/cua-smoke/desktop_mcp.py \
 && openssl req -new -x509 -newkey rsa:2048 -nodes -days 3650 -subj /CN=offline-cua-desktop \
      -keyout /opt/cua/offline.key -out /opt/cua/offline.crt \
 && chmod -R go-rwx /opt/cua \
 && chmod 700 /opt/cua/entrypoint.sh \
 && if [ -f /opt/cua/web-entrypoint.sh ]; then chmod 700 /opt/cua/web-entrypoint.sh; fi

WORKDIR /workspace
HEALTHCHECK --interval=2s --timeout=4s --start-period=8s --retries=50 CMD ["/usr/bin/python3", "/usr/local/lib/cua-smoke/ready.py", "--check"]
ENTRYPOINT ["/opt/cua/entrypoint.sh"]
CMD ["/usr/bin/python3", "/usr/local/lib/cua-smoke/ready.py"]
