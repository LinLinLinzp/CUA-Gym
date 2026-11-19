#!/usr/bin/env python3
"""World for the stripe-payout-matching task (QuickBooks + Stripe + Gmail + local CSV).

Writes into <out>/:
  seed/{quickbooks,stripe_dashboard,gmail}.json     initial state per site
  golden/{...}.json                                 state after a correct run
  golden_output/payout_reconciliation.csv           correct CLI deliverable
  input/stripe_payouts_nov.csv                      agent-visible itemized payout export
  expected.json                                     hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/}   self-check fixtures

Story: Rosa Delgado keeps the books for Fernhill Creative, a small design studio in
Providence. Clients pay invoices by card through Stripe payment links. Stripe's
November itemized payout export lists five payouts: two Rosa already booked last week,
two that landed in the bank since, and one still in transit. Each of the 35 client
charges in the two new payouts must be matched to its QuickBooks invoice(s) and handled:
receive payment, leave open + email the balance, or refund a duplicate in Stripe.
Each payout's Stripe fees are booked as one expense.

Lever L04 (scale): 35 per-item cross-site lookups (CSV -> Stripe payment -> QuickBooks
invoice), with deposit balances, combined and split payments, duplicates, wrong
references and near-duplicate customers mixed into the routine items.
"""

import copy
import csv
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-16T09:30:00-05:00"
TODAY = "2026-11-16"
ET = timezone(timedelta(hours=-5))  # EST all of November
BOOKS = "books@fernhillcreative.com"
NADIA = "nadia@fernhillcreative.com"


def D(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def cents(x) -> int:
    return int((D(x) * 100).to_integral_value())


def unix(day: str, hm: str = "10:00") -> int:
    y, m, d = map(int, day.split("-"))
    hh, mm = map(int, hm.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=ET).timestamp())


