#!/usr/bin/env python3
"""World for exp1-l12 (cua-hard/hartley-part-year-calfile): CalFile + Gmail + PayPal + local CSV.

Story: Daniel Hartley moved from Portland, OR to Sacramento in June 2024 and files a joint
2024 California return with his wife Leah (full-year resident) in CalFile, under Leah's MyFTB
account where she already typed in her own forms. Their preparer Gloria Reyes did the federal
return and emailed the rules for finishing the California 540 (Gmail). The amounts live in PDF
attachments (W-2s, W-2c, 1099-INTs, lease), Daniel's PayPal activity (photography income, some in
CAD) and a local Bank of Canada rate export. Lever L12: proration by days in a leap year, CAD
conversion at a date-specific rate with a "last published rate" fallback, cent rounding per item,
and a fee tier computed from a corrected rate card.

Writes into <out>/:
  seed/{california_tax,gmail,paypal}.json      initial state per site
  seed/files/gmail/*.pdf                       email attachments
  golden/{...}.json                            state after a correct run
  golden_output/photography_2024.csv           correct CLI deliverable
  input/boc_usdcad_2024.csv                    agent-visible workspace input
  expected.json                                truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/}
"""

import copy
import csv
import datetime as dt
import hashlib
import json
import math
import random
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, long_pdf  # noqa: E402

CLOCK = "2025-04-10T09:15:00-07:00"
NOW_Z = "2025-04-10T16:15:00.000Z"
DANIEL = ("Daniel Hartley", "daniel.hartley@gmail.com")
LEAH = ("Leah Hartley", "leah.hartley@gmail.com")
GLORIA = ("Gloria Reyes, EA", "gloria@reyestaxservices.com")
FEE_PAYPAL = "payments@reyestaxservices.com"
GLORIA_PERSONAL = "gloria.reyes82@gmail.com"

RESIDENCY_START = dt.date(2024, 6, 18)      # lease commencement (lease PDF)
NAIVE_MOVE = dt.date(2024, 6, 15)           # what Daniel wrote in his own email
DAYS_IN_2024 = 366


