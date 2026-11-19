#!/usr/bin/env python3
"""Verifier for escalation-review-prep. Checkpoints mirror rubric.json (Z*, J*, S*, C*).

Expected values were derived independently from seed/zendesk.json, seed/jira.json,
seed/slack.json and input/billing_accounts.csv:

* Slack th_review (under Tomás' m_e4): FLD-431 is dropped and replaced by FLD-447
  (m_r2/m_r3); Diego already tagged 3220/3222 with fld-412 (m_r1); billing matches on
  billing_domain, not on the account name (m_r4). Window: opened since 2026-09-01 PT,
  i.e. created_at >= 2026-09-01T07:00:00Z.
* Escalated = group 4 "Engineering Escalations" + custom field jira_issue. Exceptions:
  3200's field still says FLD-412 but its internal note + Jira jc4 move it to FLD-398;
  3168 is closed and merged into 3166 (same account); 3140 was created 06:40Z (before
  the window); 3125 is from August.
* Accounts = requester e-mail domain -> billing_domain (3177 has no org:
  summitroofing.co -> ACC-1005; org "Brightline" = brightline-electric.com -> ACC-1004).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, new_items, plain, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/escalation-review-prep", "0.1.1"

# ticket -> (jira key, account_id, status in the seed). Status is the seed's; tagging
# must not change it (Z6), so it is also what the CSV must report.
TARGETS = {
    # FLD-412: 110000 (1013) + 66000 (1011) + 21000 (1009) + 48000 (1012) + 42000 (1001) = 287000, 5 accts
    3141: ("FLD-412", "ACC-1013", "solved"),   # meridianfp.com
    3157: ("FLD-412", "ACC-1011", "hold"),     # redwoodelevator.com
    3183: ("FLD-412", "ACC-1009", "solved"),   # atlasappliance.com
    3220: ("FLD-412", "ACC-1012", "open"),     # keystonesecurity.com (pre-tagged by Diego)
    3222: ("FLD-412", "ACC-1001", "pending"),  # copperline.com (pre-tagged by Diego)
    3233: ("FLD-412", "ACC-1001", "open"),     # copperline.com (same account as 3222)
    # FLD-398: 27500 (1006) + 18000 (1005) + 39000 (1017) + 24000 (1018) + 36000 (1004) = 144500, 5 accts
    3166: ("FLD-398", "ACC-1006", "solved"),   # harborhvac.com
    3177: ("FLD-398", "ACC-1005", "hold"),     # summitroofing.co (no org)
    3186: ("FLD-398", "ACC-1017", "solved"),   # cascadefire.com
    3200: ("FLD-398", "ACC-1018", "open"),     # oakridgepm.com (re-triaged from FLD-412)
    3236: ("FLD-398", "ACC-1004", "open"),     # brightline-electric.com
    # FLD-447: 48000 (1012) + 9600 (1007) + 66000 (1011) + 19800 (1020) + 15000 (1008) = 158400, 5 accts
    3204: ("FLD-447", "ACC-1012", "solved"),   # keystonesecurity.com
    3208: ("FLD-447", "ACC-1007", "open"),     # greenleaflandscape.com
    3210: ("FLD-447", "ACC-1011", "pending"),  # redwoodelevator.com
    3218: ("FLD-447", "ACC-1020", "hold"),     # vantageglass.com
    3230: ("FLD-447", "ACC-1008", "open"),     # pinecrestpest.com
    3241: ("FLD-447", "ACC-1011", "new"),      # redwoodelevator.com (same account as 3210)
}
BUGS = {  # key -> (issue id, ARR, distinct accounts, seed priority, expected priority)
    "FLD-412": ("i412", 287000, 5, "High", "Highest"),    # 287000 >= 150000
    "FLD-398": ("i398", 144500, 5, "High", "High"),       # 144500 < 150000, leave as is
    "FLD-447": ("i447", 158400, 5, "Medium", "Highest"),  # 158400 >= 150000
}
PRETAGGED = {3220, 3222}  # already carry fld-412 in the seed
HIDDEN = [3141, 3157, 3183, 3166, 3177, 3186, 3204, 3218]  # solved / hold targets
EXCLUDED = [3168, 3140, 3151, 3173, 3190, 3194, 3125, 3104, 3152, 3161, 3214, 3224,
            3144, 3213, 3226, 3234]
ME_SLACK, ME_JIRA = "U01", "ju1"
CHANNEL, THREAD = "support-escalations", "th_review"


def targets_of(key):
    return {t for t, (k, _, _) in TARGETS.items() if k == key}


def tags_of(ticket):
    return {str(x).strip().lower() for x in ticket.get("tags") or []}


# ------------------------------------------------------------------ text parsing
_AMOUNT = re.compile(r"(?<![\w.])\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?(k\b)?", re.I)


def amounts(text):
    """Integers in text: $287,000 / 287000 / $287k / 287.0K -> 287000."""
    found = []
    for whole, frac, k in _AMOUNT.findall(plain(text)):
        value = float(whole.replace(",", "") + ("." + frac if frac else ""))
        if k:
            value *= 1000
        found.append(int(round(value)))
    return found


def ticket_numbers(text):
    return {int(n) for n in re.findall(r"(?<![\w.$-])#?(\d{4})(?!\d)", plain(text))}


_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_ACCT_A = re.compile(r"\b(\d{1,3}|" + "|".join(_WORDNUM) + r")\s+(?:distinct\s+|unique\s+|different\s+|separate\s+)?"
                     r"(?:customer\s+)?(?:accounts?|customers)\b")
_ACCT_B = re.compile(r"\baccounts?\s*(?:affected|impacted)?\s*[:=]\s*(\d{1,3})\b")


def account_counts(text):
    body = plain(text)
    out = [int(n) if n.isdigit() else _WORDNUM[n] for n in _ACCT_A.findall(body)]
    out += [int(n) for n in _ACCT_B.findall(body)]
    return out


def evaluate(g):
    zd0, zd1 = load_site("zendesk")
    ji0, ji1 = load_site("jira")
    sl0, sl1 = load_site("slack")

    # ---- Zendesk -----------------------------------------------------------
    try:
        before = {int(t["id"]): t for t in zd0["tickets"]}
        after = {int(t["id"]): t for t in zd1["tickets"]}
    except (KeyError, TypeError, ValueError) as exc:
        raise InfraError(f"zendesk tickets unreadable: {exc}") from exc
    missing = set(before) - set(after)
    if missing or set(TARGETS) - set(before):
        raise InfraError(f"tickets missing from zendesk state: {sorted(missing | (set(TARGETS) - set(before)))}")

    def newly(tag):
        return {t for t in after if tag in tags_of(after[t]) and tag not in tags_of(before.get(t, {}))}

    seed_ids = set(before)
    correct_now = {t for t, (k, _, _) in TARGETS.items() if k.lower() in tags_of(after[t])}
    newly_correct = {t for t in correct_now if TARGETS[t][0].lower() not in tags_of(before[t])}
    # Restraint checks only earn credit in proportion to the real work done.
    cov = len(correct_now) / len(TARGETS) if newly_correct else 0.0

    for check_id, key in (("Z1.tag_fld412", "FLD-412"), ("Z2.tag_fld398", "FLD-398"), ("Z3.tag_fld447", "FLD-447")):
        tag, goal = key.lower(), targets_of(key)
        need = goal - PRETAGGED
        hits = {t for t in need if tag in tags_of(after[t])}
        wrong = newly(tag) - goal
        g.add(check_id, 11, max(0.0, (len(hits) - len(wrong)) / len(need)),
              f"tagged {sorted(hits)} of {sorted(need)}; wrongly tagged {sorted(wrong)}", core=True)

    hidden_ok = [t for t in HIDDEN if t in correct_now]
    g.add("Z4.hidden_targets", 8, len(hidden_ok) / len(HIDDEN),
          f"hidden solved/hold targets tagged: {hidden_ok}", core=True)

    bad = []
    for t in EXCLUDED:
        added = {x for x in tags_of(after[t]) - tags_of(before[t]) if x.startswith("fld-")}
        if added:
            bad.append(f"{t}+{sorted(added)}")
    if "fld-412" in tags_of(after[3200]):
        bad.append("3200 has fld-412")
    for t in PRETAGGED:
        if "fld-412" not in tags_of(after[t]):
            bad.append(f"{t} lost fld-412")
    g.add("Z5.no_tags_on_exclusions", 6, cov if not bad else 0.0, f"violations {bad}; cov={cov:.3f}")

    changed = []
    for t, old in before.items():
        new = after[t]
        diffs = [f for f in ("status", "group_id", "assignee_id", "priority") if old.get(f) != new.get(f)]
        if tags_of(old) - tags_of(new):
            diffs.append("tags removed")
        if diffs:
            changed.append(f"{t}:{','.join(diffs)}")
    g.add("Z6.no_other_ticket_changes", 3, cov if not changed else 0.0,
          f"changed tickets {changed[:10]}{'...' if len(changed) > 10 else ''}; cov={cov:.3f}")

    # ---- Jira --------------------------------------------------------------
    try:
        issues0 = {i["id"]: i for i in ji0["issues"]}
        issues1 = {i["id"]: i for i in ji1["issues"]}
    except (KeyError, TypeError) as exc:
        raise InfraError(f"jira issues unreadable: {exc}") from exc
    for iid in ["i412", "i398", "i447", "i431"]:
        if iid not in issues1 or iid not in issues0:
            raise InfraError(f"jira issue {iid} missing from state")
    added = new_items(ji0.get("comments"), ji1.get("comments"))
    mine = {}
    for c in added:
        if c.get("userId") == ME_JIRA:
            mine.setdefault(c.get("issueId"), []).append(str(c.get("content") or ""))

    commented = False
    for check_id, key in (("J1.comment_fld412", "FLD-412"), ("J2.comment_fld398", "FLD-398"),
                          ("J3.comment_fld447", "FLD-447")):
        iid, arr, n_acc, _, _ = BUGS[key]
        texts = mine.get(iid, [])
        if not texts:
            g.add(check_id, 9, 0.0, f"no new comment by Dana on {key}", core=True)
            continue
        commented = True
        body = " \n ".join(texts)
        goal = targets_of(key)
        nums = ticket_numbers(body)
        correct, wrong = nums & goal, (nums & seed_ids) - goal
        s_tickets = 0.4 * max(0.0, (len(correct) - len(wrong)) / len(goal))
        counts = account_counts(body)
        s_acc = 0.2 if counts and all(n == n_acc for n in counts) else 0.0
        s_arr = 0.4 if arr in amounts(body) else 0.0
        g.add(check_id, 9, s_tickets + s_acc + s_arr,
              f"tickets {sorted(correct)} wrong {sorted(wrong)}; account counts {counts} (want {n_acc}); "
              f"ARR {arr} {'found' if s_arr else 'missing'}", core=True)

    right = [k for k, (iid, _, _, _, want) in BUGS.items() if issues1[iid].get("priority") == want]
    g.add("J4.priorities", 9, len(right) / 3 if commented else 0.0,
          f"priorities {[(k, issues1[BUGS[k][0]].get('priority')) for k in BUGS]}; correct {right}; commented={commented}")

    i431_0, i431 = issues0["i431"], issues1["i431"]
    ok431 = (not mine.get("i431") and i431.get("priority") == i431_0.get("priority") == "Medium"
             and i431.get("status") == i431_0.get("status") == "Done")
    g.add("J5.fld431_untouched", 3, cov if (ok431 and commented) else 0.0,
          f"431 comments={len(mine.get('i431', []))} priority={i431.get('priority')} status={i431.get('status')}; "
          f"commented={commented}; cov={cov:.3f}")

    # ---- Slack -------------------------------------------------------------
    threads0, threads1 = sl0.get("threads") or {}, sl1.get("threads") or {}
    if THREAD not in threads0 or not isinstance(threads1, dict) or THREAD not in threads1:
        raise InfraError("slack thread th_review missing from state")
    old_ids = set(threads0[THREAD].get("replies") or [])
    for m in (sl0.get("messages") or {}).get(CHANNEL, []):
        old_ids.add(m.get("messageId"))
    reply_ids = [r if isinstance(r, str) else (r or {}).get("messageId") for r in threads1[THREAD].get("replies") or []]
    by_id = {}
    for msgs in (sl1.get("messages") or {}).values():
        for m in msgs or []:
            by_id[m.get("messageId")] = m
    for r in threads1[THREAD].get("replies") or []:
        if isinstance(r, dict):
            by_id.setdefault(r.get("messageId"), r)
    candidates = {rid for rid in reply_ids if rid not in old_ids}
    candidates |= {mid for mid, m in by_id.items() if m.get("threadId") == THREAD and mid not in old_ids}
    texts = [str(by_id[mid].get("content") or "") for mid in candidates
             if mid in by_id and by_id[mid].get("senderId") == ME_SLACK]
    found = []
    for key, (_, arr, _, _, _) in BUGS.items():
        others = {a for k, (_, a, _, _, _) in BUGS.items() if k != key}
        ok = False
        for raw in texts:
            body = plain(raw)
            # Segment rule: text from each "FLD-n" up to the next "FLD-n".
            parts = re.split(r"(?=\bfld-\d+)", body)
            if any(p.startswith(key.lower()) and arr in amounts(p) for p in parts):
                ok = True
            # Equivalent layout: one line / bullet naming the bug and its ARR only.
            for line in re.split(r"\n|<br\s*/?>|</p>|</li>|</div>", str(raw), flags=re.I):
                vals = set(amounts(line))
                if key.lower() in plain(line) and arr in vals and not (vals & others):
                    ok = True
        if ok:
            found.append(key)
    g.add("S1.slack_thread_reply", 4, len(found) / 3,
          f"{len(texts)} new thread reply(ies) by Dana; per-bug ARR reported for {found}")

    # ---- CSV ---------------------------------------------------------------
    rows = read_csv("escalation_review.csv")
    if rows is None:
        g.add("C1.review_csv", 7, 0.0, "escalation_review.csv missing", core=True)
    else:
        expected = {(str(t), k, a, s) for t, (k, a, s) in TARGETS.items()}
        matched = set()
        for r in rows:
            row = (re.sub(r"[#\s]", "", r.get("ticket_id", "")), r.get("jira_key", "").strip().upper(),
                   r.get("account_id", "").strip().upper(), r.get("status", "").strip().lower())
            if row in expected:
                matched.add(row)
        g.add("C1.review_csv", 7, len(matched) / max(len(TARGETS), len(rows)),
              f"{len(matched)}/{len(TARGETS)} expected rows present, {len(rows)} data rows", core=True)


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
