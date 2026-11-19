#!/usr/bin/env python3
"""Verifier for tahoe-offsite-closeout. Checkpoints mirror rubric.json (X*, A*, G*, C*).

All expected values were derived independently from the seeds and the images they
reference (seed/files/...), applying Owen's rules from the Gmail thread t_owen:
  1. receipt is the source of truth for amounts;
  2. company Amex ****1009 -> keep on report, Reimbursable off;
  3. shared bills: only the claimant's own card portion;
  4. emailed receipts get attached before approval; host receipts in Airbnb are used as-is;
  5. (as corrected by e_owen2) Nov 3 - Nov 7 counts; anything outside the offsite or
     already reimbursed -> reject the whole report with a one-line reason, delete nothing.
"""

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import (VAR_DIR, InfraError, load_site, mentions_amount, money_eq,  # noqa: E402
                       new_items, plain, read_csv, run)

TASK_ID, VERSION = "cua-hard/tahoe-offsite-closeout", "0.1.0"
NADIA_EXP = "usr_001"      # expensify currentUser
NADIA_AIR = "user_001"     # airbnb currentUser
HOST_AIR = "user_101"      # Michael Brennan, host of conv_201 / res_201
OWEN = "owen@fernbrook.io"

# ---- amount corrections (cents) ----------------------------------------------------
# exp_1012 venmo_payment.png: "You paid Michael Brennan $165.00", Nov 7 (typed 18000;
#          the host's board_repair_estimate.png in Airbnb says $180 - the trap).
# exp_1021 IMG_3390.png split tender: VISA ****7731 K MENSAH $160.00 (typed 39640 = whole bill).
# exp_1032 hertz_rental_record.png is the pickup ESTIMATE $342.18; Leo's email attachment
#          hertz_final_invoice.png: TOTAL CHARGED $324.18.
# exp_1051 Airbnb msg_2005 receipt_tariq.png: late checkout $60 + firewood $35 = $95 cash.
CORRECTIONS = {
    "X1.daniela_venmo_amount": ("exp_1012", 16500, 7),
    "X2.kofi_split_bill": ("exp_1021", 16000, 8),
    "X3.leo_hertz_final": ("exp_1032", 32418, 7),
    "X4.tariq_host_cash": ("exp_1051", 9500, 7),
}
# Receipts showing AMEX ****1009: rcpt_safeway.png (exp_1013), rcpt_paddle_oar.png (exp_1041).
# rcpt_fire_sign.png (exp_1043) is AMEX ****3005 -> personal, stays reimbursable.
COMPANY_CARD = {"exp_1013": "rpt_101", "exp_1041": "rpt_104"}
APPROVE = ["rpt_101", "rpt_102", "rpt_103", "rpt_104", "rpt_105"]
# rpt_106: rcpt_sunnyside.png dated 10/23/2026 (outside the offsite though typed 11/05).
# rpt_107: IMG_2231.png is the same United e-ticket HQ4T7N ($318.20, issued Oct 16) already
#          reimbursed on rpt_090 (exp_0901, united_eticket_HQ4T7N.png).
REJECT = {"X6.reject_mei": ("rpt_106", ["exp_1061", "exp_1062"]),
          "X7.reject_priya_duplicate": ("rpt_107", ["exp_1071", "exp_1072"])}
TARGET_REPORTS = APPROVE + ["rpt_106", "rpt_107"]
NON_TARGET_REPORTS = ["rpt_090", "rpt_091", "rpt_092", "rpt_093", "rpt_094", "rpt_095"]
# Expenses whose amount is expected to change / be touched by the correct run.
WORKED_EXPENSES = {"exp_1012", "exp_1021", "exp_1032", "exp_1051", "exp_1013", "exp_1041", "exp_1022"}
# Kofi's email: IMG_4466.png = Nov 2 SF->Oakland $22.40 (personal), IMG_4471.png = Nov 7
# Tahoe City -> RNO $38.75 (matches exp_1022). sha256 of seed/files/gmail/IMG_4471.png:
UBER_OK_NAME = "img_4471.png"
UBER_OK_SHA = "ab5969747f5985487c11099a9144d94245a30e7faa1473e26f4c467bd47fad59"

