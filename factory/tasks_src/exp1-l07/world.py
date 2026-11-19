#!/usr/bin/env python3
"""World for exp1-l07 / dad-visits-airbnb-settlement (Airbnb + Google Sheets + Gmail + CLI script).

Writes into <out>/:
  seed/{airbnb,google_sheets,gmail}.json     initial state per site
  golden/{airbnb,google_sheets,gmail}.json   state after a correct run
  golden_output/{bookings.csv,settle.py,settlement_2026-10.csv}
  expected.json                              truth for the verifier (incl. hidden replay mutations)
  variants/<name>/{state/<site>/{initial,current}.json, output/}

Story: Emily Carter and her siblings James and Megan take turns flying to Asheville while
their dad Walter is in rehab. Emily books most Airbnbs on her account and settles monthly in
a Google Sheet. The split rules live in a Gmail thread; an October amendment (cleaning fees
split three ways on stays that happen, from October check-ins) is only in replies there
(the sheet's Notes tab still shows the August wording). James takes over bookings in
December and wants a script he can rerun on a fresh export of the Bookings tab (lever L07).

Traps for October: a stay logged as confirmed was cancelled with a partial refund; a stay
was shortened; a stay was moved from Oct 31 to Nov 1 (leaves October); a castle weekend is
missing from the sheet (Megan's email) while a personal October trip and a cancelled
personal trip must stay out; James's own booking has a quote and a later updated receipt;
the Sep 29 stay belongs to September.

Airbnb is read-only in this task (its trips/receipts are the source of truth).
"""

import copy
import csv
import io
import json
import math
import os
import subprocess
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T09:00:00-08:00"
NOW = "2026-11-18T17:20:00.000Z"
EMILY = "emily.carter@gmail.com"
JAMES = "james.carter.oak@gmail.com"
MEGAN = "megan.ruiz.nc@outlook.com"
PEOPLE = ["Emily", "James", "Megan"]
COLUMNS = ["code", "check_in", "check_out", "status", "guests", "paid_by", "total", "service_fee", "cleaning_fee", "refund"]
SETTLE_HEADER = ["person", "share", "paid", "balance"]
TARGET_MONTH = "2026-10"
CLEANING_SPLIT_FROM = "2026-10"
SHEET_TITLE = "Dad visits - Asheville stays"

# id, hostId, title, city, nightly, cleaning, taxRate, weeklyPct, policy
LISTINGS = {
    "lst_016": ("user_107", "Blue Ridge Treehouse with Wraparound Deck", "Asheville", 245, 85, 0.13, 0, "moderate"),
    "lst_017": ("user_107", "Mountain Cabin w/ Hot Tub & Fire Pit", "Asheville", 279, 125, 0.13, 10, "moderate"),
    "lst_018": ("user_108", "Modern Tiny Home in the Woods", "Weaverville", 139, 50, 0.13, 0, "flexible"),
    "lst_019": ("user_108", "Hidden Forest Treehouse Castle", "Black Mountain", 315, 100, 0.13, 10, "limited"),
    "lst_020": ("user_107", "Fall Colors Cabin near Blue Ridge Pkwy", "Asheville", 189, 90, 0.13, 0, "flexible"),
    "lst_056": ("user_120", "Catskills A-Frame with Wood Stove", "Phoenicia", 235, 95, 0.08, 0, "moderate"),
    "lst_006": ("user_103", "Boulder House: Desert Modern Hideaway", "Joshua Tree", 410, 150, 0.12, 0, "firm"),
    "lst_036": ("user_115", "Haussmann Apartment near Le Marais", "Paris", 310, 90, 0.05, 0, "moderate"),
    "lst_031": ("user_113", "Williamsburg Sun-Drenched Loft", "Brooklyn", 289, 100, 0.148, 10, "moderate"),
    "lst_002": ("user_101", "Lakefront Modern Retreat with Private Dock", "Tahoe City", 845, 300, 0.1, 0, "strict"),
}
HOST_NAME = {"user_107": "Tom", "user_108": "Rachel", "user_120": "Grace", "user_103": "Daniel",
             "user_115": "Camille", "user_113": "David", "user_101": "Michael"}


# ---------------------------------------------------------------- pricing (mirrors src/utils/pricing.js)
def round2(x: float) -> float:
    return math.floor(x * 100 + 0.5 + 1e-9) / 100


def nights_between(ci: str, co: str) -> int:
    from datetime import date
    return (date.fromisoformat(co) - date.fromisoformat(ci)).days


def compute_price(lid: str, ci: str, co: str):
    _, _, _, nightly, cleaning, tax, weekly, _ = LISTINGS[lid]
    n = nights_between(ci, co)
    sub = round2(nightly * n)
    pct = weekly if n >= 7 else 0
    disc = round2(sub * pct / 100)
    taxable = sub - disc + cleaning
    service = round2(taxable * 0.142)
    taxes = round2(taxable * tax)
    return {"nightlyRate": nightly, "nights": n, "nightsSubtotal": sub, "discount": disc, "discountPct": pct,
            "cleaningFee": cleaning, "petFee": 0, "serviceFee": service, "taxes": taxes,
            "total": round2(taxable + service + taxes), "currency": "USD"}


def partial_refund(p) -> float:
    base = p["nightsSubtotal"] - p["discount"]
    return round2(base * 0.5 + p["cleaningFee"] + p["petFee"] + p["taxes"] * 0.5)


def m(x) -> str:
    return f"{x:.2f}"


def usd(x) -> str:
    return f"${x:,.2f}"


