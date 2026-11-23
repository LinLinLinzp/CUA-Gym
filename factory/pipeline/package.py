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
from urllib.parse import urljoin, urlsplit

if __package__:
    from .ap_package import AP_AGENT_TIMEOUT_SEC, DESKTOP_MCP_URL, package_sha256, validate_package
    from .checkpoints import COLUMNS, check_checklist, check_report, markdown_cell
    from .difficulty import check_difficulty_review
else:
    from ap_package import AP_AGENT_TIMEOUT_SEC, DESKTOP_MCP_URL, package_sha256, validate_package
    from checkpoints import COLUMNS, check_checklist, check_report, markdown_cell
    from difficulty import check_difficulty_review

FACTORY = Path(__file__).resolve().parents[1]
REPO = FACTORY.parent
sys.path.insert(0, str(FACTORY / "hub_tools"))
sys.path.insert(0, str(FACTORY / "runtime" / "sitehost"))
import build_dists  # noqa: E402
import offline_assets  # noqa: E402
from slack_live import live_targets  # noqa: E402

CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
# world.py may render media (Pillow/reportlab) -> prefer the factory venv.
WORLD_PYTHON = str(FACTORY / ".venv" / "bin" / "python") if (FACTORY / ".venv" / "bin" / "python").exists() else sys.executable
TEMPLATE = FACTORY / "templates" / "harbor_task"
COMPUTER_RUNTIME = FACTORY / "runtime" / "computer_mcp"
EXTRA_DESKTOP_PACKAGES = {
    "mousepad": "mousepad", "evince": "evince", "libreoffice_writer": "libreoffice-writer",
    "libreoffice_impress": "libreoffice-impress", "gimp": "gimp", "inkscape": "inkscape",
    "openshot": "openshot-qt", "qgis": "qgis",
    "scribus": "scribus", "audacity": "audacity", "libreoffice_draw": "libreoffice-draw",
}
DESKTOP_APPLICATIONS = {"libreoffice_calc", "drawio", "pdf4qt", "zotero"} | EXTRA_DESKTOP_PACKAGES.keys()
CLI_PACKAGES = {"ffmpeg", "gdal-bin"}
VERIFIER_PACKAGES = CLI_PACKAGES | {
    "python3-qgis", "python3-fitz", "libreoffice-calc", "audacity", "xvfb", "xauth", "xdotool",
}
VERIFIER_PYTHON_PACKAGES = {"pillow": "Pillow==11.2.1", "pymupdf": "PyMuPDF==1.26.6"}
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
    subprocess.run([WORLD_PYTHON, str(src / "world.py"), str(build)], cwd=build, check=True)


def copy_verifier_kit(tests: Path, *, additive_scoring: bool):
    kit = FACTORY / "verifier_kit"
    additive = kit / "cuaverify_additive.py"
    if additive_scoring:
        shutil.copy(additive, tests / "cuaverify.py")
    else:
        shutil.copy(additive, tests)
        shutil.copy(kit / "cuaverify.py", tests)


