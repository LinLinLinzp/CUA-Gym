#!/usr/bin/env python3
"""Verifier for ember-launch-status-audit. Checkpoints mirror rubric.json (S*, Y*, K*, C*).

Expected values are derived from seed/shopify.json, seed/yahoo_mail.json, seed/slack.json and
input/ember_launch_sheet.csv (see comments next to each constant).
"""

import csv
import html
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, new_items, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/ember-launch-status-audit", "0.1.0"

# spec.json clock: 2026-11-18T10:30:00-08:00 == 18:30 UTC.
NOW = datetime(2026, 11, 18, 18, 30, tzinfo=timezone.utc)
# A recreated code "starting now" may carry the UI's wall-clock time; allow a small skew past NOW.
START_SKEW = timedelta(hours=1)

# Launch sheet ref -> (kind, Shopify record id). SKUs come from products[].variants[].sku in the
# shopify seed; discount ids from discounts[].code; blog id from blogPosts[].handle.
SHEET = {
    "EMB-CND-CED": ("product", "prod_emb_ced"),
    "EMB-CND-FIG": ("product", "prod_emb_fig"),
    "EMB-CND-AMB": ("product", "prod_emb_amb"),
    "EMB-THR-RST": ("product", "prod_emb_rst"),
    "EMB-THR-CHR": ("product", "prod_emb_chr"),  # NOT prod_hh_thr_chr (HH-THR-CHR, the core throw)
    "EMB-MUG-SET": ("product", "prod_emb_mug"),
    "EMB-GFT-BOX": ("product", "prod_emb_gft"),
    "EMBER15": ("discount", "disc_ember15"),
    "EMBERSHIP": ("discount", "disc_embership"),
    "EMBERVIP": ("discount", "disc_embervip"),
    "MEET-THE-EMBER-COLLECTION": ("blog", "blog_ember_meet"),
}

# Expected audit rows: ref -> (found_status, fixed_to, live).
#  found_status = seed status (shopify seed). Target state = sheet go_live/ends vs. 2026-11-18,
#  plus the QA pull in the #ember-launch checklist thread (m_e1_r2: Fig & Clove stays draft).
#  - CED/RST/MUG active, go_live 11-18 -> keep, live.
#  - FIG draft, pulled by QA -> keep draft, not live.
#  - AMB draft, go_live 11-18 -> activate.   CHR archived, go_live 11-18 -> activate.
#  - GFT active, go_live 12-01 ("keep unpublished until go-live") -> draft, not live.
#  - EMBER15 scheduled (startsAt 11-25), sheet 11-18..11-30 -> active.
#  - EMBERSHIP active (11-18..11-25) -> keep.   EMBERVIP expired (ended 11-17) -> keep, not live.
#  - meet-the-ember-collection unpublished draft, go_live 11-18 -> published.
EXPECTED_ROWS = {
    "EMB-CND-CED": ("active", "", "yes"),
    "EMB-CND-FIG": ("draft", "", "no"),
    "EMB-CND-AMB": ("draft", "active", "yes"),
    "EMB-THR-RST": ("active", "", "yes"),
    "EMB-THR-CHR": ("archived", "active", "yes"),
    "EMB-MUG-SET": ("active", "", "yes"),
    "EMB-GFT-BOX": ("active", "draft", "no"),
    "EMBER15": ("scheduled", "active", "yes"),
    "EMBERSHIP": ("active", "", "yes"),
    "EMBERVIP": ("expired", "", "no"),
    "MEET-THE-EMBER-COLLECTION": ("draft", "published", "yes"),
}
EXPECTED_LIVE = {ref: row[2] == "yes" for ref, row in EXPECTED_ROWS.items()}

# Non-target discounts that must keep their status (shopify seed discounts[]).
OTHER_DISCOUNTS = ["disc_emberstaff", "disc_bf26", "disc_hearth10", "disc_ship150", "disc_bf25", "disc_linen"]
EMBER_PRODUCT_IDS = {rid for kind, rid in SHEET.values() if kind == "product"}

# Stockists (yahoo seed): Juniper; Ashby moved to purchasing@ashbyhome.co (msg_ashby_addr, 11/16).
JUNIPER = "hello@junipermarket.com"
ASHBY_NEW = "purchasing@ashbyhome.co"
ASHBY_OLD = "buying@ashbyandco.com"
STOCKISTS = (JUNIPER, ASHBY_NEW, ASHBY_OLD)
# Products a customer can buy today after the fixes (Fig pulled, Gift Box not until 12/1).
NOTE_MUST_MENTION = ["cedar", "amber", "rust", "charcoal", "mug"]

