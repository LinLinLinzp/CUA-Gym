#!/usr/bin/env python3
"""Keep the desktop container alive while restoring its own pristine task instance."""

import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

from site_state import canonical_site_state

PRIVATE = Path("/run/cua-reset-private")
CONTROL = PRIVATE / "control.sock"
BASELINE = PRIVATE / "pristine.tar"
ARCHIVE_ROOT = Path("/opt/cua")
WORKSPACE = Path("/workspace")
STATE = Path("/var/lib/cua")
HOME = Path("/home/agent")
CLI_HOME = Path("/home/workspace-cli")
AUDIT = Path("/var/lib/cua-mcp-audit")
GRADING_SOCKET = Path("/run/cua-grading/terminal-state.sock")
PYTHON = "/usr/bin/python3"
READY = "/usr/local/lib/cua-smoke/ready.py"
ARCHIVE_START = ("/opt/cua/entrypoint.sh", PYTHON, READY)
RESTORED = (
    WORKSPACE, STATE, HOME, CLI_HOME, AUDIT, Path("/logs/agent"),
    Path("/run/cua-desktop"), Path("/run/user"), Path("/tmp"), Path("/var/tmp"), Path("/dev/shm"),
)
HEALTH_WINDOW = 120
STARTUP_RETRIES = 1
PROFILE_SETTLE_SECONDS = 0.35
X11_STARTUP_RACE = re.compile(
    rb"X Error of failed request:[^\n]*\bBadWindow\b[^\n]*\n[^\n]*\(X_QueryTree\)"
)
MAX_PROFILE_BYTES = 8 * 1024 * 1024
PROFILE_ROOT = HOME / ".cua-chromium"


class ResetError(RuntimeError):
    """Trusted runtime setup or reset could not complete."""


