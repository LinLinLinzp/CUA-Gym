#!/usr/bin/env python3
"""Verifier for checkout-rounding-rollback. Checkpoints mirror rubric.json (G*, L*, S*, K*, O*).

Chain (derived independently from seeds + input):
  Sentry issue-3qk (CHECKOUT-API-3QK): tags/event release = checkout-api@4.31.0, environment = production
  -> input/deploys.csv row "2026-11-18T14:31:00Z,checkout-api,production,checkout-api@4.31.0,4be1c07a93d2..."
  -> GitHub r_api commit 4be1c07a... "Merge pull request #1287 from acme-commerce/tk/pay-412-line-rounding-v2"
  -> PR #1287 description "Closes PAY-412"
  -> Linear PAY-412 is Canceled, comment cm_412_3: "duplicate of PAY-431 ... Priya owns the re-land"
  -> PAY-431 (li_pay431, assignee lu_priya = Priya Natarajan): "rollback calls ... are made in #ledger-rollouts"
  -> Slack #ledger-rollouts thread th_pay431 (parent m_lr2): m_t2 (Priya) replaces the flag plan:
     open PR into main from the revert branch of the PR in the throwing release (#1287 ->
     revert-1287-line-rounding), add Priya as reviewer, leave unmerged, move PAY-431 back to
     In Progress, assign the Sentry issue to Priya, drop the PR number in this thread;
     m_t3 (Helen): leave the Sentry issue unresolved.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, new_items, plain, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/checkout-rounding-rollback", "0.1.0"

# ---- constants derived from the seeds / input --------------------------------
SENTRY_ISSUE_ID, SENTRY_SHORT = "issue-3qk", "CHECKOUT-API-3QK"
RELEASE = "checkout-api@4.31.0"                          # sentry issue-3qk tags.release / event.release
COMMIT_SHA = "4be1c07a93d2f1e86b0c5d7a2e49f310c8ab65d1"  # deploys.csv: checkout-api, production, 4.31.0
SOURCE_PR = 1287                                          # github commit 4be1c07a… "Merge pull request #1287"
REPO_ID = "r_api"                                         # acme-commerce/checkout-api
REVERT_BRANCH = "revert-1287-line-rounding"               # slack m_t2 (Priya) in th_pay431
BASE_BRANCH = "main"
GH_PRIYA = "gh_priya"                                     # github users: pnatarajan
LIN_PAY431, LIN_PAY412 = "li_pay431", "li_pay412"
TICKET = "PAY-431"                                        # PAY-412 cm_412_3: duplicate of PAY-431
WS_IN_PROGRESS = "ws_pay_in_progress"                     # linear team t1 (PAY) "In Progress"
PAY412_STATE, PAY412_ASSIGNEE = "ws_pay_canceled", "lu_tomasz"  # seed values of li_pay412
LU_SAM = "lu_sam"                                         # linear currentUserId
SU_PRIYA = "su_priya"                                     # sentry users: Priya Natarajan
OWNER = "Priya Natarajan"                                 # li_pay431.assigneeId = lu_priya
SLACK_SAM = "U_SAM"
LR_CHANNEL, THREAD = "ledger-rollouts", "th_pay431"       # thread parent m_lr2 (pinned PAY-431 rollout note)
DECOY_CHANNEL = "payments"                                # old PAY-412 / 4.30.0 thread th_pay412

TICKET_RE = re.compile(r"(?<![\w-])pay-431(?!\d)")


def has_n(text, n):
    return n is not None and re.search(rf"(?<!\d){n}(?!\d)", plain(text)) is not None


def as_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip().lstrip("#").strip()
        return int(s) if re.fullmatch(r"\d+", s) else None
    return None


def branch_name(value):
    """'acme-commerce:revert-…' or 'refs/heads/revert-…' -> 'revert-…'."""
    s = str(value or "").strip()
    s = s.split(":")[-1]
    return s[len("refs/heads/"):] if s.startswith("refs/heads/") else s


def reviewer_ids(pr):
    out = set()
    for r in pr.get("reviewers") or []:
        out.add(r.get("userId") if isinstance(r, dict) else r)
    return out


def comment_text(c):
    if not isinstance(c, dict):
        return str(c)
    return " ".join(str(c.get(k) or "") for k in ("text", "body", "content", "message"))


def evaluate(g):
    sen0, sen1 = load_site("sentry")
    gh0, gh1 = load_site("github")
    lin0, lin1 = load_site("linear")
    sl0, sl1 = load_site("slack")

    def by_id(items, key="id"):
        return {i.get(key): i for i in items or [] if isinstance(i, dict)}

    sen_issue = by_id(sen1.get("issues")).get(SENTRY_ISSUE_ID)
    lin_issues = by_id(lin1.get("issues"))
    if sen_issue is None:
        raise InfraError(f"sentry {SENTRY_ISSUE_ID} missing from final state")
    for lid in (LIN_PAY431, LIN_PAY412):
        if lid not in lin_issues:
            raise InfraError(f"linear {lid} missing from final state")
    if THREAD not in (sl1.get("threads") or {}):
        raise InfraError(f"slack thread {THREAD} missing from final state")

    # ---- GitHub ---------------------------------------------------------------
    prs0, prs1 = gh0.get("pullRequests") or [], gh1.get("pullRequests") or []
    new_prs = new_items(prs0, prs1)
    candidates = [p for p in new_prs if p.get("repoId") == REPO_ID
                  and branch_name(p.get("compareBranch")) == REVERT_BRANCH
                  and branch_name(p.get("baseBranch")) == BASE_BRANCH]
    # If several exist, take the one that best follows the plan (open, Priya reviewing).
    candidates.sort(key=lambda p: (p.get("status") == "open", GH_PRIYA in reviewer_ids(p)), reverse=True)
    pr = candidates[0] if candidates else None
    n = as_int(pr.get("number")) if pr else None
    if pr is not None and n is None:
        raise InfraError(f"new PR {pr.get('id')} has no usable number: {pr.get('number')!r}")
    others = [(p.get("repoId"), p.get("number"), branch_name(p.get("compareBranch"))) for p in new_prs]

    g.add("G1.revert_pr_branch", 13, pr is not None,
          f"revert PR #{n} from {REVERT_BRANCH}" if pr else f"no new {REVERT_BRANCH}->main PR in r_api; new PRs: {others}",
          core=True)
    g.add("G2.reviewer_owner", 8, pr is not None and GH_PRIYA in reviewer_ids(pr),
          f"reviewers={sorted(map(str, reviewer_ids(pr)))}" if pr else "no revert PR")
    g.add("G3.revert_unmerged", 6, pr is not None and pr.get("status") == "open",
          f"status={pr.get('status')}" if pr else "no revert PR")
    cur_by_id = by_id(prs1)
    altered = [p.get("number") for p in prs0 if cur_by_id.get(p.get("id")) != p]
    g4 = pr is not None and len(new_prs) == 1 and not altered
    g.add("G4.no_other_pr_changes", 4, g4,
          f"new PRs={others}; altered existing PRs={altered}" + ("" if pr else " (no revert PR, not scored)"))

    # ---- Linear ---------------------------------------------------------------
    p431, p412 = lin_issues[LIN_PAY431], lin_issues[LIN_PAY412]
    l1 = p431.get("stateId") == WS_IN_PROGRESS
    g.add("L1.pay431_in_progress", 6, l1, f"PAY-431 stateId={p431.get('stateId')}")
    lin_new = new_items(lin0.get("comments"), lin1.get("comments"))
    c431 = [c for c in lin_new if c.get("issueId") == LIN_PAY431 and c.get("userId") == LU_SAM]
    l2 = any(has_n(c.get("body"), n) for c in c431)
    g.add("L2.pay431_comment_pr", 10, l2,
          f"{len(c431)} new PAY-431 comment(s) by Sam; PR number N={n}", core=True)
    c412 = [c for c in lin_new if c.get("issueId") == LIN_PAY412]
    l3_ok = (p412.get("stateId") == PAY412_STATE and p412.get("assigneeId") == PAY412_ASSIGNEE and not c412)
    g.add("L3.pay412_untouched", 3, (l1 or l2) and l3_ok,
          f"PAY-412 state={p412.get('stateId')} assignee={p412.get('assigneeId')} new comments={len(c412)}"
          + ("" if (l1 or l2) else " (no PAY-431 work, not scored)"))

    # ---- Sentry ---------------------------------------------------------------
    s1 = sen_issue.get("assignee") == SU_PRIYA
    g.add("S1.sentry_assign_owner", 5, s1, f"assignee={sen_issue.get('assignee')}")
    sc0 = (sen0.get("comments") or {}).get(SENTRY_ISSUE_ID) or []
    sc1 = (sen1.get("comments") or {}).get(SENTRY_ISSUE_ID) or []
    s_new = new_items(sc0, sc1)
    s2 = max([0.5 * bool(TICKET_RE.search(plain(comment_text(c)))) + 0.5 * has_n(comment_text(c), n)
              for c in s_new] or [0.0])
    g.add("S2.sentry_comment", 9, s2, f"{len(s_new)} new comment(s); best has PAY-431/N={n} -> {s2}")
    g.add("S3.sentry_unresolved", 6, (s1 or s2 > 0) and sen_issue.get("status") == "unresolved",
          f"status={sen_issue.get('status')}" + ("" if (s1 or s2 > 0) else " (no Sentry work, not scored)"))

    # ---- Slack ----------------------------------------------------------------
    msgs0, msgs1 = sl0.get("messages") or {}, sl1.get("messages") or {}
    lr_new = [m for m in new_items(msgs0.get(LR_CHANNEL), msgs1.get(LR_CHANNEL), key="messageId")
              if m.get("senderId") == SLACK_SAM]
    # Thread replies are identified by threadId, or by being listed in threads[th_pay431].replies.
    old_replies = set((sl0.get("threads") or {}).get(THREAD, {}).get("replies") or [])
    new_reply_ids = set((sl1.get("threads") or {}).get(THREAD, {}).get("replies") or []) - old_replies
    k1 = 0.0
    for m in lr_new:
        in_thread = m.get("threadId") == THREAD or m.get("messageId") in new_reply_ids
        if in_thread:
            k1 = max(k1, 1.0 if has_n(m.get("content"), n) else 0.25)
        elif not m.get("threadId") and has_n(m.get("content"), n):
            k1 = max(k1, 0.5)
    g.add("K1.thread_reply_pr", 12, k1,
          f"{len(lr_new)} new #ledger-rollouts message(s) by Sam; N={n}", core=True)
    pay_new = [m for m in new_items(msgs0.get(DECOY_CHANNEL), msgs1.get(DECOY_CHANNEL), key="messageId")
               if m.get("senderId") == SLACK_SAM]
    g.add("K2.no_payments_post", 2, k1 > 0 and not pay_new,
          f"{len(pay_new)} new #payments message(s) by Sam" + ("" if k1 > 0 else " (no thread reply, not scored)"))

    # ---- Output JSON ----------------------------------------------------------
    path = OUTPUT_DIR / "incident_trace.json"
    data = None
    if path.is_file() and not path.is_symlink():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = None
    if not isinstance(data, dict):
        why = "incident_trace.json missing or not a JSON object"
        for cid, w in (("O1.output_issue_release", 2), ("O2.output_commit_pr", 8),
                       ("O3.output_ticket_owner", 3), ("O4.output_followup_pr", 3)):
            g.add(cid, w, 0, why, core=cid.startswith("O2"))
        return

    def s(key):
        v = data.get(key)
        return v.strip() if isinstance(v, str) else ""

    o1 = s("sentry_issue").upper() == SENTRY_SHORT and s("release").lower() == RELEASE
    g.add("O1.output_issue_release", 2, o1, f"sentry_issue={data.get('sentry_issue')!r} release={data.get('release')!r}")
    o2 = 0.5 * (re.sub(r"\s+", "", s("commit_sha")).lower() == COMMIT_SHA) + 0.5 * (as_int(data.get("pull_request")) == SOURCE_PR)
    g.add("O2.output_commit_pr", 8, o2, f"commit_sha={data.get('commit_sha')!r} pull_request={data.get('pull_request')!r}",
          core=True)
    o3 = 0.5 * (s("linear_ticket").upper() == TICKET) + 0.5 * (" ".join(s("owner").split()).lower() == OWNER.lower())
    g.add("O3.output_ticket_owner", 3, o3, f"linear_ticket={data.get('linear_ticket')!r} owner={data.get('owner')!r}")
    o4 = n is not None and as_int(data.get("followup_pr")) == n
    g.add("O4.output_followup_pr", 3, o4, f"followup_pr={data.get('followup_pr')!r}; N={n}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
