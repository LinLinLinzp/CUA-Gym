"""Deterministic Maple House handoff inputs and contract fixture states."""
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar

PRIOR = "2026-11-18T15:00:00.000Z"
NOW = "2026-11-19T14:00:00.000Z"
ZONE = "America/New_York"
INPUT = "Maple-Reading-Room-Working.drawio"
OUTPUT = "Maple-Reading-Room-Delivery.drawio"
MAIN_ORDER = "wf-maple-461"
MAIN_SHIPMENT = MAIN_ORDER + "-s1"
SIDE_SHIPMENT = MAIN_ORDER + "-s2"
ANNEX_ORDER = "wf-maple-462"
ANNEX_SHIPMENT = ANNEX_ORDER + "-s1"
TEAM = "maple-house"
CHANNEL = "furniture-deliveries"
THREAD = "maple-sideboard"
PROJECT = "maple-install"
TASK = "install-reading-103"
SIDE_TASK = "install-reading-chairs"
BASE_NOTES = "Install the long sideboard in Reading Room 103. Protect the terrazzo and leave the brass floor outlet accessible."
DRIVER = "Maple House Reading Room 103: enter South Gate, check in at Receiving, then use Service Hall and Freight Lift. Keep the crate upright."
WINDOW = "Tuesday, Nov 24, noon–4 pm ET"
HANDOFF = (
    "Delivery confirmed for WF-9400461 (long sideboard), " + WINDOW + ". "
    "Use South Gate, check in at Receiving, then take Service Hall and Freight Lift to Reading Room 103. "
    "Keep the crate upright. The installation crew is booked for Wednesday, Nov 25."
)
REPLY = (
    "The long sideboard freight is confirmed for " + WINDOW + " via South Gate. "
    "The editable " + OUTPUT + " is attached to Install long sideboard — Reading Room 103 in Asana / Maple House Fit-out."
)


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


LOCATIONS = (
    ("truck", "Freight truck", 55, 206, 130, 54),
    ("north-gate", "North Gate\n38 in clear", 245, 90, 145, 58),
    ("north-hall", "Gallery Hall\n35 in at turn", 480, 90, 155, 58),
    ("south-gate", "South Gate\n42 in clear", 245, 318, 145, 58),
    ("south-hall", "Service Hall\n41 in at turn", 480, 318, 155, 58),
    ("lift", "Freight Lift\n40 in clear", 710, 206, 135, 54),
    ("room", "Reading Room 103", 910, 206, 155, 54),
)
NORTH = ("truck", "north-gate", "north-hall", "lift", "room")
SOUTH = ("truck", "south-gate", "south-hall", "lift", "room")


