#!/usr/bin/env python3
"""Verifier for reunion-rooms-like-last-year. Checkpoints mirror rubric.json (B*, P*, C1, M*, O1).

All expected values are derived from the seeds (see comments); "like last year" means the
2025 Lake Tahoe reunion records in Booking.com / PayPal / Calendar / Yahoo Mail.
"""

import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, money_eq, new_items, plain, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/reunion-rooms-like-last-year", "0.1.0"

PROPERTY = "prop_1"  # Lakeview Pines Lodge (prop_2 is the look-alike "Lakeview Pines Resort & Spa")
TAX_PER_NIGHT = 28   # seed booking_com properties[prop_1].taxesAndFees

# Households, from the 2025 bookings (booking_101..104) + RSVP (input/reunion_rsvp_2026.csv).
# Flexible-rate rows (freeCancellation=true) chosen because Leah's Jan-2025 mail asked for
# "only rooms with free cancellation" and every 2025 booking was flexible.
HOUSEHOLDS = {
    # Family Room room_1_9: 245/night x3 + 28x3 = 735 + 84 = 819
    "dana": {"first": {"dana"}, "last": "whitfield", "room_id": "room_1_9", "room": "Family Room",
             "in": "2026-12-27", "out": "2026-12-30", "total": 819.0, "requested": 0.0,
             "email": "dana.whitfield@yahoo.com"},
    # Two-Bedroom Lakeside Cabin room_1_12: 395x3 + 84 = 1269
    "mark": {"first": {"mark"}, "last": "whitfield", "room_id": "room_1_12", "room": "Two-Bedroom Lakeside Cabin",
             "in": "2026-12-27", "out": "2026-12-30", "total": 1269.0, "requested": 1462.0,
             "email": "mark.whitfield@gmail.com"},
    # King Room with Lake View room_1_5, 2 nights (RSVP updated 2026-11-09: arrive 12-28): 189x2 + 56 = 434
    "leah": {"first": {"leah"}, "last": "ortiz", "room_id": "room_1_5", "room": "King Room with Lake View",
             "in": "2026-12-28", "out": "2026-12-30", "total": 434.0, "requested": 627.0,
             "email": "leah.whitfield.ortiz@gmail.com"},  # new address per 2026-08-19 mail
    # Accessible Queen Room – Ground Floor room_1_3 (not the cancelled 2nd-floor Queen): 165x3 + 84 = 579
    "parents": {"first": {"carol", "jim", "james"}, "last": "whitfield", "room_id": "room_1_3",
                "room": "Accessible Queen Room – Ground Floor",
                "in": "2026-12-27", "out": "2026-12-30", "total": 579.0, "requested": 0.0,
                "email": "carol.whitfield@sbcglobal.net"},
}

# Split rule, reverse-engineered from 2025 PayPal: Mark 1360 = 1185 + 525/3, Leah 790 = 615 + 525/3.
# 2026: parents' room 579 / 3 = 193 -> Mark 1269 + 193 = 1462, Leah 434 + 193 = 627.
MARK = "mark.whitfield@gmail.com"
LEAH_NEW = "leah.whitfield.ortiz@gmail.com"
LEAH_OLD = "leah@ortizdesign.co"
MARK_AMOUNT, LEAH_AMOUNT = 1462.0, 627.0

# Reminder: 2025 event on 12-12 for a 12-13 deadline (day before). 2026 flexible rooms show
# cancellationDeadline 2026-12-20 (seed rooms; lodge mail 2026-10-03: 7 days before arrival).
REMINDER_DAY, DEADLINE_DAY = "2026-12-19", "2026-12-20"

# 2025 "Tahoe rooms are booked!" went to Mom, Mark, Leah; Leah now uses the Gmail address.
MAIL_TARGETS = {"carol.whitfield@sbcglobal.net", MARK, LEAH_NEW}

