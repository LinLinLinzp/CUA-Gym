#!/usr/bin/env python3
"""Verifier for hartley-part-year-calfile. Checkpoint ids/weights mirror rubric.json (C1..C14).

All expected values below were derived independently from the seeds:
  seed/gmail.json (Gloria's 04-02 instructions g12, fee card g06 + correction g07, Leah's
  Web Pay receipts g09), the PDF attachments (W-2s, W-2c, 1099-INTs, lease),
  seed/paypal.json transactions and input/boc_usdcad_2024.csv.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, new_items, plain, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/hartley-part-year-calfile", "0.1.0"
TOL = 0.005

# ---------------------------------------------------------------- constants
# Residency date = lease commencement 2024-06-18 (Lease_2715J_Unit4.pdf §2), not the 6/15 in Dan's email.
# Oregon period 2024-01-01..06-17 = 31+29+31+30+31+17 = 169 days of 366 (leap year).
CASCADE_WAGES = 38416.92          # W2_2024_Cascade_Outfitters.pdf box 1 (only OR state line)
WVCU_INTEREST = 612.40            # 1099-INT_2024_WVCU.pdf box 1
WVCU_OREGON = 282.77              # round(612.40 * 169 / 366, 2) = 282.7716 -> 282.77

# Photography: 13 PayPal rows t_f01..t_f13. USD fee = round(3.49% + 0.49); CAD fee = round(4.99% + CA$0.59)
# taken in CAD, net / BoC FXUSDCAD on the date or last earlier publication; refunds sent negative, no fee.
PHOTO_ROWS = {
    "2024-01-05": (578.57, "oregon"),       # Willamette Weddings 600 USD
    "2024-02-09": (843.97, "oregon"),       # Rose City Brewing 875 USD
    "2024-03-23": (839.31, "oregon"),       # Northbound CA$1200 -> 1139.53 CAD / 1.3577 (Sat -> 03-22)
    "2024-04-30": (404.85, "oregon"),       # Hawthorne Family Dental 420 USD
    "2024-05-14": (-90.00, "oregon"),       # refund sent to Hawthorne
    "2024-06-15": (1138.33, "oregon"),      # Pearl District Gallery 1180 USD
    "2024-06-17": (442.79, "oregon"),       # Northbound CA$640 -> 607.47 / 1.3719
    "2024-06-18": (289.04, "california"),   # Midtown Farmers Market 300 USD
    "2024-09-02": (633.39, "california"),   # Northbound CA$900 -> 854.50 / 1.3491 (Labour Day -> 08-30)
    "2024-09-21": (1717.39, "california"),  # Tower Bridge Events 1780 USD
    "2024-10-05": (-200.00, "california"),  # partial refund sent to Tower Bridge
    "2024-11-16": (926.01, "california"),   # Delta Vine Winery 960 USD
    "2024-12-28": (316.34, "california"),   # Northbound CA$480 -> 455.46 / 1.4398 (Sat -> 12-27)
}
PHOTO_TOTAL = 7839.99             # sum of the 13 rounded rows
PHOTO_OREGON = 4157.82            # sum of the 7 oregon rows
CA_SUBTRACTION = 42857.51         # 38416.92 + 282.77 + 4157.82

FEDERAL_AGI = 163591.78           # g12 final (draft 164,493.60 in g11 is superseded)
ESTIMATED_2024 = 1000.00          # g09: TY2024 installments 250 (06/14) + 300 (09/12) + 450 (01/14/2025)

# Balance due for the correct return as computed by the CalFile mock (rubric C9).
TAX_DUE = 402.32
WEBPAY_DATE = "2025-04-15"        # g12: "tax-due payment dated April 15"
WEBPAY_LAST4 = "4471"             # g09: joint Golden 1 checking 1180074471 (not savings ...2290)

# Fee card g06 corrected by g07: (240 + 120 part-year + 95 Sch C + 15 third W-2 employer) * 0.85
PREPARER_FEE = 399.50
BUSINESS_PP = "payments@reyestaxservices.com"
BUSINESS_PP_NAME = "reyes tax services"       # PayPal contact c_3
PERSONAL_PP = "gloria.reyes82@gmail.com"
PERSONAL_PP_NAME = "gloria reyes"             # PayPal contact c_2
GLORIA_MAIL = "gloria@reyestaxservices.com"
DANIEL_MAIL = "daniel.hartley@gmail.com"


# ---------------------------------------------------------------- helpers
def num(value):
    """'$1,234.50', '1234.5 USD', 1234.5 -> 1234.5; None if not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"(?i)usd|\$|,|\s", "", str(value))
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def eq(value, expected):
    n = num(value)
    return n is not None and abs(n - expected) <= TOL


