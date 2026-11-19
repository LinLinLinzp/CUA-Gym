#!/usr/bin/env python3
"""Build hub mock sites into factory/build/sites/<site>/dist (static, arch-independent).

Cached by the site's git tree hash, so rebuilding is a no-op until the mock
changes. Usage: build_dists.py gmail slack shopify   (names from catalog/sites.json)

Env: NPM_REGISTRY (default npmmirror). On machines whose Node lacks some root
CAs, point NODE_EXTRA_CA_CERTS at a PEM bundle (macOS: export the System roots).
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
HUB = FACTORY.parent / "hub" / "websites"
CACHE = FACTORY / "build" / "sites"
CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
REGISTRY = os.environ.get("NPM_REGISTRY", "https://registry.npmmirror.com")
PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")
MISSING_OPTIONAL_PEER = re.compile(r"Missing: (@emnapi/(?:core|runtime))@(\S+) from lock file")


def tree_hash(path: Path) -> str:
    out = subprocess.run(["git", "-C", str(HUB.parent), "rev-parse", f"HEAD:websites/{path.name}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(HUB.parent), "status", "--porcelain", "--", f"websites/{path.name}"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit(f"{path.name} has uncommitted changes; commit them so the dist is reproducible")
    return out


def install_dependencies(src, env):
    install = ["npm", "ci", f"--registry={REGISTRY}", "--no-audit", "--no-fund", "--loglevel=error"]
    for command in (install, install + ["--legacy-peer-deps"]):
        result = subprocess.run(command, cwd=src, env=env, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout, end="")
            return {}
    missing = dict(MISSING_OPTIONAL_PEER.findall(result.stderr))
    if not missing:
        print(result.stderr, file=sys.stderr, end="")
        result.check_returncode()
    return missing


def complete_optional_peers(src, missing, env):
    lock = src / "package-lock.json"
    locked = json.loads(lock.read_text())
    subprocess.run(["npm", "install", "--package-lock-only", "--ignore-scripts",
                    f"--registry={REGISTRY}", "--no-audit", "--no-fund", "--loglevel=error"],
                   cwd=src, env=env, check=True)
    resolved = json.loads(lock.read_text())["packages"]
    for package, version in missing.items():
        key = f"node_modules/{package}"
        entry = resolved.get(key, {})
        if key in locked["packages"] or not (
            entry.get("version") == version and entry.get("dev") and entry.get("optional") and entry.get("integrity")
        ):
            raise SystemExit(f"{src.name}: unable to restore optional locked peer {package}@{version}")
        locked["packages"][key] = entry
    lock.write_text(json.dumps(locked, indent=2) + "\n")
    subprocess.run(["npm", "ci", f"--registry={REGISTRY}", "--no-audit", "--no-fund", "--loglevel=error"],
                   cwd=src, env=env, check=True)


def build_distribution(src, target, env):
    subprocess.run(["npx", "vite", "build", "--outDir", "dist", "--emptyOutDir"], cwd=src, env=env, check=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src / "dist", target / "dist")


def build(site: str) -> Path:
    src = HUB / CATALOG[site]["hub"]
    target = CACHE / site
    stamp = target / "tree.txt"
    CACHE.mkdir(parents=True, exist_ok=True)
    # Concurrent tasks may use the same mock. Serialize its npm install and cache update.
    with (CACHE / f".{site}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        key = tree_hash(src)
        if stamp.exists() and stamp.read_text() == key and (target / "dist" / "index.html").exists():
            return target / "dist"
        env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
        missing = install_dependencies(src, env)
        if missing:
            # Keep the received source tree intact. Vite's native builds do not use these WASM peers.
            with tempfile.TemporaryDirectory(prefix="cua-site-build-") as directory:
                scratch = Path(directory)
                work = scratch / "websites" / src.name
                shutil.copytree(src, work, ignore=shutil.ignore_patterns("node_modules", "dist", ".mock-states", ".mock-files"))
                shutil.copytree(HUB.parent / "templates", scratch / "templates")
                complete_optional_peers(work, missing, env)
                build_distribution(work, target, env)
                shutil.copyfile(work / "package-lock.json", target / "build-package-lock.json")
        else:
            build_distribution(src, target, env)
        stamp.write_text(key)
        return target / "dist"


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(name, build(name))