def iso_utc(day: str, hm: str) -> str:
    return datetime.fromtimestamp(unix(day, hm), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rid(prefix: str, seed: str, n: int = 24) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    out = ""
    for _ in range(n):
        h, r = divmod(h, 62)
        out += alphabet[r]
    return f"{prefix}{out}"


# ---------------------------------------------------------------- clients
# key: (QB display name, contact, QB billing email, phone, Stripe name, Stripe email, international card)
CLIENTS = {
    "ferro": ("Ferro Architects", "Lena Ferro", "admin@ferroarch.com", "(401) 555-0142", "Ferro Architects", "admin@ferroarch.com", False),
    "copperline": ("Copperline Coffee", "Sam Whitaker", "hello@copperline.coffee", "(401) 555-0187", "Copperline Coffee", "hello@copperline.coffee", False),
    "pinecrest": ("Pinecrest Montessori", "Joan Abernathy", "office@pinecrestmontessori.org", "(401) 555-0119", "Pinecrest Montessori School", "office@pinecrestmontessori.org", False),
    "velvet": ("Velvet Hour Bar", "Andre Lyle", "mgr@velvethourbar.com", "(401) 555-0163", "Velvet Hour", "mgr@velvethourbar.com", False),
    "kestrel": ("Kestrel Analytics", "Priya Raman", "ap@kestrelanalytics.io", "(617) 555-0130", "Kestrel Analytics Inc.", "ap@kestrelanalytics.io", False),
    "morrow": ("Morrow Botanicals", "Ivy Morrow", "shop@morrowbotanicals.com", "(401) 555-0171", "Morrow Botanicals", "shop@morrowbotanicals.com", False),
    "juniper": ("Juniper Health Clinic", "Dana Reyes", "billing@juniperhealth.org", "(401) 555-0105", "Juniper Health", "billing@juniperhealth.org", False),
    "greywell": ("Greywell Partners", "Martin Greywell", "ap@greywell.partners", "(617) 555-0158", "Greywell Partners LLP", "ap@greywell.partners", False),
    "atlas": ("Atlas Climbing Gym", "Kofi Mensah", "frontdesk@atlasclimbing.com", "(401) 555-0194", "Atlas Climbing", "frontdesk@atlasclimbing.com", False),
    "larkspur": ("Larkspur Wealth", "Helen Cho", "ops@larkspurwealth.com", "(617) 555-0122", "Larkspur Wealth Management", "ops@larkspurwealth.com", False),
    "northgate": ("Northgate Dental", "Dr. Ben Alvarez", "office@northgatedental.com", "(401) 555-0136", "Northgate Dental Group", "office@northgatedental.com", False),
    "hollis": ("Hollis Street Theatre", "Grace Okoye", "box@hollisstreet.org", "(401) 555-0148", "Hollis Street Theatre", "box@hollisstreet.org", False),
    "oakhaven": ("Oakhaven Veterinary", "Tom Reilly", "admin@oakhavenvets.com", "(401) 555-0177", "Oakhaven Vets", "admin@oakhavenvets.com", False),
    "sable": ("Sable & Stone Jewelry", "Mira Sato", "studio@sableandstone.com", "(212) 555-0109", "Sable & Stone", "studio@sableandstone.com", False),
    "bramble": ("Bramble & Rye Bakery", "Owen Pike", "orders@brambleandrye.com", "(401) 555-0115", "Bramble & Rye", "orders@brambleandrye.com", False),
    "saltmarsh": ("Saltmarsh Films", "Jade Moreau", "hello@saltmarshfilms.co", "(401) 555-0128", "Saltmarsh Films", "hello@saltmarshfilms.co", False),
    "ridgeline": ("Ridgeline Outdoor Guides", "Cal Brennan", "book@ridgelineguides.com", "(802) 555-0140", "Ridgeline Guides", "book@ridgelineguides.com", False),
    "nordvik": ("Nordvik Furniture AS", "Erik Nordvik", "post@nordvik.no", "+47 22 55 01 33", "Nordvik Furniture", "post@nordvik.no", True),
    "tidewater": ("Tidewater Brewing Co.", "Rachel Kim", "ap@tidewaterbrewing.com", "(401) 555-0182", "Tidewater Brewing", "ap@tidewaterbrewing.com", False),
    "ember": ("Ember Kitchen", "Luis Ortega", "luis@emberkitchen.com", "(401) 555-0191", "Ember Kitchen", "luis@emberkitchen.com", False),
    "lumen": ("Lumen Solar Co-op", "Ada Brooks", "billing@lumensolar.coop", "(401) 555-0153", "Lumen Solar Co-op", "billing@lumensolar.coop", False),
    "brightwater": ("Brightwater Yoga", "Nina Hart", "studio@brightwateryoga.com", "(401) 555-0166", "Brightwater Yoga", "studio@brightwateryoga.com", False),
    "marlowe": ("Marlowe Finch Design", "Theo Marlowe", "hello@marlowefinch.com", "(617) 555-0174", "Marlowe Finch", "hello@marlowefinch.com", False),
    "marlowlaw": ("Marlow & Finch Legal", "Ruth Marlow", "billing@marlowandfinch.law", "(617) 555-0111", "Marlow & Finch LLP", "billing@marlowandfinch.law", False),
    "quillon": ("Quillon Press", "Felix Quill", "accounts@quillonpress.com", "(401) 555-0189", "Quillon Press", "accounts@quillonpress.com", False),
    "calder": ("Calder Bikes", "Tomas Calder", "tomas@calderbikes.com", "(401) 555-0102", "Calder Bikes", "tomas@calderbikes.com", False),
    "harborpine": ("Harbor & Pine Realty", "Marta Ostrowski", "accounts@harborpine.com", "(401) 555-0134", "Marta Ostrowski", "m.ostrowski@gmail.com", False),
    "wren": ("Wren Outfitters", "Jonah Wren", "finance@wrenoutfitters.com", "(603) 555-0160", "Wren Outfitters", "finance@wrenoutfitters.com", False),
    "odessa": ("Odessa Park Ceramics", "Odessa Park", "odessa@odessaparkceramics.com", "(401) 555-0198", "Odessa Park", "odessa.park@gmail.com", False),
    "sunbeam": ("Sunbeam Daycare", "Carla Diaz", "director@sunbeamdaycare.org", "(401) 555-0125", "Sunbeam Daycare", "director@sunbeamdaycare.org", False),
}
CUST_ID = {k: f"c_{k}" for k in CLIENTS}

PRODUCTS = {
    "brand": ("Brand identity design", 0),
    "web": ("Website design & build", 0),
    "ret": ("Monthly design retainer", 0),
    "photo": ("Photography day", 1450),
    "pack": ("Packaging design", 0),
    "print": ("Print collateral design", 0),
    "copy": ("Copywriting", 95),
    "social": ("Social media kit", 0),
    "courier": ("Rush courier & proofs", 0),
    "sign": ("Signage & wayfinding", 0),
    "motion": ("Motion graphics", 0),
}
PROD_ID = {k: f"p_{k}" for k in PRODUCTS}

# ---------------------------------------------------------------- invoices
# number, client, date, terms(days), [(product, description, amount)], state
# state: ("paid", paid_date) | ("partial", deposit_amount, deposit_date) | ("open",) | ("draft",)
INVOICES = [
    (1150, "ferro", "2026-09-14", 30, [("brand", "Brand identity - phase 1", 4200)], ("paid", "2026-10-09")),
    (1151, "copperline", "2026-09-18", 15, [("social", "Social media kit - fall", 1350)], ("paid", "2026-10-05")),
    (1152, "pinecrest", "2026-09-22", 30, [("print", "Enrollment brochure", 2800)], ("paid", "2026-10-12")),
    (1153, "velvet", "2026-09-25", 15, [("sign", "Window decals", 720)], ("paid", "2026-10-08")),
    (1154, "kestrel", "2026-10-01", 30, [("web", "Marketing site redesign", 7200)], ("partial", 3600, "2026-10-09")),
    (1155, "morrow", "2026-10-02", 30, [("pack", "Seed packet packaging", 1640)], ("paid", "2026-10-19")),
    (1156, "juniper", "2026-10-05", 15, [("ret", "Design retainer - October", 1450)], ("paid", "2026-10-14")),
    (1157, "greywell", "2026-10-06", 30, [("brand", "Rebrand - strategy & identity", 9500)], ("partial", 3000, "2026-10-13")),
    (1158, "atlas", "2026-10-07", 30, [("web", "Website refresh", 2400)], ("paid", "2026-10-21")),
    (1159, "larkspur", "2026-10-08", 30, [("print", "Annual report layout", 5500)], ("paid", "2026-10-30")),
    (1160, "northgate", "2026-10-09", 30, [("brand", "Practice rebrand", 4800)], ("partial", 2400, "2026-10-16")),
    (1161, "hollis", "2026-10-12", 30, [("print", "Season poster series", 1280)], ("open",)),
    (1162, "oakhaven", "2026-10-13", 15, [("print", "Clinic rack cards", 860)], ("paid", "2026-10-27")),
    (1163, "sable", "2026-10-14", 15, [("photo", "Product photography", 1450), ("copy", "Product copy (4.7 hrs)", 450)], ("paid", "2026-10-28")),
    (1164, "bramble", "2026-10-15", 15, [("pack", "Bread bag packaging", 2150)], ("paid", "2026-11-03")),
    (1165, "saltmarsh", "2026-10-16", 15, [("motion", "Title sequence", 3600)], ("paid", "2026-11-03")),
    (1166, "ridgeline", "2026-10-19", 15, [("web", "Booking site build", 2950)], ("paid", "2026-11-03")),
    (1167, "nordvik", "2026-10-20", 15, [("photo", "Showroom photography", 2400)], ("paid", "2026-11-03")),
    (1168, "pinecrest", "2026-10-21", 15, [("social", "Open house social kit", 980)], ("paid", "2026-11-06")),
    (1169, "copperline", "2026-10-22", 15, [("pack", "Holiday blend labels", 1750)], ("paid", "2026-11-06")),
    (1170, "tidewater", "2026-10-23", 15, [("pack", "Seasonal can wraps", 3250)], ("paid", "2026-11-06")),
    (1171, "morrow", "2026-10-26", 15, [("print", "Workshop flyers", 640)], ("paid", "2026-11-06")),
    (1172, "velvet", "2026-10-27", 15, [("print", "Cocktail menu redesign", 1180)], ("paid", "2026-11-06")),
    (1173, "ember", "2026-10-27", 15, [("brand", "Logo refresh", 2050)], ("paid", "2026-11-06")),
    (1174, "bramble", "2026-10-28", 15, [("copy", "Website copy (13 hrs)", 1240)], ("open",)),
    (1175, "ferro", "2026-10-28", 30, [("brand", "Brand identity - phase 2", 5600)], ("open",)),
    (1176, "tidewater", "2026-10-29", 15, [("pack", "IPA label series (revised)", 2500), ("pack", "Extra revision round", 250)], ("open",)),
    (1177, "pinecrest", "2026-10-29", 15, [("print", "Annual fund appeal", 1980)], ("open",)),
    (1178, "saltmarsh", "2026-10-30", 15, [("photo", "Festival stills", 2200)], ("open",)),
    (1179, "lumen", "2026-10-30", 15, [("web", "Member portal landing page", 1860)], ("open",)),
    (1180, "brightwater", "2026-11-02", 15, [("social", "Winter class social kit", 890)], ("open",)),
    (1181, "copperline", "2026-11-02", 15, [("ret", "Design retainer - November", 1100)], ("open",)),
    (1182, "saltmarsh", "2026-11-02", 15, [("motion", "Trailer edit & motion", 2100)], ("open",)),
    (1183, "marlowe", "2026-11-02", 15, [("ret", "Website retainer - November", 1800)], ("open",)),
    (1184, "marlowlaw", "2026-11-02", 30, [("print", "Pitch deck redesign", 1800)], ("open",)),
    (1185, "velvet", "2026-11-03", 15, [("print", "Late-night menu", 640)], ("open",)),
    (1186, "hollis", "2026-11-03", 15, [("print", "Gala program", 1520)], ("open",)),
    (1187, "oakhaven", "2026-11-03", 30, [("sign", "Exterior signage", 3400)], ("open",)),
    (1188, "sable", "2026-11-03", 15, [("print", "Holiday lookbook", 2600)], ("open",)),
    (1189, "morrow", "2026-11-04", 15, [("photo", "Greenhouse shoot", 1450), ("courier", "Prop delivery", 75)], ("open",)),
    (1190, "nordvik", "2026-11-04", 15, [("web", "US storefront design", 4950)], ("open",)),
    (1191, "quillon", "2026-11-04", 15, [("print", "Book cover - The Low Tide", 3150)], ("open",)),
    (1192, "juniper", "2026-11-04", 30, [("print", "Patient brochure set", 2900)], ("open",)),
    (1193, "atlas", "2026-11-05", 15, [("social", "November campaign kit", 1975)], ("open",)),
    (1194, "calder", "2026-11-05", 15, [("web", "Product page templates", 1300), ("courier", "Rush courier & proofs", 85)], ("open",)),
    (1195, "harborpine", "2026-11-05", 15, [("print", "Listing kit", 1180), ("courier", "Rush courier & proofs", 240)], ("open",)),
    (1196, "wren", "2026-11-05", 15, [("pack", "Hang tags & packaging", 2640)], ("open",)),
    (1197, "juniper", "2026-11-06", 15, [("ret", "Design retainer - November", 1450)], ("open",)),
    (1198, "quillon", "2026-11-06", 15, [("ret", "Design retainer - November", 1200)], ("open",)),
    (1199, "odessa", "2026-11-06", 15, [("print", "Wholesale catalog", 640)], ("open",)),
    (1200, "odessa", "2026-11-06", 15, [("photo", "Product photography", 1150)], ("open",)),
    (1201, "greywell", "2026-11-09", 15, [("print", "Investor deck", 2250)], ("open",)),
    (1202, "ferro", "2026-11-09", 30, [("sign", "Site hoarding graphics", 1780)], ("open",)),
    (1203, "bramble", "2026-11-09", 15, [("social", "Holiday social kit", 760)], ("open",)),
    (1204, "pinecrest", "2026-11-09", 15, [("ret", "Design retainer - November", 1150)], ("open",)),
    (1205, "copperline", "2026-11-10", 15, [("pack", "Cold brew can design", 2480)], ("open",)),
    (1206, "sable", "2026-11-10", 15, [("photo", "Half-day product shoot", 980)], ("open",)),
    (1207, "hollis", "2026-11-10", 15, [("print", "Spring season poster", 1640)], ("open",)),
    (1208, "oakhaven", "2026-11-10", 30, [("web", "Online booking pages", 3875)], ("open",)),
    (1209, "ridgeline", "2026-11-10", 15, [("photo", "Trip photography", 1250)], ("open",)),
    (1210, "sunbeam", "2026-11-10", 15, [("sign", "Classroom signage", 980)], ("open",)),
    (1211, "ember", "2026-11-11", 15, [("print", "Menu & table cards", 2300)], ("open",)),
    (1212, "larkspur", "2026-11-11", 30, [("print", "Quarterly client letter", 3400)], ("open",)),
    (1213, "hollis", "2026-11-12", 15, [("print", "Donor wall program", 1320)], ("open",)),
    (1214, "velvet", "2026-11-12", 15, [("print", "NYE event posters", 1560)], ("open",)),
    (1215, "tidewater", "2026-11-13", 15, [("pack", "Tap handle decals", 890)], ("open",)),
    (1216, "kestrel", "2026-11-13", 30, [("web", "Dashboard UI concepts", 4400)], ("draft",)),
]
INV = {n: dict(number=n, client=c, date=d, terms=t, lines=l, state=s) for n, c, d, t, l, s in INVOICES}
for v in INV.values():
    v["total"] = D(sum(a for _, _, a in v["lines"]))

# ---------------------------------------------------------------- stripe charges
# key, client, day, time, amount, description, metadata, payout group
# groups: oct (older payouts), p0, pA (booked last week), pB, pC (to reconcile), pD (in transit), pend (not paid out)
CHARGES = [
    # October history (paid out in October)
    ("o1151", "copperline", "2026-10-02", "11:20", 1350, "Invoice 1151", {}, "oct"),
    ("o1153", "velvet", "2026-10-05", "15:02", 720, "Fernhill Creative - Invoice #1153", {}, "oct"),
    ("o1154", "kestrel", "2026-10-06", "09:41", 3600, "Deposit - Invoice 1154 (50%)", {"invoice_number": "1154"}, "oct"),
    ("o1152", "pinecrest", "2026-10-08", "13:15", 2800, "INV 1152", {}, "oct"),
    ("o1157", "greywell", "2026-10-09", "16:30", 3000, "Rebrand deposit - Invoice 1157", {"invoice_number": "1157"}, "oct"),
    ("o1156", "juniper", "2026-10-12", "10:05", 1450, "Invoice 1156", {}, "oct"),
    ("o1160", "northgate", "2026-10-13", "12:48", 2400, "Invoice 1160 deposit", {"invoice_number": "1160"}, "oct"),
    ("o1155", "morrow", "2026-10-15", "14:22", 1640, "Invoice 1155", {}, "oct"),
    ("o1158", "atlas", "2026-10-19", "09:12", 2400, "Invoice 1158", {}, "oct"),
    ("o1162", "oakhaven", "2026-10-23", "11:37", 860, "Invoice #1162", {}, "oct"),
    ("o1163", "sable", "2026-10-24", "17:55", 1900, "Invoice 1163", {}, "oct"),
    # po_0 (arrived Nov 3) - booked last week
    ("a1164", "bramble", "2026-10-28", "10:14", 2150, "Invoice 1164", {}, "p0"),
    ("a1165", "saltmarsh", "2026-10-29", "15:40", 3600, "Saltmarsh - title sequence inv 1165", {}, "p0"),
    ("a1166", "ridgeline", "2026-10-30", "09:03", 2950, "Invoice 1166", {}, "p0"),
    ("a1167", "nordvik", "2026-10-31", "04:26", 2400, "Faktura 1167", {}, "p0"),
    # po_A (arrived Nov 6) - booked last week
    ("a1168", "pinecrest", "2026-11-01", "19:10", 980, "Invoice 1168", {}, "pA"),
    ("a1169", "copperline", "2026-11-02", "08:44", 1750, "Invoice #1169", {}, "pA"),
    ("a1170", "tidewater", "2026-11-02", "13:29", 3250, "Tidewater - Invoice 1170", {}, "pA"),
    ("a1171", "morrow", "2026-11-02", "16:02", 640, "Invoice 1171", {}, "pA"),
    ("a1172", "velvet", "2026-11-03", "11:51", 1180, "INV-1172", {}, "pA"),
    ("a1173", "ember", "2026-11-03", "14:18", 2050, "Invoice 1173", {}, "pA"),
    # po_B (arrived Nov 10) - to reconcile
    ("b1174", "bramble", "2026-11-04", "09:22", 1240, "Invoice 1174", {}, "pB"),
    ("b1154", "kestrel", "2026-11-04", "10:47", 3600, "Invoice 1154 - balance", {"invoice_number": "1154"}, "pB"),
    ("b1175", "ferro", "2026-11-04", "14:05", 5600, "Fernhill Creative - Invoice #1175", {}, "pB"),
    ("b1176", "tidewater", "2026-11-04", "16:33", 2500, "Invoice 1176", {}, "pB"),
    ("b1177", "pinecrest", "2026-11-05", "08:58", 1980, "INV 1177", {}, "pB"),
    ("b1180a", "brightwater", "2026-11-05", "12:10", 890, "Invoice 1180", {}, "pB"),
    ("b1180b", "brightwater", "2026-11-05", "12:13", 890, "Invoice 1180", {}, "pB"),
    ("b1179a", "lumen", "2026-11-05", "15:26", 1000, "Invoice 1179", {}, "pB"),
    ("b1179b", "lumen", "2026-11-05", "15:31", 860, "Invoice 1179", {}, "pB"),
    ("b1185", "velvet", "2026-11-05", "22:40", 640, "Invoice 1185", {}, "pB"),
    ("b1178", "saltmarsh", "2026-11-06", "09:15", 4300, "Invoices 1178 & 1182", {"invoice_numbers": "1178,1182"}, "pB"),
    ("b1183", "marlowe", "2026-11-06", "11:02", 1800, "Website retainer - November", {}, "pB"),
    ("b1186", "hollis", "2026-11-06", "13:44", 1520, "Gala program invoice 1186", {}, "pB"),
    ("b1187", "oakhaven", "2026-11-06", "16:20", 3400, "Invoice #1187", {}, "pB"),
    ("b1188", "sable", "2026-11-07", "10:31", 2600, "Invoice 1188", {}, "pB"),
    ("b1189", "morrow", "2026-11-07", "12:09", 1525, "Invoice 1189", {}, "pB"),
    ("b1190", "nordvik", "2026-11-07", "05:48", 4950, "Faktura 1190", {}, "pB"),
    # po_C (arrived Nov 13) - to reconcile
    ("c1201", "greywell", "2026-11-08", "18:22", 2250, "Invoice 1201", {}, "pC"),
    ("c1157", "greywell", "2026-11-08", "18:26", 6500, "Invoice 1157 - remaining balance", {"invoice_number": "1157"}, "pC"),
    ("c1194", "calder", "2026-11-09", "08:37", 1300, "Invoice 1194", {}, "pC"),
    ("c1192", "juniper", "2026-11-09", "09:54", 1450, "Inv 1192", {}, "pC"),
    ("c1160", "northgate", "2026-11-09", "11:16", 2400, "Invoice 1160", {"invoice_number": "1160"}, "pC"),
    ("c1191", "quillon", "2026-11-09", "13:03", 4350, "Invoice 1191 + November retainer", {"invoice_numbers": "1191,1198"}, "pC"),
    ("c1158", "atlas", "2026-11-09", "15:47", 1975, "Invoice 1158", {}, "pC"),
    ("c1195", "harborpine", "2026-11-09", "17:12", 1180, "Listing kit invoice", {"invoice_number": "1195"}, "pC"),
    ("c1202", "ferro", "2026-11-09", "17:40", 1780, "Invoice #1202", {}, "pC"),
    ("c1196a", "wren", "2026-11-10", "10:02", 2640, "Invoice 1196", {}, "pC"),
    ("c1196b", "wren", "2026-11-10", "10:04", 2640, "Invoice 1196", {}, "pC"),
    ("c1203", "bramble", "2026-11-10", "10:39", 760, "Invoice 1203", {}, "pC"),
    ("c1200", "odessa", "2026-11-10", "11:25", 1150, "Thanks Fernhill!", {}, "pC"),
    ("c1204", "pinecrest", "2026-11-10", "12:18", 1150, "INV 1204", {}, "pC"),
    ("c1205", "copperline", "2026-11-10", "13:51", 2480, "Invoice 1205", {}, "pC"),
    ("c1206", "sable", "2026-11-10", "14:36", 980, "Invoice 1206", {}, "pC"),
    ("c1207", "hollis", "2026-11-10", "15:58", 1640, "Spring poster - Invoice 1207", {}, "pC"),
    ("c1208", "oakhaven", "2026-11-10", "16:45", 3875, "Invoice 1208", {}, "pC"),
    # po_D (arrival Nov 16, still in transit)
    ("d1181", "copperline", "2026-11-11", "09:30", 1100, "Invoice 1181", {}, "pD"),
    ("d1209", "ridgeline", "2026-11-11", "14:12", 1250, "Invoice 1209", {}, "pD"),
    ("d1210", "sunbeam", "2026-11-12", "10:48", 980, "Invoice 1210", {}, "pD"),
    ("d1211", "ember", "2026-11-12", "13:20", 2300, "Invoice 1211", {}, "pD"),
    ("d1212", "larkspur", "2026-11-13", "11:05", 3400, "Invoice #1212", {}, "pD"),
    # after the last payout cutoff (pending balance)
    ("e1214", "velvet", "2026-11-14", "21:17", 1560, "Invoice 1214", {}, "pend"),
]
FAILED = [("f1213", "hollis", "2026-11-12", "16:02", 1320, "Invoice 1213", "card_declined")]

# Truth per charge in the two payouts to reconcile.
# action: paid | short | refunded | already_refunded
TRUTH = {
    "b1174": ([1174], "paid"), "b1154": ([1154], "paid"), "b1175": ([1175], "paid"), "b1176": ([1176], "short"),
    "b1177": ([1177], "paid"), "b1180a": ([1180], "paid"), "b1180b": ([1180], "already_refunded"),
    "b1179a": ([1179], "paid"), "b1179b": ([1179], "paid"), "b1185": ([1185], "paid"),
    "b1178": ([1178, 1182], "paid"), "b1183": ([1183], "paid"), "b1186": ([1186], "paid"), "b1187": ([1187], "paid"),
    "b1188": ([1188], "paid"), "b1189": ([1189], "paid"), "b1190": ([1190], "paid"),
    "c1201": ([1201], "paid"), "c1157": ([1157], "paid"), "c1194": ([1194], "paid"), "c1192": ([1197], "paid"),
    "c1160": ([1160], "paid"), "c1191": ([1191, 1198], "paid"), "c1158": ([1193], "paid"), "c1195": ([1195], "short"),
    "c1202": ([1202], "paid"), "c1196a": ([1196], "paid"), "c1196b": ([1196], "refunded"), "c1203": ([1203], "paid"),
    "c1200": ([1200], "paid"), "c1204": ([1204], "paid"), "c1205": ([1205], "paid"), "c1206": ([1206], "paid"),
    "c1207": ([1207], "paid"), "c1208": ([1208], "paid"),
}
ITEM_KIND = {
    "b1154": "deposit_balance", "c1157": "deposit_balance", "c1160": "deposit_balance",
    "b1178": "combined", "c1191": "combined", "b1179a": "split", "b1179b": "split",
    "b1176": "short", "c1195": "short", "c1194": "waived", "c1192": "corrected_ref", "c1158": "wrong_ref",
    "b1183": "no_ref_near_duplicate", "c1200": "no_ref", "b1180a": "duplicate_original", "b1180b": "duplicate_already_refunded",
    "c1196a": "duplicate_original", "c1196b": "duplicate_to_refund",
}
SHORT = {  # invoice -> (QB billing email, amount still owed)
    1176: ("ap@tidewaterbrewing.com", D(250)),
    1195: ("accounts@harborpine.com", D(240)),
}
PAID_INVOICES = sorted({n for key, (invs, act) in TRUTH.items() if act == "paid" for n in invs})
OPEN_TARGET_SHORT = sorted(SHORT)
IN_TRANSIT_INVOICES = [1181, 1209, 1210, 1211, 1212]
PENDING_INVOICES = [1214]
DECOY_OPEN = [1184, 1192, 1199, 1161, 1213, 1215]

PAYOUTS = {  # key: (arrival day, status, payout id seed)
    "p0": ("2026-11-03", "paid"), "pA": ("2026-11-06", "paid"), "pB": ("2026-11-10", "paid"),
    "pC": ("2026-11-13", "paid"), "pD": ("2026-11-16", "in_transit"),
}
OCT_PAYOUT_DAYS = ["2026-10-06", "2026-10-09", "2026-10-13", "2026-10-16", "2026-10-20", "2026-10-23", "2026-10-27", "2026-10-30"]
BANK = {"bank_name": "CITIZENS BANK", "last4": "6612", "routing_number": "***0019"}


def fee_for(client: str, amount) -> Decimal:
    rate = Decimal("0.044") if CLIENTS[client][6] else Decimal("0.029")
    return D(D(amount) * rate + Decimal("0.30"))


def pid(key: str) -> str:
    return rid("pi_3Q", "pi" + key, 21)


def payout_id(key: str) -> str:
    return rid("po_1Q", "po" + key, 21)


# ---------------------------------------------------------------- ledger
def build_ledger():
    """Balance transactions, refunds and payouts (Decimal dollars)."""
    charges = []
    for key, client, day, hm, amount, desc, meta, group in CHARGES:
        charges.append(dict(key=key, client=client, day=day, hm=hm, amount=D(amount), desc=desc, meta=meta,
                            group=group, id=pid(key), fee=fee_for(client, amount), created=unix(day, hm)))
    by_key = {c["key"]: c for c in charges}
    # Brightwater duplicate refunded by Nadia on Nov 6 (falls into po_B)
    refunds = [dict(key="r1180b", id=rid("re_3Q", "re1180b", 21), charge=by_key["b1180b"], amount=D(890),
                    created=unix("2026-11-06", "08:12"), group="pB", reason="duplicate")]
    payouts = {}
    for gkey, (day, status) in PAYOUTS.items():
        payouts[gkey] = dict(key=gkey, id=payout_id(gkey), arrival=day, status=status)
    for i, day in enumerate(OCT_PAYOUT_DAYS):
        payouts[f"oct{i}"] = dict(key=f"oct{i}", id=payout_id(f"oct{i}"), arrival=day, status="paid")
    # assign October charges to October payouts (charge day <= arrival - 3 days)
    for c in charges:
        if c["group"] == "oct":
            cd = date.fromisoformat(c["day"])
            for i, day in enumerate(OCT_PAYOUT_DAYS):
                if cd <= date.fromisoformat(day) - timedelta(days=3):
                    c["group"] = f"oct{i}"
                    break
    for key in [k for k in payouts if k.startswith("oct") and not any(c["group"] == k for c in charges)]:
        del payouts[key]
    for p in payouts.values():
        items = [c for c in charges if c["group"] == p["key"]]
        refs = [r for r in refunds if r["group"] == p["key"]]
        p["charges"] = items
        p["refunds"] = refs
        p["fees"] = D(sum(c["fee"] for c in items))
        p["amount"] = D(sum(c["amount"] - c["fee"] for c in items) - sum(r["amount"] for r in refs))
    return charges, by_key, refunds, payouts


CHARGES_L, BY_KEY, REFUNDS, PAYOUT_L = build_ledger()


# ---------------------------------------------------------------- quickbooks
def due(inv) -> str:
    return (date.fromisoformat(inv["date"]) + timedelta(days=inv["terms"])).isoformat()


def qb_invoice(inv):
    items = [{"id": f"li_{inv['number']}_{i}", "productId": PROD_ID[p], "description": desc, "qty": 1,
              "rate": float(D(a)), "amount": float(D(a))} for i, (p, desc, a) in enumerate(inv["lines"], 1)]
    total = float(inv["total"])
    st = inv["state"]
    status, paid, paid_date = "Sent", 0.0, None
    if st[0] == "paid":
        status, paid, paid_date = "Paid", total, st[1]
    elif st[0] == "partial":
        status, paid, paid_date = "Partial", float(D(st[1])), st[2]
    elif st[0] == "draft":
        status = "Draft"
    elif due(inv) < TODAY:
        status = "Overdue"
    return {
        "id": f"inv_{inv['number']}", "number": str(inv["number"]), "customerId": CUST_ID[inv["client"]],
        "date": inv["date"], "dueDate": due(inv), "items": items, "subtotal": total, "tax": 0, "total": total,
        "status": status, "paidAmount": paid, "paidDate": paid_date, "terms": f"Net {inv['terms']}",
        "message": "Thank you for working with Fernhill Creative. Pay by card at fernhillcreative.com/pay or by check.",
        "createdAt": f"{inv['date']}T15:00:00.000Z",
    }


def build_quickbooks():
    invoices = [qb_invoice(INV[n]) for n in sorted(INV, reverse=True)]
    customers = []
    for k, (name, contact, email, phone, *_rest) in CLIENTS.items():
        bal = sum(i["total"] - i["paidAmount"] for i in invoices if i["customerId"] == CUST_ID[k] and i["status"] not in ("Paid", "Draft"))
        customers.append({"id": CUST_ID[k], "name": name, "company": name, "email": email, "phone": phone,
                          "address": "Providence, RI" if not CLIENTS[k][6] else "Oslo, Norway",
                          "balance": round(bal, 2), "notes": f"Contact: {contact}", "isActive": True, "createdAt": "2025-03-01"})
    products = [{"id": PROD_ID[k], "name": n, "description": n, "type": "Service", "price": float(price), "cost": 0,
                 "category": "Services", "sku": "", "isActive": True, "isTaxable": False, "quantityOnHand": None}
                for k, (n, price) in PRODUCTS.items()]
    vendors = [
        {"id": "v_stripe", "name": "Stripe", "company": "Stripe, Inc.", "email": "support@stripe.com", "phone": "", "address": "354 Oyster Point Blvd, South San Francisco, CA", "balance": 0, "isActive": True, "createdAt": "2024-02-01"},
        {"id": "v_adobe", "name": "Adobe", "company": "Adobe Inc.", "email": "billing@adobe.com", "phone": "", "address": "San Jose, CA", "balance": 0, "isActive": True, "createdAt": "2024-02-01"},
        {"id": "v_figma", "name": "Figma", "company": "Figma, Inc.", "email": "billing@figma.com", "phone": "", "address": "San Francisco, CA", "balance": 0, "isActive": True, "createdAt": "2024-02-01"},
        {"id": "v_foundry", "name": "Foundry Coworking", "company": "Foundry Coworking LLC", "email": "rent@foundrypvd.com", "phone": "(401) 555-0100", "address": "10 Dorrance St, Providence, RI", "balance": 0, "isActive": True, "createdAt": "2024-02-01"},
        {"id": "v_print", "name": "Ocean State Print Co.", "company": "Ocean State Print Co.", "email": "jobs@oceanstateprint.com", "phone": "(401) 555-0150", "address": "Pawtucket, RI", "balance": 640, "isActive": True, "createdAt": "2024-03-11"},
        {"id": "v_courier", "name": "Swift Courier", "company": "Swift Courier RI", "email": "dispatch@swiftcourier.com", "phone": "(401) 555-0170", "address": "Providence, RI", "balance": 0, "isActive": True, "createdAt": "2024-05-20"},
        {"id": "v_gusto", "name": "Gusto", "company": "Gusto, Inc.", "email": "support@gusto.com", "phone": "", "address": "San Francisco, CA", "balance": 0, "isActive": True, "createdAt": "2024-02-01"},
    ]
    expenses = []

    def exp(eid, day, vendor, payee, cat, amount, desc):
        expenses.append({"id": eid, "date": day, "payee": payee, "vendorId": vendor, "category": cat,
                         "amount": float(D(amount)), "description": desc, "accountId": "acc1", "receipt": "",
                         "isBillable": False, "customerId": None, "status": "Cleared"})

    for p in sorted(PAYOUT_L.values(), key=lambda p: p["arrival"]):
        if p["status"] == "paid" and p["key"] not in ("pB", "pC"):
            d = date.fromisoformat(p["arrival"])
            exp(f"exp_fee_{p['key']}", p["arrival"], "v_stripe", "Stripe", "Miscellaneous", p["fees"],
                f"Stripe fees - payout {p['id']} ({d.strftime('%b')} {d.day})")
    exp("exp_rent_oct", "2026-10-01", "v_foundry", "Foundry Coworking", "Rent", 2400, "Studio rent - October")
    exp("exp_rent_nov", "2026-11-02", "v_foundry", "Foundry Coworking", "Rent", 2400, "Studio rent - November")
    exp("exp_adobe_oct", "2026-10-04", "v_adobe", "Adobe", "Software", 359.88, "Creative Cloud - 6 seats")
    exp("exp_adobe_nov", "2026-11-04", "v_adobe", "Adobe", "Software", 359.88, "Creative Cloud - 6 seats")
    exp("exp_figma_oct", "2026-10-11", "v_figma", "Figma", "Software", 225.00, "Figma Professional")
    exp("exp_figma_nov", "2026-11-11", "v_figma", "Figma", "Software", 225.00, "Figma Professional")
    exp("exp_print_1", "2026-10-17", "v_print", "Ocean State Print Co.", "Job Expenses", 1186.40, "Proof prints - Pinecrest brochure")
    exp("exp_courier_1", "2026-11-05", "v_courier", "Swift Courier", "Job Expenses", 85.00, "Rush proofs - Calder Bikes")
    exp("exp_courier_2", "2026-11-05", "v_courier", "Swift Courier", "Job Expenses", 240.00, "Rush proofs - Harbor & Pine")
    exp("exp_meal_1", "2026-11-12", None, "Nick's on Broadway", "Meals & Entertainment", 86.40, "Client lunch - Greywell")
    expenses.sort(key=lambda e: e["date"], reverse=True)

    accounts = [
        {"id": "acc1", "number": "10100", "name": "Checking", "type": "Bank", "detailType": "Checking", "balance": 48211.37, "bankBalance": 0, "isActive": True},
        {"id": "acc2", "number": "10200", "name": "Savings", "type": "Bank", "detailType": "Savings", "balance": 30000.00, "bankBalance": 30000.00, "isActive": True},
        {"id": "acc3", "number": "11000", "name": "Accounts Receivable", "type": "Accounts Receivable", "detailType": "Accounts Receivable (A/R)", "balance": 0, "bankBalance": 0, "isActive": True},
        {"id": "acc8", "number": "20000", "name": "Accounts Payable", "type": "Accounts Payable", "detailType": "Accounts Payable (A/P)", "balance": 640.00, "bankBalance": 640.00, "isActive": True},
        {"id": "acc10", "number": "21000", "name": "Visa", "type": "Credit Card", "detailType": "Credit Card", "balance": -1842.15, "bankBalance": -1842.15, "isActive": True},
        {"id": "acc9", "number": "30000", "name": "Owner's Equity", "type": "Equity", "detailType": "Owner's Equity", "balance": 25000.00, "bankBalance": 25000.00, "isActive": True},
        {"id": "acc13", "number": "40000", "name": "Design Services", "type": "Income", "detailType": "Service/Fee Income", "balance": 0, "bankBalance": 0, "isActive": True},
        {"id": "acc17", "number": "60100", "name": "Rent", "type": "Expenses", "detailType": "Rent or Lease", "balance": 0, "bankBalance": 0, "isActive": True},
        {"id": "acc18", "number": "60200", "name": "Software", "type": "Expenses", "detailType": "Office Expenses", "balance": 0, "bankBalance": 0, "isActive": True},
        {"id": "acc19", "number": "60300", "name": "Bank & Merchant Fees", "type": "Expenses", "detailType": "Bank Charges", "balance": 0, "bankBalance": 0, "isActive": True},
    ]
    # bank feed: one STRIPE deposit per payout that reached Checking, plus routine items
    txs = []
    for p in sorted(PAYOUT_L.values(), key=lambda p: p["arrival"]):
        if p["status"] != "paid":
            continue
        pending = p["key"] in ("pB", "pC")
        txs.append({"id": f"tx_{p['key']}", "accountId": "acc1", "date": p["arrival"],
                    "description": f"STRIPE TRANSFER ST-{p['id'][-8:].upper()} FERNHILL CREATIVE", "payee": "Stripe",
                    "amount": float(p["amount"]), "type": "credit", "category": "Uncategorized" if pending else "Sales",
                    "matchedTo": None, "status": "pending" if pending else "posted", "isReconciled": not pending})
    routine = [
        ("tx_rent_nov", "2026-11-02", "ACH FOUNDRY COWORKING", "Foundry Coworking", -2400.00, "Rent", "posted"),
        ("tx_gusto_1", "2026-10-30", "GUSTO PAYROLL 103026", "Gusto", -14820.55, "Payroll", "posted"),
        ("tx_gusto_2", "2026-11-13", "GUSTO PAYROLL 111326", "Gusto", -14820.55, "Payroll", "pending"),
        ("tx_adobe_nov", "2026-11-04", "ADOBE *CREATIVE CLOUD", "Adobe", -359.88, "Software", "posted"),
        ("tx_figma_nov", "2026-11-11", "FIGMA MONTHLY", "Figma", -225.00, "Software", "pending"),
        ("tx_chk_1159", "2026-10-30", "MOBILE DEPOSIT CHK 2210", "Larkspur Wealth", 5500.00, "Sales", "posted"),
        ("tx_chk_1150", "2026-10-09", "MOBILE DEPOSIT CHK 4471", "Ferro Architects", 4200.00, "Sales", "posted"),
        ("tx_courier", "2026-11-05", "SWIFT COURIER RI", "Swift Courier", -325.00, "Uncategorized", "pending"),
        ("tx_meal", "2026-11-12", "NICKS ON BROADWAY", "", -86.40, "Uncategorized", "pending"),
        ("tx_xfer", "2026-11-02", "ONLINE TRANSFER TO SAV ...7140", "", -5000.00, "Uncategorized", "pending"),
    ]
    for tid, day, desc, payee, amt, cat, st in routine:
        txs.append({"id": tid, "accountId": "acc1", "date": day, "description": desc, "payee": payee, "amount": amt,
                    "type": "credit" if amt > 0 else "debit", "category": cat, "matchedTo": None, "status": st,
                    "isReconciled": st == "posted"})
    txs.sort(key=lambda t: t["date"], reverse=True)
    accounts[0]["bankBalance"] = round(accounts[0]["balance"] + sum(t["amount"] for t in txs if t["status"] == "pending"), 2)

    return {
        "company": {"name": "Fernhill Creative LLC", "address": "214 Wickenden St, Providence, RI 02903",
                    "phone": "(401) 555-0190", "email": BOOKS, "website": "www.fernhillcreative.com",
                    "industry": "Graphic Design Services", "taxId": "47-2280913", "fiscalYearStart": "January",
                    "accountingMethod": "Accrual"},
        "customers": customers, "vendors": vendors, "products": products, "invoices": invoices,
        "estimates": [
            {"id": "est1", "number": "E-1031", "customerId": "c_kestrel", "date": "2026-11-06", "expiryDate": "2026-12-06",
             "items": [{"id": "ei1", "productId": "p_web", "description": "Dashboard UI - full build", "qty": 1, "rate": 12800, "amount": 12800}],
             "total": 12800, "status": "Pending"},
            {"id": "est2", "number": "E-1030", "customerId": "c_sunbeam", "date": "2026-10-20", "expiryDate": "2026-11-20",
             "items": [{"id": "ei2", "productId": "p_brand", "description": "Brand refresh", "qty": 1, "rate": 3900, "amount": 3900}],
             "total": 3900, "status": "Accepted"},
        ],
        "expenses": expenses,
        "bills": [
            {"id": "bill1", "vendorId": "v_print", "number": "OSP-8841", "date": "2026-11-09", "dueDate": "2026-12-09",
             "items": [{"id": "bi1", "description": "Lookbook print run - Sable & Stone", "qty": 1, "rate": 640, "amount": 640}],
             "total": 640, "status": "Open", "paidDate": None},
        ],
        "accounts": accounts, "transactions": txs,
        "employees": [
            {"id": "emp1", "name": "Nadia Okafor", "email": NADIA, "role": "Founder & Creative Director", "department": "Studio", "salary": 98000, "payFrequency": "Bi-weekly", "startDate": "2019-04-01", "isActive": True},
            {"id": "emp2", "name": "Felipe Santos", "email": "felipe@fernhillcreative.com", "role": "Senior Designer", "department": "Studio", "salary": 78000, "payFrequency": "Bi-weekly", "startDate": "2021-02-15", "isActive": True},
            {"id": "emp3", "name": "Hannah Lee", "email": "hannah@fernhillcreative.com", "role": "Web Developer", "department": "Studio", "salary": 82000, "payFrequency": "Bi-weekly", "startDate": "2022-06-01", "isActive": True},
            {"id": "emp4", "name": "Marcus Bell", "email": "marcus@fernhillcreative.com", "role": "Photographer", "department": "Studio", "salary": 64000, "payFrequency": "Bi-weekly", "startDate": "2023-03-20", "isActive": True},
            {"id": "emp5", "name": "Zoe Park", "email": "zoe@fernhillcreative.com", "role": "Junior Designer", "department": "Studio", "salary": 52000, "payFrequency": "Bi-weekly", "startDate": "2025-01-06", "isActive": True},
        ],
        "projects": [
            {"id": "proj1", "name": "Greywell rebrand", "customerId": "c_greywell", "status": "In Progress", "budget": 9500, "spent": 6100, "startDate": "2026-10-06", "endDate": None, "description": "Strategy, identity and rollout"},
            {"id": "proj2", "name": "Kestrel marketing site", "customerId": "c_kestrel", "status": "In Progress", "budget": 7200, "spent": 5900, "startDate": "2026-10-01", "endDate": None, "description": "Redesign and build"},
            {"id": "proj3", "name": "Ferro identity", "customerId": "c_ferro", "status": "Completed", "budget": 9800, "spent": 9100, "startDate": "2026-08-20", "endDate": "2026-10-28", "description": "Phases 1 and 2"},
        ],
        "emailDrafts": [],
    }


# ---------------------------------------------------------------- stripe
def ust(c: Decimal) -> int:
    return cents(c)


def build_stripe():
    customers, pms = [], []
    for k, (qbname, contact, qbemail, phone, sname, semail, intl) in CLIENTS.items():
        cid = rid("cus_", "cus" + k, 14)
        pm = rid("pm_1Q", "pm" + k, 21)
        brand = ["visa", "mastercard", "amex", "visa", "visa", "discover"][len(k) % 6]
        last4 = str(1000 + int(hashlib.md5(k.encode()).hexdigest()[:4], 16) % 9000)
        mine = [c for c in CHARGES_L if c["client"] == k]
        customers.append({"id": cid, "name": sname, "email": semail, "phone": phone, "description": None,
                          "address": {"line1": None, "line2": None, "city": "Oslo" if intl else "Providence",
                                      "state": None if intl else "RI", "postal_code": None, "country": "NO" if intl else "US"},
                          "balance": 0, "currency": "usd", "default_payment_method": pm, "metadata": {},
                          "created": unix("2025-03-01", "12:00"), "livemode": True, "delinquent": False,
                          "total_spent": sum(ust(c["amount"]) for c in mine), "payments_count": len(mine)})
        pms.append({"id": pm, "type": "card", "card": {"brand": brand, "last4": last4, "exp_month": 1 + len(k) % 12,
                    "exp_year": 2028, "funding": "credit"}, "billing_details": {"name": contact}, "created": unix("2025-03-01", "12:00"),
                    "customer": cid})
    cus = {k: customers[i] for i, k in enumerate(CLIENTS)}
    pm_by = {k: pms[i] for i, k in enumerate(CLIENTS)}

    def payment(key, client, created, amount, desc, meta, status="succeeded", refunded_amt=0, outcome_reason=None):
        c = cus[client]
        card = pm_by[client]["card"]
        return {"id": pid(key), "amount": amount, "currency": "usd", "status": status, "description": desc,
                "customer": c["id"], "customer_email": c["email"], "customer_name": c["name"],
                "payment_method": {"type": "card", "card": dict(card)},
                "amount_received": amount if status == "succeeded" else 0, "amount_refunded": refunded_amt,
                "refunded": refunded_amt >= amount and refunded_amt > 0, "disputed": False, "captured": status == "succeeded",
                "receipt_email": c["email"], "receipt_url": None, "metadata": dict(meta), "created": created, "livemode": True,
                "risk_score": 8 + (created % 30), "risk_level": "normal",
                "outcome": {"type": "authorized" if status == "succeeded" else "issuer_declined", "risk_level": "normal",
                            "risk_score": 8 + (created % 30), "reason": outcome_reason}, "invoice": None}

    refunded = {r["charge"]["key"]: ust(r["amount"]) for r in REFUNDS}
    payments = [payment(c["key"], c["client"], c["created"], ust(c["amount"]), c["desc"], c["meta"],
                        refunded_amt=refunded.get(c["key"], 0)) for c in CHARGES_L]
    for key, client, day, hm, amount, desc, reason in FAILED:
        payments.append(payment(key, client, unix(day, hm), cents(amount), desc, {}, status="failed", outcome_reason=reason))
    payments.sort(key=lambda p: -p["created"])

    refunds = [{"id": r["id"], "amount": ust(r["amount"]), "currency": "usd", "charge": r["charge"]["id"], "reason": r["reason"],
                "status": "succeeded", "created": r["created"], "metadata": {}} for r in REFUNDS]

    payouts, btx, events = [], [], []
    for p in sorted(PAYOUT_L.values(), key=lambda p: -unix(p["arrival"])):
        created = unix(p["arrival"], "06:00") - 2 * 86400
        payouts.append({"id": p["id"], "amount": ust(p["amount"]), "currency": "usd", "status": p["status"],
                        "arrival_date": unix(p["arrival"], "09:00"), "method": "standard", "type": "bank_account",
                        "description": "STRIPE PAYOUT", "destination": dict(BANK), "created": created,
                        "metadata": {}, "automatic": True})
        btx.append({"id": rid("txn_3Q", "txpo" + p["key"], 21), "amount": -ust(p["amount"]), "currency": "usd", "type": "payout",
                    "fee": 0, "net": -ust(p["amount"]), "status": "available", "available_on": created, "source": p["id"],
                    "description": "STRIPE PAYOUT", "created": created})
        if p["status"] == "paid":
            events.append({"id": rid("evt_3Q", "evpo" + p["key"], 21), "type": "payout.paid", "created": unix(p["arrival"], "09:00"),
                           "data": {"object": {"id": p["id"]}}, "request": None, "livemode": True})
    for c in CHARGES_L:
        btx.append({"id": rid("txn_3Q", "tx" + c["key"], 21), "amount": ust(c["amount"]), "currency": "usd", "type": "charge",
                    "fee": ust(c["fee"]), "net": ust(c["amount"] - c["fee"]), "status": "available" if c["group"] != "pend" else "pending",
                    "available_on": c["created"] + 2 * 86400, "source": c["id"], "description": c["desc"], "created": c["created"]})
        events.append({"id": rid("evt_3Q", "ev" + c["key"], 21), "type": "payment_intent.succeeded", "created": c["created"],
                       "data": {"object": {"id": c["id"]}}, "request": None, "livemode": True})
    for r in REFUNDS:
        btx.append({"id": rid("txn_3Q", "tx" + r["key"], 21), "amount": -ust(r["amount"]), "currency": "usd", "type": "refund",
                    "fee": 0, "net": -ust(r["amount"]), "status": "available", "available_on": r["created"] + 2 * 86400,
                    "source": r["id"], "description": f"Refund for {r['charge']['id']}", "created": r["created"]})
        events.append({"id": rid("evt_3Q", "ev" + r["key"], 21), "type": "charge.refunded", "created": r["created"],
                       "data": {"object": {"id": r["charge"]["id"]}}, "request": None, "livemode": True})
    for key, client, day, hm, amount, desc, reason in FAILED:
        events.append({"id": rid("evt_3Q", "ev" + key, 21), "type": "payment_intent.payment_failed",
                       "created": unix(day, hm), "data": {"object": {"id": pid(key)}}, "request": None, "livemode": True})
    btx.sort(key=lambda t: -t["created"])
    events.sort(key=lambda e: -e["created"])

    pending_net = sum(ust(c["amount"] - c["fee"]) for c in CHARGES_L if c["group"] == "pend")
    daily = []
    for d in range(28, -1, -1):
        day = date.fromisoformat(TODAY) - timedelta(days=d)
        gv = sum(ust(c["amount"]) for c in CHARGES_L if c["day"] == day.isoformat())
        daily.append({"date": f"{day.strftime('%b')} {day.day}", "amount": gv})
    gross = sum(x["amount"] for x in daily)
    return {
        "business": {"name": "Fernhill Creative", "email": BOOKS, "url": "https://fernhillcreative.com",
                     "support_email": "hello@fernhillcreative.com", "country": "US", "currency": "usd", "timezone": "America/New_York"},
        "currentUser": {"id": "user_rosa", "name": "Rosa Delgado", "email": BOOKS, "role": "administrator", "avatar": None},
        "balance": {"available": 0, "pending": pending_net, "reserved": 0, "currency": "usd"},
        "customers": customers, "payments": payments, "products": [], "prices": [], "invoices": [], "subscriptions": [],
        "payouts": payouts, "disputes": [], "refunds": refunds, "balanceTransactions": btx, "events": events,
        "paymentMethods": pms, "webhooks": [], "taxSettings": {"collect_automatically": False},
        "testMode": False, "searchQuery": "", "selectedDateRange": "last_4_weeks",
        "metrics": {
            "today": {"grossVolume": 0, "grossVolumeChart": [{"time": (f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}"), "amount": 0} for h in range(24)]},
            "summary": {"grossVolume": {"amount": gross, "change": 6.2, "previousAmount": int(gross / 1.062)},
                        "netVolume": {"amount": int(gross * 0.968), "change": 6.0, "previousAmount": int(gross * 0.968 / 1.06)},
                        "disputeActivity": {"rate": 0, "change": 0, "previousRate": 0}},
            "chartData": {"grossVolume": daily, "netVolume": [{"date": x["date"], "amount": int(x["amount"] * 0.968)} for x in daily],
                          "disputeRate": [{"date": x["date"], "rate": 0} for x in daily]},
        },
    }


# ---------------------------------------------------------------- gmail
def mail(eid, name, sender, subject, body, ts, read=False, category="primary", to=None, thread=None, folder="inbox"):
    return {"id": eid, "threadId": thread or f"t_{eid}", "from": {"name": name, "email": sender, "avatar": avatar(name)},
            "to": to or [{"name": "Fernhill Books", "email": BOOKS}], "cc": [], "bcc": [], "subject": subject, "body": body,
            "snippet": "", "timestamp": ts, "read": read, "starred": False, "important": False, "labels": [],
            "category": category, "folder": folder, "attachments": []}


def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def money(x) -> str:
    return f"{D(x):,.2f}"


def build_gmail():
    pb, pc, pd = PAYOUT_L["pB"], PAYOUT_L["pC"], PAYOUT_L["pD"]
    emails = [
        mail("m01", "Stripe", "notifications@stripe.com", f"Your payout of ${money(pb['amount'])} has been paid",
             p(f"Fernhill Creative, your payout {pb['id']} for ${money(pb['amount'])} USD was deposited to CITIZENS BANK ••••6612 on Nov 10, 2026."),
             iso_utc("2026-11-10", "09:05"), read=True),
        mail("m02", "Nadia Okafor", NADIA, "Wren paid twice",
             p("Rosa - Wren Outfitters paid invoice 1196 twice on Tuesday, two $2,640 charges a couple of minutes apart. "
               "Jonah emailed me about it. I'll refund the second one from my phone tonight.", "N"),
             iso_utc("2026-11-12", "18:41")),
        mail("m03", "Dana Reyes", "billing@juniperhealth.org", "Payment reference correction",
             p("Hi Fernhill team,", "The $1,450 card payment we made on Monday has invoice 1192 in the reference - that's a typo on our side. "
               "It was meant for the November retainer, invoice 1197. The brochure invoice (1192) is going through our AP run at the end of the month.",
               "Thanks,<br>Dana Reyes<br>Juniper Health Clinic"),
             iso_utc("2026-11-11", "10:22")),
        mail("m04", "Stripe", "notifications@stripe.com", f"Your payout of ${money(pc['amount'])} has been paid",
             p(f"Fernhill Creative, your payout {pc['id']} for ${money(pc['amount'])} USD was deposited to CITIZENS BANK ••••6612 on Nov 13, 2026."),
             iso_utc("2026-11-13", "09:04"), read=True),
        mail("m05", "Nadia Okafor", NADIA, "Calder Bikes",
             p("Tomas at Calder paid 1194 before we tacked on the $85 rush courier charge. I told him we'd eat it, "
               "so treat that invoice as paid in full and please don't chase him for the difference.", "Thanks! N"),
             iso_utc("2026-11-13", "15:12")),
        mail("m06", "Stripe", "notifications@stripe.com", f"Your payout of ${money(pd['amount'])} is on its way",
             p(f"Fernhill Creative, a payout of ${money(pd['amount'])} USD ({pd['id']}) is on its way to CITIZENS BANK ••••6612. "
               "It's expected to arrive on Mon, Nov 16, 2026. Bank processing times can vary."),
             iso_utc("2026-11-14", "06:02")),
        mail("m07", "Priya Raman", "ap@kestrelanalytics.io", "Re: Invoice 1154",
             p("Hi Rosa, paid the remaining balance on 1154 by card this morning. Thanks for the reminder!", "Priya"),
             iso_utc("2026-11-04", "11:02"), read=True),
        mail("m08", "Gusto", "no-reply@gusto.com", "Payroll processed for Nov 13",
             p("Your payroll for the period Oct 31 - Nov 13 has been processed. Total debit: $14,820.55."),
             iso_utc("2026-11-12", "13:00"), read=True, category="promotions"),
        mail("m09", "Joan Abernathy", "office@pinecrestmontessori.org", "W-9 for our files?",
             p("Hi! Our business office is asking for an updated W-9 from Fernhill before year end. Could you send one over when you get a chance?", "Joan"),
             iso_utc("2026-11-13", "14:30")),
        mail("m10", "Rachel Kim", "ap@tidewaterbrewing.com", "Invoice 1176 paid",
             p("Hi, paid invoice 1176 by card today. Thanks, Rachel - Tidewater AP"),
             iso_utc("2026-11-04", "16:40"), read=True),
        mail("m11", "Adobe", "mail@mail.adobe.com", "Your Creative Cloud invoice is ready",
             p("Your Creative Cloud for teams invoice for $359.88 is available in the Admin Console."),
             iso_utc("2026-11-04", "08:00"), read=True, category="promotions"),
        mail("m12", "Nadia Okafor", NADIA, "Stripe payouts",
             p("Thanks for booking the first two November payouts last week. Can you pick up the rest Monday? Same way as before."),
             iso_utc("2026-11-14", "17:20")),
        mail("m13", "Jonah Wren", "finance@wrenoutfitters.com", "Double charge",
             p("Hi Nadia, looks like our card was charged twice for invoice 1196 on Tuesday ($2,640 x2). Could you refund one of them? Thanks, Jonah"),
             iso_utc("2026-11-11", "09:15"), read=True, to=[{"name": "Nadia Okafor", "email": NADIA}, {"name": "Fernhill Books", "email": BOOKS}]),
        mail("m14", "Ocean State Print Co.", "jobs@oceanstateprint.com", "Invoice OSP-8841",
             p("Attached is invoice OSP-8841 for the Sable & Stone lookbook run, $640.00, due Dec 9."),
             iso_utc("2026-11-09", "12:10"), read=True),
        mail("m15", "Figma", "billing@figma.com", "Receipt for your Figma payment",
             p("We received your payment of $225.00 for Figma Professional."),
             iso_utc("2026-11-11", "07:00"), read=True, category="promotions"),
    ]
    emails[2]["read"] = False
    for e in emails:
        e["snippet"] = e["body"].replace("<p>", "").replace("</p>", " ").replace("<br>", " ")[:100]
    return {
        "user": {"userId": "u1", "username": "Fernhill Books", "email": BOOKS, "avatar": avatar("Fernhill Books")},
        "emails": emails,
        "labels": [{"id": "l1", "name": "Clients", "color": "#3b82f6"}, {"id": "l2", "name": "Vendors", "color": "#22c55e"},
                   {"id": "l3", "name": "Bank", "color": "#eab308"}],
        "drafts": [],
        "settings": {"signature": "--\nRosa Delgado\nBookkeeping, Fernhill Creative", "undoSend": 5},
    }


# ---------------------------------------------------------------- CSV export
CSV_COLS = ["automatic_payout_id", "automatic_payout_effective_at", "balance_transaction_id", "created_utc",
            "reporting_category", "source_id", "payment_intent_id", "customer_email", "gross", "fee", "net", "currency"]


def export_rows():
    rows = [CSV_COLS]
    for gkey in ("p0", "pA", "pB", "pC", "pD"):
        p = PAYOUT_L[gkey]
        items = []
        for c in p["charges"]:
            items.append((c["created"], [p["id"], p["arrival"], rid("txn_3Q", "tx" + c["key"], 21),
                          datetime.fromtimestamp(c["created"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "charge",
                          c["id"], c["id"], CLIENTS[c["client"]][5], f"{c['amount']:.2f}", f"{c['fee']:.2f}",
                          f"{c['amount'] - c['fee']:.2f}", "usd"]))
        for r in p["refunds"]:
            items.append((r["created"], [p["id"], p["arrival"], rid("txn_3Q", "tx" + r["key"], 21),
                          datetime.fromtimestamp(r["created"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "refund",
                          r["id"], r["charge"]["id"], CLIENTS[r["charge"]["client"]][5], f"{-r['amount']:.2f}", "0.00",
                          f"{-r['amount']:.2f}", "usd"]))
        rows += [r for _, r in sorted(items, key=lambda x: x[0])]
    return rows


# ---------------------------------------------------------------- golden / variants
RECON_COLS = ["payment_id", "payout_id", "invoices", "action"]


def recon_rows(truth=None, extra=()):
    truth = truth or TRUTH
    rows = [RECON_COLS]
    for gkey in ("pB", "pC"):
        for c in PAYOUT_L[gkey]["charges"]:
            invs, act = truth[c["key"]]
            rows.append([c["id"], PAYOUT_L[gkey]["id"], ";".join(str(n) for n in invs), act])
    rows += list(extra)
    return rows


def receive_payment(qb, number):
    inv = next(i for i in qb["invoices"] if i["number"] == str(number))
    inv.update({"status": "Paid", "paidAmount": inv["total"], "paidDate": TODAY})


def add_fee_expense(qb, gkey, amount=None):
    p = PAYOUT_L[gkey]
    d = date.fromisoformat(p["arrival"])
    qb["expenses"].insert(0, {"id": f"golden-fee-{gkey}", "date": p["arrival"], "payee": "Stripe", "category": "Miscellaneous",
                              "amount": float(amount if amount is not None else p["fees"]),
                              "description": f"Stripe fees - payout {p['id']} ({d.strftime('%b')} {d.day})",
                              "vendorId": "v_stripe", "accountId": "acc1", "receipt": "", "isBillable": False,
                              "customerId": None, "status": "Cleared", "type": "Expense"})


def stripe_refund(st, key, amount_cents=None):
    pay = next(x for x in st["payments"] if x["id"] == pid(key))
    amt = amount_cents if amount_cents is not None else pay["amount"] - pay["amount_refunded"]
    now = int(datetime.fromisoformat(CLOCK).timestamp()) + 1800
    ref = {"id": f"re_golden_{key}", "amount": amt, "currency": "usd", "charge": pay["id"], "reason": "requested_by_customer",
           "status": "succeeded", "created": now, "metadata": {}}
    st["refunds"].insert(0, ref)
    pay["amount_refunded"] += amt
    pay["refunded"] = pay["amount_refunded"] >= pay["amount"]
    st["balance"]["available"] -= amt
    st["balanceTransactions"].insert(0, {"id": f"txn_golden_{key}", "amount": -amt, "currency": "usd", "type": "refund", "fee": 0,
                                         "net": -amt, "status": "available", "available_on": now + 172800, "source": ref["id"],
                                         "description": f"Refund for {pay['id']}", "created": now})
    st["events"].insert(0, {"id": f"evt_golden_{key}", "type": "charge.refunded", "created": now,
                            "data": {"object": {"id": pay["id"]}}, "request": None, "livemode": True})


def send_mail(gm, to_email, to_name, subject, body, n):
    gm["emails"].insert(0, {"id": f"sent_golden_{n}", "threadId": f"t_sent_golden_{n}",
                            "from": {"name": "Fernhill Books", "email": BOOKS, "avatar": avatar("Fernhill Books")},
                            "to": [{"name": to_name, "email": to_email}], "cc": [], "bcc": [], "subject": subject,
                            "body": f"<p>{body}</p>", "snippet": body[:100], "timestamp": "2026-11-16T15:20:00.000Z",
                            "read": True, "starred": False, "important": False, "labels": [], "category": "primary",
                            "folder": "sent", "attachments": []})


def short_email(gm, number, to_email, owed, n):
    inv = INV[number]
    name = CLIENTS[inv["client"]][1]
    send_mail(gm, to_email, name, f"Invoice {number} - remaining balance",
              f"Hi {name.split()[0]}, thanks for your card payment on invoice {number}. It came through ${money(inv['total'] - owed)} "
              f"against the ${money(inv['total'])} invoice total, so ${money(owed)} is still outstanding on invoice {number}. "
              "You can pay the balance at fernhillcreative.com/pay. Thanks! Rosa", n)


def apply_run(seed, *, paid=None, shorts=None, refund_keys=("c1196b",), fee_payouts=("pB", "pC"), refunds_extra=()):
    qb, st, gm = (copy.deepcopy(seed[k]) for k in ("quickbooks", "stripe_dashboard", "gmail"))
    for n in (PAID_INVOICES if paid is None else paid):
        receive_payment(qb, n)
    for gkey in fee_payouts:
        add_fee_expense(qb, gkey)
    for key in list(refund_keys) + list(refunds_extra):
        stripe_refund(st, key)
    shorts = [(n, e, a) for n, (e, a) in SHORT.items()] if shorts is None else shorts
    for i, (n, e, a) in enumerate(shorts):
        short_email(gm, n, e, a, i)
    return {"quickbooks": qb, "stripe_dashboard": st, "gmail": gm}


def naive_variant(seed):
    """Falls into every trap: books every payout in the file, compares charges to invoice totals,
    trusts the typed invoice number and Nadia's 'I'll refund it', matches by name, emails the Stripe address."""
    paid = set(PAID_INVOICES)
    paid -= {1154, 1157, 1160}          # deposit balances look short
    paid -= {1198}                       # combined payment only by metadata
    paid -= {1179}                       # split payment: two "short" charges
    paid -= {1193, 1197, 1194, 1183}     # wrong ref, typo ref, waived, unreferenced
    paid |= {1184}                       # near-duplicate customer
    paid |= set(IN_TRANSIT_INVOICES)     # in-transit payout
    shorts = [
        (1176, "ap@tidewaterbrewing.com", D(250)),
        (1195, "m.ostrowski@gmail.com", D(240)),
        (1154, "ap@kestrelanalytics.io", D(3600)), (1157, "ap@greywell.partners", D(3000)),
        (1160, "office@northgatedental.com", D(2400)), (1179, "billing@lumensolar.coop", D(860)),
        (1192, "billing@juniperhealth.org", D(1450)), (1194, "tomas@calderbikes.com", D(85)),
    ]
    states = apply_run(seed, paid=sorted(paid), shorts=shorts, refund_keys=(), fee_payouts=("p0", "pA", "pB", "pC", "pD"),
                       refunds_extra=("c1158",))
    truth = dict(TRUTH)
    for k in ("b1154", "c1157", "c1160", "b1179a", "b1179b", "c1192", "c1194"):
        truth[k] = (truth[k][0] if k not in ("c1192",) else [1192], "short")
    truth["c1191"] = ([1191], "paid")
    truth["c1158"] = ([1158], "refunded")
    truth["b1183"] = ([1184], "paid")
    truth["c1196b"] = ([1196], "already_refunded")
    extra = []
    for gkey in ("pA", "pD"):
        for c in PAYOUT_L[gkey]["charges"]:
            extra.append([c["id"], PAYOUT_L[gkey]["id"], c["desc"].split()[-1].lstrip("#"), "paid"])
    return states, recon_rows(truth, extra)


def slip_in_transit(seed):
    """Careful run that also books the in-transit Nov 16 payout."""
    states = apply_run(seed, paid=PAID_INVOICES + IN_TRANSIT_INVOICES, fee_payouts=("pB", "pC", "pD"))
    extra = [[c["id"], PAYOUT_L["pD"]["id"], c["desc"].split()[-1].lstrip("#"), "paid"] for c in PAYOUT_L["pD"]["charges"]]
    return states, recon_rows(extra=extra)


def slip_deposits(seed):
    """Careful run that compares the deposit-balance payments to the invoice total instead of the open balance."""
    paid = [n for n in PAID_INVOICES if n not in (1154, 1157, 1160)]
    shorts = [(n, e, a) for n, (e, a) in SHORT.items()] + [
        (1154, "ap@kestrelanalytics.io", D(3600)), (1157, "ap@greywell.partners", D(3000)), (1160, "office@northgatedental.com", D(2400))]
    states = apply_run(seed, paid=paid, shorts=shorts)
    truth = dict(TRUTH)
    for k in ("b1154", "c1157", "c1160"):
        truth[k] = (truth[k][0], "short")
    return states, recon_rows(truth)


def slip_wren_refund(seed):
    """Careful run that trusts Nadia's 'I'll refund it tonight' and never checks Stripe."""
    states = apply_run(seed, refund_keys=())
    truth = dict(TRUTH)
    truth["c1196b"] = ([1196], "already_refunded")
    return states, recon_rows(truth)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def expected():
    items = []
    for gkey in ("pB", "pC"):
        for c in PAYOUT_L[gkey]["charges"]:
            invs, act = TRUTH[c["key"]]
            items.append({"payment_id": c["id"], "payout_id": PAYOUT_L[gkey]["id"], "client": CLIENTS[c["client"]][0],
                          "amount": f"{c['amount']:.2f}", "fee": f"{c['fee']:.2f}", "stripe_description": c["desc"],
                          "invoices": invs, "action": act, "kind": ITEM_KIND.get(c["key"], "standard")})
    non_target = []
    for gkey in ("pD",):
        for c in PAYOUT_L[gkey]["charges"]:
            non_target.append({"payment_id": c["id"], "payout_id": PAYOUT_L[gkey]["id"], "invoice": int(c["desc"].split()[-1].lstrip("#")),
                               "reason": "payout in_transit on 2026-11-16, not yet in the bank feed"})
    return {
        "clock": CLOCK, "today": TODAY,
        "payouts": {g: {"id": PAYOUT_L[g]["id"], "arrival": PAYOUT_L[g]["arrival"], "status": PAYOUT_L[g]["status"],
                        "amount": f"{PAYOUT_L[g]['amount']:.2f}", "fees": f"{PAYOUT_L[g]['fees']:.2f}",
                        "role": {"p0": "already_booked", "pA": "already_booked", "pB": "reconcile", "pC": "reconcile", "pD": "in_transit"}[g]}
                    for g in ("p0", "pA", "pB", "pC", "pD")},
        "fee_expenses": {PAYOUT_L[g]["id"]: f"{PAYOUT_L[g]['fees']:.2f}" for g in ("pB", "pC")},
        "stripe_vendor_id": "v_stripe",
        "items": items,
        "invoices_to_mark_paid": PAID_INVOICES,
        "short_invoices": {str(n): {"email": e, "owed": f"{a:.2f}", "wrong_email": "m.ostrowski@gmail.com" if n == 1195 else None}
                           for n, (e, a) in SHORT.items()},
        "refund": {"payment_id": pid("c1196b"), "amount_cents": cents(2640),
                   "acceptable_alternative": pid("c1196a"),
                   "note": "Wren paid 1196 twice; refunding either of the two identical charges in full is acceptable "
                           "(Nadia's email names the second, 10:04 ET). Exactly one of the two must be refunded; the CSV row of the "
                           "refunded one says refunded and the other says paid."},
        "already_refunded_payment_id": pid("b1180b"),
        "must_stay_open": sorted(set(IN_TRANSIT_INVOICES + PENDING_INVOICES + DECOY_OPEN + OPEN_TARGET_SHORT)),
        "in_transit_items": non_target,
        "no_chase": {"1194": "tomas@calderbikes.com", "1192": "billing@juniperhealth.org"},
        "decoys": {"1184": "Marlow & Finch Legal - same $1,800 amount as Marlowe Finch Design's 1183",
                   "1192": "typed reference on Juniper's 1,450 payment; real target 1197 (client email)",
                   "1158": "typed reference on Atlas's 1,975 payment; 1158 was paid in October, real target 1193"},
    }


def main(out: Path):
    seed = {"quickbooks": build_quickbooks(), "stripe_dashboard": build_stripe(), "gmail": build_gmail()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden = apply_run(seed)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "payout_reconciliation.csv", recon_rows())
    write_csv(out / "input" / "stripe_payouts_nov.csv", export_rows())
    write_json(out / "expected.json", expected())

    variants = {
        "golden": (golden, recon_rows()),
        "nop": (seed, None),
        "naive": naive_variant(seed),
        "slip_in_transit": slip_in_transit(seed),
        "slip_deposits": slip_deposits(seed),
        "slip_wren_refund": slip_wren_refund(seed),
    }
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "payout_reconciliation.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
