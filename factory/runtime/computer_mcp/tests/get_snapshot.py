"""Fetch and validate the desktop state after the Harbor agent exits."""

import io
import json
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tarfile
from urllib.request import Request, urlopen


LOGS = Path("/logs/verifier")
SOCKET = "/run/cua-grading/terminal-state.sock"
MAX_SNAPSHOT = 48 * 1024 * 1024
MANIFEST = json.loads(Path(__file__).with_name("snapshot.json").read_text())


def fetch():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(20)
        connection.connect(SOCKET)
        connection.sendall(b"snapshot\n")
        with connection.makefile("rb") as stream:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("Desktop snapshot length header is incomplete")
            size = int.from_bytes(header, "big")
            if not 0 < size <= MAX_SNAPSHOT:
                raise ValueError("Invalid desktop snapshot size")
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("Incomplete desktop snapshot")
    output = LOGS / "terminal-state"
    output.mkdir(mode=0o700, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        archive.extractall(output, filter="data")
    for site in MANIFEST["sites"]:
        for name in ("initial", "current"):
            with (output / "var/state" / site / f"{name}.json").open() as stream:
                json.load(stream)
    return output


def confirm_boundary(output):
    desktop = json.loads((output / "desktop-identity.json").read_text())["desktop_hostname"]
    main = socket.gethostname()
    if desktop == main:
        raise ValueError("The desktop and verifier report the same container hostname")
    mode = Path(SOCKET).stat()
    if not stat.S_ISSOCK(mode.st_mode) or mode.st_uid != 0 or stat.S_IMODE(mode.st_mode) != 0o600:
        raise ValueError("The desktop grading socket must be root-owned with mode 0600")
    agent = pwd.getpwnam("agent")
    permission_probe = """
import socket, sys
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(sys.argv[1])
except PermissionError:
    sys.exit(0)
sys.exit(1)
"""
    subprocess.run([sys.executable, "-c", permission_probe, SOCKET], check=True,
                   user=agent.pw_uid, group=agent.pw_gid, extra_groups=[])
    request = Request("http://desktop:8000/mcp",
                      data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=5) as response:
        tools = [tool["name"] for tool in json.load(response)["result"]["tools"]]
    if tools != ["computer"]:
        raise ValueError("Expected exactly one desktop MCP tool")
    (LOGS / "deployment.json").write_text(json.dumps({
        "main_hostname": main, "desktop_hostname": desktop, "desktop_tools": tools,
        "agent_uid": agent.pw_uid, "agent_grading_socket_denied": True,
        "grading_transport": "root-only Unix socket",
    }, indent=2) + "\n")


try:
    confirm_boundary(fetch())
except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
    (LOGS / "report.json").write_text(json.dumps({"status": "infra_error", "detail": str(error)}) + "\n")
    raise SystemExit(f"Desktop state collection failed: {error}")
