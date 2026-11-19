#!/usr/bin/env python3
"""World for the halvorsen-plateful-pricefile task (Gmail + Yahoo Mail + Airtable, lever L13).

Writes into <out>/:
  seed/{gmail,yahoo_mail,airtable}.json        initial state per site
  seed/files/gmail/<csv>                       supplier price lists attached in Gmail (v1, rev B, dairy decoy)
  seed/files/yahoo_mail/<csv>                  old Plateful import in the Yahoo Sent folder, plus the
                                               golden upload under an unguessable stored name
  golden/{gmail,yahoo_mail,airtable}.json      state after a correct run
  golden_output/halvorsen_plateful_prices.csv  local copy of the uploaded price file
  expected.json                                truth for the verifier
  variants/<name>/state/<site>/{initial,current}.json
  variants/<name>/files/yahoo_mail/__SID__/<stored file>
  variants/<name>/output/halvorsen_plateful_prices.csv

Story: Priya Raman is the operations analyst at Fennwick Provisions (four bakery-cafes in
Portland, OR). Halvorsen Mill & Pantry mailed its 2027 price list to her Gmail on Nov 13 and a
corrected "rev B" on Nov 16 (effective date moved Dec 1 -> Dec 7, corrected lines appended at the
bottom with a later Revised date, so items now appear twice). Dana (Director of Operations) wrote
the loading rules. Plateful, the recipe-costing system, only takes price files e-mailed from the
old fennwickbakery@yahoo.com account; its spec changed on Nov 1 (metric only, ISO dates, private
import address). Airtable holds the item master (Item Code <-> Supplier SKU, costing unit, case
price, contracts, status).

Lever L13 (file round trip): download rev B from Gmail, transform it locally (dedupe by latest
Revised, price-basis -> case price, imperial -> metric, map to Airtable item codes, drop
inactive/discontinued/contract items), upload the CSV as an attachment in Yahoo Mail and send it to
Plateful. The verifier parses the uploaded file from /var/lib/cua/files/yahoo_mail/<sid>/.
Airtable gets Status = Discontinued, Price Review ticks and the supplier's Prices Effective date.
"""

import copy
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url  # noqa: E402

CLOCK = "2026-11-18T10:15:00-08:00"
NOW_Z = "2026-11-18T18:40:00.000Z"
TODAY = "2026-11-18"
EFFECTIVE = "2026-12-07"        # rev B mail (Gmail); v1 said 2026-12-01
EFFECTIVE_V1 = "2026-12-01"
REVIEW_PCT = 0.08               # tick Price Review if new case price > Airtable Case Price * 1.08

PRIYA = ("Priya Raman", "priya.raman@fennwickprovisions.com")
DANA = ("Dana Okafor", "dana.okafor@fennwickprovisions.com")
MARTA = ("Marta Lindqvist", "marta.lindqvist@halvorsenmill.com")
YAHOO_USER = ("Fennwick Bakery", "fennwickbakery@yahoo.com")
IMPORT_ADDR = "fennwick-7q2k@imports.plateful.app"
OLD_IMPORT_ADDR = "imports@plateful.app"
HMP = "Halvorsen Mill & Pantry"
HDC = "Halvorsen Dairy Co-op"

V1_NAME = "HMP_PriceList_2027.csv"
V2_NAME = "HMP_PriceList_2027_revB.csv"
DAIRY_NAME = "HDC_Prices_Jan2027.csv"
OLD_UPLOAD_NAME = "cascade_prices_aug.csv"
OUT_NAME = "halvorsen_plateful_prices.csv"
HEADER = ["item_code", "supplier_sku", "case_price", "case_qty", "cost_unit", "cost_per_unit", "effective_date"]
CAT_HEADER = ["Item No", "Description", "Pack", "Size", "UOM", "Price", "Price Basis", "Status", "Revised"]

# Plateful v3 conversion factors (stated in the Oct 6 Plateful mail in Yahoo)
TO_KG = {"LB": 0.45359237, "OZ": 0.028349523125, "KG": 1.0, "G": 0.001}
TO_L = {"GAL": 3.785411784, "FL OZ": 0.0295735295625, "L": 1.0, "ML": 0.001}
UNIT_CODE = {"kg": "KG", "L": "L", "each": "EA"}

# ---------------------------------------------------------------- supplier price list
# item_no, description, pack, size, uom, price, basis, status, revised
CATALOG_V1 = [
    ("10412", "All-Purpose Flour, Unbleached", 1, "50", "LB", "0.612", "LB", "ACTIVE", "2026-11-10"),
    ("10421", "All-Purpose Flour, Bleached", 1, "50", "LB", "0.598", "LB", "ACTIVE", "2026-11-10"),
    ("10433", "Bread Flour, High Gluten", 1, "50", "LB", "0.648", "LB", "ACTIVE", "2026-11-10"),
    ("10450", "Whole Wheat Flour, Stone Ground", 1, "25", "LB", "21.75", "CS", "ACTIVE", "2026-11-10"),
    ("10466", "Dark Rye Flour", 1, "25", "LB", "24.10", "CS", "ACTIVE", "2026-11-10"),
    ("10480", "Almond Flour, Blanched", 1, "25", "LB", "6.20", "LB", "ACTIVE", "2026-11-10"),
    ("10495", "Semolina, Fine", 1, "50", "LB", "0.71", "LB", "NEW", "2026-11-10"),
    ("11205", "Granulated Sugar, Cane", 1, "50", "LB", "38.50", "CS", "ACTIVE", "2026-10-28"),
    ("11212", "Powdered Sugar 10X", 12, "2", "LB", "27.36", "CS", "ACTIVE", "2026-10-28"),
    ("11218", "Light Brown Sugar", 1, "25", "LB", "24.95", "CS", "ACTIVE", "2026-10-28"),
    ("11218", "Light Brown Sugar", 1, "25", "LB", "24.95", "CS", "ACTIVE", "2026-10-28"),   # pasted twice
    ("11230", "Turbinado Sugar", 6, "2", "LB", "31.80", "CS", "ACTIVE", "2026-10-28"),
    ("12040", "Rolled Oats, Old Fashioned", 1, "25", "LB", "22.40", "CS", "ACTIVE", "2026-11-10"),
    ("12055", "Steel Cut Oats", 1, "25", "LB", "27.90", "CS", "ACTIVE", "2026-11-10"),
    ("13110", "Cocoa Powder, Dutch Process 22/24", 1, "5", "KG", "64.50", "CS", "ACTIVE", "2026-11-10"),
    ("13125", "Dark Chocolate Callets 64%", 4, "2.5", "KG", "118.40", "CS", "ACTIVE", "2026-11-10"),
    ("13130", "Semi-Sweet Chocolate Chips 4M", 1, "25", "LB", "96.75", "CS", "ACTIVE", "2026-11-10"),
    ("13145", "White Chocolate Callets 31%", 4, "2.5", "KG", "112.80", "CS", "ACTIVE", "2026-11-10"),
    ("14010", "Pure Vanilla Extract", 6, "16", "FL OZ", "119.70", "CS", "ACTIVE", "2026-11-10"),
    ("14022", "Pure Almond Extract", 4, "16", "FL OZ", "88.40", "CS", "ACTIVE", "2026-11-10"),
    ("14105", "Canola Oil, Expeller Pressed", 1, "5", "GAL", "48.90", "CS", "ACTIVE", "2026-11-10"),
    ("14120", "Extra Virgin Olive Oil", 6, "1", "L", "74.40", "CS", "ACTIVE", "2026-11-10"),
    ("15030", "Walnut Halves & Pieces", 1, "25", "LB", "7.28", "LB", "ACTIVE", "2026-11-10"),
    ("15045", "Hazelnut Meal", 1, "10", "LB", "9.85", "LB", "ACTIVE", "2026-11-10"),
    ("15060", "Pecan Pieces, Medium", 1, "30", "LB", "8.95", "LB", "ACTIVE", "2026-11-10"),
    ("16010", "Sea Salt, Fine", 1, "25", "LB", "18.60", "CS", "ACTIVE", "2026-10-28"),
    ("16025", "Kosher Salt", 9, "3", "LB", "41.85", "CS", "ACTIVE", "2026-10-28"),
    ("16100", "Ground Cinnamon, Saigon", 6, "18", "OZ", "89.70", "CS", "ACTIVE", "2026-10-28"),
    ("16120", "Active Dry Yeast", 2, "2", "LB", "22.40", "CS", "DISC", "2026-10-28"),
    ("16125", "Instant Dry Yeast", 20, "1", "LB", "68.00", "CS", "NEW", "2026-10-28"),
    ("17005", "Baking Cups, 2.5 in White", 10, "500", "EA", "0.0118", "EA", "ACTIVE", "2026-11-10"),
    ("17010", "Parchment Sheets, Full Size", 1, "1000", "EA", "64.20", "CS", "ACTIVE", "2026-11-10"),
    ("18200", "Golden Raisins", 1, "30", "LB", "3.42", "LB", "ACTIVE", "2026-11-10"),
    ("18215", "Dried Cranberries, Sweetened", 1, "25", "LB", "4.18", "LB", "ACTIVE", "2026-11-10"),
]
# rev B = v1 + corrected lines appended at the bottom (later Revised date wins)
REVB_APPENDED = [
    ("10433", "Bread Flour, High Gluten", 1, "50", "LB", "0.668", "LB", "ACTIVE", "2026-11-16"),
    ("10480", "Almond Flour, Blanched", 1, "25", "LB", "6.48", "LB", "ACTIVE", "2026-11-16"),
    ("13110", "Cocoa Powder, Dutch Process 22/24", 1, "5", "KG", "71.25", "CS", "ACTIVE", "2026-11-16"),
    ("15045", "Hazelnut Meal", 1, "10", "LB", "9.85", "LB", "DISC", "2026-11-16"),
]


