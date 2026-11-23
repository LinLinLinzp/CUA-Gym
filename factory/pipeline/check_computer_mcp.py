#!/usr/bin/env python3
"""Run the packaged NOP and GUI Oracle on the same Harbor version as AP."""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

if __package__:
    from .ap_package import package_sha256, validate_package
    from .checkpoints import check_report
else:
    from ap_package import package_sha256, validate_package
    from checkpoints import check_report


GUI_ACTIONS = {
    "left_click", "right_click", "double_click", "triple_click", "left_click_drag",
    "key", "type", "scroll",
}


def count_gui_steps(actions):
    counts = Counter()
    total = 0
    previous = None
    with actions.open(encoding="utf-8") as stream:
        for line in stream:
            action = json.loads(line)["arguments"]["action"]
            total += 1
            if action not in GUI_ACTIONS:
                continue
            if action != "type" or previous != "type":
                counts[action] += 1
            previous = action
    return total, dict(sorted(counts.items()))


def trial_evidence(trial, jobs, agent, expected, checkpoint_ids, minimum_gui_steps):
    result = json.loads(trial.read_text())
    score = (result.get("verifier_result") or {}).get("rewards", {}).get("reward")
    if result.get("exception_info") or score != expected:
        raise SystemExit(f"{agent} returned {score}; expected {expected}. See {trial}")
    check_report(trial.parent / "verifier" / "report.json", checkpoint_ids, f"Harbor {agent}")
    evidence = {"reward": score, "trial": trial.relative_to(jobs).as_posix()}
    if agent == "oracle":
        actions = trial.parent / "verifier/terminal-state/actions.jsonl"
        if not actions.is_file() or not actions.stat().st_size:
            raise SystemExit(f"GUI Oracle has no desktop actions: {trial}")
        total, counts = count_gui_steps(actions)
        steps = sum(counts.values())
        if steps < minimum_gui_steps:
            raise SystemExit(f"GUI Oracle used {steps} effective steps; expected at least "
                             f"{minimum_gui_steps}. See {actions}")
        evidence.update(desktop_actions=total, gui_steps=steps, gui_actions_by_type=counts,
                        minimum_gui_steps=minimum_gui_steps)
        print(f"GUI Oracle effective steps: {steps} (minimum {minimum_gui_steps})", flush=True)
    print(f"{agent}={score} {trial}", flush=True)
    return evidence


def check_trials(harbor, task, jobs, checkpoint_ids, minimum_gui_steps):
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    evidence = {}
    for agent, expected in (("nop", 0.0), ("oracle", 1.0)):
        job = f"{task.name}-{agent}-{run_id}"
        subprocess.run(
            [harbor, "run", "-p", str(task), "-e", "docker", "-a", agent, "-o", str(jobs),
             "--job-name", job],
            check=True, cwd=task.parent,
        )
        trial, = (jobs / job).glob("*/result.json")
        evidence[agent] = trial_evidence(trial, jobs, agent, expected, checkpoint_ids, minimum_gui_steps)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Packaged task directory under <out>/tasks")
    parser.add_argument("--jobs", type=Path, default=Path("output/harbor/computer-mcp/jobs"))
    parser.add_argument("--min-gui-steps", type=int, default=0, help="Minimum effective native Oracle GUI steps")
    parser.add_argument("--audit-existing", action="store_true", help="Recheck retained Harbor trials for this archive")
    args = parser.parse_args()
    if args.min_gui_steps < 0:
        parser.error("--min-gui-steps must be nonnegative")
    task = args.task.resolve(strict=True)
    jobs = args.jobs.resolve()
    archive = task.parent.parent / "tars" / f"{task.name}-computer-mcp.tar.gz"
    checksum = archive.with_name(archive.name + ".sha256").read_text().split()[0]
    if package_sha256(archive) != checksum:
        raise SystemExit(f"Package checksum mismatch: {archive}")
    report_path = archive.with_name(archive.name + ".qa.json")
    with TemporaryDirectory(prefix="cua-ap-") as temp:
        extracted = Path(temp) / task.name
        checkpoint_ids = validate_package(archive, destination=extracted)
        print(f"AP file-only package {archive.name} SHA256 {checksum}", flush=True)
        if args.audit_existing:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
            if existing["archive_sha256"] != checksum or existing["harbor_version"] != "0.1.45":
                raise SystemExit(f"Retained Harbor report does not match {archive}")
            evidence = {}
            for agent, expected in (("nop", 0.0), ("oracle", 1.0)):
                trial = (jobs / existing[agent]["trial"]).resolve(strict=True)
                if not trial.is_relative_to(jobs):
                    raise SystemExit(f"Retained trial is outside {jobs}: {trial}")
                evidence[agent] = trial_evidence(
                    trial, jobs, agent, expected, checkpoint_ids, args.min_gui_steps,
                )
        else:
            harbor = shutil.which(os.environ.get("HARBOR_BIN", "harbor"))
            if not harbor or subprocess.check_output([harbor, "--version"], text=True).strip() != "0.1.45":
                raise SystemExit("Set HARBOR_BIN to the AP Harbor 0.1.45 executable")
            evidence = check_trials(str(Path(harbor).resolve()), extracted, jobs, checkpoint_ids, args.min_gui_steps)
    report = {"archive_sha256": checksum, "harbor_version": "0.1.45",
              "checkpoint_count": len(checkpoint_ids), **evidence}
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
