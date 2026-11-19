#!/usr/bin/env python3
"""World for exp1-l14 / cua-hard/hotfix-release-followups (Jira + GitLab + Slack + local CSV).

Writes into <out>/:
  seed/{jira,gitlab,slack}.json        initial state per site
  triggers.json                        reactive world (lever L14), fired by sitehost
  golden/{jira,gitlab,slack}.json      state after a correct run (incl. fired trigger records)
  golden_output/release_manifest.csv   correct CLI deliverable
  input/deploy_history.csv             agent-visible workspace input
  expected.json                        hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/}   self-check fixtures

Story: Dana Whitfield, release manager at Brightloop, hands hotfix 4.12.1 of
checkout-web to the agent. Scope = CHK tickets labelled hotfix-4.12.1 plus the
addition in Lena's Slack thread (CHK-423). Process: green latest pipeline ->
move ticket to In Review -> Marta (QA) posts a verdict in #checkout-release ->
merge only what passed. The world reacts:
  * Marta's verdicts arrive after each In Review transition (CHK-415 FAILS).
  * Merging the Klarna MR (!15) makes Ines ask for a klarna_redirect_v2 step on CHK-430
    and for the rollback plan to switch the flag off.
  * Creating release v4.12.1 makes Sam (SRE) ask for a 4.12.1 rollback section on the
    wiki page "Rollback runbook" with the tag + digest running in prod right now
    (only derivable from /workspace/input/deploy_history.csv).
  * A 4.12.1 section on that page makes Sam approve; the #releases announcement
    must come after the approval.
"""

import copy
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T09:30:00-05:00"  # 14:30Z


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


DIG = {
    "v4.11.2": digest("checkout-web v4.11.2 2026-10-14"),
    "v4.11.3": digest("checkout-web v4.11.3 2026-10-28"),
    "v4.12.0_nov10": digest("checkout-web v4.12.0 2026-11-10"),
    "v4.12.0_nov14": digest("checkout-web v4.12.0 rebuild 2026-11-14 openssl"),
    "v4.12.0_nov17": digest("checkout-web v4.12.0 node22.11 2026-11-17"),
    "v4.13.0-rc.1": digest("checkout-web v4.13.0-rc.1 2026-11-13"),
    "release-4.12": digest("checkout-web release/4.12 1e6a9c0 staging"),
}
ROLLBACK_TARGET = ("v4.12.0", DIG["v4.12.0_nov14"])
WRONG_DIGESTS = [DIG["v4.12.0_nov10"], DIG["v4.12.0_nov17"], DIG["v4.13.0-rc.1"], DIG["v4.11.3"], DIG["release-4.12"]]

# ======================================================================== JIRA
J_USERS = [
    ("u1", "Dana Whitfield", "dana.whitfield@brightloop.io"),
    ("u2", "Marta Kowalski", "marta.kowalski@brightloop.io"),
    ("u3", "Ravi Menon", "ravi.menon@brightloop.io"),
    ("u4", "Theo Grant", "theo.grant@brightloop.io"),
    ("u5", "Ines Duarte", "ines.duarte@brightloop.io"),
    ("u6", "Lena Fischer", "lena.fischer@brightloop.io"),
    ("u7", "Sam Okafor", "sam.okafor@brightloop.io"),
]

# key, type, status, priority, points, summary, assignee, sprint, labels, created, description
J_ISSUES = [
    ("CHK-399", "Story", "Done", "Medium", 5, "Move address autocomplete to Places API v2", "u3", "s3", ["address"], "2026-10-21T15:00:00.000Z",
     "Places API v1 is deprecated in January. Swap the autocomplete widget to v2 behind new_address_autocomplete."),
    ("CHK-402", "Bug", "Done", "High", 2, "Apple Pay sheet shows USD for CAD carts on iOS 17", "u3", "s3", ["apple-pay", "hotfix-4.12.0"], "2026-11-03T16:20:00.000Z",
     "iOS 17 only: the Apple Pay sheet ignores the cart currency when the merchant country is US. Shipped in 4.12.0."),
    ("CHK-405", "Story", "In Progress", "Medium", 8, "Order summary card redesign", "u3", "s1", ["design"], "2026-11-06T14:00:00.000Z",
     "New order summary card per the Figma file (Checkout / Summary v3). Behind order_summary_v3."),
    ("CHK-406", "Task", "To Do", "Medium", 3, "Add Datadog monitors for checkout latency p95", "u7", "s1", ["observability"], "2026-11-06T14:30:00.000Z",
     "Alert when /checkout/confirm p95 exceeds 1.2s for 10 minutes."),
    ("CHK-408", "Story", "To Do", "Low", 3, "Saved addresses: allow a nickname", "u4", "s2", ["address"], "2026-11-07T10:00:00.000Z",
     "Let shoppers label saved addresses (Home, Office...)."),
    ("CHK-410", "Bug", "In Progress", "High", 3, "Webhook deliveries are not retried after a 5xx", "u5", "s1", ["webhooks"], "2026-11-09T18:00:00.000Z",
     "Merchant webhooks get dropped when the receiver returns 502. Add exponential backoff, max 6 attempts. Targets 4.13."),
    ("CHK-412", "Bug", "In Progress", "Highest", 3, "Apple Pay sheet shows USD instead of CAD for Canadian carts", "u3", "s1", ["hotfix-4.12.1", "apple-pay"], "2026-11-14T15:40:00.000Z",
     "Since 4.12.0 the Apple Pay payment request takes the merchant default currency instead of the cart currency. Canadian shoppers see USD on the sheet and are charged in USD."),
    ("CHK-413", "Task", "Done", "Medium", 1, "Rotate Adyen API credentials", "u7", "s1", ["security"], "2026-11-10T09:00:00.000Z",
     "Quarterly rotation. Done 11/12."),
    ("CHK-415", "Bug", "In Progress", "High", 2, "Expired promo codes are still accepted at checkout", "u4", "s1", ["hotfix-4.12.1", "promotions"], "2026-11-14T17:05:00.000Z",
     "Codes past their end date apply a discount at the payment step. Support has 14 tickets from the SPRING25 campaign."),
    ("CHK-416", "Story", "To Do", "Medium", 5, "One-click reorder from order history", "u3", "s2", ["orders"], "2026-11-11T13:00:00.000Z",
     "Add a Reorder button on past orders that rebuilds the cart."),
    ("CHK-417", "Bug", "In Review", "High", 2, "Order confirmation email is sent twice", "u5", "s1", ["hotfix-4.12.1", "email"], "2026-11-15T12:10:00.000Z",
     "The confirmation job is enqueued by both the payment webhook and the redirect handler."),
    ("CHK-418", "Bug", "To Do", "Medium", 2, "Postal code validation rejects Irish Eircodes", "u4", "s1", ["address"], "2026-11-12T11:00:00.000Z",
     "Eircodes like D02 X285 fail the regex."),
    ("CHK-419", "Bug", "In Progress", "High", 3, "Saved cards disappear after a 3DS challenge", "u4", "s1", ["hotfix-4.12.1", "3ds"], "2026-11-15T16:45:00.000Z",
     "After completing a 3DS challenge the saved cards list renders empty until reload."),
    ("CHK-420", "Story", "In Review", "Medium", 5, "Show estimated delivery date on the review step", "u5", "s1", ["shipping"], "2026-11-08T15:00:00.000Z",
     "Pull the carrier ETA into the review step. 4.13."),
    ("CHK-421", "Task", "In Progress", "Medium", 3, "Round JPY tax lines half-up", "u4", "s1", ["tax", "4.13"], "2026-11-13T10:30:00.000Z",
     "Finance wants half-up rounding on JPY tax lines together with the 4.13 invoicing changes."),
    ("CHK-422", "Bug", "Done", "Low", 1, "Apple Pay button misaligned on Safari 18", "u3", "s1", ["apple-pay"], "2026-11-10T12:00:00.000Z",
     "2px offset on the express checkout row."),
    ("CHK-423", "Bug", "In Progress", "Highest", 2, "Klarna checkout loops back to the payment step after redirect", "u3", "s1", ["klarna", "payments"], "2026-11-17T20:40:00.000Z",
     "When Klarna returns with an encoded return URL the redirect handler sends the shopper back to the payment step. Fernway Outdoor cannot take Klarna payments at all."),
    ("CHK-424", "Story", "To Do", "Low", 2, "Klarna: show pay-in-4 messaging on cart", "u3", "s2", ["klarna"], "2026-11-12T09:00:00.000Z",
     "Marketing request: show the Klarna pay-in-4 placement on the cart page."),
    ("CHK-425", "Task", "In Progress", "Low", 2, "Lazy-load payment method icons", "u3", "s1", ["performance"], "2026-11-13T14:00:00.000Z",
     "Saves ~40KB on first paint."),
    ("CHK-426", "Bug", "To Do", "Medium", 1, "Gift card balance shows 3 decimals for KWD", "u4", "s1", ["hotfix-4.12.2", "gift-cards"], "2026-11-17T13:00:00.000Z",
     "Queued for the next hotfix by Lena."),
    ("CHK-427", "Task", "To Do", "Medium", 2, "Post-mortem: 11/17 base image rollback", "u7", "s1", ["incident"], "2026-11-17T23:00:00.000Z",
     "Write up the failed node 22.11 base image deploy and the automatic rollback."),
    ("CHK-428", "Story", "To Do", "Medium", 5, "Promo codes: per-customer usage limit", "u4", "s2", ["promotions"], "2026-11-14T10:00:00.000Z",
     "Allow one use per customer for campaign codes."),
    ("CHK-430", "Task", "In Progress", "High", 1, "Release 4.12.1 (hotfix)", "u1", "s1", ["release"], "2026-11-17T22:55:00.000Z",
     "Release ticket for checkout-web 4.12.1. Scope: CHK tickets labelled hotfix-4.12.1, see the scope thread in #checkout-release. Deploy window Wed 11/18 11:00-15:00 ET (Sam)."),
    ("CHK-431", "Bug", "To Do", "Medium", 2, "Checkout spinner never stops when the 3DS iframe is blocked", None, "s1", ["3ds"], "2026-11-16T11:00:00.000Z",
     "Happens with strict tracking protection in Firefox."),
    ("PLAT-88", "Task", "In Progress", "Medium", 3, "Upgrade service base images to node 22.11", "u7", None, ["infra"], "2026-11-12T09:30:00.000Z",
     "Paused after the 11/17 checkout-web rollback."),
    ("PLAT-91", "Story", "To Do", "Low", 5, "Feature flag audit log", "u5", None, ["flags"], "2026-11-05T09:30:00.000Z",
     "Record who flipped which flag in which environment."),
    ("PLAT-93", "Bug", "Done", "High", 2, "deployctl rollback ignores --digest when a tag is also given", "u7", None, ["deployctl"], "2026-11-04T09:30:00.000Z",
     "Fixed in deployctl 1.9. Always roll back by digest."),
    ("PLAT-95", "Task", "To Do", "Medium", 8, "Move staging to the new VPC", "u7", None, ["infra"], "2026-11-15T09:30:00.000Z",
     "Cutover planned for December."),
]
J_KEY = {row[0]: f"i{n}" for n, row in enumerate(J_ISSUES, 1)}

