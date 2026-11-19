#!/usr/bin/env python3
"""World for the larkspur-map-flatfile task (Amazon Seller Central + Yahoo Mail + Shopify, lever L13).

Writes into <out>/:
  seed/{amazon_seller,yahoo_mail,shopify}.json   initial state per site
  seed/files/yahoo_mail/<csv>                    supplier sheets attached to mails (v1, rev2, decoy)
  seed/files/amazon_seller/<golden upload>       file referenced only by the golden upload record
  golden/{amazon_seller,yahoo_mail,shopify}.json state after a correct run
  golden_output/larkspur_price_quantity.txt      local copy of the uploaded flat file
  expected.json                                  truth for the verifier
  variants/<name>/state/<site>/{initial,current}.json
  variants/<name>/files/amazon_seller/__SID__/<stored file>
  variants/<name>/output/larkspur_price_quantity.txt

Story: Tessa Lindgren co-owns Fernwood Table Co. (Minneapolis), a kitchenware shop on
Shopify and Amazon. Larkspur Pottery mailed its 2027 cost/MAP sheet, then a corrected
rev2 three days later (two MAPs, one effective date, one discontinuation). Rafael's mail
sets the rules. The work is a file round trip (lever L13): download Seller Central's
All Listings report (tab-delimited, seller-sku/asin1/...), join it locally with rev2 and
Shopify stock, write a tab-delimited Price & Quantity flat file and upload it back in
Seller Central. The uploaded file is what gets graded; Shopify price raises are the
second persisted effect.

Amazon needs two features the hub mock does not have yet (see gaps.json):
products[].minimumSellerAllowedPrice/maximumSellerAllowedPrice, an Inventory Reports
page that downloads the All Listings report, and an inventory-file upload page that
stores the file through /upload and records inventoryFileUploads[].
"""

import copy
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, product_image  # noqa: E402

CLOCK = "2026-11-18T09:30:00-06:00"
NOW_Z = "2026-11-18T16:20:00.000Z"
TODAY = "2026-11-18"
CUTOFF = "2026-11-27"                     # Black Friday: effective on or before -> switch now
BUFFER = 2

OWNER = ("Tessa Lindgren", "tessa.fernwoodtable@yahoo.com")
RAFAEL = ("Rafael Ruiz", "rafael@fernwoodtable.com")
STORE = "Fernwood Table Co."

V1_NAME = "Larkspur_MAP_2027.csv"
V2_NAME = "Larkspur_MAP_2027_rev2.csv"
DECOY_NAME = "Northwind_Glass_2027_Pricing.csv"
UPLOAD_NAME = "larkspur_price_quantity.txt"
HEADER = ["sku", "price", "minimum-seller-allowed-price", "maximum-seller-allowed-price", "quantity", "fulfillment-channel"]
REPORT_HEADER = ["seller-sku", "asin1", "item-name", "price", "minimum-seller-allowed-price",
                 "maximum-seller-allowed-price", "quantity", "fulfillment-channel", "status"]


def m(x) -> str:
    return f"{float(x):.2f}"


# ---------------------------------------------------------------- catalog
# Larkspur products on Shopify: key -> (product title, [(variant title, sku, price, stock)])
LARKSPUR = {
    "mug": ("Larkspur Speckled Stoneware Mug, 12 oz", [("Default Title", "LK-MUG-SPK", "24.00", 46)]),
    "bowl": ("Larkspur Nesting Prep Bowls, Set of 3", [("Default Title", "LK-BWL-NST3", "58.00", 12)]),
    "vase": ("Larkspur Ribbed Vase", [("Sage", "LK-VSE-RIB-SG", "44.00", 9), ("Charcoal", "LK-VSE-RIB-CH", "44.00", 1)]),
    "plate": ("Larkspur Stoneware Dinner Plates, Set of 4", [("Default Title", "LK-PLT-DIN4", "68.00", 20)]),
    "pitcher": ("Larkspur Glazed Pitcher, 64 oz", [("Default Title", "LK-PCH-LG", "52.00", 6)]),
    "candle": ("Larkspur Taper Candle Holders, Pair", [("Default Title", "LK-CND-HLD2", "27.00", 30)]),
    "spoon": ("Larkspur Spoon Rest", [("Default Title", "LK-SPN-RST", "12.00", 40)]),
    "tray": ("Larkspur Oval Serving Tray", [("Default Title", "LK-TRY-SRV", "39.00", 15)]),
    "carafe": ("Larkspur Glass-Lid Carafe, 1 L", [("Default Title", "LK-CRF-GLS", "34.00", 18)]),
    "butter": ("Larkspur Covered Butter Dish", [("Default Title", "LK-BTR-DSH", "23.00", 22)]),
    "cruet": ("Larkspur Olive Oil Cruet", [("Default Title", "LK-OIL-CRT", "18.00", 25)]),
    "salt": ("Larkspur Salt Cellar with Lid", [("Default Title", "LK-SLT-CEL", "16.00", 0)]),
}
# Archived old-mold listing, near-duplicate of the Sage vase (different SKU, more stock).
ARCHIVED = ("Larkspur Ribbed Vase - Sage", "LK-VSE-RIB-SG-23", "39.00", 14)

