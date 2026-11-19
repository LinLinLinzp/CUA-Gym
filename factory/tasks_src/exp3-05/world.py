#!/usr/bin/env python3
"""Generate the Portland case and replay mock mutations into offline fixtures."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "factory"))
from worldkit import avatar, file_url

SITES = ("netsuite", "yahoo_mail", "mattermost")
NOW = "2026-11-18T19:30:00.000Z"
PO = "po_4582"
ROOT_POST = "post-portland-l6712"
CHANNEL = "ch-portland-receiving"
CLERK = "usr-alex-morgan"
PEOPLE = {
    "usr-marisol-vega": ("Marisol", "Vega", "Receiving Supervisor"),
    "usr-devon-park": ("Devon", "Park", "Dock Shift Lead"),
    "usr-stella-ortiz": ("Stella", "Ortiz", "Inbound Coordinator"),
    "usr-jules-raman": ("Jules", "Raman", "Accounts Payable Lead"),
}

# Use the checked-in application seed builders for complete baseline arrays and
# the same transaction functions as the forms for derived fields and audit rows.
def run_js(source, payload=None):
    return json.loads(subprocess.check_output(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT / "hub" / "websites", text=True, input=json.dumps(payload),
    ))


def timestamp(hour, minute=0):
    return f"2026-11-18T{hour:02}:{minute:02}:00.000Z"


def portland_post(id_, user, message, time, root=None):
    return dict(id=id_, channelId=CHANNEL, userId=user, rootId=root, message=message,
                fileIds=[], mentionedUserIds=[], isPinned=False, editedAt=None, deletedAt=None,
                deletedBy=None, createdAt=time, updatedAt=time)


def setup_chat(chat, assets):
    base = "2026-11-12T16:00:00.000Z"
    chat["channels"].append(dict(
        id=CHANNEL, teamId=chat["currentTeamId"], name="portland-receiving",
        displayName="Portland Receiving", type="O", purpose="Portland inbound dock exceptions",
        header="Receiving handoffs and signed counts", status="active", isDefault=False,
        createdBy="usr-marisol-vega", archivedBy=None, archivedAt=None,
        createdAt=base, updatedAt=base,
    ))
    for user, (first, last, role) in PEOPLE.items():
        handle = f"{first}.{last}".lower()
        chat["users"].append(dict(id=user, username=handle, firstName=first, lastName=last,
                                  email=f"{handle}@acme.example", position=role,
                                  status="active", presence="online", isGuest=False,
                                  createdAt=base, updatedAt=base))
        chat["teamMembers"].append(dict(id=f"portland-team-{user}", teamId=chat["currentTeamId"],
                                       userId=user, role="team_user", status="active",
                                       createdAt=base, updatedAt=base))
    for user in (CLERK, *PEOPLE):
        chat["channelMembers"].append(dict(
            id=f"portland-member-{user}", channelId=CHANNEL, userId=user, role="channel_user",
            status="active", addedBy="usr-marisol-vega", joinedAt=base, leftAt=None,
            isFavorite=False, muted=False, lastViewedAt=None, lastReadPostId=None,
            createdAt=base, updatedAt=base,
        ))
    assets.mkdir(parents=True, exist_ok=True)
    for collection, field in (("users", "avatarUrl"), ("teams", "iconUrl")):
        for record in chat[collection]:
            name = (f"{record['firstName']} {record['lastName']}" if collection == "users"
                    else record["displayName"])
            filename = f"{record['id']}.svg"
            (assets / filename).write_text(unquote(avatar(name).split(",", 1)[1]))
            record[field] = file_url(filename)
    chat["posts"].extend([
        portland_post("post-portland-l6702", "usr-stella-ortiz",
                      "Summit SPT-L6702 / PO4583 goes to Reno. Portland has no receipt action on that load.",
                      timestamp(16, 5)),
        portland_post(ROOT_POST, "usr-marisol-vega",
                      "PO4582 / Summit Power Transmission / SPT-L6712 at Portland, door 4. "
                      "Alex, please close out today's receiving handoff and log the match here. "
                      "The Nov 12 load SPT-L6680 belongs to a separate AP case.",
                      timestamp(16, 15)),
        portland_post("post-l6712-staging", "usr-stella-ortiz",
                      "Inbound manifest tallied against the labels at staging: 14 BLT-5VX800, "
                      "3 SPR-40B18, 5 boxes CHN-40-10. Carrier handoff closed at door 4; "
                      "these are the quantities in my inbound sheet.",
                      timestamp(16, 40), ROOT_POST),
        portland_post("post-l6712-signed", "usr-devon-park",
                      "Signed dock acceptance / SPT-L6712 / Devon Park, Portland shift lead, "
                      "Nov 18 09:05 PST. Counted and released for put-away: BLT-5VX800 11 ea, "
                      "SPR-40B18 0 ea, CHN-40-10 5 boxes. Three sprockets were in the damaged carton "
                      "refused at the door. Belt bundle label said 14; the open count was 11.",
                      timestamp(17, 5), ROOT_POST),
        portland_post("post-l6712-ap", "usr-jules-raman",
                      "AP exception AP-2718: you can enter the matched portion of the issued invoice "
                      "and leave the balance disputed. SPT-L6680's receipt includes two belts that "
                      "remain unbilled under AP-2691. Keep that prior lot out of this invoice. "
                      "Anything past approved PO capacity stays off the receipt while Purchasing reviews it.",
                      timestamp(18, 55), ROOT_POST),
    ])
    root_posts = [p for p in chat["posts"] if p["rootId"] == ROOT_POST]
    chat["threads"].append(dict(id=ROOT_POST, rootPostId=ROOT_POST, channelId=CHANNEL,
                                replyCount=len(root_posts), lastReplyAt=root_posts[-1]["createdAt"],
                                participantIds=["usr-marisol-vega", *[p["userId"] for p in root_posts]],
                                createdAt=timestamp(16, 15), updatedAt=root_posts[-1]["createdAt"]))


def setup_mail(mail):
    vendor = {"name": "Tessa Nouri · Summit Power Transmission", "email": "billing@summit-power.example"}
    inbox = {"name": "Alex Morgan", "email": "alex.portlandreceiving@yahoo.com"}
    mail["currentUser"].update(name=inbox["name"], firstName="Alex", email=inbox["email"],
                               aliases=[], jobTitle="Receiving Clerk", company="Cascade Industrial Supply",
                               location="Portland, OR")
    mail["settings"]["writing"].update(defaultFrom=inbox["email"], signature={"enabled": False, "text": ""})
    mail["settings"]["viewing"]["markAsRead"] = "never"
    mail["messages"] = [m for m in mail["messages"] if m["folderId"] == "inbox"]
    for i, m in enumerate(mail["messages"]):
        # Keep a plausible amount of inbox noise using actual open PO references.
        number = 4501 + i % 26
        subject, body = [
            ("Carrier appointment confirmation", "The carrier confirmed the booked dock slot. Check the appointment board for the door assignment."),
            ("Packing paperwork filed", "Packing paperwork is filed with the carrier reference. The receiving team has the original."),
            ("Dispatch status update", "The order is in the dispatch queue. We will send a shipment reference once the trailer is sealed."),
            ("Receiving queue update", "This purchase order is assigned to the regular inbound queue. No exception handoff was requested."),
        ][i % 4]
        day = 17 - i // 4
        date = f"2026-11-{day:02}T18:{i % 60:02}:00.000Z"
        m.update(conversationId=f"receiving-noise-{i}", category="primary", cc=[], to=[inbox],
                 subject=f"{subject} / PO{number}", body=body, snippet=body,
                 summary=None, attachments=[], orderInfo=None, travelInfo=None, isRead=True,
                 isStarred=False, replyTo=None, listUnsubscribe=False, date=date, createdAt=date)
        m["from"] = {"name": "Inbound Dispatch", "email": "dispatch@freightdesk.example"}
    subject = "Summit / PO4582 / SPT-L6712"
    papers = [
        ("summit-ack", "2026-11-10T18:15:00.000Z", subject,
         "Order acknowledgment ACK-4582-A. Purchasing copy, Rev A: BLT-5VX800 22 ea at $38.20, "
         "SPR-40B18 12 ea at $27.40, CHN-40-10 10 boxes at $54.00. "
         "Our warehouse printed pick labels against this acknowledgment."),
        ("summit-prebill", timestamp(16, 25), "Re: " + subject,
         "Commercial prebill PB-97641 / PO4582 / SPT-L6712. Dispatch estimate for document review: "
         "14 BLT-5VX800 at $38.20, 3 SPR-40B18 at $27.40 and 5 boxes CHN-40-10 at $54.00. "
         "Estimated total $887.00. This copy is from the dispatch billing queue."),
        ("summit-invoice", timestamp(18, 20), "Re: " + subject,
         "SUMMIT POWER TRANSMISSION | ISSUED INVOICE SPT-97641\n"
         "PO4582 · Portland · shipment SPT-L6712\n"
         "Invoice date Nov 18, 2026 · Due Dec 18, 2026\n"
         "BLT-5VX800 | 14 ea | $38.20 | $534.80\n"
         "SPR-40B18 | 3 ea | $27.40 | $82.20\n"
         "CHN-40-10 | 4 boxes | $54.00 | $216.00\n"
         "USD $833.00 due. One chain box was supplied for inspection and is excluded from this invoice. "
         "This is the issued AR copy. No freight or tax is charged."),
        ("summit-near-load", timestamp(18, 27), "Summit invoice SPT-97614 / PO4583 / SPT-L6702",
         "Reno replenishment invoice, SPT-L6702. BLT-5VX800 11 ea, SPR-40B18 3 ea, "
         "CHN-40-10 4 boxes. This load is for Reno, PO4583."),
    ]
    for index, (id_, date, title, body) in enumerate(papers):
        mail["messages"].append(dict(
            id=id_, conversationId="summit-l6712" if index < 3 else "summit-l6702",
            folderId="inbox", category="primary", status="received", isDraft=False,
            isRead=True, isStarred=False, subject=title, body=body, snippet=body[:140],
            to=[inbox], cc=[], bcc=[], attachments=[], createdAt=date, date=date,
            inReplyToId="summit-ack" if index in (1, 2) else None, **{"from": vendor},
        ))


def seed(out):
    states = run_js("""
        import { createInitialData as ns } from './netsuite_mock/src/data/seed.js';
        import { createInitialData as ym } from './yahoo_mail_mock/src/data/seed.js';
        import { createInitialData as mm } from './mattermost_mock/src/data/seed.js';
        console.log(JSON.stringify({netsuite: ns(), yahoo_mail: ym(), mattermost: mm()}));
    """)
    setup_chat(states["mattermost"], out / "seed" / "files" / "mattermost")
    setup_mail(states["yahoo_mail"])
    ns = states["netsuite"]
    clerk_email = "alex.morgan@cascadeindustrial.com"
    ns["currentUser"].update(employeeId="emp_111", name="Alex Morgan", initials="AM",
                             email=clerk_email, role="Receiving Clerk")
    ns["employees"].append(dict(id="emp_111", internalId=111, entityId="E111", name="Alex Morgan",
                                firstName="Alex", lastName="Morgan", email=clerk_email,
                                title="Receiving Clerk", departmentId="dept_2", supervisorId="emp_106",
                                phone="(503) 555-0111", isSalesRep=False, isBuyer=False, inactive=False))
    source = next(o for o in ns["purchaseOrders"] if o["id"] == "po_4517")
    order = deepcopy(source)
    order.update(id=PO, internalId=4582, tranId="PO4582", tranDate="2026-11-10",
                 postingPeriod="Nov 2026", status="Pending Billing/Partially Received",
                 createdAt="2026-11-10T19:00:00.000Z",
                 approvedAt="2026-11-16T19:10:00.000Z", dueDate="2026-11-18",
                 lastModifiedAt="2026-11-16T19:10:00.000Z",
                 memo="Approved Rev B (Nov 16) · Portland replenishment. Belt line reduced from 22 to 18.",
                 otherRefNum="ACK-4582-A")
    for line, qty, received, billed, rate in zip(
        order["lines"], [18, 12, 10], [8, 4, 0], [6, 4, 0], [38.20, 27.40, 54.00]
    ):
        line.update(quantity=qty, quantityReceived=received, quantityBilled=billed,
                    rate=rate, amount=round(qty * rate, 2), expectedReceiptDate="2026-11-18")
    order["subtotal"] = order["total"] = round(sum(line["amount"] for line in order["lines"]), 2)
    ns["purchaseOrders"].append(order)
    neighbor = deepcopy(order)
    neighbor.update(id="po_4583", internalId=4583, tranId="PO4583", status="Pending Receipt",
                    shipToLocationId="loc_2", locationId="loc_2",
                    memo="Reno replenishment · SPT-L6702", otherRefNum="ACK-4583")
    for line in neighbor["lines"]:
        line.update(quantityReceived=0, quantityBilled=0)
    ns["purchaseOrders"].append(neighbor)
    for key, prefix, number, date, quantities in [
        ("itemReceipts", "ir", 3390, "2026-11-12", [8, 4]),
        ("vendorBills", "bill", 1190, "2026-11-13", [6, 4]),
    ]:
        row = deepcopy(ns[key][0])
        row.update(id=f"{prefix}_{number}", internalId=number, vendorId=order["vendorId"],
                   createdFromId=PO, createdFromType="purchaseOrder", locationId=order["locationId"],
                   postingPeriod="Nov 2026", tranDate=date, createdAt=f"{date}T19:00:00.000Z",
                   lastModifiedAt=f"{date}T19:00:00.000Z", lines=[],
                   memo="Earlier shipment SPT-L6680 · AP-2691")
        for line, quantity in zip(order["lines"], quantities):
            child = {k: line[k] for k in ("lineId", "line", "itemId", "description", "units", "rate")}
            child.update(orderLineId=line["lineId"], quantity=quantity, amount=round(quantity * line["rate"], 2))
            if prefix == "ir":
                child["locationId"] = order["locationId"]
            row["lines"].append(child)
        row["total"] = round(sum(line["amount"] for line in row["lines"]), 2)
        if prefix == "ir":
            row.update(tranId="IR3390", status="Received")
        else:
            row.update(tranId="SPT-97582", transactionNumber="BILL1190", status="Open",
                       termsId=order["termsId"], dueDate="2026-12-13", amountPaid=0,
                       amountRemaining=row["total"], expenses=[])
        ns[key].append(row)
    # The opening stock includes the earlier linked receipt.
    for line in order["lines"][:2]:
        item = next(i for i in ns["items"] if i["id"] == line["itemId"])
        stock = next(s for s in item["locations"] if s["locationId"] == order["locationId"])
        stock["onHand"] += line["quantityReceived"]
    return states


REPLAY = """
    import fs from 'node:fs';
    import { conversionDraft, saveMovement } from './netsuite_mock/src/utils/conversions.js';
    import { saveOrder, orderDraft } from './netsuite_mock/src/utils/orders.js';
    import { sendPost } from './mattermost_mock/src/data/postActions.js';
    const {states, now, po, root, channel, variant} = JSON.parse(fs.readFileSync(0, 'utf8'));
    const RealDate = Date;
    globalThis.Date = class extends RealDate {
      constructor(...args) { super(...(args.length ? args : [now])); }
      static now() { return RealDate.parse(now); }
    };
    let sequence = 0;
    Object.defineProperty(globalThis, 'crypto', {value: {randomUUID: () => 'fixture-' + ++sequence}});
    let ns = states.netsuite;
    const naive = variant === 'naive';
    const revision = naive || variant === 'slip_revision';
    const dock = naive || variant === 'slip_dock';
    const invoice = naive || variant === 'slip_invoice';
    const prior = naive || variant === 'slip_prior_lot';
    const order = () => ns.purchaseOrders.find(row => row.id === po);
    if (revision) {
      const draft = orderDraft(ns, 'purchord', order());
      draft.lines = draft.lines.map((line, i) => i ? line : {...line, quantity: 22});
      ns = saveOrder(ns, 'purchord', draft, po).state;
    }
    const belt = revision ? (naive ? 14 : 11) : 10;
    const sprocket = dock ? 3 : 0;
    const receiptQty = [belt, sprocket, 5];
    const billQty = [belt + (prior ? 2 : 0), sprocket, invoice ? 5 : 4];
    const reference = naive ? 'PB-97641' : 'SPT-97641';
    function post(code, quantities, fields) {
      const draft = conversionDraft(ns, code, order());
      Object.assign(draft, fields);
      draft.lines = draft.lines.map(row => {
        const i = order().lines.findIndex(line => line.lineId === row.orderLineId);
        return {...row, selected: quantities[i] > 0, quantity: quantities[i]};
      });
      const saved = saveMovement(ns, code, po, draft);
      ns = saved.state;
      return saved.record;
    }
    const receipt = post('itemrcpt', receiptQty, {tranDate:'2026-11-18'});
    const bill = post('vendbill', billQty, {tranId:reference, tranDate:'2026-11-18', dueDate:'2026-12-18'});
    states.netsuite = ns;
    const approved = revision ? 22 : 18;
    const accepted = naive ? '14 / 3 / 5' : dock ? '11 / 3 / 5' : '11 / 0 / 5';
    const claimed = invoice ? '14 / 3 / 5' : '14 / 3 / 4';
    const invoiceTotal = invoice ? 887 : 833;
    const heldBelts = 14 - billQty[0];
    const heldSprockets = 3 - billQty[1];
    const message = [
      `PO4582 / SPT-L6712 · receipt ${receipt.tranId} · bill ${bill.transactionNumber} / ${reference}.`,
      `In SKU order BLT-5VX800 / SPR-40B18 / CHN-40-10: PO Rev ${revision ? 'A' : 'B'} authorized ${approved} / 12 / 10, ${approved - 8} / 8 / 10 open before this receipt. Dock accepted ${accepted}; invoice claimed ${claimed}.`,
      `Received ${receiptQty.join(' / ')} and billed ${billQty.join(' / ')}. Posted $${bill.total.toFixed(2)} open; disputed $${(invoiceTotal - bill.total).toFixed(2)} (${heldBelts} belts and ${heldSprockets} sprockets).`,
      revision ? 'The received belts fit Rev A.' : 'One excess belt was held off inventory because it exceeds Rev B capacity.',
      dock ? 'Sprockets entered stock from the manifest.' : 'We refused 3 sprockets because the carton was damaged.',
      invoice ? 'All five chain boxes were billed.' : 'One received chain box remains unbilled because the issued invoice claims four.',
      prior ? 'Rolled the two AP-2691 belts into this bill.' : 'Two belts from the earlier load SPT-L6680 remain unbilled under AP-2691.',
    ].join(' ');
    states.mattermost = sendPost(states.mattermost, channel, root, {message}, now);
    console.log(JSON.stringify(states));
"""


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main(out):
    initial = seed(out)
    variants = ("golden", "nop", "naive", "slip_revision", "slip_dock", "slip_invoice", "slip_prior_lot")
    for site in SITES:
        write(out / "seed" / f"{site}.json", initial[site])
    for variant in variants:
        current = initial if variant == "nop" else run_js(REPLAY, dict(
            states=initial, now=NOW, po=PO, root=ROOT_POST, channel=CHANNEL, variant=variant,
        ))
        folder = out / "variants" / variant
        (folder / "output").mkdir(parents=True, exist_ok=True)
        for site in SITES:
            if variant == "golden":
                write(out / "golden" / f"{site}.json", current[site])
            paths = folder / "state" / site
            write(paths / "initial.json", initial[site])
            write(paths / "current.json", current[site])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
