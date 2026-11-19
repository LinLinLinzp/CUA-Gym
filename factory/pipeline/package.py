#!/usr/bin/env python3
"""Assemble a Harbor task package from factory/tasks_src/<task>/.

    python3 factory/pipeline/package.py damage-claims-backlog [--out output/harbor]

Steps: run world.py -> fixture self-check (refuses to package on failure) ->
build site dists + offline assets -> write output/harbor/tasks/<task>/ ->
tar.gz without a top-level directory in output/harbor/tars/.

Task source layout (what the generation agents produce):
  spec.json  instruction.md  world.py  rubric.json  proposal.md  tests/verifier.py
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if __package__:
    from .ap_package import AP_AGENT_TIMEOUT_SEC, DESKTOP_MCP_URL, package_sha256, validate_package
else:
    from ap_package import AP_AGENT_TIMEOUT_SEC, DESKTOP_MCP_URL, package_sha256, validate_package

FACTORY = Path(__file__).resolve().parents[1]
REPO = FACTORY.parent
sys.path.insert(0, str(FACTORY / "hub_tools"))
import build_dists  # noqa: E402
import offline_assets  # noqa: E402

CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
# world.py may render media (Pillow/reportlab) -> prefer the factory venv.
WORLD_PYTHON = str(FACTORY / ".venv" / "bin" / "python") if (FACTORY / ".venv" / "bin" / "python").exists() else sys.executable
TEMPLATE = FACTORY / "templates" / "harbor_task"
COMPUTER_RUNTIME = FACTORY / "runtime" / "computer_mcp"
# Labels are numeric. operation_difficulty: 1 初级 / 2 中级 / 3 高级;
# tool_type: 1 纯web / 2 web+app 或 web+cli / 3 web+cli+app; difficulty = product
# (1-2 简单, 3-4 中等, 6/9 困难).
AGENT_TIMEOUT_SEC = 18000.0


def check_labels(md: dict):
    op, tool, difficulty = md["operation_difficulty"], md["tool_type"], md["difficulty"]
    if op not in (1, 2, 3) or tool not in (1, 2, 3):
        raise SystemExit(f"operation_difficulty/tool_type must be 1-3, got {op}/{tool}")
    if difficulty != op * tool:
        raise SystemExit(f"difficulty {difficulty} != operation_difficulty {op} x tool_type {tool}")


def run_world(src: Path, build: Path):
    subprocess.run([WORLD_PYTHON, str(src / "world.py"), str(build)], check=True)


def copy_verifier_kit(tests: Path, *, additive_scoring: bool):
    kit = FACTORY / "verifier_kit"
    additive = kit / "cuaverify_additive.py"
    if additive_scoring:
        shutil.copy(additive, tests / "cuaverify.py")
    else:
        shutil.copy(additive, tests)
        shutil.copy(kit / "cuaverify.py", tests)


def selfcheck(src: Path, build: Path, spec: dict) -> dict:
    """Score every fixture variant with the task's verifier; return {name: reward}."""
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        shutil.copytree(src / "tests", tests)
        copy_verifier_kit(tests, additive_scoring=spec.get("additive_scoring", False))
        if (build / "expected.json").exists():
            shutil.copy(build / "expected.json", tests)
        shutil.copytree(build / "variants", tests / "fixtures")
        (tests / "fixtures" / "expectations.json").write_text(json.dumps(spec["fixture_expectations"]))
        shutil.copy(TEMPLATE / "tests" / "test_verifier.py", tests)
        result = subprocess.run([sys.executable, str(tests / "test_verifier.py")], capture_output=True, text=True)
        print(result.stdout, end="")
        if result.returncode != 0:
            raise SystemExit(f"fixture self-check failed:\n{result.stderr}")
    return {line.split()[1]: float(line.split("reward=")[1].split()[0])
            for line in result.stdout.splitlines() if line.startswith("PASS")}