# Other vendors: (sku, title, vendor, shopify price, stock, type)
NOISE = [
    ("NW-VSE-RIB-SG", "Northwind Ribbed Glass Vase, Sage", "Northwind Glass", "38.00", 14, "Vases"),
    ("NW-TMB-SET6", "Northwind Recycled Glass Tumblers, Set of 6", "Northwind Glass", "42.00", 25, "Drinkware"),
    ("NW-CRF-1L", "Northwind Glass Carafe with Cork, 1 L", "Northwind Glass", "29.00", 11, "Drinkware"),
    ("NW-PCH-GLS", "Northwind Glass Pitcher, 2 qt", "Northwind Glass", "34.00", 8, "Drinkware"),
    ("NW-DEC-750", "Northwind Wine Decanter, 750 ml", "Northwind Glass", "46.00", 5, "Drinkware"),
    ("FH-NAP-OAT4", "Fernhill Linen Napkins, Oat, Set of 4", "Fernhill Linen", "32.00", 40, "Table Linen"),
    ("FH-RUN-72", "Fernhill Linen Table Runner, 72 in", "Fernhill Linen", "36.00", 18, "Table Linen"),
    ("FH-TWL-WAF2", "Fernhill Waffle Kitchen Towels, Pair", "Fernhill Linen", "18.00", 52, "Kitchen Textiles"),
    ("FH-APR-CHB", "Fernhill Chambray Apron", "Fernhill Linen", "34.00", 9, "Kitchen Textiles"),
    ("FH-PLC-4", "Fernhill Linen Placemats, Set of 4", "Fernhill Linen", "28.00", 26, "Table Linen"),
    ("CK-PAN-10", "Cobalt Carbon Steel Skillet, 10 in", "Cobalt Kitchen", "48.00", 22, "Cookware"),
    ("CK-DTO-5Q", "Cobalt Enameled Dutch Oven, 5 qt", "Cobalt Kitchen", "89.00", 7, "Cookware"),
    ("CK-KNF-CHF8", "Cobalt Chef's Knife, 8 in", "Cobalt Kitchen", "64.00", 16, "Cutlery"),
    ("CK-BRD-WAL", "Cobalt Walnut Cutting Board, Large", "Cobalt Kitchen", "58.00", 13, "Prep"),
    ("CK-TNG-12", "Cobalt Locking Tongs, 12 in", "Cobalt Kitchen", "14.00", 60, "Utensils"),
    ("CK-WSK-11", "Cobalt Balloon Whisk, 11 in", "Cobalt Kitchen", "12.00", 44, "Utensils"),
    ("FW-CND-CDR", "Fernwood Soy Candle, Cedar & Smoke", "Fernwood Table Co.", "24.00", 33, "Candles"),
    ("FW-CND-FIG", "Fernwood Soy Candle, Black Fig", "Fernwood Table Co.", "24.00", 0, "Candles"),
    ("FW-GFT-HOST", "Fernwood Hostess Gift Box", "Fernwood Table Co.", "72.00", 10, "Gifts"),
    ("FW-SPC-SET", "Fernwood Spice Jar Set of 6", "Fernwood Table Co.", "38.00", 21, "Pantry"),
    ("MB-MUG-SPK", "Maple & Birch Speckled Camp Mug", "Maple & Birch", "19.00", 28, "Drinkware"),
    ("MB-BWL-SRV", "Maple & Birch Acacia Serving Bowl", "Maple & Birch", "44.00", 12, "Serveware"),
    ("MB-SPN-SET", "Maple & Birch Olive Wood Spoon Set", "Maple & Birch", "26.00", 35, "Utensils"),
    ("MB-BRD-OLV", "Maple & Birch Olive Wood Board", "Maple & Birch", "52.00", 6, "Serveware"),
]

# Amazon listings: (amazon sku, shopify sku, channel, price, min, max, amazon qty, status)
AMAZON = [
    ("LK-MUG-SPK", "LK-MUG-SPK", "FBM", 26.99, 24.00, 30.00, 40, "Active"),
    ("LK-MUG-SPK-FBA", "LK-MUG-SPK", "FBA", 26.99, 24.00, 30.00, 118, "Active"),
    ("LK-BWL-NST3", "LK-BWL-NST3", "FBM", 64.99, 55.00, 70.00, 10, "Active"),
    ("LK-VSE-RIB-SG", "LK-VSE-RIB-SG", "FBM", 45.99, 42.00, 54.00, 9, "Active"),
    ("LK-VSE-RIB-CH", "LK-VSE-RIB-CH", "FBM", 45.99, 42.00, 54.00, 3, "Active"),
    ("LK-PLT-DIN4-FBA", "LK-PLT-DIN4", "FBA", 74.99, 66.00, 82.00, 35, "Active"),
    ("LK-PCH-LG", "LK-PCH-LG", "FBM", 54.99, 50.00, 64.00, 6, "Active"),
    ("LK-PCH-LG-FBA", "LK-PCH-LG", "FBA", 54.99, 50.00, 64.00, 22, "Active"),
    ("LK-CND-HLD2", "LK-CND-HLD2", "FBM", 28.99, 26.00, 36.00, 25, "Active"),
    ("LK-SPN-RST", "LK-SPN-RST", "FBM", 14.99, 12.00, 18.00, 30, "Active"),
    ("LK-TRY-SRV", "LK-TRY-SRV", "FBM", 42.99, 38.00, 48.00, 12, "Active"),
    ("LK-TRY-SRV-FBA", "LK-TRY-SRV", "FBA", 42.99, 38.00, 48.00, 40, "Active"),
    ("LK-CRF-GLS", "LK-CRF-GLS", "FBM", 35.99, 32.00, 42.00, 15, "Active"),
    ("LK-BTR-DSH-FBA", "LK-BTR-DSH", "FBA", 24.99, 20.00, 26.00, 28, "Active"),
    ("LK-SLT-CEL", "LK-SLT-CEL", "FBM", 16.99, 14.00, 18.00, 0, "Inactive"),
    # other vendors
    ("NW-VSE-RIB-SG", "NW-VSE-RIB-SG", "FBM", 41.99, 36.00, 48.00, 14, "Active"),
    ("NW-TMB-SET6", "NW-TMB-SET6", "FBM", 44.99, 40.00, 52.00, 20, "Active"),
    ("NW-TMB-SET6-FBA", "NW-TMB-SET6", "FBA", 44.99, 40.00, 52.00, 60, "Active"),
    ("NW-CRF-1L", "NW-CRF-1L", "FBM", 31.99, 28.00, 38.00, 11, "Active"),
    ("NW-PCH-GLS", "NW-PCH-GLS", "FBM", 36.99, 32.00, 42.00, 8, "Active"),
    ("FH-NAP-OAT4", "FH-NAP-OAT4", "FBM", 34.99, 30.00, 40.00, 36, "Active"),
    ("FH-RUN-72-FBA", "FH-RUN-72", "FBA", 39.99, 34.00, 46.00, 44, "Active"),
    ("FH-TWL-WAF2", "FH-TWL-WAF2", "FBM", 19.99, 16.00, 24.00, 50, "Active"),
    ("FH-TWL-WAF2-FBA", "FH-TWL-WAF2", "FBA", 19.99, 16.00, 24.00, 90, "Active"),
    ("FH-APR-CHB", "FH-APR-CHB", "FBM", 36.99, 32.00, 42.00, 9, "Active"),
    ("CK-PAN-10-FBA", "CK-PAN-10", "FBA", 52.99, 46.00, 60.00, 38, "Active"),
    ("CK-DTO-5Q", "CK-DTO-5Q", "FBM", 96.99, 85.00, 110.00, 7, "Active"),
    ("CK-DTO-5Q-FBA", "CK-DTO-5Q", "FBA", 96.99, 85.00, 110.00, 15, "Active"),
    ("CK-KNF-CHF8", "CK-KNF-CHF8", "FBM", 69.99, 60.00, 80.00, 16, "Active"),
    ("CK-BRD-WAL-FBA", "CK-BRD-WAL", "FBA", 62.99, 55.00, 72.00, 27, "Active"),
    ("CK-TNG-12", "CK-TNG-12", "FBM", 15.99, 12.00, 19.00, 55, "Active"),
    ("FW-CND-CDR", "FW-CND-CDR", "FBM", 26.99, 22.00, 30.00, 30, "Active"),
    ("FW-CND-FIG", "FW-CND-FIG", "FBM", 26.99, 22.00, 30.00, 0, "Inactive"),
    ("FW-GFT-HOST", "FW-GFT-HOST", "FBM", 78.99, 70.00, 90.00, 10, "Active"),
    ("FW-SPC-SET-FBA", "FW-SPC-SET", "FBA", 41.99, 36.00, 48.00, 40, "Active"),
    ("MB-MUG-SPK", "MB-MUG-SPK", "FBM", 21.99, 18.00, 26.00, 25, "Active"),
    ("MB-BWL-SRV", "MB-BWL-SRV", "FBM", 47.99, 40.00, 55.00, 12, "Active"),
    ("MB-SPN-SET-FBA", "MB-SPN-SET", "FBA", 28.99, 24.00, 34.00, 70, "Active"),
]

