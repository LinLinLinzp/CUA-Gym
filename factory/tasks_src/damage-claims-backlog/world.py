#!/usr/bin/env python3
"""World for the damage-claims-backlog task (Gmail + Slack + Shopify + local CSV).

Writes into <out>/:
  seed/{gmail,slack,shopify}.json      initial state per site
  golden/{gmail,slack,shopify}.json    state after a correct run
  golden_output/claims_log.csv         correct CLI deliverable
  input/carrier_deliveries.csv         agent-visible workspace input
  expected.json                        hidden truth for the verifier
  variants/<name>/{state/*.json,output/claims_log.csv}   self-check fixtures

The story: Maya runs support for a small home-goods shop. Damage claims piled up
while a colleague was out. The pinned Slack policy was amended in a thread
(approval limit $150 -> $200, glassware refunds include shipping); Shopify only
knows ship dates, the carrier export has delivery dates.
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, product_image  # noqa: E402

STORE_EMAIL = "maya@juniperandpine.com"
CLOCK = "2026-03-16T09:30:00-07:00"

# ---------------------------------------------------------------- catalog
PRODUCTS = [
    ("prod_mug", "Stoneware Mug - Speckled", "CR-MUG-01", "18.00", "Ceramics"),
    ("prod_vase", "Hand-blown Glass Vase - Large", "GL-VASE-L", "139.00", "Glassware"),
    ("prod_rug", "Jute Area Rug 5x8", "RG-JUTE-58", "240.00", "Rugs"),
    ("prod_napkin", "Linen Napkin Set of 4 - Oat", "LN-NAP-4", "32.00", "Linen"),
    ("prod_towel", "Organic Bath Towel Set", "BT-TWL-SET", "68.00", "Bath"),
    ("prod_candle", "Soy Candle - Cedar & Smoke", "CN-SOY-12", "24.00", "Candles"),
    ("prod_tumbler", "Recycled Glass Tumblers (6)", "GL-TUM-6", "42.00", "Glassware"),
    ("prod_board", "Walnut Serving Board", "WD-BOARD-M", "56.00", "Kitchen"),
    ("prod_throw", "Waffle Knit Throw - Sand", "TX-THROW", "89.00", "Textiles"),
    ("prod_bowl", "Ceramic Pasta Bowls (2)", "CR-BOWL-2", "38.00", "Ceramics"),
    ("prod_planter", "Terracotta Planter - Medium", "CR-PLNT-M", "34.00", "Garden"),
    ("prod_carafe", "Glass Water Carafe", "GL-CARAFE", "46.00", "Glassware"),
]
SKU = {p[2]: p for p in PRODUCTS}

CUSTOMERS = {
    "emma": ("cust_101", "Emma", "Reyes", "emma.reyes@fastmail.com"),
    "liam": ("cust_102", "Liam", "Chen", "liam@chenstudio.co"),
    "sofia": ("cust_103", "Sofia", "Marquez", "sofia.m@protonmail.com"),
    "grace": ("cust_104", "Grace", "Kim", "gracekim.design@gmail.com"),
    "priya": ("cust_105", "Priya", "Nair", "priya.nair@outlook.com"),
    "tom": ("cust_106", "Tom", "Becker", "tbecker@gmail.com"),
    "noah": ("cust_107", "Noah", "Patel", "noah.patel@icloud.com"),
    "ava": ("cust_108", "Ava", "Thompson", "ava.thompson@yahoo.com"),
    "marcus": ("cust_109", "Marcus", "Bell", "mbell@bellarchitects.com"),
    "hana": ("cust_110", "Hana", "Sato", "hana.sato@gmail.com"),
    "owen": ("cust_111", "Owen", "Gallagher", "owen.g@hey.com"),
    "lucia": ("cust_112", "Lucia", "Romano", "lucia.romano@gmail.com"),
}

ADDRESSES = {
    "emma": ("2140 SE Division St", "Portland", "Oregon", "OR", "97202"),
    "liam": ("88 Valencia St Apt 4", "San Francisco", "California", "CA", "94103"),
    "sofia": ("1520 Pearl St", "Boulder", "Colorado", "CO", "80302"),
    "grace": ("411 E Pine St", "Seattle", "Washington", "WA", "98122"),
    "priya": ("77 Mass Ave", "Cambridge", "Massachusetts", "MA", "02139"),
    "tom": ("3005 N Williams Ave", "Portland", "Oregon", "OR", "97227"),
    "noah": ("950 W Fulton Market", "Chicago", "Illinois", "IL", "60607"),
    "ava": ("12 Elm St", "Austin", "Texas", "TX", "78704"),
    "marcus": ("600 1st Ave", "Seattle", "Washington", "WA", "98104"),
    "hana": ("221 Sutter St", "San Francisco", "California", "CA", "94108"),
    "owen": ("45 Water St", "Brooklyn", "New York", "NY", "11201"),
    "lucia": ("18 Commonwealth Ave", "Boston", "Massachusetts", "MA", "02116"),
}

STANDARD, HEAVY = "9.95", "14.95"

# number, customer, [(sku, qty)], shipping, placed, shipped, delivered|None
ORDERS = [
    (1029, "tom", [("WD-BOARD-M", 1), ("CR-BOWL-2", 1)], STANDARD, "2026-02-14T18:22:00Z", "2026-02-17", "2026-02-20"),
    (1031, "ava", [("CN-SOY-12", 3)], STANDARD, "2026-02-21T16:05:00Z", "2026-02-23", "2026-02-26"),
    (1033, "marcus", [("WD-BOARD-M", 2), ("CR-PLNT-M", 1)], STANDARD, "2026-02-24T20:40:00Z", "2026-02-26", "2026-03-02"),
    (1035, "noah", [("GL-TUM-6", 1)], HEAVY, "2026-02-26T15:10:00Z", "2026-02-28", "2026-03-04"),
    (1038, "priya", [("RG-JUTE-58", 1)], HEAVY, "2026-03-01T13:45:00Z", "2026-03-03", "2026-03-07"),
    (1040, "hana", [("GL-CARAFE", 1), ("CR-MUG-01", 2)], HEAVY, "2026-03-02T22:15:00Z", "2026-03-04", "2026-03-08"),
    (1042, "emma", [("CR-MUG-01", 4), ("CN-SOY-12", 1)], STANDARD, "2026-03-03T17:30:00Z", "2026-03-05", "2026-03-09"),
    (1044, "sofia", [("TX-THROW", 2), ("CN-SOY-12", 1)], STANDARD, "2026-03-04T19:05:00Z", "2026-03-06", "2026-03-10"),
    (1047, "grace", [("BT-TWL-SET", 1)], STANDARD, "2026-02-27T21:00:00Z", "2026-03-01", "2026-03-04"),
    (1049, "owen", [("TX-THROW", 1), ("LN-NAP-4", 1)], STANDARD, "2026-03-06T14:20:00Z", "2026-03-09", "2026-03-12"),
    (1051, "liam", [("GL-VASE-L", 1), ("WD-BOARD-M", 1)], HEAVY, "2026-03-05T23:50:00Z", "2026-03-07", "2026-03-11"),
    (1053, "grace", [("LN-NAP-4", 1), ("CN-SOY-12", 1)], STANDARD, "2026-03-07T16:35:00Z", "2026-03-09", "2026-03-12"),
    (1055, "lucia", [("GL-TUM-6", 2)], HEAVY, "2026-03-10T18:10:00Z", "2026-03-12", "2026-03-15"),
    (1056, "ava", [("CR-BOWL-2", 2)], STANDARD, "2026-03-12T15:55:00Z", "2026-03-13", None),
    (1058, "marcus", [("GL-CARAFE", 2)], HEAVY, "2026-03-14T17:25:00Z", None, None),
    (1059, "hana", [("BT-TWL-SET", 1), ("CN-SOY-12", 2)], STANDARD, "2026-03-15T20:05:00Z", None, None),
]

# Truth for every claim. decision ∈ refund | approval | late | already_refunded
CLAIMS = {
    1042: {"from": "emma.reyes@fastmail.com", "decision": "refund", "lines": {"CR-MUG-01": 3}, "shipping": "0.00", "amount": "54.00"},
    1051: {"from": "liam.chen.home@gmail.com", "decision": "refund", "lines": {"GL-VASE-L": 1}, "shipping": HEAVY, "amount": "153.95"},
    1044: {"from": "sofia.m@protonmail.com", "decision": "refund", "lines": {"TX-THROW": 2}, "shipping": "0.00", "amount": "178.00"},
    1053: {"from": "gracekim.design@gmail.com", "decision": "refund", "lines": {"LN-NAP-4": 1}, "shipping": "0.00", "amount": "32.00"},
    1038: {"from": "priya.nair@outlook.com", "decision": "approval", "approval_amount": "254.95", "amount": "0.00"},
    1029: {"from": "tbecker@gmail.com", "decision": "late", "amount": "0.00"},
    1035: {"from": "noah.patel@icloud.com", "decision": "already_refunded", "prior_refund": "56.95", "amount": "0.00"},
}
TAGGED = sorted(n for n, c in CLAIMS.items() if c["decision"] in ("refund", "approval"))


def money(value) -> str:
    return f"{float(value):.2f}"


def iso(day: str, hour: str = "17:00:00") -> str:
    return f"{day}T{hour}Z"


# ---------------------------------------------------------------- shopify
def build_shopify():
    products = []
    for pid, title, sku, price, ptype in PRODUCTS:
        products.append({
            "id": pid, "title": title, "bodyHtml": f"<p>{title}.</p>", "vendor": "Juniper & Pine",
            "productType": ptype, "handle": sku.lower(), "status": "active", "tags": [ptype.lower()],
            "images": [{"id": f"img_{pid[5:]}", "src": product_image(title), "alt": title, "position": 1}],
            "variants": [{"id": f"var_{pid[5:]}", "productId": pid, "title": "Default Title", "price": price,
                          "compareAtPrice": None, "sku": sku, "inventoryQuantity": 40, "option1": "Default Title",
                          "option2": None, "position": 1}],
            "options": [{"id": f"opt_{pid[5:]}", "name": "Title", "position": 1, "values": ["Default Title"]}],
            "collections": [], "createdAt": "2025-09-01T16:00:00Z", "updatedAt": "2026-01-10T16:00:00Z",
        })

    orders, spent = [], {}
    for number, who, items, shipping, placed, shipped, delivered in ORDERS:
        cid, first, last, email = CUSTOMERS[who]
        street, city, province, code, zipcode = ADDRESSES[who]
        address = {"address1": street, "city": city, "province": province, "provinceCode": code,
                   "country": "United States", "countryCode": "US", "zip": zipcode,
                   "firstName": first, "lastName": last}
        line_items, subtotal = [], 0.0
        for i, (sku, qty) in enumerate(items, 1):
            pid, title, _, price, _ = SKU[sku]
            line_items.append({"id": f"li_{number}_{i}", "productId": pid, "variantId": f"var_{pid[5:]}",
                               "title": title, "variantTitle": "", "quantity": qty, "price": price, "sku": sku,
                               "imageSrc": product_image(title), "fulfillmentStatus": "fulfilled" if shipped else None})
            subtotal += float(price) * qty
        total = subtotal + float(shipping)
        timeline = [{"id": f"evt_{number}_1", "type": "created", "message": "Order was placed", "createdAt": placed, "user": "System"},
                    {"id": f"evt_{number}_2", "type": "payment", "message": f"A ${total:.2f} USD payment was processed on Visa ending in 4242", "createdAt": placed, "user": "System"}]
        if shipped:
            timeline.append({"id": f"evt_{number}_3", "type": "fulfilled",
                             "message": f"Items were fulfilled. Tracking: 1Z84J{number}03 (UPS)",
                             "createdAt": iso(shipped, "19:00:00"), "user": "Ben Russo"})
        order = {
            "id": f"order_{number}", "name": f"#{number}", "orderNumber": number, "email": email,
            "financialStatus": "paid", "fulfillmentStatus": "fulfilled" if shipped else None, "currency": "USD",
            "subtotalPrice": money(subtotal), "totalShippingPrice": shipping, "totalTax": "0.00",
            "totalDiscounts": "0.00", "totalPrice": money(total), "lineItems": line_items,
            "customer": {"id": cid, "firstName": first, "lastName": last, "email": email},
            "shippingAddress": address, "billingAddress": address, "note": "", "tags": [],
            "discountCodes": [], "timeline": timeline, "refunds": [],
            "createdAt": placed, "updatedAt": iso(shipped, "19:00:00") if shipped else placed,
        }
        orders.append(order)
        spent[cid] = spent.get(cid, 0.0) + total

    # #1035 was already refunded in full on Mar 10 (vase-style glass breakage).
    noah = next(o for o in orders if o["orderNumber"] == 1035)
    noah["financialStatus"] = "refunded"
    noah["refunds"] = [{"id": "refund_1035_1", "createdAt": "2026-03-10T18:12:00Z",
                        "lineItems": [{"lineItemId": "li_1035_1", "sku": "GL-TUM-6", "quantity": 1, "amount": "42.00"}],
                        "shipping": "14.95", "total": "56.95", "note": "Arrived broken - photo in email from 3/9"}]
    noah["tags"] = ["damage-claim"]
    noah["timeline"].append({"id": "evt_1035_4", "type": "refund", "message": "Refund of $56.95 was issued: Arrived broken - photo in email from 3/9",
                             "createdAt": "2026-03-10T18:12:00Z", "user": "Jess Alvarez"})
    noah["updatedAt"] = "2026-03-10T18:12:00Z"

    customers = []
    for key, (cid, first, last, email) in CUSTOMERS.items():
        count = sum(1 for o in orders if o["customer"]["id"] == cid)
        customers.append({"id": cid, "firstName": first, "lastName": last, "email": email, "phone": None,
                          "state": "enabled", "ordersCount": count, "totalSpent": money(spent.get(cid, 0)),
                          "tags": [], "acceptsMarketing": key in ("emma", "grace", "ava"),
                          "createdAt": "2025-11-20T16:00:00Z", "note": ""})

    return {
        "store": {"id": "store_1", "name": "Juniper & Pine", "email": STORE_EMAIL, "domain": "juniper-and-pine.myshopify.com",
                  "currency": "USD", "plan": "Shopify", "owner": {"firstName": "Maya", "lastName": "Ortiz", "email": STORE_EMAIL}},
        "products": products, "collections": [], "orders": sorted(orders, key=lambda o: -o["orderNumber"]),
        "customers": customers,
        "discounts": [{"id": "disc_1", "code": "SORRY15", "type": "percentage", "value": "15", "status": "active",
                       "usageCount": 4, "usageLimit": None, "startsAt": "2026-03-01T00:00:00Z", "endsAt": None,
                       "appliesTo": "all", "minimumRequirement": None, "oncePerCustomer": True}],
        "draftOrders": [], "giftCards": [],
        "analytics": {"dailyMetrics": [], "totalSalesThisMonth": 2284.15, "totalOrdersThisMonth": 11, "totalSessionsThisMonth": 1934},
        "pages": [], "blogPosts": [], "navigationMenus": [],
        "settings": {"storeName": "Juniper & Pine", "storeEmail": STORE_EMAIL, "currency": "USD",
                     "timezone": "(GMT-08:00) Pacific Time", "weightUnit": "lb"},
    }


# ---------------------------------------------------------------- slack
SLACK_USERS = [
    ("U01", "Maya Ortiz", "Maya", "maya@juniperandpine.com", "Customer Support Lead"),
    ("U02", "Daniel Okafor", "Daniel", "daniel@juniperandpine.com", "Operations"),
    ("U03", "Jess Alvarez", "Jess", "jess@juniperandpine.com", "Customer Support"),
    ("U04", "Ben Russo", "Ben", "ben@juniperandpine.com", "Warehouse"),
    ("U05", "Nora Lindqvist", "Nora", "nora@juniperandpine.com", "Founder"),
]


def slack_msg(mid, sender, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": sender, "content": text, "timestamp": ts, "threadId": thread,
            "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack():
    users = [{"userId": uid, "fullName": full, "displayName": short, "email": email, "avatar": avatar(full),
              "title": title, "status": "online" if uid in ("U01", "U02") else "away",
              "statusMessage": "Out Mon-Tue" if uid == "U03" else "", "statusEmoji": "", "timeZone": "America/Los_Angeles"}
             for uid, full, short, email, title in SLACK_USERS]
    everyone = [u[0] for u in SLACK_USERS]

    def channel(cid, name, desc, pinned=()):
        return {"channelId": cid, "name": name, "description": desc, "topic": desc, "isPrivate": False,
                "isStarred": cid == "support", "members": everyone, "createdBy": "U05",
                "createdAt": "2025-06-01T16:00:00Z", "pinnedMessages": list(pinned), "unreadCount": 0}

    policy = (
        "Damage claims policy (effective Mar 1) :pushpin:\n"
        "1. Claims have to come in within 14 days of delivery. Delivery = carrier delivery date, not ship date. "
        "Late claims don't get a refund, reply with our one-time 15% code SORRY15 instead.\n"
        "2. Refund only the damaged units, not shipping. If everything in the order arrived damaged, refund the whole order.\n"
        "3. Anything over $150 doesn't get refunded directly. Post it in #refund-approvals (order #, amount, one-line reason) and I'll approve.\n"
        "4. Tag the order damage-claim whenever we accept a claim (refunded or sent for approval).\n"
        "5. Reply to every claim so nobody is left hanging, even if the answer is no."
    )
    messages = {
        "general": [
            slack_msg("m_g1", "U05", "2026-03-09T16:02:00Z", "Spring collection photos are in the drive. Huge thanks to Ben for the warehouse shoot!"),
            slack_msg("m_g2", "U04", "2026-03-13T22:40:00Z", "Reminder: UPS pickup moves to 3pm starting next week."),
        ],
        "support": [
            slack_msg("m_s1", "U02", "2026-03-02T17:15:00Z", policy, reactions=[{"emoji": "+1", "users": ["U01", "U03"], "count": 2}]),
            slack_msg("m_s2", "U03", "2026-03-10T18:20:00Z", "Refunded #1035 (Noah, broken tumblers). Glass + shipping, he'd sent photos on Monday."),
            slack_msg("m_s4", "U03", "2026-03-13T23:05:00Z", "I'm out Mon-Tue. Maya is covering the claims inbox, there's a few new ones since Thursday."),
            slack_msg("m_s5", "U01", "2026-03-13T23:10:00Z", "Got it, feel better!"),
        ],
        "ops": [
            slack_msg("m_o1", "U04", "2026-03-13T21:30:00Z", "Pulled the UPS delivery export for the last 4 weeks, it's on the support laptop as carrier_deliveries.csv"),
            slack_msg("m_o2", "U02", "2026-03-13T21:34:00Z", "thanks Ben"),
            slack_msg("m_o3", "U04", "2026-03-14T17:50:00Z", "Restocked GL-TUM-6 and GL-CARAFE, 40 each."),
        ],
        "refund-approvals": [
            slack_msg("m_r1", "U03", "2026-03-04T19:00:00Z", "#1019 - $212.00 - both cushion covers arrived torn, whole order",
                      reactions=[{"emoji": "white_check_mark", "users": ["U02"], "count": 1}]),
            slack_msg("m_r2", "U02", "2026-03-04T19:25:00Z", "approved, go ahead"),
        ],
    }
    # The policy amendment lives in the thread under the pinned message.
    thread_replies = [
        slack_msg("m_s1_r1", "U02", "2026-03-12T16:45:00Z",
                  "Update as of today: approval limit is now $200, not $150. Also for glassware (GL- SKUs) refund the shipping too, "
                  "UPS keeps crushing those boxes and it's not the customer's fault.", thread="th_policy"),
        slack_msg("m_s1_r2", "U03", "2026-03-12T16:51:00Z", "noted :+1:", thread="th_policy"),
    ]
    messages["support"][0]["threadId"] = None
    messages["support"][0]["replyCount"] = len(thread_replies)
    messages["support"].insert(1, thread_replies[0])
    messages["support"].insert(2, thread_replies[1])
    threads = {"th_policy": {"threadId": "th_policy", "parentMessageId": "m_s1", "channelId": "support", "dmId": None,
                             "replies": [r["messageId"] for r in thread_replies], "followers": ["U01", "U02", "U03"]}}
    return {
        "currentUser": users[0],
        "workspace": {"workspaceId": "ws_jp", "workspaceName": "Juniper & Pine", "icon": avatar("Juniper Pine")},
        "users": users,
        "channels": [channel("general", "general", "Company-wide"),
                     channel("support", "support", "Customer support", pinned=["m_s1"]),
                     channel("ops", "ops", "Warehouse & shipping"),
                     channel("refund-approvals", "refund-approvals", "Refunds that need Daniel's OK")],
        "messages": messages, "threads": threads, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


# ---------------------------------------------------------------- gmail
def email(eid, sender_name, sender, subject, body, ts, read=False, category="primary", attachments=None):
    return {"id": eid, "threadId": f"t_{eid}", "from": {"name": sender_name, "email": sender, "avatar": avatar(sender_name)},
            "to": [{"name": "Juniper & Pine Support", "email": STORE_EMAIL}], "cc": [], "bcc": [],
            "subject": subject, "body": body, "snippet": "", "timestamp": ts, "read": read, "starred": False,
            "important": False, "labels": [], "category": category, "folder": "inbox", "attachments": attachments or []}


def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def build_gmail():
    emails = [
        email("e01", "Emma Reyes", "emma.reyes@fastmail.com", "Cracked mugs - order #1042",
              p("Hi there,", "My order #1042 arrived on Monday and 2 of the 4 speckled mugs are cracked straight through. "
                "The candle is fine. Can you refund the broken ones? Happy to send photos.", "Thanks,<br>Emma"),
              "2026-03-13T17:42:00Z"),
        email("e02", "Liam Chen", "liam.chen.home@gmail.com", "Vase arrived in pieces",
              p("Hello,", "The large glass vase from order 1051 (ordered under my studio email, liam@chenstudio.co) "
                "arrived shattered. The serving board is fine. I'd like a refund for the vase please.", "Liam"),
              "2026-03-13T20:15:00Z"),
        email("e03", "Ava Thompson", "ava.thompson@yahoo.com", "When will my bowls ship?",
              p("Hi! Just wondering when order #1056 will arrive, it's a gift for Saturday. Thanks, Ava"),
              "2026-03-14T15:03:00Z"),
        email("e04", "Sofia Marquez", "sofia.m@protonmail.com", "Damaged throws (#1044)",
              p("Hi,", "Both waffle throws in #1044 came with large bleach-like stains across the middle, I think something "
                "leaked in the truck. The candle was fine. Could I get a refund for the two throws?", "Best,<br>Sofia Marquez"),
              "2026-03-14T18:27:00Z"),
        email("e05", "UPS My Choice", "mcinfo@ups.com", "Your weekly shipment summary",
              p("You shipped 9 packages last week. 1 delivery exception: 1Z84J105103 (delay, delivered next day)."),
              "2026-03-14T09:00:00Z", read=True, category="promotions"),
        email("e06", "Grace Kim", "gracekim.design@gmail.com", "Torn napkins - order #1047",
              p("Hello,", "Order #1047 - the linen napkin set arrived with a long tear along the hem of two napkins, "
                "and the set is clearly unusable for a dinner party. Could you refund it?", "Grace"),
              "2026-03-14T21:48:00Z"),
        email("e07", "Priya Nair", "priya.nair@outlook.com", "Rug ruined",
              p("Hi,", "The jute rug from my order #1038 was delivered soaking wet and now has mildew spots all over it. "
                "There was nothing else in the order. I'd like a full refund.", "Priya"),
              "2026-03-15T02:11:00Z"),
        email("e08", "Tom Becker", "tbecker@gmail.com", "Split board",
              p("Hey,", "The walnut serving board from #1029 arrived last week with a split running down one side. "
                "Can I get my money back on it?", "Tom"),
              "2026-03-13T16:05:00Z"),
        email("e09", "Noah Patel", "noah.patel@icloud.com", "Re: broken tumblers #1035",
              p("Hi again,", "Still waiting to hear back about the broken tumblers from #1035. Can you refund them?", "Noah"),
              "2026-03-14T23:30:00Z"),
        email("e10", "Emma Reyes", "emma.reyes@fastmail.com", "Re: Cracked mugs - order #1042",
              p("Sorry, one correction: after washing them I found a third mug with a hairline crack through the base, "
                "so it's 3 mugs, not 2.", "Emma"),
              "2026-03-15T19:20:00Z"),
        email("e11", "Shopify", "no-reply@shopify.com", "Your payout of $1,842.10 is on its way",
              p("Payout for Mar 9 - Mar 15 has been sent to your bank account ending 7781."),
              "2026-03-16T06:00:00Z", category="promotions"),
        email("e12", "Nora Lindqvist", "nora@juniperandpine.com", "spring newsletter draft",
              p("Maya, can you skim the newsletter draft before Wednesday? Mostly want a second pair of eyes on the shipping FAQ part. Thanks! N"),
              "2026-03-15T22:45:00Z"),
        email("e13", "Etsy Seller Digest", "digest@etsy-sellers.example", "5 ways to cut packaging costs",
              p("This week: recycled mailers, right-sizing boxes, and more."),
              "2026-03-13T12:00:00Z", read=True, category="promotions"),
        email("e14", "Owen Gallagher", "owen.g@hey.com", "Love the throw!",
              p("Just wanted to say the waffle throw from my last order is gorgeous. Ordering another for my sister soon."),
              "2026-03-15T15:30:00Z"),
        email("e15", "Jess Alvarez", "jess@juniperandpine.com", "Re: broken tumblers #1035",
              p("Hi Noah, so sorry about that! I've refunded the tumblers and shipping ($56.95) to your card, it should show up in 5-10 business days. Jess"),
              "2026-03-10T18:15:00Z", read=True),
    ]
    # Jess's reply from last week sits in Sent so the thread history is visible.
    emails[-1]["folder"] = "sent"
    emails[-1]["to"] = [{"name": "Noah Patel", "email": "noah.patel@icloud.com"}]
    emails[-1]["from"] = {"name": "Jess Alvarez", "email": STORE_EMAIL, "avatar": avatar("Juniper Pine")}
    emails[-1]["threadId"] = "t_e09"
    emails[8]["threadId"] = "t_e09"
    emails[9]["threadId"] = "t_e01"
    for e in emails:
        e["snippet"] = e["body"].replace("<p>", "").replace("</p>", " ").replace("<br>", " ")[:100]
    return {
        "user": {"userId": "u1", "username": "Juniper & Pine Support", "email": STORE_EMAIL, "avatar": avatar("Juniper Pine")},
        "emails": emails,
        "labels": [{"id": "l1", "name": "Claims", "color": "#ef4444"}, {"id": "l2", "name": "Suppliers", "color": "#3b82f6"}],
        "drafts": [],
        "settings": {"signature": "--\nMaya Ortiz\nJuniper & Pine", "undoSend": 5},
    }


# ---------------------------------------------------------------- carrier CSV
def carrier_rows():
    rows = []
    for number, _, _, _, _, shipped, delivered in ORDERS:
        if not shipped:
            continue
        tracking = f"1Z84J{number}03"
        if number == 1051:  # first attempt failed, delivered next day
            rows.append([tracking, f"#{number}", shipped, "", "EXCEPTION", "2026-03-10 Delivery attempted - business closed"])
        rows.append([tracking, f"#{number}", shipped, delivered or "", "DELIVERED" if delivered else "IN_TRANSIT", ""])
    rows.sort(key=lambda r: (r[2], r[0]))
    return [["tracking_number", "order", "ship_date", "delivered_date", "status", "exception_detail"]] + rows


# ---------------------------------------------------------------- golden
def new_sent(eid, to_email, to_name, subject, body, thread):
    e = email(eid, "Juniper & Pine Support", STORE_EMAIL, subject, f"<p>{body}</p>", "2026-03-16T17:00:00Z", read=True)
    e.update({"from": {"name": "Juniper & Pine Support", "email": STORE_EMAIL, "avatar": avatar("Juniper Pine")},
              "to": [{"name": to_name, "email": to_email}], "folder": "sent", "threadId": thread})
    return e


REPLIES = {
    1042: ("Emma Reyes", "Re: Cracked mugs - order #1042", "t_e01", "Hi Emma, sorry about the mugs! I've refunded the 3 cracked mugs, $54.00 back to your card."),
    1051: ("Liam Chen", "Re: Vase arrived in pieces", "t_e02", "Hi Liam, refunded the vase plus shipping on #1051, $153.95 total."),
    1044: ("Sofia Marquez", "Re: Damaged throws (#1044)", "t_e04", "Hi Sofia, I've refunded both throws, $178.00."),
    1053: ("Grace Kim", "Re: Torn napkins - order #1047", "t_e06", "Hi Grace, the napkins were on order #1053, I've refunded the napkin set ($32.00)."),
    1038: ("Priya Nair", "Re: Rug ruined", "t_e07", "Hi Priya, I'm so sorry. Since this needs a manager's approval I've sent your full refund for #1038 for review, you'll hear back shortly."),
    1029: ("Tom Becker", "Re: Split board", "t_e08", "Hi Tom, #1029 was delivered on Feb 20, outside our 14-day window, so we can't refund it, but here's 15% off your next order: SORRY15."),
    1035: ("Noah Patel", "Re: broken tumblers #1035", "t_e09", "Hi Noah, we refunded #1035 on March 10 ($56.95 including shipping), it should reach your card within 5-10 business days."),
}


def apply_golden(shopify, slack, gmail, claims=CLAIMS, replies=REPLIES, approvals=("1038",)):
    orders = {o["orderNumber"]: o for o in shopify["orders"]}
    for number, claim in claims.items():
        order = orders[number]
        if claim["decision"] == "refund":
            lines = []
            for sku, qty in claim["lines"].items():
                li = next(l for l in order["lineItems"] if l["sku"] == sku)
                lines.append({"lineItemId": li["id"], "sku": sku, "quantity": qty, "amount": money(float(li["price"]) * qty)})
            total = sum(float(l["amount"]) for l in lines) + float(claim["shipping"])
            order["refunds"].append({"id": f"refund_{number}_g", "createdAt": "2026-03-16T17:00:00.000Z", "lineItems": lines,
                                     "shipping": claim["shipping"], "total": money(total), "note": "Damaged in transit"})
            order["financialStatus"] = "partially_refunded" if total < float(order["totalPrice"]) else "refunded"
        if claim["decision"] in ("refund", "approval") and "damage-claim" not in order["tags"]:
            order["tags"].append("damage-claim")
    for number in approvals:
        claim = claims[int(number)]
        slack["messages"]["refund-approvals"].append(
            slack_msg(f"m_new_{number}", "U01", "2026-03-16T17:05:00Z",
                      f"#{number} - ${claim.get('approval_amount', claim['amount'])} - rug arrived soaked with mildew, whole order"))
    for i, (number, (name, subject, thread, body)) in enumerate(replies.items()):
        gmail["emails"].append(new_sent(f"sent_{i}", claims[number]["from"], name, subject, body, thread))


def claims_csv(claims=CLAIMS):
    rows = [["order", "customer_email", "decision", "refund_amount"]]
    for number in sorted(claims):
        c = claims[number]
        rows.append([f"#{number}", c["from"], c["decision"], c["amount"]])
    return rows


# ---------------------------------------------------------------- variants
def naive_variant(seed):
    """Plausible shallow run: pinned policy only, first email only, ship dates, trusts the order # Grace typed."""
    shopify, slack, gmail = (copy.deepcopy(seed[k]) for k in ("shopify", "slack", "gmail"))
    claims = {
        1042: {**CLAIMS[1042], "lines": {"CR-MUG-01": 2}, "amount": "36.00"},
        1051: {**CLAIMS[1051], "shipping": "0.00", "amount": "139.00"},
        1044: {**CLAIMS[1044], "decision": "approval", "approval_amount": "178.00", "amount": "0.00"},
        1047: {"from": "gracekim.design@gmail.com", "decision": "refund", "lines": {"BT-TWL-SET": 1}, "shipping": "0.00", "amount": "68.00"},
        1038: CLAIMS[1038],
        1029: {**CLAIMS[1029], "decision": "refund", "lines": {"WD-BOARD-M": 1}, "shipping": "0.00", "amount": "56.00"},
        1035: CLAIMS[1035],
    }
    replies = {
        1042: (*REPLIES[1042][:3], "Hi Emma, refunded the 2 cracked mugs, $36.00."),
        1051: (*REPLIES[1051][:3], "Hi Liam, refunded the vase, $139.00."),
        1044: (*REPLIES[1044][:3], "Hi Sofia, your refund is pending manager approval."),
        1047: (*REPLIES[1053][:3], "Hi Grace, refunded $68.00 on #1047."),
        1038: REPLIES[1038],
        1029: (*REPLIES[1029][:3], "Hi Tom, refunded the board, $56.00."),
        1035: REPLIES[1035],
    }
    apply_golden(shopify, slack, gmail, claims, replies, approvals=("1038", "1044"))
    return {"shopify": shopify, "slack": slack, "gmail": gmail}, claims_csv(claims)


