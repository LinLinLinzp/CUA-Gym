#!/usr/bin/env python3
"""Run the packaged NOP and GUI Oracle on the same Harbor version as AP."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

if __package__:
    from .ap_package import package_sha256, validate_package
else:
    from ap_package import package_sha256, validate_package


def check_trials(harbor, task, jobs):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Packaged task directory under <out>/tasks")
    parser.add_argument("--jobs", type=Path, default=Path("output/harbor/computer-mcp/jobs"))
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    jobs = args.jobs.resolve()
    harbor = shutil.which(os.environ.get("HARBOR_BIN", "harbor"))
    if not harbor or subprocess.check_output([harbor, "--version"], text=True).strip() != "0.1.45":
        raise SystemExit("Set HARBOR_BIN to the AP Harbor 0.1.45 executable")
    harbor = str(Path(harbor).resolve())

    archive = task.parent.parent / "tars" / f"{task.name}-computer-mcp.tar.gz"
    checksum = archive.with_name(archive.name + ".sha256").read_text().split()[0]
    if package_sha256(archive) != checksum:
        raise SystemExit(f"Package checksum mismatch: {archive}")
    with TemporaryDirectory(prefix="cua-ap-") as temp:
        extracted = Path(temp) / task.name
        validate_package(archive, destination=extracted)
        print(f"AP file-only package {archive.name} SHA256 {checksum}", flush=True)
        check_trials(harbor, extracted, jobs)


if __name__ == "__main__":
    main()