# Supplier sheet. item_no, description, your_sku, case_pack, unit_cost, map, msrp, effective_date, status
SHEET_V1 = [
    ("LP-1101", "Speckled Stoneware Mug 12oz - Oat", "LK-MUG-SPK", 6, "9.40", "27.00", "32.00", "2026-11-20", "ACTIVE"),
    ("LP-1104", "Speckled Stoneware Mug 12oz - Cobalt", "", 6, "9.40", "27.00", "32.00", "2026-11-20", "ACTIVE"),
    ("LP-1210", "Nesting Prep Bowls S/3", "LK-BWL-NST3", 4, "21.50", "59.00", "72.00", "2026-11-20", "ACTIVE"),
    ("LP-2205", "Ribbed Vase - Sage Glaze", "LK-VSE-RIB-SG", 4, "15.80", "46.00", "58.00", "2026-11-20", "ACTIVE"),
    ("LP-2206", "Ribbed Vase - Charcoal Glaze", "LK-VSE-RIB-CH", 4, "15.80", "46.00", "58.00", "2026-11-20", "ACTIVE"),
    ("LP-2210", "Fluted Bud Vase Trio", "", 6, "11.20", "34.00", "40.00", "2026-11-20", "ACTIVE"),
    ("LP-3120", "Stoneware Dinner Plates S/4", "LK-PLT-DIN4", 2, "25.00", "70.00", "84.00", "2026-11-27", "ACTIVE"),
    ("LP-3305", "Glazed Pitcher 64oz", "LK-PCH-LG", 2, "19.60", "56.00", "66.00", "2026-11-28", "ACTIVE"),
    ("LP-4102", "Taper Candle Holders Pair", "LK-CND-HLD2", 6, "10.10", "30.00", "38.00", "2026-11-20", "ACTIVE"),
    ("LP-4150", "Spoon Rest", "LK-SPN-RST", 12, "4.60", "15.00", "19.00", "2026-11-20", "ACTIVE"),
    ("LP-4410", "Oval Serving Tray", "LK-TRY-SRV", 4, "15.20", "44.00", "52.00", "2027-01-04", "ACTIVE"),
    ("LP-5020", "Glass-Lid Carafe 1L", "LK-CRF-GLS", 4, "12.30", "34.00", "44.00", "2026-11-20", "ACTIVE"),
    ("LP-5110", "Covered Butter Dish", "LK-BTR-DSH", 6, "7.90", "22.00", "28.00", "2026-11-20", "ACTIVE"),
    ("LP-5205", "Olive Oil Cruet", "LK-OIL-CRT", 6, "6.40", "20.00", "24.00", "2026-11-20", "ACTIVE"),
    ("LP-5230", "Salt Cellar w/ Lid", "LK-SLT-CEL", 6, "5.10", "15.00", "19.00", "2026-11-20", "ACTIVE"),
    ("LP-6001", "Stoneware Utensil Crock", "", 4, "12.00", "36.00", "42.00", "2026-11-20", "ACTIVE"),
]
REV2 = {   # what the corrected sheet changes
    "LP-2205": {"map": "48.00"},
    "LP-2206": {"map": "48.00"},
    "LP-4102": {"effective_date": "2026-12-01"},
    "LP-4150": {"status": "DISCONTINUED"},
    "LP-5020": {"map": "36.00"},
}
COLS = ["item_no", "description", "your_sku", "case_pack", "unit_cost", "map", "msrp", "effective_date", "status"]


def sheet_rows(version: int):
    rows = []
    for r in SHEET_V1:
        row = dict(zip(COLS, r))
        if version == 2:
            row.update(REV2.get(row["item_no"], {}))
        rows.append(row)
    return rows


def csv_text(header, rows, delimiter=","):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n" if delimiter == "," else "\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------- truth
def shopify_stock():
    stock = {}
    for _, (_, variants) in LARKSPUR.items():
        for _, sku, _, qty in variants:
            stock[sku] = qty
    for sku, _, _, _, qty, _ in NOISE:
        stock[sku] = qty
    return stock


def shopify_prices():
    prices = {}
    for _, (_, variants) in LARKSPUR.items():
        for _, sku, price, _ in variants:
            prices[sku] = price
    return prices


def compute(version=2, use_dates=True, never_lower=True, fba_blank=True, buffer=BUFFER,
            skip_disc=True, include_inactive=True):
    """Return (flat-file rows as dicts, {shopify sku: new price}) under the given reading of the rules."""
    sheet = {r["your_sku"]: r for r in sheet_rows(version) if r["your_sku"]}
    stock, prices = shopify_stock(), shopify_prices()
    rows = []
    for asku, ssku, ch, price, lo, hi, _, status in AMAZON:
        if ssku not in sheet:
            continue
        if status != "Active" and not include_inactive:
            continue
        s = sheet[ssku]
        if skip_disc and s["status"] == "DISCONTINUED":
            continue
        live = (s["effective_date"] <= CUTOFF) if use_dates else True
        if live:
            p = max(price, float(s["map"])) if never_lower else float(s["map"])
            row_p, row_lo, row_hi = m(p), m(s["map"]), m(s["msrp"])
        else:
            row_p, row_lo, row_hi = m(price), m(lo), m(hi)
        if ch == "FBM":
            qty, channel = str(max(0, stock[ssku] - buffer)), "DEFAULT"
        else:
            qty, channel = ("" if fba_blank else str(max(0, stock[ssku] - buffer))), "AMAZON_NA"
        rows.append({"sku": asku, "price": row_p, "minimum-seller-allowed-price": row_lo,
                     "maximum-seller-allowed-price": row_hi, "quantity": qty, "fulfillment-channel": channel})
    raises = {}
    for ssku, s in sheet.items():
        if ssku not in prices:
            continue
        if skip_disc and s["status"] == "DISCONTINUED":
            continue
        live = (s["effective_date"] <= CUTOFF) if use_dates else True
        if live and float(prices[ssku]) < float(s["map"]):
            raises[ssku] = m(s["map"])
    return rows, raises


def flat_text(rows):
    return csv_text(HEADER, [[r[h] for h in HEADER] for r in rows], delimiter="\t")


# ---------------------------------------------------------------- amazon
def asin(sku: str) -> str:
    base = sku.replace("-FBA", "")
    return "B0" + hashlib.md5(base.encode()).hexdigest()[:8].upper()


AMZ_TITLES = {}


def amazon_title(ssku):
    for _, (title, variants) in LARKSPUR.items():
        for vt, sku, _, _ in variants:
            if sku == ssku:
                return title + ("" if vt == "Default Title" else f", {vt}")
    for sku, title, *_ in NOISE:
        if sku == ssku:
            return title
    raise KeyError(ssku)


