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
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
REPO = FACTORY.parent
sys.path.insert(0, str(FACTORY / "hub_tools"))
import build_dists  # noqa: E402
import offline_assets  # noqa: E402

CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
# world.py may render media (Pillow/reportlab) -> prefer the factory venv.
WORLD_PYTHON = str(FACTORY / ".venv" / "bin" / "python") if (FACTORY / ".venv" / "bin" / "python").exists() else sys.executable
TEMPLATE = FACTORY / "templates" / "harbor_task"
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


def task_toml(spec: dict) -> str:
    md = spec["metadata"]
    check_labels(md)
    keywords = ", ".join(json.dumps(k) for k in spec["keywords"])
    return f'''schema_version = "1.4"
artifacts = ["/workspace/output", "/logs/agent/browser", "/var/lib/cua/state"]

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
language = "en"

[agent]
timeout_sec = {float(spec.get("agent_timeout_sec", AGENT_TIMEOUT_SEC))}
user = "agent"

[verifier]
timeout_sec = 600.0
user = "root"

[environment]
build_timeout_sec = 1800.0
cpus = 2
memory_mb = 4096
storage_mb = 10240

[environment.healthcheck]
command = "curl -fsS http://127.0.0.1:8079/health >/dev/null && curl -fsS http://127.0.0.1:8090/__health >/dev/null"
interval_sec = 2.0
timeout_sec = 10.0
retries = 30

[[environment.mcp_servers]]
name = "browser"
transport = "stdio"
command = "/usr/local/bin/browser-mcp"
'''


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


def style_gate(src: Path):
    result = subprocess.run([sys.executable, str(FACTORY / "pipeline" / "style_lint.py"), str(src / "instruction.md")],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"instruction style check failed:\n{result.stdout}")


MIN_SITES = 3  # project rule: every task spans at least three websites


def package(task: str, out_root: Path, skip_selfcheck: bool = False) -> Path:
    src = FACTORY / "tasks_src" / task
    spec = json.loads((src / "spec.json").read_text())
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
        copy_runtime(env)
        cua = env / "cua"
        dists = {}
        for site in spec["sites"]:
            dists[site] = build_dists.build(site)
            shutil.copytree(dists[site], cua / "sites" / site / "dist")
        shutil.copytree(build / "seed", cua / "seed")
        if (build / "triggers.json").exists():  # lever L14: reactive world
            shutil.copy(build / "triggers.json", cua / "triggers.json")
        offline_assets.collect(list(dists.values()) + [build / "seed"], cua / "assets")
        config = {"sid": secrets.token_hex(3), "clock": spec["clock"], "timezone": spec["timezone"],
                  "locale": spec["locale"], "start_urls": [CATALOG[s]["home"] for s in spec["sites"]],
                  "sites": {s: {"origins": CATALOG[s]["origins"]} for s in spec["sites"]}}
        if spec.get("hide_browser_debug"):
            config["hide_browser_debug"] = True
        (cua / "config.json").write_text(json.dumps(config, indent=1))
        token = secrets.token_hex(32)
        (cua / "oracle.sha256").write_text(hashlib.sha256(token.encode()).hexdigest())
        workspace_input = env / "workspace" / "input"
        workspace_input.mkdir(parents=True)
        if (build / "input").is_dir():
            shutil.copytree(build / "input", workspace_input, dirs_exist_ok=True)

        solution = out / "solution"
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
    (out / "task.toml").write_text(task_toml(spec))
    (out / "verifier-checkpoints.md").write_text(checkpoints_md(json.loads((src / "rubric.json").read_text())))
    (out / "evaluation.json").write_text(json.dumps(evaluation_json(spec, rewards), ensure_ascii=False, indent=2))
    for script in (out / "solution" / "solve.sh", out / "tests" / "test.sh", env / "cua" / "entrypoint.sh"):
        script.chmod(0o755)
    return out


def make_tar(task_dir: Path, tars: Path) -> Path:
    """Platform format: files at the archive root, no top-level directory, no AppleDouble files."""
    tars.mkdir(parents=True, exist_ok=True)
    target = tars / f"{task_dir.name}.tar.gz"

    def clean(info):
        name = Path(info.name).name
        if name.startswith("._") or name in (".DS_Store", "__pycache__"):
            return None
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    with tarfile.open(target, "w:gz") as tar:
        for child in sorted(task_dir.iterdir()):
            tar.add(child, arcname=child.name, filter=clean)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="+")
    parser.add_argument("--out", type=Path, default=REPO / "output" / "harbor")
    parser.add_argument("--skip-selfcheck", action="store_true", help="draft package for UI probing (no verifier yet)")
    args = parser.parse_args()
    os.environ.setdefault("COPYFILE_DISABLE", "1")
    for task in args.tasks:
        out = package(task, args.out, args.skip_selfcheck)
        print("packaged", out)
        if not args.skip_selfcheck:
            print("tar", make_tar(out, args.out / "tars"))


if __name__ == "__main__":
    main()
