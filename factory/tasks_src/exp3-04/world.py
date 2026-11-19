#!/usr/bin/env python3
"""Deterministic October renewal true-up world and verifier fixtures."""

import copy
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

STAMP = "2026-11-18T17:30:00.000Z"
CREATED = "2026-10-28T17:00:00.000Z"
EXCEL = "microsoft_excel_for_the_web"
BOOK = "wb-oct-close"
MAYA = "usr_maya"
OWNER = "user-maya"
CLIENT = "cli_cedarline"
NAMES = [
    "Alder Finch Studio", "Brightwater Produce", "Cedarline Foodservice",
    "Driftwood Packaging", "Elm Basin Coffee", "Fable Orchard", "Granite Mill Bakery",
    "Hawthorn Dairy", "Ironwood Grains", "Juniper Pantry", "Kestrel Cider",
    "Lakeview Kitchens", "Marsh & Pine", "Northbank Roasters", "Olive Yard",
    "Palisade Grocers", "Quarry Hill Catering", "Red Fern Farms", "Sable Vinegar",
    "Tern Specialty Foods", "Union Spice", "Vale Cold Storage", "Willowbrook Market",
    "Yarrow Provisioners",
]
PERIODS = ("CF-2026-10A", "CF-2026-10B")
HEADERS = ["Entry ID", "Work date (PT)", "Client", "Period ID", "Minutes", "Approval", "Queue", "Draft Invoice"]
LATE = [
    ["CF-781", "2026-10-07", "Cedarline Foods", PERIODS[0], 73, "Approved", "Late"],
    ["CF-782", "2026-10-15", "Cedarline Foods", PERIODS[0], 58, "Approved", "Late"],
    ["CF-782", "2026-10-15", "Cedarline Foods", PERIODS[0], 58, "Approved", "Late"],
    ["CF-790", "2026-10-16", "Cedarline Foods", PERIODS[1], 66, "Approved", "Late"],
    ["CF-793", "2026-10-23", "Cedarline Foods", PERIODS[1], 51, "Approved", "Late"],
    ["CF-795", "2026-10-25", "Cedarline Foods", PERIODS[1], 39, "Rejected", "Correction"],
    ["CF-763", "2026-10-04", "Cedarline Foods", PERIODS[0], 27, "Approved", "Posted", "INV-2080"],
    ["CFS-781", "2026-10-07", "Cedarline Foodservice", "CFS-2026-10", 73, "Approved", "Late"],
    ["CF-805", "2026-11-01", "Cedarline Foods", "CF-2026-11", 62, "Approved", "Late"],
]


def audit(actor, date=CREATED):
    return dict(createdAt=date, updatedAt=date, createdBy=actor, updatedBy=actor)


def rec(id_, **fields):
    return dict(id=id_, **audit(MAYA), **fields)


def invoice(id_, number, client, ref, description, amount, *, draft=False):
    issue = "2026-11-18" if draft else "2026-10-28"
    date = STAMP if draft else CREATED
    return dict(
        id=id_, **audit(MAYA, date), invoiceNumber=number, clientId=client,
        projectId=None, reference=ref, kind="standard", issueDate=issue,
        dueDate="2026-12-18" if draft else "2026-11-27", currency="USD",
        lines=[dict(id=f"line-{id_}", kind="manual", serviceId=None,
                    name=description, description="", quantity=1, rate=amount,
                    taxPercent=0, lineSubtotal=amount, sources=[])],
        notes="", terms="", discountPercent=0, subtotal=amount, discountAmount=0,
        taxAmount=0, total=amount, amountPaid=0, amountDue=amount,
        status="draft" if draft else "sent", visibility="active",
        sentAt=None if draft else date, retainerId=None, retainerPeriodStart=None,
    )


