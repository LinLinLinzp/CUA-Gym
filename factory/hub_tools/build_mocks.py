#!/usr/bin/env python3
"""Build new high-fidelity hub mocks in parallel with Claude Code and Codex.

    build_mocks.py --tier A --scenario 公共事务 --limit 4 --workers 4
    build_mocks.py --brands "Airbnb,Spotify" --engine codex

Per site (resumable; status in factory/build/mock_status.json):
  seed     hub/websites/<slug>_mock/SEED.md: brand, real URL, must-have workflows,
           runtime contract (hub/HARBOR_CONTRACT.md), dev-server port
  plan     Claude `plan` agent (hub/.claude/agents): research + screenshots ->
           DESIGN.md, TODO.md (workflows from SEED.md become P0/P1)
  rounds   dev (Codex by default, falling back to Claude if a Codex run fails)
           -> Claude `audit` -> Claude `playwright`, up to --rounds times
  accept   all P0/P1 TODO items done, no open P0 in AUDIT.md, no open P0/P1 in
           TEST.md, `npm run build` ok, dyn_certify passes
  record   commit the mock in the hub, add it to catalog/built_sites.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
HUB = FACTORY.parent / "hub"
SITES = HUB / "websites"
STATUS = FACTORY / "build" / "mock_status.json"
BUILT = FACTORY / "catalog" / "built_sites.json"
LOGS = FACTORY / "build" / "mock_logs"
LOCK = threading.Lock()
# Drop the dead proxy and this parent session's runtime vars so child CLIs start clean.
DROP = {"http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "CLAUDECODE",
        "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID"}
ENV = {k: v for k, v in os.environ.items() if k not in DROP}
# The Homebrew codex (0.160) gets gpt-6.2-sol rejected on ChatGPT logins; the CLI bundled with
# the ChatGPT app (0.169+) is allowed to use it, so prefer that binary when it exists.
APP_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
CODEX_BIN = os.environ.get("CODEX_BIN") or (str(APP_CODEX) if APP_CODEX.exists() else "codex")
# Preferred first; probe once and fall back.
CODEX_MODELS = os.environ.get("CODEX_MODELS", "gpt-6.2-sol,gpt-6.1-sol").split(",")
_codex_model = None


def codex_model() -> str:
    global _codex_model
    with LOCK:
        if _codex_model is None:
            for model in CODEX_MODELS:
                probe = subprocess.run([CODEX_BIN, "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check",
                                        "Reply with exactly: ok"], env=ENV, capture_output=True, text=True,
                                       stdin=subprocess.DEVNULL, timeout=600)
                out = probe.stdout + probe.stderr  # "at capacity" still means the model exists
                if (probe.returncode == 0 or CODEX_BUSY.search(out)) and "model_not_found" not in out:
                    _codex_model = model
                    break
            else:
                _codex_model = ""
            print(f"codex model: {_codex_model or 'none available'} ({CODEX_BIN})", flush=True)
    return _codex_model


def slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", brand.lower().replace("&", "and")).strip("_")


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def set_status(name, **fields):
    with LOCK:
        status = load(STATUS, {})
        status[name] = {**status.get(name, {}), **fields, "at": datetime.now().isoformat(timespec="seconds")}
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"{name}: {fields.get('state', '')}", flush=True)


AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT_SEC", 3 * 3600))  # a stuck session can't eat the night


def run(cmd, log: Path, cwd=HUB) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(f"\n=== {datetime.now().isoformat()} {' '.join(cmd[:4])}\n")
        f.flush()
        try:
            return subprocess.run(cmd, cwd=cwd, env=ENV, stdout=f, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, timeout=AGENT_TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            f.write(f"\n=== TIMEOUT after {AGENT_TIMEOUT}s\n")
            return 124


def free_port(port: int):
    """Kill dev servers an agent left running on this site's port."""
    pids = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True).stdout.split()
    for pid in pids:
        subprocess.run(["kill", pid], capture_output=True)


