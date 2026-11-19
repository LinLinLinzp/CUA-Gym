"""Validate and extract the computer MCP task as AP's files-only packer sees it."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import tarfile


AP_AGENT_TIMEOUT_SEC = 5 * 60 * 60
DESKTOP_MCP_URL = "http://desktop:8000/mcp"


def check_task_config(text):
    import tomllib

    config = tomllib.loads(text)
    sections = [line.strip() for line in text.splitlines() if line.lstrip().startswith("[")]
    if sections[-2:] != ["[[environment.mcp_servers]]", "[environment]"]:
        raise ValueError("End task.toml with [[environment.mcp_servers]], then [environment] for AP")
    if config["environment"].get("mcp_servers") != [
        {"name": "desktop", "transport": "streamable-http", "url": DESKTOP_MCP_URL}
    ]:
        raise ValueError("Use exactly one desktop MCP endpoint")
    agent = config["agent"]
    if agent.get("timeout_sec") != AP_AGENT_TIMEOUT_SEC or agent.get("user") != "agent":
        raise ValueError("AP expects the agent user and a five-hour agent timeout")
    verifier = config["verifier"]
    if (verifier.get("user") != "root" or verifier.get("environment_mode") != "shared"
            or "collect" in verifier):
        raise ValueError("AP Harbor 0.1.45 expects a shared root verifier with socket-based collection")


def file_members(bundle):
    files = {}
    for member in bundle:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError(f"Invalid AP archive member: {member.name}")
        if member.isfile():
            name = path.as_posix()
            if name in files:
                raise ValueError(f"Duplicate AP archive file: {name}")
            files[name] = member
    return files


def check_archive(bundle, files):
    required = {
        "task.toml", "instruction.md", "environment/docker-compose.yaml",
        "environment/Dockerfile", "environment/desktop/Dockerfile", "environment/mcp.json",
        "tests/test.sh", "tests/get_snapshot.py", "tests/verifier.py",
        "tests/snapshot.json", "environment/desktop/cua/snapshot.json",
        "solution/solve.sh", "solution/solve.py",
    }
    missing = required.difference(files)
    if missing:
        raise ValueError(f"AP file-only package is missing: {', '.join(sorted(missing))}")

    check_task_config(bundle.extractfile(files["task.toml"]).read().decode())
    launcher = json.load(bundle.extractfile(files["environment/mcp.json"]))
    if launcher.get("mcpServers") != {
        "desktop": {"type": "http", "url": DESKTOP_MCP_URL, "alwaysLoad": True}
    }:
        raise ValueError("Claude Code must load the same single desktop MCP endpoint as task.toml")
    desktop_manifest = bundle.extractfile(files["environment/desktop/cua/snapshot.json"]).read()
    if desktop_manifest != bundle.extractfile(files["tests/snapshot.json"]).read():
        raise ValueError("Desktop and verifier have different snapshot manifests")

    for context in ("environment/", "environment/desktop/"):
        recipe = bundle.extractfile(files[context + "Dockerfile"]).read().decode()
        for line in recipe.splitlines():
            if not line.startswith("COPY "):
                continue
            fields = shlex.split(line)
            for source in (field for field in fields[1:-1] if not field.startswith("--")):
                prefix = context + source
                if prefix not in files and not any(name.startswith(prefix.rstrip("/") + "/") for name in files):
                    raise ValueError(f"AP file-only repack loses Docker COPY source {prefix}")


def validate_package(path: Path, *, destination: Path | None = None):
    with tarfile.open(path) as bundle:
        files = file_members(bundle)
        check_archive(bundle, files)
        if destination is not None:
            bundle.extractall(destination, members=files.values(), filter="data")


def package_sha256(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