def selfcheck(task_dir: Path, checkpoint_ids: set[str], rubric: dict):
    """Score every staged fixture and check the reports written by its verifier."""
    staged_tests = task_dir / "tests"
    fixtures = json.loads((staged_tests / "fixtures" / "expectations.json").read_text())
    if not fixtures:
        raise ValueError("D11 needs verifier reports from at least one fixture")
    with tempfile.TemporaryDirectory() as temp:
        tests = Path(temp) / "tests"
        reports = Path(temp) / "reports"
        shutil.copytree(staged_tests, tests)
        result = subprocess.run(
            [sys.executable, str(tests / "test_verifier.py"), "--reports-dir", str(reports)],
            cwd=tests, capture_output=True, text=True,
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            raise SystemExit(f"fixture self-check failed:\n{result.stderr}")
        reports_by_name = {}
        for index, name in enumerate(fixtures):
            report = reports / f"{index}.json"
            check_report(report, checkpoint_ids, f"fixture {name}")
            reports_by_name[name] = json.loads(report.read_text(encoding="utf-8"))
        print(f"PASS D11 {len(checkpoint_ids)} checkpoints across {len(fixtures)} verifier reports")
    difficulty = check_difficulty_review(rubric, reports_by_name)
    if difficulty:
        print(f"PASS difficulty review {json.dumps(difficulty)}")
    return {name: report["reward"] for name, report in reports_by_name.items()}, difficulty


def task_toml(spec: dict, *, computer_mcp: bool = False) -> str:
    md = spec["metadata"]
    check_labels(md)
    keywords = ", ".join(json.dumps(k) for k in spec["keywords"])
    artifacts = "" if computer_mcp else '\nartifacts = ["/workspace/output", "/logs/agent/browser", "/var/lib/cua/state"]'
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
    environment = '''[environment]
build_timeout_sec = 1800.0
cpus = 2
memory_mb = 4096
storage_mb = 10240'''
    mcp_servers = f"[[environment.mcp_servers]]\n{endpoint}"
    footer = (
        f"{mcp_servers}\n\n{environment}" if computer_mcp
        else f"{environment}\n\n{healthcheck}{mcp_servers}"
    )
    desktop_apps = "\ndesktop_apps = " + json.dumps(spec["computer_mcp"]["applications"]) if computer_mcp else ""
    verifier_mode = '\nenvironment_mode = "shared"' if computer_mcp else ""
    agent_timeout = float(AP_AGENT_TIMEOUT_SEC if computer_mcp else spec.get("agent_timeout_sec", AGENT_TIMEOUT_SEC))
    return f'''schema_version = "1.4"{artifacts}

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

{footer}
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
        "| " + " | ".join(label for _, label in COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
    ]
    for cp in rubric["checkpoints"]:
        row = {**common, **cp}
        if row.get("rule") and row.get("trap"):
            row["rule"] += f"（陷阱：{row['trap']}）"
        lines.append("| " + " | ".join(markdown_cell(row.get(key)) for key, _ in COLUMNS) + " |")
    lines += ["", "## 主观检查点", "", rubric.get("subjective_note", "无主观项。") if not rubric.get("subjective") else
              "\n".join(f"- {s['id']}：{s['dimension']}" for s in rubric["subjective"])]
    if rubric.get("fixtures"):
        lines += ["", "## 正反例自测", "", "| 夹具 | 预期 |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in rubric["fixtures"].items()]
    return "\n".join(lines) + "\n"


def evaluation_json(spec: dict, rewards: dict) -> dict:
    thresholds = {"qwen": {"valid_runs": 5, "mean_at_most": 0.4}, "opus": {"valid_runs": 2, "mean_greater_than": 0.4}}
    if "qwen_raw_score_below" in spec:
        limit = spec["qwen_raw_score_below"]
        if type(limit) not in (int, float) or not 0 < limit <= 1:
            raise ValueError("qwen_raw_score_below must be a number in (0, 1]")
        thresholds = {"qwen": {"raw_score_below": limit}}
    return {
        "task_id": spec["name"], "task_version": spec["version"], "status": "not_run", "frozen": False,
        "agent": "harbor built-in claude-code",
        "thresholds": thresholds,
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
    applications = desktop["applications"]
    if len(set(applications)) != len(applications) or set(applications) - DESKTOP_APPLICATIONS:
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
    manifest = {"sites": sites, "outputs": outputs, "attachments": attachments}
    output_extensions = desktop.get("output_extensions", [])
    attachment_extensions = desktop.get("attachment_extensions", {})
    if not isinstance(attachment_extensions, dict) or set(attachment_extensions) - set(sites):
        raise ValueError("Snapshot attachment extension site is outside the task")
    for extensions in [output_extensions, *attachment_extensions.values()]:
        if not isinstance(extensions, list) or any(
                not isinstance(suffix, str) or not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix)
                for suffix in extensions):
            raise ValueError("Snapshot extensions must be lowercase suffixes including the leading dot")
    if output_extensions:
        manifest["output_extensions"] = output_extensions
    if attachment_extensions:
        manifest["attachment_extensions"] = attachment_extensions
    if desktop.get("zotero_library"):
        manifest["zotero_library"] = True
    return manifest


def copy_computer_runtime(env: Path, spec: dict):
    shutil.copytree(COMPUTER_RUNTIME / "environment", env, ignore=shutil.ignore_patterns("__pycache__"))
    cua = env / "desktop" / "cua"
    shutil.copytree(FACTORY / "runtime" / "sitehost", cua / "sitehost",
                    ignore=shutil.ignore_patterns("__pycache__"))
    applications = spec["computer_mcp"]["applications"]
    if "libreoffice_calc" in applications:
        shutil.copy(COMPUTER_RUNTIME / "registrymodifications.xcu", cua / "sources")
    desktop = spec["computer_mcp"]
    cli = desktop.get("cli", False)
    cli_packages = desktop.get("cli_packages", [])
    if (type(cli) is not bool or not isinstance(cli_packages, list)
            or any(package not in CLI_PACKAGES for package in cli_packages)
            or (cli_packages and not cli)):
        raise ValueError("Invalid task CLI configuration")
    extras = sorted({EXTRA_DESKTOP_PACKAGES[a] for a in applications if a in EXTRA_DESKTOP_PACKAGES}
                    | set(cli_packages))
    if "audacity" in applications or "openshot" in applications:
        extras += ["libasound2-plugins", "pulseaudio", "pulseaudio-utils"]
        (cua / "enable-audio").touch()
    if "scribus" in applications:
        extras.append("fonts-freefont-ttf")
    if "pdf4qt" in applications:
        extras.append("libopengl0")
    if "gimp" in applications or "zotero" in applications:
        extras.append("librsvg2-common")
    verifier_packages = desktop.get("verifier_packages", [])
    if (not isinstance(verifier_packages, list)
            or any(name not in VERIFIER_PACKAGES for name in verifier_packages)):
        raise ValueError("Unsupported verifier package")
    python_packages = desktop.get("verifier_python_packages", [])
    if (not isinstance(python_packages, list)
            or any(name not in VERIFIER_PYTHON_PACKAGES for name in python_packages)):
        raise ValueError("Unsupported verifier Python package")
    verification = set(verifier_packages)
    if desktop.get("pdf_verification", False):
        verification.add("poppler-utils")
    if verification or python_packages:
        dockerfile = env / "Dockerfile"
        source = dockerfile.read_text()
        if verification:
            packages = " ".join(sorted(verification))
            source = source.replace("ca-certificates curl git procps ",
                                    f"ca-certificates curl git procps {packages} ", 1)
        if python_packages:
            requirements = " ".join(VERIFIER_PYTHON_PACKAGES[name] for name in sorted(set(python_packages)))
            source = source.replace("pip install --no-cache-dir openpyxl==3.1.5",
                                    f"pip install --no-cache-dir openpyxl==3.1.5 {requirements}", 1)
        dockerfile.write_text(source)
    build_args = []
    if extras:
        build_args.append(f"        DESKTOP_APPS: {' '.join(extras)}")
    if "drawio" in applications:
        build_args.append('        DRAWIO_DESKTOP: "1"')
    if "pdf4qt" in applications:
        build_args.append('        PDF4QT_DESKTOP: "1"')
        # PDF4QT's OCR wizard is a transient window with a tall minimum size.
        # Keep application workspaces maximized while allowing the wizard to move.
        wm = env / "desktop" / "openbox.xml"
        wm.write_text(wm.read_text().replace('<application class="*">',
                                             '<application class="*" type="normal">', 1))
    if "zotero" in applications:
        if "libreoffice_writer" not in applications:
            raise ValueError("The Zotero citation workflow requires LibreOffice Writer")
        build_args.append('        ZOTERO_DESKTOP: "1"')
    if cli:
        build_args.append('        WORKSPACE_CLI: "1"')
    if build_args:
        compose = env / "docker-compose.yaml"
        source = compose.read_text()
        args = "\n".join(build_args)
        compose.write_text(source.replace("      context: ./desktop\n",
                                          f"      context: ./desktop\n      args:\n{args}\n", 1))
    return cua


def stage_verifier_inputs(input_dir: Path, tests: Path, desktop: dict):
    for name in desktop.get("verifier_inputs", []):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]*", name):
            raise ValueError(f"Invalid verifier input name: {name}")
        source = input_dir / name
        if source.is_symlink() or not source.exists():
            raise ValueError(f"Missing regular verifier input: {source}")
        dest = tests / "reference-input" / name
        if source.is_dir():
            if any(path.is_symlink() for path in source.rglob("*")):
                raise ValueError(f"Verifier input contains a symlink: {source}")
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, dest)


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


def start_urls(spec: dict, computer_mcp: bool):
    paths = spec["computer_mcp"].get("start_paths", {}) if computer_mcp else {}
    if paths.keys() - set(spec["sites"]):
        raise ValueError("Desktop start paths must belong to the task's existing sites")
    urls = []
    for site in spec["sites"]:
        path = paths.get(site, "")
        if path and (not path.startswith("/") or path.startswith("//")
                     or "\\" in path or urlsplit(path).netloc):
            raise ValueError(f"Desktop start path must be relative to {site}'s configured home origin")
        task_owned = computer_mcp and site in (spec["computer_mcp"].get("python_site"),
                                                spec["computer_mcp"].get("native_site"))
        home = f"https://{site}.local/" if task_owned else CATALOG[site]["home"]
        urls.append(urljoin(home, path))
    return urls


def style_gate(src: Path):
    result = subprocess.run([sys.executable, str(FACTORY / "pipeline" / "style_lint.py"), str(src / "instruction.md")],
                            cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"instruction style check failed:\n{result.stdout}")


MIN_SITES = 3  # project rule: every task spans at least three websites


def package(task: str, out_root: Path, skip_selfcheck: bool = False, *, computer_mcp: bool = False) -> Path:
    src = FACTORY / "tasks_src" / task
    spec = json.loads((src / "spec.json").read_text())
    revisions = build_dists.task_revisions(spec)
    prompts = spec.get("site_prompts", {})
    if not isinstance(prompts, dict) or prompts.keys() - set(spec["sites"]):
        raise ValueError("site_prompts must map task sites to a prompt")
    if any(value not in ("agreement", "advertisement") for value in prompts.values()):
        raise ValueError("Supported site prompts are agreement and advertisement")
    manifest = snapshot_manifest(spec) if computer_mcp else None
    desktop_smoke = computer_mcp and spec["name"].startswith("cua-smoke/") and not spec["sites"]
    workflow_scope = computer_mcp and spec["computer_mcp"].get("site_scope") == "workflow"
    python_site = spec.get("computer_mcp", {}).get("python_site")
    native_site = spec.get("computer_mcp", {}).get("native_site")
    if native_site is not None and not (workflow_scope and not python_site and
            spec["sites"] == [native_site] and native_site in {"woocommerce", "moodle"} and
            all((src / "native" / name).is_file() for name in ("install.sh", "project.php", "site.conf"))):
        raise ValueError("Native application profile requires one supported site and its install, projection and virtual host")
    if python_site is not None and not (workflow_scope and spec["sites"] == [python_site]
                                        and python_site in CATALOG and re.fullmatch("[a-z0-9-]+", python_site)
                                        and (src / "web" / "app.py").is_file()):
        raise ValueError("Task-owned browser apps require a single workflow origin and web/app.py")
    if workflow_scope and not (spec["sites"] or spec["computer_mcp"]["applications"]):
        raise ValueError("A scoped workflow needs an actual website or desktop application")
    if len(set(spec["sites"])) < MIN_SITES and not (desktop_smoke or workflow_scope):
        raise SystemExit(f"{task}: uses {len(set(spec['sites']))} sites, at least {MIN_SITES} required")
    style_gate(src)
    out = out_root / "tasks" / task
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp)
        run_world(src, build)
        triggers = build / "triggers.json"
        reactive_slack = computer_mcp and spec["computer_mcp"].get("reactive_slack", False)
        overlays = spec["computer_mcp"].get("mock_overlays", {}) if computer_mcp else {}
        if not isinstance(overlays, dict) or overlays.keys() - set(spec["sites"]):
            raise ValueError("Mock overlays must belong to the task's existing sites")
        for site, name in overlays.items():
            build_dists.overlay_patch(site, name)
        if reactive_slack:
            if not triggers.is_file():
                raise ValueError("Slack live events require a generated triggers.json")
            if overlays.get("slack") != "live-events":
                raise ValueError("Slack live events require the live-events mock overlay")
            targets = live_targets(json.loads(triggers.read_text()), spec["sites"])
            slack = json.loads((build / "seed" / "slack.json").read_text())
            if set(targets) - {row["channelId"] for row in slack["channels"]}:
                raise ValueError("Slack live events must target existing channels")
            seed_ids = {row.get("messageId") for rows in slack["messages"].values() for row in rows}
            if seed_ids.intersection(set().union(*targets.values())):
                raise ValueError("Slack live event IDs must be new messages")
        elif computer_mcp and triggers.exists():
            raise ValueError("Computer MCP triggers require the opt-in reactive_slack profile")

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
            if site in (python_site, native_site):
                if python_site:
                    shutil.copytree(src / "web", cua / "sites" / site / "app",
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                shutil.copytree(COMPUTER_RUNTIME / "fonts", env / "desktop" / "task-fonts")
                dockerfile = env / "desktop" / "Dockerfile"
                with dockerfile.open("a") as desktop_build:
                    desktop_build.write("\nCOPY task-fonts/ /usr/local/share/fonts/cua/\nRUN fc-cache -f\n")
                if native_site:
                    native = env / "desktop" / "native"
                    policy_file = cua / "sources" / "chromium-policy.json"
                    policy = json.loads(policy_file.read_text())
                    policy["TranslateEnabled"] = False
                    policy_file.write_text(json.dumps(policy, indent=2) + "\n")
                    shutil.copytree(COMPUTER_RUNTIME / "native", native / "runtime",
                                    ignore=shutil.ignore_patterns("__pycache__"))
                    shutil.copytree(src / "native", native / "provision",
                                    ignore=shutil.ignore_patterns("__pycache__", ".git"))
                    (native / "site-id").write_text(site + "\n")
                    packages = (native / "runtime" / "packages.Dockerfile").read_text()
                    recipe = dockerfile.read_text().replace("COPY cua/ /opt/cua/", packages + "\nCOPY cua/ /opt/cua/", 1)
                    dockerfile.write_text(recipe + "\nCOPY native/ /opt/native/\nRUN bash /opt/native/runtime/install.sh\n")
                continue
            dists[site] = build_dists.build(site, overlay=overlays.get(site), revision=revisions.get(site))
            shutil.copytree(dists[site], cua / "sites" / site / "dist")
            if site in prompts:
                dist = cua / "sites" / site / "dist"
                index = dist / "index.html"
                html = index.read_text()
                asset = dist / "cua-site-prompt.js"
                if asset.exists() or "</body>" not in html:
                    raise ValueError(f"{site}: cannot install optional page prompt")
                shutil.copyfile(FACTORY / "templates" / "site-prompt.js", asset)
                tag = f'<script defer src="/cua-site-prompt.js" data-prompt="{prompts[site]}"></script>'
                index.write_text(html.replace("</body>", tag + "</body>", 1))
        if spec["sites"]:
            shutil.copytree(build / "seed", cua / "seed")
        if triggers.exists():
            shutil.copy(triggers, cua / "triggers.json")
        if spec["sites"]:
            offline_assets.collect(list(dists.values()) + [build / "seed"], cua / "assets")
            config = {"sid": secrets.token_hex(3), "clock": spec["clock"], "timezone": spec["timezone"],
                      "locale": spec["locale"], "start_urls": start_urls(spec, computer_mcp),
                      "sites": {s: {"origins": CATALOG[s]["origins"]} for s in spec["sites"]}}
            if spec.get("hide_browser_debug"):
                config["hide_browser_debug"] = True
            if python_site:
                config["python_site"] = python_site
                config["sites"][python_site]["origins"] = [f"https://{python_site}.local"]
            if native_site:
                config["native_site"] = native_site
                config["sites"][native_site]["origins"] = [f"https://{native_site}.local"]
            if reactive_slack:
                config["reactive_slack"] = True
            if overlays.get("visa_portal_ds160") == "signed-review":
                config["sites"]["visa_portal_ds160"]["signed_submissions"] = True
            if overlays.get("docusign") == "sent-envelope-history":
                config["sites"]["docusign"]["issued_envelopes"] = True
            if computer_mcp and spec["computer_mcp"].get("artwork_review"):
                if not {"asana", "pinterest", "wordpress_com"}.issubset(spec["sites"]):
                    raise ValueError("Artwork review requires Asana and both publication sites")
                config["sites"]["asana"]["artwork_review"] = True
            (cua / "config.json").write_text(json.dumps(config, indent=1))
        else:
            (cua / "web-entrypoint.sh").unlink()
        context = env / "desktop" if computer_mcp else env
        workspace_input = context / "workspace" / "input"
        workspace_input.mkdir(parents=True)
        if (build / "input").is_dir():
            shutil.copytree(build / "input", workspace_input, dirs_exist_ok=True)
        browser_inputs = spec.get("computer_mcp", {}).get("browser_readable_inputs", [])
        if computer_mcp and browser_inputs:
            urls = []
            for name in browser_inputs:
                if (not re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.(txt|html)", name)
                        or not (workspace_input / name).is_file()):
                    raise ValueError(f"Expected a public input document: {name!r}")
                urls.append("file:///workspace/input/" + name)
            policy_path = cua / "sources" / "chromium-policy.json"
            policy = json.loads(policy_path.read_text())
            policy["URLAllowlist"] = urls
            policy_path.write_text(json.dumps(policy, indent=2) + "\n")
        if computer_mcp and spec["computer_mcp"].get("zotero_library"):
            seed_name = spec["computer_mcp"]["zotero_library"]
            if ("zotero" not in spec["computer_mcp"]["applications"]
                    or not isinstance(seed_name, str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+\.sqlite", seed_name)
                    or not (workspace_input / seed_name).is_file()):
                raise ValueError("Zotero requires a regular workspace input library")
            (cua / "zotero-library-name").write_text(seed_name)

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
            stage_verifier_inputs(workspace_input, tests, spec["computer_mcp"])
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
    (out / "evaluation.json").write_text(json.dumps(evaluation_json(spec, {}), ensure_ascii=False, indent=2))
    for script in (out / "solution" / "solve.sh", out / "tests" / "test.sh", cua / "entrypoint.sh"):
        if script.is_file():
            script.chmod(0o755)
    return out


def make_tar(task_dir: Path, tars: Path, *, computer_mcp: bool = False,
             require_difficulty_review: bool = False) -> Path:
    """Platform format: files at the archive root, no top-level directory, no AppleDouble files."""
    task_dir, tars = task_dir.resolve(), tars.resolve()
    rubric = json.loads((task_dir / "rubric.json").read_text(encoding="utf-8"))
    if require_difficulty_review and rubric.get("difficulty_review") is None:
        raise ValueError(f"Missing difficulty_review in {task_dir / 'rubric.json'}")
    checkpoint_ids = check_checklist((task_dir / "verifier-checkpoints.md").read_text(encoding="utf-8"), rubric)
    rewards, difficulty = selfcheck(task_dir, checkpoint_ids, rubric)
    evaluation_path = task_dir / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation["fixture_selfcheck"] = rewards
    if difficulty:
        evaluation["difficulty_review"] = difficulty
    evaluation_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")

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
    parser.add_argument("--require-difficulty-review", action="store_true",
                        help="require audited simple points, weak paths and business constraints")
    args = parser.parse_args()
    if args.skip_selfcheck and args.require_difficulty_review:
        parser.error("--require-difficulty-review needs verifier self-checks")
    args.out = args.out.resolve()
    os.environ.setdefault("COPYFILE_DISABLE", "1")
    computer_mcp = args.runtime == "computer-mcp"
    for task in args.tasks:
        out = package(task, args.out, args.skip_selfcheck, computer_mcp=computer_mcp)
        if args.skip_selfcheck:
            print("draft", out)
        else:
            print("tar", make_tar(out, args.out / "tars", computer_mcp=computer_mcp,
                                  require_difficulty_review=args.require_difficulty_review))


if __name__ == "__main__":
    main()