# ---- per-report reimbursable totals (dollars) after corrections ----------------------
# rpt_101 shuttle 64.00 + paddleboard 165.00 (Safeway 212.48 on Amex 1009 excluded) = 229.00
# rpt_102 dinner 160.00 + Uber 38.75 + Alaska 231.60                                  = 430.35
# rpt_103 dinner 186.40 + Hertz 324.18 + Chevron 58.20                                = 568.78
# rpt_104 Lyft 41.30 + Fire Sign 86.25 (Paddle & Oar 275.00 on Amex 1009 excluded)    = 127.55
# rpt_105 host cash 95.00 + Alaska 248.90 + marina parking 24.00                      = 367.90
# rpt_106 / rpt_107 rejected                                                           = 0.00
CSV_EXPECTED = {
    "78410231": ("daniela@fernbrook.io", "approved", 229.00),
    "78410244": ("kofi@fernbrook.io", "approved", 430.35),
    "78410257": ("leo@fernbrook.io", "approved", 568.78),
    "78410263": ("ingrid@fernbrook.io", "approved", 127.55),
    "78410278": ("tariq@fernbrook.io", "approved", 367.90),
    "78410282": ("mei@fernbrook.io", "rejected", 0.00),
    "78410296": ("priya@fernbrook.io", "rejected", 0.00),
}
PAYOUT_TOTAL = 1723.58  # 229.00 + 430.35 + 568.78 + 127.55 + 367.90


