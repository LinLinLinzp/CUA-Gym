#!/usr/bin/env python3
"""Plan lever experiments: one task per difficulty lever, on newly built sites only.

    plan_experiments.py --out output/harbor/plan/exp1.jsonl      (appends; idempotent)

Each slot gets a distinct new primary scenario site that fits the lever (by keywords in
the site's workflows), one new shared tool (mail or chat) and sometimes a second new
scenario site. Levers whose prerequisites aren't built yet are skipped; re-run after
more mocks are accepted to fill them in.
"""

import argparse
import json
import random
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
BUILT = json.loads((FACTORY / "catalog" / "built_sites.json").read_text()) if (FACTORY / "catalog" / "built_sites.json").exists() else {}
LEVERS = json.loads((FACTORY / "catalog" / "levers.json").read_text())
FIT = {  # keywords a primary site's workflows should mention for the lever to be natural
    "L02": ["receipt", "attachment", "document", "invoice", "claim", "upload"],
    "L03": ["orders", "tickets", "transactions", "listings", "issues", "cases"],
    "L08": ["board", "drag", "sprint", "schedule", "calendar", "gantt", "sheet"],
    "L09": ["submit", "filing", "payment", "publish", "approval", "pay"],
    "L11": ["policy", "contract", "document", "terms", "filing"],
    "L12": ["invoice", "payment", "billing", "fees", "rent", "payroll", "tax"],
    "L13": ["upload", "files", "documents", "import", "attachments"],
}
MAIL = ("mail",)
CHAT = ("chat", "mattermost")


def is_new(name):
    return name in BUILT and CATALOG.get(name, {}).get("status") == "ready"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--levers", help="comma-separated lever ids to plan (default: all)")
    parser.add_argument("--allow-reuse", action="store_true", help="experiments may share new primary sites")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    existing = [json.loads(l) for l in args.out.read_text().splitlines()] if args.out.exists() else []
    done_levers = {s["levers"][0] for s in existing}
    used = {s["primary"] for s in existing}
    scenario_sites = [n for n in CATALOG if is_new(n) and CATALOG[n]["role"] == "scenario"]
    tools = [n for n in CATALOG if is_new(n) and CATALOG[n]["role"] == "common"]
    mail = [t for t in tools if any(k in t for k in MAIL)]
    chat = [t for t in tools if any(k in t for k in CHAT)]
    if not (mail or chat) and not args.allow_reuse:
        print("no new mail/chat tool built yet; nothing planned")
        return
    wanted = set(args.levers.split(",")) if args.levers else None
    planned = []
    for lever in LEVERS:
        lid = lever["id"]
        if lid in done_levers or (wanted and lid not in wanted):
            continue
        free = [n for n in scenario_sites if args.allow_reuse or n not in used]
        if args.allow_reuse:  # spread levers over the few new sites
            free.sort(key=lambda n: sum(s["primary"] == n for s in existing + planned))
        keys = FIT.get(lid, [])
        ranked = sorted(free, key=lambda n: -sum(k in BUILT[n]["workflows"].lower() for k in keys))
        if not ranked or (keys and not args.allow_reuse and not any(k in BUILT[ranked[0]]["workflows"].lower() for k in keys)):
            continue
        primary = ranked[0]
        used.add(primary)
        others = [n for n in scenario_sites if n != primary and (args.allow_reuse or n not in used)]
        secondary = rng.choice(others) if others and rng.random() < 0.5 else None
        tool = (rng.choice(mail or chat) if rng.random() < 0.6 or not chat else rng.choice(chat)) if (mail or chat) else None
        op = 3 if lid == "L08" else 2
        slot = {"slot_id": f"{args.out.stem}-{lid.lower()}", "scenario": CATALOG[primary]["scenario"], "primary": primary,
                "secondary": secondary, "tools": [tool] if tool else [],
                "sites": [primary] + ([secondary] if secondary else []) + ([tool] if tool else []),
                "levers": [lid], "operation_difficulty": op, "tool_type": 2, "difficulty": op * 2}
        planned.append(slot)
    with args.out.open("a") as f:
        for slot in planned:
            f.write(json.dumps(slot, ensure_ascii=False) + "\n")
    print(f"planned {len(planned)} new experiment slots ({len(done_levers) + len(planned)}/{len(LEVERS)} levers covered)")
    for s in planned:
        print(f"  {s['slot_id']}: {s['sites']}")


if __name__ == "__main__":
    main()