# ---------------------------------------------------------------- the stays
# key, code, listing, check_in, check_out, guests(names), adults, status, paid_by, account
#   account: "emily" (in Emily's Airbnb) or "james" (only in James's emails)
STAYS = [
    ("A1", "HMC8A1K2Q7", "lst_018", "2026-08-07", "2026-08-10", ["Emily"], 1, "confirmed", "Emily", "emily"),
    ("A3", "HMJ4W8N2D5", "lst_020", "2026-08-14", "2026-08-16", ["James"], 1, "confirmed", "James", "james"),
    ("A2", "HM4RT7Z9PL", "lst_017", "2026-08-21", "2026-08-24", ["Emily", "James", "Megan"], 3, "confirmed", "Emily", "emily"),
    ("S1", "HMQ2V6B8XK", "lst_018", "2026-09-04", "2026-09-07", ["Megan"], 1, "confirmed", "Emily", "emily"),
    ("S2", "HMJ7P3R9T1", "lst_020", "2026-09-11", "2026-09-13", ["James"], 1, "confirmed", "James", "james"),
    ("S3", "HMT5K9C3MZ", "lst_016", "2026-09-18", "2026-09-20", ["Emily"], 1, "cancelled", "Emily", "emily"),
    ("S4", "HMW3N8F6JD", "lst_017", "2026-09-29", "2026-10-02", ["Emily", "Megan"], 2, "confirmed", "Emily", "emily"),
    ("O1", "HMR6D2H7QA", "lst_016", "2026-10-09", "2026-10-11", ["Megan"], 1, "cancelled", "Emily", "emily"),
    ("O2", "HMZ9L4T2WC", "lst_017", "2026-10-16", "2026-10-19", ["James"], 1, "confirmed", "Emily", "emily"),
    ("O3", "HMK7S3X5PB", "lst_019", "2026-10-23", "2026-10-26", ["Emily", "Megan"], 2, "confirmed", "Emily", "emily"),
    ("O4", "HMJ2F8V6LN", "lst_020", "2026-10-30", "2026-11-01", ["James"], 1, "confirmed", "James", "james"),
    ("O5", "HMV8B5Q1RE", "lst_018", "2026-11-01", "2026-11-03", ["Megan"], 1, "confirmed", "Emily", "emily"),
    ("N1", "HMG3Y7M4KS", "lst_017", "2026-11-25", "2026-11-29", ["Emily", "James", "Megan"], 3, "confirmed", "Emily", "emily"),
]
STAY = {s[0]: s for s in STAYS}
# What the sheet showed before October was reconciled (stale dates) and the superseded quote for O4.
O2_ORIGINAL = ("2026-10-16", "2026-10-20")
O5_ORIGINAL = ("2026-10-31", "2026-11-02")
O4_QUOTE = ("2026-10-30", "2026-11-02")
CANCELLED_AT = {"S3": "2026-09-15T16:40:00.000Z", "O1": "2026-10-06T13:05:00.000Z"}


def stay_amounts(key, dates=None):
    _, code, lid, ci, co, *_ = STAY[key]
    ci, co = dates or (ci, co)
    p = compute_price(lid, ci, co)
    refund = partial_refund(p) if STAY[key][7] == "cancelled" else 0.0
    return p, refund


def booking_row(key, dates=None, status=None, amounts=True, refund=None):
    s = STAY[key]
    _, code, lid, ci, co, guests, _, st, payer, _ = s
    ci, co = dates or (ci, co)
    p, rf = stay_amounts(key, (ci, co))
    row = {"code": code, "check_in": ci, "check_out": co, "status": status or st,
           "guests": "; ".join(guests), "paid_by": payer}
    if amounts:
        row.update({"total": m(p["total"]), "service_fee": m(p["serviceFee"]), "cleaning_fee": m(p["cleaningFee"]),
                    "refund": m(rf if refund is None else refund)})
    else:
        row.update({"total": "", "service_fee": "", "cleaning_fee": "", "refund": ""})
    return row


ORDER = ["A1", "A3", "A2", "S1", "S2", "S3", "S4", "O1", "O2", "O4", "O5", "N1"]  # O3 is missing from the sheet


def seed_rows():
    rows = []
    for key in ORDER:
        if key == "O1":
            rows.append(booking_row(key, status="confirmed", amounts=False))
        elif key == "O2":
            rows.append(booking_row(key, dates=O2_ORIGINAL, amounts=False))
        elif key == "O4":
            rows.append(booking_row(key, dates=O4_QUOTE, amounts=False))
        elif key == "O5":
            rows.append(booking_row(key, dates=O5_ORIGINAL, amounts=False))
        else:
            rows.append(booking_row(key))
    return rows


def golden_rows():
    rows = [booking_row(k) for k in ORDER]
    rows.append(booking_row("O3"))
    return rows


# ---------------------------------------------------------------- settlement (reference rules)
D0 = Decimal("0")
CENT = Decimal("0.01")


class BadInput(Exception):
    pass


def settle(rows, month, cleaning_from=CLEANING_SPLIT_FROM, floor=True, validate=True):
    share = {p: D0 for p in PEOPLE}
    paid = {p: D0 for p in PEOPLE}
    for raw in rows:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if row.get("check_in", "")[:7] != month:
            continue
        status = row.get("status", "").lower()
        guests = [g.strip() for g in row.get("guests", "").split(";") if g.strip()]
        payer = row.get("paid_by", "").strip()
        try:
            total, service, cleaning, refund = (Decimal(row[k]) for k in ("total", "service_fee", "cleaning_fee", "refund"))
        except Exception:
            if validate:
                raise BadInput("amount")
            continue
        if validate and (status not in ("confirmed", "cancelled") or payer not in PEOPLE or not guests
                         or any(g not in PEOPLE for g in guests)):
            raise BadInput("row")
        net = total - refund
        clean_part = D0
        if status == "cancelled":
            pool = net - service
        elif cleaning_from is not None and month >= cleaning_from:
            clean_part = cleaning
            pool = net - service - cleaning
        else:
            pool = net - service
        if floor:
            pool = max(D0, pool)
        valid_guests = [g for g in guests if g in share] or [payer]
        for g in valid_guests:
            share[g] += pool / len(valid_guests)
        for p in PEOPLE:
            share[p] += clean_part / 3
        if payer in share:
            share[payer] += net - pool - clean_part
            paid[payer] += net
    out = []
    for p in PEOPLE:
        s, pd = share[p].quantize(CENT, ROUND_HALF_UP), paid[p].quantize(CENT, ROUND_HALF_UP)
        out.append({"person": p, "share": f"{s:.2f}", "paid": f"{pd:.2f}", "balance": f"{pd - s:.2f}"})
    return out


