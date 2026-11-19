#!/usr/bin/env python3
"""World for the ember-launch-status-audit task (Shopify + Yahoo Mail + Slack + local CSV).

Writes into <out>/:
  seed/{shopify,yahoo_mail,slack}.json      initial state per site
  golden/{shopify,yahoo_mail,slack}.json    state after a correct run
  golden_output/launch_audit.csv            correct CLI deliverable
  input/ember_launch_sheet.csv              agent-visible launch sheet
  expected.json                             hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/launch_audit.csv}

Story (lever L15, status illusion): Nadia Okafor runs e-commerce at Hearth & Hollow.
It is launch morning for the Ember Collection (go-live Wed Nov 18 2026, 08:00 PT).
The merchandiser's email and the #ember-launch channel say everything is live, but in
Shopify two launch products are still draft / archived, the gift box (due Dec 1) went
active early, the launch code EMBER15 is only *scheduled* (wrong start date), the blog
post is saved but not published, and Nadia's own stockist note is still sitting in
Drafts. A thread reply pulled Fig & Clove from the launch (stays draft), the VIP code
correctly expired the night before, and one stockist changed its buying address.
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, product_image  # noqa: E402

CLOCK = "2026-11-18T10:30:00-08:00"
ACT = "2026-11-18T19:05:00.000Z"          # when the golden run does its writes (11:05 PT)
NADIA = {"name": "Nadia Okafor", "email": "nadia@hearthandhollow.com"}
STORE = "Hearth & Hollow"

# ====================================================================== shopify
# (id, title, sku, price, type, status, collections, created, updated, tags)
EMBER = [
    ("prod_emb_ced", "Ember Candle – Cedar & Smoke", "EMB-CND-CED", "34.00", "Candles", "active", "2026-11-03T18:00:00Z", "2026-11-17T23:41:00Z"),
    ("prod_emb_fig", "Ember Candle – Fig & Clove", "EMB-CND-FIG", "34.00", "Candles", "draft", "2026-11-03T18:05:00Z", "2026-11-18T05:16:00Z"),
    ("prod_emb_amb", "Ember Candle – Amber Hearth", "EMB-CND-AMB", "34.00", "Candles", "draft", "2026-11-03T18:10:00Z", "2026-11-17T22:58:00Z"),
    ("prod_emb_rst", "Ember Wool Throw – Rust", "EMB-THR-RST", "148.00", "Throws", "active", "2026-11-04T17:30:00Z", "2026-11-17T23:41:00Z"),
    ("prod_emb_chr", "Ember Wool Throw – Charcoal", "EMB-THR-CHR", "148.00", "Throws", "archived", "2026-11-04T17:35:00Z", "2026-11-17T23:52:00Z"),
    ("prod_emb_mug", "Ember Stoneware Mug Set (2)", "EMB-MUG-SET", "46.00", "Kitchen", "active", "2026-11-05T19:00:00Z", "2026-11-17T23:41:00Z"),
    ("prod_emb_gft", "Ember Gift Box", "EMB-GFT-BOX", "118.00", "Gift sets", "active", "2026-11-06T20:00:00Z", "2026-11-17T23:41:00Z"),
]
CORE = [
    ("prod_hh_thr_chr", "Wool Throw – Charcoal", "HH-THR-CHR", "129.00", "Throws", "active"),
    ("prod_hh_thr_oat", "Wool Throw – Oat", "HH-THR-OAT", "129.00", "Throws", "active"),
    ("prod_hh_thr_sge", "Wool Throw – Sage", "HH-THR-SGE", "129.00", "Throws", "active"),
    ("prod_hh_thr_lin", "Summer Linen Throw – Sand", "HH-THR-LIN", "98.00", "Throws", "archived"),
    ("prod_hh_cnd_cdw", "Hearth Candle – Cedarwood", "HH-CND-CDW", "28.00", "Candles", "active"),
    ("prod_hh_cnd_tob", "Hearth Candle – Tobacco & Vanilla", "HH-CND-TOB", "28.00", "Candles", "active"),
    ("prod_hh_cnd_lav", "Hearth Candle – Lavender Field", "HH-CND-LAV", "28.00", "Candles", "active"),
    ("prod_hh_cnd_pmp", "Hearth Candle – Pumpkin Spice", "HH-CND-PMP", "28.00", "Candles", "archived"),
    ("prod_hh_cnd_trv", "Travel Tin Candle Trio", "HH-CND-TRV", "36.00", "Candles", "active"),
    ("prod_hh_mug_spk", "Speckled Stoneware Mug", "HH-MUG-SPK", "22.00", "Kitchen", "active"),
    ("prod_hh_bwl_set", "Stoneware Pasta Bowls (2)", "HH-BWL-SET", "42.00", "Kitchen", "active"),
    ("prod_hh_brd_wal", "Walnut Serving Board", "HH-BRD-WAL", "64.00", "Kitchen", "active"),
    ("prod_hh_nap_oat", "Linen Napkins Set of 4 – Oat", "HH-NAP-OAT", "38.00", "Kitchen", "active"),
    ("prod_hh_tea_tow", "Waffle Tea Towels (2)", "HH-TEA-TOW", "24.00", "Kitchen", "active"),
    ("prod_hh_pil_bou", "Bouclé Pillow Cover – Cream", "HH-PIL-BOU", "58.00", "Pillows", "active"),
    ("prod_hh_pil_vel", "Velvet Pillow Cover – Rust", "HH-PIL-VEL", "54.00", "Pillows", "active"),
    ("prod_hh_pil_ins", "Feather Pillow Insert 20x20", "HH-PIL-INS", "26.00", "Pillows", "active"),
    ("prod_hh_orn_set", "Felt Ornament Set (6)", "HH-ORN-SET", "32.00", "Holiday", "draft"),
    ("prod_hh_wrt_eu", "Eucalyptus Wreath", "HH-WRT-EUC", "72.00", "Holiday", "draft"),
    ("prod_hh_mat_dor", "Coir Doormat – Hello", "HH-MAT-DOR", "44.00", "Home", "active"),
    ("prod_hh_bsk_sea", "Seagrass Storage Basket", "HH-BSK-SEA", "56.00", "Home", "active"),
    ("prod_hh_gft_card", "Hearth & Hollow Gift Card", "HH-GIFT-CARD", "50.00", "Gift cards", "active"),
    ("prod_hh_gft_cnd", "Candle Lover's Gift Set", "HH-GFT-CND", "74.00", "Gift sets", "active"),
]
EMBER_IDS = [p[0] for p in EMBER]
BY_SKU = {p[2]: p for p in EMBER + [c + ("", "") for c in CORE]}

COLLECTIONS = [
    ("coll_ember", "Ember Collection", "ember-collection", EMBER_IDS),
    ("coll_candles", "Candles", "candles", ["prod_emb_ced", "prod_emb_fig", "prod_emb_amb", "prod_hh_cnd_cdw", "prod_hh_cnd_tob",
                                            "prod_hh_cnd_lav", "prod_hh_cnd_pmp", "prod_hh_cnd_trv"]),
    ("coll_throws", "Throws & Blankets", "throws", ["prod_emb_rst", "prod_emb_chr", "prod_hh_thr_chr", "prod_hh_thr_oat",
                                                    "prod_hh_thr_sge", "prod_hh_thr_lin"]),
    ("coll_kitchen", "Kitchen & Table", "kitchen", ["prod_emb_mug", "prod_hh_mug_spk", "prod_hh_bwl_set", "prod_hh_brd_wal",
                                                     "prod_hh_nap_oat", "prod_hh_tea_tow"]),
    ("coll_gifts", "Gifts", "gifts", ["prod_emb_gft", "prod_hh_gft_card", "prod_hh_gft_cnd", "prod_hh_cnd_trv"]),
    ("coll_holiday", "Holiday 2026", "holiday-2026", ["prod_hh_orn_set", "prod_hh_wrt_eu"]),
]


def money(v) -> str:
    return f"{float(v):.2f}"


def product(pid, title, sku, price, ptype, status, created, updated, collections, ember):
    tags = (["ember", "launch-2026"] if ember else ["core"]) + [ptype.lower().replace(" ", "-")]
    body = (f"<p>{title}. Part of the Ember Collection, our winter 2026 line.</p>" if ember
            else f"<p>{title}. Part of our year-round Hearth &amp; Hollow line.</p>")
    stock = {"EMB-GFT-BOX": 60, "EMB-THR-CHR": 35, "HH-THR-CHR": 22}.get(sku, 48)
    return {
        "id": pid, "title": title, "bodyHtml": body, "vendor": STORE, "productType": ptype,
        "handle": title.lower().replace(" – ", "-").replace("&", "and").replace("'", "").replace("(", "").replace(")", "").replace(" ", "-"),
        "status": status, "tags": tags,
        "images": [{"id": f"img_{pid[5:]}", "src": product_image(title), "alt": title, "position": 1}],
        "variants": [{"id": f"var_{pid[5:]}", "productId": pid, "title": "Default Title", "price": price,
                      "compareAtPrice": None, "sku": sku, "inventoryQuantity": stock, "option1": "Default Title",
                      "option2": None, "position": 1}],
        "options": [{"id": f"opt_{pid[5:]}", "name": "Title", "position": 1, "values": ["Default Title"]}],
        "collections": collections, "createdAt": created, "updatedAt": updated,
        "publishedAt": (updated if status == "active" else None) if ember else (created if status == "active" else None),
    }


CUSTOMERS = [
    ("cust_201", "Hannah", "Moreau", "hannah.moreau@gmail.com"),
    ("cust_202", "Rafael", "Ortega", "rafa.ortega@outlook.com"),
    ("cust_203", "Grace", "Liu", "graceliu.home@gmail.com"),
    ("cust_204", "Owen", "Fitzgerald", "owen.fitz@icloud.com"),
    ("cust_205", "Amara", "Nwosu", "amara.nwosu@yahoo.com"),
    ("cust_206", "Ben", "Carver", "bcarver@fastmail.com"),
    ("cust_207", "Sofia", "Lindqvist", "sofia.lindqvist@gmail.com"),
    ("cust_208", "Jamal", "Wright", "jamal.wright@proton.me"),
    ("cust_209", "Ivy", "Tanaka", "ivy.tanaka@gmail.com"),
    ("cust_210", "Lucas", "Bennett", "lucas.bennett@hey.com"),
    ("cust_211", "Elena", "Petrova", "elena.petrova@gmail.com"),
    ("cust_212", "Marcus", "Hale", "mhale@halestudio.com"),
]
ADDR = [("2140 SE Division St", "Portland", "Oregon", "OR", "97202"), ("88 Valencia St", "San Francisco", "California", "CA", "94103"),
        ("1520 Pearl St", "Boulder", "Colorado", "CO", "80302"), ("411 E Pine St", "Seattle", "Washington", "WA", "98122"),
        ("77 Mass Ave", "Cambridge", "Massachusetts", "MA", "02139"), ("3005 N Williams Ave", "Portland", "Oregon", "OR", "97227"),
        ("950 W Fulton Market", "Chicago", "Illinois", "IL", "60607"), ("12 Elm St", "Austin", "Texas", "TX", "78704"),
        ("600 1st Ave", "Seattle", "Washington", "WA", "98104"), ("221 Sutter St", "San Francisco", "California", "CA", "94108"),
        ("45 Water St", "Brooklyn", "New York", "NY", "11201"), ("18 Commonwealth Ave", "Boston", "Massachusetts", "MA", "02116")]

# number, customer index, [(sku, qty)], shipping, placed (UTC), discount code
ORDERS = [
    (2268, 0, [("HH-THR-OAT", 1)], "12.00", "2026-11-05T18:22:00Z", None),
    (2269, 3, [("HH-CND-CDW", 2), ("HH-CND-TOB", 1)], "8.00", "2026-11-06T02:10:00Z", "HEARTH10"),
    (2270, 5, [("HH-BRD-WAL", 1)], "8.00", "2026-11-07T17:45:00Z", None),
    (2271, 8, [("HH-PIL-BOU", 2), ("HH-PIL-INS", 2)], "12.00", "2026-11-08T21:30:00Z", None),
    (2272, 1, [("HH-THR-CHR", 1)], "12.00", "2026-11-10T16:05:00Z", None),
    (2273, 10, [("HH-MUG-SPK", 4)], "8.00", "2026-11-11T19:40:00Z", None),
    (2274, 4, [("HH-CND-TRV", 1), ("HH-TEA-TOW", 1)], "8.00", "2026-11-12T15:12:00Z", "EMBERVIP"),
    (2275, 6, [("HH-NAP-OAT", 1), ("HH-BWL-SET", 1)], "8.00", "2026-11-13T20:55:00Z", None),
    (2276, 11, [("HH-BSK-SEA", 2)], "12.00", "2026-11-14T18:30:00Z", None),
    (2277, 2, [("HH-GFT-CND", 1)], "8.00", "2026-11-15T22:48:00Z", "EMBERVIP"),
    (2278, 7, [("HH-THR-SGE", 1), ("HH-PIL-VEL", 1)], "12.00", "2026-11-16T17:20:00Z", None),
    (2279, 9, [("HH-MAT-DOR", 1)], "8.00", "2026-11-17T01:05:00Z", None),
    (2280, 0, [("HH-CND-LAV", 3)], "8.00", "2026-11-17T19:33:00Z", None),
    # launch morning (after 08:00 PT = 16:00Z) – only truly active Ember items can be bought
    (2281, 6, [("EMB-CND-CED", 2)], "0.00", "2026-11-18T16:04:00Z", "EMBERSHIP"),
    (2282, 3, [("EMB-THR-RST", 1)], "0.00", "2026-11-18T16:11:00Z", "EMBERSHIP"),
    (2283, 8, [("EMB-MUG-SET", 1), ("EMB-CND-CED", 1)], "0.00", "2026-11-18T16:37:00Z", "EMBERSHIP"),
    (2284, 11, [("EMB-GFT-BOX", 1)], "0.00", "2026-11-18T17:02:00Z", "EMBERSHIP"),
    (2285, 2, [("EMB-CND-CED", 1), ("HH-CND-CDW", 1)], "8.00", "2026-11-18T17:48:00Z", None),
    (2286, 10, [("EMB-THR-RST", 1), ("EMB-MUG-SET", 1)], "0.00", "2026-11-18T18:09:00Z", "EMBERSHIP"),
]


def build_orders():
    orders, spent, counts = [], {}, {}
    for number, ci, items, shipping, placed, code in ORDERS:
        cid, first, last, mail = CUSTOMERS[ci]
        street, city, prov, pc, zipc = ADDR[ci]
        address = {"address1": street, "city": city, "province": prov, "provinceCode": pc, "country": "United States",
                   "countryCode": "US", "zip": zipc, "firstName": first, "lastName": last}
        lines, subtotal = [], 0.0
        for i, (sku, qty) in enumerate(items, 1):
            p = BY_SKU[sku]
            lines.append({"id": f"li_{number}_{i}", "productId": p[0], "variantId": f"var_{p[0][5:]}", "title": p[1],
                          "variantTitle": "", "quantity": qty, "price": p[3], "sku": sku, "imageSrc": product_image(p[1]),
                          "fulfillmentStatus": None})
            subtotal += float(p[3]) * qty
        disc = round(subtotal * {"HEARTH10": 0.10, "EMBERVIP": 0.20}.get(code, 0.0), 2)
        total = subtotal - disc + float(shipping)
        shipped = placed < "2026-11-17"
        timeline = [{"id": f"evt_{number}_1", "type": "created", "message": "Order was placed", "createdAt": placed, "user": "System"},
                    {"id": f"evt_{number}_2", "type": "payment", "message": f"A ${total:.2f} USD payment was processed on Visa ending in 4242",
                     "createdAt": placed, "user": "System"}]
        if shipped:
            timeline.append({"id": f"evt_{number}_3", "type": "fulfilled", "message": f"Items were fulfilled. Tracking: 9400111{number}0 (USPS)",
                             "createdAt": placed[:11] + "23:30:00Z", "user": "Marcus Bell"})
            for li in lines:
                li["fulfillmentStatus"] = "fulfilled"
        orders.append({
            "id": f"order_{number}", "name": f"#{number}", "orderNumber": number, "email": mail, "financialStatus": "paid",
            "fulfillmentStatus": "fulfilled" if shipped else None, "currency": "USD", "subtotalPrice": money(subtotal),
            "totalShippingPrice": shipping, "totalTax": "0.00", "totalDiscounts": money(disc), "totalPrice": money(total),
            "lineItems": lines, "customer": {"id": cid, "firstName": first, "lastName": last, "email": mail},
            "shippingAddress": address, "billingAddress": address, "note": "", "tags": ["ember-launch"] if placed >= "2026-11-18" else [],
            "discountCodes": [{"code": code, "amount": money(disc if code != "EMBERSHIP" else 12.0),
                               "type": "free_shipping" if code == "EMBERSHIP" else "percentage"}] if code else [],
            "timeline": timeline, "refunds": [], "createdAt": placed,
            "updatedAt": placed[:11] + "23:30:00Z" if shipped else placed,
        })
        spent[cid] = spent.get(cid, 0.0) + total
        counts[cid] = counts.get(cid, 0) + 1
    customers = []
    for i, (cid, first, last, mail) in enumerate(CUSTOMERS):
        street, city, prov, pc, zipc = ADDR[i]
        customers.append({"id": cid, "firstName": first, "lastName": last, "email": mail, "phone": None, "state": "enabled",
                          "ordersCount": counts.get(cid, 0), "totalSpent": money(spent.get(cid, 0.0)), "note": "", "tags": [],
                          "taxExempt": False, "verifiedEmail": True, "acceptsMarketing": i % 3 != 1,
                          "defaultAddress": {"address1": street, "city": city, "province": prov, "provinceCode": pc,
                                             "country": "United States", "countryCode": "US", "zip": zipc},
                          "createdAt": "2025-10-01T16:00:00Z", "updatedAt": "2026-11-18T18:09:00Z"})
    return sorted(orders, key=lambda o: -o["orderNumber"]), customers


def discount(did, title, code, dtype, value, status, starts, ends, created, usage, applies="all", ids=(), minimum=("none", ""),
             limit=None, once=False):
    return {"id": did, "title": title, "code": code, "type": dtype, "value": value, "status": status, "appliesTo": applies,
            "appliesToIds": list(ids), "minimumRequirement": minimum[0], "minimumValue": minimum[1], "customerEligibility": "all",
            "usageLimit": limit, "usageCount": usage, "oncePerCustomer": once, "startsAt": starts, "endsAt": ends, "createdAt": created}


def build_discounts():
    return [
        discount("disc_ember15", "Ember launch – 15% off", "EMBER15", "percentage", "15", "scheduled",
                 "2026-11-25T08:00:00Z", "2026-12-01T07:59:00Z", "2026-11-16T22:10:00Z", 0, "specific_collections", ["coll_ember"]),
        discount("disc_embership", "Ember launch week – free shipping", "EMBERSHIP", "free_shipping", "0", "active",
                 "2026-11-18T16:00:00Z", "2026-11-26T07:59:00Z", "2026-11-16T22:14:00Z", 5, minimum=("min_purchase", "75")),
        discount("disc_embervip", "Ember early access – newsletter", "EMBERVIP", "percentage", "20", "expired",
                 "2026-11-11T16:00:00Z", "2026-11-18T07:59:00Z", "2026-11-09T19:00:00Z", 41, limit=250, once=True),
        discount("disc_emberstaff", "Ember staff preview", "EMBERSTAFF", "percentage", "30", "expired",
                 "2026-11-06T16:00:00Z", "2026-11-11T07:59:00Z", "2026-11-05T18:00:00Z", 9, "specific_collections", ["coll_ember"], once=True),
        discount("disc_bf26", "Black Friday 2026 – 25% sitewide", "BLACKFRIDAY26", "percentage", "25", "scheduled",
                 "2026-11-27T08:00:00Z", "2026-12-01T07:59:00Z", "2026-11-12T17:30:00Z", 0),
        discount("disc_hearth10", "Welcome – 10% first order", "HEARTH10", "percentage", "10", "active",
                 "2025-03-01T08:00:00Z", None, "2025-02-26T18:00:00Z", 318, once=True),
        discount("disc_ship150", "Free shipping over $150", None, "free_shipping", "0", "active",
                 "2025-06-01T07:00:00Z", None, "2025-05-28T18:00:00Z", 604, minimum=("min_purchase", "150")),
        discount("disc_bf25", "Black Friday 2025", "BLACKFRIDAY25", "percentage", "25", "expired",
                 "2025-11-28T08:00:00Z", "2025-12-02T07:59:00Z", "2025-11-20T18:00:00Z", 1207),
        discount("disc_linen", "Summer linen – $15 off", "LINEN15", "fixed_amount", "15", "expired",
                 "2026-06-01T07:00:00Z", "2026-07-01T06:59:00Z", "2026-05-27T18:00:00Z", 142, "specific_collections", ["coll_throws"]),
    ]


def build_blog():
    def post(bid, title, handle, author, body, tags, published, published_at, created):
        return {"id": bid, "title": title, "author": author, "bodyHtml": body, "handle": handle, "tags": tags,
                "published": published, "publishedAt": published_at, "createdAt": created}
    return [
        post("blog_ember_meet", "Meet the Ember Collection", "meet-the-ember-collection", "Priya Shah",
             "<p>Six pieces for long winter evenings: three hand-poured candles, two merino throws and a stoneware mug set, "
             "all in the warm rust-and-charcoal palette of a fire that has burned down to embers.</p>",
             ["ember", "launch"], False, None, "2026-11-17T23:30:00Z"),
        post("blog_ember_first", "A first look at Ember", "a-first-look-at-ember", "Priya Shah",
             "<p>Our newsletter crowd gets the first peek at the winter line, plus early access with EMBERVIP.</p>",
             ["ember", "preview"], True, "2026-11-10T17:00:00Z", "2026-11-09T21:00:00Z"),
        post("blog_care_wool", "How to care for a wool throw", "how-to-care-for-a-wool-throw", "Theo Brandt",
             "<p>Air it out, spot clean, and never tumble dry.</p>", ["care", "throws"], True, "2026-10-02T16:00:00Z", "2026-10-01T20:00:00Z"),
        post("blog_candle_tunnel", "Why candles tunnel (and how to stop it)", "why-candles-tunnel", "Marcus Bell",
             "<p>The first burn sets the memory. Let the wax melt to the edge.</p>", ["candles", "care"], True,
             "2026-09-15T16:00:00Z", "2026-09-14T22:00:00Z"),
        post("blog_holiday_guide", "Holiday gift guide 2026 (draft)", "holiday-gift-guide-2026", "Priya Shah",
             "<p>Coming soon.</p>", ["holiday", "gifts"], False, None, "2026-11-12T18:00:00Z"),
    ]


def build_shopify():
    coll_of = {}
    for cid, _t, _h, ids in COLLECTIONS:
        for pid in ids:
            coll_of.setdefault(pid, []).append(cid)
    products = [product(pid, t, sku, price, ty, st, cr, up, coll_of.get(pid, []), True) for pid, t, sku, price, ty, st, cr, up in EMBER]
    for i, (pid, t, sku, price, ty, st) in enumerate(CORE):
        created = f"2025-{(i % 9) + 2:02d}-{(i % 20) + 5:02d}T17:00:00Z"
        products.append(product(pid, t, sku, price, ty, st, created, "2026-10-20T17:00:00Z", coll_of.get(pid, []), False))
    collections = [{"id": cid, "title": t, "bodyHtml": f"<p>{t}</p>", "handle": h, "collectionType": "custom", "productIds": ids,
                    "productsCount": len(ids), "sortOrder": "manual", "publishedAt": "2026-11-18T16:00:00Z" if cid == "coll_ember" else "2025-06-01T16:00:00Z",
                    "updatedAt": "2026-11-17T23:41:00Z", "image": product_image(t)} for cid, t, h, ids in COLLECTIONS]
    orders, customers = build_orders()
    email = NADIA["email"]
    return {
        "store": {"id": "store_hh", "name": STORE, "email": email, "phone": "+1 (503) 555-0148", "domain": "hearth-and-hollow.myshopify.com",
                  "customDomain": "www.hearthandhollow.com",
                  "address": {"address1": "1120 NW Couch St", "city": "Portland", "province": "Oregon", "provinceCode": "OR",
                              "country": "United States", "countryCode": "US", "zip": "97209"},
                  "currency": "USD", "timezone": "(GMT-08:00) Pacific Time", "weightUnit": "lb", "plan": "Shopify",
                  "owner": {"firstName": "Nadia", "lastName": "Okafor", "email": email}, "createdAt": "2024-02-10T18:00:00Z"},
        "products": products, "collections": collections, "orders": orders, "customers": customers,
        "discounts": build_discounts(), "draftOrders": [], "giftCards": [],
        "analytics": {"dailyMetrics": [], "totalSalesThisMonth": 6148.30, "totalOrdersThisMonth": 19, "totalSessionsThisMonth": 5310},
        "pages": [{"id": "page_about", "title": "About us", "handle": "about", "bodyHtml": "<p>Made in Portland since 2024.</p>",
                   "published": True, "createdAt": "2024-02-10T18:00:00Z", "updatedAt": "2025-01-10T18:00:00Z"},
                  {"id": "page_shipping", "title": "Shipping & returns", "handle": "shipping",
                   "bodyHtml": "<p>Free shipping over $150. 30-day returns.</p>", "published": True,
                   "createdAt": "2024-02-10T18:00:00Z", "updatedAt": "2025-06-01T18:00:00Z"}],
        "blogPosts": build_blog(), "navigationMenus": [],
        "settings": {"storeName": STORE, "storeEmail": email, "senderEmail": email, "storePhone": "+1 (503) 555-0148",
                     "currency": "USD", "timezone": "(GMT-08:00) Pacific Time", "weightUnit": "lb"},
    }


# ====================================================================== slack
SLACK_USERS = [
    ("U_NADIA", "Nadia Okafor", "Nadia", "nadia@hearthandhollow.com", "E-commerce Manager"),
    ("U_THEO", "Theo Brandt", "Theo", "theo@hearthandhollow.com", "Merchandiser"),
    ("U_PRIYA", "Priya Shah", "Priya", "priya@hearthandhollow.com", "Marketing"),
    ("U_MARCUS", "Marcus Bell", "Marcus", "marcus@hearthandhollow.com", "Ops & QA"),
    ("U_LENA", "Lena Hartmann", "Lena", "lena@hearthandhollow.com", "Founder"),
]
CHECKLIST_THREAD = "th_ember_checklist"


def smsg(mid, sender, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": sender, "content": text, "timestamp": ts, "threadId": thread,
            "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack():
    users = [{"userId": uid, "fullName": full, "displayName": short, "email": mail, "avatar": avatar(full), "title": title,
              "status": "online" if uid in ("U_NADIA", "U_THEO", "U_PRIYA") else "away", "statusMessage": "", "statusEmoji": "",
              "timeZone": "America/Los_Angeles"} for uid, full, short, mail, title in SLACK_USERS]
    everyone = [u[0] for u in SLACK_USERS]

    def channel(cid, desc, pinned=(), starred=False):
        return {"channelId": cid, "name": cid, "description": desc, "topic": desc, "isPrivate": False, "isStarred": starred,
                "members": everyone, "createdBy": "U_LENA", "createdAt": "2024-03-01T17:00:00Z", "pinnedMessages": list(pinned),
                "unreadCount": 0}

    checklist = (
        "Ember launch checklist :pushpin: Go-live is Wed Nov 18, 8am PT. The launch sheet (`ember_launch_sheet.csv`, same copy on "
        "everyone's laptop) is the source of truth for what goes live when: SKUs, discount codes, start and end dates. "
        "Theo: Ember products and discount codes in Shopify, exactly per the sheet. Priya: launch blog post and socials. "
        "Nadia: stockist note to Juniper Market and Ashby & Co on launch day. Marcus: final QA on the candles Tuesday afternoon. "
        "Launch morning I'll check what's actually live and post the real status here."
    )
    ember = [
        smsg("m_e1", "U_NADIA", "2026-11-12T18:30:00Z", checklist,
             reactions=[{"emoji": "+1", "users": ["U_THEO", "U_PRIYA", "U_MARCUS"], "count": 3}]),
        smsg("m_e2", "U_PRIYA", "2026-11-13T17:05:00Z", "Blog draft for launch day is in Shopify, will publish Wednesday morning."),
        smsg("m_e3", "U_THEO", "2026-11-17T02:10:00Z", "Set up EMBER15 and EMBERSHIP in Shopify tonight. EMBERVIP keeps running for the newsletter list."),
        smsg("m_e4", "U_THEO", "2026-11-18T02:45:00Z", "Products and codes are all set up in Shopify for tomorrow :white_check_mark:"),
        smsg("m_e5", "U_NADIA", "2026-11-18T06:40:00Z", "Stockist note is written, going out tonight."),
        smsg("m_e6", "U_THEO", "2026-11-18T15:58:00Z", "We're live!! :rocket: all the Ember products and EMBER15 are up",
             reactions=[{"emoji": "tada", "users": ["U_PRIYA", "U_LENA"], "count": 2}]),
        smsg("m_e7", "U_PRIYA", "2026-11-18T16:06:00Z",
             "Blog post is up too :tada: and EMBERVIP is still going for the newsletter folks through today"),
        smsg("m_e8", "U_LENA", "2026-11-18T16:20:00Z", "So exciting. First orders already coming in!"),
        smsg("m_e9", "U_PRIYA", "2026-11-18T17:40:00Z",
             "Couple of IG DMs asking where the Amber Hearth candle is, and one person says the charcoal throw on the site is the old one?"),
        smsg("m_e10", "U_THEO", "2026-11-18T17:52:00Z", "it's all published on my end, probably cache. will look after my 10:30"),
    ]
    replies = [
        smsg("m_e1_r1", "U_THEO", "2026-11-13T18:02:00Z", "Ember Gift Box is on the sheet for Dec 1, I'll keep it hidden until then.", thread=CHECKLIST_THREAD),
        smsg("m_e1_r2", "U_MARCUS", "2026-11-18T01:12:00Z",
             "QA update: Fig & Clove failed the burn test this afternoon (tunnelling on 3 of 5 samples). Pulling it from the launch. "
             "It stays in draft until the new batch lands in early December. Haven't updated the sheet yet.", thread=CHECKLIST_THREAD),
        smsg("m_e1_r3", "U_THEO", "2026-11-18T01:15:00Z", "ugh. ok, keeping Fig & Clove unpublished :+1:", thread=CHECKLIST_THREAD),
        smsg("m_e1_r4", "U_LENA", "2026-11-18T01:30:00Z", "Good call Marcus. Everything else on the sheet goes as planned.", thread=CHECKLIST_THREAD),
    ]
    ember[0]["replyCount"] = len(replies)
    # thread replies are stored in the channel array right after their timestamps
    ember_all = sorted(ember + replies, key=lambda m: m["timestamp"])
    messages = {
        "general": [
            smsg("m_g1", "U_LENA", "2026-11-09T17:00:00Z", "Holiday hours: warehouse closes at 2pm on Nov 25 and is closed Nov 26-27."),
            smsg("m_g2", "U_MARCUS", "2026-11-13T22:15:00Z", "New label printer is in, old one goes to the studio."),
            smsg("m_g3", "U_LENA", "2026-11-17T18:00:00Z", "Big day tomorrow, thanks everyone for the push on Ember :fire:"),
        ],
        "ember-launch": ember_all,
        "marketing": [
            smsg("m_m1", "U_PRIYA", "2026-11-10T17:10:00Z", "Newsletter with the Ember first look went out, 38% open rate so far."),
            smsg("m_m2", "U_PRIYA", "2026-11-14T19:00:00Z", "Black Friday creative is in review. BLACKFRIDAY26 starts Nov 27."),
            smsg("m_m3", "U_LENA", "2026-11-14T19:12:00Z", "Love it."),
        ],
        "ops": [
            smsg("m_o1", "U_MARCUS", "2026-11-11T21:00:00Z", "Restocked the core Wool Throw – Charcoal, 22 on hand."),
            smsg("m_o2", "U_MARCUS", "2026-11-16T20:30:00Z", "Ember gift boxes are assembled, 60 units, shelf B4. Not shipping before Dec 1."),
            smsg("m_o3", "U_THEO", "2026-11-17T23:55:00Z", "Cleaned up old/duplicate listings in Shopify tonight, archived a bunch of stuff."),
        ],
    }
    threads = {CHECKLIST_THREAD: {"threadId": CHECKLIST_THREAD, "parentMessageId": "m_e1", "channelId": "ember-launch", "dmId": None,
                                  "replies": [r["messageId"] for r in replies], "followers": ["U_NADIA", "U_THEO", "U_MARCUS"]}}
    return {
        "currentUser": users[0],
        "workspace": {"workspaceId": "ws_hh", "workspaceName": STORE, "icon": avatar("Hearth Hollow")},
        "users": users,
        "channels": [channel("general", "Company-wide"), channel("ember-launch", "Ember Collection launch – Nov 18", ["m_e1"], True),
                     channel("marketing", "Campaigns, socials, newsletter"), channel("ops", "Warehouse, QA, shipping")],
        "messages": messages, "threads": threads, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


# ====================================================================== yahoo mail
THEO = {"name": "Theo Brandt", "email": "theo@hearthandhollow.com"}
JUNIPER = {"name": "Juniper Market", "email": "hello@junipermarket.com"}
ASHBY_OLD = {"name": "Ashby & Co Buying", "email": "buying@ashbyandco.com"}
ASHBY_NEW = {"name": "Ashby Home Purchasing", "email": "purchasing@ashbyhome.co"}
JORDAN = {"name": "Jordan Ashby", "email": "jordan@ashbyhome.co"}

SYSTEM_FOLDERS = [("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"), ("spam", "Spam"), ("trash", "Trash")]
USER_FOLDERS = [("fld_stockists", "Stockists"), ("fld_suppliers", "Suppliers"), ("fld_receipts", "Receipts")]

DRAFT_ID = "msg_draft_stockist"
DRAFT_BODY = (
    "Hi both,\n\n"
    "The Ember Collection is live on hearthandhollow.com as of this morning. Here's what's in the launch:\n\n"
    "- Ember Candle – Cedar & Smoke\n"
    "- Ember Candle – Fig & Clove\n"
    "- Ember Candle – Amber Hearth\n"
    "- Ember Wool Throw – Rust\n"
    "- Ember Wool Throw – Charcoal\n"
    "- Ember Stoneware Mug Set (2)\n\n"
    "Wholesale line sheets with case packs follow on Monday. Shout if you want samples for your windows.\n\n"
    "Best,\nNadia"
)
GOLDEN_BODY = (
    "Hi both,\n\n"
    "The Ember Collection is live on hearthandhollow.com as of this morning. Here's what's live today:\n\n"
    "- Ember Candle – Cedar & Smoke\n"
    "- Ember Candle – Amber Hearth\n"
    "- Ember Wool Throw – Rust\n"
    "- Ember Wool Throw – Charcoal\n"
    "- Ember Stoneware Mug Set (2)\n\n"
    "Wholesale line sheets with case packs follow on Monday. Shout if you want samples for your windows.\n\n"
    "Best,\nNadia"
)


def ymsg(mid, cnv, sender, subject, body, date, to=None, cc=None, folder="inbox", category="primary", read=True, starred=False):
    received = folder not in ("sent", "draft")
    frm = sender if received else NADIA
    return {"id": mid, "conversationId": cnv, "folderId": folder, "previousFolderId": None, "category": category,
            "from": dict(frm), "to": [dict(x) for x in (to or [NADIA])], "cc": [dict(x) for x in (cc or [])], "bcc": [],
            "replyTo": None, "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None,
            "date": date, "isRead": read, "isStarred": starred, "isDraft": folder == "draft",
            "status": "draft" if folder == "draft" else ("received" if received else "sent"),
            "attachments": [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"), "summary": None,
            "orderInfo": None, "travelInfo": None, "inReplyToId": None, "forwardedFromId": None, "replyType": None,
            "repliedAt": None, "forwardedAt": None, "sentAt": date if folder == "sent" else None, "movedAt": None,
            "appliedFilterId": None, "createdAt": date, "updatedAt": date if folder == "draft" else None}


def build_yahoo():
    m = [
        ymsg("msg_theo_setup", "cnv_theo_setup", THEO, "Ember – Shopify setup done",
             "Hi Nadia,\n\nAll set for tomorrow. In Shopify:\n\n"
             "- Cedar & Smoke, Fig & Clove, Amber Hearth candles: live from 8am\n"
             "- Rust and Charcoal throws: live from 8am\n- Mug set: live from 8am\n"
             "- Gift Box: hidden until Dec 1 like the sheet says\n"
             "- EMBER15 (15% off Ember, Nov 18-30) and EMBERSHIP (free shipping over $75, launch week) both set up\n\n"
             "Theo", "2026-11-17T23:05:00.000Z", starred=True),
        ymsg("msg_theo_live", "cnv_theo_live", THEO, "We're live :)",
             "Everything for Ember is published and the codes are on. Going into my 10:30 with the photographer, ping me on Slack.\n\nT",
             "2026-11-18T16:01:00.000Z", read=False),
        ymsg("msg_ashby_addr", "cnv_ashby_addr", JORDAN, "Ashby & Co is now Ashby Home – new buying address",
             "Hi Nadia,\n\nQuick admin note: we've rebranded as Ashby Home and buying has moved. From now on please send line sheets, "
             "launch notes and POs to purchasing@ashbyhome.co. The old buying@ashbyandco.com mailbox stops being read this week.\n\n"
             "Looking forward to Ember!\nJordan Ashby\nOwner, Ashby Home", "2026-11-16T17:42:00.000Z", folder="fld_stockists"),
        ymsg("msg_juniper_q", "cnv_preview", JUNIPER, "Re: Ember Collection preview – wholesale",
             "Thanks Nadia! The rust throw is going to look great in our window. Send the launch note when it's live and we'll "
             "share it with our list.\n\nMei at Juniper Market", "2026-11-11T18:20:00.000Z", folder="fld_stockists"),
        ymsg("msg_preview_sent", "cnv_preview", None, "Ember Collection preview – wholesale",
             "Hi both,\n\nA first look at our winter line, launching Nov 18: three candles, two wool throws, a mug set and a gift box "
             "later in December. Photos attached in the line sheet next week.\n\nBest,\nNadia",
             "2026-11-10T18:00:00.000Z", to=[JUNIPER, ASHBY_OLD], folder="sent"),
        ymsg(DRAFT_ID, "cnv_draft_stockist", None, "Ember Collection is live today", DRAFT_BODY,
             "2026-11-18T06:35:00.000Z", to=[JUNIPER, ASHBY_OLD], folder="draft"),
        ymsg("msg_draft_old", "cnv_draft_old", None, "Holiday wholesale minimums", "Hi Mei, for the holiday window our minimum is",
             "2026-11-04T20:10:00.000Z", to=[JUNIPER], folder="draft"),
        ymsg("msg_lena_q", "cnv_lena_q", {"name": "Lena Hartmann", "email": "lena@hearthandhollow.com"}, "Launch day",
             "Have a great launch! I'll follow along in #ember-launch, mostly want to know the codes are working.\nL",
             "2026-11-18T15:30:00.000Z", read=False),
        ymsg("msg_wax_inv", "cnv_wax_inv", {"name": "Northwest Wax Supply", "email": "billing@nwwaxsupply.com"}, "Invoice NW-20931",
             "Invoice NW-20931 for 240 lb soy wax blend is attached. Net 30.", "2026-11-12T16:00:00.000Z", folder="fld_suppliers"),
        ymsg("msg_wool_ship", "cnv_wool_ship", {"name": "Fenwick Mills", "email": "orders@fenwickmills.co.uk"}, "Dispatch: order FM-7781",
             "Your merino throws (rust x60, charcoal x60) left our mill today.", "2026-10-29T10:00:00.000Z", folder="fld_suppliers"),
        ymsg("msg_shop_payout", "cnv_payout", {"name": "Shopify", "email": "no-reply@shopify.com"}, "Your payout of $2,914.62 is on its way",
             "Payout for Nov 9 - Nov 15 has been sent to your bank account ending 3302.", "2026-11-16T14:00:00.000Z", folder="fld_receipts"),
        ymsg("msg_usps", "cnv_usps", {"name": "USPS Informed Delivery", "email": "informeddelivery@usps.com"}, "Your daily digest",
             "You have 2 packages arriving today.", "2026-11-18T12:00:00.000Z", category="newsletters"),
        ymsg("msg_canva", "cnv_canva", {"name": "Canva", "email": "marketing@canva.com"}, "New holiday templates are here",
             "Make your holiday campaigns pop.", "2026-11-17T15:00:00.000Z", category="offers"),
        ymsg("msg_etsy", "cnv_etsy", {"name": "Retail Brew", "email": "newsletter@retailbrew.com"}, "BFCM: what shoppers want this year",
             "Free shipping thresholds are back in fashion.", "2026-11-18T11:00:00.000Z", category="newsletters", read=False),
        ymsg("msg_ig", "cnv_ig", {"name": "Instagram", "email": "no-reply@mail.instagram.com"}, "hearthandhollow, you have 14 new messages",
             "See what people are saying.", "2026-11-18T17:45:00.000Z", category="social", read=False),
        ymsg("msg_photog", "cnv_photog", {"name": "Sam Rivera", "email": "sam@riverastudio.co"}, "Ember lifestyle shoot – call sheet",
             "Call time 10:30 at the studio, Theo confirmed.", "2026-11-17T20:00:00.000Z"),
        ymsg("msg_juniper_old", "cnv_juniper_old", JUNIPER, "October reorder", "Could we get 12 more Hearth candles (Cedarwood)?",
             "2026-10-14T17:00:00.000Z", folder="fld_stockists"),
        ymsg("msg_sent_juniper_old", "cnv_juniper_old", None, "Re: October reorder", "Done, shipping Thursday.",
             "2026-10-14T19:00:00.000Z", to=[JUNIPER], folder="sent"),
        ymsg("msg_sent_lena", "cnv_sent_lena", None, "Ember launch sheet final",
             "Lena, final launch sheet is on the drive and everyone's laptop. Gift box Dec 1, VIP code ends the night before launch.",
             "2026-11-12T18:20:00.000Z", to=[{"name": "Lena Hartmann", "email": "lena@hearthandhollow.com"}], folder="sent"),
    ]
    folders = [{"id": fid, "name": n, "type": "system", "parentId": None, "order": i, "createdAt": "2024-02-10T18:00:00.000Z"}
               for i, (fid, n) in enumerate(SYSTEM_FOLDERS)]
    folders += [{"id": fid, "name": n, "type": "user", "parentId": None, "order": i, "createdAt": "2024-03-01T18:00:00.000Z",
                 "updatedAt": None} for i, (fid, n) in enumerate(USER_FOLDERS)]

    def contact(cid, first, last, mail, company):
        return {"id": cid, "firstName": first, "lastName": last, "nickname": "", "emails": [{"type": "work", "address": mail}],
                "phones": [], "addresses": [], "company": company, "jobTitle": "", "birthday": "", "website": "", "notes": "",
                "isFavorite": False, "source": "manual", "createdAt": "2025-01-10T18:00:00.000Z"}
    contacts = [contact("ct_juniper", "Mei", "Tan", JUNIPER["email"], "Juniper Market"),
                contact("ct_ashby", "Ashby & Co", "Buying", ASHBY_OLD["email"], "Ashby & Co"),
                contact("ct_jordan", "Jordan", "Ashby", JORDAN["email"], "Ashby Home"),
                contact("ct_theo", "Theo", "Brandt", THEO["email"], STORE)]
    return {
        "currentUser": {"id": "usr_nadia", "name": NADIA["name"], "firstName": "Nadia", "email": NADIA["email"], "aliases": [],
                        "avatarColor": "#B45309", "jobTitle": "E-commerce Manager", "company": STORE, "location": "Portland, OR",
                        "storage": {"usedBytes": 1834567123, "totalBytes": 1099511627776}},
        "folders": folders, "messages": sorted(m, key=lambda x: x["date"], reverse=True), "contacts": contacts, "contactLists": [],
        "filters": [], "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {
            "appearance": {"theme": "light", "themeColor": "blue", "density": "comfortable", "messageLayout": "list"},
            "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
            "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
            "writing": {"signature": {"enabled": False, "text": "Nadia"}, "defaultFont": "sans-serif", "defaultFontSize": "medium",
                        "defaultFrom": NADIA["email"], "sendWithCtrlEnter": True, "linkPreviews": True},
            "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False},
            "rightPanel": {"open": False, "tab": "contacts"},
            "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "", "onlyContacts": False,
                                 "updatedAt": None},
            "ai": {"messageSummaries": False}, "notifications": {"browser": False, "sound": False}, "keyboardShortcuts": True,
        },
    }


# ====================================================================== launch sheet + truth
SHEET = [  # ref, type, name, go_live, ends, notes
    ("EMB-CND-CED", "product", "Ember Candle – Cedar & Smoke", "2026-11-18", "", ""),
    ("EMB-CND-FIG", "product", "Ember Candle – Fig & Clove", "2026-11-18", "", ""),
    ("EMB-CND-AMB", "product", "Ember Candle – Amber Hearth", "2026-11-18", "", ""),
    ("EMB-THR-RST", "product", "Ember Wool Throw – Rust", "2026-11-18", "", ""),
    ("EMB-THR-CHR", "product", "Ember Wool Throw – Charcoal", "2026-11-18", "", ""),
    ("EMB-MUG-SET", "product", "Ember Stoneware Mug Set (2)", "2026-11-18", "", ""),
    ("EMB-GFT-BOX", "product", "Ember Gift Box", "2026-12-01", "", "keep unpublished until go-live"),
    ("EMBER15", "discount", "15% off the Ember Collection", "2026-11-18", "2026-11-30", ""),
    ("EMBERSHIP", "discount", "Free shipping over $75, launch week", "2026-11-18", "2026-11-25", ""),
    ("EMBERVIP", "discount", "Newsletter early access, 20% off", "2026-11-11", "2026-11-17", "early access ends the night before launch"),
    ("meet-the-ember-collection", "blog", "Meet the Ember Collection (launch blog post)", "2026-11-18", "", ""),
]
# ref -> (shopify object id, found_status, fixed_to, live after a correct run)
TRUTH = {
    "EMB-CND-CED": ("prod_emb_ced", "active", "", "yes"),
    "EMB-CND-FIG": ("prod_emb_fig", "draft", "", "no"),
    "EMB-CND-AMB": ("prod_emb_amb", "draft", "active", "yes"),
    "EMB-THR-RST": ("prod_emb_rst", "active", "", "yes"),
    "EMB-THR-CHR": ("prod_emb_chr", "archived", "active", "yes"),
    "EMB-MUG-SET": ("prod_emb_mug", "active", "", "yes"),
    "EMB-GFT-BOX": ("prod_emb_gft", "active", "draft", "no"),
    "EMBER15": ("disc_ember15", "scheduled", "active", "yes"),
    "EMBERSHIP": ("disc_embership", "active", "", "yes"),
    "EMBERVIP": ("disc_embervip", "expired", "", "no"),
    "meet-the-ember-collection": ("blog_ember_meet", "draft", "published", "yes"),
}
CSV_HEADER = ["ref", "found_status", "fixed_to", "live"]


def sheet_rows():
    return [["ref", "type", "name", "go_live", "ends", "notes"]] + [list(r) for r in SHEET]


# ====================================================================== golden mutations
def apply_shopify(shop, fixes):
    """fixes: ref -> new status (product: active/draft/archived, discount: active/expired, blog: published/draft)."""
    for ref, new in fixes.items():
        oid = TRUTH[ref][0]
        if oid.startswith("prod_"):
            p = next(x for x in shop["products"] if x["id"] == oid)
            p["status"] = new
            p["updatedAt"] = ACT
        elif oid.startswith("disc_"):
            d = next(x for x in shop["discounts"] if x["id"] == oid)
            d["status"] = new
        else:
            b = next(x for x in shop["blogPosts"] if x["id"] == oid)
            b["published"] = new == "published"


def apply_yahoo(mail, to, body):
    d = next(x for x in mail["messages"] if x["id"] == DRAFT_ID)
    before_to = d["to"]
    html = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;").replace("\n", "<br>")
    d.update({"to": [dict(x) for x in to], "body": body, "bodyHtml": html, "snippet": " ".join(body.split())[:140], "status": "sent",
              "isDraft": False, "folderId": "sent", "isRead": True, "sentAt": ACT, "date": ACT, "updatedAt": ACT})
    d.pop("recipientInput", None)
    base = {"actor": NADIA["email"], "createdAt": ACT, "messageIds": [DRAFT_ID], "filterIds": [], "contactIds": [], "listIds": []}
    mail["activityLog"] += [
        {**base, "id": "act_draft_save", "type": "draft.save", "folderIds": ["draft"],
         "details": {"changedFields": ["to", "body", "snippet"] if before_to != d["to"] else ["body", "snippet"], "isNew": False}},
        {**base, "id": "act_send", "type": "message.send", "folderIds": ["sent"],
         "details": {"to": d["to"], "cc": [], "bcc": [], "subject": d["subject"], "attachmentIds": [], "originalMessageId": None,
                     "incomingCopyIds": []}},
    ]


def status_post(live):
    lines = "\n".join(f"{ref}: {'live' if live[ref] == 'yes' else 'not live'}" for ref, *_ in SHEET)
    return "Ember launch status as of 11am, checked in Shopify:\n" + lines


def apply_slack(slack, live):
    slack["messages"]["ember-launch"].append(smsg("m_new_status", "U_NADIA", "2026-11-18T19:10:00.000Z", status_post(live)))


def csv_rows(table):
    return [CSV_HEADER] + [[ref, *table[ref]] for ref, *_ in SHEET]


GOLDEN_FIXES = {ref: t[2] for ref, t in TRUTH.items() if t[2]}
GOLDEN_TABLE = {ref: [t[1], t[2], t[3]] for ref, t in TRUTH.items()}


def run(seed, fixes, to, body, table):
    s = {k: copy.deepcopy(v) for k, v in seed.items()}
    apply_shopify(s["shopify"], fixes)
    if to:
        apply_yahoo(s["yahoo_mail"], to, body)
    apply_slack(s["slack"], {ref: row[2] for ref, row in table.items()})
    return s, csv_rows(table)


def naive_variant(seed):
    """Trusts Theo's email and the channel: changes nothing in Shopify, sends the draft as written, reports claims."""
    claimed = {"EMB-CND-CED": "active", "EMB-CND-FIG": "active", "EMB-CND-AMB": "active", "EMB-THR-RST": "active",
               "EMB-THR-CHR": "active", "EMB-MUG-SET": "active", "EMB-GFT-BOX": "draft", "EMBER15": "active",
               "EMBERSHIP": "active", "EMBERVIP": "active", "meet-the-ember-collection": "published"}
    table = {ref: [st, "", "no" if st == "draft" else "yes"] for ref, st in claimed.items()}
    return run(seed, {}, [JUNIPER, ASHBY_OLD], DRAFT_BODY, table)


