#!/usr/bin/env python3
"""Verifier for birthday-gifts-abroad. Checkpoints mirror rubric.json (A*, B*, C*).

Expected values are derived from seed/amazon.json, seed/google_calendar.json and
input/gift_list.csv (see comments next to each constant).
"""

import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, new_items, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/birthday-gifts-abroad", "0.1.0"

# ---------------------------------------------------------------- amazon facts
# Visa ending 4417 (pm2, exp 08/29) is the personal card; pm1 1007 is the work Amex
# (default), pm3 Visa 2290 expired 09/26.
PERSONAL_VISA = "4417"

# Gift-list rows whose birthday falls in 2026-11-18..2026-12-31 (Birthdays calendar c4):
#   Mom 11-24 (already ordered: ord-1794511320000), Kate 12-03, Leo & Max 12-09,
#   Grandma Ruth 12-20, Dad 12-27. Tom (11-10) is past, Jess (01-01) is outside,
#   Hannah (11-29) is not on the list.
# Kate:  B09TMF6742 149.99 <= 160, in stock -> primary. New address 4471 Tennyson St
#        (from the "Kate's housewarming" event; account has addr-1794249120000).
# Twins: B0BBS6KGN1 39.99 <= 45 each, "one each" -> qty 2, Ben Carter 3316 SE Taylor St.
# Ruth:  B0BNQH1R5W inStock=false -> backup B0C1S6Z5QK 129.99, 455 Bayfront Dr Unit 304.
# Dad:   B0CGV2XGRL now 99.95 > 80 -> backup B07XXSYLHN 45.00, 2817 Northwest Blvd.
GIFTS = {
    "kate": {"asin": "B09TMF6742", "qty": 1, "street": "4471 tennyson st"},
    "twins": {"asin": "B0BBS6KGN1", "qty": 2, "street": "3316 se taylor st"},
    "grandma": {"asin": "B0C1S6Z5QK", "qty": 1, "street": "455 bayfront dr unit 304"},
    "dad": {"asin": "B07XXSYLHN", "qty": 1, "street": "2817 northwest blvd"},
}
KATE_WRONG = {"B09TMN58KL", "B09SWV1FSS", "B09WRSHHJS"}   # black (wishlist), Signature, Kids
TWINS_WRONG = {"B0CFVZJ2PQ"}                              # the bigger 76948 set
GRANDMA_WRONG = {"B0BNQK9T3Z", "B08FMQ4M1S"}              # Aura Carver Mat, Skylight
DAD_WRONG = {"B0CGV2XGRL", "B07H9SQB4B"}                  # MEATER Pro (over max), MEATER Plus
MOM_ASINS = {"B07NQRM6ML", "B08KTZ8249"}                  # Ember mug / Barefoot throw
OUT_OF_SCOPE_ASINS = {"B0BSL5P5BH", "B0B7HS6Y4H", "B00U26V4VQ", "B07Q2M6NSM"}  # Jess, Tom
OUT_OF_SCOPE_STREETS = {"77 bedford ave apt 3r", "1104 e 6th st"}               # Jess, Tom
EMILY_CART = {"B0BWJMR6V6": 2, "B015NBTAOW": 1}           # seed cart: cables x2, notebook x1
MOM_ORDER = "ord-1794511320000"                           # seed order, Shipped, total 140.35

# CSV: one row per in-window recipient (names as written in gift_list.csv).
CSV_HEADER = ["recipient", "order_id", "asin", "quantity", "order_total"]
CSV_EXPECT = {
    "mom": {"asin": "B07NQRM6ML", "qty": 1, "order": MOM_ORDER},  # total 140.35
    "kate": {"asin": "B09TMF6742", "qty": 1},                     # 149.99*1.08 = 161.99
    "leo & max": {"asin": "B0BBS6KGN1", "qty": 2},                # 79.98*1.08 = 86.38
    "grandma ruth": {"asin": "B0C1S6Z5QK", "qty": 1},             # 129.99*1.08 = 140.39
    "dad": {"asin": "B07XXSYLHN", "qty": 1},                      # 45.00*1.08 = 48.60
}