def freshbooks():
    def client(id_, name):
        return rec(id_, name=name, email=f"ap@{name.lower().replace(' ', '')}.example",
                   currency="USD", billingAddress={}, visibility="active", contacts=[])

    clients = [client(CLIENT, "Cedarline Foods")]
    invoices = [
        invoice("inv_prior_a", "INV-2080", CLIENT, PERIODS[0], "October provisional overage", 36.47),
        invoice("inv_prior_b", "INV-2081", CLIENT, PERIODS[1], "October provisional overage", 28.63),
        invoice("inv_fee", "INV-2082", CLIENT, PERIODS[0], "October base retainer fee", 1275),
        invoice("inv_other_month", "INV-2083", CLIENT, "CF-2026-09", "September overage", 82.16),
    ]
    for i, name in enumerate(NAMES):
        id_ = f"cli_{i}"
        clients.append(client(id_, name))
        ref = PERIODS[0] if name == "Cedarline Foodservice" else f"OCT-{300+i}"
        invoices.append(invoice(f"inv_{i}", f"INV-{2050+i}", id_, ref, "October advisory", 285 + i * 17))
    return dict(
        business=dict(id="biz_birch_vale", name="Birch & Vale Consulting",
                      email="billing@birchvale.example", currency="USD", netDays=30,
                      address=dict(street="42 Beacon Street", city="Boston", region="MA",
                                   postalCode="02108", country="US")),
        currentUserId=MAYA, users=[rec(MAYA, name="Maya Chen", email="maya@birchvale.example", role="owner")],
        clients=clients, invoices=invoices, projects=[], services=[], expenseCategories=[],
        payments=[], timeEntries=[], expenses=[], retainers=[], retainerPeriods=[],
        activeTimer=None, activityEvents=[],
    )


def cell(sheet, row, column, value, date=CREATED):
    address = f"{chr(64 + column)}{row}"
    value_type = "string" if isinstance(value, str) else "number"
    if value_type == "string" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value_type = "date"
    return dict(id=f"cell-{sheet}-{address}", **audit(OWNER, date), workbookId=BOOK,
                sheetId=sheet, row=row, column=column, address=address, input=str(value),
                formula=None, value=value, valueType=value_type,
                error=None, dependencies=[])


def excel():
    state = {name: [] for name in (
        "tables", "filters", "sorts", "shares", "shareLinks", "comments", "charts",
        "conditionalFormats", "validationRules", "operations",
    )}
    state.update(
        schemaVersion=1, currentUserId=OWNER, preferences=dict(ribbonMode="classic", zoom=100),
        users=[dict(id=OWNER, displayName="Maya Chen", email="maya@birchvale.example",
                    initials="MC", avatarColor="#29584A")],
        workbooks=[dict(id=BOOK, **audit(OWNER), name="October Retainer Close", ownerId=OWNER,
                        location="OneDrive / Documents / Finance", status="active", favoriteUserIds=[],
                        activeSheetId="closeout", lastOpenedAt=None)],
        sheets=[], cells=[],
    )
    late_noise = [[f"OPS-{500+i}", f"2026-10-{i+2:02}", name, f"OCT-{300+i}",
                   23 + i * 3, "Pending" if i % 4 == 0 else "Approved", "Late"]
                  for i, name in enumerate(NAMES) if i != 2]
    closeout = [
        ["Period ID", "Service dates (PT)", "Posted minutes", "Allowance minutes",
         "Excess minutes", "Gross overage", "Prior overage", "Net due", "Draft Invoice"],
        [PERIODS[0], "Oct 1–15, 2026", 278],
        [PERIODS[1], "Oct 16–31, 2026", 365],
    ]
    for pos, (id_, name, widths, rows) in enumerate([
        ("closeout", "Closeout", [126, 146, 106, 134, 105, 120, 104, 92, 122], closeout),
        ("late-time", "Late Time", [95, 118, 164, 130, 72, 97, 98, 130], [HEADERS, *LATE, *late_noise]),
    ]):
        state["sheets"].append(dict(id=id_, **audit(OWNER), workbookId=BOOK, name=name, position=pos,
                                    status="active", visibility="visible", tabColor=None, autoFilterRange=None,
                                    frozenRows=1, frozenColumns=0,
                                    columnWidths={str(i): w for i, w in enumerate(widths, 1)}))
        for row, values in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                state["cells"].append(cell(id_, row, col, value))
    return state