def json_bytes(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def present(path):
    return os.path.lexists(path)


def remove_entry(path):
    if not present(path):
        return
    if path.is_mount():
        for child in path.iterdir():
            remove_entry(child)
        return
    if stat.S_ISDIR(path.lstat().st_mode):
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ResetError("safe directory removal unavailable")
        shutil.rmtree(path)
    else:
        path.unlink()


def pristine_capture():
    if (STATE / ".booted").exists():
        raise ResetError("desktop baseline must be captured before the original entrypoint")
    baseline_paths = [str(path).lstrip("/") for path in RESTORED if present(path)]
    options = ("--numeric-owner", "--xattrs", "--acls")
    subprocess.run(
        ["tar", "--create", "--format=pax", "--file", str(BASELINE), *options,
         "--directory", "/", "--", *baseline_paths],
        check=True,
    )
    BASELINE.chmod(0o600)


def pristine_restore():
    for path in RESTORED:
        remove_entry(path)
    GRADING_SOCKET.unlink(missing_ok=True)
    subprocess.run(
        ["tar", "--extract", "--file", str(BASELINE), "--directory", "/",
         "--numeric-owner", "--same-owner", "--same-permissions", "--xattrs", "--acls"],
        check=True,
    )


def process_index():
    """Read PID, parent, process group, start tick, state and real uid in this namespace."""
    processes = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            contents = (path / "stat").read_text()
            values = contents.rsplit(")", 1)[1].split()
            metadata = (path / "status").read_text()
            uid = int(next(line for line in metadata.splitlines() if line.startswith("Uid:")).split()[1])
            processes[int(path.name)] = (
                int(values[1]), int(values[2]), int(values[19]), values[0], uid,
            )
        except (OSError, ValueError, IndexError, StopIteration):
            continue
    return processes


def tree(path):
    """Hash directory entries, bytes, ownership and permissions without following links."""
    result = {"present": present(path), "entries": 0, "bytes": 0, "sha256": None}
    if not result["present"]:
        return result
    digest = hashlib.sha256()

    def include(parent, filename, relative):
        info = os.stat(filename, dir_fd=parent, follow_symlinks=False)
        mode = info.st_mode
        row = [relative, mode, info.st_uid, info.st_gid]
        result["entries"] += 1
        if stat.S_ISLNK(mode):
            row.append(os.readlink(filename, dir_fd=parent))
        if stat.S_ISREG(mode):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(filename, flags, dir_fd=parent), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ResetError("tree changed while being inspected")
                file_digest = hashlib.sha256()
                while data := stream.read(1024 * 1024):
                    file_digest.update(data)
                    result["bytes"] += len(data)
                row.append(file_digest.hexdigest())
        digest.update(json_bytes(row) + b"\n")
        if stat.S_ISDIR(mode):
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
            fd = os.open(filename, flags, dir_fd=parent)
            try:
                contents = os.fstat(fd)
                if (contents.st_dev, contents.st_ino) != (info.st_dev, info.st_ino):
                    raise ResetError("tree changed while being inspected")
                for name in sorted(os.listdir(fd)):
                    child = f"{relative}/{name}" if relative != "." else name
                    include(fd, name, child)
            finally:
                os.close(fd)

    include(None, str(path), ".")
    result["sha256"] = digest.hexdigest()
    return result


def read_regular(path, limit=MAX_PROFILE_BYTES):
    """Read a selected regular file beneath root-owned ancestry, rejecting symlinks."""
    if not path.is_absolute():
        raise ValueError("expected absolute selection")
    root = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            os.close(root)
            root = child
        with os.fdopen(os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root),
                       "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                return None
            payload = stream.read(limit + 1)
            return payload if len(payload) <= limit else None
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return None
    except OSError as exc:
        if exc.errno == 40:  # ELOOP from O_NOFOLLOW.
            return None
        raise
    finally:
        os.close(root)


def restored_root_digests():
    return {str(path): tree(path) for path in RESTORED}


def selected_hash(path, limit=MAX_PROFILE_BYTES):
    contents = read_regular(path, limit)
    return sha(contents) if contents is not None else None


def as_json(contents):
    try:
        value = json.loads(contents or b"{}")
    except (UnicodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def site_manifest(config):
    sid = config.get("sid", "")
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]*", sid):
        raise ResetError("invalid archive site session")
    rows = {}
    raw_hashes = {}
    for seed in sorted((ARCHIVE_ROOT / "seed").glob("*.json")):
        name = seed.stem
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ResetError("invalid archive site key")
        raw_seed = read_regular(seed, 16 * 1024 * 1024)
        if raw_seed is None:
            raise ResetError("archive site seed is missing")
        initial = read_regular(STATE / "state" / name / "initial.json", 16 * 1024 * 1024)
        current = read_regular(STATE / "state" / name / "current.json", 16 * 1024 * 1024)
        expected = raw_seed.replace(b"__SID__", sid.encode())
        stable_current = canonical_site_state(name, expected, current)
        raw_hashes[name] = sha(current) if current is not None else None
        state = as_json(current)
        # Hash visible identity fields without returning email, profile data or auth values.
        identity_keys = ("account", "user", "currentUser", "currentUserId", "current_user", "sessionUserId")
        actor = {key: state[key] for key in identity_keys if key in state}
        rows[name] = {
            "archive_seed_sha256": sha(expected),
            "initial_sha256": sha(initial) if initial is not None else None,
            "current_sha256": sha(stable_current) if stable_current is not None else None,
            "initial_matches_archive": initial == expected,
            "current_matches_initial": current is not None and current == initial,
            "active_account_sha256": sha(json_bytes(actor)) if actor else None,
        }
    return rows, raw_hashes


def chromium_profile():
    prefs = as_json(read_regular(PROFILE_ROOT / "Default" / "Preferences"))
    local = as_json(read_regular(PROFILE_ROOT / "Local State"))
    profile = prefs.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    sign_in = prefs.get("signin")
    sign_in = sign_in if isinstance(sign_in, dict) else {}
    session = prefs.get("session")
    session = session if isinstance(session, dict) else {}
    content = profile.get("content_settings")
    content = content if isinstance(content, dict) else {}
    local_profile = local.get("profile")
    local_profile = local_profile if isinstance(local_profile, dict) else {}
    # Chrome timestamps, UMA, client IDs, sessions and DB journals are intentionally
    # omitted. Hash values instead of emitting cookies, accounts or startup URLs.
    chromium = {
        "profile_name": profile.get("name"),
        "profile_accounts": prefs.get("account_info", []),
        "signin_allowed": sign_in.get("allowed"),
        "startup_mode": session.get("restore_on_startup"),
        "startup_urls": session.get("startup_urls", []),
        "last_used_profile": local_profile.get("last_used", "Default"),
        "content_defaults": profile.get("default_content_setting_values", {}),
        "content_exceptions": content.get("exceptions", {}),
    }
    info_cache = local_profile.get("info_cache")
    default_profile = info_cache.get("Default") if isinstance(info_cache, dict) else None
    initialized = bool(prefs and local and (
        profile.get("name")
        or isinstance(default_profile, dict) and default_profile
        or local_profile.get("last_used") == "Default" and profile
    ))
    return chromium, bool(prefs), bool(local), initialized


def comparable_chromium_profile(chromium):
    """Exclude only startup-generated engagement timestamps, preserving decisions."""
    exceptions = chromium.get("content_exceptions")
    engagement = exceptions.get("site_engagement") if isinstance(exceptions, dict) else None
    if not isinstance(engagement, dict):
        return chromium
    normalized = {}
    for origin, rule in engagement.items():
        if not isinstance(rule, dict):
            normalized[origin] = rule
            continue
        normalized_rule = dict(rule)
        modified = rule.get("last_modified")
        if isinstance(modified, str) and modified.isdecimal():
            normalized_rule.pop("last_modified")
        setting = rule.get("setting")
        if isinstance(setting, dict) and type(setting.get("lastEngagementTime")) in (int, float):
            normalized_rule["setting"] = {
                key: value for key, value in setting.items() if key != "lastEngagementTime"
            }
        normalized[origin] = normalized_rule
    stable_exceptions = {**exceptions, "site_engagement": normalized}
    return {**chromium, "content_exceptions": stable_exceptions}


def profile_manifest(config):
    chromium, prefs_present, local_present, _ = chromium_profile()
    return {
        "archive_browser_policy_sha256": selected_hash(Path("/etc/chromium/policies/managed/cua.json")),
        "archive_start_urls_sha256": sha(json_bytes(config.get("start_urls", []))),
        "archive_timezone_sha256": sha(json_bytes(config.get("timezone"))),
        "browser_preferences_present": prefs_present,
        "browser_local_state_present": local_present,
        "browser_identity_settings_sha256": sha(json_bytes(comparable_chromium_profile(chromium))),
        "agent_defaults": {
            name: selected_hash(HOME / name)
            for name in (".profile", ".bashrc", ".config/mimeapps.list", ".local/share/applications/mimeapps.list")
        },
        "cli_home": {
            "present": present(CLI_HOME),
            "profile_sha256": selected_hash(CLI_HOME / ".profile"),
            "shell_rc_sha256": selected_hash(CLI_HOME / ".bashrc"),
        },
        "native_app_configuration": {
            "openbox_config_sha256": selected_hash(Path("/usr/local/lib/cua-smoke/openbox.xml")),
            "libreoffice_seed_sha256": selected_hash(ARCHIVE_ROOT / "sources" / "registrymodifications.xcu"),
            "libreoffice_profile_present": present(HOME / ".config" / "cua-libreoffice" / "user"),
        },
    }


def volatile_profile():
    rows = {}
    for label, path in (
        ("local_storage", PROFILE_ROOT / "Default" / "Local Storage"),
        ("session_storage", PROFILE_ROOT / "Default" / "Session Storage"),
        ("indexed_db", PROFILE_ROOT / "Default" / "IndexedDB"),
        ("cookie_db", PROFILE_ROOT / "Default" / "Cookies"),
        ("libreoffice_profile", HOME / ".config" / "cua-libreoffice"),
        ("gui_audit", AUDIT),
    ):
        try:
            rows[label] = tree(path)
        except (OSError, ResetError):
            rows[label] = {"present": present(path), "changing": True}
    return rows


class Supervisor:
    def __init__(self, command, baseline):
        self.boot_uuid = str(uuid.uuid4())
        self.generation = 0
        self.command = command
        self.baseline = baseline
        self.terminated = False
        self.child = None
        self.child_start_ticks = None
        self.boot_target = 0
        self.startup_attempt = 0
        self.startup_deadline = None
        self.startup_failure = None
        self.attempt_ready = False
        self.profile_observation = None
        self.launch_sequence = 0
        self.child_log = None
        self.child_log_offset = 0
        self.state = "starting"
        self.service_uids = set()
        users = ["agent", "desktop-driver", "workspace-cli"]
        if Path("/opt/native/site-id").is_file():
            users.extend(["mysql", "www-data"])
        for name in users:
            try:
                self.service_uids.add(pwd.getpwnam(name).pw_uid)
            except KeyError:
                continue

    def start_boot(self, generation):
        self.boot_target = generation
        self.startup_attempt = 0
        self.startup_deadline = time.monotonic() + HEALTH_WINDOW
        self.startup_failure = None
        self.launch()

    def launch(self):
        self.state = "starting"
        self.attempt_ready = False
        self.profile_observation = None
        self.startup_attempt += 1
        self.launch_sequence += 1
        self.child_log = PRIVATE / f"archive-start-{self.launch_sequence:04d}.log"
        self.child_log_offset = 0
        fd = os.open(self.child_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        with os.fdopen(fd, "wb") as log:
            self.child = subprocess.Popen(self.command, cwd=WORKSPACE, start_new_session=True,
                                          stdout=log, stderr=subprocess.STDOUT)
        self.child_start_ticks = process_index().get(self.child.pid, (0, 0, None))[2]

    def mirror_diagnostics(self):
        if self.child_log is None:
            return
        with self.child_log.open("rb") as log:
            log.seek(self.child_log_offset)
            data = log.read(128 * 1024)
        if data:
            self.child_log_offset += len(data)
            sys.stderr.buffer.write(data)
            sys.stderr.buffer.flush()

    def known_early_exit(self):
        if self.child_log is None:
            return False
        with self.child_log.open("rb") as log:
            log.seek(max(0, self.child_log.stat().st_size - 64 * 1024))
            return X11_STARTUP_RACE.search(log.read()) is not None

    def restore(self):
        self.stop_desktop()
        self.mirror_diagnostics()
        pristine_restore()
        if restored_root_digests() != self.baseline:
            raise ResetError("pristine trees differ from the pre-boot baseline")

    def advance_startup(self):
        self.mirror_diagnostics()
        if self.state not in ("starting", "ready") or self.child is None:
            return
        code = self.child.poll()
        if code is not None:
            retryable = not self.attempt_ready and self.known_early_exit()
            can_retry = (retryable and self.startup_attempt <= STARTUP_RETRIES
                         and not self.terminated and time.monotonic() < self.startup_deadline)
            reason = "xdotool BadWindow (X_QueryTree)" if retryable else "archive child exited"
            self.startup_failure = {"reason": reason, "exit_code": code, "attempt": self.startup_attempt}
            if can_retry:
                print(f"Desktop startup attempt {self.startup_attempt} failed before readiness: {reason}. "
                      f"Restoring and retrying generation {self.boot_target}.", file=sys.stderr, flush=True)
                try:
                    self.restore()
                    self.launch()
                    return
                except (OSError, ResetError, subprocess.SubprocessError) as exc:
                    self.startup_failure["retry_error"] = str(exc) if isinstance(exc, ResetError) else type(exc).__name__
            self.state = "failed"
        elif not self.attempt_ready and time.monotonic() >= self.startup_deadline:
            self.startup_failure = {"reason": "archive startup timed out", "attempt": self.startup_attempt}
            self.state = "failed"

    def check(self):
        if self.child is None or self.child.poll() is not None:
            return False
        try:
            probe = subprocess.run([PYTHON, READY, "--check"], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return probe.returncode == 0 and self.child.poll() is None

    def profile_ready(self):
        projection, _, _, initialized = chromium_profile()
        if not initialized:
            self.profile_observation = None
            return False
        digest = sha(json_bytes(comparable_chromium_profile(projection)))
        observed_at = time.monotonic()
        if self.profile_observation is None or self.profile_observation[0] != digest:
            self.profile_observation = (digest, observed_at)
            return False
        return observed_at - self.profile_observation[1] >= PROFILE_SETTLE_SECONDS

    def status(self):
        self.advance_startup()
        healthy = (self.state in ("starting", "ready") and self.check()
                   and (self.attempt_ready or self.profile_ready()))
        if healthy:
            self.state = "ready"
            self.attempt_ready = True
            self.generation = self.boot_target
        elif self.state == "ready":
            self.state = "starting"
        return {"boot_uuid": self.boot_uuid, "generation": self.generation, "pid1": os.getpid(),
                "child_pid": self.child.pid if self.child is not None else None,
                "child_start_ticks": self.child_start_ticks, "healthy": healthy, "state": self.state,
                "target_generation": self.boot_target, "startup_attempt": self.startup_attempt,
                "startup_failure": self.startup_failure}

    def owned(self):
        processes = process_index()
        root = self.child.pid if self.child else None
        targets = {pid for pid, (_, group, _, state, uid) in processes.items()
                   if pid != os.getpid() and state != "Z" and (group == root or uid in self.service_uids)}
        if root is not None and root in processes:
            descendants = {root}
            while True:
                expanded = descendants | {pid for pid, row in processes.items() if row[0] in descendants}
                if expanded == descendants:
                    break
                descendants = expanded
            targets |= {pid for pid in descendants if processes[pid][3] != "Z"}
        return {pid: processes[pid][2] for pid in targets}

    @staticmethod
    def signal_owned(targets, sig):
        # Verify start ticks at signal time to avoid targeting a reused PID.
        current = process_index()
        for pid, ticks in targets.items():
            if pid in current and current[pid][2] == ticks:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass

    def reap(self):
        if self.child is not None:
            self.child.poll()
        direct_child = self.child.pid if self.child else None
        for pid, (parent, _, _, state, _) in process_index().items():
            if parent == os.getpid() and state == "Z" and pid != direct_child:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def stop_desktop(self):
        for sig, seconds in ((signal.SIGTERM, 4), (signal.SIGKILL, 5)):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                self.reap()
                targets = self.owned()
                if not targets:
                    self.child = None
                    return
                self.signal_owned(targets, sig)
                time.sleep(0.15)
        if self.owned():
            raise ResetError("desktop processes did not stop before restoration")
        self.child = None

    def reset(self):
        self.state = "resetting"
        self.restore()
        self.start_boot(self.generation + 1)
        while not self.terminated:
            self.reap()
            status = self.status()
            if status["healthy"]:
                return status
            if status["state"] == "failed":
                break
            time.sleep(0.4)
        self.state = "failed"
        raise ResetError("archive desktop did not become healthy after restoration")

    def manifest(self):
        status = self.status()
        config = as_json(read_regular(ARCHIVE_ROOT / "config.json"))
        sites, raw_hashes = site_manifest(config)
        stable = {
            "preboot_restoration_sha256": sha(json_bytes(self.baseline)),
            "workspace": tree(WORKSPACE),
            "workspace_input": tree(WORKSPACE / "input"),
            "workspace_output": tree(WORKSPACE / "output"),
            "workspace_downloads": tree(WORKSPACE / "downloads"),
            "sites": sites,
            "uploads": tree(STATE / "files"),
            "login_profiles": profile_manifest(config),
        }
        chromium, _, _, _ = chromium_profile()
        volatile = {"profiles_and_audit": volatile_profile(), "site_state_raw": raw_hashes,
                    "chromium_profile_raw_field_sha256": {
                        key: sha(json_bytes(value)) for key, value in chromium.items()
                    },
                    "stamped_boot_marker_present": present(STATE / ".booted"),
                    "advisory_secret_policy": "generated privately by each archive bootstrap"}
        return {"status": status, "stable": stable, "stable_sha256": sha(json_bytes(stable)),
                "volatile": volatile}


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _, uid, _ = struct.unpack("3i", credentials)
        if uid != 0:
            return
        action = self.rfile.readline(32).strip()
        control = self.server.supervisor
        handlers = {b"status": control.status, b"reset": control.reset, b"manifest": control.manifest}
        if action not in handlers:
            response = {"error": "unsupported control request"}
        else:
            try:
                response = handlers[action]()
            except (OSError, ResetError, subprocess.SubprocessError) as exc:
                if action == b"reset":
                    control.state = "failed"
                response = {
                    "error": str(exc) if isinstance(exc, ResetError) else type(exc).__name__,
                    "boot_uuid": control.boot_uuid, "generation": control.generation,
                    "state": control.state, "startup_failure": control.startup_failure,
                }
        try:
            self.wfile.write(json_bytes(response) + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    if os.getpid() != 1 or os.geteuid() != 0:
        raise ResetError("the reset supervisor must be container root as PID 1")
    mounted = Path(__file__).parent.stat()
    if mounted.st_uid != 0 or mounted.st_mode & 0o077:
        raise ResetError("the reset runtime directory must be mounted root-only")
    command = tuple(sys.argv[1:]) or ARCHIVE_START
    if command != ARCHIVE_START:
        raise ResetError("desktop command must match the original archive entrypoint")
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    owner = PRIVATE.lstat()
    if not stat.S_ISDIR(owner.st_mode) or owner.st_uid != 0 or owner.st_mode & 0o077:
        raise ResetError("unsafe control directory")
    if present(BASELINE) or present(CONTROL):
        raise ResetError("reset supervisor requires a fresh desktop container")
    pristine_capture()
    control = Supervisor(command, restored_root_digests())

    def terminate(_signum, _frame):
        control.terminated = True

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    with socketserver.UnixStreamServer(str(CONTROL), ControlHandler) as server:
        CONTROL.chmod(0o600)
        server.supervisor = control
        server.timeout = 0.25
        try:
            # Match the archive entrypoint's original boot umask, while retaining
            # explicit protection on the controller directory and socket.
            os.umask(0o022)
            control.start_boot(0)
            while not control.terminated:
                server.handle_request()
                control.reap()
                control.advance_startup()
        finally:
            control.state = "stopped"
            control.stop_desktop()
            control.mirror_diagnostics()
            CONTROL.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except ResetError as exc:
        sys.exit(str(exc))
