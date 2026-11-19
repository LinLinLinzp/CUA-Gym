#!/usr/bin/env bash
# Local Qwen pre-screen: Harbor's built-in claude-code agent driven by Qwen via
# Bailian's Anthropic-compatible endpoint. Tasks Qwen already solves are sent
# back before spending platform rollouts.
#
#   factory/pipeline/prescreen.sh <task-dir> [attempts]
#
# Reads DASHSCOPE_API_KEY, QWEN_ANTHROPIC_BASE_URL and QWEN_MODEL from .env.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
TASK=${1:?usage: prescreen.sh <task-dir> [attempts]}
ATTEMPTS=${2:-1}
set -a; source "$REPO/.env"; set +a
: "${DASHSCOPE_API_KEY:?missing in .env}" "${QWEN_ANTHROPIC_BASE_URL:?missing in .env}" "${QWEN_MODEL:?set QWEN_MODEL in .env}"

# Only the Bailian credentials may reach the agent: drop any Anthropic
# credentials and the (dead) proxy inherited from the calling shell.
exec env -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL -u ANTHROPIC_API_KEY \
  -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
  ANTHROPIC_API_KEY="$DASHSCOPE_API_KEY" ANTHROPIC_BASE_URL="$QWEN_ANTHROPIC_BASE_URL" \
  harbor run -p "$TASK" -a claude-code -m "$QWEN_MODEL" -k "$ATTEMPTS" \
    -o "$REPO/output/harbor/jobs" --job-name "prescreen-$(basename "$TASK")-$(date +%m%d-%H%M)"
