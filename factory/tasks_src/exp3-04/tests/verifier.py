"""Grade the Cedarline Foods October retainer true-up from site snapshots."""

import re
from decimal import Decimal, InvalidOperation

from cuaverify import InfraError, load_site, run

TASK_ID = "cua-hard/retainer-renewal-true-up"
VERSION = "0.1.1"

CLIENT = "cli_cedarline"
BOOK = "wb-oct-close"
CLOSE = "closeout"
LATE = "late-time"

# Yahoo's executed agreement and signed amendment give the 600/735 minute
# monthly allowances: floor(600*15/31)=290, floor(735*16/31)=379.
# Excel's posted totals (278, 365) plus distinct approved late rows (73+58,
# 66+51) less the allowances give 119 and 103 excess minutes. CF-782's
# second row, the rejected correction, and time already posted are excluded.
# Gross A: (45*137.34 + 74*174.85)/60 -> 318.65, rounded half up once.
# Gross B: (50*154.25 + 53*193.65)/60 -> 299.60, rounded half up once.
# FreshBooks inv_prior_a/b are the same-period provisional overage invoices
# (36.47 and 28.63). The base fee and September overage do not qualify.
PERIODS = (
    ("A", "CF-2026-10A", 2, (2, 3), 4, 290, 119, ("318.65", "36.47", "282.18")),
    ("B", "CF-2026-10B", 3, (5, 6), 7, 379, 103, ("299.60", "28.63", "270.97")),
)
EDITABLE = {
    *((BOOK, CLOSE, f"{column}{row}") for row in (2, 3) for column in "DEFGHI"),
    *((BOOK, LATE, f"H{row}") for row in (2, 3, 4, 5, 6)),
}
AUDIT = {"createdAt", "createdBy", "updatedAt", "updatedBy"}
MONEY = re.compile(r"(?:USD\s+|\$\s*)?([+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)(?:\s+USD)?", re.I)


def normalized(value):
    return str(value).strip().casefold() if value is not None else ""


def number(value, money=False):
    if money and isinstance(value, str):
        match = MONEY.fullmatch(value.strip())
        if not match:
            return None
        value = match[1].replace(",", "")
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def without(record, fields):
    return {key: value for key, value in record.items() if key not in fields}


def indexed(state, collection, site):
    records = state.get(collection)
    if not isinstance(records, list):
        raise InfraError(f"{site}.{collection} is missing or invalid")
    result = {}
    for record in records:
        key = record.get("id") if isinstance(record, dict) else None
        if not isinstance(key, str) or not key or key in result:
            raise InfraError(f"{site}.{collection} contains a missing or duplicate ID")
        result[key] = record
    return result


def snapshots(site, required):
    try:
        pair = load_site(site)
    except (UnicodeError, ValueError) as exc:
        raise InfraError(f"cannot decode {site} state: {exc}") from exc
    for state in pair:
        if not isinstance(state, dict):
            raise InfraError(f"{site} snapshot is not an object")
        for collection in required:
            indexed(state, collection, site)
    return pair


def cells(state):
    result = {}
    for cell in state["cells"]:
        key = tuple(cell.get(field) for field in ("workbookId", "sheetId", "address"))
        if (not all(isinstance(part, str) and part for part in key)
                or key in result or "value" not in cell):
            raise InfraError("Excel contains a malformed cell or duplicate coordinate")
        result[key] = cell
    return result


def cell_value(cell):
    if cell.get("error") or cell.get("valueType") == "error":
        return cell.get("error") or "#ERROR!"
    return cell.get("value")


def projection(state, omitted, record_fields):
    """Compare record collections by ID while preserving each record's contents."""
    result = without(state, omitted)
    for key, value in result.items():
        if isinstance(value, list) and all(isinstance(row, dict) and "id" in row for row in value):
            ignored = record_fields.get(key, record_fields.get("*", set()))
            result[key] = sorted(
                (without(row, ignored) for row in value), key=lambda row: row["id"]
            )
    return result


def protected_cells(grid):
    protected = {}
    for key, cell in grid.items():
        if key in EDITABLE:
            continue
        content = without(cell, AUDIT | {"id"})
        if (cell_value(cell) in (None, "") and not cell.get("input")
                and not cell.get("formula") and not cell.get("format")):
            continue  # Clearing an unformatted blank may remove its sparse record.
        protected[key] = content
    return protected


def linked(before, after, sheet, address, invoice_number):
    key = (BOOK, sheet, address)
    return bool(invoice_number) and (
        normalized(cell_value(after.get(key, {}))) == invoice_number
        and normalized(cell_value(before.get(key, {}))) != invoice_number
    )


def entered(before, after, address, expected, money=False):
    key = (BOOK, CLOSE, address)
    return (
        number(cell_value(after.get(key, {})), money) == expected
        and number(cell_value(before.get(key, {})), money) != expected
    )


