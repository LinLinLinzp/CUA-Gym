"""Grade the PO4582 receiving and invoice reconciliation."""
import re
from decimal import Decimal, InvalidOperation

from cuaverify import InfraError, load_site, new_items, plain, run

TASK_ID = "cua-hard/summit-dock-reconciliation"
VERSION = "0.1.2"
PO_ID = "po_4582"
SKUS = ("blt-5vx800", "spr-40b18", "chn-40-10")
PRODUCTS = (r"belts?", r"sprockets?", r"(?:chain(?:\s+boxes?)?|boxes?\s+of\s+chain)")
# PO4582 Rev B and its opening counters give authorized totals and capacity.
AUTHORIZED = (18, 12, 10)
CAPACITY = (10, 8, 10)
# Mattermost post-l6712-signed gives dock acceptance. Yahoo summit-invoice gives the claim.
ACCEPTED = (11, 0, 5)
CLAIMED = (14, 3, 4)
RECEIVED = tuple(map(min, CAPACITY, ACCEPTED))
BILLED = tuple(map(min, RECEIVED, CLAIMED))
# Issued invoice SPT-97641, dated Nov 18 and due Dec 18. At the PO rates,
# 10*38.20 + 4*54 = 598; 4*38.20 + 3*27.40 = 235 of the $833 claim.
INVOICE = "spt-97641"
DATE = "2026-11-18"
DUE = "2026-12-18"
POSTED, DISPUTED = 598, 235

TRANSACTIONS = (
    "purchaseOrders", "itemReceipts", "vendorBills", "vendorPayments",
    "inventoryAdjustments", "inventoryTransfers", "salesOrders",
    "itemFulfillments", "invoices", "customerPayments",
)


def records(state, field, key="id"):
    if not isinstance(state, dict) or not isinstance(state.get(field), list):
        raise InfraError(f"missing or malformed {field} collection")
    result = {}
    for row in state[field]:
        identity = row.get(key) if isinstance(row, dict) else None
        if not isinstance(identity, str) or not identity or identity in result:
            raise InfraError(f"missing, malformed, or duplicate {field}.{key}")
        result[identity] = row
    return result


def site_states(site):
    try:
        return load_site(site)
    except UnicodeError as exc:
        raise InfraError(f"cannot decode {site} state") from exc


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def money(value, expected):
    value = number(value)
    return value is not None and abs(value - expected) <= Decimal("0.005")


def same(value, expected):
    return isinstance(value, str) and value.strip().casefold() == expected.casefold()


def stock(state):
    result = {}
    for item_id, item in records(state, "items").items():
        for loc_id, row in records(item, "locations", "locationId").items():
            qty = number(row.get("onHand"))
            if qty is None:
                raise InfraError(f"invalid onHand for {item_id} at {loc_id}")
            result[item_id, loc_id] = qty
    return result


def linked(row, po):
    return bool(row) and all(
        same(row.get(key), expected)
        for key, expected in (
            ("createdFromId", PO_ID), ("createdFromType", "purchaseOrder"),
            ("vendorId", po["vendorId"]), ("locationId", po["locationId"]),
        )
    )


def child_lines(row, source):
    allowed = {line["itemId"]: line["lineId"] for line in source}
    lines = records(row, "lines", "lineId")
    result = {}
    for line in lines.values():
        item = line.get("itemId")
        if not isinstance(item, str) or item not in allowed or item in result:
            return {}
        if line.get("orderLineId") != allowed[item]:
            return {}
        result[item] = line
    return result


def matched_line(lines, source, quantity):
    line = lines.get(source["itemId"], {})
    rate = Decimal(str(source["rate"]))
    return (
        number(line.get("quantity")) == quantity
        and same(line.get("units"), source["units"])
        and money(line.get("rate"), rate)
        and money(line.get("amount"), quantity * rate)
    )


def po_preserved(before, after, source):
    if after is None:
        return False
    expected = {
        line["lineId"]: {
            **line,
            "quantityReceived": line["quantityReceived"] + RECEIVED[i],
            "quantityBilled": line["quantityBilled"] + BILLED[i],
        }
        for i, line in enumerate(source)
    }
    new_lines = records(after, "lines", "lineId")
    audit = {"lastModifiedAt", "lastModifiedById", "lines", "status"}
    return (
        same(after.get("status"), "Pending Billing/Partially Received")
        and new_lines == expected
        and {k: v for k, v in before.items() if k not in audit}
        == {k: v for k, v in after.items() if k not in audit}
    )