def slip_fig(seed):
    """Careful run that misses the QA thread reply: activates Fig & Clove and keeps it in the note."""
    fixes = dict(GOLDEN_FIXES, **{"EMB-CND-FIG": "active"})
    table = copy.deepcopy(GOLDEN_TABLE)
    table["EMB-CND-FIG"] = ["draft", "active", "yes"]
    return run(seed, fixes, [JUNIPER, ASHBY_NEW], DRAFT_BODY, table)


def slip_charcoal(seed):
    """Careful run that takes the core 'Wool Throw – Charcoal' (active) for the Ember one and leaves EMB-THR-CHR archived."""
    fixes = {k: v for k, v in GOLDEN_FIXES.items() if k != "EMB-THR-CHR"}
    table = copy.deepcopy(GOLDEN_TABLE)
    table["EMB-THR-CHR"] = ["active", "", "yes"]
    return run(seed, fixes, [JUNIPER, ASHBY_NEW], GOLDEN_BODY, table)


def slip_address(seed):
    """Careful run that sends the stockist note to Ashby's retired address."""
    return run(seed, GOLDEN_FIXES, [JUNIPER, ASHBY_OLD], GOLDEN_BODY, GOLDEN_TABLE)


def slip_giftbox(seed):
    """Careful run that trusts Theo's 'gift box stays hidden' and never notices it is active."""
    fixes = {k: v for k, v in GOLDEN_FIXES.items() if k != "EMB-GFT-BOX"}
    table = copy.deepcopy(GOLDEN_TABLE)
    table["EMB-GFT-BOX"] = ["draft", "", "no"]
    return run(seed, fixes, [JUNIPER, ASHBY_NEW], GOLDEN_BODY, table)


