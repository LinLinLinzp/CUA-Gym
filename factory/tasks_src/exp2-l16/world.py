#!/usr/bin/env python3
"""World for the reunion-rooms-like-last-year task (Booking.com + Yahoo Mail + Google Calendar + PayPal + local CSV).

Writes into <out>/:
  seed/{booking_com,yahoo_mail,google_calendar,paypal}.json     initial state per site
  golden/{...}.json                                             state after a correct run
  golden_output/reunion_2026.csv                                correct CLI deliverable
  input/reunion_rsvp_2026.csv                                   agent-visible RSVP export
  expected.json                                                 truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/reunion_2026.csv}

Story (lever L16, implicit intent): Dana Whitfield organises the Whitfield family's winter reunion.
Her mother asks her to "do the rooms like last year" for Lakeview Pines Lodge, Lake Tahoe, 27-30 Dec
2026. "Like last year" is never spelled out; it must be read from the 2025 reunion's records:
  * Booking.com: the four completed 2025 bookings (one per household, all flexible / free-cancellation
    rates; the parents in the Accessible Queen ground-floor room with a cane special request) and a
    cancelled Queen Room booking that Mom rejected by email (stairs, no elevator).
  * PayPal: the Nov 2025 requests to Mark ($1,360) and Leah ($790) only. 1360-1185 = 790-615 = 175 =
    525/3, i.e. each household pays its own room and Dana, Mark and Leah each cover a third of the
    parents' room. The 2024 Big Bear per-head split and the Jan 2025 "Dana should be exempt" idea are
    nearby distractor histories.
  * Calendar: last year Dana set "free cancellation ends tomorrow" one day before the deadline
    (Dec 12 for a Dec 13 deadline). This season the lodge's flexible deadline is Dec 20 (7 days out,
    announced by the lodge and shown at checkout), so the reminder belongs on Dec 19.
  * Yahoo: last year's "rooms are booked" email (to Mom, Mark, Leah with confirmation numbers);
    Leah's old work address has since been retired in favour of her Gmail (PayPal too).
The RSVP export adds ordinary traps: Leah's later row moves her to 28-30 Dec, Jake needs no room,
Aunt Ruth declined.

Browser timezone is UTC (see TZ below); Dana lives in Sacramento but nothing depends on the offset.
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T18:30:00+00:00"
NOW = "2026-11-18T18:30:00.000Z"
# The browser runs in UTC: booking_com_mock renders YYYY-MM-DD dates via new Date(str), which shows the
# previous day in any timezone west of UTC (My Trips / Confirmation). All calendar times are UTC wall time.
TZ = "UTC"

DANA = {"name": "Dana Whitfield", "email": "dana.whitfield@yahoo.com"}
CHRIS = {"name": "Chris Alvarado", "email": "chris.alvarado@gmail.com"}
MARK = {"name": "Mark Whitfield", "email": "mark.whitfield@gmail.com"}
LEAH_OLD = {"name": "Leah Ortiz", "email": "leah@ortizdesign.co"}
LEAH_NEW = {"name": "Leah Whitfield-Ortiz", "email": "leah.whitfield.ortiz@gmail.com"}
CAROL = {"name": "Carol Whitfield", "email": "carol.whitfield@sbcglobal.net"}
JAKE = {"name": "Jake Whitfield", "email": "jake.whitfield92@gmail.com"}
RUTH = {"name": "Ruth Whitfield", "email": "ruthie.w@comcast.net"}
BOOKING = {"name": "Booking.com", "email": "noreply@booking.com"}
LODGE = {"name": "Lakeview Pines Lodge", "email": "stay@lakeviewpineslodge.com"}

PHONES = {"dana": "+1 (916) 555-0142", "mark": "+1 (510) 555-0187", "leah": "+1 (415) 555-0123",
          "carol": "+1 (530) 555-0161"}

LODGE_ID = "prop_1"
TAX_2026 = 28
DEADLINE_2026 = "2026-12-20"
REMINDER_DAY = "2026-12-19"


def picsum(seed, w=800, h=600):
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


# ====================================================================== booking.com
DESTINATIONS = [
    ("dest_1", "Lake Tahoe", "region", 412, True, "Alpine lake, ski resorts and cosy cabins on the CA/NV line"),
    ("dest_2", "Big Bear Lake", "city", 238, False, "Mountain lake town in the San Bernardino forest"),
    ("dest_3", "Napa Valley", "region", 301, True, "Vineyards, tasting rooms and slow weekends"),
    ("dest_4", "Seattle", "city", 1180, False, "Waterfront city with markets and coffee"),
    ("dest_5", "San Diego", "city", 1420, True, "Beaches, sunshine and the harbour"),
    ("dest_6", "Monterey", "city", 264, False, "Aquarium, Cannery Row and coastal drives"),
    ("dest_7", "Palm Springs", "city", 377, False, "Desert pools and mid-century style"),
    ("dest_8", "Yosemite", "region", 145, True, "Granite cliffs, waterfalls and national park lodges"),
    ("dest_9", "Portland", "city", 860, False, "Food carts, bridges and bookshops"),
    ("dest_10", "Los Angeles", "city", 3120, False, "Sun, beaches and Hollywood"),
]

# id, name, type, stars, dest, city, address, dist, lat, lng, score, word, count, price, tax, fc, short, desc, facilities
PROPERTIES = [
    ("prop_1", "Lakeview Pines Lodge", "hotel", 3, "dest_1", "South Lake Tahoe", "3411 Lake Tahoe Blvd, South Lake Tahoe, CA 96150",
     "1.2 km from center", 38.9399, -119.9772, 8.6, "Fabulous", 1184, 129, TAX_2026, False,
     "Family-run lodge with lake-view rooms and two-bedroom cabins",
     "Family-run since 1978, Lakeview Pines Lodge sits among the pines a short walk from the lake. The main lodge has "
     "rooms on two floors (no elevator; the ground floor is by the lobby and fireplace lounge) and the grounds have "
     "two-bedroom cabins with kitchenettes. Flexible rates can be cancelled free of charge until the date shown at checkout; "
     "non-refundable rates are charged in full.",
     ["free_wifi", "parking", "24h_front_desk", "garden", "terrace", "breakfast", "non_smoking", "kitchen"]),
    ("prop_2", "Lakeview Pines Resort & Spa", "resort", 4, "dest_1", "Stateline", "55 Highway 50, Stateline, NV 89449",
     "3.8 km from center", 38.9617, -119.9433, 8.9, "Fabulous", 2210, 239, 45, True,
     "Ski-in resort with spa, pool and casino shuttle",
     "A full-service resort at the foot of Heavenly with a heated outdoor pool, spa, three restaurants and a free shuttle to the casinos.",
     ["free_wifi", "pool", "spa", "fitness", "restaurant", "bar", "valet_parking", "room_service", "concierge"]),
    ("prop_3", "Tahoe Timberline Cabins", "apartment", 0, "dest_1", "South Lake Tahoe", "1250 Ski Run Blvd, South Lake Tahoe, CA 96150",
     "2.1 km from center", 38.9302, -119.9561, 8.3, "Very Good", 640, 189, 31, True,
     "Self-catering log cabins near Heavenly Village",
     "Independent log cabins with full kitchens, wood stoves and private hot tubs. Self check-in with a key box.",
     ["free_wifi", "kitchen", "washer", "parking", "terrace"]),
    ("prop_4", "Emerald Bay Inn", "guesthouse", 0, "dest_1", "South Lake Tahoe", "780 Emerald Bay Rd, South Lake Tahoe, CA 96150",
     "4.4 km from center", 38.9101, -120.0112, 9.1, "Superb", 312, 165, 24, True,
     "Eight-room B&B with homemade breakfast",
     "A quiet eight-room inn on the road to Emerald Bay. Breakfast is cooked to order every morning.",
     ["free_wifi", "breakfast", "garden", "parking", "non_smoking"]),
    ("prop_5", "Stateline Grand Hotel & Casino", "hotel", 4, "dest_1", "Stateline", "18 Highway 50, Stateline, NV 89449",
     "3.5 km from center", 38.9631, -119.9401, 7.6, "Good", 4105, 149, 39, False,
     "High-rise casino hotel with lake views",
     "Casino hotel with 500 rooms, a buffet, live shows and lake-view towers.",
     ["free_wifi", "pool", "fitness", "restaurant", "bar", "valet_parking", "24h_front_desk"]),
    ("prop_6", "Big Bear Timber Lodge", "hotel", 3, "dest_2", "Big Bear Lake", "40650 Village Dr, Big Bear Lake, CA 92315",
     "0.4 km from center", 34.2433, -116.9114, 8.1, "Very Good", 902, 139, 22, False,
     "Village lodge steps from the lake and shops",
     "A timber-frame lodge in Big Bear Village with suites for families and a stone fireplace lounge.",
     ["free_wifi", "parking", "24h_front_desk", "breakfast", "garden"]),
    ("prop_7", "Big Bear Lakefront Suites", "apartment", 0, "dest_2", "Big Bear Lake", "39000 North Shore Dr, Big Bear Lake, CA 92315",
     "2.9 km from center", 34.2590, -116.8962, 8.4, "Very Good", 418, 175, 25, True,
     "Lakefront apartments with docks",
     "One- and two-bedroom apartments right on the north shore, with kayaks to borrow in summer.",
     ["free_wifi", "kitchen", "washer", "parking", "balcony"]),
    ("prop_8", "Vintners Rest Inn", "guesthouse", 0, "dest_3", "St. Helena", "1020 Main St, St. Helena, CA 94574",
     "0.6 km from center", 38.5052, -122.4703, 9.3, "Superb", 287, 289, 41, True,
     "Adults-only inn among the vineyards",
     "A restored 1890s farmhouse with twelve rooms, a pool and wine-country breakfasts.",
     ["free_wifi", "pool", "breakfast", "garden", "parking"]),
    ("prop_9", "Pike Street Hotel", "hotel", 4, "dest_4", "Seattle", "1415 5th Ave, Seattle, WA 98101",
     "0.3 km from center", 47.6105, -122.3361, 8.5, "Fabulous", 3311, 219, 38, True,
     "Downtown hotel by Pike Place Market",
     "Modern hotel two blocks from Pike Place Market with a rooftop bar.",
     ["free_wifi", "fitness", "restaurant", "bar", "24h_front_desk", "air_conditioning"]),
    ("prop_10", "Coronado Shores Hotel", "hotel", 4, "dest_5", "Coronado", "1500 Orange Ave, Coronado, CA 92118",
     "1.0 km from center", 32.6859, -117.1831, 8.8, "Fabulous", 2650, 259, 36, True,
     "Beachfront hotel on Coronado Island",
     "Steps from Coronado Beach with two pools, kids' club and bikes to borrow.",
     ["free_wifi", "pool", "private_beach", "kids_club", "restaurant", "bar", "bicycle_rental"]),
]

# room id -> (property, name, type, maxGuests, bed, size, price, fc, view, breakfast, avail)
ROOMS = {
    # Lakeview Pines Lodge, flexible rows carry the Dec 20 deadline
    "room_1_1": ("prop_1", "Queen Room – Second Floor", "double", 2, "1 queen bed", "22 m²", 152, True, "Forest view", False, 4),
    "room_1_2": ("prop_1", "Accessible Queen Room – Ground Floor", "double", 2, "1 queen bed", "26 m²", 148, False, "Garden view", False, 2),
    "room_1_3": ("prop_1", "Accessible Queen Room – Ground Floor", "double", 2, "1 queen bed", "26 m²", 165, True, "Garden view", False, 2),
    "room_1_4": ("prop_1", "King Room with Lake View", "double", 2, "1 king bed", "28 m²", 172, False, "Lake view", False, 3),
    "room_1_5": ("prop_1", "King Room with Lake View", "double", 2, "1 king bed", "28 m²", 189, True, "Lake view", False, 3),
    "room_1_6": ("prop_1", "Double Room", "double", 2, "1 double bed", "18 m²", 119, False, None, False, 5),
    "room_1_7": ("prop_1", "Double Room", "double", 2, "1 double bed", "18 m²", 129, True, None, False, 5),
    "room_1_8": ("prop_1", "Family Room", "family", 4, "1 queen bed and 2 bunk beds", "34 m²", 219, False, "Forest view", True, 2),
    "room_1_9": ("prop_1", "Family Room", "family", 4, "1 queen bed and 2 bunk beds", "34 m²", 245, True, "Forest view", True, 2),
    "room_1_10": ("prop_1", "Two-Bedroom Forest Cabin", "suite", 6, "1 queen bed and 2 twin beds", "55 m²", 335, True, "Forest view", False, 1),
    "room_1_11": ("prop_1", "Two-Bedroom Lakeside Cabin", "suite", 6, "1 king bed and 2 twin beds", "62 m²", 352, False, "Lake view", False, 2),
    "room_1_12": ("prop_1", "Two-Bedroom Lakeside Cabin", "suite", 6, "1 king bed and 2 twin beds", "62 m²", 395, True, "Lake view", False, 2),
    "room_2_1": ("prop_2", "Deluxe King Room", "double", 2, "1 king bed", "36 m²", 239, False, "Mountain view", False, 6),
    "room_2_2": ("prop_2", "Deluxe King Room", "double", 2, "1 king bed", "36 m²", 265, True, "Mountain view", False, 6),
    "room_2_3": ("prop_2", "Family Suite", "family", 5, "1 king bed and 1 sofa bed", "58 m²", 389, True, "Lake view", True, 2),
    "room_2_4": ("prop_2", "Lakeside Two-Bedroom Villa", "suite", 6, "2 king beds", "90 m²", 545, True, "Lake view", True, 1),
    "room_3_1": ("prop_3", "One-Bedroom Cabin", "studio", 3, "1 queen bed and 1 sofa bed", "45 m²", 189, True, "Forest view", False, 3),
    "room_3_2": ("prop_3", "Two-Bedroom Cabin with Hot Tub", "suite", 6, "1 queen bed and 2 twin beds", "70 m²", 299, True, "Forest view", False, 2),
    "room_4_1": ("prop_4", "Classic Queen", "double", 2, "1 queen bed", "20 m²", 165, True, "Garden view", True, 2),
    "room_4_2": ("prop_4", "Bay View King", "double", 2, "1 king bed", "24 m²", 199, True, "Lake view", True, 1),
    "room_5_1": ("prop_5", "Tower King", "double", 2, "1 king bed", "32 m²", 149, False, "Lake view", False, 9),
    "room_5_2": ("prop_5", "Tower Two Queens", "double", 4, "2 queen beds", "38 m²", 169, False, "Lake view", False, 9),
    "room_6_1": ("prop_6", "Queen Room", "double", 2, "1 queen bed", "21 m²", 139, False, None, False, 4),
    "room_6_2": ("prop_6", "King Room", "double", 2, "1 king bed", "25 m²", 149, False, None, False, 4),
    "room_6_3": ("prop_6", "Two-Queen Room", "double", 4, "2 queen beds", "32 m²", 179, False, None, False, 3),
    "room_6_4": ("prop_6", "Family Suite", "family", 4, "1 queen bed and 1 sofa bed", "40 m²", 193, False, None, True, 2),
    "room_7_1": ("prop_7", "One-Bedroom Lakefront", "studio", 4, "1 queen bed and 1 sofa bed", "48 m²", 175, True, "Lake view", False, 3),
    "room_7_2": ("prop_7", "Two-Bedroom Lakefront", "suite", 6, "2 queen beds", "75 m²", 255, True, "Lake view", False, 2),
    "room_8_1": ("prop_8", "Vineyard King", "double", 2, "1 king bed", "30 m²", 289, True, "Vineyard view", True, 2),
    "room_8_2": ("prop_8", "Garden Cottage", "suite", 2, "1 king bed", "40 m²", 349, True, "Garden view", True, 1),
    "room_9_1": ("prop_9", "City King", "double", 2, "1 king bed", "26 m²", 219, True, "City view", False, 8),
    "room_9_2": ("prop_9", "Sound View Queen", "double", 2, "1 queen bed", "24 m²", 249, True, "Sea view", False, 4),
    "room_10_1": ("prop_10", "Ocean View Two Queens", "family", 4, "2 queen beds", "38 m²", 259, True, "Ocean view", False, 5),
    "room_10_2": ("prop_10", "Ocean Front King", "double", 2, "1 king bed", "34 m²", 299, True, "Ocean view", False, 3),
}


def build_properties():
    props, rooms = [], []
    room_ids = {}
    for rid, r in ROOMS.items():
        room_ids.setdefault(r[0], []).append(rid)
    for (pid, name, ptype, stars, dest, city, addr, dist, lat, lng, score, word, cnt, price, tax, fc, short, desc, fac) in PROPERTIES:
        country = "United States"
        photos = [{"id": f"{pid}_ph{i}", "url": picsum(f"{pid}-{i}"), "caption": cap, "category": cat}
                  for i, (cap, cat) in enumerate([("Exterior", "exterior"), ("Room", "room"), ("Lobby", "common"),
                                                  ("View", "view"), ("Breakfast", "dining")])]
        props.append({
            "id": pid, "name": name, "type": ptype, "stars": stars, "destinationId": dest, "city": city, "country": country,
            "address": addr, "distanceFromCenter": dist, "coordinates": {"lat": lat, "lng": lng}, "description": desc,
            "shortDescription": short, "reviewScore": score, "reviewScoreWord": word, "reviewCount": cnt,
            "pricePerNight": price, "originalPrice": None, "currency": "USD", "taxesAndFees": tax, "genius": pid in ("prop_2", "prop_10"),
            "geniusDiscountPercent": 10 if pid in ("prop_2", "prop_10") else 0, "freeCancellation": fc,
            "freeCancellationUntil": None, "prepayment": "no_prepayment", "breakfastIncluded": "breakfast" in fac and pid != LODGE_ID,
            "thumbnailUrl": picsum(f"{pid}-0"), "photos": photos, "facilities": fac,
            "popularFacilities": [f.replace("_", " ").title() for f in fac[:4]], "rooms": room_ids[pid],
            "checkInTime": "15:00", "checkOutTime": "11:00", "petsAllowed": pid in ("prop_3", "prop_7"), "smokingAllowed": False,
            "sustainability": pid in ("prop_1", "prop_4"), "sustainabilityLevel": 2 if pid in ("prop_1", "prop_4") else 0,
            "limitedTimeDeal": pid == "prop_5", "newToBooking": False,
        })
    for rid, (pid, name, rtype, mg, bed, size, price, fc, view, bf, avail) in ROOMS.items():
        deadline = None
        if fc:
            deadline = DEADLINE_2026 if pid == LODGE_ID else "2026-12-22"
        amen = ["Free WiFi", "Heating", "Private bathroom", "Flat-screen TV"]
        if "Cabin" in name:
            amen += ["Kitchenette", "Fireplace"]
        if "Accessible" in name:
            amen += ["Step-free access", "Grab rails", "Roll-in shower", "Near lobby"]
        if "Second Floor" in name:
            amen += ["Upper floor – stairs only"]
        rooms.append({
            "id": rid, "propertyId": pid, "name": name, "type": rtype, "maxGuests": mg, "bedType": bed, "size": size,
            "pricePerNight": price, "originalPrice": None, "amenities": amen, "view": view, "breakfastIncluded": bf,
            "breakfastPrice": None if bf else 18, "freeCancellation": fc, "cancellationDeadline": deadline,
            "prepayment": "no_prepayment" if fc else "prepayment_required", "availableCount": avail,
            "smokingAllowed": False, "imageUrl": picsum(rid),
        })
    return props, rooms


PROP = {p[0]: p for p in PROPERTIES}


def past_booking(bid, conf, pin, pid, rid, cin, cout, price, tax, status, guest, email, phone, created,
                 fc, deadline, special="", arrival="15:00 – 16:00"):
    nights = nights_between(cin, cout)
    p = PROP[pid]
    first, last = guest.split(" ", 1)
    return {"id": bid, "confirmationNumber": conf, "pinCode": pin, "userId": "user_1", "propertyId": pid,
            "propertyName": p[1], "propertyImage": picsum(f"{pid}-0"), "propertyCity": p[5], "propertyAddress": p[6],
            "roomId": rid, "roomName": ROOMS[rid][1], "checkIn": cin, "checkOut": cout, "nights": nights,
            "guests": {"adults": 2, "children": 0}, "rooms": 1, "pricePerNight": price, "totalPrice": price * nights,
            "taxesAndFees": tax * nights, "grandTotal": (price + tax) * nights, "status": status,
            "guestFirstName": first, "guestLastName": last, "guestEmail": email, "guestPhone": phone,
            "specialRequests": special, "arrivalTime": arrival, "freeCancellation": fc, "cancellationDeadline": deadline,
            "createdAt": created}


CANE_REQ = "Ground floor room near the lobby please, my husband walks with a cane."

# 2025 reunion (the precedent)
B25 = [
    ("booking_101", "3317402958", "4471", "room_1_9", 229, "completed", "Dana Whitfield", DANA["email"], PHONES["dana"], ""),
    ("booking_102", "3317403361", "9025", "room_1_12", 369, "completed", "Mark Whitfield", MARK["email"], PHONES["mark"], ""),
    ("booking_103", "3317403774", "1840", "room_1_5", 179, "completed", "Leah Ortiz", LEAH_OLD["email"], PHONES["leah"], ""),
    ("booking_104", "3317404120", "6312", "room_1_3", 149, "completed", "Carol Whitfield", CAROL["email"], PHONES["carol"], CANE_REQ),
]
B25_CANCELLED = ("booking_100", "3316998214", "5560", "room_1_1", 139, "cancelled", "Carol Whitfield", CAROL["email"], PHONES["carol"], "")
# 2024 Big Bear reunion (distractor history, non-refundable, per-head split)
B24 = [
    ("booking_091", "2958810437", "7702", "room_6_4", 193, "Dana Whitfield", DANA["email"], PHONES["dana"]),
    ("booking_092", "2958810872", "3108", "room_6_3", 179, "Mark Whitfield", MARK["email"], PHONES["mark"]),
    ("booking_093", "2958811205", "6649", "room_6_2", 149, "Leah Ortiz", LEAH_OLD["email"], PHONES["leah"]),
    ("booking_094", "2958811590", "2287", "room_6_1", 139, "Carol Whitfield", CAROL["email"], PHONES["carol"]),
]


def build_bookings():
    b = []
    for bid, conf, pin, rid, price, guest, email, phone in B24:
        b.append(past_booking(bid, conf, pin, "prop_6", rid, "2024-12-27", "2024-12-30", price, 22, "completed", guest, email,
                              phone, "2024-11-30T20:14:00.000Z", False, None))
    bid, conf, pin, rid, price, st, guest, email, phone, sp = B25_CANCELLED
    b.append(past_booking(bid, conf, pin, LODGE_ID, rid, "2025-12-27", "2025-12-30", price, 26, st, guest, email, phone,
                          "2025-11-03T19:02:00.000Z", True, "2025-12-13", sp))
    for i, (bid, conf, pin, rid, price, st, guest, email, phone, sp) in enumerate(B25):
        b.append(past_booking(bid, conf, pin, LODGE_ID, rid, "2025-12-27", "2025-12-30", price, 26, st, guest, email, phone,
                              f"2025-11-05T{18 + i // 2:02d}:{(i % 2) * 20 + 11:02d}:00.000Z", True, "2025-12-13", sp))
    # other trips (noise)
    b.append(past_booking("booking_111", "3401187720", "3391", "prop_2", "room_2_1", "2026-02-13", "2026-02-15", 229, 45, "completed",
                          "Chris Alvarado", CHRIS["email"], "+1 (916) 555-0199", "2026-01-12T04:40:00.000Z", False, None,
                          "Late check-in, driving up after work"))
    b.append(past_booking("booking_112", "3402519046", "8810", "prop_8", "room_8_1", "2026-04-10", "2026-04-12", 279, 41, "completed",
                          "Dana Whitfield", DANA["email"], PHONES["dana"], "2026-03-02T17:25:00.000Z", True, "2026-04-03",
                          "Anniversary trip, a quiet room if possible"))
    b.append(past_booking("booking_113", "3404407731", "1206", "prop_9", "room_9_1", "2026-06-08", "2026-06-11", 209, 38, "completed",
                          "Dana Whitfield", DANA["email"], PHONES["dana"], "2026-05-14T22:03:00.000Z", True, "2026-06-01"))
    b.append(past_booking("booking_114", "3405112954", "4478", "prop_10", "room_10_1", "2026-07-19", "2026-07-24", 289, 36, "completed",
                          "Dana Whitfield", DANA["email"], PHONES["dana"], "2026-03-28T16:50:00.000Z", True, "2026-07-12"))
    b.append(past_booking("booking_115", "3406630285", "7034", LODGE_ID, "room_1_6", "2026-09-18", "2026-09-20", 119, 28, "completed",
                          "Dana Whitfield", DANA["email"], PHONES["dana"], "2026-09-01T03:12:00.000Z", False, None,
                          "Sisters' weekend!"))
    b.append(past_booking("booking_116", "3407781462", "5523", "prop_10", "room_10_2", "2027-01-15", "2027-01-18", 249, 36, "confirmed",
                          "Dana Whitfield", DANA["email"], PHONES["dana"], "2026-10-21T19:40:00.000Z", True, "2027-01-08"))
    return b


REVIEWS = [
    ("prop_1", "Margaret", "2026-03-02", 9.0, "Perfect for our family", "Cabins are roomy, kids loved the bunk beds in the family room.",
     "Queen rooms are upstairs and there's no elevator.", "Family Room", 3, "family"),
    ("prop_1", "Tom", "2026-01-19", 8.0, "Cosy and quiet", "Great fireplace lounge, friendly staff.", "Thin walls.", "King Room with Lake View", 2, "couple"),
    ("prop_1", "Elaine", "2025-12-31", 9.5, "Ground floor room was ideal", "The accessible room by the lobby was perfect for my mother.",
     "", "Accessible Queen Room – Ground Floor", 3, "family"),
    ("prop_1", "Raj", "2026-08-07", 8.5, "Nice summer stay", "Lakeside cabin had a great deck.", "Parking is tight.", "Two-Bedroom Lakeside Cabin", 4, "family"),
    ("prop_2", "Kevin", "2026-02-16", 9.0, "Ski heaven", "Right by the gondola, great spa.", "Pricey restaurants.", "Deluxe King Room", 2, "couple"),
    ("prop_2", "Laura", "2025-12-29", 8.5, "Fancy", "Pool was amazing.", "Resort fee.", "Family Suite", 4, "family"),
    ("prop_3", "Ben", "2026-01-04", 8.0, "Hot tub!", "Private hot tub under the stars.", "Self check-in was confusing.", "Two-Bedroom Cabin with Hot Tub", 3, "family"),
    ("prop_4", "Ana", "2026-05-22", 9.5, "Lovely hosts", "Breakfast was the highlight.", "", "Bay View King", 2, "couple"),
    ("prop_5", "Greg", "2026-04-11", 7.0, "Fine for a night", "Lake views from the tower.", "Smells of smoke in the lobby.", "Tower King", 1, "business"),
    ("prop_6", "Sue", "2025-01-03", 8.0, "Walkable village", "Close to everything.", "No refund when we had to leave early.", "Family Suite", 3, "family"),
    ("prop_7", "Mia", "2026-07-30", 8.5, "Right on the water", "Kayaks and the dock.", "", "Two-Bedroom Lakefront", 4, "family"),
    ("prop_8", "Daniel", "2026-04-14", 9.5, "Romantic", "Gorgeous grounds and wine.", "", "Vineyard King", 2, "couple"),
    ("prop_9", "Priyanka", "2026-06-12", 8.5, "Great location", "Two blocks from the market.", "Street noise.", "City King", 3, "business"),
    ("prop_10", "Hector", "2026-07-26", 9.0, "Beach days", "Kids' club was a lifesaver.", "Busy pool.", "Ocean View Two Queens", 5, "family"),
]


def build_booking():
    props, rooms = build_properties()
    reviews = []
    counts = {}
    for (pid, author, date, score, title, pos, neg, room, nights, tt) in REVIEWS:
        counts[pid] = counts.get(pid, 0) + 1
        reviews.append({"id": f"review_{pid.split('_')[1]}_{counts[pid]}", "propertyId": pid, "authorName": author,
                        "authorCountry": "United States", "authorCountryCode": "US", "date": date, "score": score,
                        "title": title, "positive": pos, "negative": neg, "roomType": room, "nightsStayed": nights,
                        "travellerType": tt})
    cats = {p["id"]: {"staff": round(p["reviewScore"] + 0.2, 1), "facilities": round(p["reviewScore"] - 0.3, 1),
                      "cleanliness": round(p["reviewScore"] + 0.1, 1), "comfort": p["reviewScore"],
                      "valueForMoney": round(p["reviewScore"] - 0.4, 1), "location": round(p["reviewScore"] + 0.3, 1),
                      "freeWifi": round(p["reviewScore"] - 0.1, 1)} for p in props}
    return {
        "user": {"id": "user_1", "firstName": "Dana", "lastName": "Whitfield", "email": DANA["email"], "phone": PHONES["dana"],
                 "country": "United States", "nationality": "American", "avatarUrl": avatar("Dana Whitfield"), "geniusLevel": 2,
                 "geniusBookings": 14, "geniusBookingsRequired": 15, "currency": "USD", "language": "English (US)",
                 "savedProperties": ["prop_1", "prop_4", "prop_8"]},
        "destinations": [{"id": d, "name": n, "country": "United States", "countryCode": "US", "type": t, "propertyCount": c,
                          "trending": tr, "description": desc} for d, n, t, c, tr, desc in DESTINATIONS],
        "properties": props, "rooms": rooms, "reviews": reviews, "reviewCategories": cats,
        "bookings": build_bookings(),
        "searchParams": {"destination": "", "destinationId": None, "checkIn": None, "checkOut": None, "adults": 2, "children": 0,
                         "childrenAges": [], "rooms": 1, "travelingForWork": False},
        "searchFilters": {"priceMin": None, "priceMax": None, "starRating": [], "reviewScore": None, "propertyType": [],
                          "facilities": [], "freeCancellation": False, "breakfastIncluded": False, "geniusDeals": False,
                          "sortBy": "our_top_picks"},
        "searchResults": [], "selectedPropertyId": None,
        "recentSearches": [
            {"destination": "San Diego", "destinationId": "dest_5", "dates": "Jan 15 – Jan 18", "guests": "2 adults · 0 children · 1 room"},
            {"destination": "Lake Tahoe", "destinationId": "dest_1", "dates": "Sep 18 – Sep 20", "guests": "2 adults · 0 children · 1 room"},
        ],
        "recentlyViewed": ["prop_10", "prop_1"], "notifications": [], "viewedProperties": ["prop_10", "prop_1", "prop_8"],
    }


# ====================================================================== 2026 targets
# household -> (guest first, guest last, email, phone, room id, check-in, check-out, special request)
TARGETS = {
    "dana": ("Dana", "Whitfield", DANA["email"], PHONES["dana"], "room_1_9", "2026-12-27", "2026-12-30", ""),
    "mark": ("Mark", "Whitfield", MARK["email"], PHONES["mark"], "room_1_12", "2026-12-27", "2026-12-30", ""),
    "leah": ("Leah", "Whitfield-Ortiz", LEAH_NEW["email"], PHONES["leah"], "room_1_5", "2026-12-28", "2026-12-30", ""),
    "parents": ("Carol", "Whitfield", CAROL["email"], PHONES["carol"], "room_1_3", "2026-12-27", "2026-12-30", CANE_REQ),
}
HOUSEHOLD_FIRST = {"dana": ["Dana"], "mark": ["Mark"], "leah": ["Leah"], "parents": ["Carol", "Jim"]}
CONF = {"dana": "4826193057", "mark": "4826197731", "leah": "4826201148", "parents": "4826204590"}
PIN = {"dana": "3814", "mark": "9067", "leah": "2251", "parents": "7740"}


def nights_between(cin, cout):
    from datetime import date
    return (date.fromisoformat(cout) - date.fromisoformat(cin)).days


def grand_total(rid, cin, cout):
    return (ROOMS[rid][6] + TAX_2026) * nights_between(cin, cout)


def ui_booking(state, idx, first, last, email, phone, rid, cin, cout, special, conf, pin):
    """Mirror Checkout.jsx handleSubmit (deterministic id/conf/pin)."""
    prop = next(p for p in state["properties"] if p["id"] == ROOMS[rid][0])
    room = next(r for r in state["rooms"] if r["id"] == rid)
    n = nights_between(cin, cout)
    created = f"2026-11-18T18:{40 + idx * 3:02d}:12.000Z"
    return {"id": f"booking_179544{idx}000000", "confirmationNumber": conf, "pinCode": pin, "userId": "user_1",
            "propertyId": prop["id"], "propertyName": prop["name"], "propertyImage": prop["thumbnailUrl"],
            "propertyCity": prop["city"], "propertyAddress": prop["address"], "roomId": rid, "roomName": room["name"],
            "checkIn": cin, "checkOut": cout, "nights": n, "guests": {"adults": 2, "children": 0}, "rooms": 1,
            "pricePerNight": room["pricePerNight"], "totalPrice": room["pricePerNight"] * n,
            "taxesAndFees": prop["taxesAndFees"] * n, "grandTotal": room["pricePerNight"] * n + prop["taxesAndFees"] * n,
            "status": "confirmed", "guestFirstName": first, "guestLastName": last, "guestEmail": email, "guestPhone": phone,
            "specialRequests": special, "arrivalTime": "15:00 – 16:00",
            "freeCancellation": bool(room["freeCancellation"] or prop["freeCancellation"]),
            "cancellationDeadline": room["cancellationDeadline"], "createdAt": created}


# ====================================================================== yahoo mail
SYSTEM_FOLDERS = [("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"), ("spam", "Spam"), ("trash", "Trash")]
USER_FOLDERS = [("fld_family", "Family"), ("fld_travel", "Travel"), ("fld_school", "Ivy – school"), ("fld_receipts", "Receipts")]


def msg(mid, cnv, sender, subject, body, date, to=None, cc=None, folder="inbox", category="primary", read=True, starred=False):
    received = folder != "sent"
    frm = sender if received else DANA
    return {"id": mid, "conversationId": cnv, "folderId": folder, "previousFolderId": None, "category": category,
            "from": dict(frm), "to": [dict(x) for x in (to or [DANA])], "cc": [dict(x) for x in (cc or [])], "bcc": [],
            "replyTo": None, "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None,
            "date": date, "isRead": read, "isStarred": starred, "isDraft": False, "status": "received" if received else "sent",
            "attachments": [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"), "summary": None,
            "orderInfo": None, "travelInfo": None, "inReplyToId": None, "forwardedFromId": None, "replyType": None,
            "repliedAt": None, "forwardedAt": None, "sentAt": None if received else date, "movedAt": None,
            "appliedFilterId": None, "createdAt": date, "updatedAt": None}


def P(*paras):
    return "\n\n".join(paras)


def conf_mail(mid, b, date, folder="fld_travel"):
    """Booking.com confirmation e-mail for a seed booking dict."""
    terms = (f"Free cancellation until {fmt_long(b['cancellationDeadline'])}. After that the full amount is charged."
             if b["freeCancellation"] and b["cancellationDeadline"] else
             "This booking is non-refundable. If you cancel, modify or don't show up, you'll pay the full amount.")
    body = P(f"Thanks, Dana! Your booking at {b['propertyName']} is confirmed.",
             f"Confirmation number: {b['confirmationNumber']}\nPIN: {b['pinCode']}",
             f"Room: {b['roomName']}\nGuest name: {b['guestFirstName']} {b['guestLastName']}\n"
             f"Check-in: {fmt_long(b['checkIn'])} (from 15:00)\nCheck-out: {fmt_long(b['checkOut'])} (until 11:00)\n"
             f"{b['nights']} nights, 2 adults",
             f"Price: US${b['totalPrice']} + taxes and fees US${b['taxesAndFees']} = US${b['grandTotal']}",
             f"Cancellation policy: {terms}",
             (f"Special requests: {b['specialRequests']}" if b["specialRequests"] else "Special requests: none"),
             "Manage your booking any time in My Trips.")
    return msg(mid, "cnv_" + mid, BOOKING, f"Booking confirmed: {b['propertyName']}, {fmt_short(b['checkIn'])} – {fmt_short(b['checkOut'])}",
               body, date, folder=folder)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def fmt_long(d):
    return f"{int(d[8:10])} {MONTHS[int(d[5:7]) - 1]} {d[:4]}"


def fmt_short(d):
    return f"{MONTHS[int(d[5:7]) - 1][:3]} {int(d[8:10])}, {d[:4]}"


def build_mail(bookings):
    bk = {b["id"]: b for b in bookings}
    m = []
    # ---------- 2024 Big Bear: non-refundable confirmations and the per-head split
    for i, (bid, *_r) in enumerate(B24):
        m.append(conf_mail(f"msg_b24_{i}", bk[bid], f"2024-11-30T20:{15 + i}:00.000Z"))
    m.append(msg("msg_bb_split", "cnv_bb_split", DANA, "Big Bear costs + PayPal requests", P(
        "Hi all,",
        "Big Bear came to $2,244 for the four rooms (all taxes in). There were 11 of us, so I've done it per head: $204 each.",
        "Mark – 4 of you = $816\nLeah – 2 of you = $408\nMom & Dad – $408\nUs – 3 of us = $612",
        "PayPal requests are out now. Thanks for an amazing week!", "Dana"),
        "2025-01-06T03:20:00.000Z", to=[MARK, LEAH_OLD, CAROL], folder="sent"))
    thread = [
        ("msg_bb_r1", LEAH_OLD, "Paid! One thing for next time though — when Sam got sick and we had to leave a night early, the lodge wouldn't refund "
         "anything because the rooms were non-refundable. Can we please only book rooms with free cancellation from now on? "
         "It's worth the extra few dollars.", "2025-01-07T17:02:00.000Z", [DANA], [MARK, CAROL]),
        ("msg_bb_r2", MARK, "+1 on cancellable rooms. And honestly per-head felt a bit off — Noah slept on a rollaway. How about next year each "
         "household covers its own room, and the three of us kids split Mom & Dad's room three ways?", "2025-01-08T02:44:00.000Z",
         [DANA], [LEAH_OLD, CAROL]),
        ("msg_bb_r3", LEAH_OLD, "Works for me. Although Dana does ALL the organising — maybe Mark and I split Mom & Dad's between the two of us "
         "and Dana gets a pass?", "2025-01-08T05:10:00.000Z", [DANA], [MARK, CAROL]),
        ("msg_bb_r4", CAROL, "You three are sweet. Your father says thank you for Big Bear. Love, Mom", "2025-01-08T19:30:00.000Z",
         [DANA], [MARK, LEAH_OLD]),
    ]
    for mid, s, body, date, to, cc in thread:
        m.append(msg(mid, "cnv_bb_split", s, "Re: Big Bear costs + PayPal requests", body, date, to=to, cc=cc, folder="fld_family"))
    m.append(msg("msg_bb_r5", "cnv_bb_split", DANA, "Re: Big Bear costs + PayPal requests",
                 "Ha, no pass needed. Let's settle it properly when we book next year.", "2025-01-09T04:01:00.000Z",
                 to=[LEAH_OLD], cc=[MARK, CAROL], folder="sent"))
    # ---------- 2025 Tahoe: plan, the cancelled Queen room, confirmations, the "booked" email
    m.append(msg("msg_25_plan", "cnv_25_plan", CAROL, "Christmas 2025 — Tahoe?", P(
        "Hi kids,", "Dad and I would love to do Lakeview Pines Lodge at Tahoe this year, Dec 27 to 30. We stayed there years ago and he still "
        "talks about the lake.", "Dana, would you do the rooms again? Love, Mom"),
        "2025-10-12T16:40:00.000Z", to=[DANA], cc=[MARK, LEAH_OLD], folder="fld_family"))
    m.append(conf_mail("msg_25_c0", bk["booking_100"], "2025-11-03T19:03:00.000Z"))
    m.append(msg("msg_25_mom1", "cnv_25_mom", CAROL, "Re: your room at Tahoe", P(
        "Dana honey, thank you for booking us. I looked at the lodge pictures and the Queen rooms are up on the second floor — there's no "
        "elevator, and your father can't do those stairs with his knee and the cane.",
        "Can you get us the ground floor one by the lobby instead? Even if it's a bit more. Love, Mom"),
        "2025-11-04T22:15:00.000Z", folder="fld_family"))
    m.append(msg("msg_25_mom2", "cnv_25_mom", DANA, "Re: your room at Tahoe",
                 "Of course Mom — cancelling the upstairs one now and booking the accessible ground-floor room. I'll ask them to keep you near the lobby.",
                 "2025-11-05T17:30:00.000Z", to=[CAROL], folder="sent"))
    cancel_body = P("Your booking at Lakeview Pines Lodge has been cancelled. You won't be charged.",
                    "Confirmation number: 3316998214\nRoom: Queen Room – Second Floor\nCheck-in: 27 December 2025\nCheck-out: 30 December 2025",
                    "Cancellation fee: US$0")
    m.append(msg("msg_25_cx", "cnv_25_cx", BOOKING, "Booking cancelled: Lakeview Pines Lodge, Dec 27, 2025", cancel_body,
                 "2025-11-05T17:41:00.000Z", folder="fld_travel"))
    for i, (bid, *_r) in enumerate(B25):
        m.append(conf_mail(f"msg_25_c{i + 1}", bk[bid], bk[bid]["createdAt"].replace(":00.000Z", ":40.000Z")))
    m.append(msg("msg_25_booked", "cnv_25_booked", DANA, "Tahoe rooms are booked!", P(
        "Hi everyone,",
        "All four rooms at Lakeview Pines Lodge are booked for Dec 27–30:",
        "Us – Family Room (conf. 3317402958)\nMark & co – Two-Bedroom Lakeside Cabin (conf. 3317403361)\n"
        "Leah & Sam – King Room with Lake View (conf. 3317403774)\nMom & Dad – Accessible Queen Room, ground floor by the lobby (conf. 3317404120)",
        "They're all on the flexible rate, so if plans change we can cancel for free until Dec 13.",
        "I've done the split the way we talked about in January — PayPal requests for your share are on their way.", "Love, Dana"),
        "2025-11-06T04:05:00.000Z", to=[CAROL, MARK, LEAH_OLD], folder="sent"))
    m.append(msg("msg_25_b1", "cnv_25_booked", MARK, "Re: Tahoe rooms are booked!", "Got the request and paid. Thanks sis, the boys are already asking about the cabin.",
                 "2025-11-06T15:22:00.000Z", to=[DANA], cc=[CAROL, LEAH_OLD], folder="fld_family"))
    m.append(msg("msg_25_b2", "cnv_25_booked", LEAH_OLD, "Re: Tahoe rooms are booked!", "Paid! Thank you for sorting it all out again 💛",
                 "2025-11-07T01:48:00.000Z", to=[DANA], cc=[CAROL, MARK], folder="fld_family"))
    m.append(msg("msg_25_b3", "cnv_25_booked", CAROL, "Re: Tahoe rooms are booked!", "Thank you sweetheart. Dad is very pleased about the ground floor.",
                 "2025-11-07T18:05:00.000Z", to=[DANA], cc=[MARK, LEAH_OLD], folder="fld_family"))
    # ---------- 2026: ski weekend, Leah's new address, sisters' weekend, lodge policy, Mom's request
    m.append(conf_mail("msg_26_ski", bk["booking_111"], "2026-01-12T04:41:00.000Z"))
    m.append(msg("msg_26_leah", "cnv_26_leah", LEAH_OLD, "New email address!", P(
        "Hi all, Ortiz Design is officially closing at the end of August (sad but also relieved!), so this address will stop working.",
        "From now on please use leah.whitfield.ortiz@gmail.com for everything — I've moved my PayPal over to it too, so send any requests there.",
        "Love, Leah"), "2026-08-19T21:12:00.000Z", to=[DANA, MARK, CAROL], folder="fld_family"))
    m.append(conf_mail("msg_26_sis", bk["booking_115"], "2026-09-01T03:13:00.000Z"))
    m.append(msg("msg_26_sis2", "cnv_26_sis", DANA, "Sisters' weekend booked!", P(
        "Leah! Double Room at Lakeview Pines, Sept 18–20. It was the cheap non-refundable rate so no backing out ;)",
        "Total $294 — I sent you a PayPal request for your half ($147).", "D"),
        "2026-09-01T03:20:00.000Z", to=[LEAH_NEW], folder="sent"))
    m.append(msg("msg_26_sis3", "cnv_26_sis", LEAH_NEW, "Re: Sisters' weekend booked!", "YAY. Paid. Bringing the good wine.",
                 "2026-09-01T15:02:00.000Z", folder="fld_family"))
    m.append(msg("msg_26_lodge", "cnv_26_lodge", LODGE, "Winter at Lakeview Pines — our 2026–27 season", P(
        "Snow is on its way! A few updates for the winter season:",
        "• Flexible rates for stays from December 2026 can now be cancelled free of charge until 7 days before arrival (previously 14 days). "
        "The exact date is shown when you book.",
        "• The fireplace lounge has new seating and our ground-floor accessible rooms have been refreshed.",
        "• Holiday week fills fast — book early.", "See you on the lake,\nThe Lakeview Pines team"),
        "2026-10-03T16:00:00.000Z", category="offers"))
    m.append(msg("msg_26_mom", "cnv_26_mom", CAROL, "Reunion 2026!", P(
        "Hi my darlings,",
        "Same place as last year please — Lakeview Pines Lodge, December 27 to 30. Everyone has filled in Jake's little RSVP form (thank you Jake).",
        "Dana, would you do the rooms like last year? It all went so smoothly. Love, Mom"),
        "2026-10-06T17:20:00.000Z", to=[DANA], cc=[MARK, LEAH_NEW], folder="fld_family", starred=True))
    m.append(msg("msg_26_mom_r1", "cnv_26_mom", MARK, "Re: Reunion 2026!", "Whatever you did last year was perfect Dana, just do that again. We'll be there the 27th.",
                 "2026-10-06T20:05:00.000Z", to=[DANA], cc=[CAROL, LEAH_NEW], folder="fld_family"))
    m.append(msg("msg_26_jake", "cnv_26_jake", JAKE, "RSVP export for the reunion", P(
        "Hey Dana, here's the export from the RSVP form so you have it for the bookings. I'm crashing with my buddy in South Lake so don't "
        "worry about a room for me. Ruth can't make it this year.", "Jake"),
        "2026-11-12T02:30:00.000Z", folder="inbox", read=False))
    # ---------- noise
    noise = [
        ("msg_n01", {"name": "Sacramento Unified", "email": "news@scusd.edu"}, "Winter concert: Dec 17", "Ivy's choir performs at 6:30 pm in the Main Hall.", "2026-11-10T16:00:00.000Z", "fld_school", "primary"),
        ("msg_n02", {"name": "Amazon.com", "email": "shipment-tracking@amazon.com"}, "Your package was delivered", "Snow chains (pair) were delivered to your front porch.", "2026-11-14T22:10:00.000Z", "fld_receipts", "primary"),
        ("msg_n03", {"name": "PG&E", "email": "noreply@pge.com"}, "Your November statement is ready", "Amount due $142.18 by Dec 4.", "2026-11-09T12:00:00.000Z", "inbox", "primary"),
        ("msg_n04", {"name": "Booking.com", "email": "deals@booking.com"}, "Black Friday: 30% off getaways", "Save on your next trip with Getaway Deals.", "2026-11-16T15:00:00.000Z", "inbox", "offers"),
        ("msg_n05", {"name": "Erin Park", "email": "erin.park@capitolhealth.org"}, "Q4 staffing grid", "Dana, can you review the Q4 grid before Friday?", "2026-11-17T17:42:00.000Z", "inbox", "primary"),
        ("msg_n06", CHRIS, "Chains", "Got the snow chains for Tahoe. Also, Mom asked if we're doing Christmas Eve at ours?", "2026-11-15T01:15:00.000Z", "inbox", "primary"),
        ("msg_n07", {"name": "Delta Dental", "email": "reminders@deltadental.com"}, "Appointment reminder", "Ivy Alvarado — cleaning on Dec 2 at 3:30 pm.", "2026-11-11T14:00:00.000Z", "inbox", "primary"),
        ("msg_n08", {"name": "Coronado Shores Hotel", "email": "reservations@coronadoshores.com"}, "We look forward to your stay", "Your January stay is coming up. Add a parking pass?", "2026-11-13T18:00:00.000Z", "fld_travel", "primary"),
        ("msg_n09", {"name": "PayPal", "email": "service@paypal.com"}, "You've got money", "Carol Whitfield sent you $300.00 USD. Note: Christmas money for the grandkids.", "2025-12-15T19:02:00.000Z", "fld_receipts", "primary"),
        ("msg_n10", {"name": "Nextdoor", "email": "no-reply@nextdoor.com"}, "Trending in East Sacramento", "Lost dog near McKinley Park", "2026-11-17T13:00:00.000Z", "inbox", "social"),
        ("msg_n11", {"name": "REI Co-op", "email": "rei@email.rei.com"}, "Gear up for snow season", "New arrivals in skiwear.", "2026-11-12T15:00:00.000Z", "inbox", "newsletters"),
        ("msg_n12", MARK, "Fantasy league", "You're getting crushed this week, sis.", "2026-11-16T05:40:00.000Z", "inbox", "primary"),
        ("msg_n13", {"name": "Stateline Grand", "email": "offers@statelinegrand.com"}, "Holiday packages from $149", "New Year's Eve at the Stateline Grand.", "2026-11-08T17:00:00.000Z", "inbox", "offers"),
        ("msg_n14", {"name": "Lakeview Pines Resort & Spa", "email": "hello@lakeviewpinesresort.com"}, "Ski season passes + spa", "Book 3 nights, get a free spa treatment.", "2026-11-05T17:00:00.000Z", "inbox", "offers"),
        ("msg_n15", {"name": "Ivy's soccer", "email": "coach.ramos@gmail.com"}, "End of season party", "Pizza on Saturday at 5!", "2026-11-04T23:00:00.000Z", "fld_school", "primary"),
        ("msg_n16", {"name": "Google", "email": "no-reply@accounts.google.com"}, "Security alert", "New sign-in on Mac.", "2026-11-03T15:00:00.000Z", "inbox", "updates"),
        ("msg_n17", {"name": "Booking.com", "email": "noreply@booking.com"}, "How was Seattle?", "Review Pike Street Hotel and help other travellers.", "2026-06-12T15:00:00.000Z", "fld_travel", "primary"),
        ("msg_n18", CHRIS, "Ski weekend money", "Jeff and Tom paid me back for the resort weekend on PayPal, all square.", "2026-02-17T03:00:00.000Z", "inbox", "primary"),
    ]
    for mid, s, subj, body, date, folder, cat in noise:
        m.append(msg(mid, "cnv_" + mid, s, subj, body, date, folder=folder, category=cat, read=mid not in ("msg_n05", "msg_n06")))
    sent_noise = [
        ("msg_s01", CHRIS, "Re: Chains", "Yes Christmas Eve at ours. Thanks for the chains!", "2026-11-15T02:00:00.000Z"),
        ("msg_s02", {"name": "Erin Park", "email": "erin.park@capitolhealth.org"}, "Re: Q4 staffing grid", "Will do by Thursday.", "2026-11-17T18:10:00.000Z"),
        ("msg_s03", JAKE, "Re: RSVP form", "Thanks Jake, form looks great.", "2026-09-28T04:00:00.000Z"),
    ]
    for mid, to, subj, body, date in sent_noise:
        m.append(msg(mid, "cnv_" + mid, DANA, subj, body, date, to=[to], folder="sent"))
    m.sort(key=lambda x: x["date"], reverse=True)
    folders = ([{"id": fid, "name": n, "type": "system", "parentId": None, "order": i, "createdAt": "2020-01-01T00:00:00.000Z"}
                for i, (fid, n) in enumerate(SYSTEM_FOLDERS)] +
               [{"id": fid, "name": n, "type": "user", "parentId": None, "order": i, "createdAt": "2023-05-05T00:00:00.000Z",
                 "updatedAt": None} for i, (fid, n) in enumerate(USER_FOLDERS)])
    # (first, last, nickname, email, company, favourite) -- Leah's card still has her old work address
    people = [("Carol", "Whitfield", "Mom", CAROL["email"], "", True), ("Mark", "Whitfield", "", MARK["email"], "", True),
              ("Leah", "Ortiz", "", LEAH_OLD["email"], "Ortiz Design", True), ("Chris", "Alvarado", "", CHRIS["email"], "", True),
              ("Jake", "Whitfield", "", JAKE["email"], "", False), ("Ruth", "Whitfield", "Aunt Ruth", RUTH["email"], "", False),
              ("Erin", "Park", "", "erin.park@capitolhealth.org", "Capitol Health", False)]
    contacts = [{"id": f"ct_{i + 1:04d}", "firstName": f, "lastName": l, "nickname": nick, "emails": [{"type": "home", "address": e}],
                 "phones": [], "addresses": [], "company": co, "jobTitle": "", "birthday": "", "website": "", "notes": "",
                 "isFavorite": fav, "avatarColor": "#5C6BC0", "source": "manual", "createdAt": "2023-05-05T00:00:00.000Z",
                 "updatedAt": None} for i, (f, l, nick, e, co, fav) in enumerate(people)]
    return {
        "currentUser": {"id": "usr_dana", "name": "Dana Whitfield", "firstName": "Dana", "email": DANA["email"], "aliases": [],
                        "avatarColor": "#7B1FA2", "jobTitle": "Nurse manager", "company": "Capitol Health",
                        "location": "Sacramento, CA", "storage": {"usedBytes": 2412345678, "totalBytes": 1099511627776}},
        "folders": folders, "messages": m, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {
            "appearance": {"theme": "light", "themeColor": "blue", "density": "comfortable", "messageLayout": "list"},
            "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
            "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
            "writing": {"signature": {"enabled": False, "text": "Dana"},
                        "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": DANA["email"],
                        "sendWithCtrlEnter": True, "linkPreviews": True},
            "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "",
                                 "onlyContacts": False, "updatedAt": None},
            "notifications": {"browser": False, "sound": False}, "ai": {"messageSummaries": False},
            "keyboardShortcuts": True, "rightPanel": {"open": False, "tab": "starred"},
            "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False},
        },
    }


def send_mail(mail, to_list, subject, body, at="2026-11-18T19:20:00.000Z"):
    mm = copy.deepcopy(mail)
    sent = msg("msg_sent_reunion26", "cnv_sent_reunion26", DANA, subject, body, at, to=to_list, folder="sent")
    sent["updatedAt"] = at
    mm["messages"].insert(0, sent)
    mm["activityLog"].append({"id": "act_sent_reunion26", "type": "message.send", "actor": DANA["email"], "createdAt": at,
                              "messageIds": [sent["id"]], "folderIds": ["sent"], "filterIds": [], "contactIds": [], "listIds": [],
                              "details": {"to": sent["to"], "cc": [], "bcc": [], "subject": subject, "attachmentIds": [],
                                          "originalMessageId": None, "incomingCopyIds": []}})
    return mm


# ====================================================================== google calendar
COLORS = {"c1": "#039BE5", "c2": "#F4511E", "c3": "#33B679", "c4": "#F6BF26", "c5": "#8E24AA"}


def ev(eid, cal, title, start, end, location="", description="", recurring="none", all_day=False, guests=None, reminders=None):
    return {"id": eid, "calendarId": cal, "title": title, "start": start, "end": end, "allDay": all_day,
            "location": location, "description": description, "guests": guests or [], "color": COLORS[cal],
            "recurring": recurring, "reminders": reminders if reminders is not None else [{"type": "popup", "minutes": 10}]}


def la(day, hhmm):
    """Browser-local wall time (TZ) to UTC ISO."""
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    local = datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=ZoneInfo(TZ))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_calendar():
    e = []
    allday = [
        ("evt_r24", "c2", "Whitfield Reunion — Big Bear", "2024-12-27", "2024-12-30", "Big Bear Timber Lodge", "All rooms non-refundable this time."),
        ("evt_r25", "c2", "Whitfield Reunion — Lake Tahoe", "2025-12-27", "2025-12-30", "Lakeview Pines Lodge, South Lake Tahoe",
         "Rooms booked Nov 5. Mom & Dad on the ground floor."),
        ("evt_ski", "c2", "Ski weekend (Chris + guys)", "2026-02-13", "2026-02-15", "Lakeview Pines Resort & Spa, Stateline", ""),
        ("evt_napa", "c1", "Napa anniversary", "2026-04-10", "2026-04-12", "Vintners Rest Inn", ""),
        ("evt_sea", "c3", "Seattle conference", "2026-06-08", "2026-06-11", "Pike Street Hotel", ""),
        ("evt_sd", "c2", "San Diego family trip", "2026-07-19", "2026-07-24", "Coronado Shores Hotel", ""),
        ("evt_sis", "c1", "Sisters' weekend — Tahoe", "2026-09-18", "2026-09-20", "Lakeview Pines Lodge", "Double Room, non-refundable."),
        ("evt_r26", "c2", "Whitfield Reunion 2026 — Lake Tahoe", "2026-12-27", "2026-12-30", "Lakeview Pines Lodge, South Lake Tahoe",
         "Mom asked for the same as last year."),
        ("evt_sd27", "c2", "Coronado long weekend", "2027-01-15", "2027-01-18", "Coronado Shores Hotel", ""),
        ("evt_h1", "c4", "Thanksgiving Day", "2026-11-26", "2026-11-27", "", ""),
        ("evt_h2", "c4", "Christmas Day", "2026-12-25", "2026-12-26", "", ""),
        ("evt_h3", "c4", "New Year's Day", "2027-01-01", "2027-01-02", "", ""),
        ("evt_h4", "c4", "Christmas Day", "2025-12-25", "2025-12-26", "", ""),
    ]
    for eid, cal, title, s, end, loc, desc in allday:
        e.append(ev(eid, cal, title, la(s, "00:00"), la(end, "00:00"), location=loc, description=desc, all_day=True, reminders=[]))
    timed = [
        ("evt_rem25", "c1", "Reunion rooms: free cancellation ends tomorrow", "2025-12-12", "09:00", "09:15", "",
         "Lakeview Pines free cancellation for all 4 rooms ends Dec 13. Last chance to cancel or change if anyone drops out."),
        ("evt_rem24", "c1", "Pay Big Bear balance on card", "2024-12-20", "09:00", "09:15", "", "Non-refundable rooms charged today."),
        ("evt_remsd", "c1", "Coronado: free cancellation ends Jan 8", "2027-01-07", "09:00", "09:15", "", ""),
        ("evt_w1", "c3", "Unit staffing huddle", "2026-11-18", "07:30", "08:00", "Capitol Health 4W", ""),
        ("evt_w2", "c3", "Q4 staffing grid review", "2026-11-20", "13:00", "14:00", "Conf room B", ""),
        ("evt_w3", "c3", "Charge nurse 1:1s", "2026-11-23", "10:00", "11:30", "", ""),
        ("evt_k1", "c5", "Ivy — dentist", "2026-12-02", "15:30", "16:15", "Delta Dental, J St", ""),
        ("evt_k2", "c5", "Ivy — winter concert", "2026-12-17", "18:30", "20:00", "Main Hall", ""),
        ("evt_k3", "c5", "Soccer party", "2026-11-21", "17:00", "19:00", "Round Table Pizza", ""),
        ("evt_p1", "c1", "Christmas Eve dinner (ours)", "2026-12-24", "17:00", "21:00", "Home", "Mom, Dad, Jake"),
        ("evt_p2", "c1", "Buy Tahoe groceries list", "2026-12-21", "19:00", "19:30", "", ""),
        ("evt_p3", "c1", "Mom's birthday lunch", "2026-12-06", "12:00", "14:00", "Ella Dining Room", ""),
    ]
    for eid, cal, title, day, s, end, loc, desc in timed:
        e.append(ev(eid, cal, title, la(day, s), la(day, end), location=loc, description=desc))
    e.append(ev("evt_gym", "c1", "Spin class", la("2026-11-03", "06:00"), la("2026-11-03", "06:45"), location="24 Hour Fitness",
                recurring="weekly"))
    return {
        "user": {"id": "u1", "username": "Dana Whitfield", "email": DANA["email"], "avatar": avatar("Dana Whitfield")},
        "calendars": [
            {"id": "c1", "name": "Dana Whitfield", "color": "bg-blue-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c2", "name": "Family trips", "color": "bg-red-600", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c3", "name": "Work", "color": "bg-green-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c4", "name": "US Holidays", "color": "bg-yellow-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c5", "name": "Ivy", "color": "bg-purple-500", "textColor": "text-white", "visible": True, "userId": "u1"},
        ],
        "events": e, "view": "week", "currentDate": NOW, "sidebarOpen": True,
        "settings": {"weekStart": 0, "defaultDuration": 60, "defaultView": "week",
                     "defaultReminder": {"type": "popup", "minutes": 10}, "timeFormat": "12h",
                     "showWeekNumbers": False, "showDeclinedEvents": False},
        "otherCalendars": [],
    }


def ui_event(cal_state, eid, day, title, description):
    """Mirror EventModal create: {...formData, id, start, end}."""
    st = copy.deepcopy(cal_state)
    st["events"].append({"title": title, "start": la(day, "09:00"), "end": la(day, "09:15"), "allDay": False, "location": "",
                         "description": description, "calendarId": "c1", "guests": [], "color": "bg-blue-500",
                         "recurring": "none", "reminders": [{"type": "popup", "minutes": 10}], "id": eid})
    return st


# ====================================================================== paypal
def tx(tid, ttype, amount, date, desc, recipient="", sender="", status="completed", destination=""):
    return {"id": tid, "type": ttype, "amount": amount, "currency": "USD", "recipientName": recipient, "senderName": sender,
            "destination": destination, "date": date, "status": status, "description": desc}


def build_paypal():
    t = [
        # 2024 Big Bear split (per head)
        tx("t_bb1", "request_sent", 816.0, "2025-01-06T03:25:00.000Z", "Big Bear reunion — 4 people x $204", recipient="Mark Whitfield"),
        tx("t_bb2", "request_sent", 408.0, "2025-01-06T03:26:00.000Z", "Big Bear reunion — 2 people x $204", recipient="Leah Ortiz"),
        tx("t_bb3", "request_sent", 408.0, "2025-01-06T03:27:00.000Z", "Big Bear reunion — Mom & Dad 2 x $204", recipient="Carol Whitfield"),
        tx("t_bb4", "payment_received", 816.0, "2025-01-06T19:40:00.000Z", "Big Bear reunion — 4 people x $204", sender="Mark Whitfield"),
        tx("t_bb5", "payment_received", 408.0, "2025-01-07T16:58:00.000Z", "Big Bear reunion — 2 people x $204", sender="Leah Ortiz"),
        tx("t_bb6", "payment_received", 408.0, "2025-01-09T18:02:00.000Z", "Big Bear reunion — Mom & Dad 2 x $204", sender="Carol Whitfield"),
        # 2025 Tahoe split (the precedent: own room + a third of the parents' room)
        tx("t_25a", "request_sent", 1360.0, "2025-11-06T04:10:00.000Z", "Tahoe reunion '25 — rooms", recipient="Mark Whitfield"),
        tx("t_25b", "request_sent", 790.0, "2025-11-06T04:11:00.000Z", "Tahoe reunion '25 — rooms", recipient="Leah Ortiz"),
        tx("t_25c", "payment_received", 1360.0, "2025-11-06T15:20:00.000Z", "Tahoe reunion '25 — rooms", sender="Mark Whitfield"),
        tx("t_25d", "payment_received", 790.0, "2025-11-07T01:45:00.000Z", "Tahoe reunion '25 — rooms", sender="Leah Ortiz"),
        tx("t_25e", "payment_received", 300.0, "2025-12-15T19:02:00.000Z", "Christmas money for the grandkids", sender="Carol Whitfield"),
        # 2026 noise and the sisters' weekend
        tx("t_26a", "payment_received", 245.0, "2026-02-16T22:00:00.000Z", "Resort weekend — my share", sender="Jeff Tanaka"),
        tx("t_26b", "payment_received", 245.0, "2026-02-17T01:30:00.000Z", "Resort weekend", sender="Tom Becker"),
        tx("t_26c", "payment_sent", 60.0, "2026-03-14T18:00:00.000Z", "Ivy's soccer fees", recipient="Sac Youth Soccer"),
        tx("t_26d", "payment_sent", 38.5, "2026-05-02T20:10:00.000Z", "Plant sale", recipient="Etsy - GreenThumbCo"),
        tx("t_26e", "withdrawal", 500.0, "2026-06-01T16:00:00.000Z", "Transfer to bank", destination="Golden 1 CU ****3307"),
        tx("t_26f", "payment_received", 42.0, "2026-07-25T03:00:00.000Z", "Coronado dinner", sender="Chris Alvarado"),
        tx("t_26g", "request_sent", 147.0, "2026-09-01T03:18:00.000Z", "Sisters' weekend — your half", recipient="Leah Whitfield-Ortiz"),
        tx("t_26h", "payment_received", 147.0, "2026-09-01T15:00:00.000Z", "Sisters' weekend — your half", sender="Leah Whitfield-Ortiz"),
        tx("t_26i", "payment_sent", 25.0, "2026-10-12T19:00:00.000Z", "Jake's RSVP site hosting", recipient="Jake Whitfield"),
        tx("t_26j", "payment_sent", 18.99, "2026-11-02T08:00:00.000Z", "Spotify Family", recipient="Spotify"),
        tx("t_26k", "payment_received", 30.0, "2026-11-11T02:00:00.000Z", "Fantasy league buy-in back", sender="Mark Whitfield"),
    ]
    t.sort(key=lambda x: x["date"], reverse=True)
    contacts = [("c_1", MARK), ("c_2", LEAH_NEW), ("c_3", LEAH_OLD), ("c_4", CAROL), ("c_5", JAKE), ("c_6", CHRIS),
                ("c_7", {"name": "Jeff Tanaka", "email": "jeff.tanaka@outlook.com"}),
                ("c_8", {"name": "Tom Becker", "email": "tbecker@gmail.com"}),
                ("c_9", {"name": "Sac Youth Soccer", "email": "registrar@sacyouthsoccer.org"})]
    return {
        "user": {"id": "u_1", "name": "Dana Whitfield", "email": DANA["email"], "balance": 2318.42, "currency": "USD",
                 "avatar": avatar("Dana Whitfield"), "phone": PHONES["dana"],
                 "address": {"street": "4120 M St", "city": "Sacramento", "state": "CA", "zip": "95819", "country": "US"},
                 "businessName": "", "accountType": "personal", "verified": True},
        "contacts": [{"id": cid, "name": p["name"], "email": p["email"], "avatar": avatar(p["name"])} for cid, p in contacts],
        "transactions": t,
        "paymentMethods": [{"id": "pm_1", "type": "card", "brand": "Visa", "bankName": "", "last4": "6612", "expiry": "08/28", "verified": True},
                           {"id": "pm_2", "type": "bank", "brand": "", "bankName": "Golden 1 CU", "last4": "3307", "expiry": "", "verified": True}],
        "invoices": [], "subscriptions": [], "paymentLinks": [],
        "settings": {"language": "English", "timezone": "America/Los_Angeles", "securityEmails": True, "marketingEmails": False},
        "notifications": [{"id": "n_1", "message": "Mark Whitfield sent you $30.00", "read": True, "date": "2026-11-11T02:00:00.000Z"}],
    }


def ui_request(pp, tid, email, amount, note, at):
    st = copy.deepcopy(pp)
    st["transactions"].insert(0, {"id": tid, "type": "request_sent", "amount": float(amount), "currency": "USD",
                                  "recipientName": email, "date": at, "status": "pending", "description": note})
    return st


# ====================================================================== RSVP input
def rsvp_rows():
    return [
        ["submitted_at", "name", "email", "household", "attending", "arrive", "depart", "adults", "children", "notes"],
        ["2026-10-01 09:12", "Carol Whitfield", CAROL["email"], "Carol & Jim", "yes", "2026-12-27", "2026-12-30", "2", "0", "Same lodge as always please!"],
        ["2026-10-02 20:41", "Leah Whitfield-Ortiz", LEAH_NEW["email"], "Leah & Sam", "yes", "2026-12-27", "2026-12-30", "2", "0", ""],
        ["2026-10-04 18:03", "Mark Whitfield", MARK["email"], "Mark, Priya, Ella & Noah", "yes", "2026-12-27", "2026-12-30", "2", "2", "Kids are thrilled"],
        ["2026-10-05 07:55", "Dana Whitfield", DANA["email"], "Dana, Chris & Ivy", "yes", "2026-12-27", "2026-12-30", "2", "1", ""],
        ["2026-10-09 12:30", "Ruth Whitfield", RUTH["email"], "Ruth", "no", "", "", "0", "0", "Can't make it this year, have fun everyone!"],
        ["2026-10-11 22:17", "Jake Whitfield", JAKE["email"], "Jake", "yes", "2026-12-28", "2026-12-29", "1", "0",
         "Staying with friends in South Lake, no room needed for me. Count me in for dinners."],
        ["2026-11-09 19:48", "Leah Whitfield-Ortiz", LEAH_NEW["email"], "Leah & Sam", "yes", "2026-12-28", "2026-12-30", "2", "0",
         "Updating my answer: Sam has his work holiday party on the 27th, so we'll drive up on the 28th."],
    ]


# ====================================================================== plans and runs
OUT_COLS = ["guest_name", "room", "check_in", "check_out", "confirmation_number", "total", "requested"]


def golden_plan():
    return {
        "bookings": {h: dict(zip(("first", "last", "email", "phone", "room", "cin", "cout", "special"), v)) for h, v in TARGETS.items()},
        "split": "third",                  # own room + parents/3 for dana, mark, leah
        "requests": {"mark": MARK["email"], "leah": LEAH_NEW["email"]},
        "extra_requests": [],              # (email, amount)
        "reminder_day": REMINDER_DAY,
        "mail_to": [CAROL, MARK, LEAH_NEW],
    }


def compute_split(rows, kind):
    """rows: household -> grand total. Returns household -> requested amount."""
    if kind == "third":
        share = rows["parents"] / 3
        return {"dana": 0, "mark": rows["mark"] + share, "leah": rows["leah"] + share, "parents": 0}
    if kind == "half":
        share = rows["parents"] / 2
        return {"dana": 0, "mark": rows["mark"] + share, "leah": rows["leah"] + share, "parents": 0}
    if kind == "perhead":
        heads = {"dana": 3, "mark": 4, "leah": 2, "parents": 2}
        ph = sum(rows.values()) / 11
        out = {h: round(ph * n, 2) for h, n in heads.items()}
        out["dana"] = 0
        return out
    raise ValueError(kind)


def run(seed, plan):
    booking = copy.deepcopy(seed["booking_com"])
    totals, confs, bk_rows = {}, {}, {}
    for i, (h, b) in enumerate(plan["bookings"].items()):
        rec = ui_booking(booking, i + 1, b["first"], b["last"], b["email"], b["phone"], b["room"], b["cin"], b["cout"],
                         b["special"], CONF[h], PIN[h])
        booking["bookings"].append(rec)
        totals[h] = rec["grandTotal"]
        confs[h] = rec["confirmationNumber"]
        bk_rows[h] = rec
    req = compute_split(totals, plan["split"])
    pp = seed["paypal"]
    k = 0
    for h, email in plan["requests"].items():
        k += 1
        pp = ui_request(pp, f"rq{k}x7Lm", email, round(req[h], 2), "Tahoe reunion '26 — rooms", f"2026-11-18T19:{0 + k:02d}:30.000Z")
    for email, amt in plan["extra_requests"]:
        k += 1
        pp = ui_request(pp, f"rq{k}x7Lm", email, amt, "Tahoe reunion '26 — rooms", f"2026-11-18T19:{0 + k:02d}:30.000Z")
    cal = seed["google_calendar"]
    if plan["reminder_day"]:
        dl = DEADLINE_2026
        cal = ui_event(cal, "evtRem26a", plan["reminder_day"], "Reunion rooms: free cancellation ends tomorrow",
                       f"Lakeview Pines free cancellation for all 4 rooms ends {fmt_short(dl)}. Last chance to cancel or change if anyone drops out.")
    names = {"dana": "Us", "mark": "Mark & co", "leah": "Leah & Sam", "parents": "Mom & Dad"}
    lines = "\n".join(f"{names[h]} – {bk_rows[h]['roomName']}, {fmt_short(bk_rows[h]['checkIn'])} to {fmt_short(bk_rows[h]['checkOut'])} "
                      f"(conf. {confs[h]})" for h in plan["bookings"])
    body = P("Hi everyone,", "The reunion rooms at Lakeview Pines Lodge are booked:", lines,
             "Same as last year: free-cancellation rooms, and PayPal requests for your share are on their way.", "Love, Dana")
    mail = send_mail(seed["yahoo_mail"], plan["mail_to"], "Tahoe rooms are booked! (2026)", body)
    out = [OUT_COLS]
    for h in plan["bookings"]:
        b = bk_rows[h]
        out.append([f"{b['guestFirstName']} {b['guestLastName']}", b["roomName"], b["checkIn"], b["checkOut"], b["confirmationNumber"],
                    f"{b['grandTotal']:.2f}", f"{req.get(h, 0):.2f}"])
    return {"booking_com": booking, "yahoo_mail": mail, "google_calendar": cal, "paypal": pp}, out


def naive_plan():
    p = golden_plan()
    b = p["bookings"]
    b["dana"]["room"] = "room_1_8"          # non-refundable Family Room
    b["mark"]["room"] = "room_1_11"         # non-refundable Lakeside Cabin
    b["leah"].update(room="room_1_4", cin="2026-12-27", last="Ortiz", email=LEAH_OLD["email"])
    b["parents"].update(room="room_1_1", special="")   # the upstairs Queen room from the cancelled booking
    p["split"] = "perhead"
    p["requests"] = {"mark": MARK["email"], "leah": LEAH_OLD["email"]}
    p["extra_requests"] = []  # carol request added in run via compute_split below
    p["reminder_day"] = "2026-12-12"
    p["mail_to"] = [CAROL, MARK, LEAH_OLD]
    p["carol_request"] = True
    return p


def slip(kind):
    p = golden_plan()
    if kind == "rsvp":
        p["bookings"]["leah"]["cin"] = "2026-12-27"
    elif kind == "split":
        p["split"] = "half"
    elif kind == "old_email":
        p["bookings"]["leah"]["email"] = LEAH_OLD["email"]
        p["requests"]["leah"] = LEAH_OLD["email"]
        p["mail_to"] = [CAROL, MARK, LEAH_OLD]
    elif kind == "parents_room":
        p["bookings"]["parents"].update(room="room_1_1", special="")
    elif kind == "reminder":
        p["reminder_day"] = "2026-12-12"
    else:
        raise ValueError(kind)
    return p


def run_plan(seed, plan):
    states, rows = run(seed, plan)
    if plan.get("carol_request"):
        totals = {h: next(b for b in states["booking_com"]["bookings"] if b["confirmationNumber"] == CONF[h])["grandTotal"] for h in CONF}
        amt = round(compute_split(totals, "perhead")["parents"], 2)
        states["paypal"] = ui_request(states["paypal"], "rq9x7Lm", CAROL["email"], amt, "Tahoe reunion '26 — rooms",
                                      "2026-11-18T19:09:30.000Z")
        for r in rows[1:]:
            if r[0].startswith("Carol"):
                r[6] = f"{amt:.2f}"
    return states, rows


# ====================================================================== io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def expected(seed):
    tg = {}
    totals = {}
    for h, (first, last, email, _ph, rid, cin, cout, special) in TARGETS.items():
        totals[h] = grand_total(rid, cin, cout)
        tg[h] = {"guest_first_names": HOUSEHOLD_FIRST[h], "guest_last_contains": "Ortiz" if h == "leah" else "Whitfield",
                 "guest_email": email, "property_id": LODGE_ID, "room_id": rid, "room_name": ROOMS[rid][1],
                 "check_in": cin, "check_out": cout, "grand_total": totals[h],
                 "special_request_keywords": ["ground", "lobby", "cane", "stairs", "elevator", "accessible"] if h == "parents" else []}
    req = compute_split(totals, "third")
    return {
        "clock": CLOCK, "timezone": TZ,
        "booking": {
            "property_id": LODGE_ID,
            "seed_booking_ids": [b["id"] for b in seed["booking_com"]["bookings"]],
            "households": tg,
            "wrong_room_ids": {"dana": ["room_1_8"], "mark": ["room_1_11", "room_1_10"], "leah": ["room_1_4"],
                               "parents": ["room_1_1", "room_1_2"]},
            "flexible_deadline": DEADLINE_2026,
        },
        "paypal": {
            "seed_transaction_ids": [t["id"] for t in seed["paypal"]["transactions"]],
            "requests": {"mark": {"email": MARK["email"], "amount": round(req["mark"], 2)},
                         "leah": {"email": LEAH_NEW["email"], "amount": round(req["leah"], 2), "old_email": LEAH_OLD["email"]}},
            "forbidden_request_emails": [CAROL["email"], JAKE["email"], CHRIS["email"], RUTH["email"], DANA["email"]],
            "dana_share": round(totals["dana"] + totals["parents"] / 3, 2),
            "wrong_amounts": {"same_as_2025": {"mark": 1360.0, "leah": 790.0},
                              "half_parents": {"mark": totals["mark"] + totals["parents"] / 2, "leah": totals["leah"] + totals["parents"] / 2},
                              "leah_three_nights": grand_total("room_1_5", "2026-12-27", "2026-12-30") + totals["parents"] / 3},
        },
        "calendar": {"seed_event_ids": [e["id"] for e in seed["google_calendar"]["events"]], "reminder_local_date": REMINDER_DAY,
                     "partial_local_date": DEADLINE_2026, "wrong_local_dates": ["2026-12-12", "2026-12-13"],
                     "text_keyword": "cancel"},
        "mail": {"required_recipients": [CAROL["email"], MARK["email"], LEAH_NEW["email"]], "old_leah": LEAH_OLD["email"],
                 "seed_message_ids": [mm["id"] for mm in seed["yahoo_mail"]["messages"]]},
        "output": {"path": "/workspace/output/reunion_2026.csv", "columns": OUT_COLS,
                   "rows": {h: {"guest_first_names": HOUSEHOLD_FIRST[h], "room": ROOMS[TARGETS[h][4]][1], "check_in": TARGETS[h][5],
                                "check_out": TARGETS[h][6], "total": totals[h], "requested": round(req[h], 2)} for h in TARGETS}},
    }


def main(out: Path):
    seed = {"booking_com": build_booking()}
    seed["yahoo_mail"] = build_mail(seed["booking_com"]["bookings"])
    seed["google_calendar"] = build_calendar()
    seed["paypal"] = build_paypal()
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, golden_rows = run_plan(seed, golden_plan())
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "reunion_2026.csv", golden_rows)
    write_csv(out / "input" / "reunion_rsvp_2026.csv", rsvp_rows())
    write_json(out / "expected.json", expected(seed))

    variants = {"golden": (golden, golden_rows), "nop": (seed, None), "naive": run_plan(seed, naive_plan())}
    for kind in ("rsvp", "split", "old_email", "parents_room", "reminder"):
        variants[f"slip_{kind}"] = run_plan(seed, slip(kind))
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "reunion_2026.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
