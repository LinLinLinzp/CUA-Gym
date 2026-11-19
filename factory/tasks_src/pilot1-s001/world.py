#!/usr/bin/env python3
"""World for the birthday-gifts-abroad task (Amazon + Google Calendar + local CSV).

Writes into <out>/:
  seed/{amazon,google_calendar}.json      initial state per site
  golden/{amazon,google_calendar}.json    state after a correct run
  golden_output/birthday_gifts.csv        correct CLI deliverable
  input/gift_list.csv                     agent-visible workspace input
  expected.json                           hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/birthday_gifts.csv}

The story: Emily Carter, an American living in London, sends this year's
family birthday presents from amazon.com straight to her relatives in the US
and puts a "Call <name>" reminder on her (London-time) calendar for 7pm the
recipient's local time on each birthday.

Traps: Kate moved (two saved "Kate Carter" addresses, the current one only
appears on the calendar's housewarming event); Mom's gift was already ordered
last week and her call is already on the calendar; Grandma's first choice is
unavailable; Dad's first choice now costs more than the max (the CSV note
quotes an old price); near-duplicate Kindles / MEATERs / Aura frames; the twins
need two sets; 7pm in the US is the next calendar day in London; Emily's own
items sit in the cart; the default card is the company Amex and one of the two
Visas is expired; Hannah (on the calendar, not on the list) and Jess (Jan 1)
are plausible non-targets.
"""

import copy
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, product_image  # noqa: E402

CLOCK = "2026-11-18T10:15:00+00:00"
USER_EMAIL = "emily.carter.ldn@gmail.com"
TAX = 0.08


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def money(value: float) -> str:
    return f"{value:.2f}"


