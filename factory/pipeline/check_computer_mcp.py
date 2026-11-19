#!/usr/bin/env python3
"""Run the packaged NOP and GUI Oracle on the same Harbor version as AP."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("--jobs", type=Path, default=Path("output/harbor/computer-mcp/jobs"))
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    jobs = args.jobs.resolve()
    harbor = os.environ.get("HARBOR_BIN", "harbor")
    version = subprocess.check_output([harbor, "--version"], text=True).strip()
    if version != "0.1.45":
        raise SystemExit(f"Expected AP Harbor 0.1.45, got {version}; set HARBOR_BIN to the legacy CLI")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for agent, expected in (("nop", 0.0), ("oracle", 1.0)):
        job = f"{task.name}-{agent}-{run_id}"
        subprocess.run(
            [harbor, "run", "-p", str(task), "-e", "docker", "-a", agent, "-o", str(jobs),
             "--job-name", job],
            check=True, cwd=task.parent,
        )
        trial, = (jobs / job).glob("*/result.json")
        result = json.loads(trial.read_text())
        score = (result.get("verifier_result") or {}).get("rewards", {}).get("reward")
        if result.get("exception_info") or score != expected:
            raise SystemExit(f"{agent} returned {score}; expected {expected}. See {trial}")
        if agent == "oracle":
            actions = trial.parent / "verifier/terminal-state/actions.jsonl"
            if not actions.is_file() or not actions.stat().st_size:
                raise SystemExit(f"GUI Oracle has no desktop actions: {trial}")
        print(f"{agent}={score} {trial}", flush=True)


if __name__ == "__main__":
    main()