CHK430_SUBTASKS = [
    ("st_430_1", "Merge QA-passed MRs into release/4.12", False),
    ("st_430_2", "Create release v4.12.1 in GitLab", False),
    ("st_430_3", "Prod deploy approved by SRE on call", False),
    ("st_430_4", "Announce in #releases", False),
]

J_COMMENTS = [
    ("CHK-402", "u2", "2026-11-07T17:30:00.000Z", "Verified on iOS 17.6 with a CAD cart. Pass."),
    ("CHK-410", "u5", "2026-11-12T16:00:00.000Z", "Not a hotfix, this goes with the 4.13 webhook work."),
    ("CHK-412", "u3", "2026-11-17T20:30:00.000Z",
     "!10 is the fix against release/4.12. !11 is the same change ported to main, leave that one to me, I'll merge it once 4.12.1 is out."),
    ("CHK-415", "u4", "2026-11-17T20:02:00.000Z", "Lint failure is fixed in the follow-up commit, the pipeline is green now."),
    ("CHK-417", "u5", "2026-11-17T18:10:00.000Z", "Merged !9 into release/4.12."),
    ("CHK-417", "u2", "2026-11-17T19:20:00.000Z", "Verified on staging: one confirmation email per order across 20 test orders. Pass."),
    ("CHK-419", "u4", "2026-11-17T22:45:00.000Z", "Pushed the handling for the frictionless 3DS2 flow, CI should be green shortly."),
    ("CHK-421", "u6", "2026-11-17T22:08:00.000Z", "This is 4.13 scope, it goes out with the invoicing changes."),
    ("CHK-423", "u3", "2026-11-17T21:35:00.000Z", "Fix is in !15 against release/4.12."),
    ("CHK-427", "u7", "2026-11-17T23:05:00.000Z",
     "Timeline: 22:10 UTC deploy of the node 22.11 base image failed health checks, deployctl rolled prod back to the 11/14 image automatically."),
    ("CHK-430", "u1", "2026-11-17T23:00:00.000Z", "Scope per Lena's thread in #checkout-release. Deploy window tomorrow 11:00-15:00 ET with Sam."),
    ("CHK-405", "u6", "2026-11-13T15:00:00.000Z", "Design review moved to Friday."),
]