LABELS = {
    "authorized": r"(?:authori[sz](?:ed|ation)|approved|ordered|(?:po\s+)?capacity|(?:open|remaining)\s+(?:po\s+)?(?:qty|quantit(?:y|ies)|balance|capacity)|po\s+(?:remaining|qty|quantity)|remaining|rev(?:ision)?\.?\s*[-–]?\s*b)",
    "accepted": r"(?:signed(?:[- ]+for|\s+dock(?:\s+count)?)?|dock(?:\s+(?:acceptance|count))?|accept(?:ed|ance)|actual(?:\s+count)?)",
    "claimed": r"(?:(?:issued|formal|official)\s+invoice|invoice(?:\s+(?:claim(?:ed)?|qty|quantit(?:y|ies)))?|claimed|invoiced)",
}
LABEL = re.compile(r"\b(?:" + "|".join(f"(?P<{k}>{v})" for k, v in LABELS.items()) + r")\b")
SKU = re.compile(r"\b(?:" + "|".join(SKUS) + r")\b")
NUM = r"(?<![\w.$-])\d+(?:\.\d+)?(?!\w|[./-]\d)"
QTY = r"(?<![\w.$-])\d+(?:\.\d+)?(?!\w|\.\d)"
VECTOR = re.compile(rf"({QTY})\s*[/,|]\s*({QTY})\s*[/,|]\s*({QTY})\b(?![./-]\d)")


def message_text(raw):
    return plain(raw.replace("*", "").replace("`", ""))


def labeled_parts(text):
    tags = list(LABEL.finditer(text))
    for index, tag in enumerate(tags):
        end = tags[index + 1].start() if index + 1 < len(tags) else len(text)
        yield tag.lastgroup, text[tag.end():end]


def quantities(part, pattern):
    return tuple(Decimal(n) for n in re.findall(pattern, part))


def product_count(text, product, expected):
    return bool(re.search(count_pattern(expected, product), text))


def has_counts(raw, kind, expected):
    body = message_text(raw)
    for label, part in labeled_parts(body):
        if label != kind:
            continue
        # An ordered slash/comma vector, or a category followed by all three SKUs.
        for match in VECTOR.finditer(part):
            if match.start() < 70 and tuple(map(Decimal, match.groups())) == expected:
                return True
        if all(product_count(part, f"{sku}|{product}", value)
               for sku, product, value in zip(SKUS, PRODUCTS, expected)):
            return True

    # SKU-by-SKU prose, or a Markdown/plain table whose header defines the column.
    sku_rows = list(SKU.finditer(body))
    per_sku = {}
    for index, marker in enumerate(sku_rows):
        end = sku_rows[index + 1].start() if index + 1 < len(sku_rows) else len(body)
        values = per_sku.setdefault(marker.group(), set())
        for label, part in labeled_parts(body[marker.end():end]):
            if label == kind:
                nums = quantities(part, NUM)
                if nums:
                    values.add(nums[0])
    if all(per_sku.get(sku) == {value} for sku, value in zip(SKUS, expected)):
        return True

    column = None
    rows = {}
    order = ()
    for line in map(message_text, raw.splitlines()):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # Support a table with SKUs as columns as well as one with SKUs as rows.
        sku_cells = [SKU.search(cell) for cell in cells[1:]]
        if len(sku_cells) == 3 and all(sku_cells):
            order = tuple(match.group() for match in sku_cells)
        elif order and len(cells) == 4 and LABEL.search(cells[0]):
            if LABEL.search(cells[0]).lastgroup == kind:
                counts = dict(zip(order, (quantities(cell, NUM) for cell in cells[1:])))
                if all(counts.get(sku) == (value,) for sku, value in zip(SKUS, expected)):
                    return True
        if not SKU.search(cells[0]):
            headers = [set(tag.lastgroup for tag in LABEL.finditer(cell)) for cell in cells]
            columns = [i for i, tags in enumerate(headers) if kind in tags]
            if len(columns) == 1 and columns[0] > 0:
                column = columns[0]
                rows = {}
        elif column is not None and column < len(cells):
            nums = quantities(cells[column], NUM)
            rows[SKU.search(cells[0]).group()] = nums
            if all(rows.get(sku) == (value,) for sku, value in zip(SKUS, expected)):
                return True

    # A legend can define the order of compact per-SKU triplets.
    for legend in re.finditer(r"([^:;.!?\n]+)\s*:", raw.lower()):
        tags = [tag.lastgroup for tag in LABEL.finditer(message_text(legend.group(1)))]
        if len(tags) != 3 or set(tags) != set(LABELS):
            continue
        counts = {}
        for row in re.finditer(SKU.pattern + rf"\s*[:=–—]?\s*\(?{VECTOR.pattern}",
                               message_text(raw[legend.end():])):
            counts[SKU.search(row.group()).group()] = Decimal(row.group(tags.index(kind) + 1))
        if all(counts.get(sku) == value for sku, value in zip(SKUS, expected)):
            return True
    return False