def yahoo():
    me = dict(name="Maya Chen", email="maya.birchvale@yahoo.com")
    state = {name: [] for name in ("folders", "messages", "contacts", "contactLists",
                                   "filters", "blockedAddresses", "unsubscribes", "activityLog")}
    state["currentUser"] = dict(id=MAYA, **me, firstName="Maya", aliases=[],
                                avatarColor="#29584A", company="Birch & Vale Consulting",
                                jobTitle="Billing Lead", location="Boston, MA",
                                storage=dict(usedBytes=0, totalBytes=1000000000))
    state["settings"] = dict(
        appearance=dict(theme="light", themeColor="purple", density="comfortable", messageLayout="list"),
        inbox=dict(categoriesEnabled=True, defaultCategory="primary", showUnreadCount=True, sort="date_desc"),
        viewing=dict(markAsRead="never", conversations=True, showImages="ask", afterMove="next"),
        writing=dict(signature=dict(enabled=False, text=""), defaultFont="sans-serif",
                     defaultFontSize="medium", defaultFrom=me["email"], sendWithCtrlEnter=True, linkPreviews=True),
        vacationResponse=dict(enabled=False, startDate="", endDate="", subject="", message="",
                              onlyContacts=False, updatedAt=None),
        notifications=dict(browser=False, sound=False), ai=dict(messageSummaries=True),
        keyboardShortcuts=True, rightPanel=dict(open=True, tab="starred"),
        sidebar=dict(compact=False, viewsExpanded=True, foldersExpanded=True, moreExpanded=False),
    )
    for i, folder in enumerate(["inbox", "draft", "sent", "archive", "spam", "trash"]):
        state["folders"].append(dict(id=folder, name=folder.title(), type="system",
                                     parentId=None, order=i, createdAt=CREATED))

    def mail(id_, sender, email, subject, body, date):
        state["messages"].append(dict(
            id=id_, conversationId=f"conv-{id_}", folderId="inbox", category="primary",
            status="received", isDraft=False, isRead=True, isStarred=False,
            **{"from": dict(name=sender, email=email)}, to=[me], cc=[], bcc=[], subject=subject,
            body=body, snippet=body[:125], attachments=[], date=date, createdAt=date,
        ))

    mail("agreement", "Nina Patel", "nina@cedarlinefoods.example", "Cedarline Foods | executed retainer agreement",
         """Maya,

Here is the executed billing language for Cedarline Foods. The original plan includes 600 minutes per full calendar month. When the plan changes mid-month, each plan's allowance is its full-month minutes times the plan's active calendar days divided by the number of days in that month. Round each allowance down to a whole minute. Allowances do not carry across the renewal. Use Pacific work dates, counting the effective date entirely under the new plan.

For each service period, add posted time and distinct approved late time, then subtract the prorated included minutes, with a floor of zero. October Retainer Close's posted totals already include rows marked Posted. For duplicate export rows with the same Entry ID, use the first occurrence only. Rejected corrections are excluded.

The original plan charges the first 45 excess minutes at USD 137.34/hour and all additional excess minutes at USD 174.85/hour. Tiers apply separately to each service period, on all excess time. Price actual minutes at the hourly rate divided by 60. Round the combined gross overage once to cents, half up, then deduct any already-issued provisional overage for the same client and Period ID. Base retainers and invoices from other periods are excluded from that deduction. Draft only the remaining USD balance, with no tax or discount.

Nina
Cedarline Foods Finance""", "2026-09-25T18:00:00.000Z")
    mail("renewal-estimate", "Nina Patel", "nina@cedarlinefoods.example", "Cedarline Foods | renewal estimate for review",
         "For budgeting only: the draft proposes an October 15 change, 720 included minutes per full month and a flat USD 160/hour overage. Signature is still pending.",
         "2026-10-12T16:00:00.000Z")
    mail("signed", "Nina Patel", "nina@cedarlinefoods.example", "Cedarline Foods | signed renewal amendment",
         """Maya,

The signed amendment replaces the October 12 estimate. The renewal takes effect October 16, 2026 Pacific time. The new plan includes 735 minutes per full calendar month. The first 50 excess minutes are USD 154.25/hour and every excess minute after that is USD 193.65/hour. Keep the original agreement's proration, tier calculation, rounding and deduction rules. The original plan governs October 1–15. October 16–31 uses the signed renewal terms.

Countersigned October 14 by Nina Patel and Maya Chen.""",
         "2026-10-14T21:00:00.000Z")
    for i, name in enumerate(NAMES):
        mail(f"handoff-{i}", f"{name} Operations", f"ops{i}@example.com",
             f"{name} | October service close",
             f"October time approvals for {name} are in the shared tracker. Our next check-in is already on the calendar.",
             f"2026-11-{2+i%14:02}T17:00:00.000Z")
    return state


