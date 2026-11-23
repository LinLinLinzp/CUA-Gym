#!/usr/bin/env bash
set -euo pipefail
# Thin wrapper: all grading lives in Python.
exec python3 /tests/verifier.py