def nearby(body, *patterns, span=115):
    """Find a short passage with each required concept in any order."""
    matches = [list(re.finditer(pattern, body)) for pattern in patterns]
    if not all(matches):
        return False
    for anchor in sorted((m for group in matches for m in group), key=lambda m: m.start()):
        if all(any(anchor.start() <= m.start() and m.end() <= anchor.start() + span
                   for m in group) for group in matches):
            return True
    return False


def in_statement(body, *patterns):
    """Keep quantities and disposition together instead of borrowing from the next sentence."""
    return any(nearby(part, *patterns) for part in re.split(r"[!?;]|\.(?=\s|$)", body))


AFFIRMED = r"\b(?<!not )(?<!never )(?<!no longer )"


def token(value):
    return rf"(?<![\w-]){re.escape(value)}(?![\w-])"


def count_pattern(value, product):
    words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    qty = rf"(?<![\w.$-]){value}(?:\.0+)?(?!\w|\.\d)"
    if value in words:
        qty = rf"(?:{qty}|\b{words[value]}\b)"
    unit = r"(?:ea|each|units?|pcs?|pieces?)"
    return (rf"(?:{qty}\s*(?:{unit}\s+)?(?:of\s+)?\b(?:{product})\b"
            rf"|\b(?:{product})\b\s*(?:[:=x]\s*|\(\s*|\s+){qty})")


def invoice_amounts(body):
    amount = r"(?<![\w.$-])(?:usd\s*)?\$?\s*(\d+(?:\.\d+)?)(?!\w|[.,/-]\d)(?:\s*usd)?"
    roles = re.compile(
        r"\b(?:(?P<posted>post(?:ed)?|billed|matched|entered|booked|open)"
        r"|(?P<disputed>disput\w*|contest\w*|challeng\w*))\b"
    )
    found = set()
    # Keep each monetary figure tied to its own label, including amount-first prose.
    label_to_amount = (r"\s*(?:(?:to|in)\s+netsuite\s*)?(?:(?:amount|balance|portion)\s*)?"
                       r"(?:(?:of|is|was|at|total(?:s|ing)?)\s*)?[:=–—-]?\s*")
    amount_to_label = r"\s*(?:(?:was|is|remains|to\s+be)\s+)?"
    for clause in re.split(r"[;!?]|\.(?=\s|$)", body):
        tags = list(roles.finditer(clause))
        for match in re.finditer(amount, clause):
            if not tags:
                continue
            for tag in tags:
                if tag.end() <= match.start():
                    linked_amount = re.fullmatch(label_to_amount, clause[tag.end():match.start()])
                else:
                    linked_amount = tag.start() >= match.end() and re.fullmatch(
                        amount_to_label, clause[match.end():tag.start()]
                    )
                expected = POSTED if tag.lastgroup == "posted" else DISPUTED
                if linked_amount and money(match.group(1), expected):
                    found.add(tag.lastgroup)
    return found == {"posted", "disputed"}