def brand_of(ssku):
    if ssku.startswith("LK-"):
        return "Larkspur Pottery"
    return next(n[2] for n in NOISE if n[0] == ssku)


CATEGORY = {"LK": "Home & Kitchen > Dining > Serveware", "NW": "Home & Kitchen > Dining > Glassware",
            "FH": "Home & Kitchen > Kitchen & Table Linens", "CK": "Home & Kitchen > Kitchen > Cookware",
            "FW": "Home & Kitchen > Home Decor", "MB": "Home & Kitchen > Kitchen Utensils"}


def build_amazon():
    products = []
    for i, (asku, ssku, ch, price, lo, hi, qty, status) in enumerate(AMAZON, 1):
        title = amazon_title(ssku)
        products.append({
            "id": f"PROD_{i:03d}", "asin": asin(asku), "sku": asku, "title": title, "brand": brand_of(ssku),
            "category": CATEGORY[ssku[:2]], "price": price, "salePrice": None,
            "costOfGoods": round(price * 0.36, 2), "fulfillmentChannel": ch, "status": status, "condition": "New",
            "availableQuantity": qty, "reservedQuantity": 1 if qty > 10 else 0,
            "inboundQuantity": 24 if ch == "FBA" and i % 3 == 0 else 0,
            "buyBoxOwner": status == "Active", "buyBoxPrice": price, "lowestPrice": round(price - 0.5, 2),
            "minimumSellerAllowedPrice": lo, "maximumSellerAllowedPrice": hi,
            "rating": round(4.2 + (i % 7) * 0.1, 1), "reviewCount": 18 + i * 11,
            "bulletPoints": [f"{title}", "Ships from Minneapolis, MN" if ch == "FBM" else "Fulfilled by Amazon"],
            "description": f"{title} from {brand_of(ssku)}.", "keywords": title.lower().replace(",", ""),
            "weight": "2 lb", "dimensions": "10 x 8 x 6 inches",
            "dateCreated": f"2025-{(i % 9) + 1:02d}-1{i % 9}T15:00:00Z", "lastUpdated": "2026-11-02T15:00:00Z",
        })
    orders = []
    for n in range(10):
        p = products[(n * 5) % len(products)]
        status = ["Shipped", "Delivered", "Unshipped", "Delivered", "Shipped"][n % 5]
        total = round(p["price"] * (1 + n % 2), 2)
        orders.append({
            "id": f"ORD_{n + 1:03d}", "amazonOrderId": f"113-{4821000 + n * 3711:07d}-{6620000 + n * 917:07d}",
            "purchaseDate": f"2026-11-{8 + n:02d}T{14 + n % 6}:12:00Z", "lastUpdateDate": f"2026-11-{9 + n:02d}T16:00:00Z",
            "status": status, "fulfillmentChannel": p["fulfillmentChannel"], "salesChannel": "Amazon.com",
            "buyerName": ["Megan R.", "Chris P.", "Alana W.", "Sam O.", "Dev K.", "Lori M.", "Pat B.", "Jun L.", "Ruth A.", "Theo G."][n],
            "buyerEmail": f"buyer{n + 1}@marketplace.amazon.com",
            "shippingAddress": {"name": "Buyer", "line1": f"{100 + n} Main St", "line2": "", "city": "Madison", "state": "WI", "postalCode": "53703"},
            "items": [{"productId": p["id"], "sku": p["sku"], "title": p["title"], "quantity": 1 + n % 2,
                       "itemPrice": p["price"], "itemTotal": total}],
            "orderTotal": total, "shippingFee": 0, "amazonFees": round(total * 0.15, 2),
            "netProceeds": round(total * 0.85, 2), "carrier": None if status == "Unshipped" else "UPS",
            "trackingNumber": None if status == "Unshipped" else f"1Z99F{n}8320{n}",
            "shipByDate": f"2026-11-{10 + n:02d}T23:59:00Z", "deliverByDate": f"2026-11-{14 + n:02d}T23:59:00Z",
            "shippedDate": None if status == "Unshipped" else f"2026-11-{9 + n:02d}T18:00:00Z",
        })
    notifications = [
        {"id": "NOTIF_001", "type": "inventory", "title": "Listing inactive: out of stock",
         "message": "2 merchant-fulfilled listings are inactive because their quantity is 0.", "timestamp": "2026-11-16T13:00:00Z",
         "isRead": False, "actionUrl": "/inventory", "category": "inventory"},
        {"id": "NOTIF_002", "type": "account", "title": "Holiday selling deadlines",
         "message": "FBA holiday inbound cut-off for Black Friday delivery is November 20.", "timestamp": "2026-11-12T15:00:00Z",
         "isRead": True, "actionUrl": "/inventory/shipments", "category": "inventory"},
        {"id": "NOTIF_003", "type": "policy", "title": "Pricing health",
         "message": "Set minimum and maximum allowed prices to protect listings from pricing errors.", "timestamp": "2026-11-10T15:00:00Z",
         "isRead": True, "actionUrl": "/pricing", "category": "policy"},
    ]
    return {
        "seller": {"id": "seller_fwt", "displayName": STORE, "legalName": "Fernwood Table Company LLC",
                   "email": OWNER[1], "marketplace": "Amazon.com", "planType": "Professional", "storeName": STORE,
                   "sellerId": "A2FWT7LK0Q9XZ3", "registeredSince": "2023-04-02", "accountHealthRating": 912,
                   "notificationCount": 1, "unreadMessages": 0},
        "products": products, "orders": orders, "messages": [], "returns": [], "campaigns": [], "feedback": [],
        "coupons": [], "pricingRules": [], "notifications": notifications,
        "inventoryReports": [], "inventoryFileUploads": [],
    }


def listings_report(state):
    rows = []
    for p in state["products"]:
        rows.append([p["sku"], p["asin"], p["title"], m(p["price"]), m(p["minimumSellerAllowedPrice"]),
                     m(p["maximumSellerAllowedPrice"]), str(p["availableQuantity"]),
                     "AMAZON_NA" if p["fulfillmentChannel"] == "FBA" else "DEFAULT", p["status"]])
    return csv_text(REPORT_HEADER, rows, delimiter="\t")


