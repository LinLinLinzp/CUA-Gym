#!/usr/bin/env python3
"""Build hub mock sites into factory/build/sites/<site>/dist (static, arch-independent).

Cached by a digest of the exported source files, so rebuilding is a no-op until the mock
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
from hashlib import sha256
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
HUB = FACTORY.parent / "hub" / "websites"
CACHE = FACTORY / "build" / "sites"
CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
REGISTRY = os.environ.get("NPM_REGISTRY", "https://registry.npmmirror.com")
PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")
MISSING_OPTIONAL_PEER = re.compile(r"Missing: (@emnapi/(?:core|runtime))@(\S+) from lock file")
OVERLAYS = Path(__file__).with_name("overlays")


def ensure_revision(revision: str):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid Hub release identifier")
    release = HUB.parent / "releases" / revision
    if not (release / "templates").is_dir():
        raise FileNotFoundError(f"Missing Hub source release: {release}")
    return release


def source_root(revision):
    return ensure_revision(revision) if revision else HUB.parent


def read_schema(site: str, *, revision: str | None = None) -> bytes | None:
    settings = CATALOG[site]
    version = revision or settings.get("hub_revision")
    path = source_root(version) / "websites" / settings["hub"] / "SCHEMA.md"
    if version or path.is_file():
        return path.read_bytes()
    return None


def task_revisions(spec: dict) -> dict:
    revisions = spec.get("mock_revisions", {})
    if not isinstance(revisions, dict) or revisions.keys() - set(spec["sites"]):
        raise ValueError("Mock revisions must belong to the task's existing sites")
    for site, revision in revisions.items():
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(f"{site}: mock revision must be an immutable Git commit ID")
    return revisions


def tree_hash(path: Path) -> str:
    if not path.is_dir():
        raise FileNotFoundError(path)
    digest = sha256()
    for directory, subdirs, files in os.walk(path):
        subdirs[:] = sorted(name for name in subdirs if name not in
                            {"node_modules", "dist", ".git", ".mock-files", ".mock-states"})
        for name in sorted(files):
            item = Path(directory) / name
            digest.update(item.relative_to(path).as_posix().encode() + b"\0")
            digest.update(sha256(item.read_bytes()).digest())
    return digest.hexdigest()


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


def overlay_patch(site, overlay):
    if site not in CATALOG or not isinstance(overlay, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", overlay):
        raise ValueError(f"Unknown overlay {site}/{overlay}")
    path = OVERLAYS / site / f"{overlay}.patch"
    if not path.is_file() or path.resolve() != path:
        raise ValueError(f"Unknown overlay {site}/{overlay}")
    return path.read_bytes().replace(b"\r\n", b"\n")


def build_archived_site(src, target, env, revision, patch):
    site_path = f"websites/{src.name}"
    source = source_root(revision)
    with tempfile.TemporaryDirectory(prefix="cua-site-overlay-") as directory:
        root = Path(directory)
        work = root / site_path
        shutil.copytree(source / site_path, work, ignore=shutil.ignore_patterns(
            "node_modules", "dist", ".mock-files", ".mock-states"))
        shutil.copytree(source / "templates", root / "templates")
        if patch is not None:
            subprocess.run(["git", "apply", "--ignore-space-change", "-"], input=patch, cwd=work, check=True)
        missing = install_dependencies(work, env)
        if missing:
            complete_optional_peers(work, missing, env)
        build_distribution(work, target, env)


def build(site: str, *, overlay: str | None = None, revision: str | None = None) -> Path:
    settings = CATALOG[site]
    src = HUB / settings["hub"]
    default_revision = settings.get("hub_revision")
    explicit_revision = revision is not None
    revision = revision or default_revision
    if revision is not None:
        ensure_revision(revision)
    cache_name = f"overlay-{site}-{overlay}" if overlay is not None else site
    default_overlay = settings.get("default_overlay")
    if overlay is None and not explicit_revision:
        overlay = default_overlay
    patch = overlay_patch(site, overlay) if overlay is not None else None
    # A task pin selects the original revision, even when a newer catalog
    # overlay uses that same revision as its base.
    if revision is not None and (revision != default_revision
                                 or (explicit_revision and overlay is None and default_overlay is not None)):
        cache_name += f"-{revision}"
    target = CACHE / cache_name
    stamp = target / "tree.txt"
    CACHE.mkdir(parents=True, exist_ok=True)
    # Concurrent tasks may use the same mock. Serialize its npm install and cache update.
    with (CACHE / f".{cache_name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        release = source_root(revision)
        key = tree_hash(release / "websites" / src.name) + ":" + tree_hash(release / "templates")
        if patch is not None:
            key += f":{sha256(patch).hexdigest()}"
        if stamp.exists() and stamp.read_text() == key and (target / "dist" / "index.html").exists():
            return target / "dist"
        env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
        if revision is not None or patch is not None:
            build_archived_site(src, target, env, revision, patch)
            stamp.write_text(key)
            return target / "dist"
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
