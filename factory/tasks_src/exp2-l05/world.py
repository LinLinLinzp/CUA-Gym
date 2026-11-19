#!/usr/bin/env python3
"""World for exp2-l05 / checkout-rounding-rollback (Sentry + GitHub + Linear + Slack + local CSV).

Writes into <out>/:
  seed/{sentry,github,linear,slack}.json     initial state per site
  golden/{sentry,github,linear,slack}.json   state after a correct run
  golden_output/incident_trace.json          correct CLI deliverable
  input/deploys.csv                          agent-visible deploy history export
  expected.json                              hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/incident_trace.json}

Story: Sam Okafor (SRE, on call for checkout at Acme Commerce) was paged at 06:52 PT for
Sentry issue CHECKOUT-API-3QK and hands the incident off. Lever L05 (multi-hop chain):
  Sentry event release (checkout-api@4.31.0, production)
    -> deploys.csv row for exactly that service/env/release -> full git SHA
    -> GitHub commit "Merge pull request #1287 ..." -> PR #1287 (cites PAY-412)
    -> Linear PAY-412 is Canceled as duplicate of PAY-431 -> owner Priya, channel #ledger-rollouts
    -> Slack thread: flag plan superseded; revert from the revert branch of the PR that is in
       the throwing release (revert-1287-line-rounding, not revert-1291-krw-rounding)
    -> new GitHub PR number (#1294, auto-assigned) needed on Linear, Sentry, Slack and the JSON.
Secondary traps: deploy-log near duplicates (checkout-web@4.31.0, rc.1, newer 4.31.1 on staging
whose SHA shares the 4be1c prefix); reviewer is the ticket owner, not the PR author; stale plan for
the first attempt in #payments; keep the Sentry issue unresolved and the revert unmerged.
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T09:40:00-08:00"
RUN_TS = "2026-11-18T18:05:00.000Z"          # when the golden run's writes happen (UTC)
RUN_TS_S = "2026-11-18T18:05:00Z"

ORG = "acme-commerce"
REPO_API = "checkout-api"
SENTRY_ISSUE = "CHECKOUT-API-3QK"
RELEASE = "checkout-api@4.31.0"
GOOD_BRANCH = "revert-1287-line-rounding"
NEXT_PR = 1294

# Commit SHAs that matter (others are derived from labels)
SHA_1287 = "4be1c07a93d2f1e86b0c5d7a2e49f310c8ab65d1"   # HEAD of checkout-api@4.31.0
SHA_1291 = "4be1c70e2a8f93b1d6c04e7f5a2b18c9d30e6f47"   # HEAD of checkout-api@4.31.1 (staging only)
SHA_1285 = "9d27e5b1c0a4f8e3b6d21c7a9f05e4b38d1c62aa"   # HEAD of 4.31.0-rc.1
SHA_1279 = "e81f3c9a2b7d40c6f15e8a93d2b07c4e6a19f5d3"   # first attempt (4.30.0)
SHA_1283 = "c3a90d7e15b2f4a8e6c01d9b3f7a2e58c4d61b09"   # revert of first attempt (4.30.1)
SHA_WEB882 = "7f0b2d4e9c1a8f36b5e0d27c4a9e13f8b6d05c21"  # checkout-web@4.31.0


def fake_sha(label: str) -> str:
    import hashlib
    return hashlib.sha1(("acme-commerce/" + label).encode()).hexdigest()


# ---------------------------------------------------------------- people
# key: (full name, github username, slack id, linear id, sentry id, email, slack title)
PEOPLE = {
    "sam":    ("Sam Okafor", "sokafor", "U_SAM", "lu_sam", "su_sam", "SRE, checkout on-call"),
    "priya":  ("Priya Natarajan", "pnatarajan", "U_PRIYA", "lu_priya", "su_priya", "Staff Engineer, Payments"),
    "tomasz": ("Tomasz Kowalski", "tkowalski", "U_TOMASZ", "lu_tomasz", "su_tomasz", "Software Engineer, Payments"),
    "marco":  ("Marco Bianchi", "mbianchi", "U_MARCO", "lu_marco", "su_marco", "SRE"),
    "helen":  ("Helen Park", "hpark", "U_HELEN", "lu_helen", "su_helen", "Engineering Manager, Payments"),
    "jun":    ("Jun Watanabe", "jwatanabe", "U_JUN", "lu_jun", "su_jun", "Software Engineer, Checkout"),
    "aisha":  ("Aisha Bello", "abello", "U_AISHA", "lu_aisha", "su_aisha", "Software Engineer, Ledger"),
    "leo":    ("Leo Martins", "lmartins", "U_LEO", "lu_leo", "su_leo", "Software Engineer, Checkout"),
    "nadia":  ("Nadia Haddad", "nhaddad", "U_NADIA", "lu_nadia", "su_nadia", "Product Manager, Payments"),
    "pooja":  ("Pooja Nair", "pnair", "U_POOJA", "lu_pooja", "su_pooja", "QA Engineer"),
}


def email(key):
    first, last = PEOPLE[key][0].lower().split()
    return f"{first}.{last}@acme-commerce.com"


def gh(key):
    return "gh_" + key


# ---------------------------------------------------------------- deploy history (local CSV)
DEPLOYS = [
    # deployed_at (UTC), service, environment, release, git_sha, deployed_by, status
    ("2026-11-04T17:05:00Z", "checkout-api", "staging", "checkout-api@4.29.0", fake_sha("api-4.29.0"), "mbianchi", "succeeded"),
    ("2026-11-04T21:40:00Z", "checkout-api", "production", "checkout-api@4.29.0", fake_sha("api-4.29.0"), "mbianchi", "succeeded"),
    ("2026-11-05T16:20:00Z", "checkout-web", "staging", "checkout-web@4.29.0", fake_sha("web-4.29.0"), "jwatanabe", "succeeded"),
    ("2026-11-05T19:00:00Z", "checkout-web", "production", "checkout-web@4.29.0", fake_sha("web-4.29.0"), "jwatanabe", "succeeded"),
    ("2026-11-06T15:30:00Z", "ledger-worker", "staging", "ledger-worker@2.13.2", fake_sha("ledger-2.13.2"), "abello", "succeeded"),
    ("2026-11-06T18:10:00Z", "ledger-worker", "production", "ledger-worker@2.13.2", fake_sha("ledger-2.13.2"), "abello", "succeeded"),
    ("2026-11-09T20:40:00Z", "checkout-api", "staging", "checkout-api@4.30.0", SHA_1279, "tkowalski", "succeeded"),
    ("2026-11-10T14:35:00Z", "checkout-api", "production", "checkout-api@4.30.0", SHA_1279, "mbianchi", "succeeded"),
    ("2026-11-10T17:55:00Z", "checkout-api", "production", "checkout-api@4.30.1", SHA_1283, "mbianchi", "succeeded"),
    ("2026-11-10T18:20:00Z", "checkout-api", "staging", "checkout-api@4.30.1", SHA_1283, "mbianchi", "succeeded"),
    ("2026-11-11T16:00:00Z", "storefront-web", "staging", "storefront-web@12.4.0", fake_sha("store-12.4.0"), "lmartins", "succeeded"),
    ("2026-11-11T19:45:00Z", "storefront-web", "production", "storefront-web@12.4.0", fake_sha("store-12.4.0"), "lmartins", "succeeded"),
    ("2026-11-12T15:10:00Z", "notifications-svc", "staging", "notifications-svc@1.8.3", fake_sha("notif-1.8.3"), "pnair", "succeeded"),
    ("2026-11-12T17:30:00Z", "notifications-svc", "production", "notifications-svc@1.8.3", fake_sha("notif-1.8.3"), "mbianchi", "failed"),
    ("2026-11-12T17:52:00Z", "notifications-svc", "production", "notifications-svc@1.8.3", fake_sha("notif-1.8.3"), "mbianchi", "succeeded"),
    ("2026-11-12T21:00:00Z", "ledger-worker", "staging", "ledger-worker@2.14.0", fake_sha("ledger-2.14.0"), "abello", "succeeded"),
    ("2026-11-13T16:15:00Z", "ledger-worker", "production", "ledger-worker@2.14.0", fake_sha("ledger-2.14.0"), "abello", "succeeded"),
    ("2026-11-13T18:30:00Z", "checkout-web", "staging", "checkout-web@4.30.0", fake_sha("web-4.30.0"), "jwatanabe", "succeeded"),
    ("2026-11-13T22:05:00Z", "checkout-web", "production", "checkout-web@4.30.0", fake_sha("web-4.30.0"), "jwatanabe", "succeeded"),
    ("2026-11-16T15:40:00Z", "storefront-web", "staging", "storefront-web@12.5.0", fake_sha("store-12.5.0"), "lmartins", "succeeded"),
    ("2026-11-16T18:25:00Z", "storefront-web", "production", "storefront-web@12.5.0", fake_sha("store-12.5.0"), "lmartins", "succeeded"),
    ("2026-11-17T16:58:00Z", "checkout-api", "staging", "checkout-api@4.31.0-rc.1", SHA_1285, "tkowalski", "succeeded"),
    ("2026-11-17T19:10:00Z", "checkout-api", "staging", "checkout-api@4.31.0", SHA_1287, "tkowalski", "succeeded"),
    ("2026-11-17T21:20:00Z", "checkout-web", "staging", "checkout-web@4.31.0", SHA_WEB882, "jwatanabe", "succeeded"),
    ("2026-11-17T23:00:00Z", "ledger-worker", "staging", "ledger-worker@2.14.1", fake_sha("ledger-2.14.1"), "abello", "succeeded"),
    ("2026-11-18T14:31:00Z", "checkout-api", "production", "checkout-api@4.31.0", SHA_1287, "mbianchi", "succeeded"),
    ("2026-11-18T14:44:00Z", "checkout-web", "production", "checkout-web@4.31.0", SHA_WEB882, "jwatanabe", "succeeded"),
    ("2026-11-18T15:30:00Z", "ledger-worker", "production", "ledger-worker@2.14.1", fake_sha("ledger-2.14.1"), "abello", "succeeded"),
    ("2026-11-18T16:45:00Z", "checkout-api", "staging", "checkout-api@4.31.1", SHA_1291, "pnatarajan", "succeeded"),
    ("2026-11-18T17:10:00Z", "storefront-web", "staging", "storefront-web@12.5.1", fake_sha("store-12.5.1"), "lmartins", "succeeded"),
]


# ================================================================ SENTRY
S_PROJECTS = [
    ("proj-api", "checkout-api", "python", "#E03E2F", "team-pay"),
    ("proj-web", "checkout-web", "javascript-react", "#F5B000", "team-checkout"),
    ("proj-ledger", "ledger-worker", "python", "#2BA185", "team-pay"),
    ("proj-store", "storefront-web", "javascript-react", "#3B6ECC", "team-checkout"),
    ("proj-notif", "notifications-svc", "node", "#7C3AED", "team-sre"),
]

S_TEAMS = [
    ("team-pay", "Payments", ["priya", "tomasz", "helen", "aisha", "nadia"]),
    ("team-checkout", "Checkout", ["jun", "leo", "pooja"]),
    ("team-sre", "SRE", ["sam", "marco"]),
]


def s_frames(rows):
    return [{"filename": f, "function": fn, "lineNo": ln, "colNo": 0, "inApp": inapp, "context": ctx}
            for f, fn, ln, inapp, ctx in rows]


ROUNDING_FRAMES = s_frames([
    ("gunicorn/workers/sync.py", "handle_request", 178, False, []),
    ("checkout_api/http/carts.py", "post_totals", 212, True, [
        [209, "    cart = carts.load(cart_id, for_update=True)"],
        [210, "    rates = fx.rates_for(cart.currency)"],
        [211, "    # totals are computed before feature flags are evaluated"],
        [212, "    totals = tax.compute_totals(cart, rates)"],
        [213, "    return jsonify(totals.as_dict())"]]),
    ("checkout_api/tax/totals.py", "compute_totals", 88, True, [
        [86, "    lines = [line_tax(l, cart.region) for l in cart.lines]"],
        [87, "    # PAY-431: quantize per line before FX conversion"],
        [88, "    lines = rounding.round_line_items(lines, cart.currency, rates)"],
        [89, "    return Totals.from_lines(lines, cart.currency)"]]),
    ("checkout_api/tax/rounding.py", "round_line_items", 41, True, [
        [37, "def round_line_items(lines, currency, rates):"],
        [38, "    exp = MINOR_UNIT_EXP[currency.source]"],
        [39, "    out = []"],
        [40, "    for line in lines:"],
        [41, "        q = (line.tax * rates[line.currency]).quantize(exp, rounding=ROUND_HALF_EVEN)"],
        [42, "        out.append(line.with_tax(q))"]]),
])


def s_issue(iid, short, title, subtitle, culprit, project, status, priority, assignee, first, last, count, users,
            level="error", trend="ongoing", unhandled=True, release="", env="production"):
    stats = [max(0, int(count / 14 * (0.4 + ((i * 7 + len(short)) % 10) / 10))) for i in range(14)]
    return {"id": iid, "shortId": short, "title": title, "subtitle": subtitle, "culprit": culprit, "type": "error",
            "level": level, "status": status, "priority": priority, "isUnhandled": unhandled, "project": project,
            "assignee": assignee, "firstSeen": first, "lastSeen": last, "count": count, "userCount": users,
            "stats14d": stats, "trend": trend, "events": [f"evt-{iid}"],
            "tags": {"environment": {env: 100}, "level": {level: 100}, "release": {release: 100} if release else {},
                     "handled": {"no" if unhandled else "yes": 100}},
            "metadata": {"type": title, "value": subtitle}}


def s_event(issue, release, env, ts, url, transaction, frames, platform="python", exc_type=None, exc_value=None,
            server="", user_id="", crumbs=None):
    eid = fake_sha("evt-" + issue["id"])[:32]
    tags = {"environment": env, "release": release, "level": issue["level"],
            "handled": "no" if issue["isUnhandled"] else "yes", "server_name": server or "web-1",
            "transaction": transaction, "url": url}
    return {
        "id": f"evt-{issue['id']}", "eventId": eid, "issueId": issue["id"],
        "title": f"{issue['title']}: {issue['subtitle']}", "timestamp": ts, "level": issue["level"],
        "platform": platform, "release": release, "environment": env,
        "user": {"id": user_id or "anon", "email": "", "ip": "10.42.0.17"},
        "contexts": {"runtime": {"name": "CPython" if platform == "python" else "node",
                                 "version": "3.12.4" if platform == "python" else "20.11.1"},
                     "os": {"name": "Linux", "version": "6.1"}},
        "highlights": {"handled": tags["handled"], "level": issue["level"], "release": release,
                       "environment": env, "url": url, "transaction": transaction, "server_name": tags["server_name"]},
        "exception": {"type": exc_type or issue["title"], "value": exc_value or issue["subtitle"],
                      "stacktrace": {"frames": frames}},
        "breadcrumbs": crumbs or [
            {"type": "http", "category": "http", "message": f"POST {url}", "level": "info", "timestamp": ts, "data": {}},
            {"type": "error", "category": "exception", "message": f"{issue['title']}: {issue['subtitle']}",
             "level": "error", "timestamp": ts, "data": {}}],
        "tags": tags,
    }


def generic_frames(path, fn, line, code):
    return s_frames([(path, fn, line, True, [[line - 1, "    ..."], [line, code], [line + 1, "    ..."]])])


def build_sentry():
    users = [{"id": PEOPLE[k][4], "name": PEOPLE[k][0], "email": email(k), "avatar": avatar(PEOPLE[k][0]),
              "role": "Admin" if k in ("sam", "marco") else ("Manager" if k == "helen" else "Member"),
              "teams": [t for t, _, mem in S_TEAMS if k in mem], "dateJoined": "2024-03-01T00:00:00Z"} for k in PEOPLE]
    teams = [{"id": tid, "name": name, "slug": name.lower(), "avatar": None, "memberCount": len(mem),
              "members": [PEOPLE[m][4] for m in mem], "projects": [p[0] for p in S_PROJECTS if p[4] == tid]}
             for tid, name, mem in S_TEAMS]
    projects = [{"id": pid, "name": name, "slug": name, "platform": plat, "color": color, "teams": [team],
                 "dateCreated": "2024-03-01T00:00:00Z",
                 "stats": {"crashFreeSessions": 99.1, "crashFreeUsers": 99.4, "totalErrors24h": 0, "totalTransactions24h": 120000},
                 "latestRelease": None, "environments": ["production", "staging"]}
                for pid, name, plat, color, team in S_PROJECTS]

    issues, events = [], {}

    def add(issue, event):
        issues.append(issue)
        events[issue["id"]] = [event]

    # --- the paged issue
    i = s_issue("issue-3qk", SENTRY_ISSUE, "InvalidOperation", "[<class 'decimal.InvalidOperation'>]",
                "checkout_api/tax/rounding.py in round_line_items", "proj-api", "unresolved", "critical", None,
                "2026-11-18T14:33:12Z", "2026-11-18T17:38:40Z", 4821, 1377, trend="escalating", release=RELEASE)
    add(i, s_event(i, RELEASE, "production", "2026-11-18T17:38:40Z", "/v2/carts/{cart_id}/totals",
                   "POST /v2/carts/{cart_id}/totals", ROUNDING_FRAMES, exc_type="decimal.InvalidOperation",
                   exc_value="[<class 'decimal.InvalidOperation'>] quantize result has too many digits for current context",
                   server="checkout-api-7c9f5d6b8-xk2lp", user_id="cust_88231"))
    # --- first attempt, resolved (near duplicate)
    i = s_issue("issue-3p9", "CHECKOUT-API-3P9", "InvalidOperation", "[<class 'decimal.InvalidOperation'>]",
                "checkout_api/tax/rounding.py in round_line_items", "proj-api", "resolved", "high", PEOPLE["tomasz"][4],
                "2026-11-10T14:37:02Z", "2026-11-10T17:58:10Z", 2210, 704, release="checkout-api@4.30.0")
    add(i, s_event(i, "checkout-api@4.30.0", "production", "2026-11-10T17:58:10Z", "/v2/carts/{cart_id}/totals",
                   "POST /v2/carts/{cart_id}/totals", ROUNDING_FRAMES, exc_type="decimal.InvalidOperation",
                   server="checkout-api-5b7d9c4f1-q8m2z", user_id="cust_61420"))
    # --- same exception on staging with the follow-up release
    i = s_issue("issue-3qm", "CHECKOUT-API-3QM", "InvalidOperation", "[<class 'decimal.InvalidOperation'>]",
                "checkout_api/tax/rounding.py in round_line_items", "proj-api", "unresolved", "medium", None,
                "2026-11-18T16:52:40Z", "2026-11-18T17:20:05Z", 37, 3, release="checkout-api@4.31.1", env="staging")
    add(i, s_event(i, "checkout-api@4.31.1", "staging", "2026-11-18T17:20:05Z", "/v2/carts/{cart_id}/totals",
                   "POST /v2/carts/{cart_id}/totals", ROUNDING_FRAMES, exc_type="decimal.InvalidOperation",
                   server="checkout-api-stg-6d8f7-p2v9c", user_id="qa_bot"))

    noise = [
        ("issue-3q2", "CHECKOUT-API-3Q2", "OperationalError", "could not obtain lock on row in relation \"carts\"",
         "checkout_api/db/locks.py in acquire", "proj-api", "unresolved", "medium", "marco", "2026-11-02T09:12:00Z",
         "2026-11-18T12:04:00Z", 312, 140, "checkout-api@4.30.1", "checkout_api/db/locks.py", "acquire", 54,
         "    cur.execute(LOCK_SQL, (cart_id,))"),
        ("issue-3pz", "CHECKOUT-API-3PZ", "ReadTimeout", "HTTPSConnectionPool(host='fx.internal', port=443): Read timed out.",
         "checkout_api/fx/client.py in fetch_rates", "proj-api", "unresolved", "low", None, "2026-10-21T03:40:00Z",
         "2026-11-18T06:15:00Z", 96, 41, "checkout-api@4.30.1", "checkout_api/fx/client.py", "fetch_rates", 77,
         "    resp = self.session.get(url, timeout=2.0)"),
        ("issue-3pt", "CHECKOUT-API-3PT", "KeyError", "'promo_code'", "checkout_api/http/promos.py in apply_promo",
         "proj-api", "resolved", "medium", "jun", "2026-10-30T15:00:00Z", "2026-11-06T11:00:00Z", 58, 33,
         "checkout-api@4.29.0", "checkout_api/http/promos.py", "apply_promo", 31, "    code = payload['promo_code']"),
        ("issue-3qa", "CHECKOUT-API-3QA", "ValidationError", "postal_code: does not match pattern for region 'CA'",
         "checkout_api/http/addresses.py in validate", "proj-api", "archived", "low", None, "2026-11-12T10:00:00Z",
         "2026-11-17T22:30:00Z", 410, 388, "checkout-api@4.30.1", "checkout_api/http/addresses.py", "validate", 64,
         "    raise ValidationError(errors)"),
        ("issue-w1kd", "CHECKOUT-WEB-1KD", "TypeError", "Cannot read properties of undefined (reading 'minorUnits')",
         "src/cart/TotalsPanel.tsx in formatLineTax", "proj-web", "unresolved", "high", "leo", "2026-11-18T14:46:00Z",
         "2026-11-18T17:01:00Z", 188, 160, "checkout-web@4.31.0", "src/cart/TotalsPanel.tsx", "formatLineTax", 118,
         "  return fmt(line.tax.minorUnits, currency)"),
        ("issue-w1jx", "CHECKOUT-WEB-1JX", "ChunkLoadError", "Loading chunk 612 failed.", "webpack/runtime in jsonp",
         "proj-web", "unresolved", "low", None, "2026-11-05T19:05:00Z", "2026-11-18T15:10:00Z", 1203, 980,
         "checkout-web@4.30.0", "webpack/runtime/jsonp", "loadChunk", 30, "  throw new ChunkLoadError(id)"),
        ("issue-w1hb", "CHECKOUT-WEB-1HB", "Error", "Stripe Elements failed to mount: iframe blocked",
         "src/payment/CardForm.tsx in mountElements", "proj-web", "resolved", "medium", "jun", "2026-10-28T12:00:00Z",
         "2026-11-04T09:00:00Z", 77, 70, "checkout-web@4.29.0", "src/payment/CardForm.tsx", "mountElements", 52,
         "  elements.mount('#card')"),
        ("issue-l0rq", "LEDGER-WORKER-0RQ", "IntegrityError", "duplicate key value violates unique constraint \"refund_idem_key\"",
         "ledger_worker/refunds/batch.py in post_batch", "proj-ledger", "resolved", "high", "aisha", "2026-11-13T16:20:00Z",
         "2026-11-13T18:00:00Z", 64, 12, "ledger-worker@2.14.0", "ledger_worker/refunds/batch.py", "post_batch", 140,
         "    session.flush()"),
        ("issue-l0rv", "LEDGER-WORKER-0RV", "SoftTimeLimitExceeded", "SoftTimeLimitExceeded()",
         "ledger_worker/settlement/tasks.py in reconcile_day", "proj-ledger", "unresolved", "medium", None,
         "2026-11-16T02:00:00Z", "2026-11-18T02:00:00Z", 6, 1, "ledger-worker@2.14.0", "ledger_worker/settlement/tasks.py",
         "reconcile_day", 88, "    for batch in iter_batches(day):"),
        ("issue-s7ff", "STOREFRONT-WEB-7FF", "TypeError", "Failed to fetch", "src/search/useSuggest.ts in fetchSuggest",
         "proj-store", "unresolved", "low", None, "2026-10-12T08:00:00Z", "2026-11-18T17:30:00Z", 5402, 3120,
         "storefront-web@12.5.0", "src/search/useSuggest.ts", "fetchSuggest", 22, "  const res = await fetch(url)"),
        ("issue-s7fk", "STOREFRONT-WEB-7FK", "Error", "Hydration failed because the initial UI does not match",
         "src/pages/product/[slug].tsx in ProductPage", "proj-store", "unresolved", "medium", "leo", "2026-11-16T18:30:00Z",
         "2026-11-18T16:55:00Z", 640, 590, "storefront-web@12.5.0", "src/pages/product/[slug].tsx", "ProductPage", 74,
         "  return <PriceTag price={price} />"),
        ("issue-n2ac", "NOTIFICATIONS-SVC-2AC", "Error", "SMTP 421 Too many connections", "src/mail/send.ts in sendMail",
         "proj-notif", "resolved", "medium", "marco", "2026-11-12T17:31:00Z", "2026-11-12T17:50:00Z", 233, 0,
         "notifications-svc@1.8.3", "src/mail/send.ts", "sendMail", 61, "  await transport.sendMail(msg)"),
        ("issue-n2ae", "NOTIFICATIONS-SVC-2AE", "TemplateError", "Missing translation key receipt.tax_line for locale ja-JP",
         "src/templates/render.ts in render", "proj-notif", "unresolved", "low", "pooja", "2026-11-14T10:00:00Z",
         "2026-11-18T13:20:00Z", 45, 39, "notifications-svc@1.8.3", "src/templates/render.ts", "render", 40,
         "  throw new TemplateError(key, locale)"),
    ]
    for (iid, short, title, sub, culprit, proj, status, prio, who, first, last, cnt, ucnt, rel, path, fn, ln, code) in noise:
        env = "production"
        i = s_issue(iid, short, title, sub, culprit, proj, status, prio, PEOPLE[who][4] if who else None, first, last,
                    cnt, ucnt, release=rel, env=env, trend="ongoing")
        plat = "python" if proj in ("proj-api", "proj-ledger") else "javascript"
        add(i, s_event(i, rel, env, last, "/", fn, generic_frames(path, fn, ln, code), platform=plat))

    comments = {
        "issue-3qk": [
            {"id": "comment-3qk-1", "author": "Marco Bianchi", "type": "comment", "timestamp": "2026-11-18T14:58:00Z",
             "text": "Error rate on POST /v2/carts/{cart_id}/totals went from ~0 to 4% within two minutes of the 06:31 deploy. Mostly multi-currency carts."},
        ],
        "issue-3p9": [
            {"id": "comment-3p9-1", "author": "Marco Bianchi", "type": "comment", "timestamp": "2026-11-10T17:40:00Z",
             "text": "Reverting the rounding change, see acme-commerce/checkout-api#1283."},
        ],
    }
    releases = [
        {"id": f"rel-{n}", "version": v, "shortVersion": v.split("@")[1], "dateCreated": d, "dateReleased": d,
         "projects": [p], "newIssues": ni, "crashFreeSessions": cf, "crashFreeUsers": cf, "adoption": ad,
         "totalSessions": ts, "commitCount": cc, "authors": [PEOPLE[a][4] for a in au], "lastEvent": d}
        for n, (v, d, p, ni, cf, ad, ts, cc, au) in enumerate([
            ("checkout-api@4.31.0", "2026-11-18T14:31:00Z", "proj-api", 1, 95.9, 100, 41200, 6, ["tomasz", "priya", "jun"]),
            ("checkout-web@4.31.0", "2026-11-18T14:44:00Z", "proj-web", 1, 99.2, 96, 88400, 9, ["jun", "priya", "leo"]),
            ("ledger-worker@2.14.1", "2026-11-18T15:30:00Z", "proj-ledger", 0, 100.0, 100, 3100, 3, ["aisha"]),
            ("checkout-api@4.30.1", "2026-11-10T17:55:00Z", "proj-api", 1, 99.7, 0, 302000, 1, ["marco"]),
            ("checkout-api@4.30.0", "2026-11-10T14:35:00Z", "proj-api", 1, 96.4, 0, 9800, 11, ["tomasz", "jun"]),
            ("storefront-web@12.5.0", "2026-11-16T18:25:00Z", "proj-store", 1, 98.8, 100, 512000, 14, ["leo"]),
            ("notifications-svc@1.8.3", "2026-11-12T17:52:00Z", "proj-notif", 2, 99.9, 100, 0, 5, ["pooja", "marco"]),
        ], start=1)]
    alert_rules = [
        {"id": "alert-1", "name": "checkout-api: error spike (prod)", "type": "issue", "status": "triggered",
         "threshold": 100, "thresholdType": "above", "triggerLabel": "Above 100/5min", "dateTriggered": "2026-11-18T14:52:00Z",
         "dateCreated": "2025-02-10T00:00:00Z", "project": "proj-api", "team": "team-sre",
         "history": [{"timestamp": "2026-11-18T14:52:00Z", "status": "critical"},
                     {"timestamp": "2026-11-10T18:05:00Z", "status": "resolved"},
                     {"timestamp": "2026-11-10T14:40:00Z", "status": "critical"}]},
        {"id": "alert-2", "name": "checkout-web: JS error rate", "type": "metric", "status": "warning", "threshold": 1,
         "thresholdType": "above", "triggerLabel": "Above 1%", "dateTriggered": "2026-11-18T15:02:00Z",
         "dateCreated": "2025-02-10T00:00:00Z", "project": "proj-web", "team": "team-checkout",
         "history": [{"timestamp": "2026-11-18T15:02:00Z", "status": "warning"}]},
        {"id": "alert-3", "name": "ledger-worker: settlement duration", "type": "transaction", "status": "resolved",
         "threshold": 900, "thresholdType": "above", "triggerLabel": "Resolved", "dateTriggered": "2026-11-16T03:00:00Z",
         "dateCreated": "2025-05-01T00:00:00Z", "project": "proj-ledger", "team": "team-pay",
         "history": [{"timestamp": "2026-11-16T03:00:00Z", "status": "resolved"}]},
    ]
    transactions = [
        {"id": "txn-1", "name": "POST /v2/carts/{cart_id}/totals", "project": "proj-api", "tpm": 412.0, "p50": 48, "p75": 71,
         "p95": 160, "p99": 420, "failureRate": 0.041, "apdex": 0.88, "totalCount": 590000, "stats24h": [400, 410, 405, 398, 420, 430, 415, 410, 402, 418, 425, 412]},
        {"id": "txn-2", "name": "POST /v2/checkout/confirm", "project": "proj-api", "tpm": 96.5, "p50": 210, "p75": 300,
         "p95": 640, "p99": 1300, "failureRate": 0.006, "apdex": 0.93, "totalCount": 139000, "stats24h": [90, 95, 99, 94, 97, 100, 96, 92, 95, 98, 97, 96]},
        {"id": "txn-3", "name": "/checkout", "project": "proj-web", "tpm": 520.2, "p50": 820, "p75": 1100, "p95": 2100,
         "p99": 3900, "failureRate": 0.004, "apdex": 0.9, "totalCount": 749000, "stats24h": [500, 510, 530, 525, 515, 520, 522, 519, 521, 518, 524, 520]},
    ]
    dashboards = [{"id": "dash-1", "title": "Checkout health", "dateCreated": "2025-03-01T00:00:00Z",
                   "createdBy": PEOPLE["marco"][4], "widgets": [
                       {"id": "w-1", "title": "Errors per release (checkout-api)", "type": "bar", "layout": {"x": 0, "y": 0, "w": 6, "h": 2},
                        "data": {"series": [{"label": "Errors", "color": "#E03E2F", "values": [12, 2210, 40, 4821]}],
                                 "xLabels": ["4.29.0", "4.30.0", "4.30.1", "4.31.0"]}},
                       {"id": "w-2", "title": "Crash free sessions", "type": "big_number", "layout": {"x": 6, "y": 0, "w": 3, "h": 1},
                        "data": {"value": "95.9%", "previousValue": "99.7%", "label": "checkout-api"}}]}]
    me = next(u for u in users if u["id"] == PEOPLE["sam"][4])
    return {
        "organization": {"id": "org-acme", "name": "Acme Commerce", "slug": "acme", "avatar": None,
                         "dateCreated": "2024-03-01T00:00:00Z", "teams": [t["id"] for t in teams],
                         "members": [u["id"] for u in users], "projects": [p["id"] for p in projects]},
        "currentUser": copy.deepcopy(me), "users": users, "teams": teams, "projects": projects,
        "issues": issues, "events": events, "alertRules": alert_rules, "releases": releases,
        "dashboards": dashboards, "transactions": transactions, "comments": comments,
        "selectedProject": "all", "selectedEnvironment": "all", "dateRange": "14d", "issueListSort": "lastSeen",
        "issueListTab": "unresolved", "issueSearchQuery": "is:unresolved", "selectedIssues": [],
        "bookmarkedIssues": [], "subscribedIssues": [],
    }


# ================================================================ GITHUB
GH_EXTRA_USERS = [("gh_org", "acme-commerce", "Acme Commerce"), ("gh_dependabot", "dependabot", "Dependabot")]


def gh_user(uid, username, name, mail=""):
    return {"id": uid, "username": username, "name": name, "email": mail, "avatar": avatar(name), "bio": "",
            "location": "", "company": "Acme Commerce", "website": "", "joinedAt": "2023-06-01T00:00:00Z"}


def gh_pr(rid, num, title, desc, head, author, status, created, merged=None, merged_by=None, reviewers=(), comments=(),
          checks=None, labels=()):
    return {"id": f"pr_{rid}_{num}", "repoId": rid, "number": num, "title": title, "description": desc,
            "baseBranch": "main", "compareBranch": head, "status": status, "isDraft": False, "authorId": gh(author) if author in PEOPLE else author,
            "assignees": [], "labels": list(labels), "milestone": None, "mergeStrategy": "merge" if merged else None,
            "mergedAt": merged, "mergedBy": gh(merged_by) if merged_by else None, "createdAt": created,
            "closedAt": merged if status in ("merged", "closed") else None,
            "comments": [{"id": f"prc_{rid}_{num}_{n}", "authorId": gh(a), "content": c, "date": d, "reactions": {}}
                         for n, (a, c, d) in enumerate(comments)],
            "reviewers": [{"userId": gh(u), "status": s, "date": d, "body": ""} for u, s, d in reviewers],
            "checks": checks if checks is not None else [{"name": "ci / test", "status": "success", "detail": "Successful in 6m"},
                                                          {"name": "ci / lint", "status": "success", "detail": "Successful in 1m"}]}


def build_github():
    users = [gh_user(gh(k), PEOPLE[k][1], PEOPLE[k][0], email(k)) for k in PEOPLE]
    users += [gh_user(uid, un, nm) for uid, un, nm in GH_EXTRA_USERS]
    me = copy.deepcopy(next(u for u in users if u["id"] == gh("sam")))
    repos = [
        {"id": "r_api", "ownerId": "gh_org", "name": "checkout-api", "description": "Cart, tax and checkout HTTP API (Flask).",
         "language": "Python", "languages": {"Python": 94.1, "Dockerfile": 3.2, "Shell": 2.7}, "stars": 14, "forks": 3,
         "watchers": 22, "isPrivate": True, "defaultBranch": "main", "topics": ["payments", "checkout", "flask"],
         "license": "", "homepage": "", "hasWiki": False, "hasIssues": True, "hasProjects": False,
         "updatedAt": "2026-11-18T16:40:00Z", "createdAt": "2022-04-11T00:00:00Z"},
        {"id": "r_web", "ownerId": "gh_org", "name": "checkout-web", "description": "Checkout front end (React).",
         "language": "TypeScript", "languages": {"TypeScript": 88.0, "CSS": 10.5, "HTML": 1.5}, "stars": 9, "forks": 1,
         "watchers": 18, "isPrivate": True, "defaultBranch": "main", "topics": ["checkout", "react"], "license": "",
         "homepage": "", "hasWiki": False, "hasIssues": True, "hasProjects": False,
         "updatedAt": "2026-11-17T21:00:00Z", "createdAt": "2022-04-11T00:00:00Z"},
        {"id": "r_ledger", "ownerId": "gh_org", "name": "ledger-worker", "description": "Settlement, refunds and ledger postings.",
         "language": "Python", "languages": {"Python": 100.0}, "stars": 5, "forks": 0, "watchers": 9, "isPrivate": True,
         "defaultBranch": "main", "topics": ["ledger"], "license": "", "homepage": "", "hasWiki": False,
         "hasIssues": True, "hasProjects": False, "updatedAt": "2026-11-17T22:40:00Z", "createdAt": "2023-01-09T00:00:00Z"},
        {"id": "r_infra", "ownerId": "gh_org", "name": "deploy-config", "description": "Helm values and deploy pipelines.",
         "language": "HCL", "languages": {"HCL": 61.0, "YAML": 39.0}, "stars": 3, "forks": 0, "watchers": 7,
         "isPrivate": True, "defaultBranch": "main", "topics": ["infra"], "license": "", "homepage": "",
         "hasWiki": False, "hasIssues": True, "hasProjects": False, "updatedAt": "2026-11-18T14:20:00Z",
         "createdAt": "2022-02-01T00:00:00Z"},
    ]

    # (number, title, description, head branch, author, status, created, merged, merged_by, reviewers, comments, sha)
    api_prs = [
        (1262, "Cache FX rates per request", "Avoids three calls to fx.internal per cart.\n\nRefs PAY-398", "jw/fx-cache", "jun", "merged",
         "2026-10-29T17:00:00Z", "2026-10-30T18:12:00Z", "jun", [("priya", "approved", "2026-10-30T16:00:00Z")], [], fake_sha("m1262")),
        (1265, "Return 409 on concurrent cart updates", "Closes CHK-214", "lm/cart-409", "leo", "merged",
         "2026-11-02T15:00:00Z", "2026-11-03T20:40:00Z", "leo", [("jun", "approved", "2026-11-03T19:00:00Z")], [], fake_sha("m1265")),
        (1268, "Bump structlog to 24.4", "Dependency update.", "dependabot/pip/structlog-24.4.0", "gh_dependabot", "merged",
         "2026-11-03T06:00:00Z", "2026-11-04T15:30:00Z", "marco", [("marco", "approved", "2026-11-04T15:20:00Z")], [], fake_sha("m1268")),
        (1271, "Postal code validation for CA regions", "Closes CHK-219", "lm/ca-postal", "leo", "merged",
         "2026-11-05T15:00:00Z", "2026-11-06T17:10:00Z", "leo", [("pooja", "approved", "2026-11-06T16:00:00Z")], [], fake_sha("m1271")),
        (1274, "Add idempotency header passthrough for refunds", "Needed by ledger-worker batch refunds.\n\nRefs PAY-427",
         "ab/refund-idem", "aisha", "merged", "2026-11-06T14:00:00Z", "2026-11-07T19:30:00Z", "aisha",
         [("priya", "approved", "2026-11-07T18:00:00Z")], [], fake_sha("m1274")),
        (1279, "Round tax per line item before FX conversion",
         "Rounds each line's tax to the source currency's minor unit before converting, so order totals match invoices.\n\nCloses PAY-412",
         "tk/pay-412-line-rounding", "tomasz", "merged", "2026-11-06T16:00:00Z", "2026-11-09T20:05:00Z", "tomasz",
         [("priya", "approved", "2026-11-09T18:30:00Z")], [], SHA_1279),
        (1281, "WIP: rounding table per currency", "Superseded by #1279.", "tk/rounding-table", "tomasz", "closed",
         "2026-11-04T10:00:00Z", None, None, [], [], None),
        (1283, 'Revert "Round tax per line item before FX conversion"',
         "Reverts #1279. JPY carts throw decimal.InvalidOperation in production (CHECKOUT-API-3P9).", "revert-1279-tax-rounding",
         "marco", "merged", "2026-11-10T17:20:00Z", "2026-11-10T17:30:00Z", "marco",
         [("tomasz", "approved", "2026-11-10T17:28:00Z")], [], SHA_1283),
        (1285, "Emit JSON logs from gunicorn workers", "Structured logs for the new log pipeline.", "jw/structlog-json", "jun",
         "merged", "2026-11-14T16:00:00Z", "2026-11-17T16:50:00Z", "jun", [("marco", "approved", "2026-11-17T15:00:00Z")], [], SHA_1285),
        (1287, "Re-land: round tax per line item before FX conversion",
         "Re-land of #1279, which was reverted in #1283 after the JPY failures.\n\nChanges since the first attempt:\n"
         "- quantize each line to the source currency's minor unit before conversion\n"
         "- context precision raised for high-value carts\n\nCloses PAY-412",
         "tk/pay-412-line-rounding-v2", "tomasz", "merged", "2026-11-13T15:00:00Z", "2026-11-17T18:40:00Z", "tomasz",
         [("priya", "approved", "2026-11-17T17:55:00Z"), ("marco", "approved", "2026-11-17T18:10:00Z")],
         [("priya", "Looks right to me now. Zero-decimal currencies still go through quantize, I'll do a follow-up for KRW.", "2026-11-17T17:55:00Z"),
          ("tomasz", "Thanks! Merging so it makes the 4.31.0 cut.", "2026-11-17T18:39:00Z")], SHA_1287),
        (1288, "Currency edge-case fixtures for tax tests", "Test data only.\n\nRefs PAY-433", "pn/currency-fixtures", "pooja",
         "merged", "2026-11-16T12:00:00Z", "2026-11-17T19:25:00Z", "priya", [("priya", "approved", "2026-11-17T19:20:00Z")], [], fake_sha("m1288")),
        (1290, "Receipt line labels use cart locale", "Closes CHK-227", "lm/receipt-locale", "leo", "open",
         "2026-11-17T22:00:00Z", None, None, [("jun", "pending", "2026-11-17T22:00:00Z")], [], None),
        (1291, "Skip quantize for zero-decimal currencies (KRW, JPY)",
         "Follow-up to #1287: zero-decimal currencies don't need the per-line quantize step.\n\nPart of PAY-431",
         "pn/krw-zero-decimal", "priya", "merged", "2026-11-17T18:50:00Z", "2026-11-17T19:55:00Z", "priya",
         [("tomasz", "approved", "2026-11-17T19:50:00Z")], [], SHA_1291),
        (1293, "Bump boto3 from 1.35.40 to 1.35.62", "Dependency update.", "dependabot/pip/boto3-1.35.62", "gh_dependabot",
         "open", "2026-11-18T06:00:00Z", None, None, [], [], None),
    ]
    prs, commits = [], []
    for (num, title, desc, head, author, status, created, merged, mby, revs, coms, sha) in api_prs:
        prs.append(gh_pr("r_api", num, title, desc, head, author, status, created, merged, mby, revs, coms))
        if sha:
            commits.append({"id": sha, "repoId": "r_api", "branch": "main",
                            "message": f"Merge pull request #{num} from {ORG}/{head}",
                            "authorId": gh(mby) if mby in PEOPLE else mby, "date": merged, "additions": 40 + num % 90,
                            "deletions": 5 + num % 30})
    # direct commits on main (no PR)
    for label, msg, who, date in [
        ("d1", "ci: pin python 3.12.4 in test image", "marco", "2026-11-02T11:00:00Z"),
        ("d2", "docs: document /v2/carts totals response", "jun", "2026-11-05T09:30:00Z"),
        ("d3", "chore: regenerate openapi client", "leo", "2026-11-08T14:10:00Z"),
        ("d4", "ci: cache pip wheels between jobs", "marco", "2026-11-12T10:00:00Z"),
        ("d5", "chore: tidy imports in tax package", "tomasz", "2026-11-15T13:00:00Z"),
    ]:
        commits.append({"id": fake_sha("direct-" + label), "repoId": "r_api", "branch": "main", "message": msg,
                        "authorId": gh(who), "date": date, "additions": 12, "deletions": 4})
    api_issues = [
        (1259, "Totals endpoint p99 regression after FX cache", "jun", "closed", "2026-10-31T10:00:00Z", "2026-11-03T10:00:00Z"),
        (1277, "Flaky test_refund_partial on CI", "marco", "open", "2026-11-08T09:00:00Z", None),
        (1289, "Document the rollback procedure for checkout-api", "helen", "open", "2026-11-17T21:30:00Z", None),
    ]
    issues = [{"id": f"is_api_{n}", "repoId": "r_api", "number": n, "title": t, "description": "", "status": st,
               "authorId": gh(a), "assignees": [], "labels": [], "milestone": None, "column": "todo", "isPinned": False,
               "reactions": {}, "createdAt": c, "closedAt": cl, "comments": []} for n, t, a, st, c, cl in api_issues]

    # checkout-web
    web_prs = [
        (871, "Show per-line tax in the totals panel", "Refs PAY-431", "pn/line-tax-panel", "priya", "merged",
         "2026-11-10T12:00:00Z", "2026-11-12T18:00:00Z", "priya", [("jun", "approved", "2026-11-12T17:00:00Z")], [], fake_sha("w871")),
        (877, "Lazy-load Stripe Elements", "Closes CHK-221", "jw/lazy-stripe", "jun", "merged", "2026-11-11T12:00:00Z",
         "2026-11-13T17:00:00Z", "jun", [("leo", "approved", "2026-11-13T16:00:00Z")], [], fake_sha("w877")),
        (882, "Gate line-item rounding display behind tax_line_rounding_v2",
         "Web side of PAY-431. The flag only affects how checkout-web renders line tax; the API is not flag-aware.",
         "pn/rounding-flag-web", "priya", "merged", "2026-11-16T15:00:00Z", "2026-11-17T21:00:00Z", "priya",
         [("jun", "approved", "2026-11-17T20:40:00Z")], [], SHA_WEB882),
        (884, "Fix minorUnits crash for carts without tax lines", "Closes CHK-231", "lm/minor-units-crash", "leo", "open",
         "2026-11-18T16:00:00Z", None, None, [("priya", "pending", "2026-11-18T16:00:00Z")], [], None),
    ]
    for (num, title, desc, head, author, status, created, merged, mby, revs, coms, sha) in web_prs:
        prs.append(gh_pr("r_web", num, title, desc, head, author, status, created, merged, mby, revs, coms))
        if sha:
            commits.append({"id": sha, "repoId": "r_web", "branch": "main",
                            "message": f"Merge pull request #{num} from {ORG}/{head}", "authorId": gh(mby),
                            "date": merged, "additions": 60, "deletions": 12})
    for rid, n, title, head, author, created, merged in [
        ("r_ledger", 214, "Batch refunds with idempotency keys", "ab/batch-refunds", "aisha", "2026-11-10T12:00:00Z", "2026-11-12T20:00:00Z"),
        ("r_ledger", 217, "Settlement task soft time limit 15m", "ab/settle-timeout", "aisha", "2026-11-17T12:00:00Z", "2026-11-17T22:40:00Z"),
        ("r_infra", 402, "checkout-api: raise HPA max to 24", "mb/hpa-24", "marco", "2026-11-14T12:00:00Z", "2026-11-14T15:00:00Z"),
        ("r_infra", 405, "Add deploy annotations for Sentry releases", "mb/sentry-annotations", "marco", "2026-11-17T12:00:00Z", "2026-11-18T14:20:00Z"),
    ]:
        prs.append(gh_pr(rid, n, title, "", head, author, "merged", created, merged, author, [], []))
        commits.append({"id": fake_sha(f"{rid}-{n}"), "repoId": rid, "branch": "main",
                        "message": f"Merge pull request #{n} from {ORG}/{head}", "authorId": gh(author), "date": merged,
                        "additions": 20, "deletions": 3})

    branch_names = {
        "r_api": ["main", "release/4.30", "release/4.31", "revert-1279-tax-rounding", "tk/pay-412-line-rounding-v2",
                  "pn/krw-zero-decimal", GOOD_BRANCH, "revert-1291-krw-rounding", "lm/receipt-locale",
                  "dependabot/pip/boto3-1.35.62", "pn/currency-fixtures"],
        "r_web": ["main", "lm/minor-units-crash", "pn/rounding-flag-web"],
        "r_ledger": ["main"], "r_infra": ["main"],
    }
    branches = [{"id": f"b_{rid}_{n}", "repoId": rid, "name": name,
                 "lastCommitId": SHA_1291 if name == "main" and rid == "r_api" else fake_sha(f"branch-{rid}-{name}")}
                for rid, names in branch_names.items() for n, name in enumerate(names)]
    files = [
        {"id": "f_api_1", "repoId": "r_api", "branch": "main", "path": "README.md", "language": "markdown",
         "content": "# checkout-api\n\nCart, tax and checkout HTTP API.\n\nReleases are cut from main and tagged `checkout-api@<version>`; "
                    "the deploy pipeline records which commit each release was built from.\n"},
        {"id": "f_api_2", "repoId": "r_api", "branch": "main", "path": "checkout_api/tax/rounding.py", "language": "python",
         "content": "from decimal import ROUND_HALF_EVEN, Decimal\n\nMINOR_UNIT_EXP = {'USD': Decimal('0.01'), 'EUR': Decimal('0.01'), "
                    "'JPY': Decimal('1'), 'KRW': Decimal('1')}\nZERO_DECIMAL = {'JPY', 'KRW'}\n\n\ndef round_line_items(lines, currency, rates):\n"
                    "    if currency.source in ZERO_DECIMAL:\n        return lines\n    exp = MINOR_UNIT_EXP[currency.source]\n    out = []\n"
                    "    for line in lines:\n        q = (line.tax * rates[line.currency]).quantize(exp, rounding=ROUND_HALF_EVEN)\n"
                    "        out.append(line.with_tax(q))\n    return out\n"},
        {"id": "f_api_3", "repoId": "r_api", "branch": "main", "path": "checkout_api/tax/totals.py", "language": "python",
         "content": "from . import rounding\n\n\ndef compute_totals(cart, rates):\n    lines = [line_tax(l, cart.region) for l in cart.lines]\n"
                    "    lines = rounding.round_line_items(lines, cart.currency, rates)\n    return Totals.from_lines(lines, cart.currency)\n"},
        {"id": "f_web_1", "repoId": "r_web", "branch": "main", "path": "README.md", "language": "markdown",
         "content": "# checkout-web\n\nCheckout front end.\n"},
        {"id": "f_ledger_1", "repoId": "r_ledger", "branch": "main", "path": "README.md", "language": "markdown",
         "content": "# ledger-worker\n"},
        {"id": "f_infra_1", "repoId": "r_infra", "branch": "main", "path": "README.md", "language": "markdown",
         "content": "# deploy-config\n"},
    ]
    actions = [{"id": f"run_{n}", "repoId": "r_api", "name": "ci", "status": "success", "runNumber": 3000 + n,
                "branch": "main", "event": "push", "duration": "6m 12s", "date": d, "triggeredBy": u}
               for n, (d, u) in enumerate([("2026-11-17T16:51:00Z", gh("jun")), ("2026-11-17T18:41:00Z", gh("tomasz")),
                                           ("2026-11-17T19:26:00Z", gh("priya")), ("2026-11-17T19:56:00Z", gh("priya"))], start=1)]
    labels = [{"id": f"lab_{r}_{n}", "repoId": r, "name": nm, "color": c, "description": ""}
              for r in ("r_api", "r_web") for n, (nm, c) in enumerate([("bug", "#d73a4a"), ("dependencies", "#0366d6"), ("revert", "#e99695")])]
    notifications = [
        {"id": "n_1", "type": "review_requested", "repoId": "r_api", "issueNumber": 1290, "title": "Receipt line labels use cart locale", "isRead": True, "date": "2026-11-17T22:00:00Z"},
        {"id": "n_2", "type": "mention", "repoId": "r_api", "issueNumber": 1289, "title": "Document the rollback procedure for checkout-api", "isRead": False, "date": "2026-11-17T21:30:00Z"},
    ]
    return {"currentUser": me, "users": users, "repos": repos, "branches": branches, "files": files, "commits": commits,
            "issues": issues, "pullRequests": prs, "wiki": [], "actions": actions, "notifications": notifications,
            "labels": labels, "milestones": [], "discussions": [], "releases": []}


# ================================================================ LINEAR
L_TEAMS = [("t1", "Payments", "PAY", "💳", "#5e6ad2"), ("t2", "Checkout", "CHK", "🛒", "#26b5ce"), ("t3", "SRE", "SRE", "🛠", "#f2994a")]
L_STATES = [("triage", "Triage", "triage", "#8a8f98"), ("backlog", "Backlog", "backlog", "#8a8f98"),
            ("todo", "Todo", "unstarted", "#e2e2e3"), ("in_progress", "In Progress", "started", "#f2c94c"),
            ("in_review", "In Review", "started", "#5e6ad2"), ("done", "Done", "completed", "#27a644"),
            ("canceled", "Canceled", "canceled", "#8a8f98")]
TEAM_PREFIX = {"t1": "pay", "t2": "chk", "t3": "sre"}


def ws(team, state):
    return f"ws_{TEAM_PREFIX[team]}_{state}"


def build_linear():
    users = [{"id": PEOPLE[k][3], "name": PEOPLE[k][0], "email": email(k), "avatarUrl": avatar(PEOPLE[k][0]),
              "displayName": PEOPLE[k][0].split()[0], "role": "Admin" if k in ("sam", "helen") else "Member", "active": True}
             for k in PEOPLE]
    members = {"t1": ["priya", "tomasz", "helen", "aisha", "nadia", "sam"], "t2": ["jun", "leo", "pooja", "priya", "sam"],
               "t3": ["sam", "marco", "helen"]}
    teams = [{"id": tid, "name": name, "key": key, "icon": icon, "color": color,
              "memberIds": [PEOPLE[m][3] for m in members[tid]],
              "workflowStates": [{"id": ws(tid, sid), "name": nm, "category": cat, "color": col, "position": p, "teamId": tid}
                                 for p, (sid, nm, cat, col) in enumerate(L_STATES)],
              "triageEnabled": False, "cycleEnabled": True, "cycleDuration": 2, "activeCycleId": f"c_{tid}"}
             for tid, name, key, icon, color in L_TEAMS]
    labels = [{"id": "l_bug", "name": "Bug", "color": "#eb5757", "teamId": None},
              {"id": "l_feat", "name": "Feature", "color": "#bb87fc", "teamId": None},
              {"id": "l_impr", "name": "Improvement", "color": "#4ea7fc", "teamId": None},
              {"id": "l_incident", "name": "Incident", "color": "#f2994a", "teamId": None},
              {"id": "l_tech", "name": "Tech debt", "color": "#8a8f98", "teamId": None}]
    projects = [{"id": "p_rounding", "name": "Multi-currency tax accuracy", "description": "Make order totals match invoices in every currency.",
                 "icon": "🧮", "color": "#5e6ad2", "status": "started", "health": "atRisk", "leadId": PEOPLE["priya"][3],
                 "memberIds": [PEOPLE[k][3] for k in ("priya", "tomasz", "nadia")], "teamIds": ["t1"],
                 "targetDate": "2026-12-15", "startDate": "2026-10-01", "progress": 0.6,
                 "createdAt": "2026-09-20T00:00:00Z", "updatedAt": "2026-11-17T19:00:00Z"},
                {"id": "p_refunds", "name": "Batch refunds", "description": "Idempotent batch refunds in ledger-worker.",
                 "icon": "↩️", "color": "#26b5ce", "status": "started", "health": "onTrack", "leadId": PEOPLE["aisha"][3],
                 "memberIds": [PEOPLE["aisha"][3]], "teamIds": ["t1"], "targetDate": "2026-11-30", "startDate": "2026-10-15",
                 "progress": 0.85, "createdAt": "2026-10-10T00:00:00Z", "updatedAt": "2026-11-13T19:00:00Z"}]
    cycles = [{"id": f"c_{tid}", "number": 23, "name": "Cycle 23", "teamId": tid, "startsAt": "2026-11-09",
               "endsAt": "2026-11-22", "isActive": True, "isCompleted": False, "progress": 0.5} for tid, *_ in L_TEAMS]

    # (id, team, number, title, state, priority, assignee, creator, labels, project, created, updated, completed, description)
    rows = [
        ("li_pay398", "t1", 398, "Cache FX rates for the life of a request", "done", 3, "jun", "priya", ["l_impr"], "p_rounding",
         "2026-10-20T10:00:00Z", "2026-10-30T18:20:00Z", "2026-10-30T18:20:00Z", "Three calls to fx.internal per cart is too many."),
        ("li_pay405", "t1", 405, "Refund webhooks arrive before ledger posting", "in_progress", 2, "aisha", "helen", ["l_bug"], "p_refunds",
         "2026-10-24T10:00:00Z", "2026-11-16T12:00:00Z", None, "Ordering issue between webhook fan-out and ledger posting."),
        ("li_pay409", "t1", 409, "Invoice PDF shows tax rounded differently from order total", "backlog", 3, None, "nadia", ["l_bug"],
         "p_rounding", "2026-10-26T10:00:00Z", "2026-10-26T10:00:00Z", None, "Reported by finance. Probably fixed by the rounding work, re-check after."),
        ("li_pay412", "t1", 412, "Tax totals drift by one minor unit on multi-currency carts", "canceled", 2, "tomasz", "nadia",
         ["l_bug"], "p_rounding", "2026-10-28T10:00:00Z", "2026-11-12T16:10:00Z", None,
         "Customers paying in EUR and JPY see order totals one minor unit off from the invoice. Tax is converted first and rounded "
         "once at the end.\n\nDiscussion so far in #payments."),
        ("li_pay418", "t1", 418, "Alert when FX rates are older than 15 minutes", "todo", 3, "marco", "priya", ["l_impr"], None,
         "2026-11-02T10:00:00Z", "2026-11-02T10:00:00Z", None, ""),
        ("li_pay421", "t1", 421, "Remove legacy /v1/totals endpoint", "backlog", 4, None, "tomasz", ["l_tech"], None,
         "2026-11-03T10:00:00Z", "2026-11-03T10:00:00Z", None, "No traffic since September."),
        ("li_pay424", "t1", 424, "Refund batch dry-run mode", "done", 3, "aisha", "aisha", ["l_feat"], "p_refunds",
         "2026-11-04T10:00:00Z", "2026-11-11T10:00:00Z", "2026-11-11T10:00:00Z", ""),
        ("li_pay427", "t1", 427, "Batch refunds: idempotency keys end to end", "done", 2, "aisha", "helen", ["l_feat"], "p_refunds",
         "2026-11-05T10:00:00Z", "2026-11-13T18:30:00Z", "2026-11-13T18:30:00Z", "Rollout notes in #ledger-rollouts."),
        ("li_pay431", "t1", 431, "Line-item tax rounding before FX conversion (re-land)", "done", 2, "priya", "helen", ["l_bug"],
         "p_rounding", "2026-11-12T16:00:00Z", "2026-11-17T18:45:00Z", "2026-11-17T18:45:00Z",
         "Supersedes PAY-412 (closed as duplicate). Full repro: EUR cart with 7 lines at 19% VAT converts to USD one cent high.\n\n"
         "Plan: quantize each line to the source currency's minor unit before FX conversion, with higher decimal context "
         "precision for large carts. Tomasz implements in checkout-api, Priya owns the ticket, reviews and does the web side.\n\n"
         "Rollout: ships with checkout-api 4.31.0. Rollout and rollback calls for this change are made in #ledger-rollouts, not #payments."),
        ("li_pay433", "t1", 433, "Currency edge-case fixtures for tax tests", "done", 3, "pooja", "priya", ["l_impr"], "p_rounding",
         "2026-11-13T10:00:00Z", "2026-11-17T19:30:00Z", "2026-11-17T19:30:00Z", ""),
        ("li_pay435", "t1", 435, "Zero-decimal currencies skip per-line quantize", "done", 3, "priya", "priya", ["l_bug"], "p_rounding",
         "2026-11-17T18:30:00Z", "2026-11-17T20:00:00Z", "2026-11-17T20:00:00Z", "Follow-up to PAY-431 for KRW/JPY. checkout-api#1291."),
        ("li_pay437", "t1", 437, "Settlement report: add currency column", "todo", 4, "nadia", "nadia", ["l_feat"], None,
         "2026-11-17T10:00:00Z", "2026-11-17T10:00:00Z", None, ""),
        ("li_pay438", "t1", 438, "Reconcile Stripe payout fees per currency", "backlog", 3, None, "helen", ["l_feat"], None,
         "2026-11-17T12:00:00Z", "2026-11-17T12:00:00Z", None, ""),
        ("li_chk214", "t2", 214, "Return 409 on concurrent cart updates", "done", 2, "leo", "jun", ["l_bug"], None,
         "2026-10-29T10:00:00Z", "2026-11-03T21:00:00Z", "2026-11-03T21:00:00Z", ""),
        ("li_chk219", "t2", 219, "CA postal code validation", "done", 3, "leo", "pooja", ["l_bug"], None,
         "2026-11-03T10:00:00Z", "2026-11-06T17:20:00Z", "2026-11-06T17:20:00Z", ""),
        ("li_chk221", "t2", 221, "Lazy-load Stripe Elements", "done", 3, "jun", "jun", ["l_impr"], None,
         "2026-11-06T10:00:00Z", "2026-11-13T17:10:00Z", "2026-11-13T17:10:00Z", ""),
        ("li_chk225", "t2", 225, "Address autocomplete for Japan", "in_progress", 3, "jun", "nadia", ["l_feat"], None,
         "2026-11-10T10:00:00Z", "2026-11-17T10:00:00Z", None, ""),
        ("li_chk227", "t2", 227, "Receipt line labels use cart locale", "in_review", 3, "leo", "pooja", ["l_bug"], None,
         "2026-11-12T10:00:00Z", "2026-11-17T22:05:00Z", None, ""),
        ("li_chk229", "t2", 229, "Checkout page CLS above 0.1 on mobile", "todo", 3, None, "jun", ["l_impr"], None,
         "2026-11-14T10:00:00Z", "2026-11-14T10:00:00Z", None, ""),
        ("li_chk231", "t2", 231, "TotalsPanel crashes when a cart has no tax lines", "in_progress", 1, "leo", "leo", ["l_bug"], None,
         "2026-11-18T15:05:00Z", "2026-11-18T16:00:00Z", None, "Sentry CHECKOUT-WEB-1KD. Fix in checkout-web#884."),
        ("li_chk232", "t2", 232, "Drop IE11 polyfills", "backlog", 4, None, "leo", ["l_tech"], None,
         "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z", None, ""),
        ("li_sre88", "t3", 88, "Deploy annotations for Sentry releases", "done", 3, "marco", "marco", ["l_impr"], None,
         "2026-11-10T10:00:00Z", "2026-11-18T14:25:00Z", "2026-11-18T14:25:00Z", "deploy-config#405"),
        ("li_sre90", "t3", 90, "checkout-api HPA max 24", "done", 3, "marco", "marco", ["l_impr"], None,
         "2026-11-13T10:00:00Z", "2026-11-14T15:05:00Z", "2026-11-14T15:05:00Z", ""),
        ("li_sre92", "t3", 92, "Quarterly DR drill (Nov)", "in_progress", 2, "sam", "helen", [], None,
         "2026-11-01T10:00:00Z", "2026-11-18T16:00:00Z", None, "Runs Wednesday 11/18 from 09:00 PT."),
        ("li_sre94", "t3", 94, "notifications-svc SMTP connection limits", "done", 3, "marco", "marco", ["l_incident"], None,
         "2026-11-12T17:35:00Z", "2026-11-12T19:00:00Z", "2026-11-12T19:00:00Z", ""),
        ("li_sre95", "t3", 95, "Rotate PagerDuty escalation for December", "todo", 4, "sam", "sam", [], None,
         "2026-11-16T10:00:00Z", "2026-11-16T10:00:00Z", None, ""),
        ("li_sre97", "t3", 97, "Write up 4.30.0 rounding incident", "done", 3, "marco", "helen", ["l_incident"], None,
         "2026-11-10T19:00:00Z", "2026-11-13T12:00:00Z", "2026-11-13T12:00:00Z", "Postmortem for the first rounding attempt (PAY-412)."),
    ]
    issues = []
    for n, (iid, tid, num, title, st, prio, who, creator, labs, proj, created, updated, completed, desc) in enumerate(rows):
        key = next(t[2] for t in L_TEAMS if t[0] == tid)
        issues.append({"id": iid, "identifier": f"{key}-{num}", "number": num, "title": title, "description": desc,
                       "stateId": ws(tid, st), "priority": prio, "estimate": None,
                       "assigneeId": PEOPLE[who][3] if who else None, "creatorId": PEOPLE[creator][3], "teamId": tid,
                       "projectId": proj, "cycleId": f"c_{tid}" if st in ("todo", "in_progress", "in_review") else None,
                       "labelIds": labs, "parentId": None, "dueDate": None,
                       "subscriberIds": [PEOPLE[creator][3]] + ([PEOPLE[who][3]] if who and who != creator else []),
                       "relationIds": [], "createdAt": created, "updatedAt": updated, "completedAt": completed,
                       "sortOrder": 1000 + n})
    comments = [
        ("cm_412_1", "li_pay412", "tomasz", "2026-11-06T16:05:00Z", "PR up: acme-commerce/checkout-api#1279"),
        ("cm_412_2", "li_pay412", "marco", "2026-11-10T17:35:00Z",
         "Reverted in checkout-api#1283, JPY carts were throwing InvalidOperation in prod (CHECKOUT-API-3P9)."),
        ("cm_412_3", "li_pay412", "helen", "2026-11-12T16:10:00Z",
         "Closing this as a duplicate of PAY-431, which has the full repro and the redesign. Priya owns the re-land, track everything there from now on."),
        ("cm_431_1", "li_pay431", "tomasz", "2026-11-13T15:05:00Z", "Re-land PR: checkout-api#1287 (kept the old branch name, sorry)."),
        ("cm_431_2", "li_pay431", "priya", "2026-11-17T18:45:00Z", "Merged, goes out with checkout-api 4.31.0 tomorrow morning. KRW/JPY follow-up is PAY-435."),
        ("cm_427_1", "li_pay427", "aisha", "2026-11-13T18:30:00Z", "Live in prod, no duplicate refunds since."),
        ("cm_chk231_1", "li_chk231", "leo", "2026-11-18T16:00:00Z", "Only affects carts with zero tax lines, unrelated to rounding."),
    ]
    comments = [{"id": cid, "body": body, "issueId": iid, "userId": PEOPLE[who][3], "createdAt": ts, "updatedAt": ts,
                 "parentId": None} for cid, iid, who, ts, body in comments]
    notifications = [
        {"id": "ln_1", "type": "issue_assigned", "actorId": PEOPLE["helen"][3], "issueId": "li_sre92", "projectId": None,
         "title": "SRE-92 assigned to you", "body": "Quarterly DR drill (Nov)", "isRead": True, "isSnoozed": False,
         "isArchived": False, "createdAt": "2026-11-01T10:00:00Z"},
        {"id": "ln_2", "type": "comment", "actorId": PEOPLE["priya"][3], "issueId": "li_pay431", "projectId": None,
         "title": "Priya commented on PAY-431", "body": "Merged, goes out with checkout-api 4.31.0 tomorrow morning.",
         "isRead": False, "isSnoozed": False, "isArchived": False, "createdAt": "2026-11-17T18:45:00Z"},
    ]
    return {
        "currentUserId": PEOPLE["sam"][3],
        "workspace": {"id": "w_acme", "name": "Acme Commerce", "urlKey": "acme"},
        "users": users, "teams": teams, "issues": issues, "labels": labels, "projects": projects, "cycles": cycles,
        "comments": comments, "notifications": notifications, "views": [], "favorites": [], "issueRelations": [],
        "issueCounters": {"t1": 438, "t2": 232, "t3": 97}, "sidebarCollapsed": False,
        "teamSectionsExpanded": {"t1": True, "t2": True, "t3": True},
    }


# ================================================================ SLACK
THREAD = "th_pay431"
CHANNEL = "ledger-rollouts"
DECOY_THREAD = "th_pay412"


def smsg(mid, who, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": PEOPLE[who][2] if who in PEOPLE else who, "content": text, "timestamp": ts,
            "threadId": thread, "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack():
    users = [{"userId": PEOPLE[k][2], "fullName": PEOPLE[k][0], "displayName": PEOPLE[k][0].split()[0], "email": email(k),
              "avatar": avatar(PEOPLE[k][0]), "title": PEOPLE[k][5],
              "status": "online" if k in ("sam", "priya", "marco", "helen") else "away", "statusMessage": "",
              "statusEmoji": "", "timeZone": "America/Los_Angeles"} for k in PEOPLE]
    users.append({"userId": "U_PD", "fullName": "PagerDuty", "displayName": "PagerDuty", "email": "pagerduty@apps.acme-commerce.com", "avatar": avatar("PagerDuty"),
                  "title": "App", "status": "online", "statusMessage": "", "statusEmoji": "", "timeZone": "UTC"})
    users[0]["statusMessage"] = "DR drill 09:00-12:00"
    everyone = [u["userId"] for u in users]

    def channel(cid, desc, pinned=(), starred=False):
        return {"channelId": cid, "name": cid, "description": desc, "topic": desc, "isPrivate": False, "isStarred": starred,
                "members": everyone, "createdBy": "U_HELEN", "createdAt": "2024-05-01T17:00:00Z",
                "pinnedMessages": list(pinned), "unreadCount": 0}

    rollouts = [
        smsg("m_lr1", "aisha", "2026-11-12T18:00:00Z",
             "Rollout note for PAY-427 (batch refund idempotency): ledger-worker 2.14.0 goes to prod tomorrow morning. "
             "Rollback is a redeploy of 2.13.2, there's no data migration."),
        smsg("m_lr2", "priya", "2026-11-16T18:05:00Z",
             "Rollout note for PAY-431 (line-item tax rounding re-land): ships with checkout-api 4.31.0, prod deploy Wednesday morning. "
             "Rollback plan if prod errors spike: switch off the `tax_line_rounding_v2` flag, no code revert needed.",
             reactions=[{"emoji": "👍", "users": ["U_HELEN", "U_TOMASZ"]}]),
        smsg("m_lr3", "marco", "2026-11-18T14:36:00Z", "checkout-api 4.31.0 is live in production. checkout-web 4.31.0 follows at 06:45."),
    ]
    rollout_replies = [
        smsg("m_lr1a", "aisha", "2026-11-13T18:35:00Z", "2.14.0 is out, no duplicate refunds so far.", thread="th_pay427"),
        smsg("m_t1", "marco", "2026-11-17T17:02:00Z",
             "Careful, that flag is only read by checkout-web. checkout-api computes totals before it ever looks at flags, "
             "so switching it off won't change anything on the API side.", thread=THREAD),
        smsg("m_t2", "priya", "2026-11-17T20:15:00Z",
             "You're right, thanks Marco. Updated plan for checkout-api then: no flag, we revert. I've pushed revert branches for both "
             "rounding PRs, `revert-1287-line-rounding` and `revert-1291-krw-rounding`. If prod breaks, whoever is on call opens a PR "
             "into main from the revert branch for the PR that's in the release that's actually throwing, adds me as reviewer and "
             "leaves it unmerged, I'll review and merge it myself. Then move PAY-431 back to In Progress, assign the Sentry issue to me "
             "and drop the revert PR number in this thread.", thread=THREAD),
        smsg("m_t3", "helen", "2026-11-17T21:00:00Z",
             "+1. And leave the Sentry issue unresolved until the revert is actually deployed, we resolve it from the deploy.", thread=THREAD),
    ]
    payments = [
        smsg("m_p1", "tomasz", "2026-11-09T20:10:00Z", "#1279 (PAY-412, per-line tax rounding) is merged, goes out with checkout-api 4.30.0 tomorrow."),
        smsg("m_p2", "marco", "2026-11-10T17:15:00Z",
             "4.30.0 is throwing on JPY carts in prod (CHECKOUT-API-3P9). Reverting #1279 from `revert-1279-tax-rounding`."),
        smsg("m_p3", "helen", "2026-11-12T16:15:00Z", "FYI PAY-412 is closed as a duplicate of PAY-431, Priya owns the re-land."),
        smsg("m_p4", "nadia", "2026-11-16T17:00:00Z", "Finance asked whether the invoice PDF fix (PAY-409) can ride along with the rounding work. Not this week."),
        smsg("m_p5", "aisha", "2026-11-17T23:10:00Z", "ledger-worker 2.14.1 on staging, prod tomorrow 07:30."),
    ]
    payments_replies = [
        smsg("m_p2a", "tomasz", "2026-11-10T17:22:00Z",
             "Ack, approved. If anything like this happens again with the rounding change just do the same: open the revert from the "
             "revert branch, ping me for review and merge once CI is green.", thread=DECOY_THREAD),
        smsg("m_p2b", "marco", "2026-11-10T17:58:00Z", "4.30.1 with the revert is out, errors stopped.", thread=DECOY_THREAD),
    ]
    oncall = [
        smsg("m_o1", "U_PD", "2026-11-18T14:52:10Z",
             "Triggered #PD-48213 (high urgency): [Sentry] CHECKOUT-API-3QK decimal.InvalidOperation in round_line_items, production. Assigned to Sam Okafor."),
        smsg("m_o2", "sam", "2026-11-18T14:54:00Z", "Ack, looking."),
        smsg("m_o3", "marco", "2026-11-18T15:01:00Z", "Started right after the 06:31 checkout-api deploy. Mostly EUR/GBP carts converting to USD."),
        smsg("m_o4", "sam", "2026-11-18T16:50:00Z", "I'm in the DR drill until noon, handing this one off."),
    ]
    general = [
        smsg("m_g1", "helen", "2026-11-16T16:00:00Z", "Reminder: quarterly DR drill is Wednesday 09:00-12:00 PT. SRE on-call is covering from the drill room."),
        smsg("m_g2", "nadia", "2026-11-17T18:00:00Z", "Black Friday code freeze starts Monday 11/23. Anything risky needs to land before then."),
    ]
    sre = [
        smsg("m_s1", "marco", "2026-11-17T23:30:00Z", "deploy-config#405 merged, Sentry now gets deploy annotations for every prod release."),
        smsg("m_s2", "sam", "2026-11-18T08:00:00Z", "Morning. Pager is mine this week."),
    ]
    messages = {"general": general, "payments": payments + payments_replies, CHANNEL: rollouts + rollout_replies,
                "checkout-oncall": oncall, "sre": sre, "random": [smsg("m_r1", "leo", "2026-11-17T20:00:00Z", "Who left the oat milk out again")]}
    threads = {
        THREAD: {"threadId": THREAD, "parentMessageId": "m_lr2", "channelId": CHANNEL, "dmId": None,
                 "replies": ["m_t1", "m_t2", "m_t3"], "followers": ["U_PRIYA", "U_MARCO", "U_HELEN"]},
        "th_pay427": {"threadId": "th_pay427", "parentMessageId": "m_lr1", "channelId": CHANNEL, "dmId": None,
                      "replies": ["m_lr1a"], "followers": ["U_AISHA"]},
        DECOY_THREAD: {"threadId": DECOY_THREAD, "parentMessageId": "m_p2", "channelId": "payments", "dmId": None,
                       "replies": ["m_p2a", "m_p2b"], "followers": ["U_MARCO", "U_TOMASZ"]},
    }
    me = copy.deepcopy(users[0])
    return {
        "currentUser": me,
        "workspace": {"workspaceId": "ws_acme", "workspaceName": "Acme Commerce", "icon": avatar("Acme Commerce")},
        "users": users,
        "channels": [channel("general", "Company-wide announcements"),
                     channel("payments", "Payments team"),
                     channel(CHANNEL, "Rollout and rollback coordination for payments and ledger changes", pinned=["m_lr2"]),
                     channel("checkout-oncall", "Pages and on-call chatter for checkout services", starred=True),
                     channel("sre", "SRE team"), channel("random", "Anything goes")],
        "messages": messages, "threads": threads, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


# ================================================================ runs
GOLDEN_PLAN = {
    "branch": GOOD_BRANCH, "reviewer": "priya", "merge": False,
    "ticket": "li_pay431", "reopen": True, "linear_pr": True,
    "sentry_assignee": "priya", "sentry_ticket": "PAY-431", "sentry_pr": True, "resolve": False,
    "slack": "thread", "slack_pr": True,
    "out": {"sentry_issue": SENTRY_ISSUE, "release": RELEASE, "commit_sha": SHA_1287, "pull_request": 1287,
            "linear_ticket": "PAY-431", "owner": "Priya Natarajan", "followup_pr": "PR"},
}


def plan_with(**kw):
    p = copy.deepcopy(GOLDEN_PLAN)
    out = kw.pop("out", None)
    p.update(kw)
    if out:
        p["out"].update(out)
    return p


def apply_run(seed, plan):
    s, g, li, sl = (copy.deepcopy(seed[k]) for k in ("sentry", "github", "linear", "slack"))
    pr_num = None
    if plan["branch"]:
        pr_num = NEXT_PR
        reverted = plan["branch"].split("-")[1]
        title_of = {p["number"]: p["title"] for p in g["pullRequests"] if p["repoId"] == "r_api"}
        new_pr = {"id": "gold_pr_revert", "repoId": "r_api", "number": pr_num,
                  "title": f'Revert "{title_of[int(reverted)]}"',
                  "description": f"Reverts #{reverted}. Production errors after {RELEASE} (Sentry {SENTRY_ISSUE}). "
                                 f"Waiting on review before merge.",
                  "status": "open", "isDraft": False, "authorId": gh("sam"), "baseBranch": "main",
                  "compareBranch": plan["branch"], "reviewers": [{"userId": gh(plan["reviewer"]), "status": "pending"}],
                  "assignees": [], "comments": [], "checks": [], "createdAt": RUN_TS}
        if plan["merge"]:
            new_pr.update({"status": "merged", "mergedAt": RUN_TS, "mergedBy": gh("sam"), "mergeStrategy": "merge"})
        g["pullRequests"].append(new_pr)
    pr_ref = f"acme-commerce/checkout-api#{pr_num}" if pr_num else "none yet"

    if plan["ticket"]:
        issue = next(i for i in li["issues"] if i["id"] == plan["ticket"])
        if plan["reopen"]:
            issue["stateId"] = ws("t1", "in_progress")
            issue["updatedAt"] = RUN_TS
        body = (f"Regressed in production after {RELEASE} (Sentry {SENTRY_ISSUE}). "
                + (f"Revert PR opened: {pr_ref}, left unmerged for Priya's review." if plan["linear_pr"] and pr_num
                   else "Rollback in progress."))
        li["comments"].append({"id": "gold_cm_1", "body": body, "issueId": plan["ticket"], "userId": PEOPLE["sam"][3],
                               "createdAt": RUN_TS, "updatedAt": RUN_TS, "parentId": None})

    sissue = next(i for i in s["issues"] if i["id"] == "issue-3qk")
    if plan["sentry_assignee"]:
        sissue["assignee"] = PEOPLE[plan["sentry_assignee"]][4]
    if plan["resolve"]:
        sissue["status"] = "resolved"
    text = f"Traced to {RELEASE} -> acme-commerce/checkout-api#1287. Linear: {plan['sentry_ticket']}."
    if plan["sentry_pr"] and pr_num:
        text += f" Revert PR: #{pr_num} (unmerged, waiting on review). Leave unresolved until the revert is deployed."
    s.setdefault("comments", {}).setdefault("issue-3qk", []).append(
        {"id": "comment-gold-1", "author": "Sam Okafor", "text": text, "timestamp": RUN_TS, "type": "comment"})

    if plan["slack"]:
        content = (f"On call here. {SENTRY_ISSUE} started right after the {RELEASE} prod deploy. "
                   + (f"Revert PR is up: {pr_ref} (from {plan['branch']}), you're the reviewer and it's not merged. "
                      if plan["slack_pr"] and pr_num else "Switched off tax_line_rounding_v2. ")
                   + "PAY-431 is back In Progress and the Sentry issue is assigned to you.")
        if plan["slack"] == "thread":
            msg = smsg("gold_m_1", "sam", RUN_TS, content, thread=THREAD)
            sl["messages"][CHANNEL].append(msg)
            sl["threads"][THREAD]["replies"].append("gold_m_1")
        elif plan["slack"] == "payments":
            msg = smsg("gold_m_1", "sam", RUN_TS, content, thread=DECOY_THREAD)
            sl["messages"]["payments"].append(msg)
            sl["threads"][DECOY_THREAD]["replies"].append("gold_m_1")

    out = None
    if plan["out"] is not None:
        out = dict(plan["out"])
        out["followup_pr"] = pr_num if out["followup_pr"] == "PR" else out["followup_pr"]
    return {"sentry": s, "github": g, "linear": li, "slack": sl}, out


VARIANTS = {
    # trusts every first-found value: PR's "Closes PAY-412", PAY-412's assignee and channel, the stale
    # #payments plan (revert branch of the first attempt, Tomasz reviews, resolve), posts in #payments
    "naive": plan_with(branch="revert-1279-tax-rounding", reviewer="tomasz", ticket="li_pay412", sentry_assignee="tomasz",
                       sentry_ticket="PAY-412", resolve=True, slack="payments",
                       out={"linear_ticket": "PAY-412", "owner": "Tomasz Kowalski"}),
    # careful everywhere except the deploy-log hop: takes the newest checkout-api row (4.31.1 on staging)
    "wrong_hop": plan_with(branch="revert-1291-krw-rounding",
                           out={"commit_sha": SHA_1291, "pull_request": 1291}),
    # follows the superseded top-level plan (flag) instead of the thread correction
    "flag_plan": plan_with(branch=None, ticket=None, sentry_assignee=None, sentry_pr=False, slack_pr=False,
                           out={"followup_pr": None}),
    "slip_reviewer": plan_with(reviewer="tomasz"),
    "slip_dup_ticket": plan_with(ticket="li_pay412", sentry_ticket="PAY-412", out={"linear_ticket": "PAY-412"}),
    "slip_resolved": plan_with(resolve=True),
    "slip_merged": plan_with(merge=True),
}


def js_norm(v):
    """Match how the mocks re-serialize state in JS (integral floats become ints)."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: js_norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [js_norm(x) for x in v]
    return v


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(js_norm(value), ensure_ascii=False, indent=1))