# ---------------------------------------------------------------- shopify
def build_shopify():
    products, idx = [], 0

    def product(pid, title, vendor, ptype, status, variants, tags, options):
        return {"id": pid, "title": title, "bodyHtml": f"<p>{title}.</p>", "vendor": vendor, "productType": ptype,
                "handle": title.lower().replace(",", "").replace("&", "and").replace(" ", "-"), "status": status,
                "tags": tags, "images": [{"id": f"img_{pid[5:]}", "src": product_image(title), "alt": title, "position": 1}],
                "variants": variants, "options": options, "collections": [],
                "createdAt": "2025-03-04T16:00:00Z", "updatedAt": "2026-10-28T16:00:00Z"}

    for key, (title, vs) in LARKSPUR.items():
        idx += 1
        pid = f"prod_lk_{key}"
        variants = [{"id": f"var_lk_{key}_{j}", "productId": pid, "title": vt, "price": price, "compareAtPrice": None,
                     "sku": sku, "inventoryQuantity": qty, "option1": vt, "option2": None, "position": j}
                    for j, (vt, sku, price, qty) in enumerate(vs, 1)]
        options = ([{"id": f"opt_lk_{key}", "name": "Glaze", "position": 1, "values": [v[0] for v in vs]}]
                   if len(vs) > 1 else [{"id": f"opt_lk_{key}", "name": "Title", "position": 1, "values": ["Default Title"]}])
        products.append(product(pid, title, "Larkspur Pottery", "Ceramics", "active", variants, ["larkspur", "ceramics"], options))
    t, sku, price, qty = ARCHIVED
    products.append(product("prod_lk_vase_old", t, "Larkspur Pottery", "Ceramics", "archived",
                            [{"id": "var_lk_vase_old_1", "productId": "prod_lk_vase_old", "title": "Default Title", "price": price,
                              "compareAtPrice": None, "sku": sku, "inventoryQuantity": qty, "option1": "Default Title",
                              "option2": None, "position": 1}],
                            ["larkspur", "old-mold"], [{"id": "opt_lk_vase_old", "name": "Title", "position": 1, "values": ["Default Title"]}]))
    for i, (sku, title, vendor, price, qty, ptype) in enumerate(NOISE, 1):
        pid = f"prod_n{i:02d}"
        products.append(product(pid, title, vendor, ptype, "active",
                                [{"id": f"var_n{i:02d}", "productId": pid, "title": "Default Title", "price": price,
                                  "compareAtPrice": None, "sku": sku, "inventoryQuantity": qty, "option1": "Default Title",
                                  "option2": None, "position": 1}],
                                [vendor.split()[0].lower()], [{"id": f"opt_n{i:02d}", "name": "Title", "position": 1, "values": ["Default Title"]}]))

    customers_raw = [("cust_201", "Erin", "Walsh", "erin.walsh@gmail.com"), ("cust_202", "Marcus", "Hale", "mhale@outlook.com"),
                     ("cust_203", "Priya", "Desai", "priya.desai@icloud.com"), ("cust_204", "Owen", "Brandt", "owen.brandt@gmail.com"),
                     ("cust_205", "Lena", "Kowalski", "lena.k@fastmail.com"), ("cust_206", "Jamal", "Reed", "jreed@hey.com")]
    sku_index = {v["sku"]: (p, v) for p in products for v in p["variants"]}
    order_specs = [(1301, 0, [("LK-MUG-SPK", 2), ("FH-NAP-OAT4", 1)], "2026-11-09T17:20:00Z"),
                   (1302, 1, [("CK-DTO-5Q", 1)], "2026-11-10T19:02:00Z"),
                   (1303, 2, [("LK-VSE-RIB-SG", 1)], "2026-11-12T15:44:00Z"),
                   (1304, 3, [("LK-PCH-LG", 1), ("FW-CND-CDR", 2)], "2026-11-14T21:10:00Z"),
                   (1305, 4, [("NW-TMB-SET6", 1)], "2026-11-16T16:31:00Z"),
                   (1306, 5, [("LK-BWL-NST3", 1), ("CK-TNG-12", 1)], "2026-11-17T22:05:00Z")]
    orders, spent = [], {}
    for number, ci, items, placed in order_specs:
        cid, first, last, email = customers_raw[ci]
        lines, subtotal = [], 0.0
        for j, (sku, q) in enumerate(items, 1):
            p, v = sku_index[sku]
            lines.append({"id": f"li_{number}_{j}", "productId": p["id"], "variantId": v["id"], "title": p["title"],
                          "variantTitle": "" if v["title"] == "Default Title" else v["title"], "quantity": q, "price": v["price"],
                          "sku": sku, "imageSrc": product_image(p["title"]), "fulfillmentStatus": "fulfilled" if number < 1305 else None})
            subtotal += float(v["price"]) * q
        total = subtotal + 9.95
        addr = {"address1": f"{200 + number % 100} Lake St", "city": "Minneapolis", "province": "Minnesota", "provinceCode": "MN",
                "country": "United States", "countryCode": "US", "zip": "55408", "firstName": first, "lastName": last}
        orders.append({"id": f"order_{number}", "name": f"#{number}", "orderNumber": number, "email": email,
                       "financialStatus": "paid", "fulfillmentStatus": "fulfilled" if number < 1305 else None, "currency": "USD",
                       "subtotalPrice": m(subtotal), "totalShippingPrice": "9.95", "totalTax": "0.00", "totalDiscounts": "0.00",
                       "totalPrice": m(total), "lineItems": lines,
                       "customer": {"id": cid, "firstName": first, "lastName": last, "email": email},
                       "shippingAddress": addr, "billingAddress": addr, "note": "", "tags": [], "discountCodes": [],
                       "timeline": [{"id": f"evt_{number}_1", "type": "created", "message": "Order was placed", "createdAt": placed, "user": "System"}],
                       "refunds": [], "createdAt": placed, "updatedAt": placed})
        spent[cid] = spent.get(cid, 0.0) + total
    customers = [{"id": cid, "firstName": f, "lastName": l, "email": e, "phone": None, "state": "enabled",
                  "ordersCount": sum(1 for o in orders if o["customer"]["id"] == cid), "totalSpent": m(spent.get(cid, 0)),
                  "tags": [], "acceptsMarketing": True, "createdAt": "2025-10-01T16:00:00Z", "note": ""}
                 for cid, f, l, e in customers_raw]
    return {
        "store": {"id": "store_fwt", "name": STORE, "email": "hello@fernwoodtable.com", "domain": "fernwood-table.myshopify.com",
                  "currency": "USD", "plan": "Shopify", "owner": {"firstName": "Tessa", "lastName": "Lindgren", "email": "hello@fernwoodtable.com"}},
        "products": products, "collections": [], "orders": sorted(orders, key=lambda o: -o["orderNumber"]), "customers": customers,
        "discounts": [], "draftOrders": [], "giftCards": [],
        "analytics": {"dailyMetrics": [], "totalSalesThisMonth": 6412.40, "totalOrdersThisMonth": 58, "totalSessionsThisMonth": 4120},
        "pages": [], "blogPosts": [], "navigationMenus": [],
        "settings": {"storeName": STORE, "storeEmail": "hello@fernwoodtable.com", "currency": "USD",
                     "timezone": "(GMT-06:00) Central Time", "weightUnit": "lb"},
    }


# ---------------------------------------------------------------- yahoo mail
def yahoo_attachment(aid, name, size):
    return {"id": aid, "name": name, "size": size, "mimeType": "text/csv", "kind": "document", "url": file_url(name),
            "source": "seed", "uploadedAt": None, "sourceMessageId": None, "sourceAttachmentId": None}


