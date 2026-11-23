ARG MAIN_BASE_IMAGE=python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
FROM ${MAIN_BASE_IMAGE}

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    npm_config_registry=https://registry.npmmirror.com

COPY debian-aliyun.sources /etc/apt/sources.list.d/cua-aliyun.sources
RUN rm -f /etc/apt/sources.list \
 && find /etc/apt/sources.list.d -maxdepth 1 \( -name '*.list' -o -name '*.sources' \) ! -name cua-aliyun.sources -delete \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends ca-certificates curl git procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir openpyxl==3.1.5 \
 && useradd -m -u 1001 -s /bin/bash agent \
 && install -d -o agent -g agent /workspace

RUN set -eu; \
    artifact='@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.316.tgz'; \
    curl -fsSL --retry 2 --connect-timeout 15 "https://registry.npmmirror.com/$artifact" -o /tmp/claude.tgz; \
    echo '745e1b196eb475161a185a00f5e1144d7324ec6094e21149eae719fa42481000  /tmp/claude.tgz' | sha256sum -c -; \
    tar -xOzf /tmp/claude.tgz package/claude > /usr/local/bin/claude-native; \
    chmod 755 /usr/local/bin/claude-native; \
    rm /tmp/claude.tgz

COPY --chmod=755 claude /usr/local/bin/claude
COPY --chmod=755 gui-tool-gate /usr/local/bin/cua-gui-tool-gate
COPY mcp.json claude-shell.sh /etc/cua-smoke/
COPY managed-settings.json /etc/claude-code/managed-settings.json

ENV BASH_ENV=/etc/cua-smoke/claude-shell.sh \
    ENABLE_TOOL_SEARCH=false MCP_CONNECTION_NONBLOCKING=0 \
    DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

WORKDIR /workspace