def catalog(version: int):
    rows = CATALOG_V1 + (REVB_APPENDED if version == 2 else [])
    return [dict(zip(["item_no", "desc", "pack", "size", "uom", "price", "basis", "status", "revised"], r)) for r in rows]


def dedupe(rows, keep="latest"):
    """One line per item number. keep='latest': latest Revised (ties: later line); 'first': first line seen."""
    out = {}
    for r in rows:
        k = r["item_no"]
        if k not in out:
            out[k] = r
        elif keep == "latest" and r["revised"] >= out[k]["revised"]:
            out[k] = r
    return out


# ---------------------------------------------------------------- Airtable item master
SUPPLIERS = [
    # id, name, rep, email, phone, account, terms, prices effective, notes
    ("rec_sup_hmp", HMP, "Marta Lindqvist", MARTA[1], "(503) 555-0142", "FWP-20418", "Net 30", "2025-12-01",
     "Dry goods, baking and pantry. Price list each autumn."),
    ("rec_sup_hdc", HDC, "Ben Halvorsen", "ben@halvorsendairy.coop", "(503) 555-0177", "HD-7731", "Net 15", "2026-01-05",
     "Butter, cream, eggs. Separate company from Halvorsen Mill & Pantry (own item numbers)."),
    ("rec_sup_cp", "Cascade Produce", "Luis Ortega", "orders@cascadeproduce.com", "(503) 555-0110", "CP-5512", "Net 15", "2026-08-24",
     "Produce, delivered Tue/Fri."),
    ("rec_sup_bc", "Bridgetown Coffee Roasters", "Hana Kim", "wholesale@bridgetowncoffee.com", "(503) 555-0193", "BCR-0884", "Net 30",
     "2026-07-01", "Espresso and drip blends."),
    ("rec_sup_rc", "Rose City Paper & Packaging", "Owen Price", "sales@rosecitypaper.com", "(503) 555-0158", "RC-31207", "Net 30",
     "2026-03-02", "Cups, boxes, bags, baking paper."),
    ("rec_sup_wv", "Willamette Valley Fruit Co.", "Grace Ito", "grace@wvfruitco.com", "(503) 555-0136", "WVF-118", "COD",
     "2026-06-15", "Seasonal berries and preserves."),
]