def cents(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def m(x) -> str:
    return f"{cents(x):.2f}"


def commas(x) -> str:
    return f"{cents(x):,.2f}"


# ---------------------------------------------------------------- Bank of Canada USD/CAD series
BOC_HOLIDAYS = {"2024-01-01", "2024-02-19", "2024-03-29", "2024-04-01", "2024-05-20", "2024-07-01", "2024-08-05",
                "2024-09-02", "2024-09-30", "2024-10-14", "2024-11-11", "2024-12-25", "2024-12-26"}
# Pinned values around the CAD payment dates so the fallback rule changes the cents.
BOC_PINNED = {"2024-03-21": 1.3552, "2024-03-22": 1.3577, "2024-03-25": 1.3604,
              "2024-06-14": 1.3741, "2024-06-17": 1.3719, "2024-06-18": 1.3706,
              "2024-08-29": 1.3478, "2024-08-30": 1.3491, "2024-09-03": 1.3542,
              "2024-12-24": 1.4373, "2024-12-27": 1.4398, "2024-12-30": 1.4381}


def boc_rates():
    rng = random.Random(20240)
    anchors = [(0, 1.3390), (60, 1.3540), (120, 1.3650), (170, 1.3720), (210, 1.3700), (240, 1.3500),
               (300, 1.3820), (335, 1.4010), (366, 1.4390)]
    rates, d = {}, dt.date(2024, 1, 1)
    while d.year == 2024:
        k = (d - dt.date(2024, 1, 1)).days
        for (a, va), (b, vb) in zip(anchors, anchors[1:]):
            if a <= k <= b:
                base = va + (vb - va) * (k - a) / (b - a)
                break
        s = d.isoformat()
        if d.weekday() < 5 and s not in BOC_HOLIDAYS:
            rates[s] = BOC_PINNED.get(s, round(base + rng.uniform(-0.0045, 0.0045), 4))
        d += dt.timedelta(days=1)
    return rates


RATES = boc_rates()


def rate_for(day: str, mode="fallback"):
    """fallback = last published on/before (correct); next = first published on/after (slip)."""
    d = dt.date.fromisoformat(day)
    step = -1 if mode == "fallback" else 1
    while d.isoformat() not in RATES:
        d += dt.timedelta(days=step)
    return RATES[d.isoformat()]


# ---------------------------------------------------------------- forms (PDF attachments)
LEAH_W2 = {"employer": "Capitol Health Partners", "ein": "68-0412975", "wages": "71840.00", "fed": "8920.00",
           "state_wages": "71840.00", "state_wh": "1380.00"}
LEAH_W2C_WAGES = "70915.00"          # corrected box 1 and box 16 (box 2 / 17 unchanged)
CASCADE = {"employer": "Cascade Outfitters Supply Co.", "ein": "93-1184520", "wages": "38416.92", "fed": "4105.30",
           "or_wages": "38416.92", "or_wh": "2987.11"}
SIERRA = {"employer": "Sierra Ridge Engineering, Inc.", "ein": "68-0527714", "wages": "46250.00", "fed": "5212.40",
          "state_wages": "46250.00", "state_wh": "774.62"}
LEAH_INT = ("Golden 1 Credit Union", "88.17")
WVCU_INT = ("Willamette Valley Credit Union", "612.40")
SAFE_INT = ("SAFE Credit Union", "23.18")

ESTIMATES = [  # (date paid, tax year, installment, amount, account)
    ("2024-01-12", 2023, 4, "180.00", ("savings", "2290")),
    ("2024-06-14", 2024, 2, "250.00", ("savings", "2290")),
    ("2024-09-12", 2024, 3, "300.00", ("savings", "2290")),
    ("2025-01-14", 2024, 4, "450.00", ("checking", "4471")),
    ("2025-04-01", 2025, 1, "200.00", ("checking", "4471")),
]
EST_2024 = sum(Decimal(a) for d, y, i, a, _ in ESTIMATES if y == 2024)
EST_ALL = sum(Decimal(a) for d, y, i, a, _ in ESTIMATES)

BANK = {"routing": "321175261", "account": "1180074471", "type": "checking", "last4": "4471"}


def build_pdfs(files: Path):
    g = files / "gmail"
    long_pdf(g / "W2_2024_Cascade_Outfitters.pdf", "2024 Form W-2 Wage and Tax Statement", [
        ("Employer", ["Cascade Outfitters Supply Co., 1220 SE Water Ave, Portland, OR 97214",
                      "b Employer identification number (EIN): 93-1184520", "Control number: CO-24-00871"]),
        ("Employee", ["Daniel J Hartley, SSN XXX-XX-3318", "Address on file: 4410 SE Lincoln St, Portland, OR 97215",
                      "Employment dates: 01/01/2024 - 06/07/2024 (separated)"]),
        ("Federal boxes", [f"1 Wages, tips, other compensation: {commas(CASCADE['wages'])}",
                           f"2 Federal income tax withheld: {commas(CASCADE['fed'])}",
                           "3 Social security wages: 39,816.92    4 Social security tax withheld: 2,468.65",
                           "5 Medicare wages and tips: 39,816.92    6 Medicare tax withheld: 577.35",
                           "12a Code D (401k elective deferral): 1,400.00"]),
        ("State and local", ["15 State: OR   Employer's state ID: 0918842-6",
                             f"16 State wages, tips, etc.: {commas(CASCADE['or_wages'])}",
                             f"17 State income tax: {commas(CASCADE['or_wh'])}",
                             "No other state is reported on this W-2.",
                             "Statewide transit tax (OR STT) withheld: 38.42"]),
    ])
    long_pdf(g / "W2_2024_SierraRidge.pdf", "2024 Form W-2 Wage and Tax Statement", [
        ("Employer", ["Sierra Ridge Engineering, Inc., 1515 K Street, Suite 400, Sacramento, CA 95814",
                      "b Employer identification number (EIN): 68-0527714", "Control number: SRE-2024-1197"]),
        ("Employee", ["Daniel J Hartley, SSN XXX-XX-3318", "2715 J Street, Apt 4, Sacramento, CA 95816",
                      "Hire date: 06/24/2024"]),
        ("Federal boxes", [f"1 Wages, tips, other compensation: {commas(SIERRA['wages'])}",
                           f"2 Federal income tax withheld: {commas(SIERRA['fed'])}",
                           "3 Social security wages: 46,250.00    4 Social security tax withheld: 2,867.50",
                           "5 Medicare wages and tips: 46,250.00    6 Medicare tax withheld: 670.63"]),
        ("State and local", ["15 State: CA   Employer's state ID: 418-2291-7",
                             f"16 State wages, tips, etc.: {commas(SIERRA['state_wages'])}",
                             f"17 State income tax: {commas(SIERRA['state_wh'])}",
                             "14 Other: CA SDI 508.75"]),
    ])
    long_pdf(g / "W2c_2024_CapitolHealth.pdf", "Form W-2c Corrected Wage and Tax Statement (Tax year 2024)", [
        ("Employer", ["Capitol Health Partners, 2600 Capitol Ave, Sacramento, CA 95816",
                      "Employer identification number (EIN): 68-0412975",
                      "Reason for correction: 401(k) elective deferrals for Oct-Dec 2024 were not excluded from box 1 "
                      "and box 16 on the original W-2 issued 01/22/2025."]),
        ("Employee", ["Leah M Hartley, SSN XXX-XX-7742"]),
        ("Box 1 Wages, tips, other compensation",
         [f"Previously reported: {commas(LEAH_W2['wages'])}", f"Correct information: {commas(LEAH_W2C_WAGES)}"]),
        ("Box 2 Federal income tax withheld", ["Not changed (original W-2 amount stands): " + commas(LEAH_W2['fed'])]),
        ("Box 12a Code D", ["Previously reported: 6,100.00", "Correct information: 7,025.00"]),
        ("State correction (CA, employer state ID 207-5512-4)",
         [f"Box 16 State wages - Previously reported: {commas(LEAH_W2['state_wages'])}",
          f"Box 16 State wages - Correct information: {commas(LEAH_W2C_WAGES)}",
          "Box 17 State income tax: not changed (" + commas(LEAH_W2['state_wh']) + ")"]),
    ])
    long_pdf(g / "1099-INT_2024_WVCU.pdf", "2024 Form 1099-INT Interest Income", [
        ("Payer", ["Willamette Valley Credit Union, PO Box 2117, Salem, OR 97308", "Payer TIN 93-0381527"]),
        ("Recipient", ["Daniel J Hartley, account ending 5520 (High-Yield Share Savings)",
                       "Account open all of 2024; interest credited monthly."]),
        ("Amounts", [f"1 Interest income: {commas(WVCU_INT[1])}", "2 Early withdrawal penalty: 0.00",
                     "4 Federal income tax withheld: 0.00"]),
    ])
    long_pdf(g / "1099-INT_2024_SAFE.pdf", "2024 Form 1099-INT Interest Income", [
        ("Payer", ["SAFE Credit Union, 2295 Iron Point Rd, Folsom, CA 95630", "Payer TIN 94-1187455"]),
        ("Recipient", ["Daniel J Hartley, Money Market account ending 0193, opened 07/08/2024"]),
        ("Amounts", [f"1 Interest income: {commas(SAFE_INT[1])}", "4 Federal income tax withheld: 0.00"]),
    ])
    long_pdf(g / "Lease_2715J_Unit4.pdf", "Residential Lease Agreement - 2715 J Street, Apt 4, Sacramento, CA 95816", [
        ("1. Parties", ["This Lease is made on June 5, 2024 between Capitol Row Property Management LLC (\"Landlord\") "
                        "and Leah M. Moreno and Daniel J. Hartley (\"Tenants\")."]),
        ("2. Term", ["The term of this Lease begins on June 18, 2024 (the \"Commencement Date\") and ends on "
                     "June 30, 2025, after which it continues month to month.",
                     "Tenants may take possession and move in on the Commencement Date. Keys are released at the "
                     "Landlord's office on that date."]),
        ("3. Rent", ["Monthly rent is $2,385.00, due on the 1st. Rent for June 18-30, 2024 is prorated to $1,033.50 "
                     "and is due with the security deposit."]),
        ("4. Security deposit", ["A security deposit of $2,385.00 is due at signing, June 5, 2024."]),
        ("5. Utilities", ["Tenants pay SMUD electric and PG&E gas. Landlord pays water, sewer and trash."]),
        ("6. Occupants", ["The Premises shall be occupied only by the Tenants named above."]),
        ("7. Pets", ["One cat is permitted with a $300 pet deposit."]),
        ("8. Signatures", ["Signed by Landlord and Tenants on June 5, 2024."]),
    ])


# ---------------------------------------------------------------- PayPal
CLIENT_TX = [  # key, date, kind, name, email, desc, amount, currency
    ("F01", "2024-01-05", "in", "Willamette Weddings", "books@willametteweddings.com",
     "Final balance - Price/Okoro wedding (Dec 9)", "600.00", "USD"),
    ("F02", "2024-02-09", "in", "Rose City Brewing Co.", "ap@rosecitybrewing.com",
     "Spring can-release product shoot", "875.00", "USD"),
    ("F03", "2024-03-23", "in", "Northbound Media Inc.", "payables@northboundmedia.ca",
     "Editorial assignment NB-0324, paid in CAD", "1200.00", "CAD"),
    ("F04", "2024-04-30", "in", "Hawthorne Family Dental", "office@hawthornedental.com",
     "Staff headshots (8 people)", "420.00", "USD"),
    ("F05", "2024-05-14", "refund", "Hawthorne Family Dental", "office@hawthornedental.com",
     "Refund - 2 headshot retakes not delivered", "90.00", "USD"),
    ("F06", "2024-06-15", "in", "Pearl District Gallery", "info@pearldistrictgallery.com",
     "Exhibition prints and install photos", "1180.00", "USD"),
    ("F07", "2024-06-17", "in", "Northbound Media Inc.", "payables@northboundmedia.ca",
     "Summer feature NB-0624, paid in CAD", "640.00", "CAD"),
    ("F08", "2024-06-18", "in", "Midtown Farmers Market Assoc.", "hello@midtownfarmersmarket.org",
     "Promo shoot - opening day", "300.00", "USD"),
    ("F09", "2024-09-02", "in", "Northbound Media Inc.", "payables@northboundmedia.ca",
     "Fall issue NB-0924, paid in CAD", "900.00", "CAD"),
    ("F10", "2024-09-21", "in", "Tower Bridge Events", "billing@towerbridgeevents.com",
     "Corporate gala coverage (Sep 14)", "1780.00", "USD"),
    ("F11", "2024-10-05", "refund", "Tower Bridge Events", "billing@towerbridgeevents.com",
     "Partial refund - late gallery delivery", "200.00", "USD"),
    ("F12", "2024-11-16", "in", "Delta Vine Winery", "events@deltavinewinery.com",
     "Harvest shoot - website and social set", "960.00", "USD"),
    ("F13", "2024-12-28", "in", "Northbound Media Inc.", "payables@northboundmedia.ca",
     "Holiday spread NB-1224, paid in CAD", "480.00", "CAD"),
]
CAMERA = ("X01", "2024-07-02", "Kyle Brennan", "kbrennan.photo@gmail.com", "Sold: used Fujifilm X-T3 body + 2 batteries", "780.00")


def fee_for(amount: str, currency: str, kind: str) -> Decimal:
    if kind == "refund":
        return Decimal("0.00")
    a = Decimal(amount)
    return cents(a * Decimal("0.0499") + Decimal("0.59")) if currency == "CAD" else cents(a * Decimal("0.0349") + Decimal("0.49"))


def ts(day: str, hhmm: str = "20:10") -> str:
    return f"{day}T{hhmm}:00.000Z"


def tx(key, kind, day, amount, *, currency="USD", fee="0.00", name=None, email=None, desc="", category="services",
       status="completed", source=None, destination=None, hhmm="20:10"):
    # paypal_mock's normalizeTransaction keeps only these keys (fee/netAmount/transactionId/category are dropped),
    # so the seed carries gross amounts only and the fee rule lives in Gloria's email.
    base = {"id": f"t_{key.lower()}", "type": kind, "amount": float(Decimal(amount)), "currency": currency,
            "recipientName": "", "senderName": "", "destination": destination or "", "date": ts(day, hhmm),
            "status": status, "description": desc}
    if kind in ("payment_sent", "request_sent"):
        base["recipientName"] = name
    elif kind in ("payment_received", "refund"):
        base["senderName"] = name
    return base


def build_paypal():
    t = []
    for key, day, kind, name, email, desc, amount, cur in CLIENT_TX:
        if kind == "in":
            t.append(tx(key, "payment_received", day, amount, currency=cur, fee=fee_for(amount, cur, kind), name=name,
                        email=email, desc=desc, source="PayPal"))
        else:
            t.append(tx(key, "payment_sent", day, amount, name=name, email=email, desc=desc, source="PayPal balance"))
    k, day, name, email, desc, amount = CAMERA
    t.append(tx(k, "payment_received", day, amount, fee=fee_for(amount, "USD", "in"), name=name, email=email,
                desc=desc, category="goods", source="PayPal"))
    noise = [
        tx("P2301", "payment_received", "2023-11-18", "500.00", fee=fee_for("500.00", "USD", "in"),
           name="Rose City Brewing Co.", email="ap@rosecitybrewing.com", desc="Holiday taproom event photos"),
        tx("P2302", "payment_received", "2023-12-27", "1400.00", fee=fee_for("1400.00", "USD", "in"),
           name="Willamette Weddings", email="books@willametteweddings.com", desc="Deposit - Price/Okoro wedding (Dec 9)"),
        tx("P2303", "withdrawal", "2023-12-29", "1200.00", destination="OnPoint Community CU ····9012",
           desc="Transfer to bank", category="personal", source="PayPal balance"),
        tx("P01", "payment_received", "2024-03-02", "85.00", name="Marcus Webb", email="mwebb.pdx@gmail.com",
           desc="Blazers tickets - my half", category="personal"),
        tx("P02", "payment_sent", "2024-04-11", "349.00", name="B&H Photo", email="orders@bhphotovideo.com",
           desc="Godox AD200 Pro flash", category="goods", source="Visa ····6610"),
        tx("P03", "refund", "2024-04-25", "59.99", name="B&H Photo", email="orders@bhphotovideo.com",
           desc="Refund - returned light stand", category="goods"),
        tx("P04", "withdrawal", "2024-02-20", "1500.00", destination="OnPoint Community CU ····9012",
           desc="Transfer to bank", category="personal", source="PayPal balance"),
        tx("P05", "payment_sent", "2024-06-10", "450.00", name="Two Men and a Truck - Portland",
           email="portland@twomenandatruck.com", desc="Moving deposit (load-out Jun 15)", category="services",
           source="PayPal balance"),
        tx("P06", "withdrawal", "2024-07-15", "2000.00", destination="Golden 1 Credit Union ····4471",
           desc="Transfer to bank", category="personal", source="PayPal balance"),
        tx("P07", "payment_received", "2024-08-24", "400.00", name="Leah Hartley", email=LEAH[1],
           desc="My half of the movers", category="personal"),
        tx("P08", "payment_sent", "2024-10-02", "54.99", name="Adobe", email="billing@adobe.com",
           desc="Lightroom plan - annual renewal", category="services", source="Visa ····6610"),
        tx("P09", "withdrawal", "2024-10-20", "1800.00", destination="Golden 1 Credit Union ····4471",
           desc="Transfer to bank", category="personal", source="PayPal balance"),
        tx("P10", "payment_received", "2024-11-29", "62.40", name="Leah Hartley", email=LEAH[1],
           desc="Thanksgiving groceries", category="personal"),
        tx("P11", "payment_sent", "2024-12-20", "45.00", name="Gloria Reyes", email=GLORIA_PERSONAL,
           desc="Tamales for the posada - thank you!", category="personal", source="PayPal balance"),
        tx("P12", "request_sent", "2024-12-30", "540.00", name="Fair Oaks Realty", email="admin@fairoaksrealty.com",
           desc="Listing photos - 3 properties", category="services", status="pending"),
        tx("P13", "payment_received", "2025-01-24", "640.00", fee=fee_for("640.00", "USD", "in"),
           name="Delta Vine Winery", email="events@deltavinewinery.com", desc="Winter release shoot"),
        tx("P14", "withdrawal", "2025-01-31", "1500.00", destination="Golden 1 Credit Union ····4471",
           desc="Transfer to bank", category="personal", source="PayPal balance"),
        tx("P15", "payment_received", "2025-03-08", "700.00", currency="CAD", fee=fee_for("700.00", "CAD", "in"),
           name="Northbound Media Inc.", email="payables@northboundmedia.ca", desc="Spring issue NB-0325, paid in CAD"),
        tx("P16", "payment_received", "2025-02-15", "38.00", name="Marcus Webb", email="mwebb.pdx@gmail.com",
           desc="Pizza", category="personal"),
        tx("P17", "payment_sent", "2025-04-05", "129.95", name="B&H Photo", email="orders@bhphotovideo.com",
           desc="Peak Design strap + SD cards", category="goods", source="Visa ····6610"),
    ]
    t += noise
    t.sort(key=lambda x: x["date"], reverse=True)

    def contact(cid, name, email, fav=False):
        return {"id": cid, "name": name, "email": email, "avatar": avatar(name)}

    contacts = [
        contact("c_1", "Leah Hartley", LEAH[1], True),
        contact("c_2", "Gloria Reyes", GLORIA_PERSONAL, True),
        contact("c_3", "Reyes Tax Services", FEE_PAYPAL),
        contact("c_4", "Marcus Webb", "mwebb.pdx@gmail.com", True),
        contact("c_5", "Northbound Media Inc.", "payables@northboundmedia.ca"),
        contact("c_6", "Tower Bridge Events", "billing@towerbridgeevents.com"),
        contact("c_7", "Hawthorne Family Dental", "office@hawthornedental.com"),
        contact("c_8", "Delta Vine Winery", "events@deltavinewinery.com"),
        contact("c_9", "B&H Photo", "orders@bhphotovideo.com"),
        contact("c_10", "Two Men and a Truck - Portland", "portland@twomenandatruck.com"),
    ]
    return {
        "user": {"id": "u_1", "name": "Daniel Hartley", "email": DANIEL[1], "balance": 2416.85, "currency": "USD",
                 "avatar": avatar("Daniel Hartley")},
        "contacts": contacts,
        "transactions": t,
        "paymentMethods": [
            {"id": "pm_1", "type": "bank", "brand": "", "bankName": "Golden 1 Credit Union", "last4": "4471",
             "expiry": "", "verified": True},
            {"id": "pm_2", "type": "card", "brand": "Visa", "bankName": "", "last4": "6610", "expiry": "08/27",
             "verified": True},
        ],
        "invoices": [],
        "notifications": [
            {"id": "n_1", "message": "Northbound Media Inc. sent you CA$700.00", "read": True, "date": ts("2025-03-08")},
            {"id": "n_2", "message": "Your 2024 tax information: PayPal doesn't issue a 1099-K for your 2024 activity. "
                                     "Your transaction history is in Activity.", "read": False,
             "date": "2025-01-31T17:00:00.000Z"},
        ],
        "subscriptions": [],
        "paymentLinks": [],
        "settings": {"language": "en", "timezone": "America/Los_Angeles", "emailNotifications": True,
                     "pushNotifications": True, "marketingEmails": False, "autoAcceptPayments": True,
                     "defaultCurrency": "USD", "twoStepVerification": True},
    }


# ---------------------------------------------------------------- the arithmetic
def freelance_rows(start=RESIDENCY_START, fx="fallback", include_camera=False, fx_op="divide", fees=True):
    rows = []
    for key, day, kind, name, email, desc, amount, cur in CLIENT_TX:
        if kind == "refund":
            usd = -Decimal(amount)
        else:
            net = Decimal(amount) - (fee_for(amount, cur, kind) if fees else 0)
            if cur == "CAD":
                r = Decimal(str(rate_for(day, fx)))
                usd = cents(net / r) if fx_op == "divide" else cents(net * r)
            else:
                usd = net
        period = "oregon" if dt.date.fromisoformat(day) < start else "california"
        rows.append({"key": key, "date": day, "payer": name, "usd_amount": m(usd), "period": period})
    if include_camera:
        k, day, name, *_rest, amount = CAMERA
        usd = Decimal(amount) - fee_for(amount, "USD", "in")
        rows.append({"key": k, "date": day, "payer": name, "usd_amount": m(usd),
                     "period": "oregon" if dt.date.fromisoformat(day) < start else "california"})
    rows.sort(key=lambda r: r["date"])
    return rows


def oregon_days(start):
    return (start - dt.date(2024, 1, 1)).days


def interest_share(start=RESIDENCY_START, year_days=DAYS_IN_2024):
    return cents(Decimal(WVCU_INT[1]) * oregon_days(start) / year_days)


def numbers(start=RESIDENCY_START, fx="fallback", include_camera=False, fx_op="divide", year_days=DAYS_IN_2024,
            fees=True):
    rows = freelance_rows(start, fx, include_camera, fx_op, fees)
    total = sum(Decimal(r["usd_amount"]) for r in rows)
    oregon = sum(Decimal(r["usd_amount"]) for r in rows if r["period"] == "oregon")
    share = interest_share(start, year_days)
    sub = Decimal(CASCADE["wages"]) + share + oregon
    return {"rows": rows, "freelance_total": total, "freelance_oregon": oregon, "interest_share": share,
            "subtraction": sub}


GOLD = numbers()
# Federal AGI as Gloria's software computed it (Schedule C net = PayPal photography net; half SE tax deducted).
SE_HALF = cents(GOLD["freelance_total"] * Decimal("0.9235") * Decimal("0.153") / 2)
WAGES_FINAL = Decimal(LEAH_W2C_WAGES) + Decimal(CASCADE["wages"]) + Decimal(SIERRA["wages"])
INTEREST_ALL = Decimal(LEAH_INT[1]) + Decimal(WVCU_INT[1]) + Decimal(SAFE_INT[1])
AGI_FINAL = cents(WAGES_FINAL + INTEREST_ALL + GOLD["freelance_total"] - SE_HALF)
AGI_DRAFT = cents(AGI_FINAL + Decimal(LEAH_W2["wages"]) - Decimal(LEAH_W2C_WAGES) - Decimal(SAFE_INT[1]))

FEE_V1 = {"base": 240, "part_year": 85, "sched_c": 95, "extra_w2": 15, "discount": Decimal("0.10")}
FEE_V2 = {**FEE_V1, "part_year": 120, "discount": Decimal("0.15")}


def fee(card):
    gross = Decimal(card["base"] + card["part_year"] + card["sched_c"] + card["extra_w2"] * 1)
    return cents(gross * (1 - card["discount"]))


FEE_OK = fee(FEE_V2)       # 399.50
FEE_OLD = fee(FEE_V1)      # 391.50


# ---------------------------------------------------------------- CalFile tax calculator (port of taxCalculator.js)
JOINT = [(0, 20824, 0.01), (20825, 49368, 0.02), (49369, 77918, 0.04), (77919, 108162, 0.06), (108163, 136700, 0.08),
         (136701, 698274, 0.093), (698275, 837922, 0.103), (837923, 1396542, 0.113), (1396543, math.inf, 0.123)]
SINGLE = [(0, 10412, 0.01), (10413, 24684, 0.02), (24685, 38959, 0.04), (38960, 54081, 0.06), (54082, 68350, 0.08),
          (68351, 349137, 0.093), (349138, 418961, 0.103), (418962, 698271, 0.113), (698272, math.inf, 0.123)]
STD = {"single": 5540, "married_joint": 11080, "married_separate": 5540, "head_of_household": 11080,
       "qualifying_widow": 11080}


def num(v):
    try:
        x = float(v)
        return 0.0 if math.isnan(x) else x
    except (TypeError, ValueError):
        return 0.0


def js_round2(x):
    return math.floor(x * 100 + 0.5) / 100


def calculate(state):
    inc, ded, cr, pi = state["income"], state["deductions"], state["credits"], state["personalInfo"]
    total_income = (sum(num(w["wages"]) for w in inc["w2s"]) + sum(num(i["amount"]) for i in inc["interest1099"])
                    + sum(num(d.get("ordinaryDividends")) for d in inc["dividend1099"])
                    + sum(num(o["amount"]) for o in inc["otherIncome"]))
    fed = num(inc["federalAgi"]) or total_income
    agi = fed - num(ded["caAdjustmentsSubtraction"]) + num(ded["caAdjustmentsAddition"])
    fs = pi["filingStatus"]
    if ded["type"] == "itemized":
        it = ded["itemized"]
        total_ded = (num(it["medicalExpenses"]) + num(it["stateLocalTaxes"]) + num(it["mortgageInterest"])
                     + num(it["charitableContributions"]) + num(it["otherDeductions"]))
    else:
        total_ded = STD.get(fs, 0)
    taxable = max(0, agi - total_ded)
    tax = 0.0
    if taxable > 0:
        for lo, hi, rate in (JOINT if fs in ("married_joint", "qualifying_widow") else SINGLE):
            if taxable <= lo:
                break
            part = min(taxable, hi) - lo
            if part > 0:
                tax += part * rate
        tax = js_round2(tax)
    exemptions = 149 + (149 if fs == "married_joint" else 0) + len(state["dependents"]) * 461
    nonref = 0.0
    for k in ("rentersCredit", "childDependentCare", "seniorHeadOfHousehold", "jointCustodyHeadOfHousehold",
              "dependentParent"):
        if cr[k]["eligible"]:
            nonref += num(cr[k]["amount"])
    nonref += sum(num(c["amount"]) for c in cr["otherCredits"])
    refundable = num(cr["calEitc"]["amount"]) if cr["calEitc"]["eligible"] else 0.0
    after_ex = max(0, tax - exemptions)
    after_nonref = max(0, after_ex - nonref)
    net = after_nonref - refundable
    withholdings = sum(num(w["stateWithheld"]) for w in inc["w2s"])
    est = num(state["payment"].get("estimatedPayments"))
    total_payments = withholdings + est
    contribs = sum(num(c.get("amount")) for c in ded.get("voluntaryContributions", []))
    diff = total_payments - net
    over_before = max(0, diff)
    owed_before = max(0, -diff)
    refund = max(0, over_before - contribs)
    owed = owed_before + max(0, contribs - over_before)
    return {"totalIncome": total_income, "adjustedGrossIncome": agi, "totalDeductions": total_ded,
            "taxableIncome": taxable, "taxBeforeCredits": tax, "exemptionCredits": exemptions,
            "totalNonrefundableCredits": nonref, "totalRefundableCredits": refundable, "netTax": max(0, net),
            "totalWithholdings": withholdings, "estimatedPayments": est, "totalPayments": total_payments,
            "overpayment": refund, "amountOwed": owed, "refundAmount": refund}


# ---------------------------------------------------------------- CalFile seed
def build_calfile():
    s = {
        "taxReturn": {"id": "CA540-2024-HRT0418", "taxYear": 2024, "status": "in_progress",
                      "createdAt": "2025-01-26T04:12:00.000Z", "updatedAt": "2025-01-26T05:03:00.000Z",
                      "confirmationNumber": None},
        "personalInfo": {
            "filingStatus": "married_joint", "firstName": "Leah", "middleInitial": "M", "lastName": "Hartley",
            "suffix": "", "ssn": "561047742", "dateOfBirth": "1991-02-27", "spouseFirstName": "Daniel",
            "spouseMiddleInitial": "J", "spouseLastName": "Hartley", "spouseSsn": "540883318",
            "spouseDateOfBirth": "1989-10-03",
            "address": {"street": "2715 J Street", "apt": "Apt 4", "city": "Sacramento", "state": "CA", "zip": "95816"},
            "phone": "(916) 555-0142", "email": LEAH[1]},
        "dependents": [],
        "income": {
            "w2s": [{"id": 1001, "employerName": LEAH_W2["employer"], "employerEin": LEAH_W2["ein"],
                     "wages": LEAH_W2["wages"], "federalWithheld": LEAH_W2["fed"],
                     "stateWages": LEAH_W2["state_wages"], "stateWithheld": LEAH_W2["state_wh"]}],
            "interest1099": [{"id": 2001, "payerName": LEAH_INT[0], "amount": LEAH_INT[1]}],
            "dividend1099": [], "otherIncome": [], "federalAgi": ""},
        "deductions": {"type": "standard", "standardAmount": 11080,
                       "itemized": {"medicalExpenses": 0, "stateLocalTaxes": 0, "mortgageInterest": 0,
                                    "charitableContributions": 0, "otherDeductions": 0},
                       "caAdjustmentsSubtraction": 0, "caAdjustmentsAddition": 0, "voluntaryContributions": []},
        "credits": {"calEitc": {"eligible": False, "amount": 0},
                    "childDependentCare": {"eligible": False, "expenses": 0, "amount": 0},
                    "rentersCredit": {"eligible": False, "amount": 0},
                    "seniorHeadOfHousehold": {"eligible": False, "amount": 0},
                    "jointCustodyHeadOfHousehold": {"eligible": False, "amount": 0},
                    "dependentParent": {"eligible": False, "amount": 0}, "otherCredits": []},
        "calculations": {},
        "payment": {"refundMethod": "direct_deposit", "bankRoutingNumber": "", "bankAccountNumber": "",
                    "accountType": "", "paymentMethod": "", "paymentDate": "", "estimatedPayments": "",
                    "webPaySubmissions": []},
        "formProgress": {"currentStep": 3, "completedSteps": ["personal-info", "dependents"], "stepErrors": {}},
        "ui": {"currentView": "filing", "showValidationErrors": False, "isSaving": False, "showConfirmDialog": False,
               "activeTooltip": None, "signatureAgreed": False, "signatureDate": "", "email": LEAH[1],
               "phone": "(916) 555-0142", "twoFAEnabled": True, "paperlessNotices": True,
               "messages": [
                   {"id": "M101", "date": "2025-01-14", "from": "FTB Web Pay",
                    "subject": "Payment received: Estimated tax payment",
                    "preview": "We received your Web Pay payment of $450.00 scheduled for 01/14/2025...",
                    "body": "We received your Web Pay payment of $450.00 scheduled for 01/14/2025 from the checking "
                            "account ending 4471. Payment type: Estimated tax payment. Keep your confirmation email "
                            "for your records.", "read": True},
                   {"id": "M102", "date": "2025-02-03", "from": "FTB Taxpayer Services",
                    "subject": "Filing season is open: file your 2024 return free with CalFile",
                    "preview": "CalFile is open for tax year 2024. Most returns are processed within...",
                    "body": "CalFile is open for tax year 2024. Most returns are processed within 2-3 weeks. "
                            "Returns and payments are due April 15, 2025.", "read": True},
                   {"id": "M103", "date": "2025-04-01", "from": "FTB Web Pay",
                    "subject": "Payment received: Estimated tax payment",
                    "preview": "We received your Web Pay payment of $200.00 scheduled for 04/01/2025...",
                    "body": "We received your Web Pay payment of $200.00 scheduled for 04/01/2025 from the checking "
                            "account ending 4471. Payment type: Estimated tax payment.", "read": False},
               ],
               "lastDownloadedForm": None, "contactMessages": [],
               "priorReturns": [
                   {"year": 2023, "form": "540", "status": "Submitted", "filedDate": "2024-04-12", "refund": 0,
                    "owed": 124.00},
                   {"year": 2022, "form": "540", "status": "Submitted", "filedDate": "2023-03-30", "refund": 211.00},
               ]},
        "meta": {"lastSavedAt": "2025-01-26T05:03:00.000Z", "sessionExpiresAt": None},
    }
    # Leah's own Web Pay history (the Sept 12 payment is one of MyFTB's built-in rows).
    for i, (day, year, inst, amount, (atype, last4)) in enumerate(ESTIMATES):
        if day == "2024-09-12":
            continue
        s["payment"]["webPaySubmissions"].append(
            {"id": f"PAY-{hashlib.md5(day.encode()).hexdigest()[:9].upper()}", "type": "estimated",
             "amount": float(amount), "date": day, "status": "processed", "accountType": atype, "lastFour": last4,
             "submittedAt": f"{day}T17:30:00.000Z"})
    s["calculations"] = calculate(s)
    return s


# ---------------------------------------------------------------- Gmail
def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def email(eid, sender, subject, body, ts_, *, to=(DANIEL,), cc=(), read=True, category="primary", attachments=None,
          thread=None, folder="inbox", starred=False):
    snippet = body.replace("<p>", "").replace("</p>", " ").replace("<br>", " ")
    return {"id": eid, "threadId": thread or f"t_{eid}",
            "from": {"name": sender[0], "email": sender[1], "avatar": avatar(sender[0])},
            "to": [{"name": n, "email": e} for n, e in to], "cc": [{"name": n, "email": e} for n, e in cc], "bcc": [],
            "subject": subject, "body": body, "snippet": snippet[:110], "timestamp": ts_, "read": read,
            "starred": starred, "important": False, "labels": [], "category": category, "folder": folder,
            "attachments": attachments or []}


def att(files: Path, aid, name):
    size = (files / "gmail" / name).stat().st_size
    return {"id": aid, "name": name, "size": f"{max(1, size // 1024)} KB", "type": "application/pdf",
            "url": file_url(name)}


def build_gmail(files: Path):
    est_lines = "<br>".join(
        f"Confirmation {hashlib.md5(('c' + d).encode()).hexdigest()[:10].upper()} - Tax year {y} - Estimated tax "
        f"payment (Form 540-ES), installment {i} - ${a} - paid {d[5:7]}/{d[8:]}/{d[:4]} from "
        f"{acct[0]} ...{acct[1]}"
        for d, y, i, a, acct in ESTIMATES)
    rules = p(
        "Hi Daniel and Leah,",
        f"Your federal return was accepted on April 2. Final federal AGI (Form 1040, line 11) is "
        f"<b>${commas(AGI_FINAL)}</b>. Please use this one and not the draft figure from March, which I ran before "
        "Leah's W-2c and Daniel's SAFE 1099 came in.",
        "CalFile only takes the regular 540, so here is how I want the California return finished in Leah's "
        "account so that only Daniel's Oregon-period income is left out of California:",
        "1. Residency date. Daniel became a California resident on the commencement date of your J Street lease "
        "(it's in the lease the property manager emailed you), not the day he left Portland. Everything dated "
        "before that day is his Oregon period; that day and later is California.",
        "2. W-2s. Enter every W-2 as issued: box 1 wages and box 2 federal withholding, and in the state columns "
        "only the California line (box 15 shows CA). If a W-2 has no California line, put 0 for state wages and "
        "state withholding; Oregon withholding doesn't go on the California return. Leah's W-2 needs the corrected "
        "figures from her W-2c.",
        "3. Interest. Enter every 1099-INT at its full box 1 amount. The Willamette Valley CU interest accrued "
        "evenly all year, so its Oregon share is box 1 x (Daniel's Oregon-period days / the number of days in "
        "2024), rounded to the cent. The SAFE account was opened after the move, so none of it is Oregon-period.",
        "4. Photography. Add one Other Income line for Daniel's 2024 photography income: every completed PayPal "
        "payment from a photography client dated in 2024, at the net amount after PayPal's fee, minus the refunds "
        "Daniel sent clients in 2024. Leave out personal transfers and the camera body he sold. "
        "Dan's PayPal activity only shows gross amounts, so take the fee off yourself at the rate PayPal charged "
        "him in 2024: 3.49% + $0.49 per US-dollar payment and 4.99% + CA$0.59 per Canadian-dollar payment, each "
        "fee rounded to the cent (refunds he sent carry no fee). For Canadian-dollar payments take the fee off in "
        "CAD first, then convert the net to USD with the Bank of Canada USD/CAD rate (Canadian dollars per US "
        "dollar) for the date the payment came in; if no rate was published that day, use the last rate "
        "published before it. Round each converted payment to the cent before adding anything up. Payments and "
        "refunds dated before the residency date are Oregon-period.",
        "5. Schedule CA subtraction. On the Deductions page, enter as the California subtraction the total of "
        "Daniel's Oregon-period income: his Cascade Outfitters wages (box 1), the Oregon share of the Willamette "
        "Valley interest, and his Oregon-period photography net. Keep the standard deduction and leave the "
        "addition at 0.",
        "6. Estimated payments. Enter only the 540-ES payments made for tax year 2024. The January 2025 fourth "
        "installment counts; the January 2024 payment (that was for 2023) and anything for 2025 don't.",
        "7. Everything to the cent, please, no rounding to whole dollars.",
        "Once it's submitted, pay the balance due with Web Pay as a tax-due payment dated April 15, then send me "
        "the CalFile confirmation number so I can attach it to your file. My invoice is the fee card from January.",
        "Thanks!<br>Gloria")
    emails = [
        email("g01", ("Capitol Row Property Mgmt", "leasing@capitolrowpm.com"), "Executed lease - 2715 J Street #4",
              p("Hi Leah and Daniel,", "Attached is your fully executed lease for 2715 J Street, Apt 4. Keys will be "
                "ready for pickup at our office on the commencement date. Welcome to Midtown!",
                "Capitol Row Property Management"),
              "2024-06-05T22:40:00Z", to=(DANIEL, LEAH), attachments=[att(files, "a_g01", "Lease_2715J_Unit4.pdf")]),
        email("g02", ("Cascade Outfitters Payroll", "payroll@cascadeoutfitters.com"), "Your 2024 Form W-2",
              p("Hello Daniel,", "As a former employee, your 2024 Form W-2 is attached. Contact payroll@cascadeoutfitters.com "
                "with any questions.", "Cascade Outfitters Supply Co. Payroll"),
              "2025-01-24T17:05:00Z", attachments=[att(files, "a_g02", "W2_2024_Cascade_Outfitters.pdf")]),
        email("g03", ("Sierra Ridge People Team", "people@sierraridge-eng.com"), "2024 W-2 now available",
              p("Hi Daniel,", "Your 2024 W-2 is attached and also available in the employee portal.",
                "Sierra Ridge Engineering - People Team"),
              "2025-01-29T18:20:00Z", attachments=[att(files, "a_g03", "W2_2024_SierraRidge.pdf")]),
        email("g04", ("Willamette Valley CU", "statements@wvcu.org"), "Your 2024 tax documents",
              p("Dear Daniel Hartley,", "Your 2024 Form 1099-INT for share savings ending 5520 is attached.",
                "Willamette Valley Credit Union"),
              "2025-01-30T15:00:00Z", attachments=[att(files, "a_g04", "1099-INT_2024_WVCU.pdf")]),
        email("g05", ("SAFE Credit Union", "estatements@safecu.org"), "Tax form 1099-INT is ready",
              p("Hi Daniel,", "Your 2024 1099-INT for Money Market ending 0193 is attached.", "SAFE Credit Union"),
              "2025-02-01T16:30:00Z", attachments=[att(files, "a_g05", "1099-INT_2024_SAFE.pdf")]),
        email("g06", GLORIA, "2025 tax season - engagement letter and fees",
              p("Hi Daniel and Leah,", "Happy to do your 2024 returns again. Here's my fee card for this season:",
                f"Joint federal + California return: ${FEE_V1['base']}<br>Part-year resident allocation (CA): "
                f"${FEE_V1['part_year']}<br>Schedule C (self-employment): ${FEE_V1['sched_c']}<br>Each W-2 employer "
                f"beyond two: ${FEE_V1['extra_w2']}<br>Returning clients: 10% off the total",
                "Since I did Leah's 2023 return you count as returning clients. Please pay once the state return is "
                f"filed, through PayPal to my business account {FEE_PAYPAL}. Please don't send it to my personal "
                "PayPal; that one is for family stuff.", "Gloria"),
              "2025-01-27T19:10:00Z", to=(DANIEL, LEAH), thread="t_fee"),
        email("g07", GLORIA, "Re: 2025 tax season - engagement letter and fees",
              p("Sorry, I pasted last season's card. For this season the part-year resident allocation is $120 and "
                "the returning-client discount is 15%. Everything else on the card is unchanged.", "Gloria"),
              "2025-01-28T16:45:00Z", to=(DANIEL, LEAH), thread="t_fee"),
        email("g08", LEAH, "Fwd: Corrected W-2 (W-2c) from Capitol Health",
              p("HR sent this, it's the 401(k) mix-up. I already typed my original W-2 into CalFile back in January, "
                "so that one needs fixing.", "L",
                "---------- Forwarded message ----------<br>From: Capitol Health Partners Payroll<br>"
                "Subject: Form W-2c for tax year 2024", "Please find your corrected 2024 wage statement attached."),
              "2025-02-12T03:22:00Z", attachments=[att(files, "a_g08", "W2c_2024_CapitolHealth.pdf")]),
        email("g09", LEAH, "FTB Web Pay receipts",
              p("Gloria asked for these. Here are all my Web Pay confirmations since last January, copied out of my "
                "email:", est_lines,
                f"For whatever we end up owing, pay from our joint Golden 1 checking: routing {BANK['routing']}, "
                f"account {BANK['account']}. Not my old savings ending 2290, I'm closing it.", "L"),
              "2025-04-03T02:05:00Z"),
        email("g10", DANIEL, "Docs for our 2024 return",
              p("Hi Gloria,", "Attaching what I've got: both W-2s, the two 1099-INTs, and the lease. I moved down to "
                "Sacramento on June 15. All my photography money goes through PayPal, a few of the Northbound jobs "
                "paid in Canadian dollars.", "Dan"),
              "2025-03-05T05:40:00Z", to=(GLORIA,), folder="sent", read=True),
        email("g11", GLORIA, "Draft federal numbers",
              p("Hi both,", f"Quick heads-up while I finish the federal: draft AGI is coming out around "
                f"${commas(AGI_DRAFT)}. I'll send the final once it's accepted.", "Gloria"),
              "2025-03-18T20:30:00Z", to=(DANIEL, LEAH)),
        email("g12", GLORIA, "Federal accepted - please finish CalFile", rules, "2025-04-02T23:55:00Z",
              to=(DANIEL, LEAH), read=False, starred=True),
        # ---- noise
        email("n01", ("Northbound Media Inc.", "payables@northboundmedia.ca"), "Remittance advice NB-1224",
              p("Payment of CA$480.00 for invoice NB-1224 (holiday spread) was sent via PayPal. Thanks Daniel!",
                "Northbound Media Accounts Payable"), "2024-12-28T18:02:00Z"),
        email("n02", ("Delta Vine Winery", "events@deltavinewinery.com"), "Harvest photos are a hit",
              p("Daniel, the harvest set is all over our Instagram. Let's talk about a winter release shoot in January.",
                "Marisol"), "2024-11-19T21:15:00Z"),
        email("n03", ("B&H Photo", "deals@bhphotovideo.com"), "Spring Savings Event: up to 30% off lenses",
              p("Save on mirrorless lenses, lighting and more through April 30."), "2025-04-08T14:00:00Z",
              category="promotions", read=False),
        email("n04", ("Franchise Tax Board", "e-updates@ftb.ca.gov"), "Tax Day is April 15",
              p("File and pay by April 15, 2025. CalFile and Web Pay are free. If you can't file by April 15 you have "
                "an automatic extension to file, but not to pay."), "2025-04-07T16:00:00Z", category="promotions"),
        email("n05", ("PayPal", "service@paypal.com"), "You've got money",
              p("Northbound Media Inc. sent you CA$700.00 CAD."), "2025-03-08T20:12:00Z", category="social"),
        email("n06", ("Marcus Webb", "mwebb.pdx@gmail.com"), "Portland trip in May?",
              p("Dan - Blazers are done but we're doing the Timbers home opener. You and Leah in?"),
              "2025-04-06T01:30:00Z", read=False),
        email("n07", ("Tower Bridge Events", "billing@towerbridgeevents.com"), "Re: Gala gallery delivery",
              p("Thanks for the partial refund, totally understand the delay. We'd love you back for the spring mixer."),
              "2024-10-05T22:00:00Z"),
        email("n08", ("Strava", "no-reply@strava.com"), "Your March in review", p("You rode 212 km in March."),
              "2025-04-01T13:00:00Z", category="social"),
        email("n09", ("Fair Oaks Realty", "admin@fairoaksrealty.com"), "Re: Listing photos invoice",
              p("Hi Daniel, sorry for the delay, the brokerage changed bookkeepers. We'll sort out the December "
                "listing photos request soon."), "2025-02-26T19:45:00Z"),
        email("n10", ("Adobe", "mail@adobe.com"), "Your Lightroom plan renews soon", p("Your annual plan renews on 10/02."),
              "2025-03-20T12:00:00Z", category="promotions"),
        email("n11", LEAH, "dinner sat?", p("my parents want to do dinner in Davis on Saturday, ok?"),
              "2025-04-09T23:10:00Z", read=False),
        email("n12", ("Northbound Media Inc.", "payables@northboundmedia.ca"), "Remittance advice NB-0924",
              p("Payment of CA$900.00 for invoice NB-0924 (fall issue) was sent via PayPal on Labour Day.",
                "Northbound Media Accounts Payable"), "2024-09-02T17:40:00Z"),
        email("n13", ("Sacramento Public Library", "noreply@saclibrary.org"), "Items due soon",
              p("2 items are due on 04/14/2025."), "2025-04-09T15:00:00Z", category="promotions"),
    ]
    emails.sort(key=lambda e: e["timestamp"], reverse=True)
    return {
        "user": {"userId": "u1", "username": DANIEL[0], "email": DANIEL[1], "avatar": avatar(DANIEL[0])},
        "emails": emails,
        "labels": [{"id": "l1", "name": "Taxes", "color": "#eab308"}, {"id": "l2", "name": "Clients", "color": "#3b82f6"},
                   {"id": "l3", "name": "Home", "color": "#22c55e"}],
        "drafts": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True,
                     "use24Hour": False},
    }


