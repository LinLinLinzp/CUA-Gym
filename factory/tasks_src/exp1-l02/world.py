#!/usr/bin/env python3
"""World generator for cua-hard/tahoe-offsite-closeout (slot exp1-l02, lever L02).

Nadia Brooks (ops coordinator, Fernbrook Labs) closes out the Lake Tahoe team
offsite expense reports for the controller.  Every decisive amount, date and
card number lives only inside receipt images (Expensify receipts, Gmail
attachments, Airbnb host photos); the typed expense fields disagree with them
in several places.

python3 world.py <out> writes
  seed/<site>.json, seed/files/<site>/<file>    initial state + served images
  golden/<site>.json                            state after a correct run
  golden_output/offsite_closeout.csv            expected deliverable
  expected.json                                 facts for the verifier
  variants/<name>/{state/<site>/*.json,output/} self-check fixtures
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, long_pdf, scan_document  # noqa: E402

CLOCK = "2026-11-16T09:30:00Z"
DOMAIN = "fernbrook.io"
NADIA = "nadia@fernbrook.io"
OWEN = "owen@fernbrook.io"
OUTPUT_CSV = "offsite_closeout.csv"
UPLOAD_PREFIX = "0a1b2c3d"  # stands in for the sitehost's random 8-hex upload prefix

# ====================================================================== images
FILES: dict[str, list[tuple[str, callable]]] = {"expensify": [], "gmail": [], "airbnb": []}


def receipt(site, name, title, lines, seed, stamp=None, width=820):
    FILES[site].append((name, lambda p: scan_document(lines, p, seed=seed, width=width, title=title, stamp=stamp)))
    return name


def phone_shot(site, name, *, brand, color, headline, amount, rows, seed):
    """App-style receipt screenshot (Venmo / Uber / Lyft)."""
    def render(path):
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        rng = random.Random(seed)
        w, h = 720, 1280
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)
        f_s, f_m, f_l, f_xl = (ImageFont.load_default(size=s) for s in (24, 30, 40, 84))
        d.rectangle([0, 0, w, 56], fill="#111111")
        d.text((28, 14), f"{rng.randint(6, 11)}:{rng.randint(10, 59):02d}", fill="white", font=f_s)
        d.text((w - 150, 14), "5G  82%", fill="white", font=f_s)
        d.rectangle([0, 56, w, 176], fill=color)
        d.text((40, 92), brand, fill="white", font=f_l)
        y = 230
        d.text((40, y), headline, fill="#222222", font=f_m)
        y += 70
        d.text((40, y), amount, fill="#111111", font=f_xl)
        y += 140
        for label, value in rows:
            d.line([40, y - 18, w - 40, y - 18], fill="#dddddd", width=2)
            d.text((40, y), label, fill="#777777", font=f_s)
            d.text((40, y + 34), value, fill="#222222", font=f_m)
            y += 104
        img = img.filter(ImageFilter.GaussianBlur(0.4))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        return path
    FILES[site].append((name, render))
    return name


def lone_eagle(site, name, seed):
    return receipt(site, name, "LONE EAGLE GRILLE", [
        "111 Country Club Dr, Incline Village NV",
        "11/05/2026   8:41 PM    Table 22   Guests 8",
        "Server: Alyssa            Check #40117",
        "------------------------------------------",
        "Food                              $262.00",
        "Wine / Bar                         $76.00",
        "Subtotal                          $338.00",
        "Tax 8.25%                          $27.89",
        "Gratuity                           $30.51",
        "TOTAL                             $396.40",
        "------------------------------------------",
        "SPLIT TENDER",
        "VISA  ****7731  K MENSAH          $160.00",
        "MC    ****0552  L FISCHER         $186.40",
        "AMEX  ****1009  FERNBROOK LABS     $50.00",
        "BALANCE DUE                         $0.00",
        "        Thank you - see you on the lake!",
    ], seed=seed)


def eticket(site, name, airline, conf, issued, passenger, legs, fare, taxes, total, card, seed):
    lines = [f"Confirmation code: {conf}", f"Issued: {issued}", f"Passenger: {passenger}", "", "ITINERARY"]
    lines += legs + ["", f"Base fare                     {fare}", f"Taxes & fees                  {taxes}",
                     f"TOTAL CHARGED                 {total}", f"Form of payment: {card}"]
    return receipt(site, name, f"{airline} - eTicket Receipt", lines, seed=seed, width=980)


# Expensify receipts ---------------------------------------------------------
R = {}
R["shuttle"] = receipt("expensify", "rcpt_shuttle_1104.png", "NORTH LAKE TAHOE EXPRESS", [
    "Reno-Tahoe Intl Airport -> Tahoe City", "Date: 11/04/2026   Dep 2:15 PM", "Passenger: D. Ruiz",
    "Shared ride, 1 adult                $58.00", "Booking fee                          $6.00",
    "TOTAL                               $64.00", "VISA ************4417   APPROVED"], seed=11)
R["venmo"] = phone_shot("expensify", "venmo_payment.png", brand="venmo", color="#3d95ce",
                        headline="You paid Michael Brennan", amount="$165.00",
                        rows=[("Date", "Nov 7, 2026 at 10:42 AM"), ("Note", "paddleboard fin - Lakefront house"),
                              ("Paid with", "Venmo balance"), ("Transaction ID", "4129 8830 1157")], seed=12)
R["safeway"] = receipt("expensify", "rcpt_safeway.png", "SAFEWAY  #1734", [
    "850 N Lake Blvd, Tahoe City CA", "11/04/2026  5:52 PM   Lane 4", "PRODUCE                     $48.17",
    "DAIRY / EGGS                $31.62", "BAKERY                      $22.95", "MEAT / DELI                 $64.38",
    "BEVERAGES                   $38.11", "HOUSEHOLD                    $7.25", "SUBTOTAL                   $212.48",
    "TAX                          $0.00", "TOTAL                      $212.48",
    "AMEX  ************1009   CHIP   APPROVED"], seed=13)
R["lone_kofi"] = lone_eagle("expensify", "IMG_3390.png", seed=21)
R["alaska_kofi"] = eticket("expensify", "alaska_eticket_mensah.png", "Alaska Airlines", "MZQ8RT", "Oct 14, 2026",
                           "MENSAH/KOFI", ["AS 3412  SFO -> RNO   Tue Nov 03 2026  6:05 PM",
                                           "AS 3417  RNO -> SFO   Sat Nov 07 2026  9:20 AM"],
                           "$188.84", "$42.76", "$231.60", "VISA ****7731", seed=22)
R["lone_leo"] = lone_eagle("expensify", "dinner_split_photo.png", seed=31)
R["hertz_est"] = receipt("expensify", "hertz_rental_record.png", "HERTZ  RENTAL RECORD", [
    "Location: RNO Reno-Tahoe Intl   Agreement 77-4410982", "Renter: FISCHER, LEO",
    "Vehicle: Full-size SUV  (Ford Explorer)", "Pickup: 11/04/2026 1:40 PM   Return: 11/07/2026",
    "Time & mileage 3 days x $79.99       $239.97", "Concession recovery fee              $26.88",
    "Vehicle license fee                    $9.42", "Fuel purchase option                  $38.60",
    "Taxes                                 $27.31", "ESTIMATED TOTAL                      $342.18",
    "This is an estimate. Final charges are calculated at return."], seed=32, stamp="ESTIMATE")
R["chevron"] = receipt("expensify", "rcpt_chevron.png", "CHEVRON  #0219", [
    "10900 Stead Blvd, Reno NV", "11/07/2026  12:18 PM   Pump 6", "Regular unleaded   12.140 gal @ $4.794",
    "FUEL TOTAL                         $58.20", "VISA ****8812   APPROVED"], seed=33)
R["kayak"] = receipt("expensify", "rcpt_paddle_oar.png", "TAHOE PADDLE & OAR", [
    "8299 N Lake Blvd, Kings Beach CA", "11/05/2026  10:05 AM", "Half-day kayak rental  x4     $160.00",
    "Half-day SUP rental     x2      $90.00", "Dry bags / waiver fee           $25.00",
    "TOTAL                         $275.00", "AMEX ***********1009", "Thank you!"], seed=41)
R["lyft_ingrid"] = phone_shot("expensify", "lyft_ride_1104.png", brand="lyft", color="#ff00bf",
                              headline="Thanks for riding with Marco", amount="$41.30",
                              rows=[("Date", "Wed, Nov 4, 2026 - 3:05 PM"),
                                    ("Route", "Reno-Tahoe Intl -> Tahoe City, CA"),
                                    ("Payment", "Visa ****2290")], seed=42)
R["firesign"] = receipt("expensify", "rcpt_fire_sign.png", "FIRE SIGN CAFE", [
    "1785 West Lake Blvd, Tahoe City CA", "11/06/2026  8:12 AM   Party of 4", "Breakfast entrees           $61.00",
    "Coffee / juice              $12.50", "Tax                          $5.00", "Tip                          $7.75",
    "TOTAL                       $86.25", "AMEX  ****3005   ENTRY: CONTACTLESS"], seed=43)
R["alaska_tariq"] = eticket("expensify", "alaska_haddad.png", "Alaska Airlines", "QW2LXH", "Oct 12, 2026",
                            "HADDAD/TARIQ", ["AS 2211  SEA -> RNO   Tue Nov 03 2026  4:40 PM",
                                             "AS 2216  RNO -> SEA   Sat Nov 07 2026  1:55 PM"],
                            "$203.52", "$45.38", "$248.90", "MC ****6143", seed=51)
R["marina"] = receipt("expensify", "rcpt_marina_parking.png", "TAHOE CITY MARINA - PARKING", [
    "700 N Lake Blvd, Tahoe City CA", "Entry 11/05/2026 9:31 AM   Exit 11/05/2026 4:48 PM",
    "Day rate                         $24.00", "PAID  VISA ****9024"], seed=52)
R["united_mei"] = eticket("expensify", "united_tanaka.png", "United Airlines", "PL3K9D", "Oct 20, 2026",
                          "TANAKA/MEI", ["UA 5530  LAX -> RNO   Tue Nov 03 2026  2:10 PM",
                                         "UA 5541  RNO -> LAX   Sat Nov 07 2026  11:45 AM"],
                          "$168.37", "$43.93", "$212.30", "VISA ****3318", seed=61)
R["sunnyside"] = receipt("expensify", "rcpt_sunnyside.png", "SUNNYSIDE RESTAURANT & LODGE", [
    "1850 West Lake Blvd, Tahoe City CA", "10/23/2026   7:48 PM   Table 9   Guests 2",
    "Lakeside salmon x2               $78.00", "Bottle - Pinot Noir              $52.00",
    "Dessert                          $14.00", "Tax                               $9.10",
    "Tip                              $11.40", "TOTAL                           $164.50", "VISA ****3318"], seed=62)
UNITED_PRIYA_LINES = ("United Airlines", "HQ4T7N", "Oct 16, 2026", "RAMAN/PRIYA",
                      ["UA 5602  SFO -> RNO   Wed Nov 04 2026  7:30 AM",
                       "UA 5619  RNO -> SFO   Sat Nov 07 2026  5:15 PM"],
                      "$262.70", "$55.50", "$318.20", "VISA ****5071")
R["united_priya_old"] = eticket("expensify", "united_eticket_HQ4T7N.png", *UNITED_PRIYA_LINES, seed=71)
R["united_priya_new"] = eticket("expensify", "IMG_2231.png", *UNITED_PRIYA_LINES, seed=71)
R["lyft_priya"] = phone_shot("expensify", "lyft_ride_1107.png", brand="lyft", color="#ff00bf",
                             headline="Thanks for riding with Dana", amount="$33.10",
                             rows=[("Date", "Sat, Nov 7, 2026 - 3:20 PM"),
                                   ("Route", "Tahoe City, CA -> Reno-Tahoe Intl"),
                                   ("Payment", "Visa ****5071")], seed=72)
R["zuni"] = receipt("expensify", "rcpt_zuni.png", "ZUNI CAFE", [
    "1658 Market St, San Francisco CA", "10/28/2026  12:52 PM   Guests 3", "Lunch                     $118.00",
    "Tax                        $10.18", "Tip                        $14.42", "TOTAL                     $142.60",
    "VISA ****8820"], seed=81)
R["officedepot"] = receipt("expensify", "rcpt_office_depot.png", "OFFICE DEPOT #2291", [
    "2675 Geary Blvd, San Francisco CA", "10/30/2026  4:10 PM", "Name badges (100)           $18.99",
    "Lanyards (25)               $14.49", "Markers / flip chart        $12.64", "TOTAL                       $46.12",
    "VISA ****6620"], seed=82)
R["figma"] = receipt("expensify", "figma_invoice_oct.png", "Figma, Inc. - Invoice", [
    "Invoice #FG-2026-10-4471", "Billing period Oct 1 - Oct 31, 2026", "Professional seats x3   $45.00",
    "TOTAL                   $45.00", "Paid by VISA ****1190"], seed=83)

# Gmail attachments ----------------------------------------------------------
UBER_RIGHT = phone_shot("gmail", "IMG_4471.png", brand="Uber", color="#000000",
                        headline="Thanks for riding, Kofi", amount="$38.75",
                        rows=[("Trip", "Sat, Nov 7, 2026 - 6:12 AM"),
                              ("Route", "Tahoe City, CA -> Reno-Tahoe Intl Airport"),
                              ("Payment", "Visa ****7731")], seed=91)
UBER_WRONG = phone_shot("gmail", "IMG_4466.png", brand="Uber", color="#000000",
                        headline="Thanks for riding, Kofi", amount="$22.40",
                        rows=[("Trip", "Mon, Nov 2, 2026 - 7:48 PM"),
                              ("Route", "Valencia St, San Francisco -> Oakland, CA"),
                              ("Payment", "Visa ****7731")], seed=92)
HERTZ_FINAL = receipt("gmail", "hertz_final_invoice.png", "HERTZ  FINAL INVOICE", [
    "Location: RNO Reno-Tahoe Intl   Agreement 77-4410982", "Renter: FISCHER, LEO",
    "Pickup: 11/04/2026 1:40 PM   Return: 11/07/2026 12:41 PM", "Time & mileage 3 days x $79.99       $239.97",
    "Concession recovery fee              $26.88", "Vehicle license fee                    $9.42",
    "Fuel purchase option   (declined - returned full)   $0.00", "Taxes                                 $47.91",
    "TOTAL CHARGED                        $324.18", "VISA ****8812"], seed=93, stamp="PAID")
AGENDA_PDF = "Tahoe_offsite_agenda.pdf"
FILES["gmail"].append((AGENDA_PDF, lambda p: long_pdf(p, "Fernbrook Labs - Lake Tahoe Offsite", [
    ("Dates", ["Arrivals Tuesday Nov 3 (evening) and Wednesday Nov 4. Sessions Wednesday Nov 4 to Friday Nov 6. "
               "Check-out Saturday Nov 7 by 11am."]),
    ("Lodging", ["Lakefront Modern Retreat with Private Dock, Tahoe City. Booked on Airbnb by Nadia on the company card."]),
    ("Getting there", ["Book your own flights into RNO and expense them on a report tagged Tahoe Offsite 2026."]),
    ("Program", ["Wednesday: roadmap review. Thursday: on the water in the morning, team dinner in the evening. "
                 "Friday: planning workshop and wrap-up."]),
])))

# Airbnb photos --------------------------------------------------------------
HOST_RECEIPT = receipt("airbnb", "receipt_tariq.png", "RECEIPT", [
    "Lakefront Retreat - Tahoe City", "Date:  Nov 7 2026", "Received from:  Tariq H.",
    "", "Late checkout (2 hrs)               $60.00", "Firewood, 3 bundles                 $35.00",
    "--------------------------------------------", "TOTAL PAID IN CASH                  $95.00",
    "", "Thank you!   - Michael Brennan, host"], seed=101, width=760)
BOARD_QUOTE = receipt("airbnb", "board_repair_estimate.png", "TAHOE BOARD WORKS - Repair Estimate", [
    "Customer: Michael Brennan (Lakefront Retreat)", "Date: 11/07/2026",
    "Item: 10'6\" inflatable SUP - cracked center fin + fin box", "Fin box replacement               $110.00",
    "Center fin                          $45.00", "Labor                               $25.00",
    "ESTIMATE TOTAL                     $180.00", "Estimate valid 30 days."], seed=102, width=900)


# ====================================================================== helpers
def iso(day, hm="17:00"):
    return f"{day}T{hm}:00Z"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def dollars(cents: int) -> str:
    return f"{cents / 100:.2f}"


# ====================================================================== expensify
PEOPLE = [
    ("usr_001", "Nadia", "Brooks", "admin", "Operations", None, "EMP-1102"),
    ("usr_002", "Daniela", "Ruiz", "employee", "Design", "usr_001", "EMP-1417"),
    ("usr_003", "Kofi", "Mensah", "employee", "Engineering", "usr_001", "EMP-1420"),
    ("usr_004", "Leo", "Fischer", "employee", "Engineering", "usr_001", "EMP-1433"),
    ("usr_005", "Ingrid", "Halvorsen", "employee", "Product", "usr_001", "EMP-1388"),
    ("usr_006", "Tariq", "Haddad", "employee", "Sales", "usr_001", "EMP-1291"),
    ("usr_007", "Mei", "Tanaka", "employee", "Design", "usr_001", "EMP-1502"),
    ("usr_008", "Priya", "Raman", "employee", "Engineering", "usr_001", "EMP-1511"),
    ("usr_009", "Owen", "Price", "admin", "Finance", None, "EMP-1007"),
    ("usr_010", "Grace", "Liu", "employee", "Product", "usr_001", "EMP-1460"),
    ("usr_011", "Sam", "Whitfield", "employee", "Engineering", "usr_009", "EMP-1222"),
    ("usr_012", "Jonah", "Reyes", "employee", "Sales", "usr_009", "EMP-1345"),
]


def person(uid):
    p = next(p for p in PEOPLE if p[0] == uid)
    return {"id": p[0], "name": f"{p[1]} {p[2]}", "email": f"{p[1].lower()}@{DOMAIN}"}


CATS = [("cat_001", "Travel: Airfare", "6010"), ("cat_002", "Travel: Hotel", "6020"),
        ("cat_003", "Travel: Car Rental", "6030"), ("cat_004", "Travel: Ground Transport", "6040"),
        ("cat_005", "Meals & Entertainment", "6100"), ("cat_006", "Office Supplies", "6200"),
        ("cat_007", "Software & Subscriptions", "6300"), ("cat_008", "Team Events", "6450"),
        ("cat_010", "Mileage", "6600"), ("cat_015", "Miscellaneous", "9999")]
CAT = {cid: name for cid, name, _ in CATS}
TAGS = [("tag_001", "Tahoe Offsite 2026", "OFF-26"), ("tag_002", "Client: Halvorsen Freight", "CL-HF"),
        ("tag_003", "Internal", "INT"), ("tag_004", "Recruiting", "REC"), ("tag_005", "Conference", "CONF")]
TAG = {tid: name for tid, name, _ in TAGS}

# report id -> (creator, title, number, status, submittedTo, submitted, approved, reimbursed, created)
REPORTS = {
    "rpt_101": ("usr_002", "Tahoe offsite - Daniela", 78410231, "submitted", "usr_001", "2026-11-09T18:22:00Z", None, None, "2026-11-09T18:05:00Z"),
    "rpt_102": ("usr_003", "Lake Tahoe offsite (Nov 3-7)", 78410244, "submitted", "usr_001", "2026-11-10T16:40:00Z", None, None, "2026-11-10T16:31:00Z"),
    "rpt_103": ("usr_004", "Offsite Tahoe - travel & meals", 78410257, "submitted", "usr_001", "2026-11-10T21:12:00Z", None, None, "2026-11-10T20:58:00Z"),
    "rpt_104": ("usr_005", "Team offsite - Tahoe City", 78410263, "submitted", "usr_001", "2026-11-11T15:03:00Z", None, None, "2026-11-11T14:47:00Z"),
    "rpt_105": ("usr_006", "Tahoe offsite expenses", 78410278, "submitted", "usr_001", "2026-11-11T19:36:00Z", None, None, "2026-11-11T19:20:00Z"),
    "rpt_106": ("usr_007", "Tahoe offsite", 78410282, "submitted", "usr_001", "2026-11-12T17:15:00Z", None, None, "2026-11-12T17:02:00Z"),
    "rpt_107": ("usr_008", "Tahoe offsite - return flight & rides", 78410296, "submitted", "usr_001", "2026-11-12T22:48:00Z", None, None, "2026-11-12T22:40:00Z"),
    # non-targets
    "rpt_090": ("usr_008", "Tahoe offsite - flights", 78390114, "reimbursed", "usr_001", "2026-10-19T17:00:00Z", "2026-10-20T16:10:00Z", "2026-10-23T15:00:00Z", "2026-10-19T16:45:00Z"),
    "rpt_091": ("usr_010", "Tahoe offsite - mileage", 78410205, "approved", "usr_001", "2026-11-09T15:30:00Z", "2026-11-13T17:20:00Z", None, "2026-11-09T15:12:00Z"),
    "rpt_092": ("usr_006", "Halvorsen Freight lunch - Oct", 78410301, "submitted", "usr_001", "2026-11-12T20:05:00Z", None, None, "2026-11-12T19:58:00Z"),
    "rpt_093": ("usr_012", "Portland client dinner", 78410315, "submitted", "usr_009", "2026-11-13T18:44:00Z", None, None, "2026-11-13T18:30:00Z"),
    "rpt_094": ("usr_011", "Design tooling - October", 78395520, "reimbursed", "usr_009", "2026-11-02T17:00:00Z", "2026-11-03T16:00:00Z", "2026-11-06T15:00:00Z", "2026-11-02T16:40:00Z"),
    "rpt_095": ("usr_001", "Offsite supplies (Nadia)", 78410322, "open", "usr_009", None, None, None, "2026-11-04T03:10:00Z"),
}
TARGETS = ["rpt_101", "rpt_102", "rpt_103", "rpt_104", "rpt_105", "rpt_106", "rpt_107"]
APPROVE = ["rpt_101", "rpt_102", "rpt_103", "rpt_104", "rpt_105"]
REJECT = {"rpt_106": "Sunnyside receipt is dated Oct 23, before the offsite - please remove it and resubmit.",
          "rpt_107": "This United ticket (HQ4T7N) was already reimbursed on your Oct 'Tahoe offsite - flights' report - please remove it and resubmit the Lyft."}

# (id, report, creator, merchant, cents, date, category, description, receipt-file or None)
EXPENSES = [
    ("exp_1011", "rpt_101", "usr_002", "North Lake Tahoe Express", 6400, "2026-11-04", "cat_004", "Airport shuttle RNO to Tahoe City", R["shuttle"]),
    ("exp_1012", "rpt_101", "usr_002", "Michael Brennan (host)", 18000, "2026-11-07", "cat_015", "Paddleboard fin repair - paid host directly", R["venmo"]),
    ("exp_1013", "rpt_101", "usr_002", "Safeway", 21248, "2026-11-04", "cat_008", "Groceries for the house (team breakfasts)", R["safeway"]),
    ("exp_1021", "rpt_102", "usr_003", "Lone Eagle Grille", 39640, "2026-11-05", "cat_005", "Team dinner Thursday - split bill", R["lone_kofi"]),
    ("exp_1022", "rpt_102", "usr_003", "Uber", 3875, "2026-11-07", "cat_004", "Ride to RNO airport", None),
    ("exp_1023", "rpt_102", "usr_003", "Alaska Airlines", 23160, "2026-11-03", "cat_001", "SFO - RNO round trip", R["alaska_kofi"]),
    ("exp_1031", "rpt_103", "usr_004", "Lone Eagle Grille", 18640, "2026-11-05", "cat_005", "Team dinner - my part", R["lone_leo"]),
    ("exp_1032", "rpt_103", "usr_004", "Hertz", 34218, "2026-11-07", "cat_003", "SUV rental Nov 4-7 for the group", R["hertz_est"]),
    ("exp_1033", "rpt_103", "usr_004", "Chevron", 5820, "2026-11-07", "cat_003", "Fuel before returning the rental", R["chevron"]),
    ("exp_1041", "rpt_104", "usr_005", "Tahoe Paddle & Oar", 27500, "2026-11-05", "cat_008", "Kayak + SUP rentals for the team", R["kayak"]),
    ("exp_1042", "rpt_104", "usr_005", "Lyft", 4130, "2026-11-04", "cat_004", "RNO to Tahoe City", R["lyft_ingrid"]),
    ("exp_1043", "rpt_104", "usr_005", "Fire Sign Cafe", 8625, "2026-11-06", "cat_005", "Breakfast with the workshop facilitators", R["firesign"]),
    ("exp_1051", "rpt_105", "usr_006", "Michael Brennan (host)", 12000, "2026-11-07", "cat_015", "Late checkout + firewood (paid host cash)", None),
    ("exp_1052", "rpt_105", "usr_006", "Alaska Airlines", 24890, "2026-11-03", "cat_001", "SEA - RNO round trip", R["alaska_tariq"]),
    ("exp_1053", "rpt_105", "usr_006", "Tahoe City Marina", 2400, "2026-11-05", "cat_004", "Parking at the boat launch", R["marina"]),
    ("exp_1061", "rpt_106", "usr_007", "United Airlines", 21230, "2026-11-03", "cat_001", "LAX - RNO round trip", R["united_mei"]),
    ("exp_1062", "rpt_106", "usr_007", "Sunnyside Restaurant & Lodge", 16450, "2026-11-05", "cat_005", "Dinner with offsite facilitator", R["sunnyside"]),
    ("exp_1071", "rpt_107", "usr_008", "United Airlines", 15910, "2026-11-07", "cat_001", "Return flight RNO - SFO", R["united_priya_new"]),
    ("exp_1072", "rpt_107", "usr_008", "Lyft", 3310, "2026-11-07", "cat_004", "Tahoe City to RNO", R["lyft_priya"]),
    # non-target reports
    ("exp_0901", "rpt_090", "usr_008", "United Airlines", 31820, "2026-10-16", "cat_001", "Flights - Tahoe offsite", R["united_priya_old"]),
    ("exp_0921", "rpt_092", "usr_006", "Zuni Cafe", 14260, "2026-10-28", "cat_005", "Lunch with Halvorsen Freight ops team", R["zuni"]),
    ("exp_0931", "rpt_093", "usr_012", "Departure Restaurant", 21875, "2026-11-12", "cat_005", "Dinner with Cascade Outfitters buyers", None),
    ("exp_0932", "rpt_093", "usr_012", "Lyft", 2645, "2026-11-12", "cat_004", "Hotel to restaurant", None),
    ("exp_0941", "rpt_094", "usr_011", "Figma", 4500, "2026-10-31", "cat_007", "Figma seats - October", R["figma"]),
    ("exp_0942", "rpt_094", "usr_011", "Notion", 2400, "2026-10-31", "cat_007", "Notion team plan - October", None),
    ("exp_0951", "rpt_095", "usr_001", "Office Depot", 4612, "2026-10-30", "cat_006", "Badges, lanyards and flip chart markers", R["officedepot"]),
    # unreported
    ("exp_0961", None, "usr_001", "Blue Bottle Coffee", 1840, "2026-11-13", "cat_005", "Coffee with candidate", None),
    ("exp_0962", None, "usr_001", "Lyft", 2215, "2026-11-12", "cat_004", "Ride to vendor walkthrough", None),
    ("exp_0963", None, "usr_001", "Amazon", 6399, "2026-11-10", "cat_006", "Conference speakerphone", None),
]
MILEAGE = ("exp_0911", "rpt_091", "usr_010", 196.0, "2026-11-04")

REPORT_EXP_STATUS = {"submitted": "processing", "approved": "approved", "reimbursed": "reimbursed", "open": "open"}


def build_expensify():
    users = []
    for uid, first, last, role, dept, mgr, emp in PEOPLE:
        users.append({"id": uid, "email": f"{first.lower()}@{DOMAIN}", "firstName": first, "lastName": last,
                      "displayName": f"{first} {last}", "avatar": None, "role": role, "managerId": mgr,
                      "employeeId": emp, "department": dept, "defaultPolicy": "pol_001",
                      "reimbursementMethod": "ach", "createdAt": "2024-03-04T17:00:00Z"})
    members = []
    for i, u in enumerate(users, 1):
        mgr = u["managerId"]
        members.append({"id": f"mem_{i:03d}", "userId": u["id"], "policyId": "pol_001", "email": u["email"],
                        "name": u["displayName"], "role": "admin" if u["role"] == "admin" else "member",
                        "managerId": mgr, "managerEmail": person(mgr)["email"] if mgr else None,
                        "employeeId": u["employeeId"], "submitsTo": mgr, "approvesTo": None,
                        "isApprover": u["role"] == "admin", "addedAt": "2024-03-04T17:00:00Z"})
    expenses = []
    for eid, rid, uid, merchant, cents, day, cat, desc, rcpt in EXPENSES:
        status = REPORT_EXP_STATUS[REPORTS[rid][3]] if rid else "unreported"
        expenses.append({"id": eid, "type": "expense", "policyId": "pol_001", "reportId": rid, "createdBy": uid,
                         "merchant": merchant, "amount": cents, "currency": "USD", "date": day,
                         "categoryId": cat, "category": CAT[cat],
                         "tagId": "tag_001" if rid in TARGETS + ["rpt_090", "rpt_091", "rpt_095"] else
                                  ("tag_002" if rid == "rpt_092" else ("tag_003" if rid else None)),
                         "tag": "", "description": desc, "comment": "",
                         "receiptUrl": file_url(rcpt) if rcpt else None, "hasReceipt": bool(rcpt),
                         "billable": rid == "rpt_092", "reimbursable": True, "taxAmount": 0, "taxRate": "",
                         "distance": None, "distanceUnit": None, "distanceRate": None, "hours": None,
                         "hourlyRate": None, "status": status, "violations": [],
                         "createdAt": iso(day, "23:30"), "modifiedAt": iso(day, "23:30")})
    eid, rid, uid, miles, day = MILEAGE
    expenses.append({"id": eid, "type": "distance", "policyId": "pol_001", "reportId": rid, "createdBy": uid,
                     "merchant": f"{miles:g} mi mileage", "amount": round(miles * 67), "currency": "USD", "date": day,
                     "categoryId": "cat_010", "category": "Mileage", "tagId": "tag_001", "tag": "",
                     "description": "SF to Tahoe City round trip, drove 3 people", "comment": "", "receiptUrl": None,
                     "hasReceipt": False, "billable": False, "reimbursable": True, "taxAmount": 0, "taxRate": "",
                     "distance": miles, "distanceUnit": "mi", "distanceRate": 67, "hours": None, "hourlyRate": None,
                     "status": "approved", "violations": [], "createdAt": iso(day, "03:00"), "modifiedAt": "2026-11-13T17:20:00Z"})
    for e in expenses:
        e["tag"] = TAG.get(e["tagId"], "") if e["tagId"] else ""
    expenses.sort(key=lambda e: e["id"])

    reports, comments, inbox = [], [], []
    for rid, (uid, title, number, status, to, sub, appr, reimb, created) in REPORTS.items():
        mine = [e for e in expenses if e["reportId"] == rid]
        dates = sorted(e["date"] for e in mine)
        creator, approver = person(uid), person(to)
        reports.append({"id": rid, "title": title, "reportNumber": number, "policyId": "pol_001",
                        "policyName": "Fernbrook Labs", "createdBy": uid, "createdByName": creator["name"],
                        "createdByEmail": creator["email"], "status": status, "total": sum(e["amount"] for e in mine),
                        "currency": "USD", "submittedTo": to, "submittedToEmail": approver["email"],
                        "submittedDate": sub, "approvedDate": appr, "reimbursedDate": reimb,
                        "startDate": dates[0], "endDate": dates[-1], "expenseCount": len(mine),
                        "starred": False, "exported": status == "reimbursed",
                        "exportedDate": reimb, "isRetracted": False, "createdAt": created,
                        "modifiedAt": reimb or appr or sub or created})
        n = len([c for c in comments]) + 1
        comments.append({"id": f"cmt_{n:03d}", "reportId": rid, "authorId": uid, "authorName": creator["name"],
                         "authorEmail": creator["email"], "type": "system", "text": "You created this report",
                         "timestamp": created})
        if sub:
            comments.append({"id": f"cmt_{n + 1:03d}", "reportId": rid, "authorId": uid, "authorName": creator["name"],
                             "authorEmail": creator["email"], "type": "status_change", "text": "Report submitted",
                             "timestamp": sub})
        if appr:
            comments.append({"id": f"cmt_{n + 2:03d}", "reportId": rid, "authorId": to, "authorName": approver["name"],
                             "authorEmail": approver["email"], "type": "status_change", "text": "Report approved",
                             "timestamp": appr})
        if reimb:
            comments.append({"id": f"cmt_{n + 3:03d}", "reportId": rid, "authorId": "system", "authorName": "System",
                             "authorEmail": "", "type": "system", "text": "Reimbursement processed via ACH",
                             "timestamp": reimb})
        if to == "usr_001" and sub:
            inbox.append({"id": f"inb_{len(inbox) + 1:03d}", "type": "report_submitted",
                          "title": "Expense Report Submitted",
                          "description": f"{creator['name']} submitted '{title}' (${sum(e['amount'] for e in mine) / 100:,.2f}) for your approval",
                          "relatedId": rid, "fromUserId": uid, "fromUserName": creator["name"],
                          "read": status != "submitted", "hidden": False, "actionRequired": status == "submitted",
                          "actionType": "approve_report", "createdAt": sub})
    comments.append({"id": "cmt_201", "reportId": "rpt_103", "authorId": "usr_004", "authorName": "Leo Fischer",
                     "authorEmail": "leo@fernbrook.io", "type": "comment",
                     "text": "Rental was for the whole group, I did all the airport runs.", "timestamp": "2026-11-10T21:14:00Z"})
    comments.append({"id": "cmt_202", "reportId": "rpt_102", "authorId": "usr_003", "authorName": "Kofi Mensah",
                     "authorEmail": "kofi@fernbrook.io", "type": "comment",
                     "text": "Uber receipt is on my phone, will send it over.", "timestamp": "2026-11-10T16:42:00Z"})
    inbox += [
        {"id": "inb_090", "type": "concierge", "title": "Welcome to Expensify!",
         "description": "Hi Nadia! I'm Concierge. Approvals routed to you show up here.", "relatedId": None,
         "fromUserId": "concierge", "fromUserName": "Concierge", "read": True, "hidden": False,
         "actionRequired": False, "actionType": None, "createdAt": "2024-03-04T17:05:00Z"},
        {"id": "inb_091", "type": "task", "title": "Review your workspace categories",
         "description": "Owen Price added the category 'Team Events' to Fernbrook Labs.", "relatedId": None,
         "fromUserId": "usr_009", "fromUserName": "Owen Price", "read": False, "hidden": False,
         "actionRequired": False, "actionType": "setup_task", "createdAt": "2026-10-01T16:00:00Z"},
    ]
    nadia = next(u for u in users if u["id"] == "usr_001")
    return {
        "currentUser": dict(nadia),
        "users": users,
        "policies": [
            {"id": "pol_001", "name": "Fernbrook Labs", "type": "corporate", "outputCurrency": "USD", "owner": "usr_009",
             "autoReporting": False, "autoReportingFrequency": "manual", "autoReportingOffset": 0, "requiresCategory": True,
             "requiresTag": False, "requiresComment": False, "maxExpenseAge": 90, "maxExpenseAmount": 5000,
             "preventSelfApproval": True, "approvalMode": "basic", "reimbursementChoice": "reimburseManual",
             "createdAt": "2024-03-01T17:00:00Z"},
            {"id": "pol_002", "name": "Nadia's Personal Expenses", "type": "personal", "outputCurrency": "USD",
             "owner": "usr_001", "autoReporting": False, "autoReportingFrequency": "manual", "autoReportingOffset": 0,
             "requiresCategory": False, "requiresTag": False, "requiresComment": False, "maxExpenseAge": 365,
             "maxExpenseAmount": 10000, "preventSelfApproval": False, "approvalMode": "basic",
             "reimbursementChoice": "noReimbursement", "createdAt": "2024-03-04T17:00:00Z"},
        ],
        "categories": [{"id": cid, "policyId": "pol_001", "name": name, "enabled": True, "glCode": gl, "payrollCode": "",
                        "maxExpenseAmount": 0, "requiresComment": False, "commentHint": "", "externalId": ""}
                       for cid, name, gl in CATS],
        "tags": [{"id": tid, "policyId": "pol_001", "name": name, "enabled": True, "glCode": gl, "required": False}
                 for tid, name, gl in TAGS],
        "expenses": expenses,
        "reports": reports,
        "comments": comments,
        "inboxItems": inbox,
        "members": members,
    }


# ====================================================================== gmail
def email(eid, name, sender, subject, body, ts, *, read=False, category="primary", attachments=None,
          thread=None, to=None, folder="inbox", starred=False):
    return {"id": eid, "threadId": thread or f"t_{eid}",
            "from": {"name": name, "email": sender, "avatar": avatar(name)},
            "to": to or [{"name": "Nadia Brooks", "email": NADIA}], "cc": [], "bcc": [], "subject": subject,
            "body": body, "snippet": re.sub(r"<[^>]*>", "", body)[:100], "timestamp": ts, "read": read, "starred": starred, "important": False,
            "labels": [], "category": category, "folder": folder, "attachments": attachments or []}


def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def att(aid, name, size):
    kind = "application/pdf" if name.endswith(".pdf") else "image/png"
    return {"id": aid, "name": name, "size": size, "type": kind, "url": file_url(name)}


def build_gmail():
    owen_rules = p(
        "Hi Nadia,",
        "Can you take the Tahoe offsite reports off my plate this week? They're all routed to you for approval in "
        "Expensify. A few rules so we close this out cleanly:",
        "1. The receipt is the source of truth. If what someone typed doesn't match the receipt, correct the expense "
        "to what the receipt shows before you approve.<br>"
        "2. Anything that went on the company Amex (ending 1009) stays on the report, but switch Reimbursable off. "
        "We already paid that card. Personal cards are reimbursable as normal.<br>"
        "3. Shared bills: each person only claims what went on their own card.<br>"
        "4. Missing receipts: people have been emailing theirs to you, so attach them to the expense before "
        "approving. If the host gave someone a receipt in the Airbnb thread, that's fine as is, no need to attach it, "
        "just go by what it says.<br>"
        "5. Only the offsite itself counts, Wed Nov 4 through Fri Nov 6. If a report has anything that wasn't part "
        "of the offsite, or that we've already reimbursed, reject the whole report with a one-line reason so they can "
        "fix it and resubmit. Please don't delete anything.",
        "Also, Michael (the host) has been asking about the paddleboard. Please sort that out with him on Airbnb so "
        "it doesn't turn into a Resolution Center claim.",
        "When you're done, reply here with the total we're reimbursing across the offsite reports so I can schedule "
        "the payout run. Thanks!",
        "Owen")
    emails = [
        email("e_owen1", "Owen Price", OWEN, "Tahoe offsite close-out", owen_rules, "2026-11-12T16:14:00Z",
              read=True, thread="t_owen", starred=True),
        email("e_owen2", "Owen Price", OWEN, "Re: Tahoe offsite close-out", p(
            "One correction to rule 5: the travel days count too. Flights on Tue Nov 3 and the rides, fuel and "
            "checkout stuff on Sat Nov 7 are fine. Everything else stands.", "Owen"),
              "2026-11-13T18:02:00Z", thread="t_owen"),
        email("e_kofi", "Kofi Mensah", "kofi@fernbrook.io", "Uber receipt for Tahoe", p(
            "Hey Nadia, here's the Uber receipt for my ride to the airport. I grabbed two screenshots off my phone, "
            "one of them is a personal ride, sorry! Should be obvious which one.", "Kofi"),
              "2026-11-10T17:05:00Z", attachments=[att("a_k1", UBER_WRONG, "188 KB"), att("a_k2", UBER_RIGHT, "191 KB")]),
        email("e_leo", "Leo Fischer", "leo@fernbrook.io", "Hertz - final invoice", p(
            "Hi Nadia, quick one: the Hertz receipt I put on my report is the rental record they printed at pickup. "
            "The final invoice came through after I returned the car, it's attached. Can you sort it out on your end?",
            "Thanks, Leo"), "2026-11-11T16:28:00Z", attachments=[att("a_l1", HERTZ_FINAL, "214 KB")]),
        email("e_daniela", "Daniela Ruiz", "daniela@fernbrook.io", "Paddleboard", p(
            "FYI I settled the paddleboard thing with Michael before we left on Saturday. The Venmo screenshot is on "
            "my report. Let me know if you need anything else!", "Daniela"), "2026-11-09T18:30:00Z", read=True),
        email("e_priya", "Priya Raman", "priya@fernbrook.io", "Offsite expenses submitted", p(
            "Hi Nadia, just submitted my offsite report with the return flight and the Lyft. Shout if anything's "
            "missing.", "Priya"), "2026-11-12T22:51:00Z"),
        email("e_ingrid", "Ingrid Halvorsen", "ingrid@fernbrook.io", "Offsite photos!", p(
            "Shared album is up, 214 photos, the kayak ones are the best. Thanks again for organizing everything."),
              "2026-11-09T02:12:00Z", read=True),
        email("e_tariq", "Tariq Haddad", "tariq@fernbrook.io", "Halvorsen lunch report", p(
            "Nadia, I also put the Halvorsen Freight lunch from October on a report since Owen said it goes through "
            "you now. No rush on that one."), "2026-11-12T20:09:00Z"),
        email("e_mei", "Mei Tanaka", "mei@fernbrook.io", "My Tahoe report", p(
            "Submitted mine! Flight plus the facilitator dinner at Sunnyside."), "2026-11-12T17:18:00Z", read=True),
        email("e_exp1", "Expensify", "concierge@expensify.com", "Reports waiting for your approval", p(
            "You have reports waiting for your approval in the Fernbrook Labs workspace. Open Expensify to review them."),
              "2026-11-13T15:00:00Z", category="updates"),
        email("e_exp2", "Expensify", "concierge@expensify.com", "Owen Price approved 'Tahoe offsite - mileage'", p(
            "Grace Liu's report 'Tahoe offsite - mileage' was approved."), "2026-11-13T17:21:00Z",
              read=True, category="updates"),
        email("e_air1", "Airbnb", "automated@airbnb.com", "Leave a review for Michael's place", p(
            "How was your stay at Lakefront Modern Retreat with Private Dock? Reviews help hosts and guests."),
              "2026-11-08T18:00:00Z", category="updates"),
        email("e_air2", "Airbnb", "automated@airbnb.com", "New message from Michael", p(
            "Michael sent you a message about your stay in Tahoe City. Open Airbnb to read and reply."),
              "2026-11-12T17:41:00Z", category="updates"),
        email("e_owen0", "Owen Price", OWEN, "Q4 budget check-in", p(
            "Can we grab 20 minutes Thursday to go over the Q4 ops budget? Nothing urgent."),
              "2026-11-05T22:10:00Z", read=True),
        email("e_news1", "Ramp Insider", "newsletter@ramp.com", "5 ways finance teams close the month faster", p(
            "This week: automating receipt matching, approval chains that don't stall, and more."),
              "2026-11-14T13:00:00Z", category="promotions"),
        email("e_news2", "Delta SkyMiles", "skymiles@delta.com", "Your November statement", p(
            "You have 18,240 miles. See offers for winter travel."), "2026-11-11T12:00:00Z", category="promotions"),
        email("e_hr", "People Team", "people@fernbrook.io", "Open enrollment closes Nov 20", p(
            "Reminder: benefits open enrollment closes Friday Nov 20."), "2026-11-10T15:00:00Z", read=True),
        email("e_grace", "Grace Liu", "grace@fernbrook.io", "Mileage report", p(
            "Owen already approved my mileage report so you can ignore that one. Thanks!"),
              "2026-11-13T17:40:00Z", read=True),
        email("e_sent_agenda", "Nadia Brooks", NADIA, "Tahoe offsite - agenda & logistics", p(
            "Hi all, agenda and logistics attached. See you at the lake!"), "2026-10-20T17:00:00Z", read=True,
              folder="sent", to=[{"name": "Offsite team", "email": "offsite@fernbrook.io"}],
              attachments=[att("a_ag", AGENDA_PDF, "38 KB")]),
    ]
    return {
        "user": {"userId": "u1", "username": "Nadia Brooks", "email": NADIA, "avatar": avatar("Nadia Brooks")},
        "emails": emails,
        "labels": [{"id": "l1", "name": "Finance", "color": "#3b82f6"}, {"id": "l2", "name": "Offsite", "color": "#10b981"}],
        "drafts": [],
        "settings": {"signature": "--\nNadia Brooks\nOps & Finance, Fernbrook Labs", "undoSend": 5},
    }


# ====================================================================== airbnb
def price(nightly, nights, cleaning, tax_rate):
    sub = nightly * nights
    fee = round(0.142 * (sub + cleaning), 2)
    taxes = round(tax_rate * (sub + cleaning), 2)
    return {"nightlyRate": nightly, "nights": nights, "nightsSubtotal": sub, "discount": 0, "discountPct": 0,
            "cleaningFee": cleaning, "petFee": 0, "serviceFee": fee, "taxes": taxes,
            "total": round(sub + cleaning + fee + taxes, 2), "currency": "USD"}


def msg(mid, conv, sender, body, ts, *, kind="text", attachments=None, read=True):
    return {"id": mid, "conversationId": conv, "senderId": sender, "kind": kind, "body": body,
            "attachments": attachments or [], "reactions": [], "createdAt": ts, "readAt": ts if read else None,
            "editedAt": None, "deletedAt": None, "translated": False}


def photo(name, size):
    return {"url": file_url(name), "name": name, "size": size, "contentType": "image/png"}


TAHOE_CONV = "conv_201"


def build_airbnb():
    def res(rid, code, lst, host, cin, cout, nights, adults, pb, status, conv, created, pm="pm_101"):
        return {"id": rid, "confirmationCode": code, "listingId": lst, "hostId": host, "guestId": "user_001",
                "checkIn": cin, "checkOut": cout, "nights": nights,
                "guests": {"adults": adults, "children": 0, "infants": 0, "pets": 0}, "status": status,
                "bookingType": "instant", "rateType": "refundable", "cancellationPolicy": "strict",
                "priceBreakdown": pb, "paymentPlan": "full", "amountPaid": pb["total"], "paymentMethodId": pm,
                "messageToHost": "", "conversationId": conv, "createdAt": created, "confirmedAt": created,
                "cancellation": None, "alterations": []}
    reservations = [
        res("res_201", "HMQ4T8XK2P", "lst_002", "user_101", "2026-11-04", "2026-11-07", 3, 8,
            price(845, 3, 300, 0.1), "confirmed", TAHOE_CONV, "2026-09-28T18:20:00Z"),
        res("res_202", "HMB7R2NC9D", "lst_023", "user_110", "2026-04-13", "2026-04-16", 3, 6,
            price(425, 3, 180, 0.15), "confirmed", "conv_202", "2026-02-24T17:00:00Z"),
        res("res_203", "HMW5L1ZE3A", "lst_031", "user_113", "2026-12-07", "2026-12-10", 3, 2,
            price(289, 3, 100, 0.148), "confirmed", "conv_203", "2026-11-02T16:00:00Z", pm="pm_102"),
        res("res_204", "HMC9P6YJ1F", "lst_057", "user_120", "2026-08-21", "2026-08-23", 2, 5,
            price(410, 2, 175, 0.08), "cancelled", "conv_204", "2026-06-30T16:00:00Z", pm="pm_102"),
    ]
    reservations[0]["messageToHost"] = "Hi Michael! Booking for our team offsite, 8 of us arriving Wednesday afternoon."
    reservations[3]["cancellation"] = {"cancelledAt": "2026-07-15T16:00:00Z", "cancelledBy": "guest",
                                       "reason": "Plans changed", "refundAmount": reservations[3]["amountPaid"]}
    conversations = [
        {"id": TAHOE_CONV, "type": "reservation", "listingId": "lst_002", "reservationId": "res_201",
         "participantIds": ["user_001", "user_101"], "hostId": "user_101", "lastMessageAt": "2026-11-12T17:40:00Z",
         "unreadCount": 1, "starred": False, "archived": False, "createdAt": "2026-09-28T18:20:00Z"},
        {"id": "conv_202", "type": "reservation", "listingId": "lst_023", "reservationId": "res_202",
         "participantIds": ["user_001", "user_110"], "hostId": "user_110", "lastMessageAt": "2026-04-16T17:00:00Z",
         "unreadCount": 0, "starred": False, "archived": False, "createdAt": "2026-02-24T17:00:00Z"},
        {"id": "conv_203", "type": "reservation", "listingId": "lst_031", "reservationId": "res_203",
         "participantIds": ["user_001", "user_113"], "hostId": "user_113", "lastMessageAt": "2026-11-03T15:10:00Z",
         "unreadCount": 0, "starred": False, "archived": False, "createdAt": "2026-11-02T16:00:00Z"},
        {"id": "conv_204", "type": "reservation", "listingId": "lst_057", "reservationId": "res_204",
         "participantIds": ["user_001", "user_120"], "hostId": "user_120", "lastMessageAt": "2026-07-15T16:00:00Z",
         "unreadCount": 0, "starred": False, "archived": False, "createdAt": "2026-06-30T16:00:00Z"},
    ]
    c = TAHOE_CONV
    messages = [
        msg("msg_2001", c, "system", "Reservation confirmed", "2026-09-28T18:20:00Z", kind="system"),
        msg("msg_2002", c, "user_001", "Hi Michael! Booking for our team offsite, 8 of us arriving Wednesday "
            "afternoon. A few people may want a late checkout on Saturday, is that possible?", "2026-09-28T18:21:00Z"),
        msg("msg_2003", c, "user_101", "Welcome Nadia! Happy to host your team. Late checkout is usually fine, just "
            "settle it with me on the day.", "2026-09-28T19:02:00Z"),
        msg("msg_2004", c, "user_101", "Door code is in the check-in guide. Paddleboards and kayaks are in the "
            "boathouse, please rinse them after use. Enjoy!", "2026-11-04T19:30:00Z"),
        msg("msg_2005", c, "user_101", "Thanks for sorting out the late checkout and firewood with Tariq this "
            "morning. Here's the receipt I gave him for your records.", "2026-11-07T16:55:00Z",
            attachments=[photo(HOST_RECEIPT, 184000)]),
        msg("msg_2006", c, "user_101", "One of the paddleboards came back with a cracked fin. Here's the estimate "
            "from the board shop. Happy to settle directly with whoever is handling it, otherwise I'll have to go "
            "through the Resolution Center.", "2026-11-07T21:20:00Z", attachments=[photo(BOARD_QUOTE, 203000)]),
        msg("msg_2007", c, "user_001", "Thanks Michael, sorry about that! Someone from the team will sort it out "
            "with you.", "2026-11-07T21:45:00Z"),
        msg("msg_2008", c, "user_101", "Hi Nadia, I've had a couple of Venmo payments come in from your group this "
            "week and honestly I can't tell which was for what. Can you confirm whether the paddleboard has been "
            "paid, who paid it and how much? If I don't hear back I'll open a Resolution Center request on Monday "
            "for the full estimate.", "2026-11-12T17:40:00Z", read=False),
        msg("msg_2101", "conv_202", "system", "Reservation confirmed", "2026-02-24T17:00:00Z", kind="system"),
        msg("msg_2102", "conv_202", "user_110", "Hi Nadia, the farmhouse is ready for your group. Gate code to follow.",
            "2026-04-10T17:00:00Z"),
        msg("msg_2103", "conv_202", "user_001", "Thanks Rosa, we had a great time!", "2026-04-16T17:00:00Z"),
        msg("msg_2201", "conv_203", "system", "Reservation confirmed", "2026-11-02T16:00:00Z", kind="system"),
        msg("msg_2202", "conv_203", "user_001", "Hi! Two of us in town for a conference, arriving around 6pm.",
            "2026-11-02T16:05:00Z"),
        msg("msg_2203", "conv_203", "user_113", "Sounds good, self check-in with the lockbox. See you in December!",
            "2026-11-03T15:10:00Z"),
        msg("msg_2301", "conv_204", "system", "Reservation cancelled", "2026-07-15T16:00:00Z", kind="system"),
    ]
    notifications = [
        {"id": "ntf_201", "type": "message", "title": "New message from Michael",
         "body": "About your stay at Lakefront Modern Retreat with Private Dock.", "link": f"/messages/{TAHOE_CONV}",
         "read": False, "createdAt": "2026-11-12T17:40:00Z"},
        {"id": "ntf_202", "type": "review_reminder", "title": "Leave a review for Michael's place",
         "body": "You have 5 days left to review your Tahoe City stay.", "link": "/reviews/write/res_201",
         "read": False, "createdAt": "2026-11-09T17:00:00Z"},
        {"id": "ntf_203", "type": "booking", "title": "Your reservation is confirmed",
         "body": "Your New York trip is coming up.", "link": "/trips/res_203", "read": True,
         "createdAt": "2026-11-02T16:00:00Z"},
        {"id": "ntf_204", "type": "account", "title": "Your account is verified", "body": "You're ready to explore.",
         "link": "/account-settings", "read": True, "createdAt": "2025-01-10T16:00:00Z"},
    ]
    return {
        "currentUser": {"id": "user_001", "firstName": "Nadia", "lastName": "Brooks", "preferredName": "Nadia",
                        "email": NADIA, "phone": "+1 (415) 555-0187", "avatarColor": "#2E6F95", "avatarUrl": None,
                        "location": "San Francisco, CA", "joinedAt": "2018-06-02",
                        "about": "Ops & finance at Fernbrook Labs. I book the team trips.",
                        "work": "Ops & Finance at Fernbrook Labs", "languages": ["English"], "school": "",
                        "identityVerified": True,
                        "address": {"street": "540 Howard St", "city": "San Francisco", "state": "CA", "zip": "94105",
                                    "country": "United States"},
                        "emergencyContact": {"name": "Chris Brooks", "relationship": "Partner",
                                             "phone": "+1 (415) 555-0140"}, "travelCredit": 0},
        "reservations": reservations,
        "conversations": conversations,
        "messages": messages,
        "notifications": notifications,
        "paymentMethods": [
            {"id": "pm_101", "type": "card", "brand": "American Express", "last4": "1009", "expMonth": 4,
             "expYear": 2029, "holderName": "Fernbrook Labs / N Brooks", "billingZip": "94105", "isDefault": True,
             "createdAt": "2024-03-10T17:00:00Z"},
            {"id": "pm_102", "type": "card", "brand": "Visa", "last4": "6620", "expMonth": 9, "expYear": 2027,
             "holderName": "Nadia Brooks", "billingZip": "94110", "isDefault": False,
             "createdAt": "2023-05-02T17:00:00Z"},
        ],
    }


# ====================================================================== correct plan
# expense id -> corrected cents (receipt wins)
CORRECT_AMOUNTS = {"exp_1012": 16500, "exp_1021": 16000, "exp_1032": 32418, "exp_1051": 9500}
NON_REIMBURSABLE = ["exp_1013", "exp_1041"]          # company Amex 1009
UPLOADS = {"exp_1022": UBER_RIGHT}                     # emailed receipt to attach
AIRBNB_REPLY = ("Hi Michael, the paddleboard is settled: Daniela Ruiz paid you $165.00 by Venmo on Nov 7 for the "
                "fin repair, so no Resolution Center claim is needed. Thanks for being so easy to work with!")


def plan(**over):
    base = {"amounts": dict(CORRECT_AMOUNTS), "nonreimb": list(NON_REIMBURSABLE), "uploads": dict(UPLOADS),
            "approve": list(APPROVE), "reject": dict(REJECT), "airbnb": AIRBNB_REPLY, "gmail_total": None}
    base.update(over)
    return base


T0 = "2026-11-16T10:{:02d}:00.000Z"


def apply_plan(state, pl):
    ex, ab, gm = state["expensify"], state["airbnb"], state["gmail"]
    tick = iter(range(1, 60))
    exp_by = {e["id"]: e for e in ex["expenses"]}
    rep_by = {r["id"]: r for r in ex["reports"]}
    me = ex["currentUser"]

    def save(eid, **changes):  # ExpenseDetailModal.save(): {...form, amount, modifiedAt} + report total
        e = exp_by[eid]
        ts = T0.format(next(tick))
        e.setdefault("amountDollars", dollars(e["amount"]))
        e.update(changes)
        e["modifiedAt"] = ts
        r = rep_by[e["reportId"]]
        r["total"] = sum(x["amount"] for x in ex["expenses"] if x["reportId"] == r["id"])
        r["modifiedAt"] = ts

    for eid, cents in pl["amounts"].items():
        save(eid, amount=cents, amountDollars=dollars(cents))
    for eid in pl["nonreimb"]:
        save(eid, reimbursable=False)
    for eid, name in pl["uploads"].items():
        save(eid, receiptUrl=f"/files/__SID__/{UPLOAD_PREFIX}_{name}", hasReceipt=True)
    n = 0
    for rid in pl["approve"]:
        ts = T0.format(next(tick))
        n += 1
        rep_by[rid].update(status="approved", approvedDate=ts)
        ex["comments"].append({"id": f"cmt_g{n:02d}", "reportId": rid, "authorId": me["id"],
                               "authorName": me["displayName"], "authorEmail": me["email"], "type": "status_change",
                               "text": "Report approved", "timestamp": ts})
        for e in ex["expenses"]:
            if e["reportId"] == rid:
                e["status"] = "approved"
        for i in ex["inboxItems"]:
            if i["relatedId"] == rid and i["actionType"] == "approve_report" and not i["read"]:
                i["read"] = True
    for rid, reason in pl["reject"].items():
        ts = T0.format(next(tick))
        n += 1
        rep_by[rid].update(status="open", isRetracted=True)
        ex["comments"].append({"id": f"cmt_g{n:02d}", "reportId": rid, "authorId": me["id"],
                               "authorName": me["displayName"], "authorEmail": me["email"], "type": "status_change",
                               "text": f"Report rejected: {reason}", "timestamp": ts})
    # airbnb: readThread on focus, then send()
    if pl["airbnb"]:
        ts = "2026-11-16T10:40:00.000Z"
        for m in ab["messages"]:
            if m["conversationId"] == TAHOE_CONV and m["senderId"] != "user_001" and m["kind"] != "system" and not m["readAt"]:
                m["readAt"] = ts
        conv = next(c for c in ab["conversations"] if c["id"] == TAHOE_CONV)
        conv["unreadCount"] = 0
        ab["messages"].append(msg("msg_g001", TAHOE_CONV, "user_001", pl["airbnb"], ts))
        conv["lastMessageAt"] = ts
    rows = closeout_rows(ex)
    total = pl["gmail_total"] or sum(float(r[3]) for r in rows[1:])
    body = (f"Hi Owen, the Tahoe offsite reports are done. Total to reimburse across the offsite reports: "
            f"${total:,.2f}. Two reports were sent back (Mei and Priya) with reasons.\n\nNadia")
    owen = next(e for e in gm["emails"] if e["id"] == "e_owen2")
    gm["emails"].append({"id": "sent_g1", "threadId": owen["threadId"],
                         "from": {"name": gm["user"]["username"], "email": gm["user"]["email"], "avatar": gm["user"]["avatar"]},
                         "to": [owen["from"]], "cc": [], "bcc": [], "subject": owen["subject"], "body": body,
                         "snippet": body[:100], "timestamp": "2026-11-16T10:50:00.000Z", "read": True,
                         "starred": False, "important": False, "labels": [], "category": "primary", "folder": "sent",
                         "attachments": []})
    for e in gm["emails"]:
        if e["id"] in ("e_owen2", "e_kofi", "e_leo"):
            e["read"] = True
    return rows


def closeout_rows(ex):
    rows = [["report_number", "employee_email", "decision", "reimbursable_total"]]
    for rid in TARGETS:
        r = next(r for r in ex["reports"] if r["id"] == rid)
        if r["status"] == "approved":
            cents = sum(e["amount"] for e in ex["expenses"] if e["reportId"] == rid and e["reimbursable"])
            rows.append([str(r["reportNumber"]), r["createdByEmail"], "approved", dollars(cents)])
        else:
            rows.append([str(r["reportNumber"]), r["createdByEmail"], "rejected", "0.00"])
    return rows


def run(seed, pl):
    state = copy.deepcopy(seed)
    rows = apply_plan(state, pl)
    return state, rows


VARIANTS = {
    "golden": plan(),
    # ignores every image: typed amounts, no card check, approves everything waiting incl. the Halvorsen lunch,
    # attaches the first Uber screenshot, quotes the board-shop estimate to the host
    "naive": plan(amounts={}, nonreimb=[], uploads={"exp_1022": UBER_WRONG},
                  approve=TARGETS + ["rpt_092"], reject={},
                  airbnb="Hi Michael, the paddleboard was settled by Venmo for the $180 estimate. Thanks!"),
    "slip_hertz": plan(amounts={k: v for k, v in CORRECT_AMOUNTS.items() if k != "exp_1032"}),
    "slip_amex3005": plan(nonreimb=NON_REIMBURSABLE + ["exp_1043"]),
    "slip_host_cash": plan(amounts={k: v for k, v in CORRECT_AMOUNTS.items() if k != "exp_1051"}),
    "slip_duplicate": plan(approve=APPROVE + ["rpt_107"], reject={"rpt_106": REJECT["rpt_106"]}),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(out: Path):
    for site, items in FILES.items():
        for name, render in items:
            render(out / "seed" / "files" / site / name)
    seed = {"expensify": build_expensify(), "airbnb": build_airbnb(), "gmail": build_gmail()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    golden, golden_rows = run(seed, VARIANTS["golden"])
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / OUTPUT_CSV, golden_rows)

    total = sum(float(r[3]) for r in golden_rows[1:])
    reports = {r["id"]: r for r in golden["expensify"]["reports"]}
    write_json(out / "expected.json", {
        "clock": CLOCK,
        "output_csv": OUTPUT_CSV,
        "csv_columns": golden_rows[0],
        "csv_rows": [dict(zip(golden_rows[0], r)) for r in golden_rows[1:]],
        "target_reports": {rid: {"reportNumber": reports[rid]["reportNumber"], "employee": reports[rid]["createdByEmail"],
                                 "decision": "approved" if rid in APPROVE else "rejected"} for rid in TARGETS},
        "corrected_amounts_cents": CORRECT_AMOUNTS,
        "typed_amounts_cents": {eid: next(e["amount"] for e in seed["expensify"]["expenses"] if e["id"] == eid)
                                for eid in CORRECT_AMOUNTS},
        "non_reimbursable": NON_REIMBURSABLE,
        "must_stay_reimbursable": [e[0] for e in EXPENSES if e[1] in APPROVE and e[0] not in NON_REIMBURSABLE],
        "receipt_upload": {"expense": "exp_1022", "correct_file": UBER_RIGHT, "wrong_file": UBER_WRONG,
                           "correct_sha256": sha(out / "seed/files/gmail" / UBER_RIGHT),
                           "wrong_sha256": sha(out / "seed/files/gmail" / UBER_WRONG)},
        "non_target_reports": [rid for rid in REPORTS if rid not in TARGETS],
        "airbnb": {"conversation": TAHOE_CONV, "sender": "user_001", "must_mention": "165", "must_not_mention": "180"},
        "gmail": {"to": OWEN, "thread": "t_owen", "total": f"{total:.2f}"},
        "grand_total": f"{total:.2f}",
    })

    for name, pl in VARIANTS.items():
        states, rows = run(seed, pl)
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        write_csv(out / "variants" / name / "output" / OUTPUT_CSV, rows)
    for site, state in seed.items():
        write_json(out / "variants" / "nop" / "state" / site / "current.json", state)
        write_json(out / "variants" / "nop" / "state" / site / "initial.json", state)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