# item code, description, supplier, sku, pack (as last ordered), costing unit, case price,
# contract price, contract ends, status, notes
ITEMS = [
    ("FP-1001", "AP Flour, Unbleached", HMP, "10412", "50 lb bag", "kg", 28.90, None, None, "Active", ""),
    ("FP-1002", "Bread Flour, High Gluten", HMP, "10433", "50 lb bag", "kg", 30.25, None, None, "Active", ""),
    ("FP-1003", "Whole Wheat Flour", HMP, "10450", "25 lb bag", "kg", 20.90, None, None, "Active", ""),
    ("FP-1004", "Dark Rye Flour", HMP, "10466", "25 lb bag", "kg", 23.10, None, None, "Inactive",
     "Rye loaf came off the menu in September."),
    ("FP-1005", "Almond Flour, Blanched", HMP, "10480", "25 lb box", "kg", 149.50, None, None, "Active", "Macarons, financiers"),
    ("FP-1010", "Granulated Cane Sugar", HMP, "11205", "50 lb bag", "kg", 36.80, None, None, "Active", ""),
    ("FP-1011", "Powdered Sugar 10X", HMP, "11212", "12 x 2 lb", "kg", 25.20, None, None, "Active", ""),
    ("FP-1012", "Light Brown Sugar", HMP, "11218", "25 lb bag", "kg", 23.90, None, None, "Active", ""),
    ("FP-1020", "Cocoa Powder, Dutch 22/24", HMP, "13110", "5 kg bag", "kg", 61.80, None, None, "Active", ""),
    ("FP-1021", "Dark Chocolate Callets 64%", HMP, "13125", "4 x 2.5 kg", "kg", 104.00, 104.00, "2026-12-31", "Active",
     "2026 volume contract."),
    ("FP-1022", "Semi-Sweet Chips 4M", HMP, "13130", "25 lb case", "kg", 88.00, 88.00, "2026-12-06", "Active",
     "Holiday contract, not renewed."),
    ("FP-1030", "Pure Vanilla Extract", HMP, "14010", "4 x 32 fl oz", "L", 152.00, None, None, "Active", ""),
    ("FP-1031", "Canola Oil", HMP, "14105", "5 gal jug", "L", 46.50, None, None, "Active", ""),
    ("FP-1032", "Extra Virgin Olive Oil", HMP, "14120", "6 x 1 L", "L", 70.80, None, None, "Active", "Focaccia"),
    ("FP-1040", "Walnut Halves & Pieces", HMP, "15030", "25 lb box", "kg", 171.25, None, None, "Active", ""),
    ("FP-1041", "Hazelnut Meal", HMP, "15045", "10 lb bag", "kg", 94.00, None, None, "Active", ""),
    ("FP-1050", "Fine Sea Salt", HMP, "16010", "25 lb bag", "kg", 18.60, None, None, "Active", ""),
    ("FP-1051", "Kosher Salt", HMP, "16025", "9 x 3 lb", "kg", 39.60, None, None, "Active", ""),
    ("FP-1052", "Saigon Cinnamon, Ground", HMP, "16100", "6 x 18 oz", "kg", 84.00, None, None, "Active", "Morning buns"),
    ("FP-1053", "Active Dry Yeast", HMP, "16120", "2 x 2 lb", "kg", 21.60, None, None, "Active", ""),
    ("FP-1060", "Baking Cups 2.5 in", HMP, "17005", "10 x 500", "each", 56.50, None, None, "Active", "Muffins"),
    ("FP-1061", "Parchment Sheets, Full Pan", HMP, "17010", "1000 sheets", "each", 61.10, None, None, "Active", ""),
    ("FP-1071", "Dried Cranberries", HMP, "18215", "25 lb box", "kg", 97.10, None, None, "Active", "Scones"),
    # Halvorsen Dairy Co-op: different company, overlapping item numbers
    ("FD-2040", "Cultured Butter, Unsalted 83%", HDC, "12040", "36 x 1 lb", "kg", 142.20, None, None, "Active", "Laminating butter"),
    ("FD-2421", "Whole Milk, Organic", HDC, "10421", "4 x 1 gal", "L", 21.80, None, None, "Active", ""),
    ("FD-2105", "Heavy Cream 40%", HDC, "20105", "4 x 0.5 gal", "L", 38.40, None, None, "Active", ""),
    ("FD-2210", "Cream Cheese Block", HDC, "22210", "10 x 3 lb", "kg", 96.50, None, None, "Active", ""),
    ("FD-2300", "Large Eggs, Cage-Free", HDC, "23000", "15 dozen", "each", 54.00, None, None, "Active", ""),
    ("FD-2315", "Liquid Egg Whites", HDC, "23150", "12 x 32 fl oz", "L", 64.80, None, None, "Active", ""),
    ("FD-2402", "Buttermilk, Cultured", HDC, "24020", "6 x 1 qt", "L", 17.90, None, None, "Inactive", ""),
    # other suppliers (noise)
    ("CP-3010", "Lemons, Fancy 115ct", "Cascade Produce", "LEM115", "1 case", "each", 48.00, None, None, "Active", ""),
    ("CP-3022", "Blueberries, Fresh", "Cascade Produce", "BLU12", "12 x 1 pint", "kg", 42.50, None, None, "Active", "Seasonal"),
    ("CP-3031", "Granny Smith Apples", "Cascade Produce", "APL-GS88", "40 lb case", "kg", 39.75, None, None, "Active", ""),
    ("CP-3044", "Baby Spinach", "Cascade Produce", "SPN4", "4 lb case", "kg", 18.20, None, None, "Active", ""),
    ("CP-3050", "Yellow Onions, Jumbo", "Cascade Produce", "ONY50", "50 lb sack", "kg", 31.00, None, None, "Active", ""),
    ("CP-3062", "Cranberries, Fresh", "Cascade Produce", "CRN24", "24 x 12 oz", "kg", 44.40, None, None, "Inactive", "Holiday only"),
    ("BC-4001", "Espresso Blend, Whole Bean", "Bridgetown Coffee Roasters", "BT-ESP-5", "5 lb bag", "kg", 58.75, None, None, "Active", ""),
    ("BC-4002", "House Drip, Whole Bean", "Bridgetown Coffee Roasters", "BT-HSE-5", "5 lb bag", "kg", 52.50, None, None, "Active", ""),
    ("BC-4010", "Decaf Swiss Water", "Bridgetown Coffee Roasters", "BT-DCF-5", "5 lb bag", "kg", 61.25, None, None, "Active", ""),
    ("BC-4020", "Chai Concentrate", "Bridgetown Coffee Roasters", "BT-CHAI-32", "6 x 32 fl oz", "L", 47.40, None, None, "Active", ""),
    ("RC-5010", "Baking Cups 2.5 in White", "Rose City Paper & Packaging", "BC-25W", "10 x 500", "each", 54.90, None, None, "Inactive",
     "Switched to Halvorsen cups in 2025."),
    ("RC-5021", "Hot Cups 12 oz", "Rose City Paper & Packaging", "HC-12", "1000 ct", "each", 96.00, None, None, "Active", ""),
    ("RC-5022", "Hot Cup Lids 12/16 oz", "Rose City Paper & Packaging", "LID-1216", "1000 ct", "each", 41.00, None, None, "Active", ""),
    ("RC-5030", "Pastry Bags, Kraft 6x9", "Rose City Paper & Packaging", "PB-69K", "2000 ct", "each", 62.40, None, None, "Active", ""),
    ("RC-5041", "Cake Boxes 10 in", "Rose City Paper & Packaging", "CB-10", "100 ct", "each", 58.00, None, None, "Active", ""),
    ("RC-5050", "Parchment Roll 15 in", "Rose City Paper & Packaging", "PR-15", "1 roll", "each", 24.60, None, None, "Active", ""),
    ("WV-6010", "Marionberry Preserves", "Willamette Valley Fruit Co.", "MB-JAM-4", "4 x 1 gal", "L", 88.00, None, None, "Active", ""),
    ("WV-6020", "Frozen Raspberries IQF", "Willamette Valley Fruit Co.", "RAS-IQF-30", "30 lb case", "kg", 112.50, None, None, "Active", ""),
]
ITEM_COLS = ["code", "desc", "supplier", "sku", "pack", "unit", "case", "cprice", "cends", "status", "notes"]
ITEM = {r[0]: dict(zip(ITEM_COLS, r)) for r in ITEMS}


def rec_id(code: str) -> str:
    return "rec_" + code.lower().replace("-", "")


def m2(x) -> str:
    return f"{x:.2f}"


# ---------------------------------------------------------------- truth
def compute(version=2, keep="latest", effective=EFFECTIVE, by_sku_only=False, include_inactive=False,
            metric=True, use_base_pack=False, contract_rule="normal", skip_disc=True, date_fmt="iso"):
    """Return (rows as dicts sorted by item_code, set of Price Review codes, set of discontinued codes)
    under a given reading of the rules. Row dicts hold formatted strings."""
    cat_rows = catalog(version)
    lines = dedupe(cat_rows, keep) if keep else None
    if keep is None:   # no dedupe at all: every line
        lines_list = cat_rows
    else:
        lines_list = list(lines.values())
    rows, review, disc = [], set(), set()
    for line in lines_list:
        matches = [it for it in ITEM.values() if it["sku"] == line["item_no"] and (by_sku_only or it["supplier"] == HMP)]
        for it in matches:
            if it["status"] != "Active" and not include_inactive:
                continue
            if line["status"] == "DISC":
                disc.add(it["code"])
                if skip_disc:
                    continue
            if it["cends"]:
                if contract_rule == "normal" and it["cends"] >= effective:
                    continue
                if contract_rule == "exclude_all":
                    continue
                if contract_rule == "strict_after" and it["cends"] > effective:   # treats end date == effective as expired
                    continue
            pack, size, price = line["pack"], float(line["size"]), float(line["price"])
            if line["basis"] == "CS":
                case_price = price
            else:   # LB / EA: price per pound or per piece
                case_price = price * pack * size
            case_price = round(case_price + 1e-9, 2)
            uom = line["uom"]
            if use_base_pack and it["code"] == "FP-1030":
                pack, size, uom = 4, 32.0, "FL OZ"
            if metric:
                unit = UNIT_CODE[it["unit"]]
                if unit != "EA" and uom not in (TO_KG if unit == "KG" else TO_L):   # wrong-supplier match
                    unit = "KG" if uom in TO_KG else "L"
                if unit == "KG":
                    qty = pack * size * TO_KG[uom]
                elif unit == "L":
                    qty = pack * size * TO_L[uom]
                else:
                    qty = pack * size
            else:
                unit, qty = uom, pack * size
            eff = effective if date_fmt == "iso" else f"{effective[5:7]}/{effective[8:10]}/{effective[:4]}"
            rows.append({"item_code": it["code"], "supplier_sku": line["item_no"], "case_price": m2(case_price),
                         "case_qty": f"{qty:.3f}", "cost_unit": unit, "cost_per_unit": f"{case_price / qty:.4f}",
                         "effective_date": eff})
            if case_price > it["case"] * (1 + REVIEW_PCT) + 1e-9:
                review.add(it["code"])
    rows.sort(key=lambda r: (r["item_code"], r["supplier_sku"]))
    return rows, review, disc


def csv_text(header, rows, eol="\n"):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator=eol)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def price_file(rows) -> str:
    return csv_text(HEADER, [[r[h] for h in HEADER] for r in rows])


