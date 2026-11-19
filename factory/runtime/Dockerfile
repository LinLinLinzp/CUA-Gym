# Shared task image: Playwright base + every site this task needs, served
# offline from one container. Package sources point at Aliyun mirrors.
ARG BASE_IMAGE=mcr.microsoft.com/playwright/python:v1.65.2-noble
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

USER root
# No apt step: the base image already has curl, procps, CA certs and CJK fonts
# (WenQuanYi Zen Hei, IPAGothic); apt from the platform network took 12+ minutes.
COPY cua/sources/pip.conf /etc/pip.conf
# pypdf gives agents PDF text extraction (replaces poppler's pdftotext).
RUN pip install --no-cache-dir playwright==1.65.2 aiohttp==3.13.2 pypdf==6.21.4

RUN useradd -m -s /bin/bash agent
COPY cua /opt/cua
COPY workspace /workspace
# Site code, seeds, oracle hash and state are root-only; the agent gets the
# browser MCP server (declared in task.toml), read-only inputs and its own
# output/download dirs.
RUN install -m 755 /opt/cua/browser/browser_mcp.py /usr/local/bin/browser-mcp \
 && chmod -R go-rwx /opt/cua \
 && chmod 755 /opt/cua/entrypoint.sh \
 && mkdir -p /workspace/input /workspace/output /workspace/downloads /var/lib/cua /logs/agent \
 && chown -R root:root /workspace /var/lib/cua && chmod -R a+rX,go-w /workspace/input \
 && chmod 755 /workspace && chmod 700 /var/lib/cua \
 && chown agent:agent /workspace/output /workspace/downloads

WORKDIR /workspace
ENTRYPOINT ["/opt/cua/entrypoint.sh"]
CMD ["sleep", "infinity"]