def build_jira():
    users = [{"id": uid, "name": name, "email": email, "avatar": avatar(name)} for uid, name, email in J_USERS]
    projects = [
        {"id": "p1", "key": "CHK", "name": "Checkout", "leadId": "u1", "category": "Software", "icon": avatar("Checkout"),
         "description": "checkout-web: cart, payment and confirmation flow."},
        {"id": "p2", "key": "PLAT", "name": "Platform", "leadId": "u7", "category": "Software", "icon": avatar("Platform"),
         "description": "Shared infrastructure, deploy tooling and flags."},
    ]
    sprints = [
        {"id": "s1", "projectId": "p1", "name": "CHK Sprint 47", "goal": "Ship 4.12.1 hotfix, start 4.13 work",
         "startDate": "2026-11-09T14:00:00.000Z", "endDate": "2026-11-20T22:00:00.000Z", "state": "active"},
        {"id": "s2", "projectId": "p1", "name": "CHK Sprint 48", "goal": "4.13 features",
         "startDate": "2026-11-23T14:00:00.000Z", "endDate": "2026-12-04T22:00:00.000Z", "state": "future"},
        {"id": "s3", "projectId": "p1", "name": "CHK Sprint 46", "goal": "Release 4.12.0",
         "startDate": "2026-10-26T14:00:00.000Z", "endDate": "2026-11-06T22:00:00.000Z", "state": "closed"},
    ]
    issues = []
    for key, itype, status, prio, pts, summary, assignee, sprint, labels, created, desc in J_ISSUES:
        issues.append({
            "id": J_KEY[key], "key": key, "projectId": "p2" if key.startswith("PLAT") else "p1",
            "summary": summary, "description": desc, "type": itype, "status": status, "priority": prio,
            "storyPoints": pts, "reporterId": "u6" if itype in ("Bug", "Story") else "u1", "assigneeId": assignee,
            "sprintId": sprint, "epicId": None, "createdAt": created, "updatedAt": created, "labels": list(labels),
            "subtasks": [{"id": i, "title": t, "completed": c} for i, t, c in CHK430_SUBTASKS] if key == "CHK-430" else [],
            "linkedIssueIds": [],
        })
    by_key = {i["key"]: i for i in issues}
    by_key["CHK-412"]["linkedIssueIds"] = [J_KEY["CHK-402"]]
    by_key["CHK-427"]["linkedIssueIds"] = [J_KEY["PLAT-88"]]
    # issues that got comments later show that as their update time
    for n, (key, uid, ts, text) in enumerate(J_COMMENTS, 1):
        if ts > by_key[key]["updatedAt"]:
            by_key[key]["updatedAt"] = ts
    comments = [{"id": f"c{n}", "issueId": J_KEY[key], "userId": uid, "content": text, "createdAt": ts}
                for n, (key, uid, ts, text) in enumerate(J_COMMENTS, 1)]
    notifications = [
        {"id": "n1", "type": "comment", "issueId": J_KEY["CHK-412"], "actorId": "u3",
         "message": 'Ravi Menon commented on CHK-412: "!10 is the fix against release/4.12..."', "read": False, "createdAt": "2026-11-17T20:30:00.000Z"},
        {"id": "n2", "type": "comment", "issueId": J_KEY["CHK-419"], "actorId": "u4",
         "message": 'Theo Grant commented on CHK-419: "Pushed the handling for the frictionless 3DS2 flow..."', "read": False, "createdAt": "2026-11-17T22:45:00.000Z"},
        {"id": "n3", "type": "assignment", "issueId": J_KEY["CHK-430"], "actorId": "u6",
         "message": 'Lena Fischer assigned CHK-430 "Release 4.12.1 (hotfix)" to you', "read": False, "createdAt": "2026-11-17T22:56:00.000Z"},
        {"id": "n4", "type": "status_change", "issueId": J_KEY["CHK-417"], "actorId": "u5",
         "message": 'Ines Duarte moved CHK-417 "Order confirmation email is sent twice" to In Review', "read": True, "createdAt": "2026-11-17T18:11:00.000Z"},
        {"id": "n5", "type": "comment", "issueId": J_KEY["CHK-427"], "actorId": "u7",
         "message": 'Sam Okafor commented on CHK-427: "Timeline: 22:10 UTC deploy of the node 22.11 base image..."', "read": True, "createdAt": "2026-11-17T23:05:00.000Z"},
    ]
    workflows = [{"id": "w1", "name": "Software Workflow", "transitions": [
        {"from": "To Do", "to": ["In Progress"]},
        {"from": "In Progress", "to": ["In Review", "To Do", "Done"]},
        {"from": "In Review", "to": ["Done", "In Progress"]},
        {"from": "Done", "to": ["In Progress", "To Do"]},
    ]}]
    return {"users": users, "projects": projects, "issues": issues, "sprints": sprints, "comments": comments,
            "workflows": workflows, "notifications": notifications, "currentUser": users[0]}


# ====================================================================== GITLAB
CW = 1  # checkout-web project id

# id, project, title, source, target, status, author, created
MRS = [
    (1, 2, "Bump stripe-go to v76", "chore/stripe-go-76", "main", "merged", "Ines Duarte", "2026-11-03T15:00:00.000Z"),
    (2, CW, "Order summary card redesign", "feat/order-summary-redesign", "main", "open", "Ravi Menon", "2026-11-06T16:00:00.000Z"),
    (3, 3, "Cache product availability for 30s", "feat/availability-cache", "main", "open", "Theo Grant", "2026-11-07T11:00:00.000Z"),
    (4, CW, "CHK-402: Apple Pay currency for CAD carts on iOS 17", "hotfix/CHK-402-applepay-ios17", "release/4.12", "merged", "Ravi Menon", "2026-11-05T18:00:00.000Z"),
    (5, CW, "CHK-399: move address autocomplete to Places API v2", "feat/CHK-399-places-v2", "main", "merged", "Ravi Menon", "2026-10-30T15:00:00.000Z"),
    (6, 4, "checkout-web: raise HPA max replicas to 24", "sre/checkout-hpa", "main", "merged", "Sam Okafor", "2026-11-12T19:00:00.000Z"),
    (7, CW, "CHK-410: retry webhook delivery with backoff", "feat/CHK-410-webhook-retry", "main", "open", "Ines Duarte", "2026-11-13T17:00:00.000Z"),
    (8, 2, "Add idempotency keys to the refund endpoint", "feat/refund-idempotency", "main", "open", "Ines Duarte", "2026-11-14T15:00:00.000Z"),
    (9, CW, "CHK-417: dedupe order confirmation emails", "hotfix/CHK-417-email-dedup", "release/4.12", "merged", "Ines Duarte", "2026-11-17T16:30:00.000Z"),
    (10, CW, "CHK-412: use cart currency in Apple Pay payment request", "hotfix/CHK-412-applepay-currency", "release/4.12", "open", "Ravi Menon", "2026-11-17T20:12:00.000Z"),
    (11, CW, "CHK-412: use cart currency in Apple Pay payment request", "port/CHK-412-main", "main", "open", "Ravi Menon", "2026-11-17T20:20:00.000Z"),
    (12, CW, "CHK-415: reject expired promo codes at apply time", "hotfix/CHK-415-promo-expiry", "release/4.12", "open", "Theo Grant", "2026-11-17T17:15:00.000Z"),
    (13, CW, "CHK-419: reload saved cards after 3DS challenge", "hotfix/CHK-419-3ds-saved-cards", "release/4.12", "open", "Theo Grant", "2026-11-17T15:10:00.000Z"),
    (14, CW, "CHK-421: round JPY tax lines half-up", "feat/CHK-421-jpy-tax-rounding", "release/4.12", "open", "Theo Grant", "2026-11-17T19:05:00.000Z"),
    (15, CW, "CHK-423: stop Klarna redirect loop on return URL", "hotfix/CHK-423-klarna-return", "release/4.12", "open", "Ravi Menon", "2026-11-17T21:28:00.000Z"),
    (16, CW, "CHK-425: lazy-load payment method icons", "perf/CHK-425-lazy-icons", "main", "open", "Ravi Menon", "2026-11-16T13:00:00.000Z"),
    (17, 3, "Return 410 for retired SKUs", "fix/retired-sku-410", "main", "merged", "Theo Grant", "2026-11-10T14:00:00.000Z"),
]
MR_DESC = {
    9: "Only the payment webhook enqueues the confirmation job now. Closes CHK-417.",
    10: "Build the Apple Pay payment request from cart.currency instead of merchant.defaultCurrency. Closes CHK-412.",
    11: "Port of the CHK-412 fix to main.",
    12: "Reject codes whose end date is in the past when they are applied. Closes CHK-415.",
    13: "Re-fetch saved cards after the 3DS challenge resolves. Closes CHK-419.",
    14: "Half-up rounding for JPY tax lines. CHK-421.",
    15: "Decode the Klarna return URL before matching the confirmation route. Gated by klarna_redirect_v2. Closes CHK-423.",
}


def stage(sid, name, jobs):
    status = "failed" if any(j[1] == "failed" for j in jobs) else ("running" if any(j[1] == "running" for j in jobs) else
                                                                    ("pending" if all(j[1] == "pending" for j in jobs) else "success"))
    return {"id": sid, "name": name, "status": status,
            "jobs": [dict({"id": sid * 10 + n, "name": jn, "status": js, "duration": jd}, **({"logs": jl} if jl else {}))
                     for n, (jn, js, jd, jl) in enumerate(jobs, 1)]}