def one_slip_variant(seed):
    """Careful run that only misses Emma's correction email."""
    shopify, slack, gmail = (copy.deepcopy(seed[k]) for k in ("shopify", "slack", "gmail"))
    claims = dict(CLAIMS)
    claims[1042] = {**CLAIMS[1042], "lines": {"CR-MUG-01": 2}, "amount": "36.00"}
    replies = dict(REPLIES)
    replies[1042] = (*REPLIES[1042][:3], "Hi Emma, refunded the 2 cracked mugs, $36.00.")
    apply_golden(shopify, slack, gmail, claims, replies)
    return {"shopify": shopify, "slack": slack, "gmail": gmail}, claims_csv(claims)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    seed = {"shopify": build_shopify(), "slack": build_slack(), "gmail": build_gmail()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden = copy.deepcopy(seed)
    apply_golden(golden["shopify"], golden["slack"], golden["gmail"])
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "claims_log.csv", claims_csv())
    write_csv(out / "input" / "carrier_deliveries.csv", carrier_rows())
    write_json(out / "expected.json", {"clock": CLOCK, "claims": {str(k): v for k, v in CLAIMS.items()},
                                       "tagged": TAGGED, "claim_orders": sorted(CLAIMS) + [1047]})

    variants = {
        "golden": (golden, claims_csv()),
        "nop": (seed, None),
        "naive": naive_variant(seed),
        "one_slip": one_slip_variant(seed),
    }
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "claims_log.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