def cents(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def stripped_name(url):
    """Basename of a receipt URL without sitehost's 8-hex-digit upload prefix, lowercased."""
    name = str(url or "").split("?")[0].rstrip("/").split("/")[-1]
    return re.sub(r"^[0-9a-f]{8}[-_]", "", name, flags=re.I).lower()


def uploaded_sha(url):
    path = VAR_DIR / "files" / "expensify" / str(url or "").split("?")[0].split("/")[-1]
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    except OSError:
        return None


def rejection_reason_given(new_comments, report_id):
    """A non-empty reason by Nadia on the report: 'Report rejected: <why>' or a separate comment."""
    for c in new_comments:
        if c.get("reportId") != report_id or c.get("authorId") != NADIA_EXP:
            continue
        text = plain(c.get("text"))
        if c.get("type") == "status_change":
            m = re.match(r"report rejected\s*[:\-–]\s*(.*)$", text)
            if m and m.group(1).strip(" .:-"):
                return True
        elif c.get("type") == "comment" and text.strip(" .:-"):
            return True
    return False


def money_cell(value):
    return re.sub(r"(?i)usd|[$,\s]", "", str(value or ""))


def evaluate(g):
    exp0, exp1 = load_site("expensify")
    air0, air1 = load_site("airbnb")
    mail0, mail1 = load_site("gmail")
    for name, state, keys in (("expensify", exp1, ("expenses", "reports", "comments")),
                              ("airbnb", air1, ("messages", "conversations")),
                              ("gmail", mail1, ("emails",))):
        for key in keys:
            if not isinstance(state.get(key), list):
                raise InfraError(f"{name} current state has no '{key}' list")

    e_before = {e["id"]: e for e in exp0["expenses"]}
    e_after = {e.get("id"): e for e in exp1["expenses"]}
    r_before = {r["id"]: r for r in exp0["reports"]}
    r_after = {r.get("id"): r for r in exp1["reports"]}
    if any(r not in r_before for r in TARGET_REPORTS + NON_TARGET_REPORTS):
        raise InfraError("seed is missing expected reports")
    # Expenses/reports *can* be deleted from the UI (Owen explicitly says not to), so a missing
    # item is scored as the model's failure rather than treated as infrastructure trouble.

    # ---- X1-X4 amount corrections -----------------------------------------------------
    corrected = 0
    for check_id, (eid, want, weight) in CORRECTIONS.items():
        now = e_after.get(eid)
        got = cents(now.get("amount")) if now else None
        ok = got == want
        corrected += ok
        g.add(check_id, weight, ok, f"{eid} amount={got if now else 'DELETED'} (was {e_before[eid]['amount']}), expected {want}")

    # ---- X5 company Amex -> non-reimbursable -------------------------------------------
    hits = sum(1 for eid, rid in COMPANY_CARD.items()
               if e_after.get(eid) and e_after[eid].get("reimbursable") is False
               and e_after[eid].get("reportId") == rid)
    wrongly_off = sorted(eid for eid, e in e_after.items()
                         if e.get("reportId") in APPROVE and eid not in COMPANY_CARD
                         and e.get("reimbursable") is False
                         and e_before.get(eid, {}).get("reimbursable") is not False)
    g.add("X5.company_amex_flags", 8, (hits - len(wrongly_off)) / len(COMPANY_CARD),
          f"{hits}/2 company-card expenses switched off on their report; wrongly switched off: {wrongly_off}")

    # ---- X6/X7 rejections --------------------------------------------------------------
    new_comments = new_items(exp0["comments"], exp1["comments"])
    for check_id, (rid, eids) in REJECT.items():
        rep = r_after.get(rid)
        rejected = bool(rep) and rep.get("status") == "open" and rep.get("isRetracted") is True
        reason = rejection_reason_given(new_comments, rid)
        kept = all(eid in e_after for eid in eids)
        g.add(check_id, 7, rejected and reason and kept,
              f"{rid}: status={rep.get('status') if rep else 'DELETED'} retracted={rep.get('isRetracted') if rep else None} "
              f"reason={reason} expenses_kept={kept}")

    # ---- X8 approvals ------------------------------------------------------------------
    approved = [rid for rid in APPROVE if r_after.get(rid, {}).get("status") == "approved"]
    g.add("X8.approve_valid_reports", 8, len(approved) / len(APPROVE), f"approved {approved}")

    # ---- X9 Kofi's Uber receipt ----------------------------------------------------------
    uber = e_after.get("exp_1022") or {}
    url = uber.get("receiptUrl")
    good = bool(uber.get("hasReceipt")) and bool(url) and (
        stripped_name(url) == UBER_OK_NAME or uploaded_sha(url) == UBER_OK_SHA)
    g.add("X9.kofi_uber_receipt", 5, good, f"exp_1022 hasReceipt={uber.get('hasReceipt')} receiptUrl={url}")

    # ---- X10 nothing else touched (only scores once real work was done) -------------------
    touched = []
    for rid in NON_TARGET_REPORTS:
        a, b = r_before[rid], r_after.get(rid)
        if not b or any(a.get(k) != b.get(k) for k in ("status", "total", "isRetracted")):
            touched.append(rid)
    for eid, a in e_before.items():
        b = e_after.get(eid)
        if a.get("reportId") in NON_TARGET_REPORTS:
            if not b or any(a.get(k) != b.get(k) for k in ("amount", "reimbursable", "receiptUrl")):
                touched.append(eid)
        elif a.get("reportId") in TARGET_REPORTS and eid not in WORKED_EXPENSES:
            if not b or cents(b.get("amount")) != cents(a.get("amount")):
                touched.append(eid)
    g.add("X10.non_targets_untouched", 6, corrected > 0 and not touched,
          f"changed: {touched}; correct amount fixes so far: {corrected}")

    # ---- A1 Airbnb reply to the host -----------------------------------------------------
    host_convs = {c.get("id") for c in air1["conversations"]
                  if c.get("id") == "conv_201" or c.get("hostId") == HOST_AIR or HOST_AIR in (c.get("participantIds") or [])}
    sent = [m for m in new_items(air0["messages"], air1["messages"])
            if m.get("conversationId") in host_convs and m.get("senderId") == NADIA_AIR and not m.get("deletedAt")]
    bodies = [m.get("body", "") for m in sent]
    says_165 = any(mentions_amount(b, 165) for b in bodies)
    # Quoting the $180 estimate next to the $165 actually paid is fine; telling him $180 is not.
    says_180 = any(mentions_amount(b, 180) and not mentions_amount(b, 165) for b in bodies)
    who = any(w in plain(b) for b in bodies for w in ("daniela", "venmo"))
    a1 = 0.0 if (says_180 or not says_165) else 1.0 if who else 0.5
    g.add("A1.reply_host_paddleboard", 8, a1,
          f"{len(sent)} new message(s) to host; $165={says_165} $180-only={says_180} names Daniela/Venmo={who}")

    # ---- G1 reply to Owen with the payout total ------------------------------------------
    def recipients(e):
        return {(r.get("email") or "").lower() for k in ("to", "cc", "bcc") for r in (e.get(k) or [])
                if isinstance(r, dict)}
    to_owen = [e for e in new_items(mail0["emails"], mail1["emails"])
               if e.get("folder") == "sent" and OWEN in recipients(e)]
    total_ok = any(mentions_amount(f"{e.get('subject', '')} {e.get('body', '')}", PAYOUT_TOTAL) for e in to_owen)
    g.add("G1.reply_owen_total", 7, total_ok, f"{len(to_owen)} sent email(s) to Owen; mentions ${PAYOUT_TOTAL}={total_ok}")

    # ---- C1 CSV ----------------------------------------------------------------------------
    rows = read_csv("offsite_closeout.csv")
    if rows is None:
        g.add("C1.closeout_csv", 15, 0, "offsite_closeout.csv missing")
        return
    correct = 0
    for number, (email, decision, amount) in CSV_EXPECTED.items():
        match = [r for r in rows if re.sub(r"[#\s]", "", r.get("report_number", "")) == number]
        if (len(match) == 1 and match[0].get("employee_email", "").lower() == email
                and match[0].get("decision", "").lower() == decision
                and money_eq(money_cell(match[0].get("reimbursable_total")), amount)):
            correct += 1
    g.add("C1.closeout_csv", 15, correct / max(len(CSV_EXPECTED), len(rows)),
          f"{correct}/{len(CSV_EXPECTED)} rows right, {len(rows)} rows total")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