# ---------------------------------------------------------------- amazon catalog
# (asin, category, brand, title, price, originalPrice, rating, reviews, prime, inStock, stockCount, badges, specs, description)
P = [
    # --- gift-list items and their near-duplicates
    ("B09TMF6742", "Electronics", "Amazon", "Kindle Paperwhite (16 GB) - Agave Green - 6.8\" display, adjustable warm light, up to 10 weeks of battery",
     149.99, 169.99, 4.6, 48211, True, True, None, ["Amazon's Choice"],
     {"Brand": "Amazon", "Storage": "16 GB", "Display": "6.8 in, 300 ppi", "Color": "Agave Green", "Waterproof": "IPX8"},
     "The thinnest, lightest Kindle Paperwhite yet, with a flush-front design and 300 ppi glare-free display."),
    ("B09TMN58KL", "Electronics", "Amazon", "Kindle Paperwhite (16 GB) - Black - 6.8\" display, adjustable warm light, up to 10 weeks of battery",
     149.99, 169.99, 4.6, 48211, True, True, None, ["Best Seller"],
     {"Brand": "Amazon", "Storage": "16 GB", "Display": "6.8 in, 300 ppi", "Color": "Black", "Waterproof": "IPX8"},
     "The thinnest, lightest Kindle Paperwhite yet, with a flush-front design and 300 ppi glare-free display."),
    ("B09SWV1FSS", "Electronics", "Amazon", "Kindle Paperwhite Signature Edition (32 GB) - Agave Green - wireless charging, auto-adjusting front light",
     189.99, None, 4.7, 21904, True, True, None, [],
     {"Brand": "Amazon", "Storage": "32 GB", "Display": "6.8 in, 300 ppi", "Color": "Agave Green", "Charging": "Wireless + USB-C"},
     "Signature Edition with 32 GB, wireless charging and an auto-adjusting front light."),
    ("B09WRSHHJS", "Electronics", "Amazon", "Kindle Paperwhite Kids (16 GB) - Emerald Forest cover - includes ad-free content and 2-year worry-free guarantee",
     169.99, None, 4.7, 9310, True, True, None, [],
     {"Brand": "Amazon", "Storage": "16 GB", "Display": "6.8 in", "Cover": "Emerald Forest", "Age Range": "8+"},
     "Kindle Paperwhite Kids includes a kid-friendly cover and a year of Amazon Kids+."),
    ("B099TJGJ91", "Electronics", "Bose", "Bose SoundLink Flex Bluetooth Portable Speaker, Wireless Waterproof Speaker for Outdoor Travel - Stone Blue",
     149.00, None, 4.7, 61377, True, True, None, [],
     {"Brand": "Bose", "Battery Life": "12 hours", "Waterproof": "IP67", "Color": "Stone Blue"},
     "Deep, clear sound in a rugged, waterproof speaker that floats."),
    ("B0BBS6KGN1", "Toys & Games", "LEGO", "LEGO Jurassic World T. rex Breakout 76944 Dinosaur Toy Building Set for Kids Ages 7+",
     39.99, None, 4.8, 5528, True, True, None, ["Best Seller"],
     {"Brand": "LEGO", "Set Number": "76944", "Pieces": "140", "Age Range": "7+"},
     "Kids recreate the T. rex escape from Jurassic World with this buildable dinosaur and jeep."),
    ("B0CFVZJ2PQ", "Toys & Games", "LEGO", "LEGO Jurassic World T. rex & Atrociraptor Dinosaur Breakout 76948 Building Toy Set",
     79.99, None, 4.8, 3110, True, True, None, [],
     {"Brand": "LEGO", "Set Number": "76948", "Pieces": "466", "Age Range": "8+"},
     "Two dinosaurs, a truck and a motorcycle for a big breakout adventure."),
    ("B0BBS3GFW8", "Toys & Games", "LEGO", "LEGO Jurassic World Velociraptor Escape 76957 Building Toy Set, Ages 4+",
     19.99, None, 4.7, 2214, True, True, None, [],
     {"Brand": "LEGO", "Set Number": "76957", "Pieces": "137", "Age Range": "4+"},
     "A starter set with a buildable raptor and helicopter."),
    ("B07N8RJ2W5", "Toys & Games", "Melissa & Doug", "Melissa & Doug Dinosaurs Floor Puzzle (48 pcs, 2 x 3 feet)",
     24.99, None, 4.8, 18740, True, True, None, [],
     {"Brand": "Melissa & Doug", "Pieces": "48", "Age Range": "3+"},
     "Extra-thick cardboard pieces form a 2 x 3 foot dinosaur scene."),
    ("B0BNQH1R5W", "Electronics", "Aura", "Aura Carver Digital Photo Frame, 10.1\" HD WiFi frame, free unlimited storage - Charcoal",
     149.00, None, 4.7, 12093, True, False, None, ["Amazon's Choice"],
     {"Brand": "Aura", "Screen Size": "10.1 in", "Resolution": "1280 x 800", "Color": "Charcoal"},
     "Invite family to add photos from anywhere with the free Aura app."),
    ("B0BNQK9T3Z", "Electronics", "Aura", "Aura Carver Mat Digital Photo Frame, 10.1\" with white mat border - Sea Salt",
     179.00, None, 4.8, 4021, True, True, None, [],
     {"Brand": "Aura", "Screen Size": "10.1 in", "Resolution": "1280 x 800", "Color": "Sea Salt"},
     "The Carver frame with a gallery-style white mat."),
    ("B0C1S6Z5QK", "Electronics", "Nixplay", "Nixplay 10.1 inch Touch Screen Digital Picture Frame with WiFi - share photos and videos via app",
     129.99, 159.99, 4.4, 7712, True, True, None, [],
     {"Brand": "Nixplay", "Screen Size": "10.1 in", "Touch Screen": "Yes", "Storage": "Cloud + 16 GB"},
     "Share photos instantly to a frame on the other side of the world."),
    ("B08FMQ4M1S", "Electronics", "Skylight", "Skylight Frame 10 inch WiFi Digital Picture Frame, email photos from anywhere",
     159.99, None, 4.5, 30551, True, True, None, [],
     {"Brand": "Skylight", "Screen Size": "10 in", "Touch Screen": "Yes"},
     "Email photos straight to the frame."),
    ("B0CGV2XGRL", "Home & Kitchen", "MEATER", "MEATER Pro Wireless Smart Meat Thermometer, dishwasher safe, unlimited range with app",
     99.95, None, 4.6, 6604, True, True, None, [],
     {"Brand": "MEATER", "Probes": "1", "Range": "Bluetooth + WiFi via app", "Dishwasher Safe": "Yes"},
     "The most accurate MEATER yet with a thinner probe and unlimited WiFi range."),
    ("B07H9SQB4B", "Home & Kitchen", "MEATER", "MEATER Plus Wireless Smart Meat Thermometer, 165ft range, for BBQ, oven and grill",
     79.95, 99.95, 4.5, 41120, True, True, None, ["Best Seller"],
     {"Brand": "MEATER", "Probes": "1", "Range": "165 ft", "Dishwasher Safe": "No"},
     "Truly wireless meat thermometer with a Bluetooth repeater in the charger."),
    ("B07XXSYLHN", "Home & Kitchen", "Stanley", "Stanley Classic Legendary Vacuum Insulated Bottle 1.5 QT - Hammertone Green",
     45.00, None, 4.8, 52841, True, True, None, [],
     {"Brand": "Stanley", "Capacity": "1.5 qt", "Color": "Hammertone Green", "Keeps Hot": "32 hours"},
     "The classic green thermos, built for life."),
    ("B07NQRM6ML", "Home & Kitchen", "Ember", "Ember Temperature Control Smart Mug 2, 10 oz, App-Controlled Heated Coffee Mug - Black",
     129.95, None, 4.3, 20145, True, True, None, [],
     {"Brand": "Ember", "Capacity": "10 oz", "Battery": "1.5 hours", "Color": "Black"},
     "Keeps coffee at your preferred temperature from first sip to last."),
    ("B07NQRZ4LR", "Home & Kitchen", "Ember", "Ember Temperature Control Smart Mug 2, 14 oz - Sage Green",
     149.95, None, 4.3, 8840, True, True, None, [],
     {"Brand": "Ember", "Capacity": "14 oz", "Battery": "80 min", "Color": "Sage Green"},
     "The larger Ember Mug 2 in sage green."),
    ("B08KTZ8249", "Home & Kitchen", "Barefoot Dreams", "Barefoot Dreams CozyChic Throw Blanket, 54 x 72 in - Ocean",
     147.00, None, 4.8, 6022, True, True, None, [],
     {"Brand": "Barefoot Dreams", "Size": "54 x 72 in", "Color": "Ocean"},
     "The famously soft CozyChic knit throw."),
    ("B0BSL5P5BH", "Electronics", "Fujifilm", "Fujifilm Instax Mini 12 Instant Camera - Pastel Blue",
     79.95, None, 4.7, 26318, True, True, None, ["Best Seller"],
     {"Brand": "Fujifilm", "Film": "Instax Mini", "Color": "Pastel Blue"},
     "Point, shoot and print with automatic exposure."),
    ("B0B7HS6Y4H", "Electronics", "Fujifilm", "Fujifilm Instax Mini Instant Film, Twin Pack (20 exposures)",
     14.99, None, 4.8, 90211, True, True, None, [],
     {"Brand": "Fujifilm", "Exposures": "20"},
     "Two packs of Instax Mini film."),
    ("B00U26V4VQ", "Toys & Games", "CATAN Studio", "CATAN Board Game (Base Game) - Family Board Game for Adults and Kids",
     44.99, None, 4.8, 77210, True, True, None, ["Best Seller"],
     {"Brand": "CATAN Studio", "Players": "3-4", "Play Time": "60-90 min"},
     "Trade, build and settle the island of Catan."),
    # --- Emily's own cart items
    ("B0BWJMR6V6", "Electronics", "Anker", "Anker USB-C to USB-C Cable, 240W 6ft (2-Pack), braided fast charging cable",
     12.99, 16.99, 4.7, 30455, True, True, None, [],
     {"Brand": "Anker", "Length": "6 ft", "Pack": "2"}, "Braided USB-C cables for laptops and phones."),
    ("B015NBTAOW", "Books", "Moleskine", "Moleskine Classic Notebook, Hard Cover, Large (5\" x 8.25\") Ruled - Black",
     19.95, None, 4.7, 51003, True, True, None, [],
     {"Brand": "Moleskine", "Pages": "240", "Ruling": "Ruled"}, "The classic hard-cover notebook."),
    # --- noise catalog
    ("B0D1XD1ZV3", "Electronics", "Apple", "Apple AirPods Pro 2 Wireless Earbuds, Active Noise Cancellation, USB-C",
     189.99, 249.00, 4.7, 98012, True, True, None, ["Best Seller"], {"Brand": "Apple", "Battery Life": "6 hours"}, "Rich audio with adaptive noise cancellation."),
    ("B0BDHWDR12", "Electronics", "Amazon", "Echo Dot (5th Gen) Smart speaker with Alexa - Charcoal",
     49.99, None, 4.7, 211873, True, True, None, [], {"Brand": "Amazon", "Color": "Charcoal"}, "Our best-sounding Echo Dot yet."),
    ("B0CHWRXH8B", "Electronics", "Apple", "Apple iPad 10.9-inch (10th generation) Wi-Fi 64GB - Blue",
     349.00, 449.00, 4.8, 18203, True, True, 6, [], {"Brand": "Apple", "Storage": "64 GB"}, "Colorful, all-screen iPad."),
    ("B0C8PSMPTH", "Electronics", "Tile", "Tile Mate (2024) Bluetooth Tracker, 4-pack",
     59.99, 79.99, 4.4, 12011, True, True, None, [], {"Brand": "Tile", "Pack": "4"}, "Find keys, bags and more."),
    ("B0B1VQ1ZQY", "Books", "Penguin", "Lessons in Chemistry: A Novel by Bonnie Garmus (Paperback)",
     11.99, 18.00, 4.6, 140221, True, True, None, [], {"Publisher": "Anchor", "Pages": "400"}, "A novel set in 1960s California."),
    ("B0BGYDQSN3", "Books", "Ten Speed Press", "Salt, Fat, Acid, Heat: Mastering the Elements of Good Cooking (Hardcover)",
     24.49, 40.00, 4.8, 23541, True, True, None, [], {"Publisher": "Simon & Schuster", "Pages": "480"}, "The four elements of good cooking."),
    ("B08FHBTK8K", "Books", "Riverhead", "Tomorrow, and Tomorrow, and Tomorrow by Gabrielle Zevin (Hardcover)",
     16.20, 28.00, 4.4, 88410, True, True, None, [], {"Publisher": "Knopf", "Pages": "416"}, "A novel about friendship and video games."),
    ("B0CB1FW8YZ", "Books", "Little Tiger", "Dinosaur Roar! Board Book",
     7.99, None, 4.8, 5520, True, True, None, [], {"Publisher": "Puffin", "Pages": "24"}, "A rhyming dinosaur book for little ones."),
    ("B00006JSUA", "Home & Kitchen", "Lodge", "Lodge 10.25 Inch Cast Iron Pre-Seasoned Skillet",
     19.90, 34.95, 4.7, 155390, True, True, None, ["Amazon's Choice"], {"Brand": "Lodge", "Size": "10.25 in"}, "Pre-seasoned and ready to use."),
    ("B07W55DDFB", "Home & Kitchen", "Instant Pot", "Instant Pot Duo 7-in-1 Electric Pressure Cooker, 6 Quart",
     89.99, 119.99, 4.7, 167004, True, True, None, ["Best Seller"], {"Brand": "Instant Pot", "Capacity": "6 qt"}, "Seven appliances in one."),
    ("B0B8F6YTHN", "Home & Kitchen", "YETI", "YETI Rambler 20 oz Tumbler with MagSlider Lid - Navy",
     35.00, None, 4.8, 64012, True, True, None, [], {"Brand": "YETI", "Capacity": "20 oz"}, "Double-wall vacuum insulated tumbler."),
    ("B09V3KXJPB", "Home & Kitchen", "ThermoPro", "ThermoPro TP19H Digital Meat Thermometer with Motion Sensing",
     19.99, 29.99, 4.7, 43208, True, True, None, [], {"Brand": "ThermoPro", "Probes": "1"}, "Instant-read thermometer with a backlit display."),
    ("B0C5S8ZQ1H", "Home & Kitchen", "Brooklinen", "Brooklinen Luxe Sateen Sheet Set, Queen - Cream",
     179.00, None, 4.6, 3022, False, True, None, [], {"Brand": "Brooklinen", "Size": "Queen"}, "Buttery-smooth 480 thread count sateen."),
    ("B07FZ8S74R", "Fashion", "UGG", "UGG Women's Scuffette II Slipper - Chestnut",
     99.95, None, 4.7, 40012, True, True, None, [], {"Brand": "UGG", "Material": "Sheepskin"}, "Cozy sheepskin slippers."),
    ("B0BHX9V2K1", "Fashion", "Carhartt", "Carhartt Men's Knit Cuffed Beanie - Brown",
     19.99, None, 4.8, 120044, True, True, None, ["Best Seller"], {"Brand": "Carhartt"}, "The classic workwear beanie."),
    ("B09QXJ3V4N", "Fashion", "Columbia", "Columbia Women's Benton Springs Full Zip Fleece Jacket",
     39.99, 60.00, 4.7, 70321, True, True, None, [], {"Brand": "Columbia"}, "Soft, warm full-zip fleece."),
    ("B0CJ4L2P8Q", "Toys & Games", "LEGO", "LEGO Star Wars Millennium Falcon 75375 Building Set",
     84.99, None, 4.9, 6620, True, True, None, [], {"Brand": "LEGO", "Set Number": "75375", "Pieces": "921"}, "Build the iconic starship."),
    ("B0BRBWQ1Y5", "Toys & Games", "Magna-Tiles", "Magna-Tiles Classic 32-Piece Magnetic Construction Set",
     49.99, None, 4.8, 33012, True, True, None, [], {"Brand": "Magna-Tiles", "Pieces": "32"}, "The original magnetic tiles."),
    ("B07Q2M6NSM", "Toys & Games", "Ticket to Ride", "Ticket to Ride Board Game - Cross-Country Train Adventure",
     39.99, 54.99, 4.8, 41002, True, True, None, [], {"Brand": "Days of Wonder", "Players": "2-5"}, "Collect cards and claim railway routes."),
    ("B004Y72ZJO", "Beauty", "L'Occitane", "L'Occitane Shea Butter Hand Cream Trio Gift Set",
     30.00, None, 4.8, 9021, True, True, None, [], {"Brand": "L'Occitane", "Size": "3 x 1 oz"}, "Nourishing hand creams in a gift box."),
    ("B01MSSDEPK", "Beauty", "CeraVe", "CeraVe Moisturizing Cream, 16 oz",
     17.78, None, 4.8, 120556, True, True, None, ["Best Seller"], {"Brand": "CeraVe", "Size": "16 oz"}, "Daily face and body moisturizer."),
    ("B0BQ1D2YH4", "Beauty", "Slip", "Slip Silk Pillowcase, Queen - Pink",
     89.00, None, 4.6, 12433, True, True, None, [], {"Brand": "Slip", "Size": "Queen"}, "Pure mulberry silk pillowcase."),
]
PRODUCTS = {row[0]: row for row in P}