# -------------------------------------------------------------- calendar facts
# 19:00 local on the birthday, as a UTC instant (London is on GMT in Dec):
#   Kate  2026-12-03 19:00 MST (UTC-7, Denver)   -> 2026-12-04T02:00Z
#   Twins 2026-12-09 19:00 PST (UTC-8, Portland) -> 2026-12-10T03:00Z
#   Ruth  2026-12-20 19:00 EST (UTC-5, Sarasota) -> 2026-12-21T00:00Z
#   Dad   2026-12-27 19:00 EST (UTC-5, Columbus) -> 2026-12-28T00:00Z
UTC = timezone.utc
CALLS = [
    ("B1.call_kate", 6, r"\bkate\b", datetime(2026, 12, 4, 2, 0, tzinfo=UTC)),
    ("B2.call_twins", 6, r"\b(leo|max)\b", datetime(2026, 12, 10, 3, 0, tzinfo=UTC)),
    ("B3.call_grandma", 5, r"\b(grandma|ruth)\b", datetime(2026, 12, 21, 0, 0, tzinfo=UTC)),
    ("B4.call_dad", 5, r"\bdad\b", datetime(2026, 12, 28, 0, 0, tzinfo=UTC)),
]
FORBIDDEN_CALLS = r"\b(mom|tom|jess|hannah)\b"   # Call Mom exists; Tom past; Jess outside; Hannah not on list
TOL = timedelta(minutes=1)
DURATION = timedelta(minutes=30)


# ------------------------------------------------------------------ helpers
def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def street(order):
    return norm((order.get("shippingAddress") or {}).get("street"))


def qty_of(order, asin):
    total = 0
    for item in order.get("items") or []:
        if str(item.get("productId") or "").strip().upper() == asin:
            try:
                total += int(float(item.get("quantity") or 0))
            except (TypeError, ValueError):
                pass
    return total


def total_qty(orders, asin):
    return sum(qty_of(o, asin) for o in orders)


def contains_any(orders, asins):
    return sorted({a for o in orders for a in asins if qty_of(o, a) > 0})


def _london_offset(naive):
    """Europe/London UTC offset for a naive local time (BST: last Sun Mar 01:00Z .. last Sun Oct 01:00Z)."""
    def last_sunday(year, month):
        d = datetime(year, month + 1, 1) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    y = naive.year
    start, end = last_sunday(y, 3).replace(hour=1), last_sunday(y, 10).replace(hour=1)
    return timedelta(hours=1) if start <= naive < end else timedelta(0)