def catalog_text(version: int) -> str:
    rows = CATALOG_V1 + (REVB_APPENDED if version == 2 else [])
    return csv_text(CAT_HEADER, [list(r) for r in rows], eol="\r\n")


# ---------------------------------------------------------------- Airtable
C = {
    "blue": "bg-[#D0F0FD] text-[#18618A]", "cyan": "bg-[#C2F5E9] text-[#20715A]", "green": "bg-[#D1F7C4] text-[#2D7514]",
    "yellow": "bg-[#FFEAB6] text-[#8D6302]", "orange": "bg-[#FEE2D5] text-[#B3540E]", "red": "bg-[#FFDCE5] text-[#B31846]",
    "purple": "bg-[#EDE2FE] text-[#6B1CB0]", "gray": "bg-[#EEEEEE] text-[#444444]",
}
PEOPLE = [("user_1", "Priya Raman", PRIYA[1]), ("user_2", "Dana Okafor", DANA[1]),
          ("user_3", "Marco Bellini", "marco.bellini@fennwickprovisions.com"),
          ("user_4", "Jules Tran", "jules.tran@fennwickprovisions.com"),
          ("user_5", "Sam Whitaker", "sam.whitaker@fennwickprovisions.com")]


def collaborator(uid, name, email):
    return {"id": uid, "name": name, "email": email, "avatar": avatar(name)}


def grid_view(vid, name, filters=None, sorts=None):
    return {"id": vid, "name": name, "type": "grid", "filters": filters or [], "sorts": sorts or [], "groupBy": [],
            "hiddenFieldIds": [], "fieldWidths": {}, "rowHeight": "short"}


def build_airtable():
    collabs = [collaborator(*p) for p in PEOPLE]
    sup_names = [s[1] for s in SUPPLIERS]
    colors = ["blue", "orange", "green", "purple", "cyan", "red"]
    item_fields = [
        {"id": "fld_code", "name": "Item Code", "type": "text", "primary": True},
        {"id": "fld_desc", "name": "Description", "type": "text"},
        {"id": "fld_supplier", "name": "Supplier", "type": "single_select",
         "options": [{"id": f"sup_opt_{i}", "name": n, "color": C[colors[i]]} for i, n in enumerate(sup_names)]},
        {"id": "fld_sku", "name": "Supplier SKU", "type": "text"},
        {"id": "fld_pack", "name": "Pack", "type": "text", "description": "Pack as last ordered"},
        {"id": "fld_unit", "name": "Costing Unit", "type": "single_select",
         "options": [{"id": "unit_kg", "name": "kg", "color": C["cyan"]}, {"id": "unit_l", "name": "L", "color": C["blue"]},
                     {"id": "unit_each", "name": "each", "color": C["yellow"]}]},
        {"id": "fld_case", "name": "Case Price", "type": "currency"},
        {"id": "fld_cprice", "name": "Contract Price", "type": "currency"},
        {"id": "fld_cends", "name": "Contract Ends", "type": "text"},   # text: the mock renders date-only values a day early west of UTC
        {"id": "fld_status", "name": "Status", "type": "single_select",
         "options": [{"id": "st_active", "name": "Active", "color": C["green"]},
                     {"id": "st_inactive", "name": "Inactive", "color": C["gray"]},
                     {"id": "st_disc", "name": "Discontinued", "color": C["red"]}]},
        {"id": "fld_review", "name": "Price Review", "type": "checkbox"},
        {"id": "fld_notes", "name": "Notes", "type": "long_text"},
    ]
    records = []
    for i, r in enumerate(ITEMS):
        it = dict(zip(ITEM_COLS, r))
        fields = {"fld_code": it["code"], "fld_desc": it["desc"], "fld_supplier": it["supplier"], "fld_sku": it["sku"],
                  "fld_pack": it["pack"], "fld_unit": it["unit"], "fld_case": it["case"], "fld_status": it["status"],
                  "fld_review": False}
        if it["cprice"] is not None:
            fields["fld_cprice"] = it["cprice"]
            fields["fld_cends"] = it["cends"]
        if it["notes"]:
            fields["fld_notes"] = it["notes"]
        records.append({"id": rec_id(it["code"]), "createdTime": f"2025-0{1 + i % 9}-1{i % 10}T17:00:00.000Z", "fields": fields})
    # one Halvorsen Dairy item already flagged from an earlier review: must stay as is
    for rec in records:
        if rec["id"] == "rec_fd2210":
            rec["fields"]["fld_review"] = True
            rec["fields"]["fld_notes"] = "Ben says block price up again in January - check before next order."
    items_table = {
        "id": "tbl_items", "name": "Supplier Items", "baseId": "base_fwp", "fields": item_fields, "records": records,
        "views": [grid_view("view_items_all", "All Items"),
                  grid_view("view_items_active", "Active Items",
                            filters=[{"id": "flt_active", "fieldId": "fld_status", "operator": "is", "value": "Active"}]),
                  {"id": "view_items_kanban", "name": "By Supplier", "type": "kanban", "groupFieldId": "fld_supplier"}],
        "activeViewId": "view_items_all",
    }
    sup_fields = [
        {"id": "fld_s_name", "name": "Supplier", "type": "text", "primary": True},
        {"id": "fld_s_rep", "name": "Rep", "type": "text"},
        {"id": "fld_s_email", "name": "Rep Email", "type": "email"},
        {"id": "fld_s_phone", "name": "Phone", "type": "phone"},
        {"id": "fld_s_account", "name": "Account #", "type": "text"},
        {"id": "fld_s_terms", "name": "Terms", "type": "single_select",
         "options": [{"id": "t_n15", "name": "Net 15", "color": C["blue"]}, {"id": "t_n30", "name": "Net 30", "color": C["purple"]},
                     {"id": "t_cod", "name": "COD", "color": C["orange"]}]},
        {"id": "fld_s_eff", "name": "Prices Effective", "type": "text"},
        {"id": "fld_s_notes", "name": "Notes", "type": "long_text"},
    ]
    sup_records = [{"id": sid, "createdTime": "2024-06-03T17:00:00.000Z",
                    "fields": {"fld_s_name": n, "fld_s_rep": rep, "fld_s_email": em, "fld_s_phone": ph, "fld_s_account": acct,
                               "fld_s_terms": terms, "fld_s_eff": eff, "fld_s_notes": notes}}
                   for sid, n, rep, em, ph, acct, terms, eff, notes in SUPPLIERS]
    sup_table = {"id": "tbl_suppliers", "name": "Suppliers", "baseId": "base_fwp", "fields": sup_fields, "records": sup_records,
                 "views": [grid_view("view_sup_all", "All Suppliers")], "activeViewId": "view_sup_all"}
    loc_fields = [{"id": "fld_l_name", "name": "Location", "type": "text", "primary": True},
                  {"id": "fld_l_addr", "name": "Address", "type": "text"},
                  {"id": "fld_l_lead", "name": "Kitchen Lead", "type": "text"},
                  {"id": "fld_l_day", "name": "Dry Goods Delivery", "type": "single_select",
                   "options": [{"id": "d_mon", "name": "Monday", "color": C["blue"]}, {"id": "d_wed", "name": "Wednesday", "color": C["green"]},
                               {"id": "d_thu", "name": "Thursday", "color": C["yellow"]}]}]
    locs = [("rec_loc_1", "Fennwick Alberta", "2914 NE Alberta St", "Marco Bellini", "Monday"),
            ("rec_loc_2", "Fennwick Division", "3350 SE Division St", "Jules Tran", "Wednesday"),
            ("rec_loc_3", "Fennwick Pearl", "1105 NW Lovejoy St", "Sam Whitaker", "Monday"),
            ("rec_loc_4", "Fennwick Commissary", "740 SE Taylor St", "Marco Bellini", "Thursday")]
    loc_table = {"id": "tbl_locations", "name": "Locations", "baseId": "base_fwp", "fields": loc_fields,
                 "records": [{"id": i, "createdTime": "2024-06-03T17:00:00.000Z",
                              "fields": {"fld_l_name": n, "fld_l_addr": a, "fld_l_lead": l, "fld_l_day": d}} for i, n, a, l, d in locs],
                 "views": [grid_view("view_loc_all", "All Locations")], "activeViewId": "view_loc_all"}
    return {
        "currentUser": collabs[0],
        "collaborators": collabs,
        "bases": {"base_fwp": {"id": "base_fwp", "name": "Fennwick Purchasing", "color": "bg-teal-600",
                               "tables": ["tbl_items", "tbl_suppliers", "tbl_locations"]}},
        "tables": {"tbl_items": items_table, "tbl_suppliers": sup_table, "tbl_locations": loc_table},
        "activeBaseId": "base_fwp",
        "activeTableId": "tbl_items",
        "ui": {"viewSidebarOpen": False, "expandedRecordId": None, "searchQuery": "", "isSearching": False, "buttonActionLog": []},
    }


