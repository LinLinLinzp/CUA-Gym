#!/usr/bin/env python3
"""World for cua-hard/refund-queue-before-payout (Stripe + Zendesk + Yahoo Mail + local CSV).

Writes into <out>/:
  seed/{stripe_dashboard,zendesk,yahoo_mail}.json     initial state per site
  golden/{...}.json                                   state after a correct run
  golden_output/refund_queue.csv                      correct CLI deliverable
  input/returns_log.csv                               warehouse returns log (agent-visible)
  expected.json                                       hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/refund_queue.csv}

Story (lever L09, irreversible + order): Rina Takahashi runs support at Kettle & Crane
Coffee (Portland). She hands her Zendesk refund queue to an assistant. A Stripe refund
cannot be pulled back, so every refund must be right the first time. Malcolm Ferris (outside
bookkeeper) set refund rules by email on Nov 2, replacing his September rules (>$250 needs
his written OK; 15% restocking on opened change-of-mind returns; never refund a disputed
charge; refund only once the warehouse has logged the return). Several tickets must be
corrected before anyone touches the Refund button:
  4412 Hannah  - asked for the whole order, later kept the scale -> 189.00 (not 248.00)
  4409 Marco   - tamper damaged, whole order back -> 71.00 incl. shipping (he says $64)
  4415 Marco   - duplicate of 4409 (email follow-up) -> merge, no second refund
  4416 Priya   - missing bag already refunded by Theo on Nov 14 -> no refund
  4413 Derek   - "never arrived", but he opened a bank dispute -> evidence, no refund
  4405 Lucia   - >$250, Malcolm first said wait, later approved 649.00 (she asked 677.00)
  4418 Ben     - >$250, no approval yet (Oct approval is for another order) -> ask Malcolm, hold
  4420 Grace   - return still in transit per returns log -> hold, no refund
  4411 Sam     - opened, changed mind -> 189.00 * 0.85 = 160.65 (asked 189.00)
"""

import copy
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

TZ = ZoneInfo("America/Los_Angeles")
CLOCK = "2026-11-18T09:40:00-08:00"
NOW_ISO = "2026-11-18T18:10:00.000Z"          # golden action time (10:10 PST)
NOW_UNIX = int(datetime(2026, 11, 18, 10, 10, tzinfo=TZ).timestamp())

RINA = ("Rina Takahashi", "rina.kettlecrane@yahoo.com")
MALCOLM = ("Malcolm Ferris", "malcolm@ferrisbookkeeping.com")
THEO = ("Theo Marsh", "theo@kettleandcrane.com")
DANA = ("Dana Kessler", "dana@kettleandcrane.com")


def rid(prefix: str, key: str, n: int = 24) -> str:
    h = hashlib.sha256(key.encode()).hexdigest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    num = int(h, 16)
    out = ""
    for _ in range(n):
        num, r = divmod(num, len(alphabet))
        out += alphabet[r]
    return prefix + out


def unix(day: str, hm: str = "12:00") -> int:
    y, m, d = map(int, day.split("-"))
    hh, mm = map(int, hm.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=TZ).timestamp())