def draft_for(added, reference):
    matches = [
        invoice for invoice in added
        if invoice.get("clientId") == CLIENT
        and normalized(invoice.get("reference")) == reference.casefold()
    ]
    if len(matches) != 1:
        return None
    invoice = matches[0]
    if (normalized(invoice.get("visibility")) == "active"
            and normalized(invoice.get("status")) == "draft"
            and invoice.get("sentAt") in (None, "")
            and normalized(invoice.get("invoiceNumber"))):
        return invoice
    return None


def evaluate(g):
    fb_before, fb_after = snapshots("freshbooks", (
        "invoices", "users", "clients", "projects", "services", "expenseCategories",
        "payments", "timeEntries", "expenses", "retainers", "retainerPeriods",
    ))
    xl_before, xl_after = snapshots("microsoft_excel_for_the_web", (
        "workbooks", "sheets", "cells",
    ))
    mail_before, mail_after = snapshots("yahoo_mail", ("messages", "folders"))

    before, after = cells(xl_before), cells(xl_after)
    old_invoices = indexed(fb_before, "invoices", "FreshBooks")
    current_invoices = indexed(fb_after, "invoices", "FreshBooks")
    added = [invoice for key, invoice in current_invoices.items() if key not in old_invoices]

    numbers, net_passes, close_links, late_links = [], [], [], []
    for label, reference, row, late_rows, excluded_row, allowance, excess, amounts in PERIODS:
        draft = draft_for(added, reference)
        invoice_number = normalized(draft["invoiceNumber"]) if draft else ""
        gross, prior, net = map(Decimal, amounts)
        correct_draft = bool(draft) and normalized(draft.get("currency")) == "usd" and all(
            number(draft.get(field), money=True) == expected
            for field, expected in (
                ("taxAmount", 0), ("discountAmount", 0), ("total", net), ("amountDue", net)
            )
        )
        g.add(f"F{label}.net_draft", 20, correct_draft,
              f"{reference}: unique new unsent USD draft, net {net}, zero tax and discount")
        g.add(f"E{label}.allowance", 5, entered(before, after, f"D{row}", allowance),
              f"Closeout D{row}: {allowance} minutes")
        g.add(f"E{label}.excess", 5, entered(before, after, f"E{row}", excess),
              f"Closeout E{row}: {excess} minutes")
        correct_amounts = all(
            entered(before, after, f"{column}{row}", expected, money=True)
            for column, expected in zip("FGH", (gross, prior, net))
        )
        g.add(f"E{label}.amounts", 8, correct_amounts,
              f"Closeout F{row}:H{row}: gross {gross}, prior {prior}, net {net}")

        numbers.append(invoice_number)
        net_passes.append(correct_draft)
        close_links.append(linked(before, after, CLOSE, f"I{row}", invoice_number))
        late_ok = all(linked(before, after, LATE, f"H{r}", invoice_number) for r in late_rows)
        excluded_blank = cell_value(after.get((BOOK, LATE, f"H{excluded_row}"), {})) in (None, "")
        late_links.append((label, late_ok and excluded_blank, late_rows, excluded_row))

    g.add("E.refs_closeout", 5, all(close_links) and len(set(numbers)) == 2,
          "Closeout I2:I3 link to two different new unsent draft invoice numbers")
    for label, okay, rows, excluded in late_links:
        g.add(f"E{label}.refs_late", 5, okay,
              f"Late Time H{rows[0]} and H{rows[1]} link to the new draft, H{excluded} is blank")

    fb_ok = (
        len(added) == 2 and all(numbers)
        and old_invoices == {key: current_invoices.get(key) for key in old_invoices}
        and projection(fb_before, {"invoices", "activityEvents"}, {})
        == projection(fb_after, {"invoices", "activityEvents"}, {})
    )
    xl_ignored = {"*": AUDIT, "workbooks": AUDIT | {"lastOpenedAt", "activeSheetId"}}
    xl_ok = (
        protected_cells(before) == protected_cells(after)
        and projection(xl_before, {"cells", "operations"}, xl_ignored)
        == projection(xl_after, {"cells", "operations"}, xl_ignored)
    )
    mail_ok = (
        projection({"messages": mail_before["messages"]}, set(), {"messages": {"isRead", "updatedAt"}})
        == projection({"messages": mail_after["messages"]}, set(), {"messages": {"isRead", "updatedAt"}})
    )
    g.add("P.isolation", 9, any(net_passes) and fb_ok and xl_ok and mail_ok,
          f"At least one correct net draft: {any(net_passes)}. "
          f"FreshBooks preserved: {bool(fb_ok)}. Excel preserved: {xl_ok}. Mail preserved: {mail_ok}.")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