SETTLE_TEMPLATE = '''#!/usr/bin/env python3
"""Monthly settlement of the Dad-visit Airbnb stays between Emily, James and Megan.

Usage:
    BOOKINGS_CSV=bookings.csv MONTH=2026-10 OUT_CSV=settlement_2026-10.csv python3 settle.py

BOOKINGS_CSV is an export of the Bookings tab
(code,check_in,check_out,status,guests,paid_by,total,service_fee,cleaning_fee,refund).
Rules (Gmail thread "Dad visits - how we split the Airbnbs"):
  * a stay belongs to the month it checks in;
  * whoever paid keeps the card points and carries the Airbnb service fee;
  * what they actually paid after refunds, minus the service fee, is split evenly between the
    people who stayed (or were going to, for cancellations); a full refund means zero;
  * from October 2026 check-ins, the cleaning fee of a stay that happened is split three ways
    between all of us, whoever went;
  * balance = what you paid after refunds - your share.
Exit 0 on success, 2 (and no output) if a row in MONTH can't be read.
"""
import csv
import os
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PEOPLE = ["Emily", "James", "Megan"]
CLEANING_SPLIT_FROM = __CLEANING__
FLOOR_AT_ZERO = __FLOOR__
VALIDATE = __VALIDATE__


def fail(msg):
    print(f"settle.py: {msg}", file=sys.stderr)
    sys.exit(2)


def main():
    path, month, out = os.environ.get("BOOKINGS_CSV"), os.environ.get("MONTH", ""), os.environ.get("OUT_CSV")
    if not path or not out or len(month) != 7:
        fail("set BOOKINGS_CSV, MONTH (YYYY-MM) and OUT_CSV")
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")
    share = {p: Decimal(0) for p in PEOPLE}
    paid = {p: Decimal(0) for p in PEOPLE}
    for n, row in enumerate(rows, 2):
        if row.get("check_in", "")[:7] != month:
            continue
        status = row.get("status", "").lower()
        guests = [g.strip() for g in row.get("guests", "").split(";") if g.strip()]
        payer = row.get("paid_by", "")
        try:
            total, service, cleaning, refund = (Decimal(row.get(k, "")) for k in
                                                ("total", "service_fee", "cleaning_fee", "refund"))
        except InvalidOperation:
            if VALIDATE:
                fail(f"line {n}: amounts must be numbers")
            continue
        if VALIDATE:
            if status not in ("confirmed", "cancelled"):
                fail(f"line {n}: unknown status {status!r}")
            if payer not in PEOPLE or not guests or any(g not in PEOPLE for g in guests):
                fail(f"line {n}: unknown person")
        net = total - refund
        clean_part = Decimal(0)
        if status == "cancelled":
            pool = net - service
        elif CLEANING_SPLIT_FROM is not None and month >= CLEANING_SPLIT_FROM:
            clean_part = cleaning
            pool = net - service - cleaning
        else:
            pool = net - service
        if FLOOR_AT_ZERO:
            pool = max(Decimal(0), pool)
        stayed = [g for g in guests if g in share] or [payer]
        for g in stayed:
            share[g] += pool / len(stayed)
        for p in PEOPLE:
            share[p] += clean_part / 3
        if payer in share:
            share[payer] += net - pool - clean_part
            paid[payer] += net
    cent = Decimal("0.01")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["person", "share", "paid", "balance"])
        for p in PEOPLE:
            s, pd = share[p].quantize(cent, ROUND_HALF_UP), paid[p].quantize(cent, ROUND_HALF_UP)
            w.writerow([p, f"{s:.2f}", f"{pd:.2f}", f"{pd - s:.2f}"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def settle_script(cleaning='"2026-10"', floor=True, validate=True) -> str:
    return (SETTLE_TEMPLATE.replace("__CLEANING__", cleaning).replace("__FLOOR__", str(floor))
            .replace("__VALIDATE__", str(validate)))


def csv_text(rows, header=COLUMNS) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in header})
    return buf.getvalue()


# ---------------------------------------------------------------- replay mutations (hidden inputs)
def synth(code, lid, ci, co, guests, status="confirmed", payer="Emily", refund="partial"):
    p = compute_price(lid, ci, co)
    rf = 0.0
    if status == "cancelled":
        rf = p["total"] if refund == "full" else partial_refund(p)
    return {"code": code, "check_in": ci, "check_out": co, "status": status, "guests": guests, "paid_by": payer,
            "total": m(p["total"]), "service_fee": m(p["serviceFee"]), "cleaning_fee": m(p["cleaningFee"]),
            "refund": m(rf)}


def mutations():
    gold = golden_rows()
    nov = [
        synth("HMX1D4C8RT", "lst_019", "2026-12-04", "2026-12-06", "James"),
        booking_row("N1"),
        synth("HMP6W2Z9QJ", "lst_016", "2026-11-13", "2026-11-15", "James; Megan", "cancelled", "James", "full"),
        synth("HMB3H7K1VS", "lst_020", "2026-11-06", "2026-11-09", "Megan; Emily", payer="Megan"),
        booking_row("O5"),
        booking_row("O3"),
        synth("HMN5T8R2GA", "lst_018", "2026-11-19", "2026-11-22", "Emily", "cancelled", "Emily", "partial"),
    ]
    dec = [
        synth("HMD2K6P9WE", "lst_017", "2026-11-30", "2026-12-02", "Emily; James"),
        synth("HMD7Q3L5BY", "lst_020", "2026-12-11", "2026-12-13", "Megan", payer="Megan"),
        synth("HMD4S9V2NC", "lst_019", "2026-12-17", "2026-12-20", "Emily; James; Megan", payer="James"),
        synth("HMD8F1M6TX", "lst_016", "2026-12-05", "2026-12-07", "James", "cancelled", "James", "partial"),
        synth("HMD5R2X8HU", "lst_017", "2026-12-30", "2027-01-02", "James; Megan"),
        synth("HMD9C4J7ZG", "lst_018", "2027-01-01", "2027-01-04", "Emily"),
    ]
    bad = [booking_row("O5"), booking_row("N1"),
           synth("HMB6Y1N4QD", "lst_020", "2026-11-14", "2026-11-16", "Emily; Dad")]
    specs = [
        ("M1_october_golden", "2026-10", gold, "golden Bookings export, October: cleaning split, cancelled partial, James-paid stay"),
        ("M2_september_old_rule", "2026-09", gold, "same file, September: old rule (no cleaning split), Sep 29 stay counts, cancelled partial"),
        ("M3_november_mixed", "2026-11", nov, "November: full refund (zero), Megan pays, spaces in names, Oct/Dec rows ignored"),
        ("M4_december_boundary", "2026-12", dec, "December: Nov 30 stay excluded, Dec 30-Jan 2 included, Jan 1 excluded, James pays"),
        ("M5_unknown_person", "2026-11", bad, "a November row lists Dad as a guest -> exit 2, no output"),
        ("M6_empty_month", "2027-01", gold, "no stays check in that month -> three zero rows"),
    ]
    out = []
    for mid, month, rows, note in specs:
        try:
            expect = {"exit": 0, "rows": settle(rows, month)}
        except BadInput:
            expect = {"exit": 2, "rows": None}
        out.append({"id": mid, "month": month, "note": note, "bookings_csv": csv_text(rows), "expect": expect})
    return out


# ---------------------------------------------------------------- airbnb
def msg(mid, conv, sender, body, ts, kind="text"):
    return {"id": mid, "conversationId": conv, "senderId": sender, "kind": kind, "body": body, "attachments": [],
            "reactions": [], "createdAt": ts, "readAt": ts, "editedAt": None, "deletedAt": None, "translated": False}


def reservation(rid, code, lid, ci, co, adults, created, note, status="confirmed", cancellation=None,
                alterations=None, plan="full", pm="pm_001", price=None):
    host, title, city, *_ , policy = LISTINGS[lid]
    p = price or compute_price(lid, ci, co)
    paid = p["total"] if plan == "full" else round2(p["total"] / 2)
    return {"id": rid, "confirmationCode": code, "listingId": lid, "hostId": host, "guestId": "user_001",
            "checkIn": ci, "checkOut": co, "nights": p["nights"],
            "guests": {"adults": adults, "children": 0, "infants": 0, "pets": 0}, "status": status,
            "bookingType": "instant", "rateType": "refundable", "cancellationPolicy": policy, "priceBreakdown": p,
            "paymentPlan": plan, "amountPaid": paid, "paymentMethodId": pm, "messageToHost": note,
            "tripReason": None, "conversationId": f"conv_{rid[4:]}", "createdAt": created, "confirmedAt": created,
            "cancellation": cancellation, "alterations": alterations or []}


def short(d: str) -> str:
    from datetime import date
    x = date.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}"


def build_airbnb():
    reviews = json.loads((HERE / "airbnb_reviews.json").read_text())["reviews"]
    R, C, M = [], [], []

    def add(rid, key_or_code, lid, ci, co, adults, created, note, host_msgs=(), **kw):
        r = reservation(rid, key_or_code, lid, ci, co, adults, created, note, **kw)
        conv = r["conversationId"]
        ms = [msg(f"msg_{rid[4:]}1", conv, "user_001", note, created),
              msg(f"msg_{rid[4:]}2", conv, "system",
                  f"Reservation confirmed · {short(ci)} – {short(co)} · {adults} guest{'s' if adults > 1 else ''}",
                  created, kind="system")]
        for i, (sender, body, ts, kind) in enumerate(host_msgs, 3):
            ms.append(msg(f"msg_{rid[4:]}{i}", conv, sender, body, ts, kind))
        R.append(r)
        M.extend(ms)
        C.append({"id": conv, "type": "reservation", "listingId": lid, "reservationId": rid,
                  "participantIds": ["user_001", r["hostId"]], "hostId": r["hostId"],
                  "lastMessageAt": max(x["createdAt"] for x in ms), "unreadCount": 0, "starred": False,
                  "archived": False, "createdAt": created})
        return r

    def dad(key, rid, created, note, host_msgs=(), **kw):
        _, code, lid, ci, co, guests, adults, *_ = STAY[key]
        return add(rid, code, lid, ci, co, adults, created, note, host_msgs, **kw)

    t, r = "user_107", "user_108"
    dad("A1", "res_301", "2026-07-24T18:10:00.000Z", "Hi Rachel! I'm in town to visit my dad, who's in rehab at Blue Ridge Rehab after hip surgery. Just me, quiet guest.",
        [(r, "Welcome Emily, hope your dad's recovery goes well. Keypad code comes the morning of check-in.", "2026-07-24T19:02:00.000Z", "text")])
    dad("A2", "res_302", "2026-08-03T16:45:00.000Z", "Hi Tom, my brother, sister and I are visiting our dad together that weekend. Three adults.",
        [(t, "Happy to have you all. The hot tub is ready, firewood by the shed.", "2026-08-03T17:30:00.000Z", "text")])
    dad("S1", "res_303", "2026-08-25T21:00:00.000Z", "Booking this for my sister Megan, she'll be driving up to see our dad. She'll check in on her own.",
        [(r, "No problem, I'll send Megan's code to you the day before.", "2026-08-25T22:14:00.000Z", "text")])
    p_s3 = compute_price("lst_016", "2026-09-18", "2026-09-20")
    rf_s3 = partial_refund(p_s3)
    s3 = dad("S3", "res_304", "2026-09-01T15:20:00.000Z", "Hi Tom, coming to see my dad for the weekend. Just me.", (),
             status="cancelled",
             cancellation={"cancelledBy": "user_001", "reason": "my_plans_changed", "reasonText": "My travel plans changed",
                           "note": "Dad's PT schedule moved", "refundAmount": rf_s3, "nonRefundedAmount": round2(p_s3["total"] - rf_s3),
                           "refundTier": "partial", "cancelledAt": CANCELLED_AT["S3"]})
    M.append(msg("msg_3049", s3["conversationId"], "system", f"Reservation cancelled · Refund of {usd(rf_s3)} on its way",
                 CANCELLED_AT["S3"], "system"))
    dad("S4", "res_305", "2026-09-10T17:00:00.000Z", "Hi Tom! My sister and I are back to see our dad, two of us this time.",
        [(t, "Welcome back! Checkout Friday Oct 2 by 10.", "2026-09-10T17:40:00.000Z", "text")])
    add("res_306", "HMF2C9D7UX", "lst_020", "2026-10-02", "2026-10-04", 2, "2026-09-12T03:30:00.000Z",
        "Hi Tom, my partner Sam is flying in after my family visit and we're staying on for a leaf-peeping weekend, just the two of us. It's our anniversary!",
        [(t, "Congrats to you both! I'll leave a bottle of cider in the fridge.", "2026-09-12T04:05:00.000Z", "text")])
    p_o1 = compute_price("lst_016", "2026-10-09", "2026-10-11")
    rf_o1 = partial_refund(p_o1)
    o1 = dad("O1", "res_307", "2026-09-20T18:00:00.000Z", "Hi Tom, booking this for my sister Megan, she's visiting our dad.",
             [(t, "Got it, I'll look out for Megan.", "2026-09-20T18:30:00.000Z", "text")],
             status="cancelled",
             cancellation={"cancelledBy": "user_001", "reason": "extenuating", "reasonText": "I have an emergency or unavoidable event",
                           "note": "My nephew is sick, Megan can't travel", "refundAmount": rf_o1,
                           "nonRefundedAmount": round2(p_o1["total"] - rf_o1), "refundTier": "partial",
                           "cancelledAt": CANCELLED_AT["O1"]})
    M.append(msg("msg_3079", o1["conversationId"], "system", f"Reservation cancelled · Refund of {usd(rf_o1)} on its way",
                 CANCELLED_AT["O1"], "system"))
    M.append(msg("msg_3078", o1["conversationId"], t, "So sorry to hear, hope he feels better soon.", "2026-10-06T14:00:00.000Z"))
    old_o2 = compute_price("lst_017", *O2_ORIGINAL)
    new_o2 = compute_price("lst_017", "2026-10-16", "2026-10-19")
    o2 = dad("O2", "res_308", "2026-09-28T20:15:00.000Z", "Hi Tom, my brother James will be staying, he's in town to take our dad to appointments.",
             [(t, "Sounds good, James is welcome any time.", "2026-09-28T20:40:00.000Z", "text")],
             alterations=[{"id": "alt_308a", "actorId": "user_001",
                           "from": {"checkIn": O2_ORIGINAL[0], "checkOut": O2_ORIGINAL[1], "guests": {"adults": 1, "children": 0, "infants": 0, "pets": 0}},
                           "to": {"checkIn": "2026-10-16", "checkOut": "2026-10-19", "guests": {"adults": 1, "children": 0, "infants": 0, "pets": 0}},
                           "priceDiff": round2(new_o2["total"] - old_o2["total"]), "status": "accepted",
                           "createdAt": "2026-10-12T02:10:00.000Z"}])
    M.append(msg("msg_3089", o2["conversationId"], "system", "Reservation changed · Oct 16 – 19", "2026-10-12T02:10:00.000Z", "system"))
    dad("O3", "res_309", "2026-10-04T16:00:00.000Z", "Hi Rachel, my sister and I are coming to see our dad again and wanted to try the castle!",
        [(r, "Wonderful, the tower bedroom is all yours. Mind the spiral stairs!", "2026-10-04T16:45:00.000Z", "text")])
    old_o5 = compute_price("lst_018", *O5_ORIGINAL)
    new_o5 = compute_price("lst_018", "2026-11-01", "2026-11-03")
    o5 = dad("O5", "res_310", "2026-10-10T19:30:00.000Z", "Hi Rachel, booking for my sister Megan again, she's visiting our dad.",
             [(r, "Always happy to have Megan back.", "2026-10-10T20:00:00.000Z", "text")],
             alterations=[{"id": "alt_310a", "actorId": "user_001",
                           "from": {"checkIn": O5_ORIGINAL[0], "checkOut": O5_ORIGINAL[1], "guests": {"adults": 1, "children": 0, "infants": 0, "pets": 0}},
                           "to": {"checkIn": "2026-11-01", "checkOut": "2026-11-03", "guests": {"adults": 1, "children": 0, "infants": 0, "pets": 0}},
                           "priceDiff": round2(new_o5["total"] - old_o5["total"]), "status": "accepted",
                           "createdAt": "2026-10-27T15:20:00.000Z"}])
    M.append(msg("msg_3109", o5["conversationId"], "system", "Reservation changed · Nov 1 – 3", "2026-10-27T15:20:00.000Z", "system"))
    M.append(msg("msg_3108", o5["conversationId"], "user_001", "Megan's flight got moved, so we shifted it by a day. Thanks Rachel!", "2026-10-27T15:22:00.000Z"))
    dad("N1", "res_311", "2026-11-02T18:00:00.000Z", "Hi Tom, all three of us are coming for Thanksgiving with our dad!",
        [(t, "Wonderful! I'll make sure the big table is set up.", "2026-11-02T18:25:00.000Z", "text")])
    # personal noise
    p312 = compute_price("lst_056", "2026-10-17", "2026-10-19")
    c312 = add("res_312", "HMU6E3W9KF", "lst_056", "2026-10-17", "2026-10-19", 2, "2026-09-02T22:00:00.000Z",
               "Hi Grace, Sam and I would love a quiet weekend by the stove.", (), status="cancelled",
               cancellation={"cancelledBy": "user_120", "reason": "host_asked_cancel", "reasonText": "Host cancelled",
                             "note": "Chimney repair", "refundAmount": p312["total"], "nonRefundedAmount": 0,
                             "refundTier": "full", "cancelledAt": "2026-10-03T15:00:00.000Z"})
    M.append(msg("msg_3129", c312["conversationId"], "user_120", "I'm so sorry, the chimney inspector failed the stove. I've cancelled with a full refund.",
                 "2026-10-03T15:00:00.000Z"))
    add("res_313", "HMA9J2K6WD", "lst_006", "2026-06-12", "2026-06-14", 2, "2026-05-01T17:00:00.000Z",
        "Hi Daniel, a desert weekend for two!", [("user_103", "Gate code 4821, park left of the boulder.", "2026-06-11T20:00:00.000Z", "text")])
    add("res_314", "HMP4L8X2QM", "lst_036", "2026-12-19", "2026-12-26", 2, "2026-10-21T19:00:00.000Z",
        "Bonjour Camille! Christmas in Paris with my partner.", [("user_115", "Bienvenue! I'll leave a list of bakeries.", "2026-10-21T20:00:00.000Z", "text")],
        plan="split")
    add("res_315", "HMB7N3V5TY", "lst_031", "2026-11-06", "2026-11-09", 1, "2026-10-15T16:00:00.000Z",
        "Hi David, in town for a client workshop.", [("user_113", "Wifi password is on the fridge.", "2026-11-06T22:00:00.000Z", "text")],
        pm="pm_002")
    add("res_316", "HMT8Q1Z4LP", "lst_002", "2027-01-15", "2027-01-18", 4, "2026-11-10T18:00:00.000Z",
        "Hi Michael, ski weekend with friends!", ())

    notifications = [
        {"id": "ntf_301", "type": "booking", "title": "Your reservation is confirmed", "body": "Thanksgiving in Asheville, Nov 25 – 29",
         "link": "/trips/res_311", "read": True, "createdAt": "2026-11-02T18:00:00.000Z"},
        {"id": "ntf_302", "type": "booking", "title": "Reservation changed", "body": "Modern Tiny Home in the Woods, now Nov 1 – 3",
         "link": "/trips/res_310", "read": True, "createdAt": "2026-10-27T15:20:00.000Z"},
        {"id": "ntf_303", "type": "review_reminder", "title": "Leave a review for Rachel's place",
         "body": "Share how your stay at the Hidden Forest Treehouse Castle went.", "link": "/reviews/write/res_309",
         "read": False, "createdAt": "2026-10-26T18:00:00.000Z"},
        {"id": "ntf_304", "type": "booking", "title": "Reservation cancelled", "body": "Your refund of " + usd(rf_o1) + " is on its way",
         "link": "/trips/res_307", "read": True, "createdAt": CANCELLED_AT["O1"]},
    ]
    return {
        "currentUser": {"email": EMILY, "about": "Product designer who loves cabins, long hikes and slow mornings. Flying to Asheville a lot lately to see my dad."},
        "reservations": R, "conversations": C, "messages": M, "reviews": reviews, "notifications": notifications,
        "experienceBookings": [], "reports": [],
    }


# ---------------------------------------------------------------- google sheets
def cell(v, bold=False, bg=None):
    v = str(v)
    c = {"value": v, "formula": v, "computed": v if (v == "" or not _isnum(v)) else float(v)}
    if bold or bg:
        c["style"] = {k: val for k, val in (("bold", bold or None), ("bg", bg)) if val}
    return c


def _isnum(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


def col(i):
    return chr(65 + i)


def table(header, rows):
    data = {}
    for j, h in enumerate(header):
        data[f"{col(j)}1"] = cell(h, bold=True, bg="#E8EAED")
    for i, r in enumerate(rows, 2):
        for j, h in enumerate(header):
            if r.get(h, "") != "":
                data[f"{col(j)}{i}"] = cell(r[h])
    return data


def settlement_records(rows):
    out = []
    for month in ("2026-08", "2026-09"):
        for r in settle(rows, month):
            out.append({"month": month, **r})
    return out


NOTES = [
    "How we split (agreed Aug 2, see James's email)",
    "Settle once a month. A stay counts in the month it checks in.",
    "Whoever books pays the Airbnb service fee (they keep the card points).",
    "The rest of what was paid, after refunds, is split evenly between whoever stayed.",
    "Cancelled trips: what we didn't get back, minus the service fee, is split between whoever was going.",
    "Balance = what you paid after refunds minus your share. Positive = you get money back.",
    "",
    "Bookings tab: one row per Airbnb booking, guests = first names, amounts in USD from the receipt.",
]


def build_sheets():
    rows = seed_rows()
    settled = settlement_records(golden_rows())
    sheets = [
        {"id": "sheet_bookings", "name": "Bookings", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 0,
         "tabColor": "#0F9D58", "isHidden": False,
         "columnWidths": {"0": 120, "1": 100, "2": 100, "3": 90, "4": 160, "5": 80, "6": 90, "7": 90, "8": 95, "9": 80},
         "data": table(COLUMNS, rows)},
        {"id": "sheet_settlement", "name": "Settlement", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 0,
         "tabColor": "#1A73E8", "isHidden": False, "columnWidths": {"0": 90},
         "data": table(["month"] + SETTLE_HEADER, settled)},
        {"id": "sheet_notes", "name": "Notes", "rowCount": 100, "colCount": 26, "frozenRows": 0, "frozenCols": 0,
         "tabColor": None, "isHidden": False, "columnWidths": {"0": 620},
         "data": {f"A{i}": cell(t, bold=(i == 1)) for i, t in enumerate(NOTES, 1) if t}},
    ]
    return {"id": "workbook_dad", "title": SHEET_TITLE, "sheets": sheets, "activeSheetId": "sheet_bookings",
            "selectedCell": "A1", "selectionRange": None, "clipboard": None, "isDragging": False, "undoStack": [],
            "redoStack": [], "namedRanges": [], "conditionalFormats": [], "charts": [], "showGridlines": True,
            "showFormulas": False, "zoom": 100}


def sheet_by_name(state, name):
    return next(s for s in state["sheets"] if s["name"] == name)


def ui_set(sheet, ref, value):
    """Typing a value into a cell: value/formula/computed as the mock's updateCell writes them."""
    v = str(value)
    existing = sheet["data"].get(ref, {"value": "", "formula": ""})
    sheet["data"][ref] = {**existing, "value": v, "formula": v,
                          "computed": (v if v == "" or not _isnum(v) else float(v))}


def apply_bookings(sheet, rows):
    """Make the Bookings tab equal `rows` (row 2.. in order), editing only cells that differ."""
    for i, r in enumerate(rows, 2):
        for j, h in enumerate(COLUMNS):
            ref = f"{col(j)}{i}"
            have = sheet["data"].get(ref, {}).get("value", "")
            if have != r.get(h, ""):
                ui_set(sheet, ref, r.get(h, ""))


def append_settlement(sheet, month, result):
    last = max(int(k[1:]) for k in sheet["data"])
    for i, r in enumerate(result, last + 1):
        for j, h in enumerate(["month"] + SETTLE_HEADER):
            ui_set(sheet, f"{col(j)}{i}", month if h == "month" else r[h])


# ---------------------------------------------------------------- gmail
def addr(name, email):
    return {"name": name, "email": email}


NAMES = {EMILY: "Emily Carter", JAMES: "James Carter", MEGAN: "Megan Ruiz", "automated@airbnb.com": "Airbnb",
         "news@airbnb.com": "Airbnb", "care.team@blueridgerehab.org": "Blue Ridge Rehab", "sam.okoro@gmail.com": "Sam Okoro",
         "alerts@chase.com": "Chase", "noreply@delta.com": "Delta Air Lines", "hello@lumenstudio.co": "Lumen Studio",
         "noreply@venmo.com": "Venmo"}


def email(eid, frm, to, subject, body, ts, thread=None, read=True, category="primary", folder="inbox", cc=()):
    fname = NAMES.get(frm, frm.split("@")[0])
    return {"id": eid, "threadId": thread or f"t_{eid}", "from": {**addr(fname, frm), "avatar": avatar(fname)},
            "to": [addr(NAMES.get(x, x), x) for x in to], "cc": [addr(NAMES.get(x, x), x) for x in cc], "bcc": [],
            "subject": subject, "body": body, "snippet": "", "timestamp": ts, "read": read, "starred": False,
            "important": False, "labels": [], "category": category, "folder": folder, "attachments": []}


def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def receipt_html(title, ci, co, pr, code):
    lines = [f"Confirmation code: {code}", f"{title}", f"{short(ci)} – {short(co)}, 2026 · 1 guest",
             f"{usd(pr['nightlyRate'])} x {pr['nights']} nights: {usd(pr['nightsSubtotal'])}",
             f"Cleaning fee: {usd(pr['cleaningFee'])}", f"Airbnb service fee: {usd(pr['serviceFee'])}",
             f"Taxes: {usd(pr['taxes'])}", f"Total (USD): {usd(pr['total'])}"]
    return "<p>" + "<br>".join(lines) + "</p>"


def build_gmail():
    q = compute_price("lst_020", *O4_QUOTE)
    f4 = compute_price("lst_020", "2026-10-30", "2026-11-01")
    o2 = compute_price("lst_017", "2026-10-16", "2026-10-19")
    p_o1 = compute_price("lst_016", "2026-10-09", "2026-10-11")
    split_subject = "Dad visits - how we split the Airbnbs"
    E = [
        email("g01", JAMES, [EMILY, MEGAN], split_subject, p(
            "Hi both,",
            "Now that we're taking turns flying out to see Dad while he's at Blue Ridge Rehab, here's what I'd suggest for the Airbnbs so nobody has to think about it:",
            "1. We settle once a month. A stay belongs to the month it checks in, even if it runs into the next one.",
            "2. Whoever books keeps the card points, so they also eat the Airbnb service fee. The rest of what they actually paid (after any refund) gets split evenly between whoever stayed.",
            "3. If a trip gets cancelled, whatever we couldn't get back (still minus the service fee) is split between the people who were going to go. If Airbnb refunded the whole thing it's just zero for everyone.",
            "4. Each month we compare what everyone paid out (after refunds) with their share, and whoever's behind sends the difference to whoever's ahead.",
            "Em, since most bookings are on your account, could you keep the sheet?", "J"),
            "2026-08-02T17:12:00Z", thread="t_split"),
        email("g02", MEGAN, [JAMES, EMILY], "Re: " + split_subject, p("Works for me! Thanks for organizing, J."),
              "2026-08-02T18:40:00Z", thread="t_split"),
        email("g03", EMILY, [JAMES, MEGAN], "Re: " + split_subject,
              p("Yep, I'll log everything in the sheet (Bookings tab) and do the numbers at the start of each month."),
              "2026-08-02T19:05:00Z", thread="t_split", folder="sent"),
        email("g04", MEGAN, [JAMES, EMILY], "Re: " + split_subject, p(
            "One tweak before October? The cleaning fee is the same whether one of us goes or all three, and the solo trips are mostly someone driving Dad to PT, which helps all of us.",
            "Could we split cleaning fees three ways on every stay, no matter who went? Only for stays that actually happen, obviously, cancelled ones get the cleaning fee refunded anyway.", "M"),
            "2026-10-01T14:22:00Z", thread="t_split"),
        email("g05", JAMES, [MEGAN, EMILY], "Re: " + split_subject, p(
            "Fair. Let's do it starting with stays that check in in October. No redoing August and September, those are settled.",
            "Everything else stays as it is."), "2026-10-01T16:03:00Z", thread="t_split"),
        email("g06", EMILY, [JAMES, MEGAN], "Re: " + split_subject, p("Deal, I'll fold it in when I do October."),
              "2026-10-02T03:30:00Z", thread="t_split", folder="sent"),
        email("g07", JAMES, [EMILY], "Halloween weekend - booked it myself", p(
            "Hey Em, I booked the Fall Colors Cabin for my Halloween visit on my own account (I had a coupon on mine). Can you put it in the sheet? Receipt below.")
            + receipt_html(LISTINGS["lst_020"][1], *O4_QUOTE, q, STAY["O4"][1]),
            "2026-10-20T04:15:00Z", thread="t_hallo"),
        email("g08", JAMES, [EMILY], "Re: Halloween weekend - booked it myself", p(
            "Change of plans, I have to be back for a work thing on Sunday so I shortened it to two nights (Oct 30 to Nov 1). Airbnb sent an updated receipt, this one replaces the one above:")
            + receipt_html(LISTINGS["lst_020"][1], "2026-10-30", "2026-11-01", f4, STAY["O4"][1]),
            "2026-10-28T22:47:00Z", thread="t_hallo"),
        email("g09", MEGAN, [EMILY], "October?", p(
            "Hi Em, whenever you get to October, no rush.",
            "Also I don't see our castle weekend in the sheet (the treehouse castle in Black Mountain, Oct 23-26, you and me), can you add it? Lucas still talks about the spiral stairs.", "M"),
            "2026-11-03T15:10:00Z", thread="t_oct"),
        email("g10", JAMES, [EMILY], "Taking over the bookings in December", p(
            "Em, as discussed, I'll take over booking the Asheville stays from December so you get a break.",
            "Could you leave me something I can just rerun every month? I'll download the Bookings tab as a CSV at the start of each month and would rather not redo the math by hand and get the rules wrong.",
            "Thanks!! J"), "2026-11-16T20:30:00Z", thread="t_handover", read=False),
        # Airbnb transactional mail
        email("g11", "automated@airbnb.com", [EMILY], "Reservation canceled: Blue Ridge Treehouse with Wraparound Deck", p(
            f"Your reservation {STAY['O1'][1]} for Oct 9 – 11 has been canceled.",
            f"Refund: {usd(partial_refund(p_o1))} to Visa •••• 4242. Refunds can take 5-7 business days."),
            CANCELLED_AT["O1"].replace(".000", ""), category="primary"),
        email("g12", "automated@airbnb.com", [EMILY], "Your reservation change is confirmed", p(
            f"Your trip to Asheville ({STAY['O2'][1]}) is now Oct 16 – 19.",
            f"New total: {usd(o2['total'])}. The difference has been refunded to your payment method."),
            "2026-10-12T02:11:00Z"),
        email("g13", "automated@airbnb.com", [EMILY], "Reservation confirmed - Mountain Cabin w/ Hot Tub & Fire Pit", p(
            "Pack your bags! You're going to Asheville Nov 25 – 29.", f"Confirmation code: {STAY['N1'][1]}"),
            "2026-11-02T18:01:00Z"),
        email("g14", "automated@airbnb.com", [EMILY], "Reservation confirmed - Haussmann Apartment near Le Marais", p(
            "You're going to Paris Dec 19 – 26. You paid half now, the rest is due Dec 5."), "2026-10-21T19:01:00Z",
            category="primary"),
        # noise
        email("g15", "care.team@blueridgerehab.org", [EMILY, JAMES, MEGAN], "Walter Carter - care plan meeting Nov 20", p(
            "Dear Carter family, Walter's quarterly care plan meeting is Friday Nov 20 at 2pm ET. You can join by phone.",
            "He's walking the hallway twice a day now with the walker. - Blue Ridge Rehab care team"), "2026-11-12T16:00:00Z"),
        email("g16", "sam.okoro@gmail.com", [EMILY], "dinner friday?", p("Thai place on Valencia? I'll book 7:30."),
              "2026-11-17T23:10:00Z", read=False),
        email("g17", "alerts@chase.com", [EMILY], "Your statement is ready", p("Your Sapphire statement ending in 4242 is ready to view."),
              "2026-11-05T10:00:00Z", category="promotions"),
        email("g18", "noreply@delta.com", [EMILY], "Your trip to Asheville is confirmed", p("SFO → AVL Wed Nov 25, 7:05am. Confirmation GQ7TRX."),
              "2026-11-02T18:30:00Z"),
        email("g19", "hello@lumenstudio.co", [EMILY], "Design review moved to Thursday", p("Hi Emily, the Northwind review is now Thursday 10am."),
              "2026-11-17T17:00:00Z"),
        email("g20", "news@airbnb.com", [EMILY], "Wish lists for winter", p("Cozy cabins for the holidays."), "2026-11-14T13:00:00Z",
              category="promotions"),
        email("g21", MEGAN, [EMILY], "Thanksgiving pie assignments", p("I'm doing pecan, you're on pumpkin, James is 'bringing ice' as usual."),
              "2026-11-10T02:00:00Z"),
        email("g22", "noreply@venmo.com", [EMILY], "Megan Ruiz paid you $362.35", p("Megan Ruiz paid you $362.35 - \"Aug Airbnbs\""),
              "2026-10-04T15:00:00Z", category="social"),
    ]
    for e in E:
        if e["folder"] == "sent":
            e["read"] = True
        e["snippet"] = e["body"].replace("<p>", "").replace("</p>", " ").replace("<br>", " ")[:100]
    return {
        "user": {"userId": "u1", "username": "Emily Carter", "email": EMILY, "avatar": avatar("Emily Carter")},
        "emails": sorted(E, key=lambda e: e["timestamp"], reverse=True),
        "labels": [{"id": "l1", "name": "Family", "color": "#22c55e"}, {"id": "l2", "name": "Work", "color": "#3b82f6"}],
        "drafts": [],
        "settings": {"signature": "--\nEmily", "undoSend": 5},
    }


def sent_settlement_email(gmail, result, eid="sent_oct"):
    by = {r["person"]: r for r in result}

    def phrase(name):
        b = Decimal(by[name]["balance"])
        return (f"{name} owes {usd(float(-b))}" if b < 0 else f"{name} gets {usd(float(b))} back")
    body = p("Hi both,", "October is settled (stays checking in Oct 1-31, cleaning fees split three ways from this month):",
             "<br>".join(f"{r['person']}: share {usd(float(r['share']))}, paid {usd(float(r['paid']))}, balance {usd(float(r['balance']))}"
                         for r in result),
             f"So {phrase('James')} and {phrase('Megan')}. The Settlement tab has the same numbers.", "Em")
    e = email(eid, EMILY, [JAMES, MEGAN], "October Airbnb settlement", body, NOW.replace(".000", ""), folder="sent")
    e["to"] = [{"name": x, "email": x} for x in (JAMES, MEGAN)]  # compose writes name=email
    e["from"] = {"name": "Emily Carter", "email": EMILY, "avatar": avatar("Emily Carter")}
    e["snippet"] = body.replace("<p>", "").replace("</p>", " ")[:100]
    gmail["emails"].insert(0, e)


# ---------------------------------------------------------------- runs
def run(seed, rows, script, script_month_rows=None):
    """Apply a run: Bookings tab = rows, Settlement += result of `script` on rows, email sent."""
    sheets, gmail = copy.deepcopy(seed["google_sheets"]), copy.deepcopy(seed["gmail"])
    apply_bookings(sheet_by_name(sheets, "Bookings"), rows)
    result = run_script(script, rows, TARGET_MONTH)["rows"]
    append_settlement(sheet_by_name(sheets, "Settlement"), TARGET_MONTH, result)
    sent_settlement_email(gmail, result)
    states = {"airbnb": copy.deepcopy(seed["airbnb"]), "google_sheets": sheets, "gmail": gmail}
    outputs = {"bookings.csv": csv_text(rows), "settle.py": script,
               "settlement_2026-10.csv": csv_text(result, SETTLE_HEADER)}
    return states, outputs


def run_script(script, rows, month):
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "settle.py").write_text(script)
        (t / "in.csv").write_text(csv_text(rows) if isinstance(rows, list) else rows)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "BOOKINGS_CSV": str(t / "in.csv"),
               "MONTH": month, "OUT_CSV": str(t / "out.csv")}
        done = subprocess.run([sys.executable, str(t / "settle.py")], env=env, capture_output=True, text=True, timeout=30)
        out = None
        if (t / "out.csv").exists():
            out = list(csv.DictReader((t / "out.csv").open()))
        return {"exit": done.returncode, "rows": out}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def main(out: Path):
    seed = {"airbnb": build_airbnb(), "google_sheets": build_sheets(), "gmail": build_gmail()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    gold_rows = golden_rows()
    gold_script = settle_script()
    muts = mutations()
    # The reference script must agree with the reference rules on every hidden mutation.
    for mu in muts:
        got = run_script(gold_script, mu["bookings_csv"], mu["month"])
        assert got["exit"] == mu["expect"]["exit"], (mu["id"], got)
        if got["exit"] == 0:
            assert got["rows"] == mu["expect"]["rows"], (mu["id"], got["rows"], mu["expect"]["rows"])

    golden_states, golden_out = run(seed, gold_rows, gold_script)
    for site, state in golden_states.items():
        write_json(out / "golden" / f"{site}.json", state)
    for name, text in golden_out.items():
        (out / "golden_output").mkdir(parents=True, exist_ok=True)
        (out / "golden_output" / name).write_text(text)

    october = settle(gold_rows, TARGET_MONTH)
    old_rule_october = settle(gold_rows, TARGET_MONTH, cleaning_from=None)
    seed_sheet_rows = {r["code"]: r for r in seed_rows()}
    expected = {
        "clock": CLOCK, "target_month": TARGET_MONTH, "people": PEOPLE,
        "emails": {"Emily": EMILY, "James": JAMES, "Megan": MEGAN},
        "sheet": {"title": SHEET_TITLE, "bookings_tab": "Bookings", "settlement_tab": "Settlement", "notes_tab": "Notes",
                  "bookings_columns": COLUMNS, "settlement_columns": ["month"] + SETTLE_HEADER},
        "bookings_golden": {r["code"]: r for r in gold_rows},
        "bookings_seed": seed_sheet_rows,
        "october_codes": [STAY[k][1] for k in ("O1", "O2", "O3", "O4")],
        "checked_rows": {
            "cancelled_partial": STAY["O1"][1], "shortened": STAY["O2"][1], "missing_added": STAY["O3"][1],
            "james_updated_receipt": STAY["O4"][1], "moved_to_november": STAY["O5"][1]},
        "superseded": {"O4_quote": booking_row("O4", dates=O4_QUOTE),
                       "O2_original_dates": list(O2_ORIGINAL), "O5_original_dates": list(O5_ORIGINAL)},
        "non_targets": {"personal_oct_trip": "HMF2C9D7UX", "personal_cancelled_oct_trip": "HMU6E3W9KF",
                        "september_boundary_stay": STAY["S4"][1]},
        "settled_rows_before": settlement_records(gold_rows),
        "october_settlement": october,
        "october_settlement_old_rule": old_rule_october,
        "replay": {"script": "/workspace/output/settle.py", "env": ["BOOKINGS_CSV", "MONTH", "OUT_CSV"],
                   "output_header": SETTLE_HEADER, "tolerance": 0.02, "mutations": muts},
    }
    write_json(out / "expected.json", expected)

    variants = {"golden": (golden_states, golden_out), "nop": ({k: copy.deepcopy(v) for k, v in seed.items()}, {})}

    # naive: trusts the sheet's stale rows, misses the castle weekend, uses James's first quote,
    # old rule (Notes tab), no zero floor, no input validation.
    naive_rows = []
    for key in ORDER:
        if key == "O1":
            naive_rows.append(booking_row(key, status="confirmed", refund=0.0))
        elif key == "O2":
            row = booking_row(key)
            row["check_out"] = O2_ORIGINAL[1]
            naive_rows.append(row)
        elif key == "O4":
            naive_rows.append(booking_row(key, dates=O4_QUOTE))
        elif key == "O5":
            row = booking_row(key)
            row["check_in"], row["check_out"] = O5_ORIGINAL
            naive_rows.append(row)
        else:
            naive_rows.append(booking_row(key))
    variants["naive"] = run(seed, naive_rows, settle_script("None", floor=False, validate=False))

    variants["slip_floor"] = run(seed, gold_rows, settle_script(floor=False))
    variants["slip_validation"] = run(seed, gold_rows, settle_script(validate=False))
    variants["slip_effective_date"] = run(seed, gold_rows, settle_script('""'))
    moved = [dict(r) for r in gold_rows]
    for r in moved:
        if r["code"] == STAY["O5"][1]:
            r["check_in"], r["check_out"] = O5_ORIGINAL
    variants["slip_moved_stay"] = run(seed, moved, gold_script)
    quote = [booking_row("O4", dates=O4_QUOTE) if r["code"] == STAY["O4"][1] else dict(r) for r in gold_rows]
    variants["slip_james_quote"] = run(seed, quote, gold_script)

    for name, (states, outputs) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        (out / "variants" / name / "output").mkdir(parents=True, exist_ok=True)
        for fname, text in outputs.items():
            (out / "variants" / name / "output" / fname).write_text(text)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