def pipeline(pid, project, status, branch, commit, message, duration, created, failed_job=None, logs=None, review=True):
    def js(name):
        if status == "running":
            return "running" if name in ("unit-tests", "lint") else ("success" if name == "build-app" else "pending")
        if failed_job == name:
            return "failed"
        if failed_job and name in ("review-app", "deploy-staging", "e2e-checkout"):
            return "pending"
        return "success"

    def job(name, dur):
        return (name, js(name), dur if js(name) != "pending" else "0s", logs if failed_job == name else None)

    stages = [stage(pid * 10 + 1, "build", [job("build-app", "1m 12s")]),
              stage(pid * 10 + 2, "test", [job("unit-tests", "2m 40s"), job("lint", "34s"), job("e2e-checkout", "4m 05s")])]
    if branch.startswith("release/"):
        stages.append(stage(pid * 10 + 3, "deploy", [job("deploy-staging", "1m 30s")]))
    elif review:
        stages.append(stage(pid * 10 + 3, "review", [job("review-app", "1m 05s")]))
    return {"id": pid, "projectId": project, "status": status, "branch": branch, "commit": commit, "message": message,
            "duration": duration, "createdAt": created, "stages": stages}


def build_pipelines():
    p = []
    # checkout-web, newest first (GitLab lists newest first)
    p.append(pipeline(4832, CW, "running", "feat/order-summary-redesign", "77ac0d1", "Summary card: sticky total on mobile", "1m 50s", "2026-11-18T14:18:00.000Z"))
    p.append(pipeline(4831, CW, "failed", "hotfix/CHK-419-3ds-saved-cards", "c7d2e19", "CHK-419: handle 3DS2 frictionless flow", "3m 02s",
                      "2026-11-17T22:41:00.000Z", failed_job="unit-tests",
                      logs="FAIL src/payment/SavedCards.test.tsx\n  SavedCards > keeps saved cards after a frictionless 3DS2 result\n    Expected: 3 cards\n    Received: 0 cards\n\nTests: 1 failed, 412 passed\nERROR: Job failed: exit code 1"))
    p.append(pipeline(4830, CW, "success", "hotfix/CHK-423-klarna-return", "9ab41f0", "CHK-423: stop Klarna redirect loop on return URL", "8m 41s", "2026-11-17T21:30:00.000Z"))
    p.append(pipeline(4829, CW, "success", "port/CHK-412-main", "e41c7a2", "CHK-412: use cart currency in Apple Pay payment request", "8m 12s", "2026-11-17T20:22:00.000Z"))
    p.append(pipeline(4828, CW, "success", "hotfix/CHK-412-applepay-currency", "5f30b8d", "CHK-412: use cart currency in Apple Pay payment request", "8m 30s", "2026-11-17T20:15:00.000Z"))
    p.append(pipeline(4827, CW, "success", "hotfix/CHK-415-promo-expiry", "0d9e6c4", "CHK-415: compare promo expiry in UTC (review fix)", "8m 55s", "2026-11-17T19:55:00.000Z"))
    p.append(pipeline(4826, CW, "success", "feat/CHK-421-jpy-tax-rounding", "b88f1d3", "CHK-421: round JPY tax lines half-up", "8m 20s", "2026-11-17T19:10:00.000Z"))
    p.append(pipeline(4825, CW, "success", "release/4.12", "1e6a9c0", "Merge branch 'hotfix/CHK-417-email-dedup' into 'release/4.12'", "9m 48s", "2026-11-17T18:05:00.000Z"))
    p.append(pipeline(4824, CW, "failed", "hotfix/CHK-415-promo-expiry", "a3c5e77", "CHK-415: reject expired promo codes at apply time", "1m 58s",
                      "2026-11-17T17:20:00.000Z", failed_job="lint",
                      logs="$ npm run lint\nsrc/promotions/applyCode.ts\n  41:7  error  'now' is assigned a value but never used  no-unused-vars\n\n1 problem (1 error, 0 warnings)\nERROR: Job failed: exit code 1"))
    p.append(pipeline(4823, CW, "success", "hotfix/CHK-417-email-dedup", "6c2f8e1", "CHK-417: dedupe order confirmation emails", "8m 03s", "2026-11-17T16:40:00.000Z"))
    p.append(pipeline(4822, CW, "success", "hotfix/CHK-419-3ds-saved-cards", "f19b3a2", "CHK-419: reload saved cards after 3DS challenge", "8m 37s", "2026-11-17T15:12:00.000Z"))
    p.append(pipeline(4821, CW, "failed", "feat/order-summary-redesign", "3b9e5aa", "Summary card: tax row layout", "5m 10s", "2026-11-17T14:30:00.000Z",
                      failed_job="e2e-checkout", logs="e2e-checkout: summary.spec.ts > shows tax row\n  Timed out waiting for [data-test=tax-row]\nERROR: Job failed: exit code 1"))
    p.append(pipeline(4818, CW, "success", "main", "d0a4b61", "Merge branch 'feat/CHK-399-places-v2' into 'main'", "9m 02s", "2026-11-14T18:00:00.000Z"))
    p.append(pipeline(4815, CW, "success", "feat/CHK-410-webhook-retry", "28e7f90", "CHK-410: exponential backoff for webhook retries", "8m 44s", "2026-11-13T17:30:00.000Z"))
    p.append(pipeline(4802, CW, "success", "release/4.12", "9c3d2f4", "Release 4.12.0", "10m 12s", "2026-11-10T17:40:00.000Z"))
    # other projects
    p.append(pipeline(3310, 2, "success", "main", "aa71c3e", "Merge branch 'chore/stripe-go-76' into 'main'", "4m 10s", "2026-11-04T10:00:00.000Z", review=False))
    p.append(pipeline(3314, 2, "failed", "feat/refund-idempotency", "f0e9d21", "Add idempotency keys to the refund endpoint", "2m 20s", "2026-11-14T15:20:00.000Z",
                      failed_job="unit-tests", logs="--- FAIL: TestRefundIdempotency (0.02s)\n    refund_test.go:88: expected 1 refund, got 2\nFAIL", review=False))
    p.append(pipeline(2207, 3, "success", "main", "4c1d8e2", "Merge branch 'fix/retired-sku-410' into 'main'", "3m 01s", "2026-11-10T15:00:00.000Z", review=False))
    p.append(pipeline(2209, 3, "success", "feat/availability-cache", "8d2a7b0", "Cache product availability for 30s", "3m 22s", "2026-11-07T11:20:00.000Z", review=False))
    p.append(pipeline(910, 4, "success", "main", "51be0f9", "checkout-web: raise HPA max replicas to 24", "1m 02s", "2026-11-12T19:20:00.000Z", review=False))
    return p


RUNBOOK_SEED = (
    "# Rollback runbook\n\n"
    "Every release and hotfix of checkout-web gets a section here before the SRE on call approves the production deploy. Newest section first.\n\n"
    "Each section lists the image we roll back to (tag and digest of what is running in production right before the deploy), "
    "the feature flags to switch off before rolling back, and the deployctl command. Always roll back by digest (see PLAT-93).\n\n"
    f"## 4.12.0\n- Roll back to: v4.11.3 @ {DIG['v4.11.3']}\n- Flags off before rollback: new_address_autocomplete\n"
    f"- Command: `deployctl rollback checkout-web --env production --digest {DIG['v4.11.3']}`\n- Approved by Sam Okafor, 2026-11-10\n\n"
    f"## 4.11.3\n- Roll back to: v4.11.2 @ {DIG['v4.11.2']}\n- Flags off before rollback: none\n"
    f"- Command: `deployctl rollback checkout-web --env production --digest {DIG['v4.11.2']}`\n- Approved by Sam Okafor, 2026-10-28\n"
)
GOLDEN_SECTION = (
    f"## 4.12.1\n- Roll back to: v4.12.0 @ {ROLLBACK_TARGET[1]}\n- Flags off before rollback: klarna_redirect_v2\n"
    f"- Command: `deployctl rollback checkout-web --env production --digest {ROLLBACK_TARGET[1]}`\n\n"
)