def build_products():
    products = []
    for i, (asin, cat, brand, title, price, orig, rating, count, prime, in_stock, stock, badges, specs, desc) in enumerate(P):
        img = product_image(title)
        products.append({
            "id": asin, "title": title, "price": price, "originalPrice": orig, "rating": rating, "reviewCount": count,
            "image": img, "images": [img, product_image(f"{brand} {title.split(',')[0]} - detail")],
            "description": desc,
            "bulletPoints": [desc] + [f"{k}: {v}" for k, v in specs.items()],
            "specs": specs, "category": cat, "brand": brand, "prime": prime, "inStock": in_stock, "stockCount": stock,
            "seller": "Amazon.com" if brand in ("Amazon", "Apple", "LEGO") else brand, "badges": badges,
            "createdAt": f"2025-{(i % 12) + 1:02d}-15T00:00:00.000Z",
        })
    return products


# ---------------------------------------------------------------- addresses & cards
def addr(aid, name, street, city, state, zipc, phone, default=False):
    return {"id": aid, "fullName": name, "street": street, "city": city, "state": state, "zip": zipc,
            "country": "United States", "phone": phone, "isDefault": default}


ADDRESSES = [
    addr("addr1", "Linda Carter", "2817 Northwest Blvd", "Columbus", "OH", "43221", "614-555-0182", True),
    addr("addr2", "Kate Carter", "1820 Larimer St Apt 5B", "Denver", "CO", "80202", "720-555-0147"),
    addr("addr3", "Ruth Holloway", "455 Bayfront Dr Unit 304", "Sarasota", "FL", "34236", "941-555-0119"),
    addr("addr4", "Ben Carter", "3316 SE Taylor St", "Portland", "OR", "97214", "503-555-0163"),
    addr("addr5", "Jess Nguyen", "77 Bedford Ave Apt 3R", "Brooklyn", "NY", "11211", "347-555-0175"),
    addr("addr6", "Tom Becker", "1104 E 6th St", "Austin", "TX", "78702", "512-555-0131"),
    addr("addr-1794249120000", "Kate Carter", "4471 Tennyson St", "Denver", "CO", "80212", "720-555-0147"),
]
ADDR = {a["id"]: a for a in ADDRESSES}
CARDS = [
    {"id": "pm1", "last4": "1007", "brand": "American Express", "expiry": "05/28", "isDefault": True},
    {"id": "pm2", "last4": "4417", "brand": "Visa", "expiry": "08/29", "isDefault": False},
    {"id": "pm3", "last4": "2290", "brand": "Visa", "expiry": "09/26", "isDefault": False},
]
CARD = {c["id"]: c for c in CARDS}

