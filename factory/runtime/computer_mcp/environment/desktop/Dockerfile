ARG DESKTOP_BASE_IMAGE=ghcr.io/trycua/linux:24.04-slim@sha256:c1f832a2616896a1571d3ed0be6c0f0de95a1ca8a6b9fb4329d8e7347bfac7a2
FROM ${DESKTOP_BASE_IMAGE}

COPY cua/sources/ubuntu.sources /etc/apt/sources.list.d/cua-aliyun.sources
RUN rm -f /etc/apt/sources.list \
 && find /etc/apt/sources.list.d -maxdepth 1 \( -name '*.list' -o -name '*.sources' \) ! -name cua-aliyun.sources -delete \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends libreoffice-calc openbox python3-pil ristretto xauth xclip xdotool xvfb \
 && rm -rf /var/lib/apt/lists/*
ENV DISPLAY=:99 XAUTHORITY=/run/cua-desktop/Xauthority SAL_USE_VCLPLUGIN=gen

COPY cua/ /opt/cua/
COPY workspace/ /workspace/
COPY gui_server.py snapshot_server.py ready.py offline_web.py openbox.xml /usr/local/lib/cua-smoke/
RUN useradd -m -s /usr/sbin/nologin agent \
 && useradd -M -s /usr/sbin/nologin -G agent desktop-driver \
 && viewer=$(dpkg -L ristretto | sed -n 's@^/usr/share/applications/\(.*\.desktop\)$@\1@p') \
 && test -n "$viewer" \
 && runuser -u agent -- xdg-mime default "$viewer" image/png image/jpeg \
 && install -d -m 700 -o desktop-driver -g desktop-driver /var/lib/cua-mcp-audit \
 && install -d -m 700 /var/lib/cua \
 && install -d -m 755 -o agent -g agent /workspace/output /workspace/downloads \
 && install -D -m 644 /opt/cua/sources/chromium-policy.json /etc/chromium/policies/managed/cua.json \
 && install -m 644 /opt/cua/desktop_mcp.py /usr/local/lib/cua-smoke/desktop_mcp.py \
 && openssl req -new -x509 -newkey rsa:2048 -nodes -days 3650 -subj /CN=offline-cua-desktop \
      -keyout /opt/cua/offline.key -out /opt/cua/offline.crt \
 && chmod -R go-rwx /opt/cua \
 && chmod 700 /opt/cua/entrypoint.sh /opt/cua/web-entrypoint.sh

WORKDIR /workspace
HEALTHCHECK --interval=2s --timeout=4s --start-period=8s --retries=50 CMD ["/usr/bin/python3", "/usr/local/lib/cua-smoke/ready.py", "--check"]
ENTRYPOINT ["/opt/cua/entrypoint.sh"]
CMD ["/usr/bin/python3", "/usr/local/lib/cua-smoke/ready.py"]