def runbook_with(section: str) -> str:
    head, sep, tail = RUNBOOK_SEED.partition("## 4.12.0")
    return head + section + sep + tail


def build_gitlab():
    me = {"id": 1, "name": "Dana Whitfield", "username": "dwhitfield", "avatarUrl": avatar("Dana Whitfield")}
    cw_branches = ["release/4.12", "main", "hotfix/CHK-412-applepay-currency", "port/CHK-412-main", "hotfix/CHK-415-promo-expiry",
                   "hotfix/CHK-417-email-dedup", "hotfix/CHK-419-3ds-saved-cards", "hotfix/CHK-423-klarna-return",
                   "feat/CHK-421-jpy-tax-rounding", "feat/order-summary-redesign", "feat/CHK-410-webhook-retry", "perf/CHK-425-lazy-icons"]
    projects = [
        {"id": CW, "name": "checkout-web", "description": "Brightloop hosted checkout: cart, payment and confirmation flow.",
         "visibility": "private", "stars": 18, "forks": 3, "updatedAt": "2026-11-18T14:18:00.000Z", "branches": cw_branches,
         "files": [
             {"name": "src", "type": "folder", "children": [
                 {"name": "payment", "type": "folder", "children": [
                     {"name": "applePay.ts", "type": "file", "content": "export function paymentRequest(cart) {\n  return { currencyCode: cart.currency, total: cart.total };\n}\n"},
                     {"name": "klarnaReturn.ts", "type": "file", "content": "import { flags } from '../flags';\n\nexport function handleReturn(url) {\n  if (!flags.klarna_redirect_v2) return legacyReturn(url);\n  return routeFor(decodeURIComponent(url));\n}\n"},
                 ]},
                 {"name": "flags.ts", "type": "file", "content": "export const flags = {\n  klarna_redirect_v2: false,\n  order_summary_v3: false,\n  new_address_autocomplete: true,\n};\n"},
             ]},
             {"name": ".gitlab-ci.yml", "type": "file", "content": "stages: [build, test, review, deploy]\n"},
             {"name": "package.json", "type": "file", "content": "{\n  \"name\": \"checkout-web\",\n  \"version\": \"4.12.0\"\n}\n"},
             {"name": "README.md", "type": "file", "content": "# checkout-web\n\nHosted checkout for Brightloop merchants.\n\nReleases are cut from `release/<minor>` branches, see the wiki page Release process.\n"},
         ]},
        {"id": 2, "name": "payments-gateway", "description": "Go service in front of Adyen, Stripe and Klarna.", "visibility": "private",
         "stars": 9, "forks": 1, "updatedAt": "2026-11-14T15:20:00.000Z", "branches": ["main", "feat/refund-idempotency"],
         "files": [{"name": "main.go", "type": "file", "content": "package main\n\nfunc main() {}\n"}]},
        {"id": 3, "name": "storefront-api", "description": "Catalog and availability API.", "visibility": "internal",
         "stars": 6, "forks": 0, "updatedAt": "2026-11-10T15:00:00.000Z", "branches": ["main", "feat/availability-cache"],
         "files": [{"name": "README.md", "type": "file", "content": "# storefront-api\n"}]},
        {"id": 4, "name": "infra-deploy", "description": "Helm charts and deployctl config for production and staging.", "visibility": "private",
         "stars": 4, "forks": 0, "updatedAt": "2026-11-17T22:20:00.000Z", "branches": ["main"],
         "files": [{"name": "charts", "type": "folder", "children": [{"name": "checkout-web.yaml", "type": "file", "content": "replicas: 6\nhpa:\n  max: 24\n"}]}]},
    ]
    mrs = [{"id": i, "projectId": proj, "title": t, "description": MR_DESC.get(i, ""), "sourceBranch": s, "targetBranch": tb,
            "status": st, "author": a, "createdAt": c, "reviewers": []} for i, proj, t, s, tb, st, a, c in MRS]
    issues = [
        {"id": 1, "projectId": CW, "title": "Flaky e2e: summary.spec.ts tax row", "description": "Times out about 1 in 10 runs on the redesign branch.", "status": "open", "labels": ["flaky-test"], "assignee": "Ravi Menon"},
        {"id": 2, "projectId": CW, "title": "Renovate: bump vite to 6.1", "description": "", "status": "open", "labels": ["dependencies"], "assignee": None},
        {"id": 3, "projectId": CW, "title": "Review apps: shorten TTL to 3 days", "description": "Saves cluster capacity.", "status": "in_progress", "labels": ["ci"], "assignee": "Sam Okafor"},
        {"id": 4, "projectId": CW, "title": "Document the hotfix branch naming", "description": "hotfix/<KEY>-slug against release/<minor>.", "status": "closed", "labels": ["docs"], "assignee": "Dana Whitfield"},
        {"id": 5, "projectId": 2, "title": "Klarna webhook signature v2", "description": "", "status": "open", "labels": ["klarna"], "assignee": "Ines Duarte"},
        {"id": 6, "projectId": 4, "title": "Alert on deployctl auto-rollback", "description": "Page the on-call when an automatic rollback fires.", "status": "open", "labels": ["sre"], "assignee": "Sam Okafor"},
    ]
    wiki = [
        {"id": 1, "projectId": CW, "title": "Home", "content": "# checkout-web wiki\n\n- Release process\n- Rollback runbook\n- Feature flags\n"},
        {"id": 2, "projectId": CW, "title": "Release process", "content":
            "# Release process\n\n1. Scope lives in Jira (CHK, label hotfix-<version> for hotfixes); the PM settles changes in #checkout-release.\n"
            "2. A ticket whose MR into release/<minor> has a green latest pipeline moves to In Review; QA verifies it on the review app and posts the verdict in #checkout-release.\n"
            "3. Merge only what QA passed. Anything that misses the train goes to the next hotfix label.\n"
            "4. Create the GitLab release (tag v<version>) with the shipped ticket keys.\n"
            "5. The SRE on call approves the production deploy.\n"
            "6. Announce in #releases with the shipped ticket keys.\n"},
        {"id": 3, "projectId": CW, "title": "Rollback runbook", "content": RUNBOOK_SEED},
        {"id": 4, "projectId": CW, "title": "Feature flags", "content":
            "# Feature flags\n\n| flag | prod | owner |\n|---|---|---|\n| new_address_autocomplete | on | Ravi |\n| order_summary_v3 | off | Ravi |\n"
            "| klarna_redirect_v2 | off | Ines |\n\nFlags are flipped with `flagctl set <flag> on|off --env production`.\n"},
        {"id": 5, "projectId": 2, "title": "Home", "content": "# payments-gateway\n\nOn-call: #sre-oncall\n"},
        {"id": 6, "projectId": 4, "title": "deployctl", "content": "# deployctl\n\n`deployctl history checkout-web --env production` shows what is running.\n"},
    ]
    registry = [
        {"id": 1, "projectId": CW, "name": "checkout-web/app", "tags": ["v4.13.0-rc.1", "v4.12.0", "v4.11.3", "v4.11.2"], "size": "212MB", "updatedAt": "2026-11-17T22:05:00.000Z"},
        {"id": 2, "projectId": 2, "name": "payments-gateway/server", "tags": ["v2.8.0", "v2.7.4"], "size": "38MB", "updatedAt": "2026-11-04T10:10:00.000Z"},
        {"id": 3, "projectId": 3, "name": "storefront-api/server", "tags": ["v1.19.0"], "size": "54MB", "updatedAt": "2026-11-10T15:10:00.000Z"},
    ]
    releases = [
        {"id": 1, "projectId": CW, "tagName": "v4.11.3", "name": "checkout-web 4.11.3", "description": "Hotfix: CHK-371, CHK-374.", "createdAt": "2026-10-28T18:00:00.000Z", "author": "Dana Whitfield"},
        {"id": 2, "projectId": 2, "tagName": "v2.8.0", "name": "payments-gateway 2.8.0", "description": "stripe-go v76, Klarna sandbox fixes.", "createdAt": "2026-11-04T10:30:00.000Z", "author": "Ines Duarte"},
        {"id": 3, "projectId": CW, "tagName": "v4.12.0", "name": "checkout-web 4.12.0", "description": "CHK-388, CHK-391, CHK-399, CHK-402.", "createdAt": "2026-11-10T18:30:00.000Z", "author": "Dana Whitfield"},
        {"id": 4, "projectId": CW, "tagName": "v4.13.0-rc.1", "name": "checkout-web 4.13.0-rc.1", "description": "Release candidate for 4.13. Staging only.", "createdAt": "2026-11-13T16:20:00.000Z", "author": "Dana Whitfield"},
        {"id": 5, "projectId": 3, "tagName": "v1.19.0", "name": "storefront-api 1.19.0", "description": "410 for retired SKUs.", "createdAt": "2026-11-10T15:30:00.000Z", "author": "Theo Grant"},
    ]
    return {
        "currentUser": me, "projects": projects, "pipelines": build_pipelines(), "issues": issues, "mergeRequests": mrs,
        "registry": registry,
        "snippets": [{"id": 1, "title": "Rollback by digest", "code": "deployctl rollback checkout-web --env production --digest <sha256:...>", "language": "bash", "author": "Sam Okafor"}],
        "wiki": wiki,
        "vulnerabilities": [
            {"id": 1, "projectId": CW, "severity": "medium", "name": "Outdated dependency: semver 7.5.1", "status": "detected"},
            {"id": 2, "projectId": CW, "severity": "low", "name": "Missing Permissions-Policy header", "status": "detected"},
            {"id": 3, "projectId": CW, "severity": "critical", "name": "OpenSSL CVE-2026-4127 in base image", "status": "resolved"},
        ],
        "milestones": [
            {"id": 1, "projectId": CW, "title": "4.12.1 hotfix", "dueDate": "2026-11-18", "progress": 40},
            {"id": 2, "projectId": CW, "title": "4.13", "dueDate": "2026-12-09", "progress": 25},
        ],
        "releases": releases,
    }