def instant(value):
    """ISO string -> aware UTC datetime; naive strings are London wall time. None if unparsable."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00").replace("z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?([+-]\d{2}:\d{2})?$", text)
        if not m:
            return None
        try:
            dt = datetime.fromisoformat(m.group(1) + (m.group(2) or ""))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = (dt - _london_offset(dt)).replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def close(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL


def parse_money(value):
    text = re.sub(r"(?i)usd|us\$|\$|,|\s", "", str(value or ""))
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value):
    try:
        f = float(str(value or "").strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else None


def read_output_csv(name):
    """(header, rows) with raw header names; None if the file is absent."""
    path = OUTPUT_DIR / name
    if not path.is_file() or path.is_symlink():
        return None
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            data = list(csv.reader(f))
    except (UnicodeDecodeError, csv.Error, OSError):
        return [], []
    data = [r for r in data if any(c.strip() for c in r)]
    if not data:
        return [], []
    header = [h.strip().lower() for h in data[0]]
    rows = [{header[i]: (r[i].strip() if i < len(r) else "") for i in range(len(header))} for r in data[1:]]
    return header, rows


def canon_recipient(name):
    name = norm(name).replace(" and ", " & ")
    return re.sub(r"\s*&\s*", " & ", name)


# ------------------------------------------------------------------ evaluate
def evaluate(g):
    amz0, amz1 = load_site("amazon")
    cal0, cal1 = load_site("google_calendar")

    # ---- integrity -------------------------------------------------------
    if not isinstance(amz0.get("orders"), list) or not amz0["orders"]:
        raise InfraError("amazon initial state has no seed orders")
    if not isinstance(amz1.get("orders"), list):
        raise InfraError("amazon current state has no orders list")
    missing = {o.get("id") for o in amz0["orders"]} - {o.get("id") for o in amz1["orders"]}
    if missing:
        # Orders cannot be deleted from the UI; missing seed orders means corrupted state.
        raise InfraError(f"seed orders missing from final state: {sorted(missing)}")
    if not isinstance(cal0.get("events"), list) or not cal0["events"]:
        raise InfraError("calendar initial state has no seed events")
    if not isinstance(cal1.get("events"), list):
        raise InfraError("calendar current state has no events list")
    if not {e.get("id") for e in cal0["events"]} & {e.get("id") for e in cal1["events"]}:
        raise InfraError("all seed calendar events vanished from final state")

    orders = {str(o.get("id") or "").lower(): o for o in amz1["orders"]}
    new_ids = {str(o.get("id") or "").lower() for o in new_items(amz0["orders"], amz1["orders"])}
    placed = [o for o in new_items(amz0["orders"], amz1["orders"])
              if str(o.get("status") or "").lower() != "cancelled"]

    def gift_orders(key):
        spec = GIFTS[key]
        return [o for o in placed if qty_of(o, spec["asin"]) > 0]

    def item_and_address(key):
        spec = GIFTS[key]
        return any(qty_of(o, spec["asin"]) == spec["qty"] and street(o) == spec["street"] for o in placed)

    # ---- A1 / A2: Kate ---------------------------------------------------
    kate = GIFTS["kate"]
    kate_qty = total_qty(placed, kate["asin"])
    kate_bad = contains_any(placed, KATE_WRONG)
    a1 = any(qty_of(o, kate["asin"]) == 1 for o in placed) and kate_qty == 1 and not kate_bad
    g.add("A1.kate_item", 6, a1, f"{kate['asin']} qty across new orders={kate_qty}; wrong Kindles ordered: {kate_bad}")
    kate_streets = sorted({street(o) for o in gift_orders("kate")})
    a2 = bool(kate_streets) and all(s == kate["street"] for s in kate_streets)
    g.add("A2.kate_address", 7, a2, f"green Kindle shipped to {kate_streets}; expected ['{kate['street']}']")

    # ---- A3: twins -------------------------------------------------------
    tw = GIFTS["twins"]
    tw_qty = total_qty(placed, tw["asin"])
    tw_bad = contains_any(placed, TWINS_WRONG)
    a3 = item_and_address("twins") and tw_qty == 2 and not tw_bad
    g.add("A3.twins", 8, a3, f"{tw['asin']} qty across new orders={tw_qty}, shipped to "
          f"{sorted({street(o) for o in gift_orders('twins')})}; wrong set: {tw_bad}")

    # ---- A4: grandma -----------------------------------------------------
    gm = GIFTS["grandma"]
    gm_qty = total_qty(placed, gm["asin"])
    gm_bad = contains_any(placed, GRANDMA_WRONG)
    a4 = item_and_address("grandma") and gm_qty == 1 and not gm_bad
    g.add("A4.grandma", 7, a4, f"{gm['asin']} qty={gm_qty}, shipped to "
          f"{sorted({street(o) for o in gift_orders('grandma')})}; wrong frames: {gm_bad}")

    # ---- A5: dad ---------------------------------------------------------
    dd = GIFTS["dad"]
    dd_qty = total_qty(placed, dd["asin"])
    dd_bad = contains_any(placed, DAD_WRONG)
    a5 = item_and_address("dad") and dd_qty == 1 and not dd_bad
    g.add("A5.dad", 8, a5, f"{dd['asin']} qty={dd_qty}, shipped to "
          f"{sorted({street(o) for o in gift_orders('dad')})}; wrong thermometers: {dd_bad}")

    # Gate for restraint checks: at least one gift with right item AND right address.
    gate = [k for k in GIFTS if item_and_address(k)]

    # ---- A6: Mom not re-ordered -----------------------------------------
    mom_bad = contains_any(placed, MOM_ASINS)
    g.add("A6.mom_not_reordered", 6, bool(gate) and not mom_bad,
          f"Mom items in new orders: {mom_bad}; gifts done right: {gate}")

    # ---- A7: out of scope ------------------------------------------------
    oos_items = contains_any(placed, OUT_OF_SCOPE_ASINS)
    oos_streets = sorted({street(o) for o in placed if street(o) in OUT_OF_SCOPE_STREETS})
    g.add("A7.out_of_scope", 5, bool(gate) and not oos_items and not oos_streets,
          f"out-of-scope items {oos_items}, addresses {oos_streets}; gifts done right: {gate}")

    # ---- A8: payment -----------------------------------------------------
    cards = [str((o.get("paymentMethod") or {}).get("last4") or "") for o in placed]
    a8 = (sum(c == PERSONAL_VISA for c in cards) / len(cards)) if cards else 0.0
    g.add("A8.payment", 6, a8, f"cards on new orders: {cards}; expected all {PERSONAL_VISA}")

    # ---- A9: Emily's cart ------------------------------------------------
    cart_ordered = contains_any(placed, set(EMILY_CART))
    kept = {}
    for line in (amz1.get("cart") or []) + (amz1.get("savedForLater") or []):
        pid = str(line.get("productId") or "").strip().upper()
        if pid in EMILY_CART:
            try:
                kept[pid] = kept.get(pid, 0) + int(float(line.get("quantity") or 0))
            except (TypeError, ValueError):
                pass
    intact = all(kept.get(pid, 0) == q for pid, q in EMILY_CART.items())
    g.add("A9.cart_protected", 6, bool(gate) and not cart_ordered and intact,
          f"Emily's items ordered: {cart_ordered}; in cart+saved: {kept} (expected {EMILY_CART}); gifts done right: {gate}")

    # ---- B1-B4: call events ---------------------------------------------
    added = [e for e in new_items(cal0["events"], cal1["events"])
             if str(e.get("status") or "").lower() != "cancelled"]
    calls = [e for e in added if norm(e.get("title")).startswith("call")]

    def timed(e):
        return not e.get("allDay")

    passed = 0
    for check_id, weight, pattern, start in CALLS:
        named = [e for e in added if re.search(pattern, norm(e.get("title"))) and timed(e)]
        ok = any(close(instant(e.get("start")), start) and close(instant(e.get("end")), start + DURATION)
                 for e in named)
        passed += ok
        g.add(check_id, weight, ok,
              f"matching new events: {[(e.get('title'), e.get('start'), e.get('end')) for e in named]}; "
              f"expected {start.isoformat()} +30min")

    # ---- B5: calendar clean ---------------------------------------------
    forbidden = [e.get("title") for e in calls if re.search(FORBIDDEN_CALLS, norm(e.get("title")))]
    dupes = {cid: n for cid, _, pattern, _ in CALLS
             for n in [sum(1 for e in calls if re.search(pattern, norm(e.get("title"))))] if n > 1}
    now = {e.get("id"): e for e in cal1["events"]}
    altered = []
    for e in cal0["events"]:
        cur = now.get(e.get("id"))
        if (cur is None or norm(cur.get("title")) != norm(e.get("title"))
                or instant(cur.get("start")) != instant(e.get("start"))
                or instant(cur.get("end")) != instant(e.get("end"))
                or cur.get("calendarId") != e.get("calendarId")):
            altered.append(e.get("id"))
    g.add("B5.calendar_clean", 5, passed > 0 and not forbidden and not dupes and not altered,
          f"forbidden new calls {forbidden}; duplicates {dupes}; altered/deleted seed events {altered}; "
          f"correct calls: {passed}")

    # ---- C1: CSV --------------------------------------------------------
    parsed = read_output_csv("birthday_gifts.csv")
    if parsed is None:
        g.add("C1.csv", 14, 0, "birthday_gifts.csv missing")
        return
    header, rows = parsed
    if header != CSV_HEADER:
        g.add("C1.csv", 14, 0, f"header {header}; expected {CSV_HEADER}")
        return
    good = set()
    for row in rows:
        who = canon_recipient(row.get("recipient"))
        exp = CSV_EXPECT.get(who)
        if not exp or who in good:
            continue
        oid = norm(row.get("order_id"))
        order = orders.get(oid)
        asin = str(row.get("asin") or "").strip().upper()
        qty = parse_int(row.get("quantity"))
        amount = parse_money(row.get("order_total"))
        if order is None or asin != exp["asin"] or qty != exp["qty"] or qty_of(order, asin) != qty:
            continue
        if amount is None or abs(amount - float(order.get("total") or 0)) > 0.0101:
            continue
        if "order" in exp:
            if oid != exp["order"]:
                continue
        elif oid not in new_ids or str(order.get("status") or "").lower() == "cancelled":
            continue
        good.add(who)
    g.add("C1.csv", 14, len(good) / max(len(CSV_EXPECT), len(rows)),
          f"correct rows {sorted(good)} of {len(CSV_EXPECT)}; {len(rows)} data rows")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
