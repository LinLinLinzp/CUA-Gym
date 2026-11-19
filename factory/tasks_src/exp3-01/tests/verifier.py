"""Grade the Walmart return and its Google Calendar pickup reminder."""

import re
from datetime import datetime
from decimal import Decimal

from cuaverify import InfraError, load_site, run

TASK_ID = "cua-hard/filter-box-pickup"
VERSION = "0.1.3"

# Theo's pre-return photo shows three VN-180 sleeves and one correct VN-160
# sleeve for this order. Walmart's completed return already accounts for one
# VN-180 sleeve, leaving two to refund against the original VN-160 order line.
ORDER_ID = "parcel-a"
ORDER_NUMBER = "2000147-835261"
LINE_ID = "parcel-a-1"
PRODUCT_ID = "vn-160"
QUANTITY = 2
# The Walmart order line is $18.50 per unit at 8% tax.
SUBTOTAL = Decimal("37.00")
TAX = Decimal("2.96")
TOTAL = SUBTOTAL + TAX
# The two Wednesday windows conflict with the Personal dentist and Work
# training events. The first Thursday window ends just as the Personal
# studio-key event starts at 11:00 CST.
WINDOW = (
    datetime.fromisoformat("2026-11-19T09:00:00-06:00"),
    datetime.fromisoformat("2026-11-19T11:00:00-06:00"),
)
PERSONAL_ID = "c1"  # Personal calendar ID in the calendar seed.


def indexed(state, site, snapshot, field):
    label = f"{site} {snapshot}.{field}"
    records = state.get(field) if isinstance(state, dict) else None
    if not isinstance(records, list):
        raise InfraError(f"expected a record list at {label}")
    result = {}
    for record in records:
        record_id = record.get("id") if isinstance(record, dict) else None
        if not isinstance(record_id, str) or not record_id or record_id in result:
            raise InfraError(f"missing, invalid, or duplicate record ID at {label}")
        result[record_id] = record
    return result


def load_records(site, *fields):
    try:
        snapshots = load_site(site)
    except UnicodeError as exc:
        raise InfraError(f"invalid text encoding in {site} state") from exc
    return [
        [indexed(state, site, label, field) for field in fields]
        for label, state in zip(("initial", "current"), snapshots)
    ]


def only_new(before, after):
    added = after.keys() - before.keys()
    return after[next(iter(added))] if len(added) == 1 else {}


def matches_money(value, expected):
    match = re.fullmatch(
        r"\s*\$?\s*(-?\d+(?:\.\d+)?)\s*(?:USD)?\s*", str(value), re.I
    )
    return bool(match and abs(Decimal(match[1]) - expected) < Decimal("0.005"))


def instant(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise InfraError(f"invalid state timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise InfraError(f"missing offset in state timestamp {value!r}")
    return parsed


def preserved(before, after):
    return all(after.get(key) == value for key, value in before.items())


def evaluate(g):
    (old_orders, old_returns), (orders, returns) = load_records(
        "walmart", "orders", "returns"
    )
    (old_events,), (events,) = load_records("google_calendar", "events")
    load_records("yahoo_mail", "messages")
    original_address = old_orders.get(ORDER_ID, {}).get("shippingAddress")
    if not isinstance(original_address, dict) or not original_address:
        raise InfraError(f"missing initial shipping address for {ORDER_ID}")

    request = only_new(old_returns, returns)
    target = request.get("status") == "submitted" and request.get("orderId") == ORDER_ID
    lines = request.get("lines", [])
    if not isinstance(lines, list) or any(not isinstance(line, dict) for line in lines):
        raise InfraError("invalid Walmart return lines")
    line = lines[0] if len(lines) == 1 else {}
    filter_only = (
        target and line.get("orderLineId") == LINE_ID and line.get("productId") == PRODUCT_ID
    )
    correct_quantity = filter_only and line.get("quantity") == QUANTITY
    correct_reason = filter_only and line.get("reason") == "wrong_item" and line.get("resolution") == "refund"
    estimate = all(
        matches_money(amount, expected)
        for amount, expected in (
            (line.get("refundSubtotal"), SUBTOTAL),
            (line.get("refundTax"), TAX),
            (line.get("refundAmount"), TOTAL),
            (request.get("refundEstimate"), TOTAL),
        )
    )

    appointment = request.get("pickupAppointment")
    if appointment is None:
        appointment = {}
    if not isinstance(appointment, dict):
        raise InfraError("invalid Walmart pickup appointment")
    pickup_window = (instant(appointment.get("startAt")), instant(appointment.get("endAt")))
    correct_pickup = target and request.get("method") == "scheduled_pickup" and (
        appointment.get("address") == original_address
    )
    earliest = correct_pickup and pickup_window == WINDOW

    event = only_new(old_events, events)
    event_window = (instant(event.get("start")), instant(event.get("end")))

    g.add("W1.order", 18, target, f"One new submitted return for order {ORDER_NUMBER}")
    g.add("W2.line", 12, filter_only, "Only the ordered VN-160 line is on the return")
    g.add("W3.quantity", 20, correct_quantity, "Two wrong-size filters after the completed return")
    g.add("W4.estimate", 10, filter_only and estimate, "$37.00 subtotal + $2.96 tax = $39.96")
    g.add("W5.reason", 5, correct_reason, "Wrong item with refund resolution")
    g.add("W6.method", 8, correct_pickup, "Pickup at the original shipping address for the target order")
    g.add("W7.earliest", 15, earliest, "Thursday November 19, 9–11 a.m. Central")
    g.add("C1.reference", 4, correct_pickup and event.get("calendarId") == PERSONAL_ID
          and event.get("title") == f"Walmart return pickup – {ORDER_NUMBER}",
          "One new Personal event with the exact pickup title")
    g.add("C2.window", 5, correct_pickup and None not in pickup_window and event_window == pickup_window
          and event.get("calendarId") == PERSONAL_ID and event.get("allDay") is False
          and event.get("recurring", "none") == "none",
          "One timed, nonrecurring event for the full confirmed window")
    g.add("P1.preserve", 3, target and bool(event) and orders == old_orders
          and preserved(old_returns, returns) and preserved(old_events, events),
          "Existing orders, returns, and events are intact, with no new orders")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
