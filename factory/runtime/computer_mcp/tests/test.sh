#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt
# Allow the browser's debounced state writes to reach the desktop before collection.
sleep 2
python3 /tests/get_snapshot.py
export CUA_VAR_DIR=/logs/verifier/terminal-state/var
export CUA_OUTPUT_DIR=/logs/verifier/terminal-state/output
export CUA_SETTLE_SECONDS=0
exec python3 /tests/verifier.py
