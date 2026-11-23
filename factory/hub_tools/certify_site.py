#!/usr/bin/env python3
"""Static certification of hub mocks for the single-container runtime.

    certify_site.py gmail_mock slack_mock ...      report only
    certify_site.py --fix gmail_mock ...           also apply safe fixes (page title)
    certify_site.py --all                          report on every mock

Checks what sitehost/browserd rely on:
  sid       info: falls back to sessionStorage 'mock_sid' (sitehost also redirects page loads to carry ?sid=)
  sync      client pushes state to the server via /post (else the verifier sees nothing)
  title     <title> has no "Clone"/"Mock" giveaway
  external  absolute asset URLs (served from the offline cache; count only)
  timers    setInterval in src (manual check: an idle tab must not POST stale state)
Dynamic checks (render, UI change reaches current.json) run in the task image.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "hub" / "websites"
TITLE_JUNK = re.compile(r"\s*(?:[-–|:]\s*)?\b(?:Clone|Mock)\b", re.I)


def sources(mock: Path):
    return [p for p in (mock / "src").rglob("*") if p.suffix in (".js", ".jsx", ".ts", ".tsx")]


def certify(mock: Path, fix: bool) -> dict:
    code = "\n".join(p.read_text(errors="ignore") for p in sources(mock))
    index = mock / "index.html"
    html = index.read_text()
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = title.group(1).strip() if title else ""
    clean = TITLE_JUNK.sub("", title).strip(" -–|:") or title
    if fix and clean != title:
        index.write_text(html.replace(f"<title>{title}</title>", f"<title>{clean}</title>", 1))
    report = {
        "sid": "mock_sid" in code,
        "sync": bool(re.search(r"""['"`]/post""", code)),
        "title": clean if fix else title,
        "title_ok": fix or clean == title,
        "external": len(set(re.findall(r"https?://(?!localhost)[\w.-]+\.\w+/[^\s'\"`)]*", code + html))),
        "timers": len(re.findall(r"setInterval\(", code)),
    }
    report["pass"] = report["sync"] and report["title_ok"]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mocks", nargs="*")
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    names = sorted(p.name for p in HUB.iterdir() if (p / "index.html").exists()) if args.all else args.mocks
    results = {name: certify(HUB / name, args.fix) for name in names}
    for name, r in results.items():
        flags = " ".join(f"{k}={v}" for k, v in r.items() if k != "pass")
        print(f"{'PASS' if r['pass'] else 'FAIL'} {name:<26} {flags}")
    out = Path(__file__).resolve().parents[1] / "build" / "certify.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(out.read_text()) if out.exists() else {}
    out.write_text(json.dumps({**previous, **results}, ensure_ascii=False, indent=1))
    return 0 if all(r["pass"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