# ---------------------------------------------------------------- applying a run
def run_calfile(seed, *, leah_wages, cascade_state_wh, other_income, agi, subtraction, estimates, submit=True,
                pay=True, pay_amount=None, pay_date="2025-04-15", pay_account=BANK, conf="CA-M8XK2Q1A-H7T4PZ"):
    s = copy.deepcopy(seed)
    inc = s["income"]
    inc["w2s"][0].update(wages=leah_wages, stateWages=leah_wages)
    inc["w2s"].append({"id": 1744300100001, "employerName": CASCADE["employer"], "employerEin": CASCADE["ein"],
                       "wages": CASCADE["wages"], "federalWithheld": CASCADE["fed"],
                       "stateWages": "0.00" if cascade_state_wh == "0.00" else CASCADE["or_wages"],
                       "stateWithheld": cascade_state_wh})
    inc["w2s"].append({"id": 1744300200002, "employerName": SIERRA["employer"], "employerEin": SIERRA["ein"],
                       "wages": SIERRA["wages"], "federalWithheld": SIERRA["fed"], "stateWages": SIERRA["state_wages"],
                       "stateWithheld": SIERRA["state_wh"]})
    inc["interest1099"] += [{"id": 1744300300003, "payerName": WVCU_INT[0], "amount": WVCU_INT[1]},
                            {"id": 1744300300004, "payerName": SAFE_INT[0], "amount": SAFE_INT[1]}]
    inc["otherIncome"].append({"id": 1744300400005, "description": "Hartley Photo - 2024 net photography income",
                               "amount": m(other_income)})
    inc["federalAgi"] = m(agi)
    s["deductions"]["caAdjustmentsSubtraction"] = m(subtraction)
    s["payment"]["estimatedPayments"] = m(estimates)
    calc = calculate(s)
    if calc["amountOwed"] > 0:
        s["payment"]["paymentMethod"] = "electronic"
    elif calc["refundAmount"] > 0:
        s["payment"].update(bankRoutingNumber=pay_account["routing"], bankAccountNumber=pay_account["account"],
                            accountType=pay_account["type"])
    s["calculations"] = calc
    s["formProgress"] = {"currentStep": 8, "completedSteps": ["personal-info", "dependents", "income", "deductions",
                                                             "credits", "tax-summary", "review"], "stepErrors": {}}
    s["taxReturn"]["updatedAt"] = "2025-04-10T17:20:00.000Z"
    if submit:
        s["ui"].update(signatureAgreed=True, signatureDate="2025-04-10")
        s["taxReturn"].update(status="submitted", confirmationNumber=conf, updatedAt="2025-04-10T17:25:00.000Z")
    if pay and calc["amountOwed"] > 0:
        amount = round(calc["amountOwed"], 2) if pay_amount is None else float(pay_amount)
        s["payment"]["webPaySubmissions"].append(
            {"id": "PAY-M8XK9F3B", "type": "tax_due", "amount": amount, "date": pay_date, "status": "pending",
             "accountType": pay_account["type"], "lastFour": pay_account["account"][-4:],
             "submittedAt": "2025-04-10T17:31:00.000Z"})
    return s


