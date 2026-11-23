# Harbor 0.1.45 runs this installer even when the CLI is already in the image.
if [[ "$0" == /installed-agent/install.sh ]] && grep -Fq 'https://claude.ai/install.sh' "$0"; then
    /usr/local/bin/claude-native --version | grep -Fx '2.1.316 (Claude Code)'
    exit "$?"
fi

# Harbor launchers prepend the CLI installer directory to PATH.
claude() {
    /usr/local/bin/claude "$@"
}