def task_toml(spec: dict, *, computer_mcp: bool = False) -> str:
    md = spec["metadata"]
    check_labels(md)
    keywords = ", ".join(json.dumps(k) for k in spec["keywords"])
    artifacts = 'artifacts = ["/workspace/output", "/logs/agent/browser", "/var/lib/cua/state"]'
    endpoint = (
        f'name = "desktop"\ntransport = "streamable-http"\nurl = "{DESKTOP_MCP_URL}"'
        if computer_mcp else 'name = "browser"\ntransport = "stdio"\ncommand = "/usr/local/bin/browser-mcp"'
    )
    healthcheck = '' if computer_mcp else '''[environment.healthcheck]
command = "curl -fsS http://127.0.0.1:8079/health >/dev/null && curl -fsS http://127.0.0.1:8090/__health >/dev/null"
interval_sec = 2.0
timeout_sec = 10.0
retries = 30

'''
    environment = f'''[environment]
build_timeout_sec = 1800.0
cpus = 2
memory_mb = 4096
storage_mb = 10240'''
    mcp_servers = f"[[environment.mcp_servers]]\n{endpoint}"
    header = f"\n{mcp_servers}\n\n{environment}" if computer_mcp else artifacts
    footer = "" if computer_mcp else f"\n{environment}\n\n{healthcheck}{mcp_servers}\n"
    desktop_apps = "\ndesktop_apps = " + json.dumps(spec["computer_mcp"]["applications"]) if computer_mcp else ""
    verifier_mode = '\nenvironment_mode = "shared"' if computer_mcp else ""
    agent_timeout = float(AP_AGENT_TIMEOUT_SEC if computer_mcp else spec.get("agent_timeout_sec", AGENT_TIMEOUT_SEC))
    return f'''schema_version = "1.4"
{header}

[task]
name = "{spec["name"]}"
version = "{spec["version"]}"
description = {json.dumps(spec["description"], ensure_ascii=False)}
authors = []
keywords = [{keywords}]

[metadata]
scenario = "{md["scenario"]}"
subscenario = "{md.get("subscenario", "")}"
operation_difficulty = {md["operation_difficulty"]}
tool_type = {md["tool_type"]}
difficulty = {md["difficulty"]}
sites = [{", ".join(json.dumps(CATALOG[s]["brand"]) for s in spec["sites"])}]
language = "en"{desktop_apps}

[agent]
timeout_sec = {agent_timeout}
user = "agent"

[verifier]
timeout_sec = 600.0
user = "root"{verifier_mode}
{footer}'''


