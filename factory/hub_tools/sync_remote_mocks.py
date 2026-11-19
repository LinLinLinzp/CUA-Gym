#!/usr/bin/env python3
"""List published mock sites, or import and certify them with --apply."""

import argparse
import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path

import build_dists
from build_mocks import load, slug


FACTORY = Path(__file__).resolve().parents[1]
HUB = FACTORY.parent / "hub"
CATALOG = FACTORY / "catalog"
BUILD = FACTORY / "build"
BASE = "31e9abd047d0ed728476aaec93c816b97e5f6955"
TIER_A = "codex/mock-tier-a-production"
PILOT = "codex/mock-wayfair-grubhub"
HANDOFF = BUILD / "mock_status_snapshot_20261118-1731.json"
WORKFLOWS_PASS = re.compile(
    r"WORKFLOWS:\s*PASS|TEST COMPLETE:.*PASS|all (\w+ )?`?SEED\.md`? workflows passed", re.I
)


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(HUB), *args], text=True, capture_output=True, check=check)


def publish_ref(branch):
    ref = f"refs/heads/{branch}"
    visible = git("ls-remote", "--exit-code", "--heads", "origin", ref, check=False)
    if visible.returncode == 2:
        return None
    visible.check_returncode()
    tracking = f"refs/remotes/origin/{branch}"
    git("fetch", "--no-tags", "origin", f"{ref}:{tracking}")
    revision = git("rev-parse", tracking).stdout.strip()
    git("merge-base", "--is-ancestor", BASE, revision)
    return revision


def released_sites(branch):
    candidates = load(CATALOG / "candidates.json", {})
    sites = {
        slug(site["brand"]): {**site, "scenario": scenario}
        for scenario, group in candidates.items()
        for site in group["new"]
    }
    if branch == PILOT:
        return {name: sites[name] for name in ("grubhub", "wayfair")}
    local = json.loads(HANDOFF.read_text())
    return {name: site for name, site in sites.items() if site["tier"] == "A" and name not in local}


def published_sites(branch, revision, registered):
    released = released_sites(branch)
    paths = git("diff", "--no-renames", "--name-only", "-z", BASE, revision).stdout.split("\0")
    directories = {"/".join(path.split("/")[:2]) for path in paths if path}
    for directory in sorted(directories):
        site = directory.removeprefix("websites/").removesuffix("_mock")
        if directory != f"websites/{site}_mock" or site not in released:
            print(f"Outside delivery scope: {directory}")
            continue
        remote_tree = git("rev-parse", f"{revision}:{directory}", check=False)
        if remote_tree.returncode:
            print(f"On hold: {site} was removed from the published branch")
            continue
        tree = remote_tree.stdout.strip()
        files = set(git("ls-tree", "--name-only", tree).stdout.splitlines())
        required = {"AUDIT.md", "TEST.md", "SEED.md", "SCHEMA.md", "package-lock.json", "index.html"}
        if required - files or not WORKFLOWS_PASS.search(git("show", f"{tree}:TEST.md").stdout):
            print(f"On hold: {site} is missing its delivery files or passing workflow report")
            continue
        local = git("rev-parse", "--verify", f"HEAD:{directory}", check=False)
        local_tree = local.stdout.strip() if local.returncode == 0 else None
        existing = registered.get(site, {})
        if git("status", "--porcelain", "--", directory).stdout or (
            not local_tree and (HUB / directory).exists()
        ):
            print(f"On hold: {site} has local changes")
        elif tree == local_tree == existing.get("source_tree"):
            print(f"Ready: {site} is already registered")
        elif local_tree and local_tree != tree:
            print(f"On hold: {site} already has a different local version")
        else:
            yield site, directory, tree, local_tree, released[site]


def passing_sites(script, names):
    run = subprocess.run([sys.executable, str(Path(__file__).with_name(script)), *names],
                         text=True, stdout=subprocess.PIPE)
    print(run.stdout, end="", flush=True)
    if run.returncode and (script != "certify_site.py" or run.returncode != 1):
        run.check_returncode()
    return set(re.findall(r"^PASS\s+(\S+)", run.stdout, re.M))


def sync(branch, apply):
    revision = publish_ref(branch)
    if not revision:
        print(f"Waiting for the first push to {branch}")
        return
    print(f"Published {branch} at {revision}")
    registry = CATALOG / "built_sites.json"
    registered = load(registry, {})
    pending = list(published_sites(branch, revision, registered))
    for site, *_ in pending:
        print(f"Pending local certification: {site}", flush=True)
    if not apply:
        return
    if not pending:
        catalog = load(CATALOG / "sites.json", {}).get("sites", {})
        if registered.keys() - catalog.keys():
            subprocess.run([sys.executable, str(CATALOG / "build_catalog.py")], check=True)
        return

    git("symbolic-ref", "HEAD")
    built = {}
    for site, directory, tree, local_tree, candidate in pending:
        if tree != local_tree:
            if (HUB / directory).exists() or git("status", "--porcelain", "--", directory).stdout:
                print(f"On hold: {site} appeared locally during sync", flush=True)
                continue
            git("restore", f"--source={revision}", "--staged", "--worktree", "--", directory)
            git("commit", "-m", f"Import {candidate['brand']} mock", "-m",
                f"Source: {branch} at {revision}\nSite tree: {tree}", "--", directory)
        app = Path(directory).name
        build_dists.CATALOG[site] = {"hub": app}
        try:
            build_dists.build(site)
        except (subprocess.CalledProcessError, SystemExit) as exc:
            print(f"On hold: {site} build failed: {exc}", flush=True)
            continue
        if (BUILD / "sites" / site / "tree.txt").read_text() != tree:
            print(f"On hold: {site} changed locally during build", flush=True)
            continue
        built[site] = {
            "hub": app, "brand": candidate["brand"], "origins": [candidate["origin"]],
            "scenario": candidate["scenario"], "tier": candidate["tier"],
            "workflows": candidate["workflows"],
            "audit_debt": load(HUB / directory / ".audit_debt.json", []),
            "source_branch": branch, "source_commit": revision, "source_tree": tree,
        }
    if not built:
        return

    static = passing_sites("certify_site.py", [entry["hub"] for entry in built.values()])
    test = [name for name, entry in built.items() if entry["hub"] in static]
    if not test:
        return
    dynamic = passing_sites("dyn_certify.py", test)
    ready = [name for name in test if name in dynamic]
    if ready:
        temp = registry.with_suffix(".json.tmp")
        temp.write_text(json.dumps({**load(registry, {}), **{n: built[n] for n in ready}},
                                   indent=1, ensure_ascii=False) + "\n")
        temp.replace(registry)
        subprocess.run([sys.executable, str(CATALOG / "build_catalog.py")], check=True)
        print("Registered:", ", ".join(ready))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="check the Wayfair and Grubhub pilot branch")
    parser.add_argument("--apply", action="store_true", help="import, certify and register published sites")
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    with (BUILD / ".sync_remote_mocks.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sync(PILOT if args.pilot else TIER_A, args.apply)


if __name__ == "__main__":
    main()