def write_drawing(path, branch, *, retain_plan=True, equivalent=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    document = ET.Element("mxfile", host="Electron", version="32.6.10")
    sheet = ET.SubElement(document, "diagram", id="maple-l1", name="Ground floor and lift")
    graph = ET.SubElement(sheet, "mxGraphModel", grid="1", gridSize="5", guides="1", connect="1",
                          page="1", pageScale="1", pageWidth="1120", pageHeight="465",
                          background="#ffffff")
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", value="Maple House floor plan", parent="0")
    ET.SubElement(root, "mxCell", id="route", value="Crew carry route", parent="0")

    def vertex(ident, label, x, y, width, height, style):
        cell = ET.SubElement(root, "mxCell", id=ident, value=label, style=style, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(width), height=str(height),
                      attrib={"as": "geometry"})

    text = "text;html=1;whiteSpace=wrap;align=left;fontColor=#123346;"
    vertex("title", "Maple House | Reading Room 103 delivery access", 42, 26, 1020, 32,
           text + "fontSize=24;fontStyle=1;")
    vertex("legend", "Blue arrows show the active carry path. Clear widths are minimum field measurements.",
           47, 416, 1010, 27, text + "fontSize=14;")
    vertex("receiving", "Receiving check-in desk", 247, 377, 160, 23, text + "fontSize=12;")
    if retain_plan:
        vertex("keep-clear", "Courtyard glazing\nKeep clear", 255, 201, 370, 65,
               "rounded=0;whiteSpace=wrap;html=0;fillColor=#f9e9e5;strokeColor=#be7e70;"
               "fontColor=#743b34;fontSize=16;connectable=0;")
    for ident, label, x, y, width, height in LOCATIONS:
        vertex(ident, label, x, y, width, height,
               "rounded=1;whiteSpace=wrap;html=0;fillColor=#edf5f9;strokeColor=#7995a8;"
               "fontColor=#123346;fontSize=16;")

    endpoints = {
        ("truck", "north-gate"): [(212, 233), (212, 119)],
        ("north-hall", "lift"): [(675, 119), (675, 233)],
        ("truck", "south-gate"): [(212, 233), (212, 347)],
        ("south-hall", "lift"): [(675, 347), (675, 233)],
    }
    if equivalent:
        endpoints[("truck", "south-gate")] = [(222, 233), (222, 347)]
        endpoints[("south-hall", "lift")] = [(660, 347), (660, 233)]
    for index, (source, target) in enumerate(zip(branch, branch[1:]), 1):
        cell = ET.SubElement(
            root, "mxCell", id=f"carry-{index}", parent="route", edge="1", source=source, target=target,
            style="edgeStyle=segmentEdgeStyle;rounded=0;html=1;strokeColor=#145985;strokeWidth=4;"
                  "endArrow=block;endFill=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
        )
        points = ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
        if (source, target) in endpoints:
            waypoints = ET.SubElement(points, "Array", attrib={"as": "points"})
            for x, y in endpoints[source, target]:
                ET.SubElement(waypoints, "mxPoint", x=str(x), y=str(y))
    ET.ElementTree(document).write(path, encoding="utf-8", xml_declaration=True)


def slot(shipment, label, day, start, end):
    return dict(id=f"{shipment}-{label}", startAt=f"2026-11-{day}T{start}:00:00.000Z",
                endAt=f"2026-11-{day}T{end}:00:00.000Z")


def item(shipment, name, sku, variant, price):
    return dict(id=f"{shipment}-i1", name=name, sku=sku, variant=variant,
                quantity=1, canceledQuantity=0, unitPrice=price, unitTax=0,
                returnable=True, shipmentId=shipment)


def wayfair():
    account = dict(id="avery-quinn", name="Avery Quinn", email="avery@example.test", timeZone=ZONE)
    address = dict(name="Maple House", line1="614 Fable Street", line2="Reading Room 103",
                   city="Providence", region="RI", postalCode="02903", country="US")
    long = item(MAIN_SHIPMENT, "Alder Row 84-inch Long Sideboard", "AR-84-ALD", 'Alder / 34 in crate depth', 949)
    chair = item(SIDE_SHIPMENT, "Alder Row Reading Chair", "AR-CH-ALD", 'Alder / 28 in crate depth', 315)
    short = item(ANNEX_SHIPMENT, "Alder Row 60-inch Sideboard", "AR-60-ALD", 'Alder / 30 in crate depth', 689)
    orders = [
        dict(id=MAIN_ORDER, orderNumber="WF-9400461", placedAt=PRIOR, currency="USD", shippingAmount=0,
             totalAmount=1264, paymentLabel="Visa ending in 0184", shipTo=address, items=[long, chair]),
        dict(id=ANNEX_ORDER, orderNumber="WF-9400462", placedAt=PRIOR, currency="USD", shippingAmount=0,
             totalAmount=689, paymentLabel="Visa ending in 0184",
             shipTo={**address, "name": "Maple House Annex", "line2": "Community Room 201"}, items=[short]),
    ]
    shipments, appointments = [], []
    for order_id, shipment in ((MAIN_ORDER, MAIN_SHIPMENT), (MAIN_ORDER, SIDE_SHIPMENT), (ANNEX_ORDER, ANNEX_SHIPMENT)):
        options = [
            slot(shipment, "mon-am", 23, 14, 18),
            slot(shipment, "tue-am", 24, 13, 17),
            slot(shipment, "tue-pm", 24, 17, 21),
            slot(shipment, "wed-pm", 25, 17, 21),
        ]
        shipments.append(dict(
            id=shipment, orderId=order_id, type="freight", status="ready_to_schedule",
            carrier="Eastline Freight", trackingNumber=f"ELF-{order_id[-3:]}-{shipment[-1]}",
            timeZone=ZONE, availableSlots=options,
            trackingEvents=[dict(at=PRIOR, label="Arrived at local delivery station", location="Providence, RI")],
        ))
        booked = options[0]
        appointments.append(dict(
            id=f"appt-{shipment}", orderId=order_id, shipmentId=shipment, slotId=booked["id"],
            startAt=booked["startAt"], endAt=booked["endAt"], timeZone=ZONE,
            instructions="Use North Gate.", status="confirmed", actorId=account["id"], createdAt=PRIOR,
        ))
    return dict(account=account, orders=orders, shipments=shipments, orderCancellations=[],
                deliveryAppointments=appointments, damageClaims=[], returns=[])


def asana():
    people = [
        dict(userId=ident, name=name, email=f"{ident}@example.test", avatar=avatar(name),
             title=title, department="Maple House", location="Providence", timezone=ZONE, theme="light")
        for ident, name, title in (
            ("avery", "Avery Quinn", "Project Coordinator"),
            ("jamie", "Jamie Silva", "Installation Lead"),
            ("carla", "Carla Ngo", "Facilities Supervisor"),
        )
    ]
    members = [person["userId"] for person in people]
    project = dict(projectId=PROJECT, name="Maple House Fit-out", teamId=TEAM, color="#126f79", icon=avatar("Maple House"),
                   description="Furniture and fixtures for the reopened Maple House reading room.",
                   ownerId="avery", memberIds=members, sections=[dict(sectionId="fitout", name="Installation", collapsed=False)],
                   customFields=[], privacy="private", archived=False, starred=True, createdDate=PRIOR, modifiedDate=PRIOR)

    def task(ident, name, due, notes):
        return dict(taskId=ident, name=name, projectId=PROJECT, sectionId="fitout", description=notes,
                    assigneeId="jamie", creatorId="avery", dueDate=due, completed=False, dependencies=[],
                    tags=[], attachmentIds=[], customFieldValues={}, likeCount=0, createdDate=PRIOR, modifiedDate=PRIOR)

    return dict(
        currentUser=people[0], users=people,
        teams=[dict(teamId=TEAM, name="Maple House", description="Project team", memberIds=members,
                    ownerId="avery", privacy="private", createdDate=PRIOR)],
        projects=[project],
        tasks=[
            task(TASK, "Install long sideboard — Reading Room 103", "2026-11-24", BASE_NOTES),
            task(SIDE_TASK, "Install reading chairs — Reading Room 103", "2026-11-24",
                 "Set the chairs along the window and retain all floor protectors."),
        ],
        comments=[dict(commentId="prep-note", taskId=TASK, userId="jamie",
                       content="Protective pads are staged in the room.", createdDate=PRIOR, likedBy=[])],
        portfolios=[], goals=[], notifications=[], attachments=[],
    )


def message(ident, author, content, timestamp=PRIOR, *, parent=None, channel=CHANNEL, subject=""):
    return dict(messageId=ident, containerId=channel, containerType="channel", senderId=author,
                content=content, contentType="text", messageType="message", createdDateTime=timestamp,
                lastEditedDateTime=None, deletedDateTime=None, importance="normal", subject=subject,
                replyToId=parent, reactions=[], mentions=[], attachments=[], isBookmarked=False)


def teams():
    people = [
        dict(userId=ident, displayName=name, email=f"{ident}@example.test", avatar=avatar(name),
             avatarColor="#126f79", avatarInitials="".join(part[0] for part in name.split()),
             jobTitle=title, department="Maple House", presence="available", statusMessage="")
        for ident, name, title in (
            ("avery", "Avery Quinn", "Project Coordinator"),
            ("carla", "Carla Ngo", "Facilities Supervisor"),
            ("jamie", "Jamie Silva", "Installation Lead"),
            ("theo", "Theo Hart", "Receiving Assistant"),
        )
    ]
    ids = [user["userId"] for user in people]
    channels = [
        dict(channelId=ident, teamId=TEAM, displayName=name, description=description,
             membershipType="standard", isFavoriteByDefault=True, isPinned=False, isMuted=False,
             unreadCount=0, lastMessagePreview="", lastMessageTimestamp=PRIOR, createdDateTime=PRIOR,
             members=ids, tabs=[dict(tabId=f"tab-{ident}", displayName="Posts", type="posts", isDefault=True)],
             pinnedMessages=[])
        for ident, name, description in (
            ("general", "General", "Maple House project updates"),
            (CHANNEL, "Furniture Deliveries", "Freight bookings and receiving coordination"),
        )
    ]
    messages = {
        "general": [message("general-supplies", "theo", "Extra furniture pads are in the receiving cabinet.",
                            channel="general")],
        CHANNEL: [
            message(THREAD, "jamie", "The 84-inch Alder Row sideboard for Reading Room 103 needs a new truck "
                    "slot. It shares Wayfair order WF-9400461 with the chairs, but they're separate freight "
                    "shipments. The 60-inch sideboard is the annex's order. The floor-plan copy for this room "
                    "is in the project packet. Facilities needs to clear the route and lift before we move anything.",
                    subject="Reading Room 103 | long sideboard delivery"),
            message("route-draft", "theo", "I'd leave the truck on Monday, using North Gate as usual. The door "
                    "itself clears 38 inches and the crate is 34.", "2026-11-18T16:00:00.000Z",
                    subject="Reading Room 103 | sideboard route suggestion"),
            message("crew-availability", "jamie", "Our receiving crew is available Tuesday Nov 24 from noon "
                    "through 4 pm Eastern. We can install Wednesday Nov 25. Please move the date on the existing "
                    "Install long sideboard — Reading Room 103 task in Maple House Fit-out.",
                    "2026-11-19T12:10:00.000Z", subject="Reading Room 103 | sideboard crew availability"),
            message("clearance-approved", "carla", "Facilities clearance for the sideboard supersedes the North "
                    "Gate suggestion. Carry the crate upright, allowing one inch of clearance on each side of "
                    "its 34-inch depth. Check the narrowest turn on the ground-floor plan as well as the gate "
                    "and lift. Use the route that meets those clearances all the way. Never cut across the courtyard "
                    "glazing. On Tuesday the freight lift is staffed 11 am–4 pm Eastern. The whole truck window "
                    "must fit the lift and crew overlap. Driver should check in at Receiving. Leave the chair and "
                    "annex bookings as they are.", "2026-11-19T13:00:00.000Z",
                    subject="Reading Room 103 | sideboard facilities clearance"),
            message("chair-thread", "theo", "The Reading Room 103 chair freight stays on its original slot. "
                    "Use the usual North Gate path for those smaller cartons.", "2026-11-19T13:10:00.000Z",
                    subject="Reading Room 103 | chair delivery"),
            message("annex-thread", "theo", "Community Room 201 has its own sideboard and remains on the annex plan.",
                    "2026-11-19T13:15:00.000Z", subject="Annex sideboard"),
        ],
    }
    return dict(currentUser=people[0], users=people,
                teams=[dict(teamId=TEAM, displayName="Maple House Fit-out", description="Project field team",
                            avatar=people[0]["avatar"], avatarColor="#126f79", avatarInitials="MH",
                            visibility="private", isArchived=False, isFavorite=True, createdDateTime=PRIOR,
                            members=ids, owners=["avery"], channels=[channel["channelId"] for channel in channels],
                            settings=dict(allowMemberCreateChannels=True, allowMemberDeleteMessages=True,
                                          allowGiphy=True, allowStickers=True))],
                channels=channels, messages=messages, chats=[], meetings=[], calls=[], files=[], notifications=[])


def make_fixture(directory, initial, *, shipment=MAIN_SHIPMENT, booking=True, window="tue-pm",
                 driver=DRIVER, route=SOUTH, retain_plan=True, date="2026-11-25",
                 notes=HANDOFF, attach=True, thread=THREAD, reply=REPLY, equivalent=False):
    state = deepcopy(initial)
    output = directory / "output"
    output.mkdir(parents=True)
    if route:
        write_drawing(output / OUTPUT, route, retain_plan=retain_plan, equivalent=equivalent)

    if booking:
        wayfair_state = state["wayfair"]
        selected = next(row for row in wayfair_state["shipments"] if row["id"] == shipment)
        prior = next(row for row in wayfair_state["deliveryAppointments"] if row["shipmentId"] == shipment)
        offered = next(row for row in selected["availableSlots"] if row["id"] == f"{shipment}-{window}")
        new_id = f"appt-fixture-{shipment}"
        prior.update(status="rescheduled", updatedAt=NOW, updatedBy="avery-quinn", replacedByAppointmentId=new_id)
        wayfair_state["deliveryAppointments"].append(dict(
            id=new_id, orderId=selected["orderId"], shipmentId=shipment, slotId=offered["id"],
            startAt=offered["startAt"], endAt=offered["endAt"], timeZone=ZONE,
            instructions=driver, status="confirmed", actorId="avery-quinn", createdAt=NOW,
            previousAppointmentId=prior["id"],
        ))

    asana_state = state["asana"]
    task = next(row for row in asana_state["tasks"] if row["taskId"] == TASK)
    if date is not None:
        task.update(dueDate=date, modifiedDate=NOW)
    if notes:
        task.update(description=BASE_NOTES + "\n\n" + notes, modifiedDate=NOW)
    if attach and route:
        ident = "attachment-fixture"
        stored = "f1e17010_" + OUTPUT
        blob = directory / "files" / "asana" / "fixture" / stored
        blob.parent.mkdir(parents=True)
        shutil.copyfile(output / OUTPUT, blob)
        asana_state["attachments"].append(dict(
            attachmentId=ident, taskId=TASK, fileName=OUTPUT, fileType="application/octet-stream",
            fileSize=blob.stat().st_size, fileUrl=f"/files/fixture/{stored}", uploaderId="avery", uploadDate=NOW,
        ))
        task.update(attachmentIds=[ident], modifiedDate=NOW)
    if reply:
        state["microsoft_teams"]["messages"][CHANNEL].append(
            message("fixture-reply", "avery", reply, NOW, parent=thread)
        )
    for key, value in state.items():
        dump(directory / "state" / key / "initial.json", initial[key])
        dump(directory / "state" / key / "current.json", value)
    return state


def main(root):
    write_drawing(root / "input" / INPUT, NORTH)
    initial = dict(wayfair=wayfair(), asana=asana(), microsoft_teams=teams())
    for key, value in initial.items():
        dump(root / "seed" / f"{key}.json", value)
    blank = dict(booking=False, route=None, date=None, notes=None, attach=False, reply=None)
    fixture_options = {
        "golden": {},
        "nop": blank,
        "bypass": {**blank, "route": NORTH, "date": "2026-11-25", "reply": "The installation date has been updated."},
        "one_core": {**blank, "booking": True},
        "false_completion": {**blank, "reply": "This is done."},
        "wrong_shipment": dict(shipment=SIDE_SHIPMENT),
        "wrong_window": dict(window="tue-am"),
        "stale_driver": dict(driver="Use North Gate and Gallery Hall."),
        "stale_carry_route": dict(route=NORTH),
        "deleted_floor_detail": dict(retain_plan=False),
        "wrong_install_date": dict(date="2026-11-24"),
        "wrong_reply_thread": dict(thread="chair-thread"),
        "delivery_and_route": {**blank, "booking": True, "route": SOUTH},
        "route_and_asana": dict(booking=False, reply=None),
        "equivalent": dict(
            equivalent=True,
            driver="Check in at Receiving. South Gate to Service Hall, then Freight Lift and Room 103. Do not tip the crate.",
            notes="WF-9400461 sideboard arrives 11/24/26, 12:00–16:00 Eastern. From South Gate, check in at Receiving and carry upright through Service Hall and the Freight Lift into Reading Room 103.",
            reply="Booked Nov. 24, 12–4 p.m. ET via South Gate. For the editable Maple-Reading-Room-Delivery.drawio, look in Asana, Maple House Fit-out, under Install long sideboard — Reading Room 103.",
        ),
    }
    for name, options in fixture_options.items():
        directory = root / "variants" / name
        current = make_fixture(directory, initial, **options)
        if name == "golden":
            for key, value in current.items():
                dump(root / "golden" / f"{key}.json", value)
            shutil.copytree(directory / "output", root / "golden_output")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

