#!/usr/bin/env python3
"""Positive/negative self-test: run verifier.py on every fixture in fixtures/
and check the reward falls in the range recorded in fixtures/expectations.json.

    python3 tests/test_verifier.py
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def score(fixture: Path, report: Path | None = None) -> float:
    with tempfile.TemporaryDirectory() as logs:
        output = fixture / "output"
        env = {**os.environ, "CUA_VAR_DIR": str(fixture), "CUA_OUTPUT_DIR": str(output),
               "CUA_VERIFIER_LOG_DIR": logs, "CUA_SETTLE_SECONDS": "0"}
        result = subprocess.run([sys.executable, str(HERE / "verifier.py")], env=env, capture_output=True, text=True)
        match = re.search(r"REWARD: ([0-9.]+)", result.stdout)
        if result.returncode != 0 or not match:
            raise RuntimeError(f"{fixture.name}: verifier failed\n{result.stdout}\n{result.stderr}")
        if report is not None:
            source = Path(logs) / "report.json"
            if not source.is_file():
                raise RuntimeError(f"D11 fixture {fixture.name}: verifier did not write report.json")
            shutil.copyfile(source, report)
        return float(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, help="Save the reports emitted by the fixture runs")
    args = parser.parse_args()
    if args.reports_dir is not None:
        args.reports_dir.mkdir(parents=True, exist_ok=True)
    expectations = json.loads((HERE / "fixtures" / "expectations.json").read_text())
    failed = 0
    for index, (name, (low, high)) in enumerate(expectations.items()):
        report = args.reports_dir / f"{index}.json" if args.reports_dir is not None else None
        reward = score(HERE / "fixtures" / name, report)
        ok = low <= reward <= high
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name:<12} reward={reward:<7} expected [{low}, {high}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
