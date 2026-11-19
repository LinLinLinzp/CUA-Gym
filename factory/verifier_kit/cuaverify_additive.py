"""Shared grading helpers, vendored into every task's tests/ directory.

A task verifier builds a Grader, records weighted checks (each scored 0..1),
and calls finish(). reward = sum(weight*score)/sum(weight).
Infrastructure problems raise InfraError: the run is reported
as invalid and no reward file is written, so it can't count as a model's 0.
"""

import csv
import html
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

VAR_DIR = Path(os.environ.get("CUA_VAR_DIR", "/var/lib/cua"))
OUTPUT_DIR = Path(os.environ.get("CUA_OUTPUT_DIR", "/workspace/output"))
LOG_DIR = Path(os.environ.get("CUA_VERIFIER_LOG_DIR", "/logs/verifier"))
# Debounced mocks flush ~300-500 ms after the last UI change.
SETTLE_SECONDS = float(os.environ.get("CUA_SETTLE_SECONDS", "2"))


class InfraError(Exception):
    """Trusted data is missing or unreadable: not the model's fault."""


# ------------------------------------------------------------------ state
def load_site(site: str):
    """Return (initial, current) state of a site as persisted by sitehost."""
    folder = VAR_DIR / "state" / site
    try:
        initial = json.loads((folder / "initial.json").read_text())
        current = json.loads((folder / "current.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InfraError(f"cannot read {site} state: {exc}") from exc
    return initial, current


def new_items(before, after, key="id"):
    """Items present in `after` whose key never appeared in `before`."""
    seen = {item.get(key) for item in before or []}
    return [item for item in after or [] if item.get(key) not in seen]


def changed_items(before, after, key="id"):
    """(old, new) pairs for items that exist in both lists but differ."""
    old = {item.get(key): item for item in before or []}
    return [(old[item.get(key)], item) for item in after or []
            if item.get(key) in old and old[item.get(key)] != item]


# ------------------------------------------------------------------ text
def plain(text) -> str:
    """HTML/markdown-ish rich text -> lowercase plain text with single spaces."""
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", " ", str(text or ""), flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip().lower()


_MONEY = re.compile(r"(?<![\w.])\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d])")


def amounts(text) -> list:
    """All numbers in a text, parsed as dollars (handles $1,234.50 and 54)."""
    found = []
    for whole, cents in _MONEY.findall(plain(text)):
        found.append(float(whole.replace(",", "") + "." + (cents or "0")))
    return found


def mentions_amount(text, value, tol=0.005) -> bool:
    return any(abs(a - float(value)) <= tol for a in amounts(text))


def mentions(text, *needles) -> bool:
    body = plain(text)
    return all(n.lower() in body for n in needles)


def money_eq(a, b, tol=0.005) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ files
def read_csv(name: str):
    """Rows of an agent CSV as dicts with stripped lowercase headers, or None if absent."""
    path = OUTPUT_DIR / name
    if not path.is_file() or path.is_symlink():
        return None
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
    except (UnicodeDecodeError, csv.Error):
        return []


def run_replay(script: Path, env: dict, timeout: int = 60, user: str = "agent"):
    """Lever L07: run an agent-delivered script on hidden inputs as the unprivileged user.

    `env` carries the paths the instruction promised (e.g. INPUT_DIR, OUTPUT_DIR); the
    caller prepares them (readable/writable by `user`). Returns (exit_code, stdout+stderr);
    exit code 124 means it timed out. A missing interpreter is the model's failure, not infra.
    """
    import shutil
    import subprocess
    runner = {".py": ["python3"], ".sh": ["bash"], ".js": ["node"], ".ts": ["bun"]}.get(script.suffix)
    if not runner or not script.is_file():
        return 127, f"no runnable script at {script}"
    cmd = runner + [str(script)]
    runuser = shutil.which("runuser")  # absolute path: the clean PATH below has no sbin
    if os.geteuid() == 0 and runuser:
        cmd = [runuser, "-u", user, "--"] + cmd
    clean = {"PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/tmp", "LANG": "C.UTF-8", **env}
    try:
        done = subprocess.run(cmd, env=clean, cwd=str(script.parent), capture_output=True, text=True, timeout=timeout)
        return done.returncode, (done.stdout + done.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        return 124, "timed out"


# ------------------------------------------------------------------ grading
class Grader:
    def __init__(self, task_id: str, version: str):
        self.task_id, self.version = task_id, version
        self.checks = []

    def add(self, check_id: str, weight: float, score: float, detail: str = "", core: bool = False):
        score = max(0.0, min(1.0, float(score)))
        self.checks.append({"id": check_id, "weight": weight, "score": round(score, 4), "detail": detail, "core": core})
        return score

    def reward(self) -> float:
        total = sum(c["weight"] for c in self.checks)
        raw = sum(c["weight"] * c["score"] for c in self.checks) / total if total else 0.0
        return round(raw, 4)

    def report(self, reward: float) -> dict:
        return {"task_id": self.task_id, "task_version": self.version, "status": "valid",
                "run_id": os.environ.get("HARBOR_TRIAL_NAME", ""), "reward": reward,
                "checks": self.checks}

    def finish(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        reward = self.reward()
        (LOG_DIR / "report.json").write_text(json.dumps(self.report(reward), ensure_ascii=False, indent=2))
        (LOG_DIR / "reward.txt").write_text(f"{reward}\n")
        for c in self.checks:
            print(f"{c['id']:<28} w={c['weight']:<4} score={c['score']:<6} {c['detail']}")
        print(f"REWARD: {reward}")
        return reward


def run(task_id: str, version: str, evaluate, *, grader_type=Grader):
    """Entry point: evaluate(grader) records checks; infra errors exit non-zero without reward."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "reward.txt").unlink(missing_ok=True)
    time.sleep(SETTLE_SECONDS)
    # Keep sitehost's write log next to the report so a platform run shows who wrote what.
    writes = VAR_DIR / "writes.log"
    if writes.is_file():
        try:
            (LOG_DIR / "writes.log").write_bytes(writes.read_bytes())
        except OSError:
            pass
    grader = grader_type(task_id, version)
    try:
        evaluate(grader)
    except InfraError as exc:
        _invalid(task_id, version, f"infrastructure: {exc}")
    except Exception:
        _invalid(task_id, version, "verifier crashed:\n" + traceback.format_exc())
    grader.finish()


def _invalid(task_id, version, reason):
    (LOG_DIR / "report.json").write_text(json.dumps(
        {"task_id": task_id, "task_version": version, "status": "invalid", "reason": reason}, ensure_ascii=False, indent=2))
    print(reason, file=sys.stderr)
    sys.exit(1)