def money(value):
    return value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def calculate(index, mode):
    full, days, posted, late, tier, low, high, prior = [
        (600, 15, 278, 131, 45, "137.34", "174.85", "36.47"),
        (735, 16, 365, 117, 50, "154.25", "193.65", "28.63"),
    ][index]
    allowance = full * days // 31
    if mode == "slip_duplicate" and index == 0:
        late += 58
    if mode == "naive":
        # Uses the unsigned estimate and counts duplicate, posted, rejected, and
        # near-name rows. October 15 entries are assigned to the new plan.
        allowance = (600 * 14 // 31, 720 * 17 // 31)[index]
        late = (73 + 27 + 73, 58 + 58 + 66 + 51 + 39)[index]
        if index == 1:
            low = high = "160"
        prior = "0"
    excess = max(0, posted + late - allowance)
    first = Decimal(low) * min(tier, excess) / 60
    rest = Decimal(high) * max(0, excess - tier) / 60
    gross = money(first) + money(rest) if mode in ("slip_rounding", "naive") else money(first + rest)
    credit = Decimal(prior)
    return allowance, excess, float(gross), float(credit), float(gross - credit)


def completed(seed, mode):
    state = copy.deepcopy(seed)
    fresh, sheet = state["freshbooks"], state[EXCEL]

    sheet["workbooks"][0]["lastOpenedAt"] = STAMP
    sheet["operations"].append(dict(
        id="op-open", type="workbook.open", actorId=OWNER, createdAt=STAMP,
        workbookId=BOOK, sheetId=None, targetIds=[BOOK],
        details=dict(before=None, lastOpenedAt=STAMP),
    ))

    def put(tab, row, column, value):
        entry = cell(tab, row, column, value, STAMP)
        key = entry["address"]
        existing = next((c for c in sheet["cells"] if c["id"] == entry["id"]), None)
        before = dict(input=existing["input"] if existing else "", format=None)
        if existing:
            entry["createdAt"] = existing["createdAt"]
            existing.update(entry)
        else:
            sheet["cells"].append(entry)
        change = dict(id=entry["id"], address=key, before=before,
                      after=dict(input=entry["input"], format=None))
        sheet["operations"].append(dict(
            id=f"op-{tab}-{key}", type="cell.edit", actorId=OWNER, createdAt=STAMP,
            workbookId=BOOK, sheetId=tab, targetIds=[entry["id"]],
            details=dict(range=key, changes=[change], recalculatedCellIds=[entry["id"]]),
        ))

    for i, period in enumerate(PERIODS):
        fields = calculate(i, mode)
        number = f"INV-{2084+i}"
        draft = invoice(f"inv_trueup_{i}", number, CLIENT, period,
                        "October retainer overage true-up", fields[-1], draft=True)
        fresh["invoices"].append(draft)
        fresh["activityEvents"].append(dict(id=f"event_{i}", action="invoice.created", actorId=MAYA,
                                             createdAt=STAMP, entityType="invoice", entityId=draft["id"],
                                             relatedIds=[CLIENT]))
        for j, value in enumerate((*fields, number), 4):
            put("closeout", i+2, j, value)

    sheet["workbooks"][0]["activeSheetId"] = "late-time"
    sheet["operations"].append(dict(
        id="op-select-late-time", type="sheet.select", actorId=OWNER, createdAt=STAMP,
        workbookId=BOOK, sheetId="late-time", targetIds=["late-time"],
        details=dict(before="closeout", activeSheetId="late-time"),
    ))
    assignments = {2: 0, 3: 0, 5: 1, 6: 1}
    if mode == "slip_duplicate":
        assignments[4] = 0
    if mode == "naive":
        assignments = {2: 0, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 0, 9: 0}
    for row, period in assignments.items():
        number = f"INV-{2084+period}"
        put("late-time", row, 8, number)
    sheet["workbooks"][0].update(updatedAt=STAMP, updatedBy=OWNER)
    return state


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(out):
    seed = {"freshbooks": freshbooks(), EXCEL: excel(), "yahoo_mail": yahoo()}
    variants = {"nop": seed}
    for name in ("golden", "naive", "slip_duplicate", "slip_rounding"):
        variants[name] = completed(seed, name)
    for site, initial in seed.items():
        write(out / "seed" / f"{site}.json", initial)
        write(out / "golden" / f"{site}.json", variants["golden"][site])
        for name, states in variants.items():
            base = out / "variants" / name
            (base / "output").mkdir(parents=True, exist_ok=True)
            write(base / "state" / site / "initial.json", initial)
            write(base / "state" / site / "current.json", states[site])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