def apply_airtable(at, disc=(), review=(), effective=EFFECTIVE):
    recs = {r["id"]: r for r in at["tables"]["tbl_items"]["records"]}
    for code in disc:
        if code in ITEM and ITEM[code]["status"] == "Active":
            recs[rec_id(code)]["fields"]["fld_status"] = "Discontinued"
    for code in review:
        recs[rec_id(code)]["fields"]["fld_review"] = True
    if effective:
        for r in at["tables"]["tbl_suppliers"]["records"]:
            if r["id"] == "rec_sup_hmp":
                r["fields"]["fld_s_eff"] = effective


# ---------------------------------------------------------------- Gmail
def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def gmail_email(eid, sender, subject, body, ts, *, thread=None, read=False, category="primary", attachments=None,
                folder="inbox", to=None, starred=False, important=False, labels=None):
    return {"id": eid, "threadId": thread or f"t_{eid}",
            "from": {"name": sender[0], "email": sender[1], "avatar": avatar(sender[0])},
            "to": to or [{"name": PRIYA[0], "email": PRIYA[1]}], "cc": [], "bcc": [], "subject": subject, "body": body,
            "snippet": "", "timestamp": ts, "read": read, "starred": starred, "important": important, "labels": labels or [],
            "category": category, "folder": folder, "attachments": attachments or []}


def kb(n: int) -> str:
    return f"{max(1, round(n / 1024))} KB"


DANA_BODY = p(
    "Hi Priya,",
    "Halvorsen's 2027 price list has to be in Plateful before their new prices start, otherwise December recipe costs will be off. "
    "Marta sent it to you. Here's how I want it loaded:",
    "Only items we buy from Halvorsen Mill &amp; Pantry that are Active in the Supplier Items table in Airtable. Halvorsen Dairy Co-op "
    "is a different company (Ben's side of the family) with its own item numbers, so match on supplier as well as SKU. "
    "Plateful uses the same item codes as our Item Code column.",
    "If an item is on a contract price that runs through the day the new prices take effect, leave it out of the file. Plateful "
    "already has the contract price. If the contract ends before that day, it gets the new list price like everything else.",
    "Anything Halvorsen lists as discontinued stays out of the file, and set its Status in Airtable to Discontinued so nobody orders it.",
    "Please don't type the new prices into Airtable. Plateful's nightly sync writes case prices back once the import is in. "
    "But if an item's new case price is more than 8% above the Case Price we have in Airtable now, tick Price Review on it so I can "
    "look at it before the next order. And put the date the new prices take effect in Prices Effective on Halvorsen's row in Suppliers.",
    "Plateful only accepts files mailed from the old fennwickbakery Yahoo account the subscription was set up under. Their "
    "instructions are in that inbox, follow whatever they currently ask for.",
    "Thanks!<br>Dana")


def build_gmail(sizes):
    hdc = ("Ben Halvorsen", "ben@halvorsendairy.coop")
    att = lambda aid, name: {"id": aid, "name": name, "size": kb(sizes[name]), "type": "text/csv", "url": file_url(name)}  # noqa: E731
    emails = [
        gmail_email("g01", MARTA, "Halvorsen Mill & Pantry - 2027 price list",
                    p("Hi Priya,",
                      "Attached is our 2027 wholesale price list for Fennwick. New prices take effect Tuesday, December 1; "
                      "deliveries before then are billed at current prices.",
                      "How to read the sheet: Pack is the number of units in a case and Size/UOM is what each unit holds. "
                      "Price Basis says what the price is for: CS = per case, LB = per pound, EA = per piece. Items marked DISC "
                      "are discontinued and can't be ordered after November; NEW items are new to our line.",
                      "Let me know if anything looks off.",
                      "Marta Lindqvist<br>Account Manager, Halvorsen Mill &amp; Pantry"),
                    "2026-11-13T18:42:00Z", thread="t_hmp", read=True, attachments=[att("att_hmp_v1", V1_NAME)]),
        gmail_email("g02", MARTA, "Re: Halvorsen Mill & Pantry - 2027 price list",
                    p("Hi Priya,",
                      "Two corrections to Friday's list, sorry for the trouble. The increase now takes effect Monday, December 7 "
                      "instead of December 1, because our mill contract renewal slipped a week.",
                      "A few lines on the sheet were also wrong. Rather than redo the whole file I added the corrected lines at the "
                      "bottom of the attached rev B with a November 16 revision date. Where an item number shows up more than once, "
                      "the line with the latest Revised date is the one that stands. Please use rev B in place of the first file.",
                      "Marta"),
                    "2026-11-16T23:05:00Z", thread="t_hmp", attachments=[att("att_hmp_v2", V2_NAME)]),
        gmail_email("g03", DANA, "Loading the Halvorsen price list", DANA_BODY, "2026-11-18T00:20:00Z", starred=True, important=True),
        gmail_email("g04", hdc, "Halvorsen Dairy Co-op - January 2027 prices",
                    p("Hi Priya,", "Our January prices are attached, effective January 4, 2027. Butter is up a little again, "
                      "cream is flat. Holiday cream allocations are confirmed as ordered.", "Ben Halvorsen<br>Halvorsen Dairy Co-op"),
                    "2026-11-12T21:10:00Z", read=True, attachments=[att("att_hdc", DAIRY_NAME)]),
        gmail_email("g05", ("Marco Bellini", "marco.bellini@fennwickprovisions.com"), "Butter usage up at the commissary",
                    p("Priya, croissant volume is up about 20% since the Pearl opened, we went through 14 cases of the Halvorsen "
                      "Dairy butter last week. Can we bump the standing order before Thanksgiving? Marco"),
                    "2026-11-17T15:32:00Z", read=True),
        gmail_email("g06", ("Bridgetown Coffee Roasters", "wholesale@bridgetowncoffee.com"), "Invoice BCR-88213",
                    p("Invoice BCR-88213 for $1,284.50 is attached to your account portal. Terms Net 30."),
                    "2026-11-16T17:00:00Z", read=True),
        gmail_email("g07", ("Cascade Produce", "orders@cascadeproduce.com"), "This week's availability",
                    p("Fresh cranberries back through December. Blueberries are now Chilean, price up $4 a flat. Order by 2pm Monday for Tuesday drop."),
                    "2026-11-17T13:00:00Z", category="promotions"),
        gmail_email("g08", ("Rose City Paper & Packaging", "sales@rosecitypaper.com"), "Order RC-55190 shipped",
                    p("Your order RC-55190 (hot cups, lids, cake boxes) shipped today and will arrive Thursday."),
                    "2026-11-17T20:15:00Z", read=True),
        gmail_email("g09", DANA, "Holiday hours",
                    p("Team, Thanksgiving: all cafes close at 2pm Wednesday and stay closed Thursday. Commissary runs a short shift Friday. Dana"),
                    "2026-11-15T19:00:00Z", read=True),
        gmail_email("g10", ("Toast", "no-reply@toasttab.example.com"), "Weekly sales summary - Fennwick Provisions",
                    p("Net sales last week: $48,912. Top item: Morning Bun (1,212 sold)."),
                    "2026-11-17T09:00:00Z", category="promotions", read=True),
        gmail_email("g11", ("Jules Tran", "jules.tran@fennwickprovisions.com"), "Division walk-in temp",
                    p("Heads up, the walk-in at Division read 42F this morning. Tech is coming at 3. Nothing lost so far. Jules"),
                    "2026-11-18T15:10:00Z"),
        gmail_email("g12", ("Google Workspace", "workspace-noreply@google.example.com"), "Your storage is 82% full",
                    p("Upgrade your plan or free up space."), "2026-11-14T12:00:00Z", category="promotions", read=True),
        gmail_email("g13", ("Willamette Valley Fruit Co.", "grace@wvfruitco.com"), "Marionberry preserves - last call",
                    p("Hi Priya! Last pressing of the year, we can hold 6 more gallons of the marionberry for you until Friday. Grace"),
                    "2026-11-16T18:25:00Z", read=True),
        gmail_email("g14", PRIYA, "Re: 2027 pricing?",
                    p("Hi Marta, any update on the 2027 list? We need it a couple of weeks ahead to update costing. Thanks, Priya"),
                    "2026-11-09T17:30:00Z", thread="t_hmp_ask", folder="sent",
                    to=[{"name": MARTA[0], "email": MARTA[1]}], read=True),
        gmail_email("g15", MARTA, "Re: 2027 pricing?",
                    p("Hi Priya, it's with our pricing team, you'll have it by Friday. Marta"),
                    "2026-11-09T22:02:00Z", thread="t_hmp_ask", read=True),
        gmail_email("g16", ("LinkedIn", "messages-noreply@linkedin.example.com"), "Priya, you appeared in 9 searches this week",
                    p("See who's looking at your profile."), "2026-11-16T08:00:00Z", category="social", read=True),
    ]
    for e in emails:
        e["snippet"] = " ".join(e["body"].replace("<p>", " ").replace("</p>", " ").replace("<br>", " ").replace("&amp;", "&").split())[:110]
    return {
        "user": {"userId": "u1", "username": PRIYA[0], "email": PRIYA[1], "avatar": avatar(PRIYA[0])},
        "emails": emails,
        "labels": [{"id": "l1", "name": "Suppliers", "color": "#3b82f6"}, {"id": "l2", "name": "Team", "color": "#22c55e"}],
        "drafts": [],
        "settings": {"signature": "--\nPriya Raman\nOperations Analyst, Fennwick Provisions", "undoSend": 5},
    }