def ymsg(mid, conv, sender, subject, body, date, *, folder="inbox", category="primary", read=False, attachments=None,
         to=None, cc=None, reply_to_id=None, starred=False):
    received = folder not in ("sent", "draft")
    me = {"name": OWNER[0], "email": OWNER[1]}
    return {"id": mid, "conversationId": conv, "folderId": folder, "previousFolderId": None, "category": category,
            "from": {"name": sender[0], "email": sender[1]} if received else me,
            "to": to or ([me] if received else []), "cc": cc or [], "bcc": [], "replyTo": None, "subject": subject,
            "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None, "date": date,
            "isRead": read or not received, "isStarred": starred, "isDraft": False,
            "status": "received" if received else "sent", "attachments": attachments or [], "hasImages": False,
            "listUnsubscribe": category in ("offers", "newsletters"), "summary": None, "orderInfo": None, "travelInfo": None,
            "inReplyToId": reply_to_id, "forwardedFromId": None, "replyType": "reply" if reply_to_id and not received else None,
            "repliedAt": None, "forwardedAt": None, "sentAt": None if received else date, "movedAt": None,
            "appliedFilterId": None, "createdAt": date, "updatedAt": None}


RAFAEL_BODY = """Hi Tessa,

Since you're doing the Larkspur upload today, here's how I want it rolled out.

Amazon: pull the All Listings report from Seller Central and build a Price & Quantity file with only our Larkspur listings in it, FBA and merchant-fulfilled, active or not. Nothing else goes in the file, the loader overwrites every row it gets.

Larkspur enforces MAP from each row's effective date. Anything effective on or before Black Friday (Nov 27) we switch now. Rows that go live later stay on current pricing, so carry their price, minimum and maximum over from the report unchanged.

For the rows we switch: price is the new MAP or our current Amazon price, whichever is higher. We're not cutting anything going into the holidays. Minimum allowed price = new MAP, maximum allowed price = MSRP.

Quantity goes on merchant-fulfilled rows only: Shopify stock for that SKU minus 2 (we hold two back for site orders), never below zero. Leave quantity empty on FBA rows and keep them AMAZON_NA, otherwise Amazon converts them to merchant fulfilled.

If Larkspur marks something discontinued, leave it out of the file and leave it alone on Shopify. We'll sell through what we have at today's prices.

Shopify: for the rows going live now, any Larkspur variant on our site that's priced below its new MAP goes up to exactly the MAP. Don't touch anything else.

Thanks!
Rafael"""


