#!/usr/bin/env python3
"""Verifier for dad-visits-airbnb-settlement. Checkpoint ids/weights mirror rubric.json.

Expected values are derived independently from the seeds:
  * Bookings golden: Airbnb reservations (seed/airbnb.json) + James's receipts (gmail g07/g08)
    + Megan's "October?" email (g09) on top of the seed Bookings tab.
  * Split rules: Gmail thread "Dad visits - how we split the Airbnbs" (g01 James 8/2 rules,
    g04 Megan 10/1 cleaning-fee amendment, g05 James "starting with stays that check in in
    October, no redoing Aug/Sep", g06 Emily confirms).
Replay inputs for settle.py are built here (hidden months/mutations) and their expected
outputs are computed by `reference_settle` below; the constants are hard-coded and
cross-checked against it at start-up.
"""

import csv
import os
import re
import shutil
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import (OUTPUT_DIR, InfraError, amounts, load_site, new_items, plain,  # noqa: E402
                       read_csv, run, run_replay)

TASK_ID, VERSION = "cua-hard/dad-visits-airbnb-settlement", "0.1.0"
TOL = 0.02
PEOPLE = ("Emily", "James", "Megan")
COLS = ["code", "check_in", "check_out", "status", "guests", "paid_by", "total", "service_fee", "cleaning_fee", "refund"]
JAMES, MEGAN = "james.carter.oak@gmail.com", "megan.ruiz.nc@outlook.com"


def B(code, ci, co, status, guests, paid_by, total, svc, clean, refund):
    return dict(zip(COLS, [code, ci, co, status, guests, paid_by, total, svc, clean, refund]))


# ---------------------------------------------------------------- golden Bookings tab
# Rows 2-8 and HMG3Y7M4KS are the seed values (already settled / correct).
HISTORY = [
    B("HMC8A1K2Q7", "2026-08-07", "2026-08-10", "confirmed", "Emily", "Emily", "594.02", "66.31", "50.00", "0.00"),
    B("HMJ4W8N2D5", "2026-08-14", "2026-08-16", "confirmed", "James", "James", "595.30", "66.46", "90.00", "0.00"),
    B("HM4RT7Z9PL", "2026-08-21", "2026-08-24", "confirmed", "Emily; James; Megan", "Emily", "1223.66", "136.60", "125.00", "0.00"),
    B("HMQ2V6B8XK", "2026-09-04", "2026-09-07", "confirmed", "Megan", "Emily", "594.02", "66.31", "50.00", "0.00"),
    B("HMJ7P3R9T1", "2026-09-11", "2026-09-13", "confirmed", "James", "James", "595.30", "66.46", "90.00", "0.00"),
    B("HMT5K9C3MZ", "2026-09-18", "2026-09-20", "cancelled", "Emily", "Emily", "731.40", "81.65", "85.00", "367.38"),
    B("HMW3N8F6JD", "2026-09-29", "2026-10-02", "confirmed", "Emily; Megan", "Emily", "1223.66", "136.60", "125.00", "0.00"),
]
THANKSGIVING = B("HMG3Y7M4KS", "2026-11-25", "2026-11-29", "confirmed", "Emily; James; Megan", "Emily", "1578.55", "176.22", "125.00", "0.00")
KEY_ROWS = {
    # airbnb res_307: cancelled 10/6, refundAmount 367.38 (also gmail g11)
    "HMR6D2H7QA": B("HMR6D2H7QA", "2026-10-09", "2026-10-11", "cancelled", "Megan", "Emily", "731.40", "81.65", "85.00", "367.38"),
    # airbnb res_308: altered 10/12 to 10/16-10/19, priceBreakdown total 1223.66 (gmail g12)
    "HMZ9L4T2WC": B("HMZ9L4T2WC", "2026-10-16", "2026-10-19", "confirmed", "James", "Emily", "1223.66", "136.60", "125.00", "0.00"),
    # airbnb res_309 + Megan g09 ("castle weekend ... Oct 23-26, you and me")
    "HMK7S3X5PB": B("HMK7S3X5PB", "2026-10-23", "2026-10-26", "confirmed", "Emily; Megan", "Emily", "1329.24", "148.39", "100.00", "0.00"),
    # James g08 receipt replaces g07 (2 nights, total 595.30, service 66.46, cleaning 90)
    "HMJ2F8V6LN": B("HMJ2F8V6LN", "2026-10-30", "2026-11-01", "confirmed", "James", "James", "595.30", "66.46", "90.00", "0.00"),
    # airbnb res_310: altered 10/27 to 11/1-11/3, total 417.22 / 46.58 / 50
    "HMV8B5Q1RE": B("HMV8B5Q1RE", "2026-11-01", "2026-11-03", "confirmed", "Megan", "Emily", "417.22", "46.58", "50.00", "0.00"),
}
GOLDEN = HISTORY + list(KEY_ROWS.values()) + [THANKSGIVING]
PRIVATE = ("HMF2C9D7UX", "HMU6E3W9KF")  # Emily's own trips with Sam: must not be logged