def section(state, key, kind=dict):
    value = state.get(key)
    if not isinstance(value, kind):
        raise InfraError(f"state section {key!r} missing or malformed")
    return value


def find(items, field, *keywords):
    return [i for i in items if any(k in str(i.get(field) or "").lower() for k in keywords)]


def evaluate(g):
    tax0, tax1 = load_site("california_tax")
    mail0, mail1 = load_site("gmail")
    pp0, pp1 = load_site("paypal")
    income = section(tax1, "income")
    deductions = section(tax1, "deductions")
    payment = section(tax1, "payment")
    ret = section(tax1, "taxReturn")
    calcs = tax1.get("calculations") or {}
    section(pp1, "transactions", list)
    section(mail1, "emails", list)

    # ---- C1: Schedule CA subtraction -------------------------------------------
    sub = deductions.get("caAdjustmentsSubtraction")
    add_ok = eq(deductions.get("caAdjustmentsAddition") or 0, 0)
    c1 = g.add("C1.ca_subtraction", 14, eq(sub, CA_SUBTRACTION) and add_ok,
               f"subtraction={sub!r} addition={deductions.get('caAdjustmentsAddition')!r}; expected {CA_SUBTRACTION}")

    # ---- C2: photography Other Income ------------------------------------------
    other = income.get("otherIncome") or []
    c2 = g.add("C2.photography_other_income", 10, len(other) == 1 and eq(other[0].get("amount"), PHOTO_TOTAL),
               f"{len(other)} other-income line(s) {[o.get('amount') for o in other]}; expected one of {PHOTO_TOTAL}")

    # ---- C3: Daniel's W-2s -------------------------------------------------------
    w2s = income.get("w2s") or []

    def w2_ok(keyword, wages, fed, swages, swh):
        hits = find(w2s, "employerName", keyword)
        return len(hits) == 1 and all(eq(hits[0].get(f), v) for f, v in (
            ("wages", wages), ("federalWithheld", fed), ("stateWages", swages), ("stateWithheld", swh)))

    cascade = w2_ok("cascade", CASCADE_WAGES, 4105.30, 0.0, 0.0)          # OR-only W-2: CA state cols 0
    sierra = w2_ok("sierra ridge", 46250.00, 5212.40, 46250.00, 774.62)  # CA line on Sierra Ridge W-2
    c3 = g.add("C3.daniel_w2s", 8, 0.5 * cascade + 0.5 * sierra,
               f"cascade_ok={cascade} sierra_ok={sierra}; w2s={[(w.get('employerName'), w.get('wages'), w.get('stateWithheld')) for w in w2s]}")

    # ---- C4: Leah's W-2c correction ---------------------------------------------
    capitol = find(w2s, "employerName", "capitol health")
    c4_ok = len(capitol) == 1 and all(eq(capitol[0].get(f), v) for f, v in (
        ("wages", 70915.00), ("stateWages", 70915.00), ("federalWithheld", 8920.00), ("stateWithheld", 1380.00)))
    c4 = g.add("C4.leah_w2c", 6, c4_ok,
               f"{len(capitol)} Capitol Health W-2(s) {[(w.get('wages'), w.get('stateWages')) for w in capitol]}; expected 70915.00")

    # ---- C5: 1099-INTs -------------------------------------------------------------
    ints = income.get("interest1099") or []
    wv = find(ints, "payerName", "willamette")
    safe = [i for i in ints if re.search(r"\bsafe\b", str(i.get("payerName") or "").lower())]
    g1 = find(ints, "payerName", "golden 1", "golden one")
    wv_ok = len(wv) == 1 and eq(wv[0].get("amount"), WVCU_INTEREST)
    safe_ok = len(safe) == 1 and eq(safe[0].get("amount"), 23.18)
    keep_ok = len(ints) == 3 and len(g1) == 1 and eq(g1[0].get("amount"), 88.17)
    c5 = g.add("C5.interest_1099s", 4, (0.5 * wv_ok + 0.5 * safe_ok) if keep_ok else 0.0,
               f"wvcu_ok={wv_ok} safe_ok={safe_ok} golden1_kept_and_3_rows={keep_ok}; rows={[(i.get('payerName'), i.get('amount')) for i in ints]}")

    # ---- C6: federal AGI -------------------------------------------------------------
    c6 = g.add("C6.federal_agi", 5, eq(income.get("federalAgi"), FEDERAL_AGI),
               f"federalAgi={income.get('federalAgi')!r}; expected {FEDERAL_AGI}")

    # ---- C7: estimated payments --------------------------------------------------------
    c7 = g.add("C7.estimated_payments", 6, eq(payment.get("estimatedPayments"), ESTIMATED_2024),
               f"estimatedPayments={payment.get('estimatedPayments')!r}; expected {ESTIMATED_2024}")

    # ---- C8: submitted --------------------------------------------------------------------
    confirmation = str(ret.get("confirmationNumber") or "").strip()
    submitted = str(ret.get("status") or "").lower() == "submitted" and bool(confirmation)
    g.add("C8.submitted", 4, submitted, f"status={ret.get('status')!r} confirmation={confirmation!r}")

    # ---- C9: Web Pay tax due ----------------------------------------------------------------
    webpays = new_items((tax0.get("payment") or {}).get("webPaySubmissions"), payment.get("webPaySubmissions"))
    due = [w for w in webpays if str(w.get("type") or "").lower().replace("-", "_").replace(" ", "_") == "tax_due"]

    def right_account(w):
        last4 = str(w.get("lastFour") or w.get("accountNumber") or w.get("bankAccountNumber") or "").strip()
        return (str(w.get("accountType") or "").lower() == "checking" and last4.endswith(WEBPAY_LAST4)
                and str(w.get("date") or "")[:10] == WEBPAY_DATE)

    paid = sum(num(w.get("amount")) or 0.0 for w in due)
    owed = num(calcs.get("amountOwed"))
    inputs_right = all(s == 1 for s in (c1, c2, c3, c4, c5, c6, c7))
    if not due or not all(right_account(w) for w in due):
        c9 = 0.0
    elif abs(paid - TAX_DUE) <= TOL:
        c9 = 1.0
    elif owed is not None and abs(paid - owed) <= TOL:
        # Paid what CalFile showed. Full credit only if every input is right (then that IS the true balance).
        c9 = 1.0 if inputs_right else 0.4
    else:
        c9 = 0.0
    g.add("C9.webpay_tax_due", 8, c9,
          f"{len(due)} new tax_due payment(s) totalling {paid:.2f} "
          f"{[(w.get('date'), w.get('accountType'), w.get('lastFour')) for w in due]}; expected {TAX_DUE} on {WEBPAY_DATE} "
          f"checking ...{WEBPAY_LAST4}; final amountOwed={owed}")

    # ---- C10/C11: preparer fee on PayPal -------------------------------------------------------
    sent = [t for t in new_items(pp0.get("transactions"), pp1.get("transactions"))
            if str(t.get("type") or "") == "payment_sent"]

    def party(t):
        return (str(t.get("recipientEmail") or "").strip().lower(), str(t.get("recipientName") or "").strip().lower())

    def to_business(t):
        email, name = party(t)
        return email == BUSINESS_PP or BUSINESS_PP in name or name == BUSINESS_PP_NAME

    def to_personal(t):
        email, name = party(t)
        return email == PERSONAL_PP or PERSONAL_PP in name or (not email and name == PERSONAL_PP_NAME)

    business = [t for t in sent if to_business(t) and not to_personal(t)]
    usd = [t for t in business if str(t.get("currency") or "USD").upper() == "USD"]
    amounts = [num(t.get("amount")) or 0.0 for t in usd]
    fee_ok = any(abs(a - PREPARER_FEE) <= TOL for a in amounts) or (amounts and abs(sum(amounts) - PREPARER_FEE) <= TOL)
    g.add("C10.preparer_fee", 8, 1.0 if fee_ok else 0.25 if business else 0.0,
          f"{len(business)} payment(s) to {BUSINESS_PP}: {[(t.get('amount'), t.get('currency')) for t in business]}; expected {PREPARER_FEE}")

    personal = [t for t in sent if to_personal(t)]
    g.add("C11.no_personal_or_double_fee", 3, bool(sent) and not personal and len(business) == 1,
          f"{len(sent)} new payment_sent; {len(personal)} to personal account; {len(business)} to business account")

    # ---- C12: confirmation email to Gloria ------------------------------------------------------
    def recipients(e):
        return {str(r.get("email") or "").strip().lower() for k in ("to", "cc", "bcc") for r in (e.get(k) or [])
                if isinstance(r, dict)}

    outgoing = [e for e in new_items(mail0.get("emails"), mail1.get("emails"))
                if e.get("folder") not in ("drafts", "draft")
                and (e.get("folder") == "sent" or str((e.get("from") or {}).get("email") or "").lower() == DANIEL_MAIL)]
    to_gloria = [e for e in outgoing if GLORIA_MAIL in recipients(e)]

    def has_conf(e):
        if not confirmation:
            return False
        text = plain(str(e.get("subject") or "") + " " + str(e.get("body") or ""))
        squash = re.sub(r"[^a-z0-9]", "", confirmation.lower())
        return confirmation.lower() in text or squash in re.sub(r"[^a-z0-9]", "", text)

    g.add("C12.email_confirmation", 5, 1.0 if any(has_conf(e) for e in to_gloria) else 0.5 if to_gloria else 0.0,
          f"{len(to_gloria)} new email(s) to {GLORIA_MAIL}; confirmation {confirmation!r} included="
          f"{any(has_conf(e) for e in to_gloria)}")

    # ---- C13: photography CSV ----------------------------------------------------------------------
    rows = read_csv("photography_2024.csv")
    if rows is None:
        g.add("C13.photography_csv", 16, 0, "photography_2024.csv missing")
    else:
        matched, correct = set(), 0
        for r in rows:
            day = str(r.get("date") or "").strip()[:10]
            if day in PHOTO_ROWS and day not in matched:
                amount, period = PHOTO_ROWS[day]
                if eq(r.get("usd_amount"), amount) and str(r.get("period") or "").strip().lower() == period:
                    matched.add(day)
                    correct += 1
        g.add("C13.photography_csv", 16, correct / max(len(PHOTO_ROWS), len(rows)),
              f"{correct}/{len(PHOTO_ROWS)} rows right, {len(rows)} rows total; missing/wrong {sorted(set(PHOTO_ROWS) - matched)}")

    # ---- C14: unrelated return content untouched (only once filed) -----------------------------------
    problems = []
    for key in ("personalInfo", "dependents", "credits"):
        if tax1.get(key) != tax0.get(key):
            problems.append(key)
    if str(deductions.get("type") or "") != "standard":
        problems.append("deductions.type")
    if not add_ok:
        problems.append("caAdjustmentsAddition")
    if deductions.get("voluntaryContributions"):
        problems.append("voluntaryContributions")
    now_by_id = {w.get("id"): w for w in payment.get("webPaySubmissions") or []}
    for w in (tax0.get("payment") or {}).get("webPaySubmissions") or []:
        if now_by_id.get(w.get("id")) != w:
            problems.append(f"webPay {w.get('id')}")
    g.add("C14.calfile_non_targets", 3, submitted and not problems,
          f"submitted={submitted}; changed: {problems}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