def run_paypal(seed, *, recipient=FEE_PAYPAL, amount=FEE_OK):
    s = copy.deepcopy(seed)
    s["transactions"].insert(0, {"id": "k3j9x2a", "type": "payment_sent", "amount": float(amount), "currency": "USD",
                                 "recipientName": recipient, "date": "2025-04-10T17:40:00.000Z",
                                 "status": "completed", "description": "2024 tax prep - Hartley joint return"})
    s["user"]["balance"] = round(s["user"]["balance"] - float(amount), 2)
    return s


def run_gmail(seed, conf, paid):
    s = copy.deepcopy(seed)
    s["emails"].insert(0, {
        "id": "sent_1", "threadId": "t_g12", "from": {"name": DANIEL[0], "email": DANIEL[1], "avatar": avatar(DANIEL[0])},
        "to": [{"name": GLORIA[0], "email": GLORIA[1]}], "cc": [], "bcc": [],
        "subject": "Re: Federal accepted - please finish CalFile",
        "body": f"Hi Gloria, the CalFile return is submitted, confirmation number {conf}. I paid the ${commas(paid)} "
                f"balance with Web Pay dated April 15, and sent your fee through PayPal. Thanks! Dan",
        "snippet": f"Hi Gloria, the CalFile return is submitted, confirmation number {conf}.",
        "timestamp": "2025-04-10T17:45:00.000Z", "read": True, "starred": False, "important": False, "labels": [],
        "category": "primary", "folder": "sent", "attachments": []})
    return s