PERSONAL_CART = [{"productId": "B0BWJMR6V6", "quantity": 2}, {"productId": "B015NBTAOW", "quantity": 1}]


def norm_addr(a):
    return {k: a[k] for k in ("fullName", "street", "city", "state", "zip", "country", "phone")}


def seed_order(date, status, items, address_id, card_id, tracking, eta):
    subtotal = sum(PRODUCTS[pid][4] * q for pid, q in items)
    card = CARD[card_id]
    return {"id": f"ord-{ms(date)}", "date": date, "status": status, "total": round(subtotal * (1 + TAX), 2),
            "shippingAddress": norm_addr(ADDR[address_id]),
            "items": [{"productId": pid, "quantity": q} for pid, q in items],
            "paymentMethod": {"last4": card["last4"], "brand": card["brand"]},
            "trackingNumber": tracking, "estimatedDelivery": eta}


SEED_ORDERS = [
    seed_order("2026-11-16T21:04:00.000Z", "Processing", [("B0C8PSMPTH", 1)], "addr1", "pm2", None, "2026-11-21"),
    seed_order("2026-11-12T19:22:00.000Z", "Shipped", [("B07NQRM6ML", 1)], "addr1", "pm2", "1Z4F82W70398812245", "2026-11-19"),
    seed_order("2026-11-03T18:40:00.000Z", "Delivered", [("B00U26V4VQ", 1)], "addr6", "pm2", "1Z4F82W70391120873", None),
    seed_order("2026-10-21T20:15:00.000Z", "Delivered", [("B0B1VQ1ZQY", 1), ("B08FHBTK8K", 1)], "addr1", "pm2", "9400111899561230087", None),
    seed_order("2026-10-02T17:55:00.000Z", "Delivered", [("B0B8F6YTHN", 1)], "addr2", "pm3", "1Z4F82W70384410566", None),
    seed_order("2026-09-14T16:30:00.000Z", "Delivered", [("B0BRBWQ1Y5", 1), ("B0CB1FW8YZ", 2)], "addr4", "pm3", "1Z4F82W70379921904", None),
    seed_order("2026-09-02T15:12:00.000Z", "Cancelled", [("B0CHWRXH8B", 1)], "addr1", "pm1", None, None),
    seed_order("2026-08-19T14:48:00.000Z", "Delivered", [("B004Y72ZJO", 1)], "addr3", "pm3", "9400111899548810233", None),
    seed_order("2026-07-30T18:05:00.000Z", "Delivered", [("B07W55DDFB", 1)], "addr1", "pm1", "1Z4F82W70361102257", None),
    seed_order("2026-06-08T13:20:00.000Z", "Delivered", [("B0BHX9V2K1", 2)], "addr4", "pm3", "1Z4F82W70350087712", None),
]
MOM_ORDER_ID = SEED_ORDERS[1]["id"]