# ====================================================================== io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    seed = {"shopify": build_shopify(), "yahoo_mail": build_yahoo(), "slack": build_slack()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, golden_csv = run(seed, GOLDEN_FIXES, [JUNIPER, ASHBY_NEW], GOLDEN_BODY, GOLDEN_TABLE)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "launch_audit.csv", golden_csv)
    write_csv(out / "input" / "ember_launch_sheet.csv", sheet_rows())

    expected = {
        "clock": CLOCK, "timezone": "America/Los_Angeles",
        "items": {ref: {"object_id": t[0], "found_status": t[1], "fixed_to": t[2], "live": t[3],
                        "final_status": t[2] or t[1]} for ref, t in TRUTH.items()},
        "item_order": [r[0] for r in SHEET],
        "ember_product_ids": EMBER_IDS,
        "near_duplicate_product_id": "prod_hh_thr_chr",
        "protected_discount_ids": ["disc_embervip", "disc_emberstaff", "disc_bf26", "disc_hearth10", "disc_ship150", "disc_bf25", "disc_linen"],
        "stockist_note": {
            "draft_id": DRAFT_ID, "required_to": [JUNIPER["email"], ASHBY_NEW["email"]], "retired_to": [ASHBY_OLD["email"]],
            "must_mention": ["Cedar", "Amber", "Rust", "Charcoal", "Mug"], "must_not_mention": ["Fig"],
        },
        "slack_channel": "ember-launch",
        "output_csv": "/workspace/output/launch_audit.csv", "csv_header": CSV_HEADER,
    }
    write_json(out / "expected.json", expected)

    variants = {
        "golden": (golden, golden_csv),
        "nop": (seed, None),
        "naive": naive_variant(seed),
        "slip_fig": slip_fig(seed),
        "slip_charcoal": slip_charcoal(seed),
        "slip_address": slip_address(seed),
        "slip_giftbox": slip_giftbox(seed),
    }
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "launch_audit.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