# ---------------------------------------------------------------- hidden replay inputs
M3_NOVEMBER = GOLDEN + [
    # James-paid, host-style full refund: net 0, pool must floor at 0 (no negative split)
    B("HMN1C4X8RA", "2026-11-12", "2026-11-14", "cancelled", "James; Megan", "James", "690.43", "80.23", "95.00", "690.43"),
    # paid by Megan, shared with Emily
    B("HMN2M5P7KD", "2026-11-13", "2026-11-16", "confirmed", "Emily; Megan", "Megan", "835.70", "93.29", "90.00", "0.00"),
    # Emily-paid partial-refund cancellation
    B("HMN3E8T2VB", "2026-11-19", "2026-11-21", "cancelled", "Emily", "Emily", "731.40", "81.65", "85.00", "426.24"),
]  # HMJ2F8V6LN (10/30-11/01) must stay out of November
M4_DECEMBER = GOLDEN + [
    B("HMD1A7K3QZ", "2026-11-30", "2026-12-03", "confirmed", "Emily; James; Megan", "James", "1223.66", "136.60", "125.00", "0.00"),  # Nov
    B("HMD2B4R8WX", "2026-12-04", "2026-12-06", "confirmed", "Megan", "James", "595.30", "66.46", "90.00", "0.00"),
    B("HMD3F6N1TY", "2026-12-11", "2026-12-14", "confirmed", "James; Megan", "James", "1329.24", "148.39", "100.00", "0.00"),
    B("HMD4H2L9UC", "2026-12-18", "2026-12-20", "cancelled", "Emily", "Emily", "731.40", "81.65", "85.00", "367.38"),
    B("HMD5K8P3JE", "2026-12-30", "2027-01-02", "confirmed", "Emily; James; Megan", "Megan", "1578.55", "176.22", "125.00", "0.00"),  # Dec
    B("HMD6Q5S7GM", "2027-01-01", "2027-01-04", "confirmed", "James", "James", "594.02", "66.31", "50.00", "0.00"),  # Jan
]
M5_UNKNOWN = GOLDEN + [
    B("HMX9D4D2AD", "2026-11-14", "2026-11-16", "confirmed", "Emily; Dad", "Emily", "417.22", "46.58", "50.00", "0.00"),
]

# Expected (share, paid, balance). R1/R2 by hand from the thread rules (also match the
# Settlement tab's existing 2026-09 rows); R3 reproduces rubric's M3 numbers; R4 from
# reference_settle (hand-checked: Emily 30+33.33+364.02+41.67+425.78 = 894.80, ...).
EXP_OCT = {"Emily": (1012.07, 2916.92, 1904.85), "James": (1572.36, 595.30, -977.06), "Megan": (927.80, 0.00, -927.80)}
EXP_SEP = {"Emily": (1110.46, 2181.70, 1071.24), "James": (595.30, 595.30, 0.00), "Megan": (1071.24, 0.00, -1071.24)}
EXP_NOV = {"Emily": (1368.28, 2300.93, 932.65), "James": (514.11, 0.00, -514.11), "Megan": (1254.25, 835.70, -418.55)}
EXP_DEC = {"Emily": (894.80, 364.02, -530.78), "James": (1286.05, 1924.54, 638.49), "Megan": (1686.26, 1578.55, -107.71)}
EXP_ZERO = {p: (0.0, 0.0, 0.0) for p in PEOPLE}