def main(out: Path):
    seed = {"sentry": build_sentry(), "github": build_github(), "linear": build_linear(), "slack": build_slack()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, gold_out = apply_run(seed, GOLDEN_PLAN)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_json(out / "golden_output" / "incident_trace.json", gold_out)

    (out / "input").mkdir(parents=True, exist_ok=True)
    with (out / "input" / "deploys.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["deployed_at", "service", "environment", "release", "git_sha", "deployed_by", "status"])
        w.writerows(DEPLOYS)

    write_json(out / "expected.json", {
        "clock": CLOCK, "timezone": "America/Los_Angeles",
        "chain": {"sentry_issue": SENTRY_ISSUE, "sentry_issue_id": "issue-3qk", "release": RELEASE,
                  "environment": "production", "commit_sha": SHA_1287, "pull_request": 1287,
                  "cited_ticket": "PAY-412", "linear_ticket": "PAY-431", "owner": "Priya Natarajan"},
        "github": {"repo_id": "r_api", "repo": "acme-commerce/checkout-api", "revert_branch": GOOD_BRANCH,
                   "wrong_branches": ["revert-1291-krw-rounding", "revert-1279-tax-rounding"], "base_branch": "main",
                   "reviewer_user_id": gh("priya"), "reviewer_username": "pnatarajan",
                   "pr_author_user_id": gh("tomasz"), "me_user_id": gh("sam"),
                   "expected_new_pr_number": NEXT_PR,
                   "note": "new PR number is whatever the UI assigned to the PR with compareBranch == revert_branch; "
                           "downstream checks must use that actual number"},
        "linear": {"ticket_issue_id": "li_pay431", "ticket": "PAY-431", "in_progress_state": ws("t1", "in_progress"),
                   "seed_state": ws("t1", "done"), "duplicate_issue_id": "li_pay412", "duplicate_ticket": "PAY-412",
                   "me": PEOPLE["sam"][3]},
        "sentry": {"issue_id": "issue-3qk", "owner_user_id": PEOPLE["priya"][4], "wrong_user_id": PEOPLE["tomasz"][4],
                   "me_name": "Sam Okafor", "required_status": "unresolved"},
        "slack": {"channel": CHANNEL, "thread": THREAD, "parent": "m_lr2", "me": PEOPLE["sam"][2],
                  "decoy_channel": "payments", "decoy_thread": DECOY_THREAD},
        "output": {"path": "/workspace/output/incident_trace.json",
                   "keys": ["sentry_issue", "release", "commit_sha", "pull_request", "linear_ticket", "owner", "followup_pr"]},
        "decoy_shas": {"checkout-web@4.31.0": SHA_WEB882, "checkout-api@4.31.1(staging)": SHA_1291,
                       "checkout-api@4.31.0-rc.1(staging)": SHA_1285},
    })

    variants = {"golden": (golden, gold_out), "nop": (seed, None)}
    for name, plan in VARIANTS.items():
        variants[name] = apply_run(seed, plan)
    for name, (states, outj) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if outj is not None:
            write_json(out / "variants" / name / "output" / "incident_trace.json", outj)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
