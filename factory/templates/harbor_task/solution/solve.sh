#!/usr/bin/env bash
set -euo pipefail
# Reference solution: writes the golden end state directly (no UI replay).
exec python3 /solution/apply_golden.py
