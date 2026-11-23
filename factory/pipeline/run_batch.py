#!/usr/bin/env python3
"""Turn allocation slots into packaged Harbor tasks.

    run_batch.py output/harbor/plan/batch01.jsonl [--only s001,s002] [--workers 3] [--rounds 3]
    run_batch.py output/harbor/plan/exp3.jsonl --engine codex --codex-model gpt-6.2-sol

Per slot (resumable; state in output/harbor/plan/<batch>.status.json):
  1. hard-task-author        writes factory/tasks_src/<slot>/ (spec, world, instruction, rubric, proposal)
  2. world.py -> build; a barrier sandbox gets only instruction/rubric/spec/seed/input/schemas
  3. hard-verifier-writer    writes tests/verifier.py in the sandbox (never sees world or golden)
  4. hard-instruction-stylist polishes instruction.md (style_lint must pass)
  5. package.py              fixture self-check is the gate; on failure a REVIEW.md with the
                             failing checks goes back to author and verifier for another round
Passed slots are appended to catalog/usage.jsonl so later batches avoid their sites.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import re
import threading
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path

from package import build_dists, copy_verifier_kit

FACTORY = Path(__file__).resolve().parents[1]
REPO = FACTORY.parent
CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
# world.py may render media (Pillow/reportlab) -> prefer the factory venv.
WORLD_PYTHON = str(FACTORY / ".venv" / "bin" / "python") if (FACTORY / ".venv" / "bin" / "python").exists() else sys.executable
WORK = REPO / "output" / "harbor" / "work"
LOGS = REPO / "output" / "harbor" / "logs"
LOCK = threading.Lock()
# Child CLIs start clean: no dead proxy, none of this parent session's runtime vars.
DROP = {"http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "CLAUDECODE",
        "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID"}
ENV = {k: v for k, v in os.environ.items() if k not in DROP}


API_OUTAGE = re.compile(r"API Error: (5\d\d|429)|No available accounts|overloaded_error|rate_limit_error", re.I)


def claude(agent: str, prompt: str, log: Path, cwd: Path = REPO) -> int:
    """Run an agent; if its run dies on an API outage (gateway 5xx, no accounts, rate limit),
    wait and rerun the same agent instead of burning a round on it."""
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "--agent", agent, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions"]
    for attempt, wait in enumerate([0, 120, 300, 600, 1200, 1800]):
        time.sleep(wait)
        start = log.stat().st_size if log.exists() else 0
        with log.open("a") as f:
            f.write(f"\n=== {datetime.now().isoformat()} {agent}\n")
            f.flush()
            code = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=f, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL).returncode
        with log.open(errors="ignore") as f:
            f.seek(start)
            tail = f.read()[-4000:]
        if not ('"is_error":true' in tail and API_OUTAGE.search(tail)):
            return code
        with log.open("a") as f:
            f.write(f"\n=== API outage, retrying {agent} (attempt {attempt + 2})\n")
    return code


def codex(agent: str, prompt: str, log: Path, cwd: Path = REPO, *, model: str) -> None:
    role = (FACTORY / "agents" / f"{agent}.md").read_text().split("---", 2)[-1].strip()
    app_binary = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
    binary = os.environ.get("CODEX_BIN") or (str(app_binary) if app_binary.is_file() else "codex")
    command = [binary, "-a", "never", "exec", "--model", model, "--json", "--ephemeral",
               "--ignore-user-config", "--skip-git-repo-check", "--sandbox",
               "workspace-write" if agent == "hard-verifier-writer" else "danger-full-access", "-"]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        stream.write(f"\n=== {datetime.now().isoformat()} {agent} codex model={model}\n")
        stream.flush()
        result = subprocess.run(command, cwd=cwd, env=ENV, text=True, input=f"{role}\n\n{prompt}\n",
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError(f"Codex {agent} exited {result.returncode}; see {log.relative_to(REPO)}")


def author_prompt(slot: dict, task_dir: Path, review: str | None, runtime: str = "auto") -> str:
    sites = {s: {k: CATALOG[s][k] for k in ("hub", "brand", "origins", "scenario", "hub_revision")
                 if k in CATALOG[s]} for s in slot["sites"]}
    spec_path = task_dir / "spec.json"
    if spec_path.is_file():
        revisions = build_dists.task_revisions(json.loads(spec_path.read_text()))
        for name in sites.keys() & revisions.keys():
            sites[name]["hub_revision"] = revisions[name]
    for settings in sites.values():
        if "hub_revision" in settings:
            build_dists.ensure_revision(settings["hub_revision"])
    levers = json.loads((FACTORY / "catalog" / "levers.json").read_text())
    lever_text = "".join(f"\nPrimary lever {l['id']} {l['name_zh']}: {l['what']} Build: {l['build']}"
                         for l in levers if l["id"] in slot.get("levers", [])[:1])
    text = (f"Author the task for this slot into {task_dir.relative_to(REPO)} (task name: cua-hard/<short-slug>).\n"
            f"Slot: {json.dumps(slot, ensure_ascii=False)}\nSites: {json.dumps(sites, ensure_ascii=False)}\n{lever_text}\n")
    if slot.get("premise"):
        text += (f"\nPremise to build from (adapt freely, keep it realistic): {slot['premise']}\n"
                 "The primary site is fixed. A companion that would make the story artificial may be swapped for a "
                 "better-fitting ready site from factory/catalog/sites.json, but the task must keep at least 3 "
                 "different websites, each one necessary to the work (spec.json `sites` is what counts).\n")
    if runtime != "legacy":
        runtime_rule = ("Author for the isolated computer-mcp desktop. " if runtime == "computer-mcp"
                        else "If spec.json declares computer_mcp, follow the isolated desktop contract. ")
        text += (
            f"\n{runtime_rule}For computer-mcp, declare desktop apps, output files and needed "
            "attachment names in spec.json computer_mcp. Provide solution/solve.py using only the packaged "
            "computer module for screenshot and mouse/keyboard operations. Ground each mock workflow in "
            "the app's normal layout and interactions and verify it on the desktop. Use a real operational "
            "difficulty lever other than L01. Document additive difficulty_review in rubric.json with "
            "simple_checks, named bypass/one_core/false_completion fixtures and at least four distinct "
            "constraint counterexamples. The simple total and each weak path must score at most 0.35. "
            "Exercise the strongest credible shortcut and include it in fixture_expectations. See "
            "交接迁移说明.md.\n"
        )
    if review:
        text += f"\nThe previous round failed self-check. Fix the world/rubric where they are wrong:\n{review}\n"
    return text


def build_world(task_dir: Path, build: Path):
    shutil.rmtree(build, ignore_errors=True)
    subprocess.run([WORLD_PYTHON, str(task_dir / "world.py"), str(build)], check=True, capture_output=True)


def make_sandbox(slot: dict, task_dir: Path, build: Path, sandbox: Path, review: str | None):
    keep = sandbox / "tests" / "verifier.py"
    previous = keep.read_text() if keep.exists() else None
    shutil.rmtree(sandbox, ignore_errors=True)
    (sandbox / "tests").mkdir(parents=True)
    for name in ("instruction.md", "rubric.json", "spec.json"):
        shutil.copy(task_dir / name, sandbox / name)
    shutil.copytree(build / "seed", sandbox / "seed")
    if (build / "input").is_dir():
        shutil.copytree(build / "input", sandbox / "input")
    (sandbox / "schemas").mkdir()
    spec = json.loads((task_dir / "spec.json").read_text())
    revisions = build_dists.task_revisions(spec)
    for site in slot["sites"]:
        schema = build_dists.read_schema(site, revision=revisions.get(site))
        if schema is not None:
            (sandbox / "schemas" / f"{site}.md").write_bytes(schema)
    copy_verifier_kit(sandbox / "tests", additive_scoring=spec.get("additive_scoring", False))
    if previous:
        keep.write_text(previous)
    if review:
        (sandbox / "REVIEW.md").write_text(review)


def selfcheck_review(output: str) -> str:
    return "Packaging and fixture self-check results:\n" + "\n".join(output.splitlines()[-60:])


def run_slot(slot: dict, rounds: int, status: dict, status_path: Path, agent_runner=claude, runtime="auto"):
    sid = slot["slot_id"]
    task_dir = FACTORY / "tasks_src" / sid
    sandbox, build, log = WORK / sid / "verifier_sandbox", WORK / sid / "build", LOGS / f"{sid}.log"
    review = None
    for attempt in range(1, rounds + 1):
        update(status, status_path, sid, f"round{attempt}:author")
        agent_runner("hard-task-author", author_prompt(slot, task_dir, review, runtime), log)
        if (task_dir / "gaps.json").exists():
            return update(status, status_path, sid, "blocked:ui_gap", gaps=json.loads((task_dir / "gaps.json").read_text()))
        try:
            build_world(task_dir, build)
        except subprocess.CalledProcessError as exc:
            review = f"world.py failed:\n{exc.stderr.decode()[-3000:]}"
            continue
        update(status, status_path, sid, f"round{attempt}:verifier")
        spec = json.loads((task_dir / "spec.json").read_text())
        spec_sites = spec.get("sites", slot["sites"])
        make_sandbox({**slot, "sites": spec_sites}, task_dir, build, sandbox, review)
        agent_runner("hard-verifier-writer", f"Sandbox: {sandbox}. Write tests/verifier.py there.", log, cwd=sandbox)
        if not (sandbox / "tests" / "verifier.py").exists():
            review = "verifier-writer produced no tests/verifier.py"
            continue
        (task_dir / "tests").mkdir(exist_ok=True)
        shutil.copy(sandbox / "tests" / "verifier.py", task_dir / "tests" / "verifier.py")
        update(status, status_path, sid, f"round{attempt}:style")
        agent_runner("hard-instruction-stylist", f"Task directory: {task_dir}", log)
        update(status, status_path, sid, f"round{attempt}:package")
        task_runtime = ("computer-mcp" if "computer_mcp" in spec else "legacy") if runtime == "auto" else runtime
        packaging = [sys.executable, str(FACTORY / "pipeline" / "package.py"), sid, "--runtime", task_runtime]
        if task_runtime == "computer-mcp":
            packaging.append("--require-difficulty-review")
        result = subprocess.run(packaging, capture_output=True, text=True)
        with log.open("a") as f:
            f.write(result.stdout + result.stderr)
        if result.returncode == 0:
            # Platform-like check (x86_64 host if DOCKER_HOST is set): oracle right after boot, then nop.
            check_command = [str(FACTORY / "pipeline" / "platform_check.sh"),
                             str(REPO / "output" / "harbor" / "tasks" / sid)]
            if agent_runner is not claude and task_runtime == "legacy":
                check_command.append("--reset")
            check = subprocess.run(check_command, capture_output=True, text=True, env=ENV)
            with log.open("a") as f:
                f.write("platform_check: " + check.stdout + check.stderr)
            if check.returncode != 0:
                review = "Packaged, but the platform-like check failed:\n" + (check.stdout + check.stderr)[-2000:]
                continue
            if agent_runner is not claude and task_runtime == "computer-mcp":
                evidence_parent = REPO / "output" / "harbor" / "reset" / sid
                evidence_parent.mkdir(parents=True, exist_ok=True)
                evidence = tempfile.mkdtemp(prefix=f"round-{attempt}-", dir=evidence_parent)
                reset_command = [sys.executable, str(FACTORY / "pipeline" / "check_reset_with_image.py"),
                                 str(FACTORY / "pipeline"), str(REPO / "output" / "harbor" / "tasks" / sid),
                                 "--out", evidence]
                reset = subprocess.run(reset_command, capture_output=True, text=True, env=ENV)
                with log.open("a") as f:
                    f.write(f"Reset evidence: {evidence}\n" + reset.stdout + reset.stderr)
                if reset.returncode:
                    review = "Same-instance Reset failed:\n" + (reset.stdout + reset.stderr)[-2000:]
                    continue
            with LOCK, (FACTORY / "catalog" / "usage.jsonl").open("a") as f:
                f.write(json.dumps({**slot, "task_dir": str(task_dir.relative_to(REPO))}, ensure_ascii=False) + "\n")
            return update(status, status_path, sid, "packaged", rounds=attempt, runtime=task_runtime)
        review = selfcheck_review(result.stdout + result.stderr)
    return update(status, status_path, sid, "failed", review=review)


def guarded(slot, rounds, status, status_path, agent_runner, runtime):
    try:
        run_slot(slot, rounds, status, status_path, agent_runner, runtime)
    except Exception as exc:  # keep the batch going; the slot is marked for a retry
        update(status, status_path, slot["slot_id"], "error", error=f"{type(exc).__name__}: {exc}"[:500])


def update(status, path, sid, state, **extra):
    with LOCK:
        status[sid] = {"state": state, "at": datetime.now().isoformat(timespec="seconds"), **extra}
        path.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"{sid}: {state}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--only")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--engine", choices=("claude", "codex"), default="claude")
    parser.add_argument("--runtime", choices=("auto", "legacy", "computer-mcp"), default="auto")
    parser.add_argument("--codex-model", default="gpt-6.2-sol")
    parser.add_argument("--retry", action="store_true", help="also rerun failed / ui-gap-blocked slots")
    parser.add_argument("--resume", action="store_true", help="keep an already-authored task and start from its verifier")
    args = parser.parse_args()
    slots = [json.loads(l) for l in args.plan.read_text().splitlines() if l.strip()]
    status_path = args.plan.with_suffix(".status.json")
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    wanted = set(args.only.split(",")) if args.only else None
    skip = {"packaged"} | (set() if args.retry else {"failed", "blocked:ui_gap"})
    todo = [s for s in slots if (not wanted or s["slot_id"] in wanted) and status.get(s["slot_id"], {}).get("state") not in skip]
    print(f"{len(todo)} slots to run")
    agent_runner = claude if args.engine == "claude" else partial(codex, model=args.codex_model)
    with ThreadPoolExecutor(args.workers) as pool:
        for slot in todo:
            pool.submit(guarded, slot, args.rounds, status, status_path, agent_runner, args.runtime)


if __name__ == "__main__":
    main()