def evaluate(g):
    initial, current = site_states("netsuite")
    old_mm, new_mm = site_states("mattermost")
    for mail in site_states("yahoo_mail"):
        records(mail, "messages")

    before = {key: records(initial, key) for key in TRANSACTIONS}
    after = {key: records(current, key) for key in TRANSACTIONS}
    po = before["purchaseOrders"].get(PO_ID)
    if po is None or not all(po.get(k) for k in ("vendorId", "locationId", "termsId")):
        raise InfraError("initial PO4582 or its linkage fields are missing")
    source_rows = records(po, "lines", "lineId").values()
    by_sku = {str(line.get("vendorCode")).casefold(): line for line in source_rows}
    try:
        source = [by_sku[sku] for sku in SKUS]
        for line in source:
            if (not line["itemId"] or not line["units"] or number(line["rate"]) is None
                    or not all(type(line[key]) is int for key in ("quantityReceived", "quantityBilled"))):
                raise InfraError("invalid initial PO4582 line fields")
    except KeyError as exc:
        raise InfraError(f"missing initial PO4582 line data: {exc}") from exc

    receipts = new_items(before["itemReceipts"].values(), after["itemReceipts"].values())
    bills = new_items(before["vendorBills"].values(), after["vendorBills"].values())
    receipt = receipts[0] if len(receipts) == 1 else {}
    bill = bills[0] if len(bills) == 1 else {}
    r_lines = child_lines(receipt, source) if receipt else {}
    b_lines = child_lines(bill, source) if bill else {}
    r_link = linked(receipt, po) and same(receipt.get("tranDate"), DATE) and same(receipt.get("status"), "Received")
    b_link = linked(bill, po)
    r_belt = r_link and matched_line(r_lines, source[0], RECEIVED[0])
    r_chain = (r_link and len(r_lines) == 2 and source[1]["itemId"] not in r_lines
               and matched_line(r_lines, source[2], RECEIVED[2]))
    b_belt = b_link and matched_line(b_lines, source[0], BILLED[0])
    b_chain = (b_link and len(b_lines) == 2 and source[1]["itemId"] not in b_lines
               and matched_line(b_lines, source[2], BILLED[2]) and bill.get("expenses") == [])
    if bill and not isinstance(bill.get("expenses"), list):
        raise InfraError("new bill has missing or malformed expenses")

    old_stock, new_stock = stock(initial), stock(current)
    expected_stock = dict(old_stock)
    for line, qty in zip(source, RECEIVED):
        if qty:
            key = line["itemId"], po["locationId"]
            expected_stock[key] = expected_stock.get(key, 0) + qty

    def unchanged(*collections):
        return all(before[key] == after[key] for key in collections)

    prior_kept = all(
        after[key].get(identity) == row
        for key in ("itemReceipts", "vendorBills") for identity, row in before[key].items()
    )
    other_pos_kept = (
        {k: v for k, v in before["purchaseOrders"].items() if k != PO_ID}
        == {k: v for k, v in after["purchaseOrders"].items() if k != PO_ID}
    )

    old_posts = records(old_mm, "posts")
    posts = records(new_mm, "posts")
    if "post-portland-l6712" not in old_posts:
        raise InfraError("original receiving thread missing from initial state")
    replies = []
    for post in new_items(old_posts.values(), posts.values()):
        if (post.get("userId") == "usr-alex-morgan"
                and post.get("channelId") == "ch-portland-receiving"
                and post.get("rootId") == "post-portland-l6712" and not post.get("deletedAt")):
            if not isinstance(post.get("message"), str):
                raise InfraError("target reply has missing or malformed message text")
            if plain(post["message"]):
                replies.append(post["message"])
    raw = replies[0] if len(replies) == 1 else ""
    body = message_text(raw)
    receipt_no = plain(receipt.get("tranId"))
    bill_no = plain(bill.get("transactionNumber"))
    thread_ids = all(
        identifier and re.search(token(identifier), body)
        for identifier in (receipt_no, bill_no, INVOICE)
    )

    belt = f"{PRODUCTS[0]}|{SKUS[0]}"
    sprocket = f"{PRODUCTS[1]}|{SKUS[1]}"
    chain = f"{PRODUCTS[2]}|{SKUS[2]}"
    held = in_statement(
        body, count_pattern(1, rf"(?:(?:dock[- ]accepted|accepted|signed|excess|extra)\s+)?(?:{belt})"),
        r"\b(?:over(?:age|\s+(?:the\s+)?(?:cap|limit|capacity))?|excess|extra|beyond|cap(?:acity)?|limit)\b",
        AFFIRMED + r"(?:held|hold|(?:left|kept|remains?)\s+off|excluded|quarantined|set\s+aside|not\s+(?:received|posted|stocked|put\s+away|added\s+to\s+stock))\b",
    )
    damage = r"(?:damaged|crushed|broken)"
    packaging = r"(?:box|carton|case|packaging)"
    damaged_sprockets = count_pattern(3, rf"{damage}\s+(?:{sprocket})")
    damaged_package = (
        rf"\b(?:{damage}\s+{packaging}|{packaging}\s+(?:(?:was\s+)?{damage}|damage)"
        rf"|{packaging}\s+of\s+{damaged_sprockets})\b"
    )
    refused = in_statement(
        body, count_pattern(3, rf"(?:{damage}\s+)?(?:{sprocket})"), damaged_package,
        AFFIRMED + r"(?:refused|rejected|turned\s+away|declined)\b",
    )
    # AP-2718 separates the two older belts. The issued invoice excludes
    # one of the five dock-accepted chain boxes.
    unbilled = (AFFIRMED + r"(?:unbilled|not\s+(?:yet\s+)?(?:billed|invoiced)|"
                r"(?:not\s+on|excluded\s+from|off|omitted\s+from)\s+(?:(?:this|the)\s+)?(?:issued\s+)?(?:bill|invoice))\b")
    chain_box = r"(?:(?:accepted|received|extra)\s+)?(?:chain\s+box(?:es)?|box(?:es)?\s+of\s+(?:roller\s+)?chain|box(?:es)?\s+(?:of\s+)?chn-40-10|chn-40-10\s+box(?:es)?)"
    one_box = in_statement(body, rf"(?:{count_pattern(1, chain_box)}|\bfifth\s+{chain_box}\b)", unbilled)
    prior_belt = rf"(?:(?:prior[- ]lot|previous[- ]lot|older)\s+)?(?:{belt})"
    prior_two = in_statement(body, count_pattern(2, prior_belt), r"\b(?:spt-l6680|ap-2691)\b", unbilled)
    dispute_scope = nearby(body, r"\b(?:disput\w*|contest\w*|challeng\w*)\b",
                           count_pattern(4, belt), count_pattern(3, sprocket))

    g.add("N1.receipt_link", 5, r_link, "One new linked Portland receipt dated November 18")
    g.add("N2.belt_capacity", 10, r_belt, "Receipt belt line is 10 Ea at 38.20")
    g.add("N3.dock_acceptance", 9, r_chain, "Receipt has two lines, including five chain boxes and zero sprockets")
    g.add("N4.bill_link", 5, b_link, "One new linked Portland vendor bill")
    g.add("N5.invoice_identity", 10, b_link and all(
        same(bill.get(k), v) for k, v in (
            ("tranId", INVOICE), ("tranDate", DATE), ("dueDate", DUE), ("termsId", po["termsId"])
        )
    ), "Issued invoice reference, dates, and inherited PO terms")
    g.add("N6.bill_current_belts", 9, b_belt, "Bill belt line is 10 Ea at 38.20")
    g.add("N7.bill_issued_lines", 10, b_chain, "Two billed item lines, four chain boxes, zero sprockets or expenses")
    g.add("N8.open_balance", 5, b_link and same(bill.get("status"), "Open")
          and money(bill.get("total"), POSTED) and money(bill.get("amountRemaining"), POSTED)
          and money(bill.get("amountPaid"), 0) and unchanged("vendorPayments"), "Open 598 balance with zero payments")
    g.add("N9.po_conservation", 5, r_link and b_link
          and po_preserved(po, after["purchaseOrders"].get(PO_ID), source), "PO authorization preserved and cumulative counts updated")
    g.add("N10.stock_conservation", 5, r_link and new_stock == expected_stock
          and unchanged("inventoryAdjustments", "inventoryTransfers"), "Only Portland belt and chain on-hand balances increased")
    g.add("N11.protect_history", 3, r_belt and r_chain and b_belt and b_chain and prior_kept and other_pos_kept
          and unchanged("salesOrders", "itemFulfillments", "invoices", "customerPayments"), "Prior procurement and sales records preserved")
    g.add("M1.thread_target", 4, r_link and b_link and thread_ids, "Unique original-thread reply identifies both transactions and the issued invoice")
    g.add("M2.po_scope", 4, bool(re.search(r"\brev(?:ision)?\.?\s*[-–]?\s*b\b", body)) and held
          and any(has_counts(raw, "authorized", values) for values in (AUTHORIZED, CAPACITY)), "Rev B authorization and one excess belt held out of stock")
    g.add("M3.dock_scope", 4, refused and has_counts(raw, "accepted", ACCEPTED), "Signed acceptance and damaged-carton refusal")
    g.add("M4.ar_scope", 4, has_counts(raw, "claimed", CLAIMED) and dispute_scope
          and invoice_amounts(body), "Issued claim, 598 posted, and 235 disputed for four belts and three sprockets")
    g.add("M5.unbilled_lots", 8, one_box and prior_two, "One chain box and two prior-lot belts remain unbilled")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