def build_yahoo(v1_size, v2_size, decoy_size):
    hannah = ("Hannah Pruitt", "hannah.pruitt@larkspurpottery.com")
    owen = ("Owen Tate", "owen.tate@larkspurpottery.com")
    msgs = [
        ymsg("ym_001", "cnv_lk", hannah, "Larkspur Pottery - 2027 wholesale cost & MAP sheet",
             "Hi Tessa,\n\nAttached is our 2027 cost and MAP sheet for all Larkspur items. Costs and MAP change on the effective date shown on each row, and our MAP policy is enforced from that date on every channel, including your own website.\n\nThe your_sku column is filled in for the items Fernwood carries.\n\nBest,\nHannah Pruitt\nWholesale Accounts, Larkspur Pottery",
             "2026-11-13T15:12:00.000Z", read=True, attachments=[yahoo_attachment("att_lk_v1", V1_NAME, v1_size)]),
        ymsg("ym_002", "cnv_lk", owen, "Re: Larkspur Pottery - 2027 wholesale cost & MAP sheet",
             "Hi Tessa,\n\nOwen from pricing here. A few rows in Hannah's sheet were wrong, sorry about that: the ribbed vase glazes and the glass-lid carafe had last year's MAP, the candle holders move to December 1, and the spoon rest is being discontinued after this production run.\n\nThe corrected file is attached and replaces the first one entirely.\n\nOwen Tate\nPricing Analyst, Larkspur Pottery",
             "2026-11-16T20:41:00.000Z", attachments=[yahoo_attachment("att_lk_v2", V2_NAME, v2_size)], reply_to_id="ym_001",
             cc=[{"name": hannah[0], "email": hannah[1]}]),
        ymsg("ym_003", "cnv_rr", RAFAEL, "Larkspur update - Amazon + Shopify", RAFAEL_BODY, "2026-11-17T23:18:00.000Z", starred=True),
        ymsg("ym_004", "cnv_nw", ("Dmitri Volkov", "dmitri@northwindglass.com"), "Northwind Glass 2027 pricing",
             "Hello Tessa,\n\nPlease find our 2027 wholesale pricing attached. New pricing takes effect January 15, 2027. Let me know if you'd like to place a pre-order at 2026 prices.\n\nDmitri Volkov\nNorthwind Glass",
             "2026-11-15T14:05:00.000Z", read=True, attachments=[yahoo_attachment("att_nw", DECOY_NAME, decoy_size)]),
        ymsg("ym_005", "cnv_lk_show", hannah, "Larkspur open studio - Dec 6",
             "Hi Tessa, we're opening the studio to our retail partners on December 6, 10am-2pm. Preview of the 2027 glazes and coffee from the shop next door. Hope you can make it! Hannah",
             "2026-11-17T16:30:00.000Z"),
        ymsg("ym_006", "cnv_shp1", ("Shopify", "no-reply@shopify.com"), "Your payout of $3,218.44 is on its way",
             "Payout for Nov 9 - Nov 15 has been sent to your bank account ending 4410.", "2026-11-16T11:00:00.000Z", read=True, category="offers"),
        ymsg("ym_007", "cnv_amz1", ("Amazon Seller Central", "seller-notification@amazon.com"), "Action recommended: set minimum and maximum prices",
             "Listings without minimum and maximum allowed prices can be deactivated by pricing error protection. You can set them in Manage Pricing or with a Price & Quantity inventory file.",
             "2026-11-10T13:00:00.000Z", read=True, category="offers"),
        ymsg("ym_008", "cnv_amz2", ("Amazon Seller Central", "seller-notification@amazon.com"), "Inventory file processing report available",
             "Your inventory file larkspur_restock_oct.txt (batch 50211873) was processed: 9 records processed, 9 successful, 0 errors.",
             "2026-10-21T18:22:00.000Z", read=True, category="offers"),
        ymsg("ym_009", "cnv_ck", ("Jill Moreno", "jill@cobaltkitchen.co"), "Dutch oven restock - ETA",
             "Hi Tessa, the 5 qt Dutch ovens ship from our warehouse on Nov 24. 12 units on PO 8841. Jill", "2026-11-14T17:48:00.000Z", read=True),
        ymsg("ym_010", "cnv_fh", ("Fernhill Linen", "orders@fernhilllinen.com"), "Order FH-22918 shipped",
             "Your order FH-22918 (napkins, runners) shipped via FedEx Ground, tracking 7781 2290 1173.", "2026-11-12T19:10:00.000Z", read=True),
        ymsg("ym_011", "cnv_rr2", RAFAEL, "Window display for the holidays",
             "Thinking we put the Larkspur plates and the Cobalt Dutch oven in the window from Thanksgiving week. Can you pull 2 of each from stock on Monday? R",
             "2026-11-16T15:02:00.000Z", read=True),
        ymsg("ym_012", "cnv_ups", ("UPS", "mcinfo@ups.com"), "UPS My Choice: weekly summary",
             "You shipped 31 packages last week. 0 delivery exceptions.", "2026-11-17T10:00:00.000Z", read=True, category="offers"),
        ymsg("ym_013", "cnv_news1", ("Retail Brew", "news@retailbrew.example.com"), "Black Friday pricing: what independents are doing",
             "Five shops on how they protect margins in November.", "2026-11-17T12:00:00.000Z", category="newsletters"),
        ymsg("ym_014", "cnv_news2", ("Marketplace Pulse", "digest@marketplacepulse.example.com"), "Amazon fee changes for 2027",
             "Referral fees on home and kitchen hold steady; FBA fulfillment fees rise 15 cents for small standard.", "2026-11-15T12:00:00.000Z",
             read=True, category="newsletters"),
        ymsg("ym_015", "cnv_bank", ("North Star Credit Union", "alerts@northstarcu.example.com"), "Your statement is ready",
             "Your November business checking statement is available online.", "2026-11-05T12:00:00.000Z", read=True, category="offers"),
        ymsg("ym_016", "cnv_mb", ("Ana Ruiz", "ana@mapleandbirch.co"), "Spoon sets back in stock",
             "Hi Tessa! The olive wood spoon sets are back, we can send 40 more next week if you want them for Amazon. Ana",
             "2026-11-11T18:40:00.000Z", read=True),
        ymsg("ym_017", "cnv_social", ("Neighborly", "updates@neighborly.example.com"), "New posts near Lyndale",
             "3 new conversations in your neighborhood.", "2026-11-17T08:00:00.000Z", category="social"),
        ymsg("ym_018", "cnv_insta", ("Instagram", "no-reply@mail.instagram.example.com"), "fernwoodtable, you have 4 new followers",
             "See who followed you this week.", "2026-11-16T09:00:00.000Z", read=True, category="social"),
        ymsg("ym_019", "cnv_rr", RAFAEL, "Re: Larkspur update - Amazon + Shopify",
             "Sounds good, I'll start on it in the morning.", "2026-11-18T01:05:00.000Z", folder="sent",
             to=[{"name": RAFAEL[0], "email": RAFAEL[1]}], reply_to_id="ym_003"),
        ymsg("ym_020", "cnv_acct", ("Grace Lee CPA", "grace@leecpa.example.com"), "Q4 estimated taxes reminder",
             "Hi Tessa, reminder that the Q4 estimate is due January 15. Send me the November P&L when it's ready. Grace",
             "2026-11-14T20:00:00.000Z", read=True),
    ]
    msgs[18]["subject"] = "Re: Larkspur update - Amazon + Shopify"
    folders = [{"id": fid, "name": name, "type": "system", "parentId": None, "order": i, "createdAt": "2025-01-05T16:00:00.000Z"}
               for i, (fid, name) in enumerate([("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"),
                                                ("spam", "Spam"), ("trash", "Trash")])]
    folders += [{"id": "fld_suppliers", "name": "Suppliers", "type": "user", "parentId": None, "order": 0,
                 "createdAt": "2025-01-05T16:00:00.000Z", "updatedAt": None},
                {"id": "fld_amazon", "name": "Amazon", "type": "user", "parentId": None, "order": 1,
                 "createdAt": "2025-01-05T16:00:00.000Z", "updatedAt": None}]
    contacts = [{"id": f"ct_{i:04d}", "firstName": n.split()[0], "lastName": n.split()[-1], "nickname": "",
                 "emails": [{"type": "work", "address": e}], "phones": [], "addresses": [], "company": c, "jobTitle": "",
                 "birthday": "", "website": "", "notes": "", "isFavorite": i == 1, "source": "manual",
                 "createdAt": "2025-02-01T16:00:00.000Z", "updatedAt": None}
                for i, (n, e, c) in enumerate([(RAFAEL[0], RAFAEL[1], STORE), ("Hannah Pruitt", "hannah.pruitt@larkspurpottery.com", "Larkspur Pottery"),
                                               ("Owen Tate", "owen.tate@larkspurpottery.com", "Larkspur Pottery"),
                                               ("Dmitri Volkov", "dmitri@northwindglass.com", "Northwind Glass"),
                                               ("Jill Moreno", "jill@cobaltkitchen.co", "Cobalt Kitchen"),
                                               ("Ana Ruiz", "ana@mapleandbirch.co", "Maple & Birch")], 1)]
    return {
        "currentUser": {"id": "usr_tessa", "name": OWNER[0], "firstName": "Tessa", "email": OWNER[1], "aliases": [],
                        "avatarColor": "#2E7D32", "jobTitle": "Co-owner", "company": STORE, "location": "Minneapolis, MN",
                        "storage": {"usedBytes": 812345678, "totalBytes": 21474836480}},
        "folders": folders, "messages": msgs, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {"writing": {"signature": {"enabled": True, "text": "Tessa Lindgren\nFernwood Table Co."},
                                 "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": OWNER[1],
                                 "sendWithCtrlEnter": True, "linkPreviews": True}},
    }


# ---------------------------------------------------------------- golden mutations
def stored_name(text: str) -> str:
    return hashlib.sha256(("fwt-golden-" + text).encode()).hexdigest()[:8] + "_" + UPLOAD_NAME


def apply_amazon(amazon, text, file_type="price_quantity", report_type="all_listings"):
    stored = stored_name(text)
    amazon["inventoryReports"].append({
        "id": "RPT_001", "reportType": report_type,
        "reportName": "All Listings Report" if report_type == "all_listings" else "Active Listings Report",
        "requestedAt": "2026-11-18T15:41:00.000Z", "completedAt": "2026-11-18T15:41:00.000Z", "status": "Done",
        "fileName": "All+Listings+Report_11-18-2026.txt" if report_type == "all_listings" else "Active+Listings+Report_11-18-2026.txt",
        "rowCount": len(amazon["products"]) if report_type == "all_listings" else sum(p["status"] == "Active" for p in amazon["products"])})
    amazon["inventoryFileUploads"].append({
        "id": "UPL_001", "fileType": file_type, "fileName": UPLOAD_NAME, "storedName": stored,
        "url": f"/files/__SID__/{stored}", "size": len(text.encode()), "contentType": "text/plain",
        "uploadedAt": NOW_Z, "status": "Done", "recordsProcessed": max(0, text.count("\n") - 1)})
    return stored


def apply_shopify(shopify, raises):
    for p in shopify["products"]:
        touched = False
        for v in p["variants"]:
            if p["status"] == "active" and v["sku"] in raises:
                v["price"] = raises[v["sku"]]
                touched = True
        if touched:
            p["updatedAt"] = NOW_Z