REVIEWS = [
    ("rev-k1", "B09TMF6742", "BookClubBeth", 5, "Love the green!", "Light, crisp screen, and the warm light is great for reading in bed. The green color is even nicer in person."),
    ("rev-k2", "B09TMN58KL", "CommuterReader", 4, "Great upgrade", "Faster page turns than my old one and the battery lasts weeks. Wish it came with a charger."),
    ("rev-l1", "B0BBS6KGN1", "DinoDad", 5, "My 6 year old built it alone", "Took about an hour with a bit of help on the jeep. The T. rex jaw moves, huge hit."),
    ("rev-a1", "B0BNQH1R5W", "GrandmaOfSeven", 5, "Easiest frame for grandparents", "My kids add photos from three states and they just appear. No setup on my end at all."),
    ("rev-n1", "B0C1S6Z5QK", "FarAwayFamily", 4, "Good value frame", "Touch screen is responsive and the app is easy. Slightly less sharp than the Aura but cheaper."),
    ("rev-m1", "B0CGV2XGRL", "PitmasterPete", 5, "Best thermometer I've owned", "The WiFi range is the real deal. Price went up recently but still worth it."),
    ("rev-s1", "B07XXSYLHN", "CampCoffee", 5, "Same as my grandpa's", "Keeps coffee hot all day on the boat. Built like a tank."),
    ("rev-e1", "B07NQRM6ML", "LatteLinda", 4, "Pricey but I use it daily", "Coffee stays hot through my whole morning. Battery could be better."),
]


def build_amazon():
    reviews = [{"id": rid, "productId": pid, "userId": f"u{100 + i}", "userName": name, "rating": rating, "title": title,
                "content": body, "date": f"2026-{9 + i % 3:02d}-{10 + i:02d}T00:00:00.000Z", "helpful": 3 + 7 * i,
                "verifiedPurchase": True}
               for i, (rid, pid, name, rating, title, body) in enumerate(REVIEWS)]
    return {
        "products": build_products(),
        "user": {"id": "u1", "name": "Emily Carter", "email": USER_EMAIL, "address": copy.deepcopy(ADDRESSES[0]),
                 "addresses": copy.deepcopy(ADDRESSES), "paymentMethod": copy.deepcopy(CARDS[0]),
                 "paymentMethods": copy.deepcopy(CARDS)},
        "cart": copy.deepcopy(PERSONAL_CART),
        "wishlist": ["B09TMN58KL", "B0BQ1D2YH4", "B0D1XD1ZV3"],
        "savedForLater": [],
        "orders": copy.deepcopy(SEED_ORDERS),
        "reviews": reviews,
        "recentSearches": ["usb c cable 6ft", "moleskine large ruled", "tile mate", "slip silk pillowcase"],
        "recentlyViewed": ["B0BWJMR6V6", "B015NBTAOW", "B0C8PSMPTH", "B0BQ1D2YH4", "B09TMN58KL"],
    }


# ---------------------------------------------------------------- google calendar
COLORS = {"c1": "bg-blue-500", "c2": "bg-green-500", "c3": "bg-purple-500", "c4": "bg-yellow-500"}


def ev(eid, cal, title, start, end, all_day=False, location="", description="", recurring="none", reminders=None, guests=None):
    return {"id": eid, "calendarId": cal, "title": title, "start": start, "end": end, "allDay": all_day,
            "location": location, "description": description, "guests": guests or [], "color": COLORS[cal],
            "recurring": recurring, "reminders": reminders if reminders is not None else [{"type": "popup", "minutes": 10}]}