# ---------------------------------------------------------------- Yahoo Mail
def yahoo_attachment(aid, name, size, source="seed", url=None, uploaded=None):
    return {"id": aid, "name": name, "size": size, "mimeType": "text/csv", "kind": "document", "url": url or file_url(name),
            "source": source, "uploadedAt": uploaded, "sourceMessageId": None, "sourceAttachmentId": None}


def ymsg(mid, conv, sender, subject, body, date, *, folder="inbox", category="primary", read=False, attachments=None,
         to=None, reply_to_id=None, starred=False):
    received = folder not in ("sent", "draft")
    me = {"name": YAHOO_USER[0], "email": YAHOO_USER[1]}
    return {"id": mid, "conversationId": conv, "folderId": folder, "previousFolderId": None, "category": category,
            "from": {"name": sender[0], "email": sender[1]} if received else me,
            "to": to or ([me] if received else []), "cc": [], "bcc": [], "replyTo": None, "subject": subject,
            "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None, "date": date,
            "isRead": read or not received, "isStarred": starred, "isDraft": False,
            "status": "received" if received else "sent", "attachments": attachments or [], "hasImages": False,
            "listUnsubscribe": category in ("offers", "newsletters"), "summary": None, "orderInfo": None, "travelInfo": None,
            "inReplyToId": reply_to_id, "forwardedFromId": None, "replyType": "reply" if reply_to_id and not received else None,
            "repliedAt": None, "forwardedAt": None, "sentAt": None if received else date, "movedAt": None,
            "appliedFilterId": None, "createdAt": date, "updatedAt": None}


PLATEFUL_V2 = """Hi Fennwick Bakery,

Welcome to Plateful! To update supplier prices, email a CSV file to imports@plateful.app. We pick up attachments every 15 minutes and email you a receipt.

Columns, in this order:
item_code,supplier_sku,case_price,case_qty,cost_unit,cost_per_unit,effective_date

item_code: the item code from your Plateful item list
supplier_sku: the supplier's item number
case_price: price of one case in USD
case_qty: how much one case holds, in cost_unit
cost_unit: any unit from your supplier's price list (LB, OZ, KG, G, GAL, FL OZ, L, ML, EA). We convert for you.
cost_per_unit: case_price divided by case_qty
effective_date: MM/DD/YYYY

Questions? Just reply to this email.
Plateful Support"""

PLATEFUL_V3 = """Hello Fennwick Bakery,

From November 1, 2026 Plateful costs every ingredient in metric, and price files must use the v3 layout below. Files in the old layout are rejected.

Format: CSV (comma-separated, UTF-8), one header row, then one row per item:
item_code,supplier_sku,case_price,case_qty,cost_unit,cost_per_unit,effective_date

item_code: the item code from your item list
supplier_sku: the supplier's item number as printed on their price list
case_price: USD for one case, two decimals, no currency symbol
case_qty: how much one case holds, expressed in cost_unit, three decimals
cost_unit: the costing unit of the item in your item list, written as KG, L or EA. Imperial units are no longer accepted. Convert with 1 lb = 0.45359237 kg, 1 oz = 28.349523125 g, 1 US gal = 3.785411784 L, 1 US fl oz = 29.5735295625 mL.
cost_per_unit: case_price divided by case_qty, four decimals
effective_date: the date the price takes effect, YYYY-MM-DD

If an item_code appears more than once in a file, the last row silently overwrites the earlier ones, so send each item once.

Send files as an attachment to your account's private import address: fennwick-7q2k@imports.plateful.app
The shared imports@plateful.app inbox is retired together with the old layout. Files must come from the address that owns the account (fennwickbakery@yahoo.com).

The Plateful team"""


