#!/usr/bin/env python3
"""Plan task slots: which sites each task uses and which labels it targets.

    allocate.py --total 200 --out output/harbor/plan/batch01.jsonl [--seed 7]

Rules (keep RL data diverse, avoid re-picking sites):
  * scenarios split evenly; a slot's scenario = its primary site's scenario
  * every slot: 1 primary scenario site + optional secondary scenario site from
    another scenario + 1-2 shared tools (mail/chat/docs/calendar)
  * a scenario site is primary at most MAX_PRIMARY times and secondary at most
    MAX_SECONDARY times, counting previous batches (catalog/usage.jsonl);
    least-used sites go first, scarce scenarios are filled first
  * no two slots share the same site set; sites sharing an origin never mix
  * labels: no 简单 tasks — op x tool targets come from LABEL_MIX
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]
CATALOG = json.loads((FACTORY / "catalog" / "sites.json").read_text())["sites"]
USAGE = FACTORY / "catalog" / "usage.jsonl"
SCENARIOS = ["生活消费", "文化内容", "组织办公", "专业事务", "产业运营", "数字技术", "公共事务"]
MAX_PRIMARY = 1  # each scenario site leads at most one task
MAX_SECONDARY = 2
# (operation_difficulty, tool_type, share): 4 中等 / 6 困难 / 3 中等
LABEL_MIX = [(2, 2, 0.50), (3, 2, 0.25), (3, 1, 0.25)]
# Shared tools people actually reach for together with business apps.
COMMON_WEIGHTS = {"gmail": 5, "slack": 5, "outlook_web": 2, "microsoft_teams": 2, "google_sheets": 3, "google_docs": 2,
                  "google_drive": 2, "google_calendar": 2, "notion": 2, "zoom_web": 1}


def ready(name):
    return CATALOG[name]["status"] == "ready" and CATALOG[name]["locale"] == "en"


def previous_usage():
    primary, secondary = Counter(), Counter()
    if USAGE.exists():
        for line in USAGE.read_text().splitlines():
            slot = json.loads(line)
            primary[slot["primary"]] += 1
            if slot.get("secondary"):
                secondary[slot["secondary"]] += 1
    return primary, secondary


def compatible(sites):
    groups = [CATALOG[s].get("origin_group") or CATALOG[s]["origins"][0] for s in sites]
    return len(groups) == len(set(groups))


def label_plan(total, rng):
    labels = []
    for op, tool, share in LABEL_MIX:
        labels += [(op, tool)] * round(total * share)
    labels = (labels + [LABEL_MIX[0][:2]] * total)[:total]
    rng.shuffle(labels)
    return labels


def allocate(total, seed, prefix="b"):
    rng = random.Random(seed)
    used, used_secondary = previous_usage()
    by_scenario = {sc: [n for n, s in CATALOG.items() if s["role"] == "scenario" and s["scenario"] == sc and ready(n)]
                   for sc in SCENARIOS}
    commons = [n for n, s in CATALOG.items() if s["role"] == "common" and ready(n)]
    quota = {sc: total // len(SCENARIOS) + (i < total % len(SCENARIOS)) for i, sc in enumerate(SCENARIOS)}
    labels = label_plan(total, rng)
    seen, slots, short = set(), [], Counter()

    def pick(pool, counts, limit):
        pool = [n for n in pool if counts[n] < limit]
        rng.shuffle(pool)
        return sorted(pool, key=lambda n: used[n] + used_secondary[n])[:1]

    # Scarce scenarios first so their few sites aren't spent as secondaries.
    order = sorted(SCENARIOS, key=lambda sc: len(by_scenario[sc]))
    for sc in order:
        for _ in range(quota[sc]):
            for _attempt in range(50):
                primary = pick(by_scenario[sc], used, MAX_PRIMARY)
                if not primary:
                    break
                secondary = []
                if rng.random() < 0.4:
                    others = [n for o in SCENARIOS if o != sc for n in by_scenario[o]]
                    secondary = pick(others, used_secondary, MAX_SECONDARY)
                k = 1 if secondary else 2  # at least three sites per task
                tools = rng.choices(commons, weights=[COMMON_WEIGHTS.get(c, 1) for c in commons], k=4)
                tools = list(dict.fromkeys(tools))[:k]
                sites = primary + secondary + tools
                key = frozenset(sites)
                if key in seen or not compatible(sites):
                    continue
                seen.add(key)
                used[primary[0]] += 1
                for s in secondary:
                    used_secondary[s] += 1
                op, tool = labels[len(slots)]
                slots.append({"slot_id": f"{prefix}-s{len(slots) + 1:03d}", "scenario": sc, "primary": primary[0],
                              "secondary": secondary[0] if secondary else None, "tools": tools, "sites": sites,
                              "operation_difficulty": op, "tool_type": tool, "difficulty": op * tool})
                break
            else:
                short[sc] += 1
                continue
            if not primary:
                short[sc] += 1
    return slots, short, by_scenario


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    prefix = args.out.stem if args.out else "dry"
    slots, short, pools = allocate(args.total, args.seed, prefix)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in slots))
    print(f"{len(slots)} slots planned")
    for sc in SCENARIOS:
        n = sum(s["scenario"] == sc for s in slots)
        print(f"  {sc}: {n} slots from {len(pools[sc])} ready sites (capacity {len(pools[sc]) * MAX_PRIMARY})"
              + (f"  SHORT {short[sc]}" if short[sc] else ""))
    print("  labels:", dict(Counter(f"op{s['operation_difficulty']}xtool{s['tool_type']}={s['difficulty']}" for s in slots)))


if __name__ == "__main__":
    main()
