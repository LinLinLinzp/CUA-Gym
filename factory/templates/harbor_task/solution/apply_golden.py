#!/usr/bin/env python3
"""Oracle: push golden site states through sitehost's token-gated endpoint and
copy golden workspace outputs. Runs as the unprivileged agent user."""

import json
import shutil
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
states = {p.stem: json.loads(p.read_text()) for p in sorted((HERE / "golden").glob("*.json"))}
request = urllib.request.Request(
    "http://127.0.0.1:8090/__oracle/apply",
    data=json.dumps(states).encode(),
    headers={"Content-Type": "application/json", "x-cua-oracle": (HERE / "oracle_token").read_text().strip()},
)
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.read().decode())

outputs = HERE / "golden_output"
if outputs.is_dir():
    for file in outputs.iterdir():
        shutil.copy(file, Path("/workspace/output") / file.name)
        print("wrote", file.name)