def build_yahoo(old_size):
    plat_s = ("Plateful Support", "support@plateful.app")
    plat_u = ("Plateful", "updates@plateful.app")
    msgs = [
        ymsg("ym_001", "cnv_plat_v2", plat_s, "Your Plateful price-file template", PLATEFUL_V2, "2025-03-04T18:20:00.000Z", read=True),
        ymsg("ym_002", "cnv_plat_v3", plat_u, "Price files: new import spec from November 1", PLATEFUL_V3, "2026-10-06T16:00:00.000Z",
             read=True, starred=True),
        ymsg("ym_003", "cnv_cascade_imp", YAHOO_USER, "Cascade price file", "Cascade Produce prices for August, attached.\n\nPriya",
             "2026-08-21T20:02:00.000Z", folder="sent", to=[{"name": "", "email": OLD_IMPORT_ADDR}],
             attachments=[yahoo_attachment("att_cascade", OLD_UPLOAD_NAME, old_size)]),
        ymsg("ym_004", "cnv_cascade_imp", ("Plateful", "receipts@plateful.app"), "Import complete: cascade_prices_aug.csv",
             "We imported cascade_prices_aug.csv: 6 rows, 6 updated, 0 errors. Recipe costs were recalculated.",
             "2026-08-21T20:17:00.000Z", read=True, reply_to_id=None),
        ymsg("ym_005", "cnv_plat_tips", plat_u, "3 ways to keep recipe costs current",
             "Set a reminder for supplier price changes, review plate costs monthly, and use menu engineering reports.",
             "2026-11-04T16:00:00.000Z", category="newsletters"),
        ymsg("ym_006", "cnv_square1", ("Square", "noreply@squareup.example.com"), "Your transfer of $612.40 is on its way",
             "Farmers market card sales from Saturday were transferred to your bank account ending 2207.",
             "2026-11-16T14:00:00.000Z", read=True, category="offers"),
        ymsg("ym_007", "cnv_pfm", ("Portland Farmers Market", "vendors@portlandfarmersmarket.example.org"),
             "Winter market vendor schedule",
             "Winter market runs Saturdays 10-2 at Shemanski Park from December 5. Confirm your booth by November 25.",
             "2026-11-10T19:00:00.000Z", read=True),
        ymsg("ym_008", "cnv_costco", ("Costco Business Center", "business@costco.example.com"), "This week's business deals",
             "Restaurant-size butter, eggs and paper goods on sale through Sunday.", "2026-11-15T13:00:00.000Z", category="offers"),
        ymsg("ym_009", "cnv_yelp", ("Yelp for Business", "no-reply@yelp.example.com"), "New review for Fennwick Bakery",
             "\"Best morning bun in Portland, the cardamom one is unreal.\" - 5 stars", "2026-11-14T22:00:00.000Z", read=True, category="social"),
        ymsg("ym_010", "cnv_nextdoor", ("Nextdoor", "updates@nextdoor.example.com"), "Trending near Alberta Arts",
             "Holiday lights walk this Friday, plus 12 more posts.", "2026-11-17T08:00:00.000Z", category="social"),
        ymsg("ym_011", "cnv_bank", ("Umpqua Bank", "alerts@umpqua.example.com"), "Your statement is ready",
             "Your October business checking statement is available online.", "2026-11-05T12:00:00.000Z", read=True, category="offers"),
        ymsg("ym_012", "cnv_insta", ("Instagram", "no-reply@mail.instagram.example.com"), "fennwickbakery, you have 18 new followers",
             "See who followed you this week.", "2026-11-16T09:00:00.000Z", read=True, category="social"),
        ymsg("ym_013", "cnv_olddomain", ("GoDaddy", "renewals@godaddy.example.com"), "fennwickbakery.com renews in 30 days",
             "Your domain fennwickbakery.com renews automatically on December 18.", "2026-11-18T07:00:00.000Z", category="offers"),
        ymsg("ym_014", "cnv_plat_bill", ("Plateful Billing", "billing@plateful.app"), "Receipt for your Plateful subscription",
             "Plateful Pro, 4 locations: $196.00 charged to Visa ending 4471.", "2026-11-01T15:00:00.000Z", read=True),
    ]
    folders = [{"id": fid, "name": name, "type": "system", "parentId": None, "order": i, "createdAt": "2019-04-02T16:00:00.000Z"}
               for i, (fid, name) in enumerate([("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"),
                                                ("spam", "Spam"), ("trash", "Trash")])]
    contacts = [{"id": f"ct_{i:04d}", "firstName": n.split()[0], "lastName": n.split()[-1] if " " in n else "", "nickname": "",
                 "emails": [{"type": "work", "address": e}], "phones": [], "addresses": [], "company": c, "jobTitle": "",
                 "birthday": "", "website": "", "notes": "", "isFavorite": False, "source": "manual",
                 "createdAt": "2025-03-04T16:00:00.000Z", "updatedAt": None}
                for i, (n, e, c) in enumerate([("Plateful Support", "support@plateful.app", "Plateful"),
                                               ("Plateful Imports", OLD_IMPORT_ADDR, "Plateful"),
                                               ("Priya Raman", PRIYA[1], "Fennwick Provisions"),
                                               ("Dana Okafor", DANA[1], "Fennwick Provisions")], 1)]
    return {
        "currentUser": {"id": "usr_fennwick", "name": YAHOO_USER[0], "firstName": "Fennwick", "email": YAHOO_USER[1], "aliases": [],
                        "avatarColor": "#8D6E63", "jobTitle": "", "company": "Fennwick Provisions", "location": "Portland, OR",
                        "storage": {"usedBytes": 2412345678, "totalBytes": 1099511627776}},
        "folders": folders, "messages": msgs, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {"writing": {"signature": {"enabled": False, "text": ""}, "defaultFont": "sans-serif",
                                 "defaultFontSize": "medium", "defaultFrom": YAHOO_USER[1], "sendWithCtrlEnter": True,
                                 "linkPreviews": True}},
    }


def stored_name(text: str, name: str = OUT_NAME) -> str:
    return hashlib.sha256(("fwp-golden-" + text).encode()).hexdigest()[:8] + "_" + name


def apply_yahoo(yahoo, text, to_addr=IMPORT_ADDR, name=OUT_NAME):
    """Compose -> attach from computer (POST /upload) -> send, as the Yahoo mock records it."""
    stored = stored_name(text, name)
    mid, aid = "msg_golden_plateful", "att_golden_plateful"
    t0, t1, t2 = "2026-11-18T18:36:00.000Z", "2026-11-18T18:38:00.000Z", NOW_Z
    file = yahoo_attachment(aid, name, len(text.encode()), source="upload", url=f"/files/__SID__/{stored}", uploaded=t1)
    me = {"name": YAHOO_USER[0], "email": YAHOO_USER[1]}
    body = "Halvorsen Mill & Pantry 2027 prices, effective December 7, attached.\n\nPriya"
    msg = ymsg(mid, "cnv_golden_plateful", YAHOO_USER, "Halvorsen Mill & Pantry price file", body, t2, folder="sent",
               to=[{"name": "", "email": to_addr}], attachments=[file])
    msg.update({"from": me, "createdAt": t0, "updatedAt": t2, "sentAt": t2, "date": t2, "category": "primary"})
    yahoo["messages"].append(msg)
    details = {"attachmentId": aid, "name": name, "size": file["size"], "mimeType": "text/csv", "url": file["url"]}
    base = {"actor": YAHOO_USER[1], "folderIds": [], "filterIds": [], "contactIds": [], "listIds": []}
    yahoo["activityLog"] += [
        {"id": "act_g1", "type": "draft.save", "createdAt": t0, "messageIds": [mid], **base,
         "details": {"changedFields": ["to", "subject", "body"], "isNew": True}},
        {"id": "act_g2", "type": "attachment.upload", "createdAt": t1, "messageIds": [mid], **base, "details": details},
        {"id": "act_g3", "type": "message.send", "createdAt": t2, "messageIds": [mid], **{**base, "folderIds": ["sent"]},
         "details": {"to": msg["to"], "cc": [], "bcc": [], "subject": msg["subject"], "attachmentIds": [aid],
                     "originalMessageId": None, "incomingCopyIds": []}},
    ]
    return stored


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def variant(seed, *, rows=None, review=(), disc=(), effective_at=EFFECTIVE, to_addr=IMPORT_ADDR, local=True, upload=True):
    gmail, yahoo, at = (copy.deepcopy(seed[k]) for k in ("gmail", "yahoo_mail", "airtable"))
    files, out = {}, None
    if rows is not None:
        text = price_file(rows)
        if upload:
            files[apply_yahoo(yahoo, text, to_addr)] = text
        if local:
            out = text
    for e in gmail["emails"]:
        if e["id"] in ("g02", "g03"):
            e["read"] = True
    apply_airtable(at, disc=disc, review=review, effective=effective_at)
    return {"gmail": gmail, "yahoo_mail": yahoo, "airtable": at}, files, out


