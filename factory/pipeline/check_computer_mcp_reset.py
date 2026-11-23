#!/usr/bin/env python3
"""Check a frozen Computer MCP archive through multiple same-container resets."""

import argparse
from base64 import b64decode
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from runpy import run_path
import secrets
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tomllib

if __package__:
    from .ap_package import package_sha256, validate_package
    from .check_computer_mcp import count_gui_steps
    from .checkpoints import check_report
else:
    from ap_package import package_sha256, validate_package
    from check_computer_mcp import count_gui_steps
    from checkpoints import check_report


MIN_GUI_STEPS = 71
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ARCHIVE_SUFFIX = "-computer-mcp.tar.gz"
RESET_RUNTIME = Path(__file__).resolve().parents[1] / "runtime/computer_mcp/reset"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CLEAR_GRADING = """
set -eu
rm -rf -- /logs/verifier/terminal-state
rm -f -- /logs/verifier/reward.txt /logs/verifier/report.json /logs/verifier/deployment.json /logs/verifier/writes.log
"""
CLEAR_AGENT_EVIDENCE = "find /logs/agent/desktop -mindepth 1 -maxdepth 1 -type f -delete"


class ResetError(RuntimeError):
    """A blocked or failed acceptance check with evidence retained."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def expect(condition, error):
    if not condition:
        raise ResetError(error)


def write_json(path, value):
    staging = path.with_name(path.name + ".tmp")
    staging.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staging.replace(path)


def input_archive(task):
    path = task.resolve(strict=True)
    if path.is_dir():
        expect(path.parent.name == "tasks", f"Expected a packaged task under <out>/tasks: {path}")
        path = path.parent.parent / "tars" / (path.name + ARCHIVE_SUFFIX)
    expect(path.is_file() and path.name.endswith(ARCHIVE_SUFFIX), f"Not a Computer MCP archive: {path}")
    return path


def freeze_archive(source, staging):
    sidecar = source.with_name(source.name + ".sha256")
    fields = sidecar.read_text(encoding="utf-8").split()
    expect(bool(fields) and SHA256_PATTERN.fullmatch(fields[0]), f"Invalid archive checksum: {sidecar}")
    if len(fields) > 1:
        expect(fields[1].lstrip("*") == source.name, f"Checksum names another archive: {sidecar}")
    frozen = staging / source.name
    with source.open("rb") as src, frozen.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    actual = package_sha256(frozen)
    expect(actual == fields[0], f"Archive SHA-256 mismatch: {source}")
    return frozen, actual


def freeze_reset_runtime(staging):
    destination = staging / "reset-runtime"
    destination.mkdir(mode=0o700)
    expect(destination.stat().st_uid != 1001, "Reset scripts must not be accessible to the desktop agent UID")
    scripts = ("supervisor.py", "reset_control.py", "site_state.py")
    for name in scripts:
        source = RESET_RUNTIME / name
        expect(source.is_file() and not source.is_symlink(), f"Missing reset runtime: {source}")
        shutil.copyfile(source, destination / name)
    return destination, scripts[0], {name: package_sha256(destination / name) for name in scripts}


def sha_tree(root):
    if not root.exists():
        return {}
    return {path.relative_to(root).as_posix(): package_sha256(path)
            for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()}


def snapshot_fingerprint(snapshot, sites, canonical_site_state):
    states = {}
    raw_current = {}
    for site in sites:
        location = snapshot / "var" / "state" / site
        initial = (location / "initial.json").read_bytes()
        current = (location / "current.json").read_bytes()
        raw_current[site] = hashlib.sha256(current).hexdigest()
        stable_current = canonical_site_state(site, initial, current)
        states[site] = {"initial_sha256": hashlib.sha256(initial).hexdigest(),
                        "current_sha256": hashlib.sha256(stable_current).hexdigest()}
    stable = {"sites": states, "outputs": sha_tree(snapshot / "output"),
              "attachments": sha_tree(snapshot / "var/files")}
    library = snapshot / "var/native/zotero.sqlite"
    if library.is_file():
        # Compare editable bibliographic records, excluding database housekeeping
        # such as WAL page layout and background sync timestamps.
        tables = (
            "SELECT itemID, itemTypeID, libraryID, key FROM items ORDER BY itemID",
            "SELECT d.itemID, d.fieldID, v.value FROM itemData d JOIN itemDataValues v USING(valueID) ORDER BY d.itemID, d.fieldID",
            "SELECT c.itemID, c.orderIndex, c.creatorTypeID, a.firstName, a.lastName, a.fieldMode FROM itemCreators c JOIN creators a USING(creatorID) ORDER BY c.itemID, c.orderIndex",
            "SELECT collectionID, collectionName, parentCollectionID, libraryID, key FROM collections ORDER BY collectionID",
            "SELECT collectionID, itemID FROM collectionItems ORDER BY collectionID, itemID",
            "SELECT itemID FROM deletedItems ORDER BY itemID",
        )
        database = sqlite3.connect(library.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            values = [database.execute(query).fetchall() for query in tables]
        finally:
            database.close()
        stable["zotero_records_sha256"] = hashlib.sha256(json.dumps(values).encode()).hexdigest()
    return stable, raw_current


class Compose:
    def __init__(self, package, runtime, supervisor, staging, evidence):
        env = package / "environment"
        self.project = "cua-reset-" + secrets.token_hex(8)
        self.evidence = evidence
        self.canonical_site_state = run_path(str(runtime / "site_state.py"))["canonical_site_state"]
        self.override = staging / "compose.reset.json"
        self.override.write_text(json.dumps({
            "services": {
                "main": {
                    "build": {"context": str(env)},
                    "entrypoint": ["/bin/sleep", "infinity"],
                    "command": [],
                },
                "desktop": {
                    "entrypoint": ["/usr/bin/python3", f"/run/cua-reset/{supervisor}"],
                    "command": ["/opt/cua/entrypoint.sh", "/usr/bin/python3", "/usr/local/lib/cua-smoke/ready.py"],
                    "volumes": [{"type": "bind", "source": str(runtime), "target": "/run/cua-reset", "read_only": True}],
                },
            },
        }, indent=2) + "\n", encoding="utf-8")
        self.command = ["docker", "compose", "--project-name", self.project,
                        "-f", str(env / "docker-compose.yaml"), "-f", str(self.override)]
        self.ids = {}
        self.identity = None
        self.started = False

    def call(self, args, log=None, *, timeout=90, docker=False, check=True):
        command = (["docker"] if docker else self.command) + list(args)
        if log is None:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            if check and result.returncode:
                detail = (result.stderr or result.stdout).decode(errors="replace").strip()
                raise ResetError(f"{' '.join(command)} exited {result.returncode}: {detail}")
            return result.stdout
        with log.open("wb") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            raise ResetError(f"{' '.join(command)} exited {result.returncode}; see {log}")
        return result.returncode

    def inspect(self):
        records = json.loads(self.call(["inspect", *self.ids.values()], docker=True))
        by_id = {record["Id"]: record for record in records}
        identity = {}
        for name, ident in self.ids.items():
            item = by_id[ident]
            state = item["State"]
            expect(state["Running"], f"{name} is no longer running")
            expect(item["RestartCount"] == 0, f"{name} has been restarted by Docker")
            identity[name] = {"id": ident, "started_at": state["StartedAt"],
                              "restart_count": item["RestartCount"], "hostname": item["Config"]["Hostname"],
                              "image_id": item["Image"]}
        expect(len({record["hostname"] for record in identity.values()}) == 2, "Expected distinct container hostnames")
        expect(by_id[self.ids["desktop"]]["State"].get("Health", {}).get("Status") == "healthy",
               "Desktop healthcheck failed")
        return identity

    def assert_identity(self):
        expect(self.inspect() == self.identity, "Container identity, start time, or restart count changed")
        for name, expected in self.ids.items():
            actual = self.call(["ps", "-q", name]).decode().strip()
            expect(actual == expected or expected.startswith(actual) and len(actual) >= 12,
                   f"Compose now points to another {name} container")
        return self.identity

    def start(self, package):
        self.call(["config", "--format", "json"], self.evidence / "compose-resolved.json")
        self.call(["build"], self.evidence / "build.log", timeout=1200)
        self.started = True
        self.call(["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "150"],
                  self.evidence / "start.log", timeout=170)
        for name in ("main", "desktop"):
            ident = self.call(["ps", "-q", name]).decode().strip()
            expect(bool(re.fullmatch(r"[0-9a-f]{12,64}", ident)), f"Expected one {name} container")
            self.ids[name] = self.call(["inspect", "--format", "{{.Id}}", ident], docker=True).decode().strip()
        self.identity = self.inspect()
        self.call(["exec", "-u", "agent", self.ids["desktop"], "/bin/sh", "-c",
                   "test ! -r /run/cua-reset/reset_control.py && test ! -x /run/cua-reset-private"],
                  self.evidence / "reset-access-probe.log", docker=True)
        for directory in ("tests", "solution"):
            self.call(["cp", str(package / directory), f"{self.ids['main']}:/{directory}"],
                      self.evidence / f"stage-{directory}.log", docker=True)
        self.main("0", "install", "-d", "-m", "0755", "-o", "agent", "-g", "agent",
                  "/logs/agent", "/logs/agent/desktop")
        return self.assert_identity()

    def main(self, user, *arguments, log=None, timeout=90):
        return self.call(["exec", "-T", "-u", user, "main", *arguments], log, timeout=timeout)

    def control(self, request, destination):
        command = ["docker", "exec", "-u", "0", self.ids["desktop"], "/usr/bin/python3",
                   "/run/cua-reset/reset_control.py", request]
        timeout = 225 if request == "reset" else 45
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            write_json(destination, {
                "error": f"control timed out after {timeout} seconds",
                "stdout": (error.stdout or b"").decode(errors="replace"),
                "stderr": (error.stderr or b"").decode(errors="replace"),
            })
            raise ResetError(f"{request} control timed out after {timeout} seconds; see {destination}") from error

        try:
            response = json.loads(result.stdout)
            if not isinstance(response, dict):
                raise ValueError("control reply must be a JSON object")
        except (ValueError, UnicodeError) as error:
            write_json(destination, {
                "error": "control did not return a JSON object",
                "exit_code": result.returncode,
                "stdout": result.stdout.decode(errors="replace"),
                "stderr": result.stderr.decode(errors="replace"),
            })
            detail = result.stderr.decode(errors="replace").strip() or str(error)
            raise ResetError(f"{request} control failed: {detail}; see {destination}") from error

        write_json(destination, response)
        if result.returncode or "error" in response:
            detail = response.get("error") or result.stderr.decode(errors="replace").strip() or "nonzero exit"
            raise ResetError(f"{request} control exited {result.returncode}: {detail}; see {destination}")
        return response

    def capture_screen(self, destination):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "computer", "arguments": {"action": "screenshot"}}}
        raw = self.call(["exec", "-u", "agent", self.ids["desktop"], "curl", "-fsS", "-m", "20",
                         "-H", "Content-Type: application/json", "--data-binary", json.dumps(payload),
                         "http://127.0.0.1:8000/mcp"], docker=True, timeout=25)
        result = json.loads(raw)["result"]
        content = result["content"]
        expect(not result.get("isError") and len(content) == 1 and content[0]["mimeType"] == "image/png",
               "Desktop screenshot did not return one PNG")
        blob = b64decode(content[0]["data"], validate=True)
        expect(blob.startswith(PNG_SIGNATURE), "Invalid desktop PNG signature")
        destination.write_bytes(blob)

    def copy_path(self, service, source, destination, log, *, required=True):
        destination.mkdir(parents=True, exist_ok=True)
        return self.call(["cp", f"{self.ids[service]}:{source}/.", str(destination)], log,
                         timeout=120, docker=True, check=required)

    def grade(self, target, checkpoint_ids, sites, expected, minimum_gui_steps, version):
        target.mkdir(parents=True)
        self.assert_identity()
        grader_error = None
        try:
            self.main("0", "bash", "/tests/test.sh", log=target / "grader.log", timeout=300)
        except (ResetError, subprocess.TimeoutExpired) as error:
            grader_error = error
        self.copy_path("main", "/logs/verifier", target / "verifier", target / "verifier-copy.log",
                       required=grader_error is None)
        if grader_error:
            raise grader_error
        verification = target / "verifier"
        check_report(verification / "report.json", checkpoint_ids, target.name)
        report = json.loads((verification / "report.json").read_text(encoding="utf-8"))
        reward = float((verification / "reward.txt").read_text(encoding="utf-8").strip())
        expect(report.get("task_version") == version, f"{target.name}: verifier ran a different task version")
        expect(report.get("status") == "valid" and report.get("reward") == reward == expected,
               f"{target.name} scored {reward}; expected {expected}: {verification}")
        deployment = json.loads((verification / "deployment.json").read_text(encoding="utf-8"))
        expect(deployment.get("agent_grading_socket_denied") is True and deployment.get("desktop_tools") == ["computer"],
               f"{target.name}: production privilege boundary was not confirmed")
        for name, identity in self.identity.items():
            expect(deployment.get(name + "_hostname") == identity["hostname"],
                   f"{target.name}: production deployment identifies a different {name} container")
        snapshot = verification / "terminal-state"
        actions = snapshot / "actions.jsonl"
        total, counts = count_gui_steps(actions) if actions.is_file() else (0, {})
        steps = sum(counts.values())
        if expected == 0:
            expect(steps == 0, f"{target.name} contains non-observation GUI input before the Oracle")
        else:
            expect(steps >= minimum_gui_steps, f"{target.name} recorded {steps} GUI steps, needs {minimum_gui_steps}")
        self.assert_identity()
        stable, raw = snapshot_fingerprint(snapshot, sites, self.canonical_site_state)
        return {"reward": reward, "gui_steps": steps, "desktop_actions": total, "gui_actions_by_type": counts,
                "snapshot": stable, "raw_current_site_sha256": raw,
                "evidence": target.relative_to(self.evidence).as_posix()}

    def stop(self):
        if self.started:
            self.call(["down", "--volumes", "--remove-orphans", "--rmi", "local", "--timeout", "12"],
                      self.evidence / "cleanup.log", timeout=65)


def valid_status(status):
    return (status.get("healthy") is True and status.get("state") == "ready" and status.get("pid1") == 1
            and isinstance(status.get("boot_uuid"), str) and bool(status["boot_uuid"])
            and type(status.get("generation")) is int
            and type(status.get("child_pid")) is int and status["child_pid"] > 1
            and bool(status.get("child_start_ticks")))


def read_manifest(services, destination):
    services.assert_identity()
    deadline = monotonic() + 125
    startup_path = destination.with_name(destination.stem + "-startup-status.json")
    status = services.control("status", startup_path)
    while not valid_status(status) and status.get("state") == "starting" and monotonic() < deadline:
        sleep(0.5)
        status = services.control("status", startup_path)
    if not valid_status(status):
        raise ResetError(f"Reset supervisor startup did not settle for {destination}")
    manifest = services.control("manifest", destination)
    expect(valid_status(manifest.get("status", {})), f"Unhealthy reset supervisor for {destination}")
    expect(isinstance(manifest.get("stable"), dict) and SHA256_PATTERN.fullmatch(manifest.get("stable_sha256", "")),
           f"Invalid supervisor manifest: {destination}")
    return manifest


def same_generation(first, later):
    keys = ("boot_uuid", "generation", "pid1", "child_pid", "child_start_ticks")
    return all(first[key] == later[key] for key in keys)


def compare_manifest_to_snapshot(manifest, grade, phase):
    captured = grade["snapshot"]["sites"]
    supervised = manifest["stable"]["sites"]
    expect(set(captured) == set(supervised), f"{phase}: supervised and graded site sets differ")
    for site, digests in captured.items():
        expect(supervised[site].get("initial_matches_archive") is True,
               f"{phase}: {site} initial state differs from the frozen archive")
        expect(all(supervised[site].get(key) == value for key, value in digests.items()),
               f"{phase}: {site} changed between graded capture and supervised manifest")


def document_reset(summary, report_path, phase):
    summary["phase"] = phase
    summary["updated_at"] = utc_now()
    write_json(report_path, summary)


def run_round(services, outcome, root, summary, path, checkpoint_ids, sites, baseline, minimum_gui_steps):
    prefix = f"round-{outcome['round']:02d}"
    root.mkdir()
    document_reset(summary, path, prefix + ":baseline")
    services.capture_screen(root / "baseline.png")
    services.main("0", "bash", "-c", CLEAR_GRADING)
    version = summary["task_version"]
    outcome["nop"] = services.grade(root / "nop", checkpoint_ids, sites, 0.0, minimum_gui_steps, version)
    start = read_manifest(services, root / "baseline-manifest.json")
    compare_manifest_to_snapshot(start, outcome["nop"], prefix + ": baseline")
    if baseline is None:
        expect(start["status"]["generation"] == 0, f"{prefix}: initial generation was already reset")
    if baseline is not None:
        expect(start["stable"] == baseline["manifest"]["stable"]
               and start["stable_sha256"] == baseline["manifest"]["stable_sha256"],
               f"{prefix}: start differs from the first baseline")
        expect(same_generation(baseline["previous_reset"]["status"], start["status"]),
               f"{prefix}: a supervisor or child changed after the last Reset")
    if baseline is None:
        baseline = {"manifest": start, "snapshot": outcome["nop"]["snapshot"]}
    expect(outcome["nop"]["snapshot"] == baseline["snapshot"], f"{prefix}: NOP snapshot drift")
    outcome["baseline"] = {"stable_sha256": start["stable_sha256"], "status": start["status"],
                           "instance": services.assert_identity()}

    document_reset(summary, path, prefix + ":oracle")
    services.main("0", "bash", "-c", CLEAR_GRADING)
    try:
        services.main("agent", "bash", "/solution/solve.sh", log=root / "oracle.log", timeout=18_000)
    finally:
        for service in ("main", "desktop"):
            services.copy_path(service, "/logs/agent/desktop", root / (service + "-oracle-screenshots"),
                               root / (service + "-screenshots-copy.log"), required=False)
    services.assert_identity()
    services.capture_screen(root / "terminal.png")
    outcome["oracle"] = services.grade(root / "oracle", checkpoint_ids, sites, 1.0, minimum_gui_steps, version)
    terminal = read_manifest(services, root / "terminal-manifest.json")
    expect(same_generation(start["status"], terminal["status"]), f"{prefix}: Oracle changed supervisor generation")
    compare_manifest_to_snapshot(terminal, outcome["oracle"], prefix + ": terminal")
    outcome["oracle"]["stable_sha256"] = terminal["stable_sha256"]
    outcome["oracle"]["instance"] = services.assert_identity()
    expect(terminal["stable_sha256"] != start["stable_sha256"], f"{prefix}: no terminal business change")
    expect(terminal["stable"]["workspace_input"] == start["stable"]["workspace_input"],
           f"{prefix}: Oracle changed protected workspace input")

    document_reset(summary, path, prefix + ":reset")
    reset = services.control("reset", root / "reset-control.json")
    services.assert_identity()
    previous = terminal["status"]
    expect(valid_status(reset) and reset["boot_uuid"] == previous["boot_uuid"] and reset["pid1"] == previous["pid1"],
           f"{prefix}: Reset failed or replaced the supervisor")
    expect(reset["generation"] == previous["generation"] + 1, f"{prefix}: Reset did not increment the generation once")
    expect((reset["child_pid"], reset["child_start_ticks"]) != (previous["child_pid"], previous["child_start_ticks"]),
           f"{prefix}: Reset did not replace the desktop child")
    services.capture_screen(root / "restored.png")
    services.main("0", "bash", "-c", CLEAR_GRADING)
    reset_grade = services.grade(root / "reset-nop", checkpoint_ids, sites, 0.0, minimum_gui_steps, version)
    restored = read_manifest(services, root / "restored-manifest.json")
    compare_manifest_to_snapshot(restored, reset_grade, prefix + ": restored")
    outcome["reset"] = {"restored": False, "stable_sha256": restored["stable_sha256"],
                        "status": restored["status"], "nop": reset_grade,
                        "instance": services.assert_identity()}
    expect(same_generation(reset, restored["status"]), f"{prefix}: restored child differs from reset result")
    expect(restored["stable"] == baseline["manifest"]["stable"]
           and restored["stable_sha256"] == baseline["manifest"]["stable_sha256"],
           f"{prefix}: stable state was not restored")
    expect(reset_grade["snapshot"] == baseline["snapshot"], f"{prefix}: restored production snapshot differs from the initial NOP")
    outcome["reset"]["restored"] = True
    services.main("0", "bash", "-c", CLEAR_AGENT_EVIDENCE)
    services.call(["logs", "--no-color", "--timestamps", "main", "desktop"], root / "compose.log")
    baseline["previous_reset"] = restored
    document_reset(summary, path, prefix + ":passed")
    print(f"{prefix}: NOP=0, Oracle=1 ({outcome['oracle']['gui_steps']} native GUI steps), Reset NOP=0", flush=True)
    return baseline


def execute(source, evidence, rounds, minimum_gui_steps):
    report_path = evidence / "reset-report.json"
    report = {"status": "running", "archive": str(source), "requested_rounds": rounds,
              "minimum_gui_steps": minimum_gui_steps, "rounds": [], "started_at": utc_now(),
              "orchestrator_sha256": package_sha256(Path(__file__).resolve())}
    document_reset(report, report_path, "archive")
    with TemporaryDirectory(prefix="cua-same-instance-") as scratch:
        staging = Path(scratch)
        services = None
        try:
            archive, digest = freeze_archive(source, staging)
            report["archive_sha256"] = digest
            package = staging / "package"
            checkpoint_ids = validate_package(archive, destination=package)
            config = tomllib.loads((package / "task.toml").read_text(encoding="utf-8"))
            rubric = json.loads((package / "rubric.json").read_text(encoding="utf-8"))
            report.update(task_id=rubric["task_id"], task_version=rubric["task_version"],
                          checkpoint_count=len(checkpoint_ids))
            expect(config["task"]["version"] == rubric["task_version"],
                   "Task config and rubric version differ")
            sites = json.loads((package / "tests/snapshot.json").read_text(encoding="utf-8"))["sites"]
            expect(sites and all(re.fullmatch(r"[a-z][a-z0-9_]*", site) for site in sites),
                   "Invalid or missing snapshot sites")
            runtime, supervisor, hashes = freeze_reset_runtime(staging)
            report["reset_runtime_sha256"] = hashes
            services = Compose(package, runtime, supervisor, staging, evidence)
            report["compose_project"] = services.project
            document_reset(report, report_path, "start")
            report["instance"] = services.start(package)
            baseline = None
            for number in range(1, rounds + 1):
                outcome = {"round": number}
                report["rounds"].append(outcome)
                baseline = run_round(services, outcome, evidence / f"round-{number:02d}", report, report_path,
                                     checkpoint_ids, sites, baseline, minimum_gui_steps)
            services.assert_identity()
            report["status"] = "passed"
            document_reset(report, report_path, "complete")
        except (Exception, KeyboardInterrupt) as error:
            report.update(status="failed", error=str(error) or type(error).__name__)
            document_reset(report, report_path, report["phase"])
            if services and services.started:
                collect_failure(services, evidence)
            raise
        finally:
            if services:
                try:
                    services.stop()
                except (ResetError, OSError, subprocess.SubprocessError) as error:
                    report["cleanup_error"] = str(error)
                    document_reset(report, report_path, report["phase"])
                    if report["status"] == "passed":
                        raise


def collect_failure(services, evidence):
    collected = {}
    actions = [("compose_logs", lambda: services.call(
        ["logs", "--no-color", "--timestamps", "main", "desktop"], evidence / "failure-compose.log",
        check=False))]
    if "desktop" in services.ids:
        actions.extend([
            ("desktop_screenshot", lambda: services.capture_screen(evidence / "failure-desktop.png")),
            ("supervisor_status", lambda: services.control("status", evidence / "failure-supervisor-status.json")),
        ])
    if "main" in services.ids:
        actions.append(("verifier_logs", lambda: services.copy_path(
            "main", "/logs/verifier", evidence / "failure-verifier", evidence / "failure-verifier-copy.log",
            required=False)))
    for name, action in actions:
        try:
            collected[name] = action()
        except (ResetError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            collected[name] = str(error)
    write_json(evidence / "failure-collection.json", collected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Packaged task directory or checksummed Computer MCP archive")
    parser.add_argument("--out", type=Path, required=True, help="Exact directory for this task's reset evidence")
    parser.add_argument("--rounds", type=int, default=2, help="Number of complete NOP/Oracle/Reset rounds")
    parser.add_argument("--min-gui-steps", type=int, default=MIN_GUI_STEPS)
    args = parser.parse_args()
    if args.rounds < 2 or args.min_gui_steps < 1:
        parser.error("Use at least 2 rounds and a positive GUI step threshold")
    try:
        evidence = args.out.resolve()
        evidence.mkdir(parents=True, exist_ok=True)
        expect(not any(evidence.iterdir()), f"Evidence directory is not empty: {evidence}")
        execute(input_archive(args.task), evidence, args.rounds, args.min_gui_steps)
    except (ResetError, OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