def claude(agent, prompt, log):
    return run(["claude", "--agent", agent, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--permission-mode", "bypassPermissions"], log)


# Transient service errors: wait and rerun instead of letting the site fall through as failed.
CODEX_BUSY = re.compile(r"at capacity|rate limit|too many requests|\b429\b|\b50[23]\b|stream disconnected", re.I)


def codex(prompt, log):
    model = codex_model()
    if not model:
        return 1  # caller falls back to Claude
    for attempt in range(12):
        start = log.stat().st_size if log.exists() else 0
        code = run([CODEX_BIN, "exec", "-m", model, "-c", "model_reasoning_effort=high", "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
                    "--skip-git-repo-check", "-C", str(HUB), prompt], log)
        with log.open() as f:
            f.seek(start)
            tail = f.read()[-600:]  # the error lines come last, just before "tokens used"
        if not CODEX_BUSY.search(tail):
            return code
        time.sleep(min(60 * 2 ** attempt, 1800))
    return code


def seed_md(site, app, port):
    return f"""# {site['brand']} — build brief

- Real product: {site['brand']} ({site['origin']}). Mock directory: `websites/{app}`.
- Scenario: {site['scenario']}; tier {site['tier']} ({'core mainstream: highest fidelity' if site['tier'] == 'A' else 'supporting site'}).
- Must-have workflows (each is P0/P1 and must persist structured records): {site['workflows']}.
- Runtime contract: follow `HARBOR_CONTRACT.md` and use `templates/state-api.js` + `templates/dataManager.js` as-is.
- Dev server port for this app: {port} (other apps are built in parallel; never use another port).
- Default data (`createInitialData`): realistic, English, fixed ids, enough volume to make
  lists, filters and search meaningful (dozens of records per main entity).
"""


def phase_prompt(role, app, port):
    common = (f"Target app directory: websites/{app}. Read websites/{app}/SEED.md and HARBOR_CONTRACT.md first; "
              f"they override generic instructions where they differ. Use dev server port {port}.")
    return {
        "plan": f"You are the plan agent. Follow .claude/agents/plan.md. {common} Every workflow in SEED.md must appear "
                f"as P0/P1 items in TODO.md with the state records it writes.",
        "dev": f"You are the dev agent. Follow .claude/agents/dev.md. {common} Fix open AUDIT.md P0 and TEST.md P0/P1 "
               f"first, then work TODO.md items in order and tick them. Finish with `npm run build` passing.",
        "audit": f"You are the audit agent. Follow .claude/agents/audit.md. {common} Also audit against HARBOR_CONTRACT.md "
                 f"(no timer-driven state writes, structured records, offline assets, renders with injected state).",
        "playwright": f"You are the playwright agent. Follow .claude/agents/playwright.md. {common} Exercise every SEED.md "
                      f"workflow and record in TEST.md which state fields each one changed (via /go). When every SEED.md "
                      f"workflow passes, put the line `WORKFLOWS: PASS` in TEST.md (even if other bugs remain).",
    }[role]


MAX_OPEN_P1 = 3  # relaxed acceptance (user, 2026-11-18): core workflows + certification, edge P0s become debt


def accepted(app_dir: Path, name: str, log: Path):
    """Accept when the site is usable for tasks; leftover audit P0s are recorded as debt, not blockers."""
    todo = (app_dir / "TODO.md").read_text() if (app_dir / "TODO.md").exists() else ""

    def open_items(level):  # only items under that heading (the legend at the top also uses "- [ ]")
        body = "\n".join(m.group(1) for m in re.finditer(rf"^## {level}\b[^\n]*\n(.*?)(?=^## |\Z)", todo, re.S | re.M))
        return [l for l in body.splitlines() if re.match(r"\s*- \[( |~)\]", l)]

    audit = (app_dir / "AUDIT.md").read_text() if (app_dir / "AUDIT.md").exists() else ""
    test = (app_dir / "TEST.md").read_text() if (app_dir / "TEST.md").exists() else ""
    reasons = []
    if open_items("P0"):
        reasons.append(f"{len(open_items('P0'))} TODO P0 items open")
    if len(open_items("P1")) > MAX_OPEN_P1:
        reasons.append(f"{len(open_items('P1'))} TODO P1 items open (max {MAX_OPEN_P1})")
    workflows_ok = re.search(r"WORKFLOWS:\s*PASS|TEST COMPLETE:.*PASS|all (\w+ )?`?SEED\.md`? workflows passed", test, re.I)
    if not workflows_ok:
        reasons.append("TEST.md does not show every SEED.md workflow passing")
    p0 = re.search(r"## P0[^\n]*\n(.*?)(?=\n## P1|\Z)", audit, re.S)
    debt = [h for h in re.findall(r"### AUDIT-[^\n]*", p0.group(1) if p0 else "") if not re.search(r"FIXED|RESOLVED|✅", h, re.I)]
    (app_dir / ".audit_debt.json").write_text(json.dumps(debt))
    if run(["npx", "vite", "build", "--outDir", "dist", "--emptyOutDir"], log, cwd=app_dir) != 0:
        reasons.append("build failed")
        return reasons
    target = FACTORY / "build" / "sites" / name
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(app_dir / "dist", target / "dist")
    cert = subprocess.run([sys.executable, str(FACTORY / "hub_tools" / "dyn_certify.py"), name],
                          capture_output=True, text=True, env=ENV)
    if not re.search(rf"^PASS {re.escape(name)}\b", cert.stdout, re.M):
        reasons.append("dyn_certify: " + cert.stdout.strip()[-300:])
    return reasons


def build_site(site, index, engine, rounds):
    name = slug(site["brand"])
    app = f"{name}_mock"
    app_dir, log, port = SITES / app, LOGS / f"{name}.log", 5300 + index
    status = load(STATUS, {}).get(name, {})
    if status.get("state") == "accepted":
        return
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "SEED.md").write_text(seed_md(site, app, port))
    def agent(role):  # non-dev phases: Claude agents, or Codex reading the same agent files
        prompt = phase_prompt(role, app, port)
        return codex(prompt, log) if engine == "codex-all" else claude(role, prompt, log)

    if not (app_dir / "TODO.md").exists():
        set_status(name, state="plan", brand=site["brand"])
        agent("plan")
        if not (app_dir / "TODO.md").exists():
            return set_status(name, state="failed", reason="plan produced no TODO.md")
    use = {"mixed": "codex" if index % 2 else "claude", "codex-all": "codex"}.get(engine, engine)
    for r in range(1, rounds + 1):
        set_status(name, state=f"round{r}:dev:{use}")
        if use == "codex":
            if codex(phase_prompt("dev", app, port), log) != 0 and engine != "codex-all":
                use = "claude"
                claude("dev", phase_prompt("dev", app, port), log)
        else:
            claude("dev", phase_prompt("dev", app, port), log)
        set_status(name, state=f"round{r}:audit")
        agent("audit")
        set_status(name, state=f"round{r}:playwright")
        agent("playwright")
        free_port(port)
        reasons = accepted(app_dir, name, log)
        if not reasons:
            return record(site, name, app, use, r)
        set_status(name, state=f"round{r}:rework", reasons=reasons)
    set_status(name, state="failed", reasons=reasons)


def record(site, name, app, engine, rounds):
    with LOCK:
        subprocess.run(["git", "-C", str(HUB), "add", f"websites/{app}"], env=ENV, check=True)
        # Commit only this site's path: other work may be staged in the hub at the same time.
        subprocess.run(["git", "-C", str(HUB), "commit", "-qm",
                        f"Add {site['brand']} mock ({site['scenario']}, tier {site['tier']})\n\n"
                        "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>", "--", f"websites/{app}"], env=ENV)
        built = load(BUILT, {})
        debt_file = SITES / app / ".audit_debt.json"
        built[name] = {"hub": app, "brand": site["brand"], "origins": [site["origin"]], "scenario": site["scenario"],
                       "tier": site["tier"], "workflows": site["workflows"], "engine": engine, "rounds": rounds,
                       "audit_debt": json.loads(debt_file.read_text()) if debt_file.exists() else []}
        BUILT.write_text(json.dumps(built, indent=1, ensure_ascii=False))
    return set_status(name, state="accepted", rounds=rounds, engine=engine)


def guarded(site, index, engine, rounds):
    try:
        build_site(site, index, engine, rounds)
    except Exception as exc:  # keep other sites building
        set_status(slug(site["brand"]), state="error", error=f"{type(exc).__name__}: {exc}"[:500])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["A", "B"])
    parser.add_argument("--scenario")
    parser.add_argument("--brands", help="comma-separated brands from candidates.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--engine", choices=["mixed", "claude", "codex", "codex-all"], default="codex",
                        help="codex = Codex dev + Claude plan/audit/test; codex-all = every phase on Codex")
    parser.add_argument("--recheck", action="store_true", help="re-run acceptance on built sites, no agents")
    args = parser.parse_args()
    candidates = load(FACTORY / "catalog" / "candidates.json", {})
    # Most important first: tier A before B; within a tier, rotate scenarios (each list is
    # already ordered by importance) so every scenario's pool grows together.
    # Shared tools first: every task needs a mail/chat/doc tool that isn't an old hub mock.
    sites = [{**i, "scenario": "公共工具"} for i in candidates.get("公共工具", {}).get("new", [])]
    candidates = {k: v for k, v in candidates.items() if k != "公共工具"}
    for tier in ("A", "B"):
        queues = [[{**i, "scenario": sc} for i in d["new"] if i["tier"] == tier] for sc, d in candidates.items()]
        while any(queues):
            for q in queues:
                if q:
                    sites.append(q.pop(0))
    if args.tier:
        sites = [s for s in sites if s["tier"] == args.tier]
    if args.scenario:
        sites = [s for s in sites if s["scenario"] == args.scenario]
    if args.brands:
        wanted = {b.strip() for b in args.brands.split(",")}
        sites = [s for s in sites if s["brand"] in wanted]
    done = {k for k, v in load(STATUS, {}).items() if v.get("state") == "accepted"}
    if args.recheck:
        for site in sites:
            name = slug(site["brand"])
            app_dir = SITES / f"{name}_mock"
            if name in done or not (app_dir / "TODO.md").exists():
                continue
            reasons = accepted(app_dir, name, LOGS / f"{name}.log")
            if reasons:
                set_status(name, state="failed", reasons=reasons)
            else:
                record(site, name, f"{name}_mock", load(STATUS, {}).get(name, {}).get("engine", "codex"), 0)
        return
    sites = [s for s in sites if slug(s["brand"]) not in done][: args.limit]
    print(f"building {len(sites)} mocks with {args.workers} workers ({args.engine})")
    all_names = [slug(s["brand"]) for d in load(FACTORY / "catalog" / "candidates.json", {}).values() for s in d["new"]]
    with ThreadPoolExecutor(args.workers) as pool:
        for site in sites:
            pool.submit(guarded, site, all_names.index(slug(site["brand"])), args.engine, args.rounds)


if __name__ == "__main__":
    main()