def main(out: Path):
    v1, v2 = catalog_text(1), catalog_text(2)
    dairy = csv_text(["Item", "Description", "Pack", "Price", "Effective"],
                     [["12040", "Cultured Butter Unsalted 83%", "36 x 1 lb", "149.40", "2027-01-04"],
                      ["10421", "Whole Milk Organic", "4 x 1 gal", "21.80", "2027-01-04"],
                      ["20105", "Heavy Cream 40%", "4 x 0.5 gal", "38.40", "2027-01-04"],
                      ["22210", "Cream Cheese Block", "10 x 3 lb", "101.20", "2027-01-04"],
                      ["23000", "Large Eggs Cage-Free", "15 dozen", "52.50", "2027-01-04"],
                      ["23150", "Liquid Egg Whites", "12 x 32 fl oz", "64.80", "2027-01-04"]], eol="\r\n")
    old_upload = csv_text(HEADER, [["CP-3010", "LEM115", "46.00", "1", "EA", "46.0000", "08/24/2026"],
                                   ["CP-3022", "BLU12", "40.50", "12", "EA", "3.3750", "08/24/2026"],
                                   ["CP-3031", "APL-GS88", "38.25", "40", "LB", "0.9563", "08/24/2026"],
                                   ["CP-3044", "SPN4", "17.60", "4", "LB", "4.4000", "08/24/2026"],
                                   ["CP-3050", "ONY50", "29.50", "50", "LB", "0.5900", "08/24/2026"],
                                   ["CP-3062", "CRN24", "44.40", "288", "OZ", "0.1542", "08/24/2026"]])
    for name, text in ((V1_NAME, v1), (V2_NAME, v2), (DAIRY_NAME, dairy)):
        write_text(out / "seed" / "files" / "gmail" / name, text)
    write_text(out / "seed" / "files" / "yahoo_mail" / OLD_UPLOAD_NAME, old_upload)

    sizes = {V1_NAME: len(v1.encode()), V2_NAME: len(v2.encode()), DAIRY_NAME: len(dairy.encode())}
    seed = {"gmail": build_gmail(sizes), "yahoo_mail": build_yahoo(len(old_upload.encode())), "airtable": build_airtable()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    rows, review, disc = compute()
    gold_states, gold_files, gold_text = variant(seed, rows=rows, review=review, disc=disc)
    for site, state in gold_states.items():
        write_json(out / "golden" / f"{site}.json", state)
    # The oracle only pushes state, so the golden upload ships as a seed file under an unguessable
    # stored name that nothing in the seed references.
    for stored, text in gold_files.items():
        write_text(out / "seed" / "files" / "yahoo_mail" / stored, text)
    write_text(out / "golden_output" / OUT_NAME, gold_text)

    # ---- truth for the verifier
    by_code = {r["item_code"]: r for r in rows}
    trap_codes = {"FP-1002", "FP-1005", "FP-1020", "FP-1022", "FP-1030"}
    expected = {
        "clock": CLOCK, "effective_date": EFFECTIVE, "superseded_effective_date": EFFECTIVE_V1,
        "header": HEADER, "import_address": IMPORT_ADDR, "retired_import_address": OLD_IMPORT_ADDR,
        "yahoo_account": YAHOO_USER[1], "local_copy": f"/workspace/output/{OUT_NAME}",
        "upload_lookup": "yahoo_mail current.messages: status=='sent', id not in initial, attachments[] with source=='upload' "
                         "and name ending .csv; file = /var/lib/cua/files/yahoo_mail/<sid>/<stored> from url /files/<sid>/<stored>",
        "tolerances": {"case_price": 0.005, "case_qty": 0.002, "cost_per_unit_abs": 0.0006, "cost_per_unit_rel": 0.0005},
        "rows": by_code,
        "ordinary_codes": sorted(c for c in by_code if c not in trap_codes),
        "revb_price_codes": {"FP-1002": "33.40", "FP-1005": "162.00", "FP-1020": "71.25"},
        "v1_prices_for_those": {"FP-1002": "32.40", "FP-1005": "155.00", "FP-1020": "64.50"},
        "contract": {"exclude": "FP-1021 (contract ends 2026-12-31 >= 2026-12-07)",
                     "include": "FP-1022 at 96.75 (contract ends 2026-12-06 < 2026-12-07)"},
        "pack_change": {"FP-1030": {"case_qty": by_code["FP-1030"]["case_qty"], "cost_per_unit": by_code["FP-1030"]["cost_per_unit"],
                                    "wrong_if_base_pack": "3.785 L / 31.6237"}},
        "must_be_absent_codes": ["FP-1004", "FP-1021", "FP-1041", "FP-1053", "FD-2040", "FD-2421", "RC-5010"],
        "airtable": {
            "table_items": "tbl_items", "table_suppliers": "tbl_suppliers",
            "record_id_rule": "rec_ + lowercase code without dash, e.g. FP-1041 -> rec_fp1041",
            "fields": {"status": "fld_status", "review": "fld_review", "case_price": "fld_case", "contract_price": "fld_cprice",
                       "contract_ends": "fld_cends", "prices_effective": "fld_s_eff"},
            "discontinue": sorted(disc), "price_review": sorted(review),
            "price_review_preexisting": ["FD-2210"],
            "supplier_record": "rec_sup_hmp", "prices_effective": EFFECTIVE,
            "prices_effective_accepted": ["2026-12-07", "12/07/2026", "12/7/2026", "Dec 7, 2026", "December 7, 2026",
                                          "2026/12/07"],
            "date_fields_are_text": "Contract Ends and Prices Effective are text fields holding ISO dates",
            "protected_supplier_records": [s[0] for s in SUPPLIERS if s[0] != "rec_sup_hmp"],
            "note": "airtable_mock deep-merges its default 'Project Tracker' base/tables (random ids) into the seed on first load; "
                    "look records up by the fixed ids above and ignore other tables.",
        },
        "review_ratios": {c: round(float(by_code[c]["case_price"]) / ITEM[c]["case"], 4) for c in by_code},
    }
    write_json(out / "expected.json", expected)

    # ---- fixtures
    v1_rows, v1_review, v1_disc = compute(version=1, effective=EFFECTIVE_V1)
    first_rows, first_review, first_disc = compute(keep="first")
    coll_rows, _, _ = compute(by_sku_only=True)
    strict_rows, strict_review, _ = compute(contract_rule="exclude_all")
    imp_rows, _, _ = compute(metric=False, date_fmt="us")
    naive_rows, naive_review, naive_disc = compute(version=1, keep=None, effective=EFFECTIVE_V1, by_sku_only=True,
                                                   include_inactive=True, metric=False, use_base_pack=True,
                                                   contract_rule="ignore", date_fmt="us")
    naive_disc = {c for c in naive_disc if c in ITEM and ITEM[c]["supplier"] == HMP}
    fixtures = {
        "golden": (gold_states, gold_files, gold_text),
        "nop": ({k: copy.deepcopy(v) for k, v in seed.items()}, {}, None),
        "naive": variant(seed, rows=naive_rows, review=naive_review, disc=naive_disc, effective_at=EFFECTIVE_V1,
                         to_addr=OLD_IMPORT_ADDR),
        "slip_v1_file": variant(seed, rows=v1_rows, review=v1_review, disc=v1_disc, effective_at=EFFECTIVE_V1),
        "slip_dedupe_first": variant(seed, rows=first_rows, review=first_review, disc=first_disc),
        "slip_dairy_collision": variant(seed, rows=coll_rows, review=review, disc=disc),
        "slip_contract_boundary": variant(seed, rows=strict_rows, review=strict_review, disc=disc),
        "slip_plateful_v2": variant(seed, rows=imp_rows, review=review, disc=disc, to_addr=OLD_IMPORT_ADDR),
    }
    for name, (states, files, text) in fixtures.items():
        base = out / "variants" / name
        for site, state in states.items():
            write_json(base / "state" / site / "current.json", state)
            write_json(base / "state" / site / "initial.json", seed[site])
        for stored, ftext in files.items():
            write_text(base / "files" / "yahoo_mail" / "__SID__" / stored, ftext)
        (base / "output").mkdir(parents=True, exist_ok=True)
        if text is not None:
            write_text(base / "output" / OUT_NAME, text)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
