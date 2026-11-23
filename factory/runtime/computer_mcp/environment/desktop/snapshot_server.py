"""Serve a single fixed grading snapshot over a root-only Unix socket."""

import errno
import io
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import subprocess
import sys
import tarfile


SOCKET = Path("/run/cua-grading/terminal-state.sock")
VAR = Path("/var/lib/cua")
OUTPUT = Path("/workspace/output")
MANIFEST = json.loads(Path("/opt/cua/snapshot.json").read_text())
LIMIT = 16 * 1024 * 1024
OPTIONAL_ARCHIVE_LIMIT = 40 * 1024 * 1024
OUTPUT_WALK_LIMIT = 1024
OUTPUT_DEPTH_LIMIT = 8
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
NATIVE_SITE_FILE = Path("/opt/native/site-id")
if NATIVE_SITE_FILE.is_file():
    sys.path.insert(0, "/opt/native/runtime")
    from projection import write_snapshot
MISSING_PATH_ERRORS = (errno.ENOENT, errno.ELOOP, errno.ENOTDIR)


def add(archive, path, name, required=True, dir_fd=None):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError as error:
        if required or error.errno not in MISSING_PATH_ERRORS:
            raise
        return
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            if required:
                raise ValueError(f"Invalid required snapshot file {name}")
            return
        if not required and archive.offset + info.st_size >= OPTIONAL_ARCHIVE_LIMIT:
            return
        member = tarfile.TarInfo(name)
        member.size = info.st_size
        member.mode = 0o600
        with os.fdopen(fd, "rb", closefd=False) as stream:
            archive.addfile(member, stream)
    finally:
        os.close(fd)


def open_directory(path, dir_fd=None):
    try:
        return os.open(path, DIRECTORY_FLAGS, dir_fd=dir_fd)
    except OSError as error:
        if error.errno not in MISSING_PATH_ERRORS:
            raise
        return None


def add_matching_outputs(archive, directory, extensions, explicit):
    remaining = OUTPUT_WALK_LIMIT

    def walk(dir_fd, parent, depth):
        nonlocal remaining
        with os.scandir(dir_fd) as entries:
            for entry in entries:
                if remaining <= 0:
                    return
                remaining -= 1
                name = entry.name
                if not name.isprintable() or "\\" in name:
                    continue
                if depth < OUTPUT_DEPTH_LIMIT and entry.is_dir(follow_symlinks=False):
                    child = open_directory(name, dir_fd)
                    if child is not None:
                        try:
                            walk(child, f"{parent}{name}/", depth + 1)
                        finally:
                            os.close(child)
                elif Path(name).suffix.lower() in extensions and (depth or name not in explicit):
                    add(archive, name, f"output/{parent}{name}", required=False, dir_fd=dir_fd)

    walk(directory, "", 0)


def add_attachments(archive, site, names, extensions):
    uploads = open_directory(VAR / "files" / site)
    if uploads is None:
        return
    remaining = OUTPUT_WALK_LIMIT if extensions else None
    try:
        with os.scandir(uploads) as sessions:
            for session in sessions:
                if remaining is not None:
                    if remaining <= 0:
                        return
                    remaining -= 1
                if not re.fullmatch(r"[A-Za-z0-9_-]+", session.name):
                    continue
                directory = open_directory(session.name, uploads)
                if directory is None:
                    continue
                try:
                    with os.scandir(directory) as files:
                        for file in files:
                            if remaining is not None:
                                if remaining <= 0:
                                    return
                                remaining -= 1
                            name = file.name
                            if not name.isprintable() or "\\" in name:
                                continue
                            original = re.sub(r"^[0-9a-f]{8}_", "", name)
                            if name in names or original in names or Path(original).suffix.lower() in extensions:
                                add(archive, name, f"var/files/{site}/{session.name}/{name}",
                                    required=False, dir_fd=directory)
                finally:
                    os.close(directory)
    finally:
        os.close(uploads)


def snapshot():
    if NATIVE_SITE_FILE.is_file():
        site = NATIVE_SITE_FILE.read_text().strip()
        if site not in MANIFEST["sites"]:
            raise ValueError("Native site and grading manifest differ")
        raw = subprocess.check_output(["php", "/opt/native/provision/project.php"], timeout=8)
        write_snapshot(VAR / "state" / site / "current.json", json.loads(raw))
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
        outputs = set(MANIFEST["outputs"])
        directory = open_directory(OUTPUT)
        if directory is not None:
            try:
                for file in sorted(outputs):
                    add(archive, file, f"output/{file}", required=False, dir_fd=directory)
                if extensions := MANIFEST.get("output_extensions"):
                    add_matching_outputs(archive, directory, set(extensions), outputs)
            finally:
                os.close(directory)
        if MANIFEST.get("zotero_library"):
            # Run the database reader with the same permissions as the desktop
            # user. SQLite backup includes committed WAL pages from a live app.
            dump = subprocess.run(
                ["/usr/sbin/runuser", "-u", "agent", "--", sys.executable, "-I",
                 str(Path(__file__).with_name("zotero_snapshot.py"))],
                stdout=subprocess.PIPE, check=True, timeout=8,
            ).stdout
            if not dump or len(dump) > LIMIT:
                raise ValueError("Invalid native library snapshot")
            member = tarfile.TarInfo("var/native/zotero.sqlite")
            member.size = len(dump)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(dump))
        attachments = MANIFEST["attachments"]
        attachment_extensions = MANIFEST.get("attachment_extensions", {})
        for site in sorted(attachments.keys() | attachment_extensions.keys()):
            add_attachments(archive, site, set(attachments.get(site, [])),
                            set(attachment_extensions.get(site, [])))
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