def birthday(eid, title, day, description=""):
    start = f"{day}T00:00:00.000Z"
    end = (datetime.fromisoformat(day) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
    return ev(eid, "c4", title, start, end, all_day=True, description=description, recurring="yearly", reminders=[])


def build_calendar():
    events = [
        birthday("bday_tom", "Tom Becker's birthday", "1991-11-10"),
        birthday("bday_mom", "Mom's birthday", "1962-11-24"),
        birthday("bday_hannah", "Hannah Okafor's birthday", "1995-11-29", "Hannah from work - card + cake in the office"),
        birthday("bday_kate", "Kate's birthday", "1994-12-03"),
        birthday("bday_twins", "Leo & Max's birthday", "2020-12-09", "Ben & Priya's twins"),
        birthday("bday_ruth", "Grandma Ruth's birthday", "1938-12-20"),
        birthday("bday_dad", "Dad's birthday", "1956-12-27"),
        birthday("bday_jess", "Jess's birthday", "1993-01-01"),
        birthday("bday_oliver", "Oliver's birthday", "1992-02-06"),
        birthday("bday_priya", "Priya's birthday", "1991-03-14"),
        birthday("bday_ben", "Ben's birthday", "1990-06-08"),
        birthday("bday_sam", "Sam Ortiz's birthday", "1993-08-22", "Kate's partner"),
        # family / personal
        ev("evt_housewarming", "c3", "Kate's housewarming (FaceTime in)", "2026-11-14T22:00:00.000Z", "2026-11-14T23:30:00.000Z",
           location="4471 Tennyson St, Denver, CO 80212",
           description="Kate & Sam's new place! They moved in on the 7th. FaceTime in for the tour, 3pm their time."),
        ev("evt_call_mom", "c1", "Call Mom", "2026-11-25T00:00:00.000Z", "2026-11-25T00:30:00.000Z"),
        ev("evt_thanksgiving", "c3", "Thanksgiving FaceTime with the Carters", "2026-11-26T22:00:00.000Z", "2026-11-26T23:30:00.000Z",
           description="Everyone at Mom & Dad's in Columbus"),
        ev("evt_dentist", "c1", "Dentist - Dr. Shah", "2026-11-20T08:30:00.000Z", "2026-11-20T09:15:00.000Z", location="Harley St Dental"),
        ev("evt_gym1", "c1", "Spin class", "2026-11-17T07:00:00.000Z", "2026-11-17T07:45:00.000Z", location="Third Space Soho", recurring="weekly"),
        ev("evt_gym2", "c1", "Yoga", "2026-11-19T18:30:00.000Z", "2026-11-19T19:30:00.000Z", location="Third Space Soho", recurring="weekly"),
        ev("evt_oliver_dinner", "c1", "Dinner with Oliver & Mia", "2026-11-21T19:30:00.000Z", "2026-11-21T22:00:00.000Z", location="Dishoom Shoreditch"),
        ev("evt_winter_wonder", "c1", "Hyde Park Winter Wonderland", "2026-12-05T15:00:00.000Z", "2026-12-05T18:00:00.000Z"),
        ev("evt_xmas_party", "c2", "Office holiday party", "2026-12-11T18:00:00.000Z", "2026-12-11T23:00:00.000Z", location="The Ivy, Covent Garden"),
        ev("evt_xmas", "c1", "Christmas lunch at Oliver's parents'", "2026-12-25T12:00:00.000Z", "2026-12-25T18:00:00.000Z", location="Richmond"),
        ev("evt_nye", "c1", "NYE at Jess's (video)", "2027-01-01T04:30:00.000Z", "2027-01-01T05:30:00.000Z",
           description="Midnight in New York"),
        ev("evt_flat", "c1", "Flat inspection", "2026-12-02T10:00:00.000Z", "2026-12-02T10:30:00.000Z", location="Home"),
        ev("evt_haircut", "c1", "Haircut", "2026-12-08T17:30:00.000Z", "2026-12-08T18:15:00.000Z", location="Hare & Bone"),
        ev("evt_call_tom", "c1", "Call Tom", "2026-11-11T01:00:00.000Z", "2026-11-11T01:30:00.000Z"),
        # work
        ev("evt_standup", "c2", "Design standup", "2026-11-16T09:30:00.000Z", "2026-11-16T09:45:00.000Z", location="Google Meet", recurring="weekly"),
        ev("evt_standup2", "c2", "Design standup", "2026-11-18T09:30:00.000Z", "2026-11-18T09:45:00.000Z", location="Google Meet", recurring="weekly"),
        ev("evt_1on1", "c2", "1:1 with Priyanka", "2026-11-19T14:00:00.000Z", "2026-11-19T14:30:00.000Z", recurring="weekly"),
        ev("evt_crit", "c2", "Design crit", "2026-11-20T13:00:00.000Z", "2026-11-20T14:00:00.000Z", location="Room 4B"),
        ev("evt_q4", "c2", "Q4 roadmap review", "2026-11-24T15:00:00.000Z", "2026-11-24T16:30:00.000Z", location="Room 2A"),
        ev("evt_offsite", "c2", "Team offsite", "2026-12-01T09:00:00.000Z", "2026-12-01T17:00:00.000Z", location="Second Home Spitalfields"),
        ev("evt_usability", "c2", "Usability sessions", "2026-12-03T10:00:00.000Z", "2026-12-03T16:00:00.000Z", location="Lab"),
        ev("evt_ny_sync", "c2", "Sync with NY team", "2026-12-09T16:00:00.000Z", "2026-12-09T17:00:00.000Z", location="Google Meet"),
        ev("evt_review", "c2", "Year-end review", "2026-12-15T11:00:00.000Z", "2026-12-15T12:00:00.000Z"),
        ev("evt_ooo", "c2", "Out of office", "2026-12-21T00:00:00.000Z", "2027-01-04T00:00:00.000Z", all_day=True, reminders=[]),
    ]
    return {
        "user": {"id": "u1", "username": "Emily Carter", "email": USER_EMAIL, "avatar": avatar("Emily Carter")},
        "calendars": [
            {"id": "c1", "name": "Emily Carter", "color": "bg-blue-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c2", "name": "Work", "color": "bg-green-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c3", "name": "Family", "color": "bg-purple-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c4", "name": "Birthdays", "color": "bg-yellow-500", "textColor": "text-white", "visible": True, "userId": "u1"},
        ],
        "events": events,
        "view": "month",
        "currentDate": "2026-11-18T10:15:00.000Z",
        "sidebarOpen": True,
        "settings": {"weekStart": 1, "defaultDuration": 60},
    }


# ---------------------------------------------------------------- gift list (input)
GIFT_LIST = [
    ["recipient", "asin", "idea", "max_price_each", "backup_asin", "backup_idea", "ship_to", "notes"],
    ["Mom", "B07NQRM6ML", "Ember Mug 2 10 oz (black)", "140", "B08KTZ8249", "Barefoot Dreams throw", "Mom & Dad's house", "she keeps microwaving her coffee"],
    ["Tom", "B00U26V4VQ", "Catan", "50", "B07Q2M6NSM", "Ticket to Ride", "Tom's place in Austin", ""],
    ["Kate", "B09TMF6742", "Kindle Paperwhite 16GB - the green one", "160", "B099TJGJ91", "Bose SoundLink Flex", "Kate's place", "she reads on her phone and complains about it"],
    ["Leo & Max", "B0BBS6KGN1", "LEGO Jurassic World T. rex Breakout", "45", "B07N8RJ2W5", "Melissa & Doug dino floor puzzle", "Ben & Priya's", "one each - same set for both so there's no fighting"],
    ["Grandma Ruth", "B0BNQH1R5W", "Aura Carver photo frame (charcoal)", "150", "B0C1S6Z5QK", "Nixplay 10.1in touch frame", "Grandma's condo", "I'll load the family album once it's set up"],
    ["Dad", "B0CGV2XGRL", "MEATER Pro thermometer", "80", "B07XXSYLHN", "Stanley classic bottle 1.5qt (green)", "Mom & Dad's house", "was $79.95 when I looked in September"],
    ["Jess", "B0BSL5P5BH", "Instax Mini 12 (pastel blue)", "90", "B0B7HS6Y4H", "Instax mini film twin pack", "Jess's apartment", ""],
]

# ---------------------------------------------------------------- truth
# recipient -> (asin, qty, address_id, birthday, call_start_utc, title keys)
TARGETS = {
    "Kate": ("B09TMF6742", 1, "addr-1794249120000", "2026-12-03", "2026-12-04T02:00:00.000Z", ["kate"]),
    "Leo & Max": ("B0BBS6KGN1", 2, "addr4", "2026-12-09", "2026-12-10T03:00:00.000Z", ["leo", "max", "twins"]),
    "Grandma Ruth": ("B0C1S6Z5QK", 1, "addr3", "2026-12-20", "2026-12-21T00:00:00.000Z", ["grandma", "ruth"]),
    "Dad": ("B07XXSYLHN", 1, "addr1", "2026-12-27", "2026-12-28T00:00:00.000Z", ["dad"]),
}
ORDER_TIMES = ["2026-11-18T10:41:07.000Z", "2026-11-18T10:52:31.000Z", "2026-11-18T11:03:12.000Z",
               "2026-11-18T11:14:45.000Z", "2026-11-18T11:22:10.000Z", "2026-11-18T11:29:58.000Z"]
ORDER_OF = ["Mom", "Tom", "Kate", "Leo & Max", "Grandma Ruth", "Dad", "Jess"]


def plus30(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(minutes=30)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def place_order(amazon, when, address_id, card_id):
    """Checkout + placeOrder: the whole cart is ordered, full address/card objects stored, cart cleared."""
    subtotal = sum(PRODUCTS[c["productId"]][4] * c["quantity"] for c in amazon["cart"])
    eta = (datetime.fromisoformat(when.replace("Z", "+00:00")) + timedelta(days=5)).strftime("%Y-%m-%d")
    order = {"id": f"ord-{ms(when)}", "date": when, "status": "Processing",
             "items": copy.deepcopy(amazon["cart"]), "total": subtotal * (1 + TAX),
             "shippingAddress": copy.deepcopy(ADDR[address_id]), "paymentMethod": copy.deepcopy(CARD[card_id]),
             "trackingNumber": None, "estimatedDelivery": eta}
    amazon["orders"].insert(0, order)
    amazon["cart"] = []
    return order


def add_call(cal, idx, title, start):
    """EventModal create: {...formData, id, guests, start, end} on the first calendar (c1)."""
    cal["events"].append({
        "title": title, "start": start, "end": plus30(start), "allDay": False, "location": "", "description": "",
        "calendarId": "c1", "guests": [], "color": "bg-blue-500", "recurring": "none",
        "reminders": [{"type": "popup", "minutes": 10}], "id": f"7c1e0b52-4d1a-4c3e-9f0a-{idx:012d}",
    })


def run(seed, plan):
    """plan = {orders: [(recipient, [(asin, qty)], address_id, card_id)], calls: [(title, start)],
    keep_personal_in_cart: bool (Buy Now with Emily's items still in the cart), extra_rows: [...]}"""
    amazon, cal = copy.deepcopy(seed["amazon"]), copy.deepcopy(seed["google_calendar"])
    personal_in_cart = plan.get("keep_personal_in_cart", False)
    if not personal_in_cart:  # "Save for later" on each personal item
        amazon["savedForLater"] = copy.deepcopy(amazon["cart"])
        amazon["cart"] = []
    rows = [["recipient", "order_id", "asin", "quantity", "order_total"]] + [list(r) for r in plan.get("extra_rows", [])]
    for i, (recipient, items, address_id, card_id) in enumerate(plan["orders"]):
        amazon["cart"] += [{"productId": pid, "quantity": q} for pid, q in items]
        order = place_order(amazon, ORDER_TIMES[i], address_id, card_id)
        pid, q = items[0]
        rows.append([recipient, order["id"], pid, str(q), money(order["total"])])
    for i, (title, start) in enumerate(plan["calls"]):
        add_call(cal, i + 1, title, start)
    rows = [rows[0]] + sorted(rows[1:], key=lambda r: ORDER_OF.index(r[0]))
    return {"amazon": amazon, "google_calendar": cal}, rows


MOM_ROW = ["Mom", MOM_ORDER_ID, "B07NQRM6ML", "1", money(SEED_ORDERS[1]["total"])]


def golden_plan():
    return {
        "orders": [(r, [(t[0], t[1])], t[2], "pm2") for r, t in TARGETS.items()],
        "calls": [(f"Call {r}", t[4]) for r, t in TARGETS.items()],
        "extra_rows": [MOM_ROW],
    }


def naive_plan():
    """Pinned to first impressions: old Kate address + wrong Kindle, Buy Now with the personal cart, default
    Amex, one LEGO set, an in-stock Aura near-duplicate, the over-budget MEATER, Mom and Jess re-ordered,
    calls at 7pm London time on the birthday itself."""
    return {
        "keep_personal_in_cart": True,
        "orders": [("Kate", [("B09TMN58KL", 1)], "addr2", "pm1"),
                   ("Leo & Max", [("B0BBS6KGN1", 1)], "addr4", "pm1"),
                   ("Grandma Ruth", [("B0BNQK9T3Z", 1)], "addr3", "pm1"),
                   ("Dad", [("B0CGV2XGRL", 1)], "addr1", "pm1"),
                   ("Mom", [("B07NQRM6ML", 1)], "addr1", "pm1"),
                   ("Jess", [("B0BSL5P5BH", 1)], "addr5", "pm1")],
        "calls": [("Call Mom", "2026-11-24T19:00:00.000Z"), ("Call Kate", "2026-12-03T19:00:00.000Z"),
                  ("Call Leo & Max", "2026-12-09T19:00:00.000Z"), ("Call Grandma Ruth", "2026-12-20T19:00:00.000Z"),
                  ("Call Dad", "2026-12-27T19:00:00.000Z"), ("Call Jess", "2027-01-01T19:00:00.000Z")],
    }


def slip(kind):
    plan = golden_plan()
    if kind == "kate_address":
        plan["orders"][0] = ("Kate", [("B09TMF6742", 1)], "addr2", "pm2")
    elif kind == "timezone":
        plan["calls"] = [(f"Call {r}", f"{t[3]}T19:00:00.000Z") for r, t in TARGETS.items()]
    elif kind == "mom_duplicate":
        plan["orders"].append(("Mom", [("B07NQRM6ML", 1)], "addr1", "pm2"))
        plan["calls"].append(("Call Mom", "2026-11-25T00:00:00.000Z"))
        plan["extra_rows"] = []
    elif kind == "dad_budget":
        plan["orders"][3] = ("Dad", [("B0CGV2XGRL", 1)], "addr1", "pm2")
    return plan


# ---------------------------------------------------------------- io
def js_numbers(value):
    """JSON.stringify writes 149.0 as 149; mirror that so seeds equal the mock's normalized state."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: js_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [js_numbers(v) for v in value]
    return value


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(js_numbers(value), ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def expected():
    return {
        "clock": CLOCK, "timezone": "Europe/London", "tax_rate": TAX,
        "window": ["2026-11-18", "2026-12-31"],
        "gift_card": {"last4": "4417", "brand": "Visa", "id": "pm2"},
        "targets": {r: {"asin": t[0], "quantity": t[1], "street": ADDR[t[2]]["street"], "address_id": t[2],
                        "birthday": t[3], "call_start": t[4], "call_end": plus30(t[4]), "title_keys": t[5],
                        "order_total": money(PRODUCTS[t[0]][4] * t[1] * (1 + TAX))}
                    for r, t in TARGETS.items()},
        "already_ordered": {"Mom": {"order_id": MOM_ORDER_ID, "asin": "B07NQRM6ML", "quantity": 1,
                                    "order_total": money(SEED_ORDERS[1]["total"]), "existing_call_event": "evt_call_mom"}},
        "forbidden_asins": ["B07NQRM6ML", "B08KTZ8249", "B00U26V4VQ", "B07Q2M6NSM", "B0BSL5P5BH", "B0B7HS6Y4H",
                            "B0CGV2XGRL", "B07H9SQB4B", "B09TMN58KL", "B09SWV1FSS", "B09WRSHHJS", "B0BNQK9T3Z",
                            "B0BNQH1R5W", "B08FMQ4M1S", "B0CFVZJ2PQ"],
        "out_of_scope": {"Tom": {"birthday": "2026-11-10", "address_id": "addr6"},
                         "Jess": {"birthday": "2027-01-01", "address_id": "addr5"},
                         "Hannah": {"birthday": "2026-11-29", "on_list": False}},
        "old_kate_address": {"id": "addr2", "street": ADDR["addr2"]["street"]},
        "personal_cart": PERSONAL_CART,
        "csv_rows": [MOM_ROW[:4] + [MOM_ROW[4]]] + [[r, "<new order id>", t[0], str(t[1]), money(PRODUCTS[t[0]][4] * t[1] * (1 + TAX))]
                                                     for r, t in TARGETS.items()],
        "call_forbidden_keys": ["mom", "tom", "jess", "hannah"],
    }


def main(out: Path):
    seed = {"amazon": build_amazon(), "google_calendar": build_calendar()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, golden_rows = run(seed, golden_plan())
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "birthday_gifts.csv", golden_rows)
    write_csv(out / "input" / "gift_list.csv", GIFT_LIST)
    write_json(out / "expected.json", expected())

    variants = {"golden": (golden, golden_rows), "nop": (seed, None), "naive": run(seed, naive_plan())}
    for kind in ("kate_address", "timezone", "mom_duplicate", "dad_budget"):
        variants[f"slip_{kind}"] = run(seed, slip(kind))
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "birthday_gifts.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
