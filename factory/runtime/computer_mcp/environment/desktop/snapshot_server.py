"""Serve a single fixed grading snapshot over a root-only Unix socket."""

import io
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import tarfile


SOCKET = Path("/run/cua-grading/terminal-state.sock")
VAR = Path("/var/lib/cua")
OUTPUT = Path("/workspace/output")
MANIFEST = json.loads(Path("/opt/cua/snapshot.json").read_text())
LIMIT = 16 * 1024 * 1024


def add(archive, path, name, required=True):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if required:
            raise
        return
    except OSError:
        if required or not path.is_symlink():
            raise
        return
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            if required:
                raise ValueError(f"Invalid required snapshot file {name}")
            return
        member = tarfile.TarInfo(name)
        member.size = info.st_size
        member.mode = 0o600
        archive.addfile(member, stream)


def snapshot():
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        identity = json.dumps({"desktop_hostname": socket.gethostname()}).encode()
        member = tarfile.TarInfo("desktop-identity.json")
        member.size = len(identity)
        archive.addfile(member, io.BytesIO(identity))
        for site in MANIFEST["sites"]:
            for file in ("initial.json", "current.json"):
                name = f"state/{site}/{file}"
                add(archive, VAR / name, f"var/{name}")
        for file in MANIFEST["outputs"]:
            add(archive, OUTPUT / file, f"output/{file}", required=False)
        for site, names in MANIFEST["attachments"].items():
            uploads = VAR / "files" / site
            for path in sorted(uploads.glob("*/*")):
                if path.parent.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_-]+", path.parent.name):
                    continue
                original = re.sub(r"^[0-9a-f]{8}_", "", path.name)
                if path.name in names or original in names:
                    add(archive, path, f"var/files/{site}/{path.parent.name}/{path.name}", required=False)
        add(archive, Path("/var/lib/cua-mcp-audit/actions.jsonl"), "actions.jsonl", required=False)
    return out.getvalue()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        if self.rfile.readline(16) != b"snapshot\n":
            return
        payload = snapshot()
        try:
            self.wfile.write(len(payload).to_bytes(8, "big"))
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            return


os.chmod(SOCKET.parent, 0o700)
SOCKET.unlink(missing_ok=True)
os.umask(0o177)
with socketserver.UnixStreamServer(str(SOCKET), Handler) as server:
    os.chmod(SOCKET, 0o600)
    server.serve_forever()
