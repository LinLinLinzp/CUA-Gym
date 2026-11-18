# Shared task image: Playwright base + every site this task needs, served
# offline from one container. Package sources point at Aliyun mirrors.
ARG BASE_IMAGE=mcr.microsoft.com/playwright/python:v1.65.2-noble
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

USER root
COPY cua/sources/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources
COPY cua/sources/pip.conf /etc/pip.conf
# Aliyun serves non-amd64 Ubuntu packages from /ubuntu-ports/.
RUN rm -f /etc/apt/sources.list \
 && if [ "$(dpkg --print-architecture)" != amd64 ]; then sed -i 's#/ubuntu/#/ubuntu-ports/#' /etc/apt/sources.list.d/ubuntu.sources; fi \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends curl ca-certificates procps poppler-utils fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir playwright==1.65.2 aiohttp==3.13.2

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
