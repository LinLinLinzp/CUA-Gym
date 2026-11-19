#!/usr/bin/env python3
"""Verifier for hotfix-release-followups. Checkpoints mirror rubric.json (K1-K6 core, S1-S8).

All expected values are derived from the seeds / input and hard-coded below with their source.
Dynamic (L14) follow-up messages are injected into Slack #checkout-release by the world with fixed
messageIds; the K* checks only score when the matching trigger message is present.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, new_items, plain, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/hotfix-release-followups", "0.1.0"

# ---------------------------------------------------------------- derived constants
# Jira issue ids (seed/jira.json): CHK-412=i7, CHK-415=i9, CHK-417=i11, CHK-419=i13,
# CHK-421=i15, CHK-423=i17, CHK-430=i23 (release ticket).
GRADED_KEYS = ["CHK-412", "CHK-415", "CHK-417", "CHK-419", "CHK-421", "CHK-423", "CHK-430"]
# Shipped: CHK-417 (!9, already merged + QA pass in c6), CHK-412 (!10, green #4828),
# CHK-423 (!15, green #4830, added by Lena in th_scope r1_t1).
SHIPPED = {"CHK-412", "CHK-417", "CHK-423"}
# Must not appear as shipped: CHK-415 (QA FAIL via trg_qa_415), CHK-419 (latest #4831 failed),
# CHK-421 (!14 is 4.13 work per r1_t2/r1_t3 and c8).
NOT_SHIPPED = {"CHK-415", "CHK-419", "CHK-421"}
# checkout-web (projectId 1) MRs touched by the task; all of !10-!15 are "open" in the seed.
MR_IDS = [9, 10, 11, 12, 13, 14, 15]
HOTFIX_MRS = [10, 12, 13, 15]  # open seed MRs into release/4.12 for in-scope tickets
# Manifest: one row per in-scope ticket (hotfix-4.12.1 labels in seed + CHK-423 from the thread).
MANIFEST = {
    "CHK-412": ("10", "shipped"),
    "CHK-415": ("12", "deferred"),
    "CHK-417": ("9", "shipped"),
    "CHK-419": ("13", "deferred"),
    "CHK-423": ("15", "shipped"),
}
# deploy_history.csv: production checkout-web currently runs the 11/14 21:15 rebuild of v4.12.0
# (the 11/17 22:10 deploy was rolled_back "to previous image" = 11/14; c10 on CHK-427 confirms).
ROLLBACK_TARGET = "39102015d9c2db847807f6c657ee45435e9fb503303b6d0acc5186515b8eee08"
WRONG_DIGESTS = [
    "49b94c684d8d136bb7fcedd05c608e9fe6c2a72b007325d9501db100a3d2158a",  # v4.12.0 11/10 first build
    "ebf3197126fb85eeb2ed4766f28834dfdf720e0e4d3601aac8aa152d5033f5b7",  # v4.12.0 11/17 rolled back
    "85faf56da334182dc7704588ed351e4d189d253f6e8150c5b9799dfe7a1377d7",  # v4.11.3 (old runbook section)
    "690861110013fef98450714c6d12a3721d038704bb637c84629b6aa7bfe2f9df",  # v4.11.2
    "847e580bf713c50c8e77b72ae8642b34de36b3e29d1d4240e80ed97c9a63bb44",  # staging release/4.12 build
    "a8a6c47417dcdb1c2bd84ef5a5fd16ed399ff9edb53c83ce8f6bc4fc3b07ae05",  # staging v4.13.0-rc.1
]
FLAG = "klarna_redirect_v2"  # MR !15 description + Feature flags wiki; requested by Ines (trg_ines_flag)
SEED_430_SUBTASKS = {"st_430_1", "st_430_2", "st_430_3", "st_430_4"}
TRIGGERS = ["trg_qa_412", "trg_qa_415", "trg_qa_423", "trg_ines_flag", "trg_sam_rollback", "trg_sam_approve"]
KEY_RE = re.compile(r"chk-\d+", re.I)
HEX_RE = re.compile(r"[0-9a-f]{12,}")


# ---------------------------------------------------------------- helpers
def keys_in(text):
    return {k.upper() for k in KEY_RE.findall(str(text or ""))}


def parse_ts(value):
    """Slack timestamps: ISO (Z / offset / ms) or epoch seconds/ms. None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)) or re.fullmatch(r"\d+(\.\d+)?", str(value).strip()):
        num = float(value)
        if num > 1e11:
            num /= 1000.0
        return datetime.fromtimestamp(num, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def digest_hits(text, digest):
    """Full sha256:<hex> or any >=12-char prefix of the hex (case-insensitive)."""
    return any(digest.startswith(run_) for run_ in HEX_RE.findall(str(text or "").lower()))


def labels(issue):
    return {str(l).strip().lower() for l in issue.get("labels") or []}


def has_label(issue, label):
    return label in labels(issue)


def evaluate(g):
    jira0, jira1 = load_site("jira")
    gl0, gl1 = load_site("gitlab")
    sl0, sl1 = load_site("slack")

    # ---- integrity ----------------------------------------------------------
    try:
        issues0 = {i["key"].upper(): i for i in jira0["issues"]}
        issues1 = {i.get("key", "").upper(): i for i in jira1["issues"]}
        mrs0 = {m["id"]: m for m in gl0["mergeRequests"] if m.get("projectId") == 1}
        mrs1 = {m.get("id"): m for m in gl1["mergeRequests"] if m.get("projectId") == 1}
        msgs1 = sl1["messages"]
        msgs0 = sl0["messages"]
    except (KeyError, TypeError, AttributeError) as exc:
        raise InfraError(f"state missing expected collections: {exc}") from exc
    missing = [k for k in GRADED_KEYS if k not in issues1] + [f"!{m}" for m in MR_IDS if m not in mrs1]
    if missing:
        raise InfraError(f"tickets/MRs missing from final state: {missing}")

    def mr_status(mid):
        return str(mrs1[mid].get("status", "")).lower()

    def merged_now(mid):
        return mr_status(mid) == "merged" and str(mrs0[mid].get("status", "")).lower() != "merged"

    def status(key):
        return str(issues1[key].get("status", ""))

    # ---- Slack triggers ---------------------------------------------------
    release_msgs = list(msgs1.get("checkout-release") or [])
    trig = {}
    for m in release_msgs:
        if m.get("messageId") in TRIGGERS:
            trig[m["messageId"]] = m
    # Tolerate a trigger landing in another list (e.g. stored per thread) - same fixed id.
    for lst in msgs1.values():
        for m in lst or []:
            if m.get("messageId") in TRIGGERS and m["messageId"] not in trig:
                trig[m["messageId"]] = m
    present = set(trig)

    # ---- K1: QA fail on CHK-415 ---------------------------------------------
    i415 = issues1["CHK-415"]
    if "trg_qa_415" in present:
        k1 = 0.6 * (mr_status(12) == "open")
        k1 += 0.4 * (status("CHK-415") == "In Progress" and has_label(i415, "hotfix-4.12.2")
                     and not has_label(i415, "hotfix-4.12.1"))
        d1 = f"!12={mr_status(12)}; CHK-415 {status('CHK-415')} labels={sorted(labels(i415))}"
    else:
        k1, d1 = 0.0, "trg_qa_415 never fired (CHK-415 never moved to In Review)"
    g.add("K1.qa_fail_415", 14, k1, d1, core=True)

    # ---- K2: merges gated on QA ---------------------------------------------
    k2 = 0.5 * (mr_status(10) == "merged" and "trg_qa_412" in present)
    k2 += 0.5 * (mr_status(15) == "merged" and "trg_qa_423" in present)
    g.add("K2.qa_gate_merges", 6, k2,
          f"!10={mr_status(10)} qa412={'trg_qa_412' in present}; !15={mr_status(15)} qa423={'trg_qa_423' in present}",
          core=True)

    # ---- K3: flag step on CHK-430 -------------------------------------------
    i430_0, i430 = issues0["CHK-430"], issues1["CHK-430"]
    if "trg_ines_flag" in present:
        new_steps = [s for s in i430.get("subtasks") or [] if s.get("id") not in SEED_430_SUBTASKS]
        step_ok = any(FLAG in plain(s.get("title")) for s in new_steps)
        new_comments = [c for c in new_items(jira0.get("comments"), jira1.get("comments"))
                        if c.get("issueId") == i430.get("id") and c.get("userId") == "u1"]
        comment_ok = any(FLAG in plain(c.get("content")) for c in new_comments)
        desc_ok = FLAG in plain(i430.get("description")) and FLAG not in plain(i430_0.get("description"))
        k3 = 1.0 if step_ok else 0.5 if (comment_ok or desc_ok) else 0.0
        d3 = f"new subtasks={[s.get('title') for s in new_steps]}; flag in comment={comment_ok} desc={desc_ok}"
    else:
        k3, d3 = 0.0, "trg_ines_flag never fired (!15 not merged)"
    g.add("K3.flag_step", 10, k3, d3, core=True)

    # ---- K4/K5: rollback runbook section ------------------------------------
    def runbook_lines(state):
        out = []
        for page in state.get("wiki") or []:
            if page.get("projectId") == 1 and str(page.get("title", "")).strip().lower() == "rollback runbook":
                out += str(page.get("content") or "").splitlines()
        return out

    seed_lines = {l.strip() for l in runbook_lines(gl0)}
    added = [l for l in runbook_lines(gl1) if l.strip() and l.strip() not in seed_lines]
    # Tolerance: a brand-new project-1 wiki page about rollback also counts as added content.
    seed_wiki_ids = {p.get("id") for p in gl0.get("wiki") or []}
    for page in gl1.get("wiki") or []:
        if (page.get("id") not in seed_wiki_ids and page.get("projectId") == 1
                and "rollback" in str(page.get("title", "")).lower()):
            added += str(page.get("content") or "").splitlines()
    added_text = "\n".join(added)

    if "trg_sam_rollback" in present:
        has_ver = "4.12.1" in added_text
        hit = digest_hits(added_text, ROLLBACK_TARGET)
        wrong = [d[:12] for d in WRONG_DIGESTS if digest_hits(added_text, d)]
        k4 = (1.0 if hit else 0.3) if has_ver else 0.0
        if wrong:
            k4 = min(k4, 0.3)
        d4 = f"{len(added)} new runbook line(s); mentions 4.12.1={has_ver} target={hit} wrong={wrong}"
        k5 = 1.0 if FLAG in added_text.lower() else 0.0
        d5 = f"{FLAG} in new runbook content={bool(k5)}"
    else:
        k4 = k5 = 0.0
        d4 = d5 = "trg_sam_rollback never fired (no v4.12.1 release)"
    g.add("K4.rollback_section", 12, k4, d4, core=True)
    g.add("K5.rollback_flag", 6, k5, d5, core=True)

    # ---- announcements in #releases -----------------------------------------
    posts = [m for m in new_items(msgs0.get("releases"), msgs1.get("releases"), key="messageId")
             if m.get("senderId") == "U01" and "4.12.1" in plain(m.get("content"))]

    # ---- K6: announce after approval ----------------------------------------
    if "trg_sam_approve" in present:
        approve_at = parse_ts(trig["trg_sam_approve"].get("timestamp"))
        if approve_at is None:
            raise InfraError("trg_sam_approve has no parseable timestamp")
        times = [parse_ts(p.get("timestamp")) for p in posts]
        after = sum(1 for t in times if t is not None and t > approve_at)
        before = sum(1 for t in times if t is None or t <= approve_at)
        k6 = (0.5 if before else 1.0) if after else 0.0
        d6 = f"{after} announcement(s) after approval, {before} before"
    else:
        k6, d6 = 0.0, f"trg_sam_approve never fired; {len(posts)} announcement(s)"
    g.add("K6.announce_after_approval", 8, k6, d6, core=True)

    # ---- S1: merge !10 only ---------------------------------------------------
    s1 = (1.0 if mr_status(10) == "merged" else 0.0) * (0.5 if merged_now(11) else 1.0)
    g.add("S1.merge_412", 6, s1, f"!10={mr_status(10)} !11={mr_status(11)}")

    # ---- S2: CHK-423 in scope -------------------------------------------------
    i423 = issues1["CHK-423"]
    s2 = 0.5 * has_label(i423, "hotfix-4.12.1") + 0.5 * (mr_status(15) == "merged")
    g.add("S2.scope_423", 6, s2, f"CHK-423 labels={sorted(labels(i423))} !15={mr_status(15)}")

    # ---- S3/S4: must-not checks, gated on real merge work -------------------
    worked = any(merged_now(m) for m in HOTFIX_MRS)
    i419 = issues1["CHK-419"]
    if worked:
        s3 = 0.4 * (mr_status(13) == "open")
        s3 += 0.4 * (has_label(i419, "hotfix-4.12.2") and not has_label(i419, "hotfix-4.12.1"))
        s3 += 0.2 * (status("CHK-419") != "Done")
        i421_0, i421 = issues0["CHK-421"], issues1["CHK-421"]
        s4 = ((mr_status(14) == "open") + (mr_status(11) == "open")
              + (i421.get("status") == i421_0.get("status") and labels(i421) == labels(i421_0))) / 3
    else:
        s3 = s4 = 0.0
    g.add("S3.defer_419", 5, s3,
          f"gate={worked}; !13={mr_status(13)} CHK-419 {status('CHK-419')} labels={sorted(labels(i419))}")
    g.add("S4.non_targets", 3, s4,
          f"gate={worked}; !14={mr_status(14)} !11={mr_status(11)} CHK-421 {status('CHK-421')} "
          f"labels={sorted(labels(issues1['CHK-421']))}")

    # ---- S5: GitLab release --------------------------------------------------
    rels = [r for r in new_items(gl0.get("releases"), gl1.get("releases"))
            if r.get("projectId") == 1 and str(r.get("tagName", "")).strip().lower() == "v4.12.1"]
    if len(rels) == 1:
        found = keys_in(rels[0].get("description"))
        s5 = len(found & SHIPPED) / 3 * (0.5 if found & NOT_SHIPPED else 1.0)
        d5 = f"release description keys={sorted(found)}"
    else:
        s5, d5 = 0.0, f"{len(rels)} new v4.12.1 release(s) in checkout-web (need exactly 1)"
    g.add("S5.release", 7, s5, d5)

    # ---- S6: Jira Done -------------------------------------------------------
    done = [k for k in GRADED_KEYS if status(k) == "Done"]
    s6 = 0.25 * len(set(done) & {"CHK-412", "CHK-417", "CHK-423", "CHK-430"}) \
        - 0.25 * len(set(done) & {"CHK-415", "CHK-419"})
    g.add("S6.jira_done", 5, max(0.0, s6), f"Done: {done}")

    # ---- S7: announcement content -------------------------------------------
    if posts:
        def sort_key(item):
            idx, p = item
            t = parse_ts(p.get("timestamp"))
            return (t or datetime.min.replace(tzinfo=timezone.utc), idx)
        last = max(enumerate(posts), key=sort_key)[1]
        found = keys_in(last.get("content"))
        s7 = len(found & SHIPPED) / 3 * (0.5 if found & NOT_SHIPPED else 1.0)
        d7 = f"last announcement keys={sorted(found)}"
    else:
        s7, d7 = 0.0, "no new 4.12.1 announcement by Dana in #releases"
    g.add("S7.announcement_content", 5, s7, d7)

    # ---- S8: manifest --------------------------------------------------------
    rows = read_csv("release_manifest.csv")
    if rows is None:
        g.add("S8.manifest", 7, 0, "release_manifest.csv missing")
    elif not rows or not {"ticket", "merge_request", "decision"} <= set(rows[0]):
        g.add("S8.manifest", 7, 0, f"bad header or empty: {sorted(rows[0]) if rows else []}")
    else:
        correct = 0
        for ticket, (mr, decision) in MANIFEST.items():
            match = [r for r in rows if r.get("ticket", "").strip().upper() == ticket]
            if len(match) == 1:
                r = match[0]
                mr_ok = re.fullmatch(r"!?\s*0*" + mr, r.get("merge_request", "").strip()) is not None
                if mr_ok and r.get("decision", "").strip().lower() == decision:
                    correct += 1
        g.add("S8.manifest", 7, correct / max(len(MANIFEST), len(rows)),
              f"{correct}/{len(MANIFEST)} rows right, {len(rows)} data rows")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
