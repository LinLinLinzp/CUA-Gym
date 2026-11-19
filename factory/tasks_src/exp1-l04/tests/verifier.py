#!/usr/bin/env python3
"""Verifier for stripe-payout-reconciliation. Checkpoints mirror rubric.json (P*, S*, G*, E*, C1).

All expected values below were derived independently from seed/*.json and
input/stripe_payouts_nov.csv:
  * Landed + unbooked payouts: Stripe status=paid, a STRIPE TRANSFER in the QuickBooks
    Checking feed (tx_pB 37,186.09 on 11/10, tx_pC 39,320.09 on 11/13), and no Stripe fee
    expense yet. po_1Q1yO5... (11/3, exp_fee_p0) and po_1QTtOT... (11/6, exp_fee_pA) are
    already booked; po_1QGiTQ... is in_transit (Gmail m06, no bank line).
  * Fees = sum of the CSV `fee` column for the payout (the refund row has fee 0).
  * Invoice matching uses each payment's description/metadata plus QuickBooks totals and
    open balances, together with the Gmail messages m02/m03/m05/m13.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import (InfraError, load_site, mentions_amount, money_eq, new_items,  # noqa: E402
                       plain, read_csv, run)

TASK_ID, VERSION = "cua-hard/stripe-payout-reconciliation", "0.1.1"

PO_B = "po_1QuGWB0KZqRczvjnKDM89oW"   # paid 11/10, bank tx_pB 37,186.09
PO_C = "po_1Qun3S1emzce8TMzyYYGsdv"   # paid 11/13, bank tx_pC 39,320.09
# CSV fee sums: po_B 17 charges -> 1218.91; po_C 18 charges -> 1179.91
FEES = {PO_B: 1218.91, PO_C: 1179.91}

WREN = ("pi_3QWICu52xMRp9dpuWadtdk2", "pi_3QgjZN5nm5s7rKz0tZVOWfL")  # 2 x 264000 for 1196
WREN_CENTS = 264000
BRIGHTWATER_DUP = "pi_3QtSzeHpNZdx6Oma7hx3Kf3"  # refunded 11/6 (re_3QjpuE...), 89000
ATLAS = "pi_3QdNEY7eLLkhc3wI7SSW5fV"            # says "Invoice 1158" but 1158 is paid -> 1193

# payment_id -> (payout, invoices, action, kind). 35 client charges in the two landed payouts.
ITEMS = {
    # ---- po_B (11/10)
    "pi_3QsXQAZ6VROh6lSydpule1A": (PO_B, ("1174",), "paid", "standard"),      # Bramble 1240
    "pi_3QzQ5je3YxlE8jU0lKUNoIt": (PO_B, ("1154",), "paid", "deposit"),       # Kestrel 3600 = 7200-3600
    "pi_3Q5fQmyFN8I0LPjTTBJd9Ne": (PO_B, ("1175",), "paid", "standard"),      # Ferro 5600
    "pi_3Q4qZIbQ3CgNJhDg6UkfadZ": (PO_B, ("1176",), "short", "short"),        # Tidewater 2500 of 2750 -> 250
    "pi_3Q9RzOyHqZucHoY6V50yGXS": (PO_B, ("1177",), "paid", "standard"),      # Pinecrest 1980
    "pi_3QnlVwR4LsNG3M6ZsKYh9KR": (PO_B, ("1180",), "paid", "brightwater"),   # Brightwater 890
    BRIGHTWATER_DUP:              (PO_B, ("1180",), "already_refunded", "already_refunded"),
    "pi_3QDdEb79qrBkN0twXNKPgCh": (PO_B, ("1179",), "paid", "split"),         # Lumen 1000
    "pi_3QZGPtuUWngJEPwCjzgQnWH": (PO_B, ("1179",), "paid", "split"),         # Lumen 860 (sum 1860)
    "pi_3QhJDUZEt6xBVVtwHJyfyrI": (PO_B, ("1185",), "paid", "standard"),      # Velvet 640
    "pi_3Q4vcThddiDPFIz0VnyOnRB": (PO_B, ("1178", "1182"), "paid", "combined"),  # Saltmarsh 2200+2100
    "pi_3Q7H5oFObWRPa8iNTszEwP1": (PO_B, ("1183",), "paid", "no_ref_near_duplicate"),  # Marlowe Finch, not 1184
    "pi_3QIT8M1XVAOF6HzlfWTIN8r": (PO_B, ("1186",), "paid", "standard"),      # Hollis 1520
    "pi_3QAaKj30FeEnK2CcWDYKFUE": (PO_B, ("1187",), "paid", "standard"),      # Oakhaven 3400
    "pi_3Qy2SC7D8kZyDJKecJFt1t5": (PO_B, ("1190",), "paid", "standard"),      # Nordvik 4950 (intl fee)
    "pi_3QjLrDfmDppxqEL1P5DD9R8": (PO_B, ("1188",), "paid", "standard"),      # Sable 2600
    "pi_3Q3VEmFv0Oa0pBE6sWbOw3C": (PO_B, ("1189",), "paid", "standard"),      # Morrow 1525
    # ---- po_C (11/13)
    "pi_3Q3IVtKQWtbmhdjEooiR4Z1": (PO_C, ("1201",), "paid", "standard"),      # Greywell 2250
    "pi_3Q6a9ABL8TW8sbays21R4bI": (PO_C, ("1157",), "paid", "deposit"),       # Greywell 6500 = 9500-3000
    "pi_3QtDbyLY4hHxcDq6hUA2SL3": (PO_C, ("1194",), "paid", "waived"),        # Calder 1300 of 1385, m05 waives 85
    "pi_3QURi9COzNSBljRjR7IoQpE": (PO_C, ("1197",), "paid", "corrected_ref"), # Juniper 1450, m03: 1192 -> 1197
    "pi_3QqeIf1BmZLFGb61UWYxQgW": (PO_C, ("1160",), "paid", "deposit"),       # Northgate 2400 = 4800-2400
    "pi_3QfGL6NypZcyYQQplUjVaYn": (PO_C, ("1191", "1198"), "paid", "combined"),  # Quillon 3150+1200
    ATLAS:                        (PO_C, ("1193",), "paid", "wrong_ref"),     # Atlas 1975
    "pi_3QMAbfMoh62NelTtkKZiiJ4": (PO_C, ("1195",), "short", "short"),        # Harbor & Pine 1180 of 1420 -> 240
    "pi_3QYmzlplGEgMgKopPpkF9QQ": (PO_C, ("1202",), "paid", "standard"),      # Ferro 1780
    WREN[0]:                      (PO_C, ("1196",), "paid", "wren"),          # Wren first charge
    WREN[1]:                      (PO_C, ("1196",), "refunded", "wren"),      # Wren duplicate (m02: "the second")
    "pi_3Qk0GKyvT4WjuRawN9CBsze": (PO_C, ("1203",), "paid", "standard"),      # Bramble 760
    "pi_3Q4SWt1CM5mSy1IKbxp9Js8": (PO_C, ("1200",), "paid", "no_ref"),        # Odessa Park 1150, not 1199 (640)
    "pi_3Q9ivldWxhvu4Rl2YISWNqz": (PO_C, ("1204",), "paid", "standard"),      # Pinecrest 1150
    "pi_3Q0FGvM9QPAzBDpluarnuCY": (PO_C, ("1205",), "paid", "standard"),      # Copperline 2480
    "pi_3QjyMpMkp89xyBRH0iyxn4z": (PO_C, ("1206",), "paid", "standard"),      # Sable 980
    "pi_3QkWrx7WD8F0OW6SsjifVMv": (PO_C, ("1207",), "paid", "standard"),      # Hollis 1640
    "pi_3QJTocVYvTv9C1moSbG4nXT": (PO_C, ("1208",), "paid", "standard"),      # Oakhaven 3875
}
assert len(ITEMS) == 35
# In-transit payout charges: their invoices must stay open.
IN_TRANSIT_INVOICES = ("1181", "1209", "1210", "1211", "1212")

SINGLE_INVOICES = ("1174", "1175", "1177", "1180", "1185", "1186", "1187", "1188", "1189",
                   "1190", "1196", "1201", "1202", "1203", "1204", "1205", "1206", "1207", "1208")
TARGETS = sorted({n for _, invs, action, _ in ITEMS.values() if action != "short" for n in invs})
# Must stay non-Paid: in-transit, 1213 (failed charge), 1214 (pending/unsettled), 1215 (no charge),
# 1161 (overdue, no charge), 1199 / 1192 / 1184 (lookalike traps).
NON_TARGETS = IN_TRANSIT_INVOICES + ("1213", "1214", "1215", "1161", "1199", "1192", "1184")

# Short payments: invoice -> (billing address on the QuickBooks customer record, amount still owed)
SHORT = {"1176": ("ap@tidewaterbrewing.com", 250.00),   # 2750 - 2500
         "1195": ("accounts@harborpine.com", 240.00)}   # 1420 - 1180
NO_CHASE = ("tomas@calderbikes.com", "billing@juniperhealth.org", "ap@kestrelanalytics.io",
            "ap@greywell.partners", "office@northgatedental.com", "billing@lumensolar.coop",
            "m.ostrowski@gmail.com")

_ADDR = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def to_float(value):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value)))
    except (TypeError, ValueError):
        return None


def recipients(email):
    found = set()
    for field in ("to", "cc", "bcc"):
        value = email.get(field) or []
        if isinstance(value, (str, dict)):
            value = [value]
        for r in value:
            text = (r.get("email") or "") if isinstance(r, dict) else str(r)
            found.update(a.lower() for a in _ADDR.findall(text))
    return found


def evaluate(g):
    qb0, qb1 = load_site("quickbooks")
    st0, st1 = load_site("stripe_dashboard")
    mail0, mail1 = load_site("gmail")

    # ---- QuickBooks invoices --------------------------------------------------
    inv0 = {str(i.get("number")): i for i in qb0.get("invoices") or []}
    inv1 = {str(i.get("number")): i for i in qb1.get("invoices") or []}
    missing = sorted(set(inv0) - set(inv1))
    if not inv0 or missing:
        raise InfraError(f"invoices missing from QuickBooks state: {missing or 'all'}")

    def paid(number):
        inv = inv1[number]
        if str(inv.get("status") or "").strip().lower() == "paid":
            return True
        total, amt = to_float(inv.get("total")), to_float(inv.get("paidAmount"))
        return total is not None and amt is not None and total > 0 and amt >= total - 0.005

    # ---- Stripe refunds (cents) ----------------------------------------------
    pay0 = {p.get("id"): p for p in st0.get("payments") or []}
    pay1 = {p.get("id"): p for p in st1.get("payments") or []}
    missing = sorted(set(pay0) - set(pay1))
    if not pay0 or missing:
        raise InfraError(f"payments missing from Stripe state: {missing or 'all'}")
    new_refunds = [r for r in new_items(st0.get("refunds"), st1.get("refunds"))
                   if str(r.get("status") or "succeeded").lower() not in ("failed", "canceled")]

    def refunded_now(pid):
        delta = int(pay1[pid].get("amount_refunded") or 0) - int(pay0[pid].get("amount_refunded") or 0)
        via_list = sum(int(r.get("amount") or 0) for r in new_refunds
                       if r.get("charge") == pid or r.get("payment_intent") == pid)
        return max(delta, via_list)

    added = {pid: refunded_now(pid) for pid in pay0}
    wren_full = [pid for pid in WREN if added[pid] == WREN_CENTS]

    # ---- Gmail -----------------------------------------------------------------
    sent = [e for e in new_items(mail0.get("emails"), mail1.get("emails")) if e.get("folder") == "sent"]

    def mails_to(address):
        return [(e.get("subject") or "") + " \n " + (e.get("body") or "") for e in sent if address in recipients(e)]

    def short_mail_ok(number):
        address, amount = SHORT[number]
        return any(re.search(rf"(?<!\d){number}(?!\d)", plain(t)) and mentions_amount(t, amount)
                   for t in mails_to(address))

    def is_stripe(e):
        return e.get("vendorId") == "v_stripe" or str(e.get("payee") or "").strip().lower().startswith("stripe")

    fee_new = [e for e in new_items(qb0.get("expenses"), qb1.get("expenses")) if is_stripe(e)]
    rows = read_csv("payout_reconciliation.csv")
    invoice_work = any(
        inv0[n].get(field) != inv1[n].get(field)
        for n in (*TARGETS, *SHORT, *NON_TARGETS)
        for field in ("status", "paidAmount")
    )
    # The unchanged seed alone earns no credit for preservation checks.
    task_started = bool(invoice_work or any(added.values()) or new_refunds or sent or fee_new or rows)

    def frac(numbers):
        return sum(paid(n) for n in numbers) / len(numbers)

    def unpaid_list(numbers):
        return [n for n in numbers if not paid(n)]

    # ---- P: invoices -----------------------------------------------------------
    g.add("P1.standard_paid", 14, frac(SINGLE_INVOICES), f"not Paid: {unpaid_list(SINGLE_INVOICES)}")
    deposits = ("1154", "1157", "1160")
    g.add("P2.deposit_balance_paid", 6, frac(deposits), f"not Paid: {unpaid_list(deposits)}")
    combos = (("1178", "1182"), ("1191", "1198"))
    g.add("P3.combined_paid", 6, sum(all(paid(n) for n in c) for c in combos) / 2,
          f"Saltmarsh 1178+1182 Paid={[paid(n) for n in combos[0]]}; Quillon 1191+1198 Paid={[paid(n) for n in combos[1]]}")
    g.add("P4.split_paid", 3, paid("1179"), f"1179 Paid={paid('1179')}")
    unreferenced = ("1183", "1200")
    g.add("P5.unreferenced_matched", 5, frac(unreferenced), f"not Paid: {unpaid_list(unreferenced)}")
    g.add("P6.wrong_reference_1193", 4, paid("1193"), f"1193 Paid={paid('1193')}")
    g.add("P7.corrected_reference_1197", 4, paid("1197"), f"1197 Paid={paid('1197')}")
    g.add("P8.calder_waived", 4, paid("1194"), f"1194 Paid={paid('1194')}")

    shorts_open = not paid("1176") and not paid("1195")
    g.add("P9.short_left_open", 3, task_started and shorts_open,
          f"1176 Paid={paid('1176')} 1195 Paid={paid('1195')}; task activity={task_started}")
    wrongly = [n for n in NON_TARGETS if paid(n)]
    g.add("P10.non_targets_untouched", 4,
          (len(NON_TARGETS) - len(wrongly)) / len(NON_TARGETS) if task_started else 0,
          f"wrongly Paid: {wrongly}; task activity={task_started}")

    # ---- S: Stripe ---------------------------------------------------------------
    g.add("S1.refund_wren", 6, bool(wren_full), f"new refunds on Wren charges: { {p: added[p] for p in WREN} }")
    # One Wren charge may carry the refund; everything else must keep its amount_refunded.
    wren_allowed = max(WREN, key=lambda p: added[p])
    extra = {pid: c for pid, c in added.items() if c and pid != wren_allowed}
    orphan_refunds = [r.get("id") for r in new_refunds
                      if r.get("charge") not in pay0 and r.get("payment_intent") not in pay0]
    g.add("S2.no_extra_refunds", 4, task_started and not extra and not orphan_refunds,
          f"other refunds added: {extra}; unlinked refunds: {orphan_refunds}; task activity={task_started}")

    # ---- G: Gmail ------------------------------------------------------------------
    g.add("G1.short_email_tidewater", 4, short_mail_ok("1176"),
          f"{len(mails_to('ap@tidewaterbrewing.com'))} mail(s) to ap@tidewaterbrewing.com; needs 1176 + $250.00")
    g.add("G2.short_email_harborpine", 4, short_mail_ok("1195"),
          f"{len(mails_to('accounts@harborpine.com'))} mail(s) to accounts@harborpine.com; needs 1195 + $240.00")
    chased = [a for a in NO_CHASE if mails_to(a)]
    g.add("G3.no_wrong_chasers", 3, task_started and not chased,
          f"{len(sent)} sent; wrongly emailed: {chased}; task activity={task_started}")

    # ---- E: fee expenses -------------------------------------------------------------
    def fee_entries(payout):
        return [e for e in fee_new if payout.lower() in str(e.get("description") or "").lower()]

    payouts_by_expense = {}
    for check_id, payout in (("E1.fees_poB", PO_B), ("E2.fees_poC", PO_C)):
        entries = fee_entries(payout)
        ok = [e for e in entries if money_eq(to_float(e.get("amount")), FEES[payout])]
        for entry in entries:
            payouts_by_expense.setdefault(entry.get("id"), []).append(payout)
        g.add(check_id, 5, bool(ok),
              f"{len(entries)} Stripe expense(s) for {payout}, amounts {[e.get('amount') for e in entries]}; expected {FEES[payout]}")
    matches = [payouts_by_expense.get(e.get("id"), []) for e in fee_new]
    unique_payouts = {payout for match in matches if len(match) == 1 for payout in match}
    g.add("E3.no_extra_fee_entries", 4, task_started and len(unique_payouts) == len(fee_new),
          f"{len(fee_new)} new Stripe expense(s); target payout matches per entry: {matches}; task activity={task_started}")

    # ---- C1: reconciliation CSV --------------------------------------------------------
    if rows is None:
        g.add("C1.recon_csv", 12, 0, "payout_reconciliation.csv missing")
    else:
        # Wren: the CSV must say "refunded" for the charge actually refunded in Stripe;
        # if Stripe shows no single full refund, either assignment is accepted.
        wren_choices = wren_full if len(wren_full) == 1 else WREN
        by_pid = {}
        for r in rows:
            by_pid.setdefault(r.get("payment_id", "").strip(), []).append(r)

        def row_ok(pid, r, refunded_wren):
            payout, invs, action, kind = ITEMS[pid]
            if kind == "wren":
                action = "refunded" if pid == refunded_wren else "paid"
            got_invs = set(re.findall(r"\d{4}", r.get("invoices", "")))
            allowed = [set(invs)]
            if action in ("refunded", "already_refunded"):
                allowed.append(set())  # refunded money arguably went toward no invoice
            return (r.get("payout_id", "").strip() == payout
                    and got_invs in allowed
                    and r.get("action", "").strip().lower().replace(" ", "_") == action)

        best = 0
        for refunded_wren in wren_choices:
            correct = sum(len(by_pid.get(pid, [])) == 1 and row_ok(pid, by_pid[pid][0], refunded_wren)
                          for pid in ITEMS)
            best = max(best, correct)
        g.add("C1.recon_csv", 12, best / max(len(ITEMS), len(rows)),
              f"{best}/{len(ITEMS)} rows right, {len(rows)} rows total")

if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