def reference_settle(rows, month):
    """Independent implementation of the agreed rules (Fractions, HALF_UP to cents)."""
    share = {p: Fraction(0) for p in PEOPLE}
    paid = {p: Fraction(0) for p in PEOPLE}
    for r in rows:
        if r["check_in"][:7] != month:
            continue
        total, svc, clean, refund = (Fraction(r[k]) for k in ("total", "service_fee", "cleaning_fee", "refund"))
        net = total - refund
        guests = [g.strip() for g in r["guests"].split(";") if g.strip()]
        if r["status"] == "confirmed" and month >= "2026-10":
            clean_part = clean
            for p in PEOPLE:
                share[p] += clean / 3
        else:
            clean_part = Fraction(0)
        pool = max(Fraction(0), net - svc - clean_part)
        for g in guests:
            share[g] += pool / len(guests)
        share[r["paid_by"]] += net - pool - clean_part
        paid[r["paid_by"]] += net

    def cents(x):
        return float((Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.01"), ROUND_HALF_UP))
    out = {}
    for p in PEOPLE:
        s, pd = cents(share[p]), cents(paid[p])
        out[p] = (s, pd, round(pd - s, 2))
    return out


for _rows, _month, _exp in ((GOLDEN, "2026-10", EXP_OCT), (GOLDEN, "2026-09", EXP_SEP), (M3_NOVEMBER, "2026-11", EXP_NOV),
                            (M4_DECEMBER, "2026-12", EXP_DEC), (GOLDEN, "2027-01", EXP_ZERO)):
    _got = reference_settle(_rows, _month)
    assert all(abs(a - b) < 0.006 for p in PEOPLE for a, b in zip(_got[p], _exp[p])), (_month, _got)


# ---------------------------------------------------------------- normalisation helpers
def num(v):
    s = str(v if v is not None else "").strip().replace("$", "").replace(",", "")
    s = re.sub(r"(?i)\s*usd$", "", s).strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def near(a, b, tol=TOL):
    x = num(a)
    return x is not None and abs(x - float(b)) <= tol + 1e-9


def norm_date(v):
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else s


def guest_set(v):
    return {g.strip().lower() for g in str(v or "").split(";") if g.strip()}


def row_matches(row, exp, blank_amounts_ok=False):
    """List of mismatching columns of an agent row vs. an expected booking dict."""
    bad = []
    for c in ("code", "status", "paid_by"):
        if str(row.get(c, "")).strip().lower() != exp[c].lower():
            bad.append(c)
    for c in ("check_in", "check_out"):
        if norm_date(row.get(c)) != exp[c]:
            bad.append(c)
    if guest_set(row.get("guests")) != guest_set(exp["guests"]):
        bad.append("guests")
    for c in ("total", "service_fee", "cleaning_fee", "refund"):
        val = str(row.get(c, "")).strip()
        if blank_amounts_ok and val == "":
            continue
        if not near(val, exp[c]):
            bad.append(c)
    return bad


# ---------------------------------------------------------------- sheets
def cell_text(cell):
    if not isinstance(cell, dict):
        return ""
    value = cell.get("value")
    if value is None or str(value).strip() == "" or str(value).startswith("="):
        comp = cell.get("computed")
        if comp is not None and str(comp).strip() != "":
            return str(comp).strip()
    return str(value if value is not None else "").strip()


def table(sheet):
    """Rows of a sheet as dicts keyed by the (lowercased) header in row 1."""
    rows = {}
    for key, cell in (sheet.get("data") or {}).items():
        m = re.fullmatch(r"([A-Z]+)(\d+)", key)
        if m:
            rows.setdefault(int(m[2]), {})[m[1]] = cell_text(cell)
    header = rows.get(1, {})
    names = {col: h.strip().lower() for col, h in header.items() if h.strip()}
    out = []
    for r in sorted(rows):
        if r == 1:
            continue
        d = {names[c]: v for c, v in rows[r].items() if c in names}
        if any(v for v in d.values()):
            out.append(d)
    return out


def find_sheet(workbook, name):
    for sh in workbook.get("sheets") or []:
        if str(sh.get("name", "")).strip().lower() == name.lower():
            return sh
    raise InfraError(f"sheet {name!r} not found in workbook")


def by_code(rows):
    found = {}
    for r in rows:
        code = str(r.get("code", "")).strip().upper()
        if code:
            found.setdefault(code, []).append(r)
    return found


# ---------------------------------------------------------------- replay
def write_bookings_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    os.chmod(path, 0o644)


def read_out(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            data = [r for r in reader if any(c.strip() for c in r)]
    except (OSError, UnicodeDecodeError, csv.Error):
        return None, None
    if not data:
        return [], {}
    header = [h.strip().lower() for h in data[0]]
    rows = {}
    for r in data[1:]:
        d = dict(zip(header, [c.strip() for c in r]))
        rows.setdefault(d.get("person", "").strip().lower(), []).append(d)
    return header, rows


def compare_out(rows, exp):
    good = []
    for p in PEOPLE:
        match = rows.get(p.lower(), [])
        if len(match) == 1 and all(near(match[0].get(k), v) for k, v in zip(("share", "paid", "balance"), exp[p])):
            good.append(p)
    return good


class Replayer:
    def __init__(self):
        self.script = OUTPUT_DIR / "settle.py"
        self.tmp = Path(tempfile.mkdtemp(prefix="settle_replay_"))
        os.chmod(self.tmp, 0o777)
        self.n = 0

    def go(self, rows, month):
        self.n += 1
        case = self.tmp / f"case{self.n}"
        case.mkdir()
        os.chmod(case, 0o777)
        src = case / "bookings.csv"
        out = case / "out.csv"
        write_bookings_csv(src, rows)
        code, log = run_replay(self.script, {"BOOKINGS_CSV": str(src), "MONTH": month, "OUT_CSV": str(out)}, timeout=60)
        return code, log, out

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------- evaluate
def evaluate(g):
    sh0, sh1 = load_site("google_sheets")
    mail0, mail1 = load_site("gmail")
    load_site("airbnb")  # read-only in this task, but its state must exist

    book0 = table(find_sheet(sh0, "Bookings"))
    book1 = table(find_sheet(sh1, "Bookings"))
    sett0 = table(find_sheet(sh0, "Settlement"))
    sett1 = table(find_sheet(sh1, "Settlement"))
    codes1 = by_code(book1)
    codes0 = by_code(book0)

    # ---- R1-R6: replay settle.py ------------------------------------------
    rp = Replayer()
    try:
        for cid, w, rows, month, exp in (("R1.replay_october", 9, GOLDEN, "2026-10", EXP_OCT),
                                         ("R2.replay_september_old_rule", 9, GOLDEN, "2026-09", EXP_SEP),
                                         ("R3.replay_november_mixed", 10, M3_NOVEMBER, "2026-11", EXP_NOV),
                                         ("R4.replay_december_boundary", 9, M4_DECEMBER, "2026-12", EXP_DEC)):
            code, log, out = rp.go(rows, month)
            if code != 0:
                g.add(cid, w, 0, f"exit {code}: {log[-300:]!r}")
                continue
            header, got = read_out(out)
            if header is None or not out.is_file():
                g.add(cid, w, 0, "exit 0 but OUT_CSV missing/unreadable")
                continue
            good = compare_out(got, exp)
            g.add(cid, w, len(good) == 3, f"MONTH={month}: correct persons {good}; got {got}; expected {exp}")

        code, log, out = rp.go(M5_UNKNOWN, "2026-11")
        g.add("R5.replay_invalid_person", 8, code == 2 and not out.exists(),
              f"guests 'Emily; Dad' in 2026-11: exit {code}, OUT_CSV exists={out.exists()}")

        code, log, out = rp.go(GOLDEN, "2027-01")
        header, got = read_out(out) if out.is_file() else (None, None)
        ok = code == 0 and header == ["person", "share", "paid", "balance"] and len(compare_out(got, EXP_ZERO)) == 3
        g.add("R6.replay_empty_month", 7, ok, f"MONTH=2027-01: exit {code}, header {header}, rows {got}")
    finally:
        rp.close()

    # ---- C1: settlement_2026-10.csv ---------------------------------------
    path = OUTPUT_DIR / "settlement_2026-10.csv"
    if not path.is_file() or path.is_symlink():
        g.add("C1.settlement_csv", 9, 0, "settlement_2026-10.csv missing")
    else:
        header, got = read_out(path)
        if header != ["person", "share", "paid", "balance"]:
            g.add("C1.settlement_csv", 9, 0, f"header {header}")
        else:
            good = compare_out(got, EXP_OCT)
            g.add("C1.settlement_csv", 9, len(good) / 3, f"correct persons {good}; got {got}")

    # ---- C2: bookings.csv --------------------------------------------------
    rows = read_csv("bookings.csv")
    if rows is None:
        g.add("C2.bookings_csv", 8, 0, "bookings.csv missing")
    else:
        try:
            with (OUTPUT_DIR / "bookings.csv").open(newline="", encoding="utf-8-sig") as f:
                header = [h.strip().lower() for h in next(csv.reader(f), [])]
        except (OSError, UnicodeDecodeError, csv.Error):
            header = []
        if header != COLS:
            g.add("C2.bookings_csv", 8, 0, f"header {header}")
        else:
            found = by_code(rows)
            right = [c for c, exp in KEY_ROWS.items() if len(found.get(c, [])) == 1 and not row_matches(found[c][0], exp)]
            score = len(right) / len(KEY_ROWS)
            leaked = [c for c in PRIVATE if c in found]
            if leaked:
                score *= 0.5
            g.add("C2.bookings_csv", 8, score, f"key rows right {right}; private trips present {leaked}")

    # ---- S1-S5: Bookings tab ----------------------------------------------
    def sheet_row_check(cid, weight, code, blank_ok=False, fields=None):
        match = codes1.get(code, [])
        if len(match) != 1:
            return g.add(cid, weight, 0, f"{len(match)} rows with code {code}")
        bad = row_matches(match[0], KEY_ROWS[code], blank_amounts_ok=blank_ok)
        if fields is not None:
            bad = [b for b in bad if b in fields]
        return g.add(cid, weight, not bad, f"{code}: mismatched {bad}; row {match[0]}")

    s_scores = [
        sheet_row_check("S1.sheet_cancelled_stay", 3, "HMR6D2H7QA"),
        sheet_row_check("S2.sheet_shortened_stay", 3, "HMZ9L4T2WC"),
    ]
    # S3: the missing stay must be newly added (it wasn't in the seed)
    if "HMK7S3X5PB" in codes0:
        raise InfraError("seed unexpectedly already contains HMK7S3X5PB")
    s_scores.append(sheet_row_check("S3.sheet_missing_stay", 3, "HMK7S3X5PB"))
    s_scores.append(sheet_row_check("S4.sheet_james_receipt", 3, "HMJ2F8V6LN"))
    s_scores.append(sheet_row_check("S5.sheet_moved_stay", 2, "HMV8B5Q1RE", blank_ok=True,
                                    fields={"check_in", "check_out", "total", "service_fee", "cleaning_fee", "refund"}))

    # ---- S6: Settlement tab October rows ----------------------------------
    oct_rows = [r for r in sett1 if str(r.get("month", "")).strip() == "2026-10"]
    oct0 = [r for r in sett0 if str(r.get("month", "")).strip() == "2026-10"]
    if oct0:
        raise InfraError("seed unexpectedly already has 2026-10 settlement rows")
    if len(oct_rows) > 3:
        s6 = g.add("S6.sheet_settlement_rows", 7, 0, f"{len(oct_rows)} rows for 2026-10 (max 3)")
    else:
        grouped = {}
        for r in oct_rows:
            grouped.setdefault(str(r.get("person", "")).strip().lower(), []).append(r)
        good = compare_out(grouped, EXP_OCT)
        s6 = g.add("S6.sheet_settlement_rows", 7, len(good) / 3, f"correct persons {good}; rows {oct_rows}")
    s_scores.append(s6)

    # ---- E1: email to James and Megan --------------------------------------
    sent = [e for e in new_items(mail0.get("emails"), mail1.get("emails")) if e.get("folder") == "sent"]

    def recipients(e):
        return {(r.get("email") or "").strip().lower() for k in ("to", "cc", "bcc") for r in (e.get(k) or [])}

    def says(e, value):
        text = (e.get("subject") or "") + " " + (e.get("body") or "")
        return any(abs(abs(a) - value) <= TOL for a in amounts(text))

    to_james = [e for e in sent if JAMES in recipients(e)]
    to_megan = [e for e in sent if MEGAN in recipients(e)]
    james_ok = any(says(e, 977.06) for e in to_james)   # EXP_OCT James balance
    megan_ok = any(says(e, 927.80) for e in to_megan)   # EXP_OCT Megan balance
    if james_ok and megan_ok:
        e1 = 1.0
    elif james_ok or megan_ok:
        e1 = 0.5
    elif to_james and to_megan:
        e1 = 0.25
    else:
        e1 = 0.0
    g.add("E1.email_siblings", 7, e1, f"{len(sent)} new sent; to James {len(to_james)} (977.06 {james_ok}), "
                                      f"to Megan {len(to_megan)} (927.80 {megan_ok})")

    # ---- P1: protect history (only once October work was done) -------------
    did_work = any(s > 0 for s in s_scores)
    problems = []
    for exp in HISTORY + [THANKSGIVING]:
        match = codes1.get(exp["code"], [])
        if len(match) != 1 or row_matches(match[0], exp):
            problems.append(f"{exp['code']} changed/missing/duplicated")
    for p in PRIVATE:
        if p in codes1:
            problems.append(f"private trip {p} logged")
    for r0 in sett0:
        month, person = str(r0.get("month", "")).strip(), str(r0.get("person", "")).strip().lower()
        if month not in ("2026-08", "2026-09"):
            continue
        match = [r for r in sett1 if str(r.get("month", "")).strip() == month
                 and str(r.get("person", "")).strip().lower() == person]
        if len(match) != 1 or not all(near(match[0].get(k), num(r0.get(k))) for k in ("share", "paid", "balance")):
            problems.append(f"settlement {month}/{person} changed")
    g.add("P1.protect_history", 3, did_work and not problems,
          f"october work done={did_work}; problems {problems}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