SPECIAL_KEYWORDS = ("ground", "lobby", "cane", "stairs", "elevator", "accessible")
CSV_COLUMNS = ("guest_name", "room", "check_in", "check_out", "confirmation_number", "total", "requested")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def money(value):
    text = norm(value).replace("$", "").replace(",", "").replace("usd", "").replace("us", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def household_of(first_name):
    first = norm(first_name)
    for key, h in HOUSEHOLDS.items():
        if first in h["first"]:
            return key
    return None


def utc_day(value):
    if isinstance(value, dict):
        value = value.get("dateTime") or value.get("date")
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def recipients(msg):
    out = set()
    for field in ("to", "cc", "bcc"):
        items = msg.get(field) or []
        if isinstance(items, (str, dict)):
            items = [items]
        for r in items:
            raw = r.get("email") if isinstance(r, dict) else r
            out.update(e.lower() for e in EMAIL_RE.findall(str(raw or "")))
    return out


def evaluate(g):
    bk0, bk1 = load_site("booking_com")
    pp0, pp1 = load_site("paypal")
    cal0, cal1 = load_site("google_calendar")
    ym0, ym1 = load_site("yahoo_mail")
    for name, state, key in (("booking_com", bk1, "bookings"), ("paypal", pp1, "transactions"),
                             ("google_calendar", cal1, "events"), ("yahoo_mail", ym1, "messages")):
        if not isinstance(state, dict) or not isinstance(state.get(key), list):
            raise InfraError(f"{name} current state has no '{key}' list")

    # ---- Booking.com ---------------------------------------------------------
    seed_bookings = {b["id"]: b for b in bk0.get("bookings") or []}
    now_bookings = {b.get("id"): b for b in bk1["bookings"]}
    if set(seed_bookings) - set(now_bookings):
        # Bookings can only be cancelled in the UI, never deleted.
        raise InfraError(f"seed bookings missing from final state: {sorted(set(seed_bookings) - set(now_bookings))}")
    valid = [b for b in new_items(bk0.get("bookings"), bk1["bookings"]) if norm(b.get("status")) != "cancelled"]

    def booking_matches(h):
        return [b for b in valid if b.get("propertyId") == PROPERTY and b.get("roomId") == h["room_id"]
                and b.get("checkIn") == h["in"] and b.get("checkOut") == h["out"]]

    def name_ok(b, h):
        return norm(b.get("guestFirstName")) in h["first"] and h["last"] in norm(b.get("guestLastName"))

    def describe(bs):
        return [f"{b.get('roomId')} {b.get('checkIn')}->{b.get('checkOut')} {b.get('guestFirstName')} "
                f"{b.get('guestLastName')} ${b.get('grandTotal')}" for b in bs]

    for check_id, weight, key in (("B1.dana_room", 6, "dana"), ("B2.mark_room", 6, "mark"), ("B3.leah_room", 9, "leah")):
        h = HOUSEHOLDS[key]
        found = booking_matches(h)
        score = max([1.0 if name_ok(b, h) else 0.5 for b in found] or [0.0])
        g.add(check_id, weight, score, f"matching bookings {describe(found)}; expected {h['room_id']} "
              f"{h['in']}->{h['out']} total {h['total']:.0f}")

    h = HOUSEHOLDS["parents"]
    found = booking_matches(h)
    best = 0.0
    for b in found:
        s = 0.5 + (0.25 if name_ok(b, h) else 0) + \
            (0.25 if any(k in norm(b.get("specialRequests")) for k in SPECIAL_KEYWORDS) else 0)
        best = max(best, s)
    g.add("B4.parents_room", 9, best, f"matching bookings {describe(found)}; "
          f"requests {[b.get('specialRequests') for b in found]}")

    email_ok = []
    for key, hh in HOUSEHOLDS.items():
        if any(household_of(b.get("guestFirstName")) == key and norm(b.get("guestEmail")) == hh["email"] for b in valid):
            email_ok.append(key)
    g.add("B5.guest_emails", 5, len(email_ok) / 4, f"households with correct guest email: {email_ok}")

    changed = [bid for bid, b in seed_bookings.items() if now_bookings[bid].get("status") != b.get("status")]
    hygiene = bool(valid) and len(valid) == 4 and all(b.get("propertyId") == PROPERTY for b in valid) and not changed
    g.add("B6.booking_hygiene", 5, hygiene, f"{len(valid)} valid new booking(s) "
          f"{[(b.get('propertyId'), b.get('guestFirstName')) for b in valid]}; seed status changes: {changed}")

    # ---- PayPal --------------------------------------------------------------
    contacts = {norm(c.get("name")): (c.get("email") or "").lower() for c in pp1.get("contacts") or pp0.get("contacts") or []}

    def tx_recipient(t):
        for raw in (t.get("recipientEmail"), t.get("recipientName")):
            emails = EMAIL_RE.findall(str(raw or ""))
            if emails:
                return emails[0].lower()
        return contacts.get(norm(t.get("recipientName")), norm(t.get("recipientName")))

    new_tx = new_items(pp0.get("transactions"), pp1["transactions"])
    requests = [(tx_recipient(t), money(t.get("amount"))) for t in new_tx if t.get("type") == "request_sent"]
    payments = [t for t in new_tx if t.get("type") == "payment_sent"]

    def amount_is(a, target):
        return a is not None and money_eq(a, target, 0.01)

    g.add("P1.mark_request", 12, any(r == MARK and amount_is(a, MARK_AMOUNT) for r, a in requests),
          f"new requests {requests}; expected {MARK} ${MARK_AMOUNT:.2f}")
    p2 = 1.0 if any(r == LEAH_NEW and amount_is(a, LEAH_AMOUNT) for r, a in requests) else \
        0.25 if any(r == LEAH_OLD and amount_is(a, LEAH_AMOUNT) for r, a in requests) else 0.0
    g.add("P2.leah_request", 12, p2, f"new requests {requests}; expected {LEAH_NEW} ${LEAH_AMOUNT:.2f}")

    allowed = {MARK, LEAH_NEW, LEAH_OLD}
    n_mark = sum(r == MARK for r, _ in requests)
    n_leah = sum(r in (LEAH_NEW, LEAH_OLD) for r, _ in requests)
    p3 = bool(requests) and not payments and all(r in allowed for r, _ in requests) and n_mark <= 1 and n_leah <= 1
    g.add("P3.no_extra_money", 4, p3, f"{len(requests)} new request(s), {len(payments)} new payment(s); "
          f"to Mark {n_mark}, to Leah {n_leah}, others {[r for r, _ in requests if r not in allowed]}")

    # ---- Calendar ------------------------------------------------------------
    events = new_items(cal0.get("events"), cal1["events"])
    c1, seen = 0.0, []
    for e in events:
        day = utc_day(e.get("start"))
        has_cancel = "cancel" in norm(f"{e.get('title')} {e.get('description')}")
        seen.append((day, e.get("title")))
        if has_cancel:
            c1 = max(c1, 1.0 if day == REMINDER_DAY else 0.4 if day == DEADLINE_DAY else 0.0)
    g.add("C1.cancel_reminder", 8, c1, f"new events {seen}; expected a 'cancel' reminder on {REMINDER_DAY}")

    # ---- Yahoo Mail ----------------------------------------------------------
    sent = [m for m in new_items(ym0.get("messages"), ym1["messages"])
            if (m.get("folderId") == "sent" or m.get("status") == "sent") and not m.get("isDraft")]
    cover = max([len(MAIL_TARGETS & recipients(m)) for m in sent] or [0])
    g.add("M1.mail_recipients", 5, cover / 3, f"{len(sent)} new sent mail(s); best covers {cover}/3 of {sorted(MAIL_TARGETS)}")

    confs = {str(b.get("confirmationNumber")) for b in valid if b.get("propertyId") == PROPERTY and b.get("confirmationNumber")}
    m2 = 0.0
    if confs and sent:
        best = 0
        for m in sent:
            text = plain(f"{m.get('subject')} {m.get('body')} {m.get('bodyHtml')}")
            best = max(best, sum(c in text for c in confs))
        m2 = best / max(4, len(confs))
    g.add("M2.mail_confirmations", 5, m2, f"{len(confs)} new lodge confirmation(s); sent mails={len(sent)}")

    # ---- CSV deliverable -----------------------------------------------------
    rows = read_csv("reunion_2026.csv")
    if rows is None:
        g.add("O1.output_csv", 14, 0, "reunion_2026.csv missing")
        return
    if not rows or any(col not in rows[0] for col in CSV_COLUMNS):
        g.add("O1.output_csv", 14, 0, f"missing columns; header {list(rows[0]) if rows else []}")
        return
    conf_by_house = {}
    for b in valid:
        conf_by_house.setdefault(household_of(b.get("guestFirstName")), set()).add(str(b.get("confirmationNumber")))
    correct, notes = set(), []
    for row in rows:
        words = norm(row.get("guest_name")).split()
        key = household_of(words[0]) if words else None
        if key is None or key in correct:
            continue
        hh = HOUSEHOLDS[key]
        problems = [field for field, ok in (
            ("room", norm(row.get("room")) == norm(hh["room"])),
            ("check_in", row.get("check_in", "").strip() == hh["in"]),
            ("check_out", row.get("check_out", "").strip() == hh["out"]),
            ("total", amount_is(money(row.get("total")), hh["total"])),
            ("requested", amount_is(money(row.get("requested")), hh["requested"])),
            ("confirmation_number", row.get("confirmation_number", "").strip() in conf_by_house.get(key, set())),
        ) if not ok]
        if problems:
            notes.append(f"{key}: bad {problems}")
        else:
            correct.add(key)
    g.add("O1.output_csv", 14, len(correct) / max(4, len(rows)),
          f"{len(correct)}/4 rows right ({sorted(correct)}), {len(rows)} rows total; {notes}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