# ======================================================================= SLACK
S_USERS = [
    ("U01", "Dana Whitfield", "Dana", "dana.whitfield@brightloop.io", "Release Manager"),
    ("U02", "Marta Kowalski", "Marta", "marta.kowalski@brightloop.io", "QA Lead"),
    ("U03", "Ravi Menon", "Ravi", "ravi.menon@brightloop.io", "Frontend Engineer"),
    ("U04", "Theo Grant", "Theo", "theo.grant@brightloop.io", "Frontend Engineer"),
    ("U05", "Ines Duarte", "Ines", "ines.duarte@brightloop.io", "Staff Engineer, Payments"),
    ("U06", "Lena Fischer", "Lena", "lena.fischer@brightloop.io", "Product Manager, Checkout"),
    ("U07", "Sam Okafor", "Sam", "sam.okafor@brightloop.io", "SRE (on call)"),
    ("U08", "Priya Raman", "Priya", "priya.raman@brightloop.io", "Merchant Support"),
]


def smsg(mid, sender, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": sender, "content": text, "timestamp": ts, "threadId": thread,
            "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack():
    users = [{"userId": uid, "fullName": full, "displayName": short, "email": email, "avatar": avatar(full), "title": title,
              "status": "busy" if uid == "U01" else "online", "statusMessage": "Vendor review until noon" if uid == "U01" else "",
              "statusEmoji": "", "timeZone": "America/New_York"} for uid, full, short, email, title in S_USERS]
    everyone = [u[0] for u in S_USERS]

    def channel(cid, desc, members=everyone, pinned=()):
        return {"channelId": cid, "name": cid, "description": desc, "topic": desc, "isPrivate": False,
                "isStarred": cid in ("checkout-release", "releases"), "members": list(members), "createdBy": "U01",
                "createdAt": "2025-03-01T15:00:00Z", "pinnedMessages": list(pinned), "unreadCount": 0}

    scope = ("Scope for 4.12.1 (hotfix, going out Wed 11/18): it's the CHK tickets labeled hotfix-4.12.1. "
             "Everything else waits for 4.13. Any changes I'll post in this thread.")
    messages = {
        "general": [
            smsg("g1", "U06", "2026-11-16T15:00:00Z", "Reminder: Thanksgiving code freeze starts Tuesday 11/24, last 4.13 RC on Monday."),
            smsg("g2", "U08", "2026-11-17T14:20:00Z", "Merchant NPS for October is up to 46, thanks everyone for the checkout fixes."),
        ],
        "checkout-release": [
            smsg("r1", "U06", "2026-11-17T15:02:00Z", scope),
            smsg("r1_t1", "U06", "2026-11-17T21:48:00Z",
                 "Adding CHK-423 (Klarna redirect loop) to 4.12.1, Fernway Outdoor can't take Klarna payments at all. Ravi's MR is up. "
                 "@Dana please label it and take it through with the rest.", thread="th_scope"),
            smsg("r1_t2", "U04", "2026-11-17T22:05:00Z",
                 "fyi !14 (CHK-421 JPY rounding) is pointed at release/4.12 by mistake, that's 4.13 work. Please don't merge it, I'll retarget it.", thread="th_scope"),
            smsg("r1_t3", "U06", "2026-11-17T22:07:00Z", "Right, 421 is 4.13.", thread="th_scope"),
            smsg("r2", "U02", "2026-11-17T16:30:00Z",
                 "QA for 4.12.1 as usual: move the ticket to In Review once its MR is green and I'll check it on the review app and post the result here. "
                 "Please don't merge anything I haven't passed."),
            smsg("r3", "U05", "2026-11-17T18:12:00Z", "Merged !9 (CHK-417) into release/4.12, Marta verified it on staging.",
                 reactions=[{"emoji": "white_check_mark", "users": ["U02"], "count": 1}]),
            smsg("r4", "U07", "2026-11-18T13:40:00Z", "Morning. checkout-web prod deploy window today is 11:00-15:00 ET. Ping me here once v4.12.1 is tagged."),
            smsg("r5", "U01", "2026-11-18T14:10:00Z", "I'm stuck in the vendor review until lunch, getting help to push 4.12.1 through. Same process as always."),
        ],
        "releases": [
            smsg("l1", "U01", "2026-10-28T19:00:00Z", "checkout-web v4.11.3 is live in production. Ships: CHK-371, CHK-374."),
            smsg("l2", "U05", "2026-11-04T11:00:00Z", "payments-gateway v2.8.0 is live in production."),
            smsg("l3", "U01", "2026-11-10T19:30:00Z", "checkout-web v4.12.0 is live in production. Ships: CHK-388, CHK-391, CHK-399, CHK-402."),
        ],
        "checkout-dev": [
            smsg("d1", "U03", "2026-11-17T20:25:00Z", "Opened !10 (release/4.12) and !11 (main) for the Apple Pay currency bug."),
            smsg("d2", "U04", "2026-11-17T22:46:00Z", "3DS frictionless fix pushed on CHK-419, waiting on CI."),
            smsg("d3", "U03", "2026-11-18T13:55:00Z", "Anyone else seeing the summary.spec.ts flake on the redesign branch?"),
        ],
        "sre-oncall": [
            smsg("o1", "U07", "2026-11-14T21:30:00Z", "checkout-web prod redeployed v4.12.0 on the patched base image (OpenSSL CVE-2026-4127). No functional changes."),
            smsg("o2", "U07", "2026-11-17T22:25:00Z",
                 "checkout-web prod: the node 22.11 base image deploy failed health checks and deployctl auto-rolled back. PLAT-88 is paused, post-mortem in CHK-427."),
        ],
    }
    messages["checkout-release"][0]["replyCount"] = 3
    threads = {"th_scope": {"threadId": "th_scope", "parentMessageId": "r1", "channelId": "checkout-release", "dmId": None,
                            "replies": ["r1_t1", "r1_t2", "r1_t3"], "followers": ["U01", "U06", "U04"]}}
    return {
        "currentUser": users[0],
        "workspace": {"workspaceId": "ws_bl", "workspaceName": "Brightloop", "icon": avatar("Brightloop")},
        "users": users,
        "channels": [channel("general", "Company-wide"),
                     channel("checkout-release", "Coordinating checkout-web releases and hotfixes", pinned=["r1"]),
                     channel("releases", "Production release announcements"),
                     channel("checkout-dev", "checkout-web engineering"),
                     channel("sre-oncall", "Production operations")],
        "messages": messages, "threads": threads, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


# ==================================================================== TRIGGERS
TRIGGER_MSGS = {
    "trg_qa_412": ("U02", "CHK-412 passed on the review app: a CAD cart shows CA$ on the Apple Pay sheet, USD and EUR carts are unchanged. Good to merge."),
    "trg_qa_415": ("U02", "CHK-415 failed on the review app. An expired code is still accepted when it's typed in lowercase (spring25 goes through, SPRING25 is rejected). "
                          "Sending it back to Theo, it can't go out in 4.12.1."),
    "trg_qa_423": ("U02", "CHK-423 passed on the review app: the Klarna sandbox payment returns to the confirmation page, no loop. Good to merge."),
    "trg_qa_419": ("U02", "I can't test CHK-419, the review app never deployed because the branch pipeline is red."),
    "trg_qa_421": ("U02", "CHK-421 isn't on my 4.12.1 list, Lena said it's 4.13. Not testing it for this hotfix."),
    "trg_ines_flag": ("U05", "@Dana saw !15 (CHK-423) land on release/4.12. The Klarna fix ships dark behind the klarna_redirect_v2 flag, so merchants won't see it until it's on. "
                             "Can you add a step to CHK-430 to turn klarna_redirect_v2 on in production right after the deploy? And the rollback plan has to switch it off before rolling back."),
    "trg_sam_rollback": ("U07", "@Dana thanks for tagging v4.12.1. Before I approve the prod deploy I need the 4.12.1 section on the Rollback runbook page in the checkout-web wiki: "
                                "the image we'd roll back to (tag and digest of what is actually running in production right now) and any flags that have to be switched off first."),
    "trg_sam_approve": ("U07", "Rollback plan for 4.12.1 looks good. Prod deploy of v4.12.1 is approved, I'll run it in the 11:00 window. Go ahead and announce."),
}


def trigger_append(mid, ts="__NOW__"):
    sender, text = TRIGGER_MSGS[mid]
    return smsg(mid, sender, ts, text)


def build_triggers():
    def qa(key, mid, delay=30):
        return {"id": mid, "when": {"site": "jira", "path": "issues", "match": {"key": key, "status": "In Review"}},
                "then": [{"site": "slack", "path": "messages.checkout-release", "append": trigger_append(mid)}], "delay_s": delay}
    return [
        qa("CHK-412", "trg_qa_412"), qa("CHK-415", "trg_qa_415", 35), qa("CHK-423", "trg_qa_423", 40),
        qa("CHK-419", "trg_qa_419", 25), qa("CHK-421", "trg_qa_421", 25),
        {"id": "trg_ines_flag", "when": {"site": "gitlab", "path": "mergeRequests", "match": {"id": 15, "status": "merged"}},
         "then": [{"site": "slack", "path": "messages.checkout-release", "append": trigger_append("trg_ines_flag")}], "delay_s": 20},
        {"id": "trg_sam_rollback", "when": {"site": "gitlab", "path": "releases", "match": {"projectId": CW, "tagName": {"contains": "4.12.1"}}},
         "then": [{"site": "slack", "path": "messages.checkout-release", "append": trigger_append("trg_sam_rollback")}], "delay_s": 20},
        {"id": "trg_sam_approve", "when": {"site": "gitlab", "path": "wiki", "match": {"title": "Rollback runbook", "content": {"contains": "4.12.1"}}},
         "then": [{"site": "slack", "path": "messages.checkout-release", "append": trigger_append("trg_sam_approve")}], "delay_s": 25},
    ]


# ================================================================ DEPLOY LOG
def deploy_rows():
    rows = [
        ("2026-10-14T18:05:12Z", "production", "checkout-web", "v4.11.2", DIG["v4.11.2"], "succeeded", "sam.okafor", ""),
        ("2026-10-28T18:20:11Z", "production", "checkout-web", "v4.11.3", DIG["v4.11.3"], "succeeded", "sam.okafor", ""),
        ("2026-11-04T10:42:30Z", "production", "payments-gateway", "v2.8.0", digest("pg v2.8.0"), "succeeded", "ines.duarte", ""),
        ("2026-11-09T16:10:00Z", "staging", "checkout-web", "v4.12.0", DIG["v4.12.0_nov10"], "succeeded", "ci", ""),
        ("2026-11-10T19:02:45Z", "production", "checkout-web", "v4.12.0", DIG["v4.12.0_nov10"], "succeeded", "sam.okafor", ""),
        ("2026-11-10T15:40:00Z", "production", "storefront-api", "v1.19.0", digest("sf v1.19.0"), "succeeded", "theo.grant", ""),
        ("2026-11-12T19:25:00Z", "production", "checkout-web", "v4.12.0", DIG["v4.12.0_nov10"], "succeeded", "sam.okafor", "scale-out only (HPA max 24), same image"),
        ("2026-11-13T16:40:02Z", "staging", "checkout-web", "v4.13.0-rc.1", DIG["v4.13.0-rc.1"], "succeeded", "ci", ""),
        ("2026-11-14T21:15:30Z", "production", "checkout-web", "v4.12.0", DIG["v4.12.0_nov14"], "succeeded", "sam.okafor", "rebuild on patched base image (OpenSSL CVE-2026-4127)"),
        ("2026-11-14T21:40:10Z", "production", "payments-gateway", "v2.8.0", digest("pg v2.8.0 openssl"), "succeeded", "sam.okafor", "rebuild on patched base image"),
        ("2026-11-17T18:20:00Z", "staging", "checkout-web", "release/4.12@1e6a9c0", DIG["release-4.12"], "succeeded", "ci", ""),
        ("2026-11-17T22:10:05Z", "production", "checkout-web", "v4.12.0", DIG["v4.12.0_nov17"], "rolled_back", "sam.okafor", "node 22.11 base image; health checks failed, auto rollback to previous image"),
        ("2026-11-18T13:05:40Z", "staging", "checkout-web", "v4.13.0-rc.1", DIG["v4.13.0-rc.1"], "succeeded", "ci", "redeploy after staging VPC test"),
    ]
    rows.sort(key=lambda r: r[0])
    return [["deployed_at_utc", "environment", "service", "version", "image_digest", "status", "triggered_by", "note"]] + [list(r) for r in rows]


# ==================================================================== RUNS
SCOPE = ["CHK-412", "CHK-415", "CHK-417", "CHK-419", "CHK-423"]
MR_OF = {"CHK-412": 10, "CHK-415": 12, "CHK-417": 9, "CHK-419": 13, "CHK-423": 15}
SHIPPED = ["CHK-412", "CHK-417", "CHK-423"]
DEFERRED = ["CHK-415", "CHK-419"]

GOLDEN_PLAN = {
    "label_423": True,
    "in_review": ["CHK-412", "CHK-415", "CHK-423"],     # QA requested -> trigger messages
    "merge": [10, 15],
    "deferred": {"CHK-415": "In Progress", "CHK-419": "In Progress"},
    "flag_subtask": "Turn on klarna_redirect_v2 in production right after the deploy",
    "release_keys": SHIPPED,
    "wiki_section": GOLDEN_SECTION,
    "done": SHIPPED + ["CHK-430"],
    "announce_keys": SHIPPED,
    "announce_after_approval": True,
    "csv": [(k, f"!{MR_OF[k]}", "shipped" if k in SHIPPED else "deferred") for k in SCOPE],
}

T0 = "2026-11-18T14:"


def ts(mmss: str) -> str:
    return f"{T0}{mmss}.000Z"


def apply_run(seed, plan):
    jira, gitlab, slack = (copy.deepcopy(seed[k]) for k in ("jira", "gitlab", "slack"))
    issues = {i["key"]: i for i in jira["issues"]}
    mrs = {m["id"]: m for m in gitlab["mergeRequests"]}
    chan = slack["messages"]["checkout-release"]

    def touch(key, when):
        issues[key]["updatedAt"] = when

    if plan.get("label_423"):
        issues["CHK-423"]["labels"].append("hotfix-4.12.1")
        touch("CHK-423", ts("35:00"))
    qa_times = {"CHK-412": "38:00", "CHK-415": "38:30", "CHK-423": "39:00", "CHK-419": "38:10", "CHK-421": "38:20"}
    for key in plan.get("in_review", []):
        issues[key]["status"] = "In Review"
        touch(key, ts("37:00"))
        chan.append(trigger_append(f"trg_qa_{key[4:]}", ts(qa_times[key])))
    for mr in plan.get("merge", []):
        mrs[mr]["status"] = "merged"
    if 15 in plan.get("merge", []):
        chan.append(trigger_append("trg_ines_flag", ts("41:30")))
    if plan.get("flag_subtask"):
        issues["CHK-430"]["subtasks"].append({"id": "st_g1", "title": plan["flag_subtask"], "completed": False})
        touch("CHK-430", ts("43:00"))
    for key, status in plan.get("deferred", {}).items():
        labels = [l for l in issues[key]["labels"] if l != "hotfix-4.12.1"]
        issues[key]["labels"] = labels + ["hotfix-4.12.2"]
        issues[key]["status"] = status
        touch(key, ts("44:00"))
    if plan.get("release_keys") is not None:
        desc = "Hotfix release of checkout-web.\n" + "\n".join(
            f"- {k}: {issues[k]['summary']}" for k in plan["release_keys"])
        gitlab["releases"].append({"id": len(gitlab["releases"]) + 1, "projectId": CW, "tagName": "v4.12.1",
                                   "name": "checkout-web 4.12.1", "description": desc,
                                   "createdAt": ts("46:00"), "author": "Dana Whitfield"})
        chan.append(trigger_append("trg_sam_rollback", ts("46:30")))
    if plan.get("wiki_section"):
        page = next(w for w in gitlab["wiki"] if w["title"] == "Rollback runbook")
        page["content"] = runbook_with(plan["wiki_section"])
        chan.append(trigger_append("trg_sam_approve", ts("50:30")))
    for key in plan.get("done", []):
        issues[key]["status"] = "Done"
        touch(key, ts("52:00"))
    if plan.get("announce_keys") is not None:
        when = "54:00" if plan.get("announce_after_approval") else "46:10"
        slack["messages"]["releases"].append(smsg(
            "msg_g_announce", "U01", ts(when),
            "checkout-web v4.12.1 is live in production. Ships: " + ", ".join(plan["announce_keys"]) + "."))
    chan.sort(key=lambda m: m["timestamp"])
    return {"jira": jira, "gitlab": gitlab, "slack": slack}, [["ticket", "merge_request", "decision"]] + [list(r) for r in plan["csv"]]


def variant_plans():
    naive = {
        "label_423": False, "in_review": [],
        "merge": [10, 11, 12, 13],
        "deferred": {},
        "flag_subtask": None,
        "release_keys": ["CHK-412", "CHK-415", "CHK-419"],
        "wiki_section": None,
        "done": ["CHK-412", "CHK-415", "CHK-419", "CHK-430"],
        "announce_keys": ["CHK-412", "CHK-415", "CHK-419"], "announce_after_approval": False,
        "csv": [("CHK-412", "!10", "shipped"), ("CHK-415", "!12", "shipped"), ("CHK-417", "!9", "shipped"), ("CHK-419", "!13", "shipped")],
    }
    slip_qa415 = dict(GOLDEN_PLAN, merge=[10, 12, 15])  # merged CHK-415 before Marta's verdict came back
    slip_flag = dict(GOLDEN_PLAN, flag_subtask=None, wiki_section=GOLDEN_SECTION.replace("klarna_redirect_v2", "none"))
    slip_digest = dict(GOLDEN_PLAN, wiki_section=GOLDEN_SECTION.replace(ROLLBACK_TARGET[1], DIG["v4.12.0_nov10"]))
    return {"naive": naive, "slip_qa415": slip_qa415, "slip_flag": slip_flag, "slip_digest": slip_digest}


# ===================================================================== IO
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def expected():
    return {
        "clock": CLOCK,
        "scope": SCOPE, "shipped": SHIPPED, "deferred": DEFERRED,
        "mr_of": MR_OF, "merge_ids": [10, 15], "must_stay_open_mrs": [11, 12, 13, 14],
        "non_target_issues": ["CHK-421", "CHK-426", "CHK-402"],
        "release": {"projectId": CW, "tagName": "v4.12.1", "must_mention": SHIPPED, "must_not_mention": ["CHK-415", "CHK-419", "CHK-421"]},
        "release_ticket": "CHK-430", "flag": "klarna_redirect_v2",
        "wiki_page": {"projectId": CW, "title": "Rollback runbook"},
        "rollback_target": {"tag": ROLLBACK_TARGET[0], "digest": ROLLBACK_TARGET[1]},
        "wrong_digests": WRONG_DIGESTS,
        "trigger_messages": {k: {"channel": "checkout-release", "senderId": v[0]} for k, v in TRIGGER_MSGS.items()},
        "qa_pass": {"CHK-412": "trg_qa_412", "CHK-423": "trg_qa_423"}, "qa_fail": {"CHK-415": "trg_qa_415"},
        "announce_channel": "releases", "agent_slack_user": "U01", "agent_jira_user": "u1",
        "manifest": [{"ticket": k, "merge_request": f"!{MR_OF[k]}", "decision": "shipped" if k in SHIPPED else "deferred"} for k in SCOPE],
        "jira_issue_ids": J_KEY,
    }


def main(out: Path):
    seed = {"jira": build_jira(), "gitlab": build_gitlab(), "slack": build_slack()}
    assert "4.12.1" not in json.dumps([w for w in seed["gitlab"]["wiki"]])
    assert all("4.12.1" not in r["tagName"] for r in seed["gitlab"]["releases"])
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    write_json(out / "triggers.json", build_triggers())

    golden, golden_csv = apply_run(seed, GOLDEN_PLAN)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "release_manifest.csv", golden_csv)
    write_csv(out / "input" / "deploy_history.csv", deploy_rows())
    write_json(out / "expected.json", expected())

    variants = {"golden": (golden, golden_csv), "nop": (seed, None)}
    for name, plan in variant_plans().items():
        variants[name] = apply_run(seed, plan)
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        (out / "variants" / name / "output").mkdir(parents=True, exist_ok=True)
        if rows:
            write_csv(out / "variants" / name / "output" / "release_manifest.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
