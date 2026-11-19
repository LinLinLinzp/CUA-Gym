"""Seed three offline sites and reference snapshots for filter-box-pickup."""

import json
import random
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, product_image, scan_document

CLOCK = "2026-11-17T14:40:00.000Z"
PERSON = "Lena Park"
ACCOUNT = "lena.park@example.test"
ORDER = "2000147-835261"
OTHER = "2000147-835621"
ATTACHMENT = "IMG_4821.jpg"
ADDRESS = {
    "id": "home", "recipient": PERSON, "line1": "418 Larkspur Bend", "city": "Bentonville",
    "region": "AR", "postalCode": "72712", "label": "Home", "timezone": "America/Chicago",
}
POLICY = {"windowDays": 30, "methods": ["store", "mail", "scheduled_pickup"], "resolutions": ["refund", "replacement"]}


def utc(day, hour, minute=0):
    return f"2026-11-{day:02}T{hour:02}:{minute:02}:00.000Z"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def photo(path):
    """Composite a photo of the carton before any of its four sleeves were returned."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    rng = random.Random(4821)
    width, height = 1320, 950
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            fiber = rng.randint(-6, 6) + (x % 43 == 0) * 4
            light = int(16 - ((x - 360) ** 2 + (y - 300) ** 2) / 115000)
            pixels.extend(channel + fiber + light for channel in (91, 71, 57))
    scene = Image.frombytes("RGB", (width, height), bytes(pixels))
    box = Image.new("RGBA", scene.size)
    draw = ImageDraw.Draw(box)
    draw.polygon([(81, 114), (1203, 61), (1256, 861), (119, 911)], fill=(39, 26, 17, 150))
    scene.paste(box.filter(ImageFilter.GaussianBlur(24)), mask=box.filter(ImageFilter.GaussianBlur(24)).getchannel("A"))
    draw = ImageDraw.Draw(scene)
    draw.polygon([(72, 91), (1184, 51), (1239, 837), (108, 888)], fill="#a9794b")
    draw.polygon([(125, 123), (1144, 91), (1191, 798), (157, 841)], fill="#c19a6d")
    draw.polygon([(638, 106), (721, 103), (754, 812), (674, 816)], fill="#c8a679")
    draw.line([(674, 108), (714, 814)], fill="#a27b56", width=3)
    for _ in range(11500):
        x, y = rng.randrange(168, 1137), rng.randrange(133, 793)
        draw.point((x, y), fill=rng.choice(("#c8a176", "#bc9568", "#bea074")))

    def place(piece, x, y, angle):
        piece = piece.convert("RGBA").rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        alpha = piece.getchannel("A")
        shadow = Image.new("RGBA", piece.size, "#39271f")
        shadow.putalpha(alpha.point(lambda value: value // 2).filter(ImageFilter.GaussianBlur(6)))
        scene.paste(shadow, (x + 12, y + 11), shadow)
        scene.paste(piece, (x, y), piece)

    # Use the scan helper for the paper texture, then crop and typeset the actual
    # thermal label at phone-preview scale.
    with TemporaryDirectory() as tmp:
        paper_path = scan_document([], Path(tmp) / "paper.png", seed=4821, width=640)
        label = Image.open(paper_path).crop((43, 88, 597, 560)).convert("RGB")
    draw = ImageDraw.Draw(label)
    small = ImageFont.load_default(size=33)
    large = ImageFont.load_default(size=55)
    draw.text((27, 29), "SHIP TO  /  LENA PARK", font=small, fill="#343338")
    draw.text((27, 95), "WALMART ORDER", font=small, fill="#343338")
    draw.text((27, 141), ORDER, font=large, fill="#181719")
    draw.line((27, 217, 522, 217), fill="#39383b", width=2)
    draw.text((27, 244), "PACKED: VELOMERE NEST", font=small, fill="#28262a")
    draw.text((27, 292), "COMPACT  /  VN-160", font=large, fill="#181719")
    x = 34
    while x < 512:
        stripe = rng.randint(2, 7)
        draw.rectangle((x, 378, x + stripe, 434), fill="#252427")
        x += stripe + rng.randint(2, 6)
    place(label, 129, 191, 5)

    for i, (model, size, color, angle) in enumerate([
        ("VN-180", "PLUS", "#385660", -7),
        ("VN-180", "PLUS", "#385660", 3),
        ("VN-180", "PLUS", "#385660", -2),
        ("VN-160", "COMPACT", "#436350", -4),
    ]):
        sleeve = Image.new("RGB", (453, 156), "#e1d9c9")
        draw = ImageDraw.Draw(sleeve)
        draw.rectangle((0, 0, 453, 104), fill=color)
        draw.rectangle((0, 146, 453, 156), fill="#c8baaa")
        draw.text((20, 7), "VELOMERE NEST", font=small, fill="#f7f1e8")
        draw.text((20, 40), model, font=large, fill="#ffffff")
        draw.text((20, 111), size + "   /   FILTER", font=small, fill="#353b39")
        for x in range(348, 445, 6):
            draw.line((x, 17, x - 27, 89), fill="#adbdba", width=2)
        place(sleeve, 726 - i * 10, 125 + i * 167, angle)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.save(path, quality=92, optimize=True)


def walmart(out):
    products = []
    images = out / "seed" / "files" / "walmart"
    images.mkdir(parents=True, exist_ok=True)

    def product(sku, title, price, variant=None, brand="Vellink Home"):
        filename = f"{sku}.svg"
        (images / filename).write_text(unquote(product_image(title).split(",", 1)[1]), encoding="utf-8")
        row = {
            "id": sku, "title": title, "price": price, "brand": brand, "department": "Home",
            "seller": "Walmart", "taxRate": 0.08, "shippingStock": 22, "maxOrderQty": 8,
            "pickupStockByStore": {}, "registryEligible": False, "returnPolicy": POLICY,
            "imagePath": file_url(filename),
        }
        if variant:
            row["variant"] = variant
        products.append(row)
        return row

    compact = product("vn-160", "Velomere Nest Air Filter - Compact", 18.50, "VN-160", "Velomere")
    plus = product("vn-180", "Velomere Nest Air Filter - Plus", 19.50, "VN-180", "Velomere")
    cloth = product("cloth-set", "Vellink Microfiber Dust Cloths", 8.25)
    supplies = [
        product(f"home-{i:02}", "Vellink " + title, price)
        for i, (title, price) in enumerate([
            ("Shelf Liner", 12), ("Dish Brush", 5), ("Felt Pads", 4), ("Drawer Tray", 14),
            ("Laundry Mesh Bags", 11), ("Storage Clips", 6), ("Door Mat", 22), ("Hanger Set", 16),
            ("Packing Tape", 7), ("Sponge Set", 7), ("LED Bulbs", 13), ("Utility Hooks", 9),
        ])
    ]

    def order(oid, number, purchased, delivered, items):
        lines = []
        for n, (item, quantity) in enumerate(items, 1):
            subtotal = round(item["price"] * quantity, 2)
            lines.append({
                "id": f"{oid}-{n}", "productId": item["id"], "quantity": quantity,
                "product": {k: item[k] for k in ("title", "variant", "seller", "imagePath") if k in item},
                "unitPrice": item["price"], "taxRate": 0.08, "lineSubtotal": subtotal,
                "lineTax": round(subtotal * 0.08, 2), "returnPolicy": POLICY,
            })
        subtotal = round(sum(line["lineSubtotal"] for line in lines), 2)
        tax = round(sum(line["lineTax"] for line in lines), 2)
        return {
            "id": oid, "orderNumber": number, "ownerId": "lena", "status": "delivered",
            "fulfillmentMode": "shipping", "lines": lines, "shippingAddress": ADDRESS,
            "paymentSummary": {"brand": "Visa", "last4": "0418"},
            "createdAt": purchased, "fulfilledAt": delivered, "events": [],
            "totals": {"subtotal": subtotal, "tax": tax, "fulfillmentFee": 0,
                       "total": round(subtotal + tax, 2), "currency": "USD"},
        }

    orders = [
        order("parcel-b", OTHER, utc(13, 17), utc(16, 18, 42), [(plus, 3), (cloth, 1)]),
        order("parcel-a", ORDER, utc(12, 18), utc(16, 18, 37), [(compact, 4), (cloth, 1)]),
    ]
    for i in range(24):
        delivered = datetime(2026, 11, 11, 19) - timedelta(days=i * 3)
        purchased = delivered - timedelta(days=3)
        orders.append(order(f"home-order-{i:02}", f"2000147-{832000-i:06}",
                            purchased.isoformat(timespec="milliseconds") + "Z",
                            delivered.isoformat(timespec="milliseconds") + "Z",
                            [(supplies[i % len(supplies)], 1 + i % 2)]))
    prior = return_record(orders[2], 1, utc(12, 18, 20), method="store", reason="changed_mind",
                          reference="71BFAB10")
    filter_return = return_record(orders[1], 1, utc(17, 13, 15), method="store", reference="36EF0192")
    for completed in (prior, filter_return):
        completed["status"] = "completed"
    return {
        "profile": {"id": "lena", "name": PERSON, "email": ACCOUNT, "addresses": [ADDRESS],
                    "paymentSummary": {"brand": "Visa", "last4": "0418"}},
        "catalog": products, "orders": orders, "returns": [filter_return, prior],
        "cart": {"id": "home-cart", "ownerId": "lena", "pickupReservationId": None, "lines": [], "events": []},
        "stores": [], "pickupSlots": [], "pickupReservations": [], "registries": [],
    }


def return_record(order, quantity, created_at, *, start=None, end=None, method="scheduled_pickup",
                  reason="wrong_item", extra=False, reference="28A411FE"):
    lines = []
    for index in range(2 if extra else 1):
        line = order["lines"][index]
        count = quantity if index == 0 else 1
        subtotal = round(line["unitPrice"] * count, 2)
        tax = round(subtotal * 0.08, 2)
        lines.append({
            "id": f"return-line-example-{reference}-{index}", "orderLineId": line["id"],
            "productId": line["productId"], "quantity": count, "reason": reason,
            "resolution": "refund", "unitPrice": line["unitPrice"], "refundSubtotal": subtotal,
            "refundTax": tax, "refundAmount": round(subtotal + tax, 2),
        })
    result = {
        "id": f"return-example-{reference.lower()}", "returnNumber": f"RMA-{reference}",
        "instructionsCode": f"RET-{reference}", "orderId": order["id"], "actorId": "lena",
        "createdAt": created_at, "status": "submitted", "method": method,
        "lines": lines, "refundEstimate": round(sum(line["refundAmount"] for line in lines), 2),
    }
    if start:
        result["pickupAppointment"] = {"startAt": start, "endAt": end, "address": order["shippingAddress"]}
    return result


def yahoo(out):
    path = out / "seed" / "files" / "yahoo_mail" / ATTACHMENT
    photo(path)
    attachment = {"id": "att-4821", "name": ATTACHMENT, "size": path.stat().st_size,
                  "mimeType": "image/jpeg", "kind": "image", "url": file_url(ATTACHMENT), "source": "seed"}

    def mail(mid, thread, sender, email, subject, body, date, attachments=()):
        return {
            "id": mid, "conversationId": thread, "folderId": "inbox", "category": "primary",
            "status": "received", "isDraft": False, "isRead": True, "isStarred": False,
            "from": {"name": sender, "email": email}, "to": [{"name": PERSON, "email": ACCOUNT}],
            "cc": [], "bcc": [], "subject": subject, "body": body, "snippet": body,
            "date": date, "createdAt": date, "attachments": list(attachments),
        }

    subject = "Filters from the porch"
    first = mail("msg-theo-first", "cnv-porch", "Theo Park", "theo.park@example.test", subject,
                 "I think the Plus order is the one with the mix-up. At a glance I saw one sleeve that looked off. The dust cloths are fine.",
                 utc(16, 21, 8))
    followup = mail("msg-theo-photo", "cnv-porch", "Theo Park", "theo.park@example.test", "Re: " + subject,
                    "That was a guess before I checked the labels. This is all the filter sleeves by the shipping "
                    "label, as they came out of that carton last night. I took some of its wrong-size sleeves back "
                    "to the Walmart returns desk this morning, after the photo. Their receipt is in Purchase "
                    "History if you need to see what they already took. The other carton was fine.",
                    utc(17, 13, 50), [attachment])
    followup["inReplyToId"] = first["id"]
    topics = [
        ("Key copy", "I left the spare with Mara."), ("Neighborhood cleanup", "We have bags and gloves at the club shed."),
        ("November gas bill", "Your statement is ready."), ("Soup recipe", "I used white beans and fresh rosemary."),
        ("Porch light", "The hardware counter has your replacement bulb."), ("Library hold", "Your book is at the front desk."),
        ("Potluck", "I'll bring the apple cake."), ("Garden club receipts", "Please keep these for next month's meeting."),
        ("Parcel shelf reminder", "The lobby parcel shelf is being painted this week."),
        ("Return receipt", "The shelf liner was returned in store. Keep this for your records."),
        ("Coat drive", "The community room has a drop box."), ("Coffee for Sunday", "Shall we meet at the corner cafe?"),
        ("Furnace service invoice", "Thanks for having us out last month."), ("Trail update", "The west loop is open again."),
        ("Parking permit", "The new permit is ready to collect."), ("Recycling", "Cardboard will be collected on Friday."),
        ("Dinner leftovers", "There's a container in the back of the fridge."), ("Board game night", "I can bring the word game."),
        ("Window measurement", "The frame is slightly narrower at the top."), ("Holiday hours", "The desk closes early next Wednesday."),
        ("November dues", "The community room payment came through."), ("Photo prints", "Your envelope is at the pickup counter."),
        ("Missing scarf", "I put it on the hook by the back door."), ("Shared grocery list", "I added oatmeal and pears."),
    ]
    messages = [
        mail(f"msg-life-{i:02}", f"cnv-life-{i:02}", sender, email, title, body, utc(16 - i // 2, 18 - i % 2))
        for i, (title, body) in enumerate(topics)
        for sender, email in [(["Mara Vale", "Neighborhood Desk", "Household Services"][i % 3],
                               ["mara.vale@example.test", "desk@example.test", "service@example.test"][i % 3])]
    ]
    return {
        "currentUser": {"id": "lena", "name": PERSON, "firstName": "Lena", "email": ACCOUNT,
                        "aliases": [], "avatarColor": "#6847a2", "storage": {"usedBytes": path.stat().st_size, "totalBytes": 1000000000}},
        "settings": {"viewing": {"conversations": True}},
        "folders": [
            {"id": folder.lower(), "name": folder, "type": "system", "parentId": None, "order": i, "createdAt": utc(1, 12)}
            for i, folder in enumerate(["Inbox", "Drafts", "Sent", "Archive", "Spam", "Trash"])
        ],
        "messages": [followup, first, *messages], "contacts": [], "contactLists": [],
        "filters": [], "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
    }


def event(eid, title, start, end, calendar="c1"):
    return {
        "id": eid, "calendarId": calendar, "title": title, "start": start, "end": end, "allDay": False,
        "location": "", "description": "", "guests": [], "color": "bg-blue-500", "recurring": "none",
        "reminders": [{"type": "popup", "minutes": 10}],
    }


def calendar():
    events = [
        event("e-dental", "Dentist across town", utc(18, 16, 30), utc(18, 17, 30)),
        event("e-training", "On-site training", utc(18, 20, 45), utc(18, 21, 30), "c2"),
        event("e-keys", "Pick up studio keys", utc(19, 17), utc(19, 17, 45)),
        event("e-review", "Review at the studio", utc(19, 20), utc(19, 21), "c2"),
    ]
    for i in range(24):
        offset = i // 2
        day = 5 + offset if i < 20 else 20 + offset - 10
        hour = 18 if i % 2 else 23
        title = ["Lunch with Mara", "Studio check-in", "Grocery run", "Supplier handoff",
                 "Library pickup", "In-office review", "Rehearsal", "Inventory walk"][i % 8]
        events.append(event(f"e-life-{i:02}", title, utc(day, hour), utc(day, hour, 30), "c2" if i % 2 else "c1"))
    return {
        "user": {"id": "lena", "username": PERSON, "email": ACCOUNT, "avatar": avatar(PERSON)},
        "calendars": [
            {"id": "c1", "name": "Personal", "color": "#039BE5", "visible": True, "userId": "lena", "isDefault": True},
            {"id": "c2", "name": "Work", "color": "#33B679", "visible": True, "userId": "lena", "isDefault": False},
        ],
        "otherCalendars": [], "events": events, "view": "week", "currentDate": CLOCK, "sidebarOpen": True,
        "settings": {"weekStart": 0, "defaultDuration": 60, "defaultView": "week", "timeFormat": "12h"},
    }


def run(out):
    initial = {"walmart": walmart(out), "yahoo_mail": yahoo(out), "google_calendar": calendar()}
    for site, state in initial.items():
        write_json(out / "seed" / f"{site}.json", state)

    def outcome(order_id, quantity, start, end, *, inspect=True, extra=False):
        result = deepcopy(initial)
        shop = result["walmart"]
        order = next(row for row in shop["orders"] if row["id"] == order_id)
        shop["returns"].append(return_record(order, quantity, CLOCK, start=start, end=end, extra=extra))
        result["google_calendar"]["events"].append(
            event("evt-example-pickup", "Walmart return pickup – " + order["orderNumber"], start, end)
        )
        if inspect:
            mail = result["yahoo_mail"]
            file = mail["messages"][0]["attachments"][0]
            mail["activityLog"].append({
                "id": "activity-example-preview", "type": "attachment.preview", "actor": ACCOUNT,
                "createdAt": CLOCK, "messageIds": ["msg-theo-photo"], "folderIds": [],
                "filterIds": [], "contactIds": [], "listIds": [],
                "details": {"attachmentId": file["id"], **{key: file[key] for key in ("name", "size", "mimeType", "url")}},
            })
        return result

    solutions = {
        "golden": outcome("parcel-a", 2, utc(19, 15), utc(19, 17)),
        "nop": initial,
        "naive": outcome("parcel-b", 1, utc(18, 15), utc(18, 17), inspect=False, extra=True),
        "slip_quantity": outcome("parcel-a", 3, utc(19, 15), utc(19, 17)),
        "slip_window": outcome("parcel-a", 2, utc(18, 20), utc(18, 22)),
    }
    for site, state in solutions["golden"].items():
        write_json(out / "golden" / f"{site}.json", state)
    for name, current in solutions.items():
        variant = out / "variants" / name
        (variant / "output").mkdir(parents=True, exist_ok=True)
        for site, before in initial.items():
            write_json(variant / "state" / site / "initial.json", before)
            write_json(variant / "state" / site / "current.json", current[site])


if __name__ == "__main__":
    run(Path(sys.argv[1]))