def checkpoints_md(rubric: dict) -> str:
    common = rubric.get("common", {})
    lines = [
        "# Verifier 检查点清单", "",
        f"任务：`{rubric['task_id']}`；任务版本：`{rubric['task_version']}`；校验器版本：`{rubric['verifier_version']}`。", "",
        "本清单由 `rubric.json` 生成，修改规则时请先改 `rubric.json` 再重新打包。", "",
        "## 评分口径", "", rubric["reward_rule"], "",
        "## 数值与时间口径", "", rubric.get("numeric_rule", "无"), "",
        "## 全部检查点", "",
        "| 检查点编号 | 对应任务要求 | 要求类型 | 检查内容与证据 | 判定标准 | 实现或评审方式 | 分值/权重 | 评分方式 | 覆盖状态 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cp in rubric["checkpoints"]:
        row = {**common, **cp}
        rule = row["rule"] + (f"（陷阱：{row['trap']}）" if row.get("trap") else "")
        lines.append(f"| {row['id']} | {row['requirement']} | {row['type']} | {row['evidence']} | {rule} | "
                     f"{row['implementation']} | {row['weight']} | {row['score_mode']} | {row['coverage']} |")
    lines += ["", "## 主观检查点", "", rubric.get("subjective_note", "无主观项。") if not rubric.get("subjective") else
              "\n".join(f"- {s['id']}：{s['dimension']}" for s in rubric["subjective"])]
    if rubric.get("fixtures"):
        lines += ["", "## 正反例自测", "", "| 夹具 | 预期 |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in rubric["fixtures"].items()]
    return "\n".join(lines) + "\n"


def evaluation_json(spec: dict, rewards: dict) -> dict:
    return {
        "task_id": spec["name"], "task_version": spec["version"], "status": "not_run", "frozen": False,
        "agent": "harbor built-in claude-code",
        "thresholds": {"qwen": {"valid_runs": 5, "mean_at_most": 0.4}, "opus": {"valid_runs": 2, "mean_greater_than": 0.4}},
        "fixture_selfcheck": rewards, "attempts": [],
        "notes": ["夹具分数来自作者构造的终态，不是模型 rollout；正式难度以平台 task-eval 结果为准。"],
    }


def copy_runtime(env: Path):
    cua = env / "cua"
    env.mkdir(parents=True)
    shutil.copy(FACTORY / "runtime" / "Dockerfile", env / "Dockerfile")
    for part in ("sitehost", "browser", "sources"):
        shutil.copytree(FACTORY / "runtime" / part, cua / part, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(FACTORY / "runtime" / "entrypoint.sh", cua / "entrypoint.sh")


def snapshot_manifest(spec: dict) -> dict:
    desktop = spec["computer_mcp"]
    if desktop["applications"] not in ([], ["libreoffice_calc"]):
        raise ValueError("Unsupported computer MCP desktop applications")
    sites = spec["sites"]
    outputs = desktop["outputs"]
    attachments = desktop.get("attachments", {})
    for site, names in attachments.items():
        if site not in sites:
            raise ValueError(f"Snapshot attachment site is outside the task: {site}")
    for name in [*outputs, *(name for names in attachments.values() for name in names)]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]*", name):
            raise ValueError(f"Snapshot entries must be filenames: {name}")
    return {"sites": sites, "outputs": outputs, "attachments": attachments}


def copy_computer_runtime(env: Path, spec: dict):
    shutil.copytree(COMPUTER_RUNTIME / "environment", env, ignore=shutil.ignore_patterns("__pycache__"))
    cua = env / "desktop" / "cua"
    shutil.copytree(FACTORY / "runtime" / "sitehost", cua / "sitehost",
                    ignore=shutil.ignore_patterns("__pycache__"))
    if spec["computer_mcp"]["applications"]:
        shutil.copy(COMPUTER_RUNTIME / "registrymodifications.xcu", cua / "sources")
    return cua


def stage_computer_oracle(src: Path, solution: Path, draft: bool):
    solution.mkdir()
    replay = src / "solution" / "solve.py"
    if not replay.is_file():
        if draft:
            return
        raise ValueError(f"Missing desktop GUI Oracle: {replay}")
    shutil.copy(replay, solution)
    shutil.copy(COMPUTER_RUNTIME / "solution" / "computer.py", solution)
    shutil.copy(COMPUTER_RUNTIME / "solution" / "solve.sh", solution)


def style_gate(src: Path):
    result = subprocess.run([sys.executable, str(FACTORY / "pipeline" / "style_lint.py"), str(src / "instruction.md")],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"instruction style check failed:\n{result.stdout}")


MIN_SITES = 3  # project rule: every task spans at least three websites


def package(task: str, out_root: Path, skip_selfcheck: bool = False, *, computer_mcp: bool = False) -> Path:
    src = FACTORY / "tasks_src" / task
    spec = json.loads((src / "spec.json").read_text())
    manifest = snapshot_manifest(spec) if computer_mcp else None
    if len(set(spec["sites"])) < MIN_SITES:
        raise SystemExit(f"{task}: uses {len(set(spec['sites']))} sites, at least {MIN_SITES} required")
    style_gate(src)
    out = out_root / "tasks" / task
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp)
        run_world(src, build)
        rewards = {} if skip_selfcheck else selfcheck(src, build, spec)

        if out.exists():
            shutil.rmtree(out)
        env = out / "environment"
        if computer_mcp:
            cua = copy_computer_runtime(env, spec)
        else:
            copy_runtime(env)
            cua = env / "cua"
        dists = {}
        for site in spec["sites"]:
            dists[site] = build_dists.build(site)
            shutil.copytree(dists[site], cua / "sites" / site / "dist")
        shutil.copytree(build / "seed", cua / "seed")
        if (build / "triggers.json").exists():  # lever L14: reactive world
            if computer_mcp:
                raise ValueError("Reactive site triggers require a verified computer MCP desktop implementation")
            shutil.copy(build / "triggers.json", cua / "triggers.json")
        offline_assets.collect(list(dists.values()) + [build / "seed"], cua / "assets")
        config = {"sid": secrets.token_hex(3), "clock": spec["clock"], "timezone": spec["timezone"],
                  "locale": spec["locale"], "start_urls": [CATALOG[s]["home"] for s in spec["sites"]],
                  "sites": {s: {"origins": CATALOG[s]["origins"]} for s in spec["sites"]}}
        if spec.get("hide_browser_debug"):
            config["hide_browser_debug"] = True
        (cua / "config.json").write_text(json.dumps(config, indent=1))
        context = env / "desktop" if computer_mcp else env
        workspace_input = context / "workspace" / "input"
        workspace_input.mkdir(parents=True)
        if (build / "input").is_dir():
            shutil.copytree(build / "input", workspace_input, dirs_exist_ok=True)

        solution = out / "solution"
        if computer_mcp:
            if not any(path.is_file() for path in workspace_input.rglob("*")):
                (workspace_input / ".gitkeep").touch()
            (cua / "snapshot.json").write_text(json.dumps(manifest, indent=2))
            stage_computer_oracle(src, solution, skip_selfcheck)
        else:
            token = secrets.token_hex(32)
            (cua / "oracle.sha256").write_text(hashlib.sha256(token.encode()).hexdigest())
            shutil.copytree(TEMPLATE / "solution", solution)
            shutil.copytree(build / "golden", solution / "golden")
            if (build / "golden_output").is_dir():
                shutil.copytree(build / "golden_output", solution / "golden_output")
            (solution / "oracle_token").write_text(token)

        tests = out / "tests"
        if (src / "tests").is_dir():
            shutil.copytree(src / "tests", tests, ignore=shutil.ignore_patterns(
                "__pycache__", "cuaverify.py", "cuaverify_additive.py", "expected.json"))
        else:
            tests.mkdir()
        if computer_mcp:
            shutil.copytree(COMPUTER_RUNTIME / "tests", tests, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(cua / "snapshot.json", tests)
        else:
            shutil.copy(TEMPLATE / "tests" / "test.sh", tests)
        shutil.copy(TEMPLATE / "tests" / "test_verifier.py", tests)
        copy_verifier_kit(tests, additive_scoring=spec.get("additive_scoring", False))
        if (build / "expected.json").exists():
            shutil.copy(build / "expected.json", tests)
        shutil.copytree(build / "variants", tests / "fixtures")
        (tests / "fixtures" / "expectations.json").write_text(json.dumps(spec["fixture_expectations"]))

    shutil.copy(src / "instruction.md", out / "instruction.md")
    shutil.copy(src / "proposal.md", out / "proposal.md")
    shutil.copy(src / "rubric.json", out / "rubric.json")
    (out / "task.toml").write_text(task_toml(spec, computer_mcp=computer_mcp))
    (out / "verifier-checkpoints.md").write_text(checkpoints_md(json.loads((src / "rubric.json").read_text())))
    (out / "evaluation.json").write_text(json.dumps(evaluation_json(spec, rewards), ensure_ascii=False, indent=2))
    for script in (out / "solution" / "solve.sh", out / "tests" / "test.sh", cua / "entrypoint.sh"):
        if script.is_file():
            script.chmod(0o755)
    return out


def make_tar(task_dir: Path, tars: Path, *, computer_mcp: bool = False) -> Path:
    """Platform format: files at the archive root, no top-level directory, no AppleDouble files."""
    tars.mkdir(parents=True, exist_ok=True)
    suffix = "-computer-mcp" if computer_mcp else ""
    target = tars / f"{task_dir.name}{suffix}.tar.gz"

    def clean(info):
        name = Path(info.name).name
        if name.startswith("._") or name in (".DS_Store", "__pycache__"):
            return None
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    def write_archive(path):
        with tarfile.open(path, "w:gz") as tar:
            for child in sorted(task_dir.iterdir()):
                tar.add(child, arcname=child.name, filter=clean)

    if computer_mcp:
        with tempfile.TemporaryDirectory(dir=tars) as temp:
            staged = Path(temp) / target.name
            write_archive(staged)
            validate_package(staged)
            checksum = staged.with_name(staged.name + ".sha256")
            checksum.write_text(f"{package_sha256(staged)}  {target.name}\n")
            staged.replace(target)
            checksum.replace(target.with_name(checksum.name))
    else:
        write_archive(target)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="+")
    parser.add_argument("--out", type=Path, default=REPO / "output" / "harbor")
    parser.add_argument("--skip-selfcheck", action="store_true", help="draft package for UI probing (no verifier yet)")
    parser.add_argument("--runtime", choices=("legacy", "computer-mcp"), default="legacy")
    args = parser.parse_args()
    os.environ.setdefault("COPYFILE_DISABLE", "1")
    computer_mcp = args.runtime == "computer-mcp"
    for task in args.tasks:
        out = package(task, args.out, args.skip_selfcheck, computer_mcp=computer_mcp)
        print("packaged", out)
        if not args.skip_selfcheck:
            print("tar", make_tar(out, args.out / "tars", computer_mcp=computer_mcp))


if __name__ == "__main__":
    main()