def csv_rows(rows):
    return [["date", "payer", "usd_amount", "period"]] + [
        [r["date"], r["payer"], r["usd_amount"], r["period"]] for r in rows]


def scenario(seed, *, start=RESIDENCY_START, fx="fallback", fx_op="divide", camera=False, year_days=DAYS_IN_2024, fees=True,
             w2c=True, or_withholding=False, draft_agi=False, all_estimates=False, fee_card=FEE_V2,
             fee_to=FEE_PAYPAL, pay_date="2025-04-15", conf="CA-M8XK2Q1A-H7T4PZ"):
    n = numbers(start, fx, camera, fx_op, year_days, fees)
    cal = run_calfile(seed["california_tax"], leah_wages=LEAH_W2C_WAGES if w2c else LEAH_W2["wages"],
                      cascade_state_wh=CASCADE["or_wh"] if or_withholding else "0.00",
                      other_income=n["freelance_total"], agi=AGI_DRAFT if draft_agi else AGI_FINAL,
                      subtraction=n["subtraction"], estimates=EST_ALL if all_estimates else EST_2024,
                      pay_date=pay_date, conf=conf)
    owed = cal["calculations"]["amountOwed"]
    states = {"california_tax": cal, "paypal": run_paypal(seed["paypal"], recipient=fee_to, amount=fee(fee_card)),
              "gmail": run_gmail(seed["gmail"], conf, owed)}
    return states, csv_rows(n["rows"]), n, owed