def iso(day: str, hm: str = "12:00") -> str:
    """Local LA wall time -> ISO UTC with Z."""
    return datetime.fromtimestamp(unix(day, hm), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_ms(day: str, hm: str = "12:00") -> str:
    return datetime.fromtimestamp(unix(day, hm), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def money(cents: int) -> str:
    return f"{cents / 100:.2f}"


# ---------------------------------------------------------------- catalog
PRODUCTS = {
    "GR-EMBER": ("Ember Conical Burr Grinder", 18900),
    "GR-EMBERPRO": ("Ember Pro Flat-Burr Grinder", 28900),
    "KT-CRANE": ("Crane Gooseneck Kettle", 12900),
    "SC-DRIP": ("Drip Scale with Timer", 5900),
    "TP-SET": ("Espresso Tamper Set", 6400),
    "ES-LISBOA": ("Lisboa Espresso Machine", 64900),
    "PT-MILK": ("Milk Frothing Pitcher", 2800),
    "DR-CERAMIC": ("Ceramic Pour-over Dripper", 2500),
    "BN-YIRGA": ("Yirgacheffe Single Origin 12oz", 2100),
    "BN-HOUSE": ("House Blend 12oz", 1800),
    "FL-PAPER": ("Paper Filters (100)", 900),
}
SHIP = 900          # standard shipping; free on item subtotal >= $200
SHIP_SMALL = 700    # small parcel


# ---------------------------------------------------------------- people
# key: (name, stripe email, zendesk email or None)
PEOPLE = {
    "hannah": ("Hannah Lowell", "hannah.lowell@gmail.com", "hannah.lowell@gmail.com"),
    "marco": ("Marco Bellini", "marco.bellini@fastmail.com", "marco.bellini@fastmail.com"),
    "priya": ("Priya Shah", "priya.shah@outlook.com", "priya.shah@outlook.com"),
    "derek": ("Derek Olsen", "derek.olsen@icloud.com", "derek.olsen@icloud.com"),
    "lucia": ("Lucia Fernandez", "lucia.fernandez@gmail.com", "lucia.fernandez@gmail.com"),
    "ben": ("Ben Arnaud", "ben.arnaud@protonmail.com", "ben.arnaud@protonmail.com"),
    "grace": ("Grace Whitaker", "gwhitaker@hey.com", "gwhitaker@hey.com"),
    "sam": ("Samuel Okoro", "sokoro@okorodesign.studio", "sam.okoro@gmail.com"),   # Stripe uses his work address
    "samokafor": ("Sam Okafor", "sam.okafor@gmail.com", None),                     # near-duplicate name in Stripe
    "nora": ("Nora Quinn", "nora.quinn@yahoo.com", "nora.quinn@yahoo.com"),
    "elena": ("Elena Marsh", "elena.marsh@gmail.com", "elena.marsh@gmail.com"),
    "kwame": ("Kwame Asante", "kwame.asante@gmail.com", "kwame.asante@gmail.com"),
    "julia": ("Julia Brandt", "jbrandt@brandtlaw.com", "jbrandt@brandtlaw.com"),
    "tomas": ("Tomas Lindgren", "tomas.lindgren@me.com", "tomas.lindgren@me.com"),
    "aiko": ("Aiko Mori", "aiko.mori@gmail.com", "aiko.mori@gmail.com"),
    "rachel": ("Rachel Dunn", "rachel.dunn@outlook.com", "rachel.dunn@outlook.com"),
    "victor": ("Victor Hale", "vhale@halecafe.com", "vhale@halecafe.com"),
    "maya": ("Maya Iqbal", "maya.iqbal@gmail.com", None),
    "owen": ("Owen Pratt", "owen.pratt@gmail.com", None),
    "lena": ("Lena Fischer", "lena.fischer@gmx.com", None),
    "chris": ("Chris Navarro", "chris.navarro@gmail.com", None),
    "dev": ("Dev Raman", "dev.raman@icloud.com", None),
    "isla": ("Isla Moreno", "isla.moreno@gmail.com", None),
    "paul": ("Paul Becker", "pbecker@beckerco.com", "pbecker@beckerco.com"),
    "zoe": ("Zoe Carter", "zoe.carter@gmail.com", None),
    "ian": ("Ian Walsh", "ian.walsh@outlook.com", None),
    "mei": ("Mei Lin", "mei.lin@gmail.com", None),
    "omar": ("Omar Haddad", "omar.haddad@gmail.com", None),
}

# ---------------------------------------------------------------- orders / charges
# key, person, order, [(sku, qty)], shipping cents, day, time
ORDERS = [
    ("o_sam_okafor", "samokafor", "KC-48226", [("GR-EMBER", 1)], SHIP, "2026-11-08", "16:22"),
    ("o_hannah", "hannah", "KC-48213", [("GR-EMBER", 1), ("SC-DRIP", 1)], 0, "2026-11-06", "19:41"),
    ("o_marco", "marco", "KC-48190", [("TP-SET", 1)], SHIP_SMALL, "2026-11-04", "10:05"),
    ("o_marco_sep", "marco", "KC-47702", [("TP-SET", 1)], SHIP_SMALL, "2026-09-22", "13:30"),
    ("o_priya", "priya", "KC-48155", [("BN-YIRGA", 2), ("PT-MILK", 1), ("DR-CERAMIC", 1)], SHIP_SMALL, "2026-11-02", "08:55"),
    ("o_derek", "derek", "KC-48177", [("GR-EMBER", 1), ("DR-CERAMIC", 1)], 0, "2026-11-03", "21:12"),
    ("o_lucia", "lucia", "KC-48122", [("ES-LISBOA", 1), ("PT-MILK", 1)], 0, "2026-11-01", "11:47"),
    ("o_ben", "ben", "KC-48204", [("GR-EMBER", 1), ("KT-CRANE", 1)], 0, "2026-11-05", "17:18"),
    ("o_ben_oct", "ben", "KC-47655", [("GR-EMBERPRO", 1)], 0, "2026-10-09", "15:02"),
    ("o_grace", "grace", "KC-48231", [("KT-CRANE", 1)], SHIP, "2026-11-09", "09:33"),
    ("o_sam", "sam", "KC-48219", [("GR-EMBER", 1)], SHIP, "2026-11-07", "12:14"),
    ("o_nora", "nora", "KC-48240", [("SC-DRIP", 1)], SHIP, "2026-11-10", "14:50"),
    # noise
    ("n01", "elena", "KC-48101", [("BN-HOUSE", 2), ("FL-PAPER", 1)], SHIP_SMALL, "2026-10-29", "08:12"),
    ("n02", "kwame", "KC-48108", [("KT-CRANE", 1), ("DR-CERAMIC", 1)], SHIP, "2026-10-30", "18:40"),
    ("n03", "julia", "KC-48113", [("ES-LISBOA", 1)], 0, "2026-10-31", "10:21"),
    ("n04", "tomas", "KC-48117", [("BN-YIRGA", 3)], SHIP_SMALL, "2026-10-31", "20:02"),
    ("n05", "aiko", "KC-48126", [("GR-EMBER", 1), ("BN-HOUSE", 1)], 0, "2026-11-01", "15:16"),
    ("n06", "rachel", "KC-48131", [("SC-DRIP", 1), ("FL-PAPER", 2)], SHIP, "2026-11-01", "19:55"),
    ("n07", "victor", "KC-48138", [("ES-LISBOA", 1), ("TP-SET", 1), ("PT-MILK", 2)], 0, "2026-11-02", "13:07"),
    ("n08", "maya", "KC-48144", [("DR-CERAMIC", 1), ("FL-PAPER", 1)], SHIP_SMALL, "2026-11-02", "16:44"),
    ("n09", "owen", "KC-48149", [("KT-CRANE", 1)], SHIP, "2026-11-02", "21:30"),
    ("n10", "lena", "KC-48160", [("BN-HOUSE", 4)], SHIP_SMALL, "2026-11-03", "09:18"),
    ("n11", "chris", "KC-48166", [("GR-EMBERPRO", 1)], 0, "2026-11-03", "12:51"),
    ("n12", "dev", "KC-48171", [("TP-SET", 1), ("BN-YIRGA", 1)], SHIP_SMALL, "2026-11-03", "18:09"),
    ("n13", "isla", "KC-48183", [("SC-DRIP", 1), ("DR-CERAMIC", 1)], SHIP, "2026-11-04", "07:40"),
    ("n14", "paul", "KC-48186", [("KT-CRANE", 2)], 0, "2026-11-04", "14:26"),
    ("n15", "zoe", "KC-48195", [("BN-YIRGA", 2)], SHIP_SMALL, "2026-11-05", "08:03"),
    ("n16", "ian", "KC-48199", [("GR-EMBER", 1), ("FL-PAPER", 1)], 0, "2026-11-05", "11:38"),
    ("n17", "mei", "KC-48208", [("PT-MILK", 1), ("BN-HOUSE", 1)], SHIP_SMALL, "2026-11-06", "10:10"),
    ("n18", "omar", "KC-48216", [("KT-CRANE", 1), ("SC-DRIP", 1)], 0, "2026-11-06", "22:47"),
    ("n19", "elena", "KC-48222", [("BN-HOUSE", 2)], SHIP_SMALL, "2026-11-08", "09:12"),
    ("n20", "kwame", "KC-48228", [("FL-PAPER", 3)], SHIP_SMALL, "2026-11-08", "18:31"),
    ("n21", "victor", "KC-48235", [("BN-YIRGA", 6), ("BN-HOUSE", 6)], 0, "2026-11-10", "08:44"),
    ("n22", "aiko", "KC-48244", [("DR-CERAMIC", 2)], SHIP_SMALL, "2026-11-11", "13:15"),
    ("n23", "tomas", "KC-48249", [("SC-DRIP", 1)], SHIP, "2026-11-12", "19:02"),
    ("n24", "rachel", "KC-48253", [("TP-SET", 1), ("PT-MILK", 1)], SHIP, "2026-11-13", "10:37"),
    ("n25", "maya", "KC-48258", [("GR-EMBER", 1)], SHIP, "2026-11-14", "15:48"),
    ("n26", "owen", "KC-48262", [("BN-YIRGA", 2), ("FL-PAPER", 1)], SHIP_SMALL, "2026-11-15", "09:29"),
    ("n27", "dev", "KC-48266", [("KT-CRANE", 1), ("DR-CERAMIC", 1)], SHIP, "2026-11-16", "12:05"),
    ("n28", "zoe", "KC-48271", [("ES-LISBOA", 1)], 0, "2026-11-17", "17:20"),
    ("n29", "paul", "KC-48090", [("GR-EMBER", 1)], SHIP, "2026-10-27", "11:11"),
    ("n30", "isla", "KC-48079", [("BN-HOUSE", 2)], SHIP_SMALL, "2026-10-25", "16:00"),
]
FAILED = [  # key, person, order, amount, day, time, reason
    ("f01", "owen", "KC-48148", 12900 + SHIP, "2026-11-02", "21:22", "insufficient_funds"),
    ("f02", "lena", "KC-48202", 64900, "2026-11-05", "13:44", "do_not_honor"),
]


def order_total(items, ship):
    return sum(PRODUCTS[s][1] * q for s, q in items) + ship


O = {o[0]: {"key": o[0], "who": o[1], "order": o[2], "items": o[3], "ship": o[4], "day": o[5], "hm": o[6],
            "amount": order_total(o[3], o[4]), "id": rid("pi_3Q", "pi" + o[0], 21)} for o in ORDERS}
FAILED_O = {f[0]: {"key": f[0], "who": f[1], "order": f[2], "amount": f[3], "day": f[4], "hm": f[5], "reason": f[6],
                   "id": rid("pi_3Q", "pi" + f[0], 21)} for f in FAILED}

# Refunds that already exist in Stripe before the task.
PRIOR_REFUNDS = [
    # key, order key, amount, day, time, reason
    ("r_priya", "o_priya", 2100, "2026-11-14", "15:26", "requested_by_customer"),   # Theo, missing bag
    ("r_ben_oct", "o_ben_oct", 28900, "2026-10-29", "10:05", "requested_by_customer"),  # approved by Malcolm Oct 28
    ("r_n29", "n29", 18900 + SHIP, "2026-11-03", "09:40", "requested_by_customer"),
    ("r_n06", "n06", 900, "2026-11-07", "11:02", "requested_by_customer"),
]

# Disputes in Stripe
DISPUTES = [
    # key, order key, reason, status, created day, due day, evidence submitted day
    ("d_derek", "o_derek", "product_not_received", "needs_response", "2026-11-15", "2026-11-25", None),
    ("d_n11", "n11", "fraudulent", "under_review", "2026-11-09", "2026-11-19", "2026-11-12"),
    ("d_n30", "n30", "unrecognized", "won", "2026-10-28", "2026-11-07", "2026-10-30"),
]

# ---------------------------------------------------------------- truth
# What each queue ticket should produce.
TRUTH = {
    4405: {"who": "lucia", "order": "KC-48122", "okey": "o_lucia", "action": "refunded", "amount": 64900},
    4409: {"who": "marco", "order": "KC-48190", "okey": "o_marco", "action": "refunded", "amount": 7100},
    4411: {"who": "sam", "order": "KC-48219", "okey": "o_sam", "action": "refunded", "amount": 16065},
    4412: {"who": "hannah", "order": "KC-48213", "okey": "o_hannah", "action": "refunded", "amount": 18900},
    4413: {"who": "derek", "order": "KC-48177", "okey": "o_derek", "action": "disputed", "amount": 0},
    4415: {"who": "marco", "order": "KC-48190", "okey": "o_marco", "action": "duplicate", "amount": 0},
    4416: {"who": "priya", "order": "KC-48155", "okey": "o_priya", "action": "already_refunded", "amount": 0},
    4418: {"who": "ben", "order": "KC-48204", "okey": "o_ben", "action": "awaiting_approval", "amount": 0},
    4420: {"who": "grace", "order": "KC-48231", "okey": "o_grace", "action": "awaiting_return", "amount": 0},
}
QUEUE = sorted(TRUTH)
GOLDEN_STATUS = {4405: "solved", 4409: "solved", 4411: "solved", 4412: "solved", 4413: "solved",
                 4415: "closed", 4416: "solved", 4418: "hold", 4420: "hold"}


# ---------------------------------------------------------------- stripe
def build_stripe():
    customers, pms = [], []
    cus = {}
    for k, (name, semail, _) in PEOPLE.items():
        mine = [o for o in O.values() if o["who"] == k]
        if not mine and k not in [f["who"] for f in FAILED_O.values()]:
            continue
        cid = rid("cus_", "cus" + k, 14)
        pm = rid("pm_1Q", "pm" + k, 21)
        brand = ["visa", "mastercard", "amex", "visa", "discover"][int(hashlib.md5(k.encode()).hexdigest()[:2], 16) % 5]
        last4 = str(1000 + int(hashlib.md5(k.encode()).hexdigest()[2:6], 16) % 9000)
        first = min(unix(o["day"], o["hm"]) for o in mine) if mine else unix("2026-10-20")
        cus[k] = {"id": cid, "pm": pm, "card": {"brand": brand, "last4": last4, "exp_month": 1 + len(k) % 12,
                                                "exp_year": 2028 + len(k) % 3, "funding": "credit"}}
        customers.append({"id": cid, "name": name, "email": semail, "phone": None, "description": None,
                          "address": {"line1": None, "line2": None, "city": "Portland", "state": "OR",
                                      "postal_code": "97214", "country": "US"},
                          "balance": 0, "currency": "usd", "default_payment_method": pm, "metadata": {},
                          "created": first - 3600, "livemode": True, "delinquent": False,
                          "total_spent": sum(o["amount"] for o in mine), "payments_count": len(mine)})
        pms.append({"id": pm, "type": "card", "card": dict(cus[k]["card"]), "billing_details": {"name": name},
                    "created": first - 3600, "customer": cid})

    refunded = {}
    for _, okey, amt, *_ in PRIOR_REFUNDS:
        refunded[okey] = refunded.get(okey, 0) + amt
    disputed = {d[1] for d in DISPUTES if d[3] in ("needs_response", "under_review")}

    def items_str(items):
        return ", ".join(f"{s} x{q}" for s, q in items)

    payments = []
    for o in O.values():
        name, semail, _ = PEOPLE[o["who"]]
        c = cus[o["who"]]
        created = unix(o["day"], o["hm"])
        amt_ref = refunded.get(o["key"], 0)
        score = 6 + created % 37
        payments.append({
            "id": o["id"], "amount": o["amount"], "currency": "usd", "status": "succeeded",
            "description": f"Order {o['order']}", "customer": c["id"], "customer_email": semail, "customer_name": name,
            "payment_method": {"type": "card", "card": dict(c["card"])},
            "amount_received": o["amount"], "amount_refunded": amt_ref, "refunded": amt_ref >= o["amount"],
            "disputed": o["key"] in disputed, "captured": True, "receipt_email": semail, "receipt_url": None,
            "metadata": {"order_id": o["order"], "items": items_str(o["items"]), "shipping": money(o["ship"])},
            "created": created, "livemode": True, "risk_score": score, "risk_level": "normal",
            "outcome": {"type": "authorized", "risk_level": "normal", "risk_score": score, "reason": None}, "invoice": None})
    for f in FAILED_O.values():
        name, semail, _ = PEOPLE[f["who"]]
        c = cus[f["who"]]
        created = unix(f["day"], f["hm"])
        payments.append({
            "id": f["id"], "amount": f["amount"], "currency": "usd", "status": "failed",
            "description": f"Order {f['order']}", "customer": c["id"], "customer_email": semail, "customer_name": name,
            "payment_method": {"type": "card", "card": dict(c["card"])}, "amount_received": 0, "amount_refunded": 0,
            "refunded": False, "disputed": False, "captured": False, "receipt_email": semail, "receipt_url": None,
            "metadata": {"order_id": f["order"]}, "created": created, "livemode": True, "risk_score": 22, "risk_level": "normal",
            "outcome": {"type": "issuer_declined", "risk_level": "normal", "risk_score": 22, "reason": f["reason"]}, "invoice": None})
    payments.sort(key=lambda p: -p["created"])

    refunds, btx, events = [], [], []
    for key, okey, amt, day, hm, reason in PRIOR_REFUNDS:
        created = unix(day, hm)
        re_id = rid("re_3Q", "re" + key, 21)
        refunds.append({"id": re_id, "amount": amt, "currency": "usd", "charge": O[okey]["id"], "reason": reason,
                        "status": "succeeded", "created": created, "metadata": {}})
        btx.append({"id": rid("txn_3Q", "tx" + key, 21), "amount": -amt, "currency": "usd", "type": "refund", "fee": 0,
                    "net": -amt, "status": "available", "available_on": created + 172800, "source": re_id,
                    "description": f"Refund for {O[okey]['id']}", "created": created})
        events.append({"id": rid("evt_3Q", "ev" + key, 21), "type": "charge.refunded", "created": created,
                       "data": {"object": {"id": O[okey]["id"]}}, "request": None, "livemode": True})
    for o in O.values():
        created = unix(o["day"], o["hm"])
        fee = round(o["amount"] * 0.029) + 30
        btx.append({"id": rid("txn_3Q", "tx" + o["key"], 21), "amount": o["amount"], "currency": "usd", "type": "charge",
                    "fee": fee, "net": o["amount"] - fee, "status": "available", "available_on": created + 172800,
                    "source": o["id"], "description": f"Order {o['order']}", "created": created})
        events.append({"id": rid("evt_3Q", "ev" + o["key"], 21), "type": "payment_intent.succeeded", "created": created,
                       "data": {"object": {"id": o["id"], "amount": o["amount"]}}, "request": None, "livemode": True})

    disputes = []
    for key, okey, reason, status, cday, dday, eday in DISPUTES:
        created = unix(cday, "07:30")
        disputes.append({"id": rid("dp_1Q", "dp" + key, 21), "amount": O[okey]["amount"], "currency": "usd",
                         "charge": O[okey]["id"], "customer": cus[O[okey]["who"]]["id"], "reason": reason, "status": status,
                         "evidence_due_by": unix(dday, "16:59"), "evidence_submitted_at": unix(eday, "14:00") if eday else None,
                         "created": created, "metadata": {"order_id": O[okey]["order"]}})
        events.append({"id": rid("evt_3Q", "ev" + key, 21), "type": "dispute.created", "created": created,
                       "data": {"object": {"id": O[okey]["id"]}}, "request": None, "livemode": True})

    payouts = []
    for i, day in enumerate(["2026-11-17", "2026-11-14", "2026-11-12", "2026-11-10", "2026-11-07", "2026-11-05", "2026-11-03", "2026-10-31"]):
        amt = 41000 + (i * 15731) % 90000
        pid = rid("po_1Q", f"po{i}", 21)
        payouts.append({"id": pid, "amount": amt, "currency": "usd", "status": "paid" if i else "in_transit",
                        "arrival_date": unix(day, "09:00"), "method": "standard", "type": "bank_account",
                        "description": "STRIPE PAYOUT", "destination": {"bank_name": "UMPQUA BANK", "last4": "3307",
                                                                        "routing_number": "123205054"},
                        "created": unix(day, "06:00") - 2 * 86400, "metadata": {}})
        btx.append({"id": rid("txn_3Q", f"txpo{i}", 21), "amount": -amt, "currency": "usd", "type": "payout", "fee": 0,
                    "net": -amt, "status": "available", "available_on": unix(day, "06:00") - 2 * 86400, "source": pid,
                    "description": "STRIPE PAYOUT", "created": unix(day, "06:00") - 2 * 86400})
    btx.sort(key=lambda t: -t["created"])
    events.sort(key=lambda e: -e["created"])

    daily = []
    for d in range(28, -1, -1):
        day = (datetime(2026, 11, 18) - timedelta(days=d)).date()
        gv = sum(o["amount"] for o in O.values() if o["day"] == day.isoformat())
        daily.append({"date": f"{day.strftime('%b')} {day.day}", "amount": gv})
    gross = sum(x["amount"] for x in daily)
    products = [{"id": "prod_" + sku.lower().replace("-", ""), "name": n, "description": n, "active": True, "images": [],
                 "default_price": "price_" + sku.lower().replace("-", ""), "metadata": {"sku": sku},
                 "created": unix("2025-06-01"), "updated": unix("2026-09-01"), "unit_label": None}
                for sku, (n, _) in PRODUCTS.items()]
    prices = [{"id": "price_" + sku.lower().replace("-", ""), "product": "prod_" + sku.lower().replace("-", ""), "active": True,
               "currency": "usd", "unit_amount": c, "billing_scheme": "per_unit", "type": "one_time", "recurring": None,
               "nickname": n, "metadata": {}, "created": unix("2025-06-01")} for sku, (n, c) in PRODUCTS.items()]
    return {
        "business": {"name": "Kettle & Crane Coffee", "email": "dana@kettleandcrane.com", "url": "https://kettleandcrane.com",
                     "support_email": "help@kettleandcrane.com", "country": "US", "currency": "usd", "timezone": "America/Los_Angeles"},
        "currentUser": {"id": "user_rina", "name": RINA[0], "email": "rina@kettleandcrane.com", "role": "support_specialist", "avatar": None},
        "balance": {"available": 1284250, "pending": 312840, "reserved": 0, "currency": "usd"},
        "customers": customers, "payments": payments, "products": products, "prices": prices, "invoices": [],
        "subscriptions": [], "payouts": payouts, "disputes": disputes, "refunds": sorted(refunds, key=lambda r: -r["created"]),
        "balanceTransactions": btx, "events": events, "paymentMethods": pms, "webhooks": [],
        "taxSettings": {"collect_automatically": False}, "testMode": False, "searchQuery": "", "selectedDateRange": "last_4_weeks",
        "metrics": {
            "today": {"grossVolume": 0, "grossVolumeChart": [{"time": f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}", "amount": 0} for h in range(24)]},
            "summary": {"grossVolume": {"amount": gross, "change": 4.1, "previousAmount": int(gross / 1.041)},
                        "netVolume": {"amount": int(gross * 0.962), "change": 3.8, "previousAmount": int(gross * 0.962 / 1.038)},
                        "disputeActivity": {"rate": 0.21, "change": 0.08, "previousRate": 0.13}},
            "chartData": {"grossVolume": daily, "netVolume": [{"date": x["date"], "amount": int(x["amount"] * 0.962)} for x in daily],
                          "disputeRate": [{"date": x["date"], "rate": 0} for x in daily]},
        },
    }


# ---------------------------------------------------------------- zendesk
AGENTS = [(1, "Rina Takahashi", "rina@kettleandcrane.com", 1, "RT"),
          (2, "Theo Marsh", "theo@kettleandcrane.com", 1, "TM"),
          (3, "Jules Abara", "jules@kettleandcrane.com", 3, "JA")]
RINA_ID, THEO_ID, JULES_ID = 1, 2, 3
ZUSERS = {k: 101 + i for i, k in enumerate(k for k, v in PEOPLE.items() if v[2])}

# label, id, who, subject, status, assignee, group, priority, channel, tags, created, convo
# convo: [(author: 'req'|agent id, day, hm, public, text)]
TICKETS = [
    (4405, "lucia", "Refund for defective Lisboa espresso machine", "open", RINA_ID, 2, "high", "web", ["refund", "return", "espresso"],
     [("req", "2026-11-12", "09:14", True,
       "Hi, the pump on my Lisboa espresso machine (order KC-48122) stopped working after a week, it just hums and nothing comes out. "
       "I'd like to send it back and get my money back for the whole order, $677. Lucia"),
      (RINA_ID, "2026-11-12", "11:02", True,
       "Hi Lucia, I'm so sorry about that. I've emailed you a prepaid return label for the machine. Once it's back with our warehouse "
       "we'll sort out the refund. Rina"),
      ("req", "2026-11-12", "12:30", True,
       "Thanks. I'll keep the milk pitcher, it's fine, just sending the machine. Dropping it at UPS tomorrow."),
      (RINA_ID, "2026-11-13", "10:20", False,
       "Over $250, asked Malcolm for the OK by email.")]),
    (4409, "marco", "Tamper set arrived bent", "open", RINA_ID, 1, "normal", "web", ["refund", "damaged"],
     [("req", "2026-11-08", "18:05", True,
       "Hello, the espresso tamper set from order KC-48190 arrived with the base bent, looks like the box was crushed. "
       "Nothing else was in the order. Can I return it for a refund?"),
      (RINA_ID, "2026-11-09", "09:40", True,
       "Hi Marco, sorry about that! Here's a prepaid label, refund goes out once it reaches our warehouse. Rina")]),
    (4411, "sam", "Return grinder - too loud", "open", RINA_ID, 1, "normal", "web", ["refund", "return"],
     [("req", "2026-11-10", "20:12", True,
       "Hi, we tried the Ember grinder (order KC-48219) for a few days but it's too loud for our apartment. "
       "I'd like to return it for a full refund of $189. Thanks, Sam"),
      (RINA_ID, "2026-11-11", "09:05", True,
       "Hi Sam, no problem, here's a return label. We'll process the refund once the grinder is back. Rina")]),
    (4412, "hannah", "Grinder broken - refund please", "open", RINA_ID, 1, "normal", "email", ["refund", "defective"],
     [("req", "2026-11-11", "07:48", True,
       "Hi, the Ember grinder from my order KC-48213 makes a grinding metal noise and the grounds are all over the place. "
       "Please refund my whole order ($248)."),
      (RINA_ID, "2026-11-11", "10:15", True,
       "Hi Hannah, sorry to hear that! I've sent you a prepaid return label. Rina"),
      ("req", "2026-11-14", "16:32", True,
       "Grinder is on its way back. Actually I'd like to keep the drip scale, it works fine and I use it every day, "
       "so please just refund the grinder.")]),
    (4413, "derek", "Order never arrived", "open", RINA_ID, 1, "high", "web", ["refund", "shipping"],
     [("req", "2026-11-15", "08:20", True,
       "My order KC-48177 never showed up. It's been almost two weeks. Please refund the $214."),
      (THEO_ID, "2026-11-16", "10:44", False,
       "UPS 1Z8V4K270356118843 shows delivered Nov 8 at 2:14pm, left at front door, delivery photo on file. "
       "Rina, handing this one to you.")]),
    (4415, "marco", "Re: tamper return KC-48190", "new", RINA_ID, 1, "normal", "email", ["refund"],
     [("req", "2026-11-16", "19:22", True,
       "Hi, following up on the bent tamper set. UPS says the return was delivered to you last week. "
       "When will I get my $64 back? Marco Bellini")]),
    (4416, "priya", "Still waiting on refund for missing coffee", "new", RINA_ID, 1, "normal", "web", ["refund"],
     [("req", "2026-11-16", "21:05", True,
       "Hi, my order KC-48155 was missing one bag of the Yirgacheffe. I still don't see the refund on my card. "
       "Can you refund the $21 please?")]),
    (4418, "ben", "Returning grinder and kettle", "open", RINA_ID, 1, "normal", "web", ["refund", "return"],
     [("req", "2026-11-12", "13:50", True,
       "Hello, I ordered the Ember grinder and the Crane kettle (KC-48204) but ended up getting a set as a gift. "
       "Both are unopened. I'd like to return them for a refund of $318."),
      (RINA_ID, "2026-11-12", "15:12", True,
       "Hi Ben, sure thing, a return label is on its way. Rina")]),
    (4420, "grace", "Kettle return - refund", "new", RINA_ID, 1, "normal", "web", ["refund", "return"],
     [("req", "2026-11-17", "08:41", True,
       "Hi! I've shipped the Crane kettle back (order KC-48231), tracking 1Z8V4K270389902217. "
       "Please refund the $129 to my card. Grace")]),
    # ---- non-targets in Rina's queue
    (4401, "kwame", "How do I descale the Crane kettle?", "open", RINA_ID, 1, "low", "web", ["how-to"],
     [("req", "2026-11-10", "17:20", True, "What's the best way to descale the Crane kettle? We have very hard water."),
      (RINA_ID, "2026-11-11", "09:30", True, "Hi Kwame! A 1:1 white vinegar and water soak for 20 minutes works well. Want our descaling guide?")]),
    (4417, "elena", "Change shipping address on KC-48222", "open", RINA_ID, 1, "normal", "email", ["shipping"],
     [("req", "2026-11-17", "07:55", True, "Can you ship KC-48222 to my office instead? 1220 SE Hawthorne Blvd, Portland OR 97214.")]),
    (4419, "victor", "Wholesale pricing for cafe", "new", RINA_ID, 3, "normal", "email", ["wholesale"],
     [("req", "2026-11-17", "11:16", True, "We run a small cafe in Salem and would like wholesale pricing on the House Blend, 20 lb a week.")]),
    (4421, "aiko", "What's your return policy?", "new", RINA_ID, 1, "low", "web", ["returns-question"],
     [("req", "2026-11-17", "14:02", True, "Thinking about the Lisboa machine as a gift. If my partner doesn't like it, can we return it, and is there a fee?")]),
    # ---- non-target refund ticket in Theo's queue
    (4414, "nora", "Refund for drip scale", "open", THEO_ID, 1, "normal", "web", ["refund", "return"],
     [("req", "2026-11-15", "10:02", True, "The drip scale (KC-48240) won't hold calibration. I'd like to return it for a refund."),
      (THEO_ID, "2026-11-15", "13:18", True, "Hi Nora, here's a prepaid label. I'll refund it as soon as it's back with us. Theo")]),
    # ---- older, solved
    (4398, "priya", "Missing bag of Yirgacheffe", "solved", THEO_ID, 1, "normal", "web", ["refund", "missing-item"],
     [("req", "2026-11-13", "18:30", True, "My order KC-48155 only had one bag of the Yirgacheffe, I paid for two."),
      (THEO_ID, "2026-11-14", "15:30", True,
       "Hi Priya, so sorry! I've refunded $21.00 for the missing bag to your card today. It can take 5-10 business days to show up. Theo")]),
    (4321, "ben", "Return Ember Pro grinder", "solved", RINA_ID, 1, "normal", "web", ["refund", "return"],
     [("req", "2026-10-15", "11:00", True, "The Ember Pro is overkill for me, returning it unopened (KC-47655)."),
      (RINA_ID, "2026-10-29", "10:10", True, "Hi Ben, Malcolm approved it and I've refunded the full $289.00. Rina")]),
    (4377, "paul", "Grinder DOA", "solved", THEO_ID, 1, "high", "email", ["refund", "defective"],
     [("req", "2026-10-30", "09:00", True, "Grinder from KC-48090 won't turn on at all."),
      (THEO_ID, "2026-11-03", "09:45", True, "Hi Paul, the warehouse confirmed the motor fault. Full refund of $198.00 issued. Theo")]),
    (4383, "rachel", "Charged for shipping twice?", "solved", THEO_ID, 2, "low", "web", ["billing"],
     [("req", "2026-11-05", "12:12", True, "My receipt for KC-48131 shows shipping but I thought it was free?"),
      (THEO_ID, "2026-11-07", "11:05", True, "Hi Rachel, free shipping starts at $200 of items, but I've refunded the $9.00 as a one-off. Theo")]),
    (4389, "tomas", "Bean Club pause for December", "pending", THEO_ID, 1, "low", "email", ["subscription"],
     [("req", "2026-11-09", "08:40", True, "We're traveling in December, can you skip that shipment?"),
      (THEO_ID, "2026-11-09", "10:00", True, "Sure! Which address should the January bag go to?")]),
    (4392, "julia", "Lisboa steam wand tips", "solved", JULES_ID, 1, "low", "web", ["how-to", "espresso"],
     [("req", "2026-11-06", "10:30", True, "Any tips for steaming oat milk on the Lisboa?"),
      (JULES_ID, "2026-11-06", "13:00", True, "Purge the wand first and keep the tip just under the surface. Barista oat milks work best!")]),
    (4403, "kwame", "Order status KC-48228", "solved", JULES_ID, 1, "low", "web", ["shipping"],
     [("req", "2026-11-09", "09:10", True, "Has KC-48228 shipped?"),
      (JULES_ID, "2026-11-09", "11:40", True, "Yes, it went out this morning with USPS, tracking is in your email.")]),
    (4407, "aiko", "Filter size for ceramic dripper", "solved", JULES_ID, 1, "low", "web", ["how-to"],
     [("req", "2026-11-12", "16:05", True, "Which paper filters fit the ceramic dripper?"),
      (JULES_ID, "2026-11-12", "17:30", True, "Our 100-pack (FL-PAPER) is the right size, or any #2 cone filter.")]),
    (4410, "tomas", "Gift card balance", "open", JULES_ID, 2, "low", "email", ["billing"],
     [("req", "2026-11-13", "12:44", True, "How do I check the balance on a gift card I got for my birthday?")]),
]


def build_zendesk():
    users = []
    for aid, name, em, grp, ini in AGENTS:
        users.append({"id": aid, "name": name, "email": em, "role": "agent", "phone": f"+1-503-555-01{aid:02d}",
                      "photo": avatar(name), "organization_id": None, "group_id": grp, "time_zone": "America/Los_Angeles",
                      "locale": "en-US", "signature": f"{name.split()[0]}\nKettle & Crane Coffee", "notes": "",
                      "suspended": False, "verified": True, "active": True, "created_at": "2024-04-01T17:00:00Z",
                      "updated_at": "2026-11-01T17:00:00Z", "last_login_at": "2026-11-18T17:30:00Z", "initials": ini})
    for k, uid in ZUSERS.items():
        name, _, zemail = PEOPLE[k]
        users.append({"id": uid, "name": name, "email": zemail, "role": "end-user", "phone": None, "photo": avatar(name),
                      "organization_id": None, "group_id": None, "time_zone": "America/Los_Angeles", "locale": "en-US",
                      "signature": "", "notes": "Cafe owner, wholesale lead" if k == "victor" else "", "suspended": False,
                      "verified": True, "active": True, "created_at": "2025-08-01T17:00:00Z", "updated_at": "2026-10-01T17:00:00Z",
                      "last_login_at": "2026-11-16T17:00:00Z", "initials": "".join(p[0] for p in name.split()[:2]).upper()})
    groups = [{"id": 1, "name": "Support", "description": "Customer support", "default": True},
              {"id": 2, "name": "Billing", "description": "Payments and refunds", "default": False},
              {"id": 3, "name": "Wholesale", "description": "Cafe and wholesale accounts", "default": False}]
    for g in groups:
        g.update({"created_at": "2024-04-01T17:00:00Z", "updated_at": "2026-06-01T17:00:00Z"})

    tickets, comments = [], {}
    cid = 700001
    for tid, who, subject, status, assignee, group, prio, channel, tags, convo in TICKETS:
        req = ZUSERS[who]
        clist = []
        for author, day, hm, public, text in convo:
            clist.append({"id": cid, "ticket_id": tid, "author_id": req if author == "req" else author, "body": text,
                          "html_body": "<p>" + text.replace("\n", "<br>") + "</p>", "public": public, "type": "Comment",
                          "attachments": [], "created_at": iso(day, hm)})
            cid += 1
        comments[str(tid)] = clist
        created, last = clist[0]["created_at"], clist[-1]["created_at"]
        agent_pub = [c for c in clist if c["author_id"] <= 3 and c["public"]]
        tickets.append({
            "id": tid, "subject": subject, "description": clist[0]["body"], "status": status,
            "type": "incident" if "refund" in tags else "question", "priority": prio, "requester_id": req, "submitter_id": req,
            "assignee_id": assignee, "group_id": group, "organization_id": None, "collaborator_ids": [], "follower_ids": [],
            "tags": list(tags), "via": {"channel": channel}, "satisfaction_rating": None, "due_at": None, "is_public": True,
            "custom_fields": [], "created_at": created, "updated_at": last, "comment_count": len(clist),
            "sla": {"first_reply_at": agent_pub[0]["created_at"] if agent_pub else None,
                    "next_reply_due": (datetime.fromisoformat(last.replace("Z", "+00:00")) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if status in ("new", "open") else None, "breached": False}})
    tickets.sort(key=lambda t: t["id"])

    def view(vid, title, all_, typ="standard", any_=()):
        return {"id": vid, "title": title, "description": title, "active": True, "position": vid - 1, "type": typ,
                "conditions": {"all": list(all_), "any": list(any_)}}
    unsolved = {"field": "status", "operator": "less_than", "value": "solved"}
    views = [
        view(1, "Your unsolved tickets", [{"field": "assignee_id", "operator": "is", "value": "current_user"}, unsolved]),
        view(2, "Unassigned tickets", [{"field": "assignee_id", "operator": "is", "value": None}, unsolved]),
        view(3, "All unsolved tickets", [unsolved]),
        view(4, "Recently updated tickets", [{"field": "updated_at", "operator": "within", "value": "7_days"}]),
        view(5, "Recently solved tickets", [{"field": "status", "operator": "is", "value": "solved"}]),
        view(6, "Pending tickets", [{"field": "status", "operator": "is", "value": "pending"}]),
        view(7, "New tickets", [{"field": "status", "operator": "is", "value": "new"}], typ="shared"),
    ]
    macros = [
        {"id": 1, "title": "Send return label", "description": "Public reply with return label, set pending", "active": True,
         "position": 0, "restriction": None,
         "actions": [{"field": "status", "value": "pending"}, {"field": "comment_mode", "value": "public"},
                     {"field": "comment_value", "value": "I've emailed you a prepaid return label. We'll process your refund once the item is back with our warehouse."}]},
        {"id": 2, "title": "Assign to me", "description": "Assign to current agent and open", "active": True, "position": 1,
         "restriction": None, "actions": [{"field": "assignee_id", "value": "current_user"}, {"field": "status", "value": "open"}]},
        {"id": 3, "title": "Transfer to Billing", "description": "Move to Billing group", "active": True, "position": 2,
         "restriction": None, "actions": [{"field": "group_id", "value": 2}, {"field": "comment_mode", "value": "internal"},
                                          {"field": "comment_value", "value": "Transferring to Billing."}]},
    ]
    tags = sorted({t for tk in tickets for t in tk["tags"]} | {"vip", "wholesale-lead"})
    current = next(u for u in users if u["id"] == RINA_ID)
    return {"currentUser": current, "users": users, "organizations": [], "groups": groups, "tickets": tickets,
            "comments": comments, "views": views, "macros": macros, "tags": tags,
            "ui": {"activeView": 1, "openTicketTabs": [], "activeTicketId": None, "searchQuery": "",
                   "selectedTicketIds": [], "replyMode": "public", "sidebarCollapsed": False}}


# ---------------------------------------------------------------- yahoo mail
def ym(mid, sender, subject, body, date, *, folder="inbox", to=None, cc=None, category="primary", read=True, conv=None,
       reply_to_id=None):
    received = folder != "sent"
    return {"id": mid, "conversationId": conv or f"cnv_{mid}", "folderId": folder, "previousFolderId": None,
            "category": category if received else None, "from": {"name": sender[0], "email": sender[1]},
            "to": [{"name": t[0], "email": t[1]} for t in (to or [RINA])], "cc": [{"name": t[0], "email": t[1]} for t in (cc or [])],
            "bcc": [], "replyTo": None, "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None,
            "date": date, "isRead": read, "isStarred": False, "isDraft": False, "status": "received" if received else "sent",
            "attachments": [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"),
            "summary": None, "orderInfo": None, "travelInfo": None, "inReplyToId": reply_to_id, "forwardedFromId": None,
            "replyType": "reply" if reply_to_id and not received else None, "repliedAt": None, "forwardedAt": None,
            "sentAt": None if received else date, "movedAt": None, "appliedFilterId": None, "createdAt": date, "updatedAt": None}


POLICY_SEP = (
    "Hi Rina,\n\nAs promised, the refund rules for the fall:\n\n"
    "- You can issue any refund up to $500 yourself, no need to check with me.\n"
    "- Opened returns where the customer simply changed their mind: refund the item less a 10% restocking fee.\n"
    "- Defective or damaged: full item price.\n"
    "- Shipping is never refunded.\n\nThanks,\nMalcolm\n\nMalcolm Ferris\nFerris Bookkeeping - for Kettle & Crane Coffee")

POLICY_NOV = (
    "Hi Rina,\n\nAfter the October chargebacks Dana and I tightened things up. These replace the September rules, "
    "effective today:\n\n"
    "1. Only refund what has physically come back: the warehouse has to have logged the return as received in the returns log first. "
    "Missing-item claims (nothing to send back) are the exception.\n"
    "2. Defective or damaged items: refund the full item price. If everything in the order came back defective or damaged, "
    "refund the shipping too.\n"
    "3. Changed-mind returns: unopened gets the full item price; opened gets the item price less a 15% restocking fee. "
    "No shipping either way.\n"
    "4. Any refund over $250 needs my OK by email before it goes out, and refund the amount I approve.\n"
    "5. If the customer has opened a dispute with their bank (Stripe > More > Disputes), do not refund that charge, "
    "it gets paid out twice if they win. Submit our evidence on the dispute instead and let the bank decide.\n\n"
    "Refunds can't be pulled back once they're issued, so if something doesn't add up, ask me first.\n\n"
    "Thanks,\nMalcolm\n\nMalcolm Ferris\nFerris Bookkeeping - for Kettle & Crane Coffee")


def build_yahoo():
    m = [
        ym("msg_001", MALCOLM, "Refund rules for the fall", POLICY_SEP, iso_ms("2026-09-08", "09:12")),
        ym("msg_002", MALCOLM, "Re: Ben Arnaud return - KC-47655",
           "Rina - fine by me, go ahead and refund Ben Arnaud the full $289.00 on KC-47655, it came back unopened. Malcolm",
           iso_ms("2026-10-28", "16:40"), conv="cnv_ben_oct"),
        ym("msg_003", MALCOLM, "Refund rules - updated from today", POLICY_NOV, iso_ms("2026-11-02", "08:30"), cc=[DANA]),
        ym("msg_004", ("Stripe", "notifications@stripe.com"), "A payment was disputed: $214.00 from Derek Olsen",
           "Derek Olsen's bank has disputed a payment of $214.00 USD (Order KC-48177). Reason: product not received. "
           "Respond by Nov 25, 2026 to contest it. View it in your Stripe Dashboard under Disputes.",
           iso_ms("2026-11-15", "07:32")),
        ym("msg_005", THEO, "Theo out Thu-Fri",
           "Hey Rina, reminder that I'm off Thursday and Friday. My queue is in decent shape, Nora's scale return is still on its way back. Theo",
           iso_ms("2026-11-17", "16:05")),
        ym("msg_006", ("Kettle & Crane Warehouse", "warehouse@kettleandcrane.com"), "Returns log export",
           "Morning! Fresh export of the returns log is saved to the support laptop as returns_log.csv. Everything that hit the dock "
           "through last night is in there with inspection notes. - Luis, Warehouse",
           iso_ms("2026-11-18", "07:15")),
        ym("msg_007", DANA, "Holiday gift guide",
           "Rina, can you send me 3-4 customer quotes about the kettle for the gift guide by Friday? Thanks! Dana",
           iso_ms("2026-11-16", "12:20")),
        ym("msg_008", ("UPS My Choice", "mcinfo@ups.com"), "Weekly shipment summary",
           "You have 14 inbound return packages this week. 3 delivered, 11 in transit.", iso_ms("2026-11-17", "05:00"),
           category="newsletters"),
        ym("msg_009", ("Barista Hustle", "news@baristahustle.com"), "Dialing in for lighter roasts",
           "This week: grind size, ratio and water temperature for light Ethiopian coffees.", iso_ms("2026-11-14", "06:00"),
           category="newsletters"),
        ym("msg_010", ("Stripe", "notifications@stripe.com"), "Your payout is on its way",
           "A payout to UMPQUA BANK ****3307 is expected to arrive Nov 19, 2026.", iso_ms("2026-11-17", "06:10")),
        ym("msg_011", ("Roastery Supply Co.", "orders@roasterysupply.com"), "Your order of 12oz kraft bags has shipped",
           "Order RS-55120: 2,000 kraft valve bags shipped via FedEx Ground.", iso_ms("2026-11-13", "13:22"), category="offers"),
        ym("msg_012", MALCOLM, "October close",
           "Rina, October is closed. Refunds were 3.1% of sales, down from 4.4% in September. Thanks for the help. Malcolm",
           iso_ms("2026-11-06", "15:50")),
        ym("msg_013", ("Shopify", "no-reply@shopify.com"), "Weekly store summary",
           "Kettle & Crane Coffee had 61 orders last week.", iso_ms("2026-11-16", "06:00"), category="newsletters"),
        # Lucia thread
        ym("msg_020", RINA, "Refund approval - Lucia Fernandez KC-48122",
           "Hi Malcolm,\n\nLucia Fernandez (ticket 4405, order KC-48122) is sending back her Lisboa espresso machine, the pump "
           "died after a week. She's asking for the whole order back, $677. OK to refund?\n\nRina",
           iso_ms("2026-11-13", "10:18"), folder="sent", to=[MALCOLM], conv="cnv_lucia"),
        ym("msg_021", MALCOLM, "Re: Refund approval - Lucia Fernandez KC-48122",
           "Not yet - let's wait until the warehouse has it in hand and has checked it. Ping me when it's logged.\n\nMalcolm",
           iso_ms("2026-11-13", "14:02"), conv="cnv_lucia", reply_to_id="msg_020"),
        ym("msg_022", RINA, "Re: Refund approval - Lucia Fernandez KC-48122",
           "Warehouse logged it on Saturday, pump failure confirmed. She's keeping the milk pitcher.\n\nRina",
           iso_ms("2026-11-17", "09:05"), folder="sent", to=[MALCOLM], conv="cnv_lucia", reply_to_id="msg_021"),
        ym("msg_023", MALCOLM, "Re: Refund approval - Lucia Fernandez KC-48122",
           "Thanks. Approved: refund $649.00 for the machine. Not the full $677 since she kept the pitcher.\n\nMalcolm",
           iso_ms("2026-11-17", "17:48"), conv="cnv_lucia", reply_to_id="msg_022", read=False),
    ]
    m.sort(key=lambda x: x["date"], reverse=True)
    fixed = "2024-01-10T10:00:00.000Z"
    folders = [{"id": fid, "name": n, "type": "system", "parentId": None, "order": i, "createdAt": fixed}
               for i, (fid, n) in enumerate([("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"),
                                             ("spam", "Spam"), ("trash", "Trash")])]
    folders.append({"id": "fld_suppliers", "name": "Suppliers", "type": "user", "parentId": None, "order": 0,
                    "createdAt": fixed, "updatedAt": None})
    people = [MALCOLM, THEO, DANA, ("Luis Vega", "warehouse@kettleandcrane.com")]
    contacts = [{"id": f"ct_{i + 1:04d}", "firstName": p[0].split()[0], "lastName": p[0].split()[-1], "nickname": "",
                 "emails": [{"type": "work", "address": p[1]}], "phones": [], "addresses": [], "company": "", "jobTitle": "",
                 "birthday": "", "website": "", "notes": "", "isFavorite": i < 2, "avatarColor": "#5B8DB8", "source": "manual",
                 "createdAt": fixed, "updatedAt": None} for i, p in enumerate(people)]
    return {
        "currentUser": {"id": "usr_rina", "name": RINA[0], "firstName": "Rina", "email": RINA[1], "aliases": [],
                        "avatarColor": "#8C5A3C", "jobTitle": "Customer Support Lead", "company": "Kettle & Crane Coffee",
                        "location": "Portland, OR", "storage": {"usedBytes": 2314398617, "totalBytes": 1099511627776}},
        "folders": folders, "messages": m, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {"appearance": {"theme": "light", "themeColor": "purple", "density": "comfortable", "messageLayout": "list"},
                     "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
                     "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
                     "writing": {"signature": {"enabled": True, "text": "Rina Takahashi\nCustomer Support Lead, Kettle & Crane Coffee"},
                                 "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": RINA[1],
                                 "sendWithCtrlEnter": True, "linkPreviews": True},
                     "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "",
                                          "onlyContacts": False, "updatedAt": None},
                     "notifications": {"browser": False, "sound": False}, "ai": {"messageSummaries": False},
                     "keyboardShortcuts": True, "rightPanel": {"open": False, "tab": "starred"},
                     "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False}},
    }


# ---------------------------------------------------------------- returns log CSV
def returns_rows():
    rows = [["rma", "order", "sku", "item", "qty", "unit_price", "reason", "status", "received_date", "inspection"]]
    data = [
        ("RMA-2291", "KC-48090", "GR-EMBER", 1, "defective", "received", "2026-11-01", "motor fault confirmed"),
        ("RMA-2297", "KC-48113", "PT-MILK", 1, "changed_mind", "received", "2026-11-04", "unopened, resaleable"),
        ("RMA-2303", "KC-48190", "TP-SET", 1, "damaged_in_transit", "received", "2026-11-13", "base bent, box crushed - confirmed"),
        ("RMA-2305", "KC-48219", "GR-EMBER", 1, "changed_mind", "received", "2026-11-14", "opened, used; no defect found"),
        ("RMA-2306", "KC-48122", "ES-LISBOA", 1, "defective", "received", "2026-11-15", "pump failure confirmed"),
        ("RMA-2308", "KC-48213", "GR-EMBER", 1, "defective", "received", "2026-11-16", "burr carrier misaligned - confirmed"),
        ("RMA-2309", "KC-48204", "GR-EMBER", 1, "changed_mind", "received", "2026-11-17", "unopened, resaleable"),
        ("RMA-2310", "KC-48204", "KT-CRANE", 1, "changed_mind", "received", "2026-11-17", "unopened, resaleable"),
        ("RMA-2311", "KC-48240", "SC-DRIP", 1, "defective", "in_transit", "", ""),
        ("RMA-2312", "KC-48231", "KT-CRANE", 1, "changed_mind", "in_transit", "", ""),
        ("RMA-2313", "KC-48186", "KT-CRANE", 1, "changed_mind", "label_created", "", ""),
    ]
    for rma, order, sku, qty, reason, status, rdate, insp in data:
        rows.append([rma, order, sku, PRODUCTS[sku][0], qty, money(PRODUCTS[sku][1]), reason, status, rdate, insp])
    return rows


# ---------------------------------------------------------------- golden mutations (mirror the mocks' reducers)
def stripe_refund(st, okey, amount, n):
    """PaymentDetail.handleRefund -> ADD_REFUND."""
    pay = next(p for p in st["payments"] if p["id"] == O[okey]["id"])
    re_id = rid("re_3Q", f"golden{okey}{n}", 14)
    ts = NOW_UNIX + n * 60
    st["refunds"].insert(0, {"id": re_id, "amount": amount, "currency": "usd", "charge": pay["id"],
                             "reason": "requested_by_customer", "status": "succeeded", "created": ts, "metadata": {}})
    pay["amount_refunded"] += amount
    pay["refunded"] = pay["amount_refunded"] >= pay["amount"]
    st["balance"]["available"] -= amount
    st["balanceTransactions"].insert(0, {"id": rid("txn_", f"golden{okey}{n}", 14), "amount": -amount, "currency": "usd",
                                         "type": "refund", "fee": 0, "net": -amount, "status": "available",
                                         "available_on": ts + 172800, "source": re_id,
                                         "description": f"Refund for {pay['id']}", "created": ts})
    st["events"].insert(0, {"id": rid("evt_", f"golden{okey}{n}", 14), "type": "charge.refunded", "created": ts,
                            "data": {"object": {"id": pay["id"]}}, "request": None, "livemode": True})


def stripe_evidence(st, dkey="d_derek"):
    d = next(x for x in st["disputes"] if x["id"] == rid("dp_1Q", "dp" + dkey, 21))
    d["status"] = "under_review"
    d["evidence_submitted_at"] = NOW_UNIX + 600


_cid = [1795000000000]


def z_comment(zd, tid, body, public=True, author=RINA_ID):
    _cid[0] += 1000
    c = {"id": _cid[0], "ticket_id": tid, "author_id": author, "body": body,
         "html_body": "<p>" + body.replace("\n", "<br>") + "</p>", "public": public, "type": "Comment",
         "attachments": [], "created_at": NOW_ISO}
    zd["comments"].setdefault(str(tid), []).append(c)
    t = next(x for x in zd["tickets"] if x["id"] == tid)
    t["comment_count"] += 1
    t["updated_at"] = NOW_ISO


def z_status(zd, tid, status):
    t = next(x for x in zd["tickets"] if x["id"] == tid)
    t["status"] = status
    t["updated_at"] = NOW_ISO


def z_reply(zd, tid, body, status):
    z_comment(zd, tid, body)
    z_status(zd, tid, status)


def z_merge(zd, source, target):
    z_comment(zd, target, f"Merged tickets #{source} into this ticket.", public=False)
    z_comment(zd, source, f"This ticket was merged into #{target}.", public=False)
    z_status(zd, source, "closed")


def y_send(yd, mid, to, subject, body):
    msg = ym(mid, RINA, subject, body, NOW_ISO, folder="sent", to=[to])
    msg.update({"isRead": True, "sentAt": NOW_ISO, "date": NOW_ISO, "updatedAt": NOW_ISO})
    yd["messages"].insert(0, msg)
    yd["activityLog"].append({"id": f"act_{mid}", "type": "message.send", "actor": RINA[1], "createdAt": NOW_ISO,
                              "messageIds": [mid], "folderIds": ["sent"], "filterIds": [], "contactIds": [], "listIds": [],
                              "details": {"to": [{"name": to[0], "email": to[1]}], "cc": [], "bcc": [], "subject": subject, "attachmentIds": [],
                                          "originalMessageId": None, "incomingCopyIds": []}})


REPLIES = {
    4405: ("Hi Lucia, the warehouse confirmed the pump failure and I've refunded $649.00 for the machine to your card. "
           "It should show up in 5-10 business days. Rina", "solved"),
    4409: ("Hi Marco, your tamper set is back with us and I've refunded the full order, $71.00 including shipping. "
           "It can take 5-10 business days to appear. Rina", "solved"),
    4411: ("Hi Sam, the grinder is back. Since it was opened and used, our 15% restocking fee applies, so I've refunded "
           "$160.65 to your card. Rina", "solved"),
    4412: ("Hi Hannah, the warehouse confirmed the fault on the grinder and I've refunded $189.00 for it. Enjoy the scale! Rina", "solved"),
    4413: ("Hi Derek, UPS shows KC-48177 delivered on Nov 8 at your front door. Because a dispute has been opened with your bank "
           "for this charge, we can't refund it separately; we've sent our delivery evidence to the bank and they will decide. Rina", "solved"),
    4416: ("Hi Priya, we already refunded the $21.00 for the missing bag on Nov 14 (see ticket 4398). Card refunds can take "
           "5-10 business days to post, so it should appear soon. Rina", "solved"),
    4418: ("Hi Ben, both items are back with us. Refunds of this size need sign-off from our finance team, so I've sent it "
           "for approval and will process it as soon as it's approved. Rina", "hold"),
    4420: ("Hi Grace, thanks for sending the kettle back. It hasn't reached our warehouse yet; we'll refund it as soon as it "
           "arrives and is logged. Rina", "hold"),
}
APPROVAL_SUBJECT = "Refund approval - Ben Arnaud KC-48204"
APPROVAL_BODY = ("Hi Malcolm,\n\nBen Arnaud (ticket 4418, order KC-48204) returned the Ember grinder and the Crane kettle, both "
                 "unopened; the warehouse logged them yesterday. Under the rules that's a full item refund of $318.00. "
                 "OK to refund?\n\nRina")
REFUNDS_GOLDEN = [("o_lucia", 64900), ("o_marco", 7100), ("o_sam", 16065), ("o_hannah", 18900)]


def apply_run(seed, *, refunds, replies, evidence=True, merge=True, approval=True, dup_reply=None):
    st, zd, yd = (copy.deepcopy(seed[k]) for k in ("stripe_dashboard", "zendesk", "yahoo_mail"))
    for n, (okey, amt) in enumerate(refunds):
        stripe_refund(st, okey, amt, n)
    if evidence:
        stripe_evidence(st)
    for tid, (body, status) in replies.items():
        z_reply(zd, tid, body, status)
    if merge:
        z_merge(zd, 4415, 4409)
    elif dup_reply:
        z_reply(zd, 4415, *dup_reply)
    if approval:
        y_send(yd, "msg_new_ben", MALCOLM, APPROVAL_SUBJECT, APPROVAL_BODY)
    return {"stripe_dashboard": st, "zendesk": zd, "yahoo_mail": yd}


def csv_rows(rows):
    return [["ticket", "order", "action", "refund_amount"]] + [[str(t), o, a, a2] for t, o, a, a2 in rows]


def golden_csv():
    return csv_rows([(t, TRUTH[t]["order"], TRUTH[t]["action"], money(TRUTH[t]["amount"])) for t in QUEUE])


def modified_csv(changes):
    rows = []
    for t in QUEUE:
        row = [t, TRUTH[t]["order"], TRUTH[t]["action"], money(TRUTH[t]["amount"])]
        if t in changes:
            row[2], row[3] = changes[t]
        rows.append(tuple(row))
    return csv_rows(rows)


# ---------------------------------------------------------------- variants
def variants(seed):
    out = {}
    out["golden"] = (apply_run(seed, refunds=REFUNDS_GOLDEN, replies=REPLIES), golden_csv())
    out["nop"] = (copy.deepcopy(seed), None)

    # naive: does what each customer literally asks, reads the September rules, no cross-checks.
    naive_refunds = [("o_lucia", 67700), ("o_marco", 6400), ("o_sam", 18900), ("o_hannah", 24800), ("o_derek", 21400),
                     ("o_marco_sep", 6400), ("o_priya", 2100), ("o_ben", 31800), ("o_grace", 12900)]
    naive_replies = {
        4405: ("Hi Lucia, I've refunded your whole order, $677.00. Rina", "solved"),
        4409: ("Hi Marco, refunded $64.00 for the tamper set. Rina", "solved"),
        4411: ("Hi Sam, refunded $189.00. Rina", "solved"),
        4412: ("Hi Hannah, I've refunded your order, $248.00. Rina", "solved"),
        4413: ("Hi Derek, sorry it never arrived, I've refunded $214.00. Rina", "solved"),
        4416: ("Hi Priya, I've issued a refund of $21.00 for the missing bag. Rina", "solved"),
        4418: ("Hi Ben, refunded $318.00 for both items. Rina", "solved"),
        4420: ("Hi Grace, I've refunded $129.00 for the kettle. Rina", "solved"),
    }
    out["naive"] = (apply_run(seed, refunds=naive_refunds, replies=naive_replies, evidence=False, merge=False, approval=False,
                              dup_reply=("Hi Marco, I've refunded $64.00. Rina", "solved")),
                    csv_rows([(4405, "KC-48122", "refunded", "677.00"), (4409, "KC-48190", "refunded", "64.00"),
                              (4411, "KC-48219", "refunded", "189.00"), (4412, "KC-48213", "refunded", "248.00"),
                              (4413, "KC-48177", "refunded", "214.00"), (4415, "KC-48190", "refunded", "64.00"),
                              (4416, "KC-48155", "refunded", "21.00"), (4418, "KC-48204", "refunded", "318.00"),
                              (4420, "KC-48231", "refunded", "129.00")]))

    # slip_approval: everything right, except Ben refunded without Malcolm's OK.
    r = dict(REPLIES)
    r[4418] = ("Hi Ben, both items are back and I've refunded $318.00 to your card. Rina", "solved")
    out["slip_approval"] = (apply_run(seed, refunds=REFUNDS_GOLDEN + [("o_ben", 31800)], replies=r, approval=False),
                            modified_csv({4418: ("refunded", "318.00")}))

    # slip_restock: misses the 15% restocking fee (or reads the September 10%) -> 189.00
    r = dict(REPLIES)
    r[4411] = ("Hi Sam, the grinder is back and I've refunded $189.00 to your card. Rina", "solved")
    out["slip_restock"] = (apply_run(seed, refunds=[x if x[0] != "o_sam" else ("o_sam", 18900) for x in REFUNDS_GOLDEN], replies=r),
                           modified_csv({4411: ("refunded", "189.00")}))

    # slip_dispute: never checks Disputes, refunds Derek.
    r = dict(REPLIES)
    r[4413] = ("Hi Derek, sorry about that, I've refunded $214.00 to your card. Rina", "solved")
    out["slip_dispute"] = (apply_run(seed, refunds=REFUNDS_GOLDEN + [("o_derek", 21400)], replies=r, evidence=False),
                           modified_csv({4413: ("refunded", "214.00")}))

    # slip_correction: misses Hannah's follow-up and refunds the whole order.
    r = dict(REPLIES)
    r[4412] = ("Hi Hannah, I've refunded your whole order, $248.00. Rina", "solved")
    out["slip_correction"] = (apply_run(seed, refunds=[x if x[0] != "o_hannah" else ("o_hannah", 24800) for x in REFUNDS_GOLDEN],
                                        replies=r), modified_csv({4412: ("refunded", "248.00")}))
    return out


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def expected():
    pay = {k: O[k]["id"] for k in O}
    return {
        "clock": CLOCK,
        "queue": QUEUE,
        "truth": {str(t): {**v, "charge": pay[v["okey"]], "amount": money(v["amount"])} for t, v in TRUTH.items()},
        "golden_status": {str(k): v for k, v in GOLDEN_STATUS.items()},
        "refund_targets": {pay[k]: money(a) for k, a in REFUNDS_GOLDEN},
        "no_refund_charges": {"priya": pay["o_priya"], "derek": pay["o_derek"], "ben": pay["o_ben"], "grace": pay["o_grace"]},
        "protected_charges": {"marco_sep": pay["o_marco_sep"], "sam_okafor": pay["o_sam_okafor"], "nora": pay["o_nora"],
                              "ben_oct": pay["o_ben_oct"]},
        "derek_dispute": rid("dp_1Q", "dpd_derek", 21),
        "malcolm": MALCOLM[1],
        "ben_approval_amount": "318.00",
        "theo_ticket": 4414,
        "non_target_rina_tickets": [4401, 4417, 4419, 4421],
        "csv_path": "/workspace/output/refund_queue.csv",
    }


def main(out: Path):
    seed = {"stripe_dashboard": build_stripe(), "zendesk": build_zendesk(), "yahoo_mail": build_yahoo()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    vs = variants(seed)
    for site, state in vs["golden"][0].items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "refund_queue.csv", golden_csv())
    write_csv(out / "input" / "returns_log.csv", returns_rows())
    write_json(out / "expected.json", expected())
    for name, (states, rows) in vs.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "refund_queue.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