def apply_yahoo(yahoo, downloaded=(("ym_002", "att_lk_v2", V2_NAME),)):
    for msg in yahoo["messages"]:
        if msg["id"] in ("ym_002", "ym_003") and not msg["isRead"]:
            msg["isRead"] = True
            msg["updatedAt"] = "2026-11-18T15:35:00.000Z"
    for i, (mid, aid, name) in enumerate(downloaded, 1):
        att = next(a for msg in yahoo["messages"] if msg["id"] == mid for a in msg["attachments"] if a["id"] == aid)
        yahoo["activityLog"].append({"id": f"act_g{i}", "type": "attachment.download", "actor": OWNER[1],
                                     "createdAt": "2026-11-18T15:37:00.000Z", "messageIds": [mid], "folderIds": [],
                                     "filterIds": [], "contactIds": [], "listIds": [],
                                     "details": {"attachmentId": aid, "name": name, "size": att["size"],
                                                 "mimeType": "text/csv", "url": att["url"]}})


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def variant(seed, *, rows=None, raises=None, upload=True, local=True, delimiter="\t", file_type="price_quantity",
            report_type="all_listings", downloaded=None):
    """Build {site: state}, {stored: text}, output text for one fixture run."""
    amazon, yahoo, shopify = (copy.deepcopy(seed[k]) for k in ("amazon_seller", "yahoo_mail", "shopify"))
    files, out = {}, None
    if rows is not None:
        text = csv_text(HEADER, [[r[h] for h in HEADER] for r in rows], delimiter=delimiter)
        if upload:
            files[apply_amazon(amazon, text, file_type, report_type)] = text
        if local:
            out = text
    if raises is not None:
        apply_shopify(shopify, raises)
    if downloaded is not None:
        apply_yahoo(yahoo, downloaded)
    return {"amazon_seller": amazon, "yahoo_mail": yahoo, "shopify": shopify}, files, out


def main(out: Path):
    v1 = csv_text(COLS, [[r[c] for c in COLS] for r in sheet_rows(1)])
    v2 = csv_text(COLS, [[r[c] for c in COLS] for r in sheet_rows(2)])
    decoy = csv_text(["item", "description", "case", "cost_2027", "map_2027", "effective"],
                     [["NW-4410", "Ribbed Glass Vase Sage", 4, "13.90", "40.00", "2027-01-15"],
                      ["NW-5120", "Recycled Tumblers S/6", 4, "15.10", "46.00", "2027-01-15"],
                      ["NW-5300", "Glass Carafe w/ Cork 1L", 6, "10.40", "32.00", "2027-01-15"],
                      ["NW-5310", "Glass Pitcher 2qt", 4, "12.20", "38.00", "2027-01-15"],
                      ["NW-6001", "Wine Decanter 750ml", 2, "16.80", "48.00", "2027-01-15"]])
    for name, text in ((V1_NAME, v1), (V2_NAME, v2), (DECOY_NAME, decoy)):
        write_text(out / "seed" / "files" / "yahoo_mail" / name, text)

    seed = {"amazon_seller": build_amazon(), "yahoo_mail": build_yahoo(len(v1.encode()), len(v2.encode()), len(decoy.encode())),
            "shopify": build_shopify()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    rows, raises = compute()
    gold_states, gold_files, gold_text = variant(seed, rows=rows, raises=raises, downloaded=(("ym_002", "att_lk_v2", V2_NAME),))
    for site, state in gold_states.items():
        write_json(out / "golden" / f"{site}.json", state)
    # The oracle can only push state, so the golden upload's file ships as a seed file under an
    # unguessable stored name; nothing in the seed references it.
    for stored, text in gold_files.items():
        write_text(out / "seed" / "files" / "amazon_seller" / stored, text)
    write_text(out / "golden_output" / UPLOAD_NAME, gold_text)

    # ---- truth for the verifier
    sheet2 = {r["your_sku"]: r for r in sheet_rows(2) if r["your_sku"]}
    amz = {a[0]: a for a in AMAZON}
    by_sku = {r["sku"]: r for r in rows}
    expected = {
        "clock": CLOCK, "cutoff": CUTOFF, "buffer": BUFFER, "header": HEADER, "upload_file_type": "price_quantity",
        "local_copy": f"/workspace/output/{UPLOAD_NAME}",
        "rows": by_sku,
        "effective_skus": sorted(s for s in by_sku if sheet2[amz[s][1]]["effective_date"] <= CUTOFF),
        "deferred_skus": sorted(s for s in by_sku if sheet2[amz[s][1]]["effective_date"] > CUTOFF),
        "fbm_skus": sorted(s for s in by_sku if amz[s][2] == "FBM"),
        "fba_skus": sorted(s for s in by_sku if amz[s][2] == "FBA"),
        "excluded_larkspur_skus": ["LK-SPN-RST"],
        "shopify_raises": raises,
        "shopify_protected_skus": sorted(v["sku"] for p in seed["shopify"]["products"] for v in p["variants"]
                                         if v["sku"] not in raises),
        "shopify_seed_prices": {v["sku"]: v["price"] for p in seed["shopify"]["products"] for v in p["variants"]},
        "listings_report_preview": listings_report(seed["amazon_seller"]),
    }
    write_json(out / "expected.json", expected)

    # ---- fixtures
    v1_rows, v1_raises = compute(version=1)
    naive_rows, naive_raises = compute(version=1, use_dates=False, never_lower=False, fba_blank=False, buffer=0,
                                       skip_disc=False, include_inactive=False)
    fba_rows = [dict(r) for r in rows]
    stock = shopify_stock()
    for r in fba_rows:
        if r["fulfillment-channel"] == "AMAZON_NA":
            r["quantity"] = str(max(0, stock[amz[r["sku"]][1]] - BUFFER))
    nodate_rows, nodate_raises = compute(use_dates=False)
    lower_rows, _ = compute(never_lower=False)
    fixtures = {
        "golden": (gold_states, gold_files, gold_text),
        "nop": ({k: copy.deepcopy(v) for k, v in seed.items()}, {}, None),
        "naive": variant(seed, rows=naive_rows, raises=naive_raises, report_type="active_listings",
                         downloaded=(("ym_001", "att_lk_v1", V1_NAME),)),
        "slip_v1_sheet": variant(seed, rows=v1_rows, raises=v1_raises, downloaded=(("ym_001", "att_lk_v1", V1_NAME),)),
        "slip_fba_quantity": variant(seed, rows=fba_rows, raises=raises),
        "slip_effective_dates": variant(seed, rows=nodate_rows, raises=nodate_raises),
        "slip_price_lowered": variant(seed, rows=lower_rows, raises=raises),
        "format_comma": variant(seed, rows=rows, raises=raises, delimiter=","),
    }
    for name, (states, files, text) in fixtures.items():
        base = out / "variants" / name
        for site, state in states.items():
            write_json(base / "state" / site / "current.json", state)
            write_json(base / "state" / site / "initial.json", seed[site])
        for stored, ftext in files.items():
            write_text(base / "files" / "amazon_seller" / "__SID__" / stored, ftext)
        if text is not None:
            write_text(base / "output" / UPLOAD_NAME, text)
        else:
            (base / "output").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