# ---------------------------------------------------------------- output
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    files = out / "seed" / "files"
    build_pdfs(files)
    seed = {"california_tax": build_calfile(), "gmail": build_gmail(files), "paypal": build_paypal()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    write_csv(out / "input" / "boc_usdcad_2024.csv",
              [["date", "FXUSDCAD"]] + [[d, f"{r:.4f}"] for d, r in sorted(RATES.items())])

    golden, gold_csv, gold_n, gold_owed = scenario(seed)
    assert gold_owed > 0, "story needs a balance due"
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "photography_2024.csv", gold_csv)

    expected = {
        "clock": CLOCK,
        "residency_start": RESIDENCY_START.isoformat(),
        "oregon_days": oregon_days(RESIDENCY_START), "days_in_year": DAYS_IN_2024,
        "calfile": {
            "w2s": {
                LEAH_W2["employer"]: {"wages": LEAH_W2C_WAGES, "federalWithheld": LEAH_W2["fed"],
                                      "stateWages": LEAH_W2C_WAGES, "stateWithheld": LEAH_W2["state_wh"]},
                CASCADE["employer"]: {"wages": CASCADE["wages"], "federalWithheld": CASCADE["fed"],
                                      "stateWages": "0.00", "stateWithheld": "0.00"},
                SIERRA["employer"]: {"wages": SIERRA["wages"], "federalWithheld": SIERRA["fed"],
                                     "stateWages": SIERRA["state_wages"], "stateWithheld": SIERRA["state_wh"]},
            },
            "interest1099": {LEAH_INT[0]: LEAH_INT[1], WVCU_INT[0]: WVCU_INT[1], SAFE_INT[0]: SAFE_INT[1]},
            "other_income": m(gold_n["freelance_total"]),
            "federal_agi": m(AGI_FINAL), "federal_agi_draft": m(AGI_DRAFT),
            "ca_subtraction": m(gold_n["subtraction"]),
            "subtraction_parts": {"cascade_wages": CASCADE["wages"], "wvcu_oregon_share": m(gold_n["interest_share"]),
                                  "photography_oregon_net": m(gold_n["freelance_oregon"])},
            "estimated_payments": m(EST_2024), "estimated_payments_all": m(EST_ALL),
            "amount_owed": m(gold_owed),
            "webpay": {"type": "tax_due", "amount": m(gold_owed), "date": "2025-04-15", "accountType": "checking",
                       "lastFour": "4471"},
        },
        "paypal": {"fee_recipient": FEE_PAYPAL, "fee_amount": m(FEE_OK), "fee_old_card": m(FEE_OLD),
                   "personal_recipient": GLORIA_PERSONAL},
        "gmail": {"to": GLORIA[1]},
        "photography_rows": {r["date"]: {k: r[k] for k in ("payer", "usd_amount", "period")} for r in gold_n["rows"]},
        "camera_sale_date": CAMERA[1],
        "fees": {CLIENT_TX[i][1]: m(fee_for(CLIENT_TX[i][6], CLIENT_TX[i][7], CLIENT_TX[i][2]))
                 for i in range(len(CLIENT_TX))},
        "rates_used": {day: rate_for(day) for _, day, _, _, _, _, _, cur in CLIENT_TX if cur == "CAD"},
    }
    write_json(out / "expected.json", expected)

    variants = {
        "golden": (golden, gold_csv),
        "nop": (seed, None),
        # every trap: Daniel's own move date, 365-day year, gross amounts, multiplies by the next published rate,
        # keeps the camera sale, Leah's original W-2, Oregon withholding as CA withholding, draft AGI,
        # every Web Pay estimate, old fee card to Gloria's personal PayPal, today's date on Web Pay.
        "naive": scenario(seed, start=NAIVE_MOVE, fx="next", fx_op="multiply", camera=True, year_days=365, fees=False,
                          w2c=False,
                          or_withholding=True, draft_agi=True, all_estimates=True, fee_card=FEE_V1,
                          fee_to=GLORIA_PERSONAL, pay_date="2025-04-10")[:2],
        "slip_move_date": scenario(seed, start=NAIVE_MOVE)[:2],
        "slip_fx_fallback": scenario(seed, fx="next")[:2],
        "slip_w2c": scenario(seed, w2c=False)[:2],
        "slip_estimates": scenario(seed, all_estimates=True)[:2],
        "slip_fee_card": scenario(seed, fee_card=FEE_V1)[:2],
    }
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "photography_2024.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