CHANNEL = "ember-launch"
STATUS_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?[`*_]*([A-Za-z0-9-]+)[`*_]*\s*[:：\-–—]\s*[`*_]*(not[\s-]+live|live)\b", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


# ------------------------------------------------------------------ helpers
def by_id(items, key="id"):
    return {item.get(key): item for item in items or [] if isinstance(item, dict)}


def norm(value) -> str:
    return str(value or "").strip().lower()


def is_true(value) -> bool:
    return value is True or norm(value) == "true"


def parse_time(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:  # date-only / naive: store-local time (PT, -08:00 in November)
        dt = dt.replace(tzinfo=timezone(timedelta(hours=-8)))
    return dt


def to_lines(text) -> list:
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>|<li[^>]*>", "\n", str(text or ""), flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text.splitlines()


def addresses(entries) -> set:
    found = set()
    if isinstance(entries, (str, dict)):
        entries = [entries]
    for entry in entries or []:
        raw = entry.get("email", "") if isinstance(entry, dict) else str(entry)
        found.update(e.lower() for e in EMAIL_RE.findall(raw or ""))
    return found


def recipients(msg) -> set:
    return addresses(msg.get("to")) | addresses(msg.get("cc")) | addresses(msg.get("bcc"))


def mail_text(msg) -> str:
    parts = [msg.get("subject"), msg.get("body"), msg.get("bodyHtml")]
    text = " ".join(str(p) for p in parts if p)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).lower()


def live_now(shop, ref) -> bool:
    """Is the sheet item live in the final Shopify state?"""
    kind, rid = SHEET[ref]
    if kind == "product":
        rec = by_id(shop.get("products")).get(rid)
        return bool(rec) and norm(rec.get("status")) == "active"
    if kind == "blog":
        rec = by_id(shop.get("blogPosts")).get(rid)
        return bool(rec) and is_true(rec.get("published"))
    # The code is live if its record (or a recreated record with the same code) is active.
    return any(isinstance(d, dict) and (d.get("id") == rid or norm(d.get("code")) == ref.lower())
               and norm(d.get("status")) == "active" for d in shop.get("discounts") or [])


def final_status(shop, ref) -> str:
    kind, rid = SHEET[ref]
    if kind == "blog":
        rec = by_id(shop.get("blogPosts")).get(rid)
        return "" if rec is None else ("published" if is_true(rec.get("published")) else "draft")
    rec = by_id(shop.get("products" if kind == "product" else "discounts")).get(rid)
    if rec is None and kind == "discount":
        rec = next((d for d in shop.get("discounts") or [] if norm(d.get("code")) == ref.lower()), None)
    return "" if rec is None else norm(rec.get("status"))


# ------------------------------------------------------------------ evaluate
def evaluate(g):
    shop0, shop1 = load_site("shopify")
    mail0, mail1 = load_site("yahoo_mail")
    slack0, slack1 = load_site("slack")

    prods0, prods1 = by_id(shop0.get("products")), by_id(shop1.get("products"))
    discs0, discs1 = by_id(shop0.get("discounts")), by_id(shop1.get("discounts"))
    blogs0, blogs1 = by_id(shop0.get("blogPosts")), by_id(shop1.get("blogPosts"))
    missing = [rid for kind, rid in SHEET.values()
               if rid not in {"product": prods0, "discount": discs0, "blog": blogs0}[kind]]
    missing += [d for d in OTHER_DISCOUNTS if d not in discs0]
    if missing:
        raise InfraError(f"seed records missing from shopify initial state: {missing}")
    for ref, (found, _, _) in EXPECTED_ROWS.items():
        if final_status(shop0, ref) != found:
            raise InfraError(f"initial state for {ref} is {final_status(shop0, ref)!r}, seed says {found!r}")
    if not isinstance(mail1.get("messages"), list) or not isinstance(slack1.get("messages"), dict):
        raise InfraError("mail/slack current state has no messages collection")

    def prod_status(pid):
        rec = prods1.get(pid)
        return None if rec is None else norm(rec.get("status"))

    # ---- Shopify: fixes ----------------------------------------------------
    s1 = g.add("S1.amber_activated", 8, prod_status("prod_emb_amb") == "active",
               f"Amber Hearth status={prod_status('prod_emb_amb')} (expected active)")
    s2 = g.add("S2.ember_charcoal_activated", 8, prod_status("prod_emb_chr") == "active",
               f"Ember Charcoal (EMB-THR-CHR) status={prod_status('prod_emb_chr')} (expected active)")
    s3 = g.add("S3.gift_box_hidden", 8, prod_status("prod_emb_gft") == "draft",
               f"Gift Box status={prod_status('prod_emb_gft')} (expected draft)")

    e15 = discs1.get("disc_ember15")
    recreated = [d for d in shop1.get("discounts") or [] if isinstance(d, dict) and d.get("id") != "disc_ember15"
                 and norm(d.get("code")) == "ember15" and norm(d.get("status")) == "active"]
    good_recreated = [d for d in recreated if norm(d.get("type")) == "percentage"
                      and _num(d.get("value")) == 15.0
                      and (parse_time(d.get("startsAt")) or NOW) <= NOW + START_SKEW]
    if e15 is not None and norm(e15.get("status")) == "active":
        s4, why = 1.0, "original EMBER15 active"
    elif e15 is None and good_recreated:
        s4, why = 0.75, "original deleted, recreated EMBER15 (lost Ember-only scope)"
    elif e15 is not None and recreated:
        s4, why = 0.5, f"original still {e15.get('status')}, duplicate active EMBER15 created"
    else:
        s4, why = 0.0, f"EMBER15 status={None if e15 is None else e15.get('status')}"
    s4 = g.add("S4.ember15_active", 8, s4, why)

    meet = blogs1.get("blog_ember_meet")
    first0, first1 = blogs0.get("blog_ember_first"), blogs1.get("blog_ember_first")
    strip = lambda b: {k: v for k, v in (b or {}).items() if k != "updatedAt"}  # noqa: E731
    first_ok = first1 is not None and strip(first0) == strip(first1)
    s5 = g.add("S5.blog_published", 7, bool(meet) and is_true(meet.get("published")) and first_ok,
               f"meet published={None if meet is None else meet.get('published')}; first-look untouched={first_ok}")

    fixed_any = max(s1, s2, s3) > 0
    g.add("S6.fig_stays_draft", 6, fixed_any and prod_status("prod_emb_fig") == "draft",
          f"Fig & Clove status={prod_status('prod_emb_fig')}; precondition S1-S3 any>0: {fixed_any}")

    vip = discs1.get("disc_embervip")
    vip_status = None if vip is None else norm(vip.get("status"))
    g.add("S7.vip_stays_expired", 5, s4 > 0 and vip_status == "expired",
          f"EMBERVIP status={vip_status}; precondition S4>0: {s4 > 0}")

    violations = []
    for pid, p0 in prods0.items():
        p1 = prods1.get(pid)
        if p1 is None:
            violations.append(f"deleted {pid}")
        elif pid not in EMBER_PRODUCT_IDS and norm(p1.get("status")) != norm(p0.get("status")):
            violations.append(f"{pid} {p0.get('status')}->{p1.get('status')}")
    for did in OTHER_DISCOUNTS:
        d1 = discs1.get(did)
        if d1 is None:
            violations.append(f"deleted {did}")
        elif norm(d1.get("status")) != norm(discs0[did].get("status")):
            violations.append(f"{did} {discs0[did].get('status')}->{d1.get('status')}")
    for bid, b0 in blogs0.items():
        if bid == "blog_ember_meet":
            continue
        b1 = blogs1.get(bid)
        if b1 is None or is_true(b1.get("published")) != is_true(b0.get("published")):
            violations.append(f"blog {bid} published changed/deleted")
    full_fix = max(s1, s2, s3, s4, s5) >= 1
    g.add("S8.non_targets_untouched", 5, (1 - 0.25 * len(violations)) if full_fix else 0,
          f"violations={violations}; precondition S1-S5 any==1: {full_fix}")

    # ---- Yahoo Mail: stockist note -------------------------------------------
    init_msgs = by_id(mail0.get("messages"))
    sent = [m for m in mail1["messages"] if isinstance(m, dict) and norm(m.get("status")) == "sent"
            and (m.get("id") not in init_msgs or norm(init_msgs[m.get("id")].get("status")) == "draft")]
    covered = set().union(*[recipients(m) for m in sent]) if sent else set()
    has_juniper = JUNIPER in covered
    has_ashby = bool({ASHBY_NEW, ASHBY_OLD} & covered)
    y1 = g.add("Y1.stockist_note_sent", 8, 1.0 if has_juniper and has_ashby else 0.5 if has_juniper or has_ashby else 0,
               f"{len(sent)} newly sent mail(s); recipients covered={sorted(covered & set(STOCKISTS))}")

    to_new = any(ASHBY_NEW in recipients(m) for m in sent)
    to_old = any(ASHBY_OLD in recipients(m) for m in sent)
    g.add("Y2.ashby_new_address", 6, y1 > 0 and to_new and not to_old,
          f"sent to {ASHBY_NEW}: {to_new}; sent to old {ASHBY_OLD}: {to_old}")

    notes = [m for m in sent if recipients(m) & set(STOCKISTS)]
    problems = []
    for m in notes:
        text = mail_text(m)
        lacking = [w for w in NOTE_MUST_MENTION if w not in text]
        if lacking:
            problems.append(f"{m.get('id')} missing {lacking}")
        if re.search(r"\bfig\b", text, re.I):
            problems.append(f"{m.get('id')} mentions Fig")
    g.add("Y3.note_lists_only_live", 9, y1 > 0 and bool(notes) and not problems,
          f"{len(notes)} stockist note(s); problems={problems}")

    counts = {a: sum(a in recipients(m) for m in sent) for a in STOCKISTS}
    g.add("Y4.no_duplicate_note", 2, y1 > 0 and all(c <= 1 for c in counts.values()),
          f"sends per stockist address={counts}")

    # ---- Slack: status update ----------------------------------------------
    thread_ids = {tid for tid, t in (slack1.get("threads") or {}).items()
                  if isinstance(t, dict) and t.get("channelId") == CHANNEL}
    seen0 = {m.get("messageId") for msgs in (slack0.get("messages") or {}).values() for m in msgs or []}
    posts, ids = [], set()
    for key, msgs in slack1["messages"].items():
        for m in msgs or []:
            if not isinstance(m, dict) or m.get("messageId") in seen0 or m.get("messageId") in ids:
                continue
            if key == CHANNEL or (m.get("threadId") and m.get("threadId") in thread_ids):
                posts.append(m)
                ids.add(m.get("messageId"))
    posts.sort(key=lambda m: str(m.get("timestamp") or ""))
    reported = {}
    for m in posts:
        for line in to_lines(m.get("content")):
            hit = STATUS_LINE.match(line)
            if hit and hit.group(1).upper() in SHEET:
                reported[hit.group(1).upper()] = not hit.group(2).lower().startswith("not")
    right = [ref for ref in SHEET if ref in reported and reported[ref] == EXPECTED_LIVE[ref]
             and live_now(shop1, ref) == EXPECTED_LIVE[ref]]
    g.add("K1.slack_status_lines", 9, len(right) / len(SHEET),
          f"{len(posts)} new post(s); {len(right)}/{len(SHEET)} refs correct and true; reported={reported}")

    # ---- Local deliverable ---------------------------------------------------
    g.add("C1.audit_csv", 11, *audit_csv(shop1))


def _num(value):
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def audit_csv(shop1):
    path = OUTPUT_DIR / "launch_audit.csv"
    if not path.is_file() or path.is_symlink():
        return 0, "launch_audit.csv missing"
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            table = [row for row in csv.reader(f) if any(c.strip() for c in row)]
    except (UnicodeDecodeError, csv.Error) as exc:
        return 0, f"unreadable csv: {exc}"
    if not table or [c.strip().lower() for c in table[0]] != ["ref", "found_status", "fixed_to", "live"]:
        return 0, f"bad header: {table[0] if table else None}"
    rows = table[1:]
    yes, no = {"yes", "y", "true"}, {"no", "n", "false"}
    correct, wrong = set(), []
    for row in rows:
        row = (row + ["", "", "", ""])[:4]
        ref, found, fixed, live = (c.strip() for c in row)
        ref = ref.upper()
        if ref not in EXPECTED_ROWS:
            wrong.append(ref or "<blank>")
            continue
        exp_found, exp_fixed, exp_live = EXPECTED_ROWS[ref]
        live = "yes" if live.lower() in yes else "no" if live.lower() in no else live.lower()
        ok = (found.lower() == exp_found and fixed.lower() == exp_fixed and live == exp_live
              and (not exp_fixed or final_status(shop1, ref) == exp_fixed))
        if ok:
            correct.add(ref)
        else:
            wrong.append(ref)
    return (len(correct) / max(len(EXPECTED_ROWS), len(rows)),
            f"{len(correct)}/{len(EXPECTED_ROWS)} rows right, {len(rows)} data rows; wrong={wrong}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
