#!/usr/bin/env python3
"""Verifier for halvorsen-plateful-pricefile. Checkpoints mirror rubric.json (F*, U1, A*).

Expected values are derived by hand from the seeds:
  * Gmail g02 (Marta, rev B): use HMP_PriceList_2027_revB.csv; for a repeated Item No the
    line with the latest Revised date stands; prices take effect Monday 2026-12-07.
  * Gmail g03 (Dana): only Halvorsen Mill & Pantry items that are Active in Supplier Items,
    matched on supplier + SKU; drop items whose Contract Ends >= effective date; drop DISC;
    set DISC items to Discontinued; tick Price Review when new case > Case Price * 1.08;
    put the effective date in Suppliers / Prices Effective; don't type prices into Airtable.
  * Yahoo ym_002 (Plateful v3 spec): metric KG/L/EA cost units, case_qty 3 dp,
    cost_per_unit 4 dp, YYYY-MM-DD dates, send to fennwick-7q2k@imports.plateful.app
    (shared imports@plateful.app is retired).
"""

import csv
import io
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, VAR_DIR, InfraError, load_site, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/halvorsen-plateful-pricefile", "0.1.0"

PLATEFUL_ADDR = "fennwick-7q2k@imports.plateful.app"   # ym_002, private import address
OLD_ADDR = "imports@plateful.app"                       # ym_001 / ym_003, retired
LOCAL_COPY = "halvorsen_plateful_prices.csv"
EFFECTIVE = "2026-12-07"                                # g02: "takes effect Monday, December 7"

# ym_002 conversion factors
TO_METRIC = {"LB": ("KG", 0.45359237), "OZ": ("KG", 0.028349523125), "GAL": ("L", 3.785411784),
             "FL OZ": ("L", 0.0295735295625), "KG": ("KG", 1.0), "L": ("L", 1.0), "EA": ("EA", 1.0)}

# Rows the file must contain: Airtable Item Code -> (rev B line used, Airtable Case Price).
# rev B line = (Item No, Pack, Size, UOM, Price, Price Basis); repeated Item Nos use the
# 2026-11-16 corrections (10433 0.668/LB, 10480 6.48/LB, 13110 71.25 CS).
# Case price: CS -> Price; LB -> Price * Pack * Size (lb); EA -> Price * Pack * Size (pieces).
EXPECTED_SOURCE = {
    "FP-1001": ("10412", 1, 50, "LB", 0.612, "LB", 28.90),
    "FP-1002": ("10433", 1, 50, "LB", 0.668, "LB", 30.25),    # rev B (v1 0.648 -> 32.40)
    "FP-1003": ("10450", 1, 25, "LB", 21.75, "CS", 20.90),
    "FP-1005": ("10480", 1, 25, "LB", 6.48, "LB", 149.50),     # rev B (v1 6.20 -> 155.00)
    "FP-1010": ("11205", 1, 50, "LB", 38.50, "CS", 36.80),
    "FP-1011": ("11212", 12, 2, "LB", 27.36, "CS", 25.20),
    "FP-1012": ("11218", 1, 25, "LB", 24.95, "CS", 23.90),     # listed twice, identical
    "FP-1020": ("13110", 1, 5, "KG", 71.25, "CS", 61.80),      # rev B (v1 64.50)
    "FP-1022": ("13130", 1, 25, "LB", 96.75, "CS", 88.00),     # contract ended 2026-12-06 < 12-07
    "FP-1030": ("14010", 6, 16, "FL OZ", 119.70, "CS", 152.00),  # list pack 6x16 fl oz, not Airtable 4x32
    "FP-1031": ("14105", 1, 5, "GAL", 48.90, "CS", 46.50),
    "FP-1032": ("14120", 6, 1, "L", 74.40, "CS", 70.80),
    "FP-1040": ("15030", 1, 25, "LB", 7.28, "LB", 171.25),
    "FP-1050": ("16010", 1, 25, "LB", 18.60, "CS", 18.60),
    "FP-1051": ("16025", 9, 3, "LB", 41.85, "CS", 39.60),
    "FP-1052": ("16100", 6, 18, "OZ", 89.70, "CS", 84.00),
    "FP-1060": ("17005", 10, 500, "EA", 0.0118, "EA", 56.50),
    "FP-1061": ("17010", 1, 1000, "EA", 64.20, "CS", 61.10),
    "FP-1071": ("18215", 1, 25, "LB", 4.18, "LB", 97.10),
}
ORDINARY = ["FP-1001", "FP-1003", "FP-1010", "FP-1011", "FP-1012", "FP-1031", "FP-1032", "FP-1040",
            "FP-1050", "FP-1051", "FP-1052", "FP-1060", "FP-1061", "FP-1071"]
REVB = {"FP-1002": 33.40, "FP-1005": 162.00, "FP-1020": 71.25}


def _expected_row(src):
    sku, pack, size, uom, price, basis, _ = src
    unit, factor = TO_METRIC[uom]
    qty = pack * size * factor
    case = price if basis == "CS" else price * pack * size
    return {"sku": sku, "case": round(case, 2), "unit": unit, "qty": qty}


EXPECTED = {code: _expected_row(src) for code, src in EXPECTED_SOURCE.items()}
# Sanity anchors from the rubric: FP-1001 30.60/22.680 KG, FP-1060 59.00/5000 EA, FP-1052 89.70/3.062 KG.

# Price Review targets: new case > Airtable Case Price * 1.08 (strict).
# 1002 +10.4%, 1005 +8.4%, 1011 +8.6%, 1020 +15.3%, 1022 +9.9%; 1071 is +7.6% (no).
REVIEW_TARGETS = {"rec_" + c.lower().replace("-", "") for c, src in EXPECTED_SOURCE.items()
                  if EXPECTED[c]["case"] > src[6] * 1.08}
assert REVIEW_TARGETS == {"rec_fp1002", "rec_fp1005", "rec_fp1011", "rec_fp1020", "rec_fp1022"}

DISC_RECS = ["rec_fp1041", "rec_fp1053"]   # 15045 DISC only in rev B correction; 16120 DISC
HMP_ACTIVE_CODES = set(EXPECTED) | {"FP-1021", "FP-1041", "FP-1053"}  # Active HMP items in seed
EFF_FORMS = {"2026-12-07", "12/07/2026", "12/7/2026", "2026/12/07", "dec 7, 2026", "december 7, 2026"}
CPU_TOL_ABS, CPU_TOL_REL = 0.0006, 0.0005


# ------------------------------------------------------------------ helpers
def num(value):
    try:
        return float(str(value).strip().replace("$", "").replace(",", "").replace("USD", "").strip())
    except (TypeError, ValueError):
        return None


def close(value, expected, tol):
    v = num(value)
    return v is not None and abs(v - expected) <= tol + 1e-9


def cpu_ok(value, exp):
    tol = max(CPU_TOL_ABS, CPU_TOL_REL * exp["case"] / exp["qty"])
    candidates = (exp["case"] / exp["qty"], exp["case"] / round(exp["qty"], 3))
    return any(close(value, c, tol) for c in candidates)


def row_ok(row, code):
    exp = EXPECTED[code]
    return bool(row) and (row.get("supplier_sku", "").strip() == exp["sku"]
                          and close(row.get("case_price"), exp["case"], 0.005)
                          and row.get("cost_unit", "").strip() == exp["unit"]
                          and close(row.get("case_qty"), exp["qty"], 0.002)
                          and cpu_ok(row.get("cost_per_unit"), exp))


def recipients(msg):
    out = set()
    for key in ("to", "cc", "bcc"):
        for r in msg.get(key) or []:
            email = r.get("email") if isinstance(r, dict) else r
            if email:
                out.add(str(email).strip().lower())
    return out


def csv_uploads(msg):
    return [a for a in msg.get("attachments") or []
            if a.get("source") == "upload" and str(a.get("name", "")).lower().strip().endswith(".csv")]


def attachment_path(att):
    m = re.search(r"/files/([^/]+)/([^?#]+)", str(att.get("url") or ""))
    if not m:
        raise InfraError(f"upload attachment has unexpected url {att.get('url')!r}")
    path = VAR_DIR / "files" / "yahoo_mail" / unquote(m.group(1)) / unquote(m.group(2))
    if not path.is_file():
        raise InfraError(f"uploaded attachment file missing: {path}")
    return path


def parse_csv(text):
    """Rows keyed by lowercase header, plus the ordered list of item codes as written."""
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = [{(k or "").strip().lower(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items()}
                for r in reader]
    except csv.Error:
        return [], {}
    by_code = {}
    for r in rows:   # Plateful: a repeated item_code -> last row wins
        by_code[r.get("item_code", "")] = r
    return rows, by_code


def norm_fields(fields):
    return {k: v for k, v in (fields or {}).items() if v not in (None, "", False, [])}


def table(state, tid):
    t = (state.get("tables") or {}).get(tid)
    if not isinstance(t, dict) or not isinstance(t.get("records"), list):
        raise InfraError(f"airtable table {tid} missing")
    return {r.get("id"): r for r in t["records"]}


# ------------------------------------------------------------------ evaluation
def evaluate(g):
    y0, y1 = load_site("yahoo_mail")
    a0, a1 = load_site("airtable")
    load_site("gmail")  # must exist; nothing to grade there

    # ---- find the uploaded file --------------------------------------------
    seen = {m.get("id") for m in y0.get("messages") or []}
    sent = [m for m in y1.get("messages") or []
            if m.get("id") not in seen and m.get("status") == "sent" and csv_uploads(m)]
    order = {id(m): i for i, m in enumerate(sent)}
    sent.sort(key=lambda m: (str(m.get("sentAt") or m.get("date") or m.get("updatedAt") or ""), order[id(m)]))
    to_new = [m for m in sent if PLATEFUL_ADDR in recipients(m)]
    chosen = (to_new or sent or [None])[-1]

    upload_text, rows, by_code = None, [], {}
    if chosen is not None:
        raw = attachment_path(csv_uploads(chosen)[-1]).read_bytes()
        upload_text = raw.decode("utf-8-sig", errors="replace")
        rows, by_code = parse_csv(upload_text)
    found = upload_text is not None
    codes = [r.get("item_code", "") for r in rows]
    price_hits = sum(1 for c in EXPECTED if c in by_code and close(by_code[c].get("case_price"), EXPECTED[c]["case"], 0.005))
    gated = found and price_hits >= 5
    why = "no uploaded CSV found" if not found else f"{len(rows)} rows, {price_hits}/19 expected case prices right"

    # ---- F1 ordinary rows ----------------------------------------------------
    good = [c for c in ORDINARY if row_ok(by_code.get(c), c)]
    g.add("F1.rows_ordinary", 18, len(good) / len(ORDINARY) if found else 0,
          f"{len(good)}/14 ordinary rows right; wrong/missing {sorted(set(ORDINARY) - set(good))}" if found else why)

    # ---- F2 rev B prices -----------------------------------------------------
    hits = [c for c, p in REVB.items() if c in by_code and close(by_code[c].get("case_price"), p, 0.005)]
    g.add("F2.revb_prices", 8, len(hits) / 3 if found else 0,
          f"rev B prices right for {hits}; got " + str({c: by_code.get(c, {}).get("case_price") for c in REVB}) if found else why)

    # ---- F3 dedupe -------------------------------------------------------------
    dups = sorted({c for c in codes if codes.count(c) > 1})
    g.add("F3.dedupe", 6, gated and not dups and "FP-1012" in codes, f"duplicate codes {dups}; {why}")

    # ---- F4 discontinued -------------------------------------------------------
    f4 = 0.5 * ("FP-1053" not in codes) + 0.5 * ("FP-1041" not in codes)
    g.add("F4.discontinued_out", 6, f4 if gated else 0,
          f"FP-1053 in file={'FP-1053' in codes}, FP-1041 in file={'FP-1041' in codes}; {why}")

    # ---- F5 contract boundary --------------------------------------------------
    if "FP-1021" in codes:
        f5 = 0.0
    elif "FP-1022" in by_code and close(by_code["FP-1022"].get("case_price"), 96.75, 0.005):
        f5 = 1.0
    else:
        f5 = 0.5
    g.add("F5.contract_boundary", 8, f5 if gated else 0,
          f"FP-1021 in file={'FP-1021' in codes}, FP-1022 price={by_code.get('FP-1022', {}).get('case_price')}; {why}")

    # ---- F6 non-targets --------------------------------------------------------
    strays = sorted({c for c in codes if c not in HMP_ACTIVE_CODES})
    g.add("F6.non_targets", 6, gated and not strays, f"item codes outside HMP Active items: {strays}; {why}")

    # ---- F7 pack from list -----------------------------------------------------
    g.add("F7.pack_from_list", 5, found and row_ok(by_code.get("FP-1030"), "FP-1030"),
          f"FP-1030 row {by_code.get('FP-1030')}; expect 119.70 / 2.839 L / 42.1619" if found else why)

    # ---- F8 effective date ----------------------------------------------------
    dates = [r.get("effective_date", "") for r in rows]
    if found and dates and all(d == EFFECTIVE for d in dates):
        f8 = 1.0
    elif found and dates and all(d.strip().lower() in EFF_FORMS for d in dates):
        f8 = 0.5
    else:
        f8 = 0.0
    g.add("F8.effective_date", 6, f8, f"dates in file {sorted(set(dates))}" if found else why)

    # ---- F9 local copy ---------------------------------------------------------
    def canon(text):
        return text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    local = OUTPUT_DIR / LOCAL_COPY
    local_text = None
    if local.is_file() and not local.is_symlink():
        local_text = local.read_bytes().decode("utf-8-sig", errors="replace")
    f9 = found and local_text is not None and canon(local_text) == canon(upload_text)
    g.add("F9.local_copy", 5, f9, f"local copy exists={local_text is not None}, identical={bool(f9)}" if found else why)

    # ---- U1 sent to Plateful ---------------------------------------------------
    if to_new:
        u1 = 1.0
    elif any(OLD_ADDR in recipients(m) for m in sent):
        u1 = 0.3
    else:
        u1 = 0.0
    g.add("U1.sent_to_plateful", 6, u1,
          f"{len(sent)} new sent mail(s) with CSV upload; recipients {[sorted(recipients(m)) for m in sent]}")

    # ---- Airtable --------------------------------------------------------------
    items0, items1 = table(a0, "tbl_items"), table(a1, "tbl_items")
    sup0, sup1 = table(a0, "tbl_suppliers"), table(a1, "tbl_suppliers")

    def field(recs, rid, fid):
        return ((recs.get(rid) or {}).get("fields") or {}).get(fid)

    disc = [r for r in DISC_RECS if field(items1, r, "fld_status") == "Discontinued"]
    g.add("A1.discontinued_status", 7, 0.5 * len(disc), f"Discontinued now: {disc}")

    ticked = {rid for rid in items1 if field(items1, rid, "fld_review") is True
              and field(items0, rid, "fld_review") is not True}
    hit, wrong = ticked & REVIEW_TARGETS, ticked - REVIEW_TARGETS
    g.add("A2.price_review", 9, max(0, len(hit) - len(wrong)) / len(REVIEW_TARGETS),
          f"newly ticked targets {sorted(hit)}, wrong ticks {sorted(wrong)}")

    eff = str(field(sup1, "rec_sup_hmp", "fld_s_eff") or "").strip()
    a3 = eff.lower() in EFF_FORMS
    g.add("A3.prices_effective", 5, a3, f"rec_sup_hmp Prices Effective = {eff!r}")

    problems = []
    for rid, rec0 in items0.items():
        rec1 = items1.get(rid)
        if rec1 is None:
            problems.append(f"{rid} deleted")
            continue
        f0, f1 = norm_fields(rec0.get("fields")), norm_fields(rec1.get("fields"))
        if (rec0.get("fields") or {}).get("fld_supplier") != "Halvorsen Mill & Pantry":
            if f0 != f1:
                problems.append(f"{rid} (non-HMP) changed")
            continue
        for fid in ("fld_case", "fld_cprice", "fld_cends", "fld_sku", "fld_supplier"):
            if f0.get(fid) != f1.get(fid):
                problems.append(f"{rid}.{fid} {f0.get(fid)!r}->{f1.get(fid)!r}")
        if rid not in DISC_RECS and f0.get("fld_status") != f1.get("fld_status"):
            problems.append(f"{rid}.fld_status {f0.get('fld_status')!r}->{f1.get('fld_status')!r}")
    added = sorted(set(items1) - set(items0))
    if added:
        problems.append(f"records added to Supplier Items {added}")
    for rid, rec0 in sup0.items():
        if rid == "rec_sup_hmp":
            continue
        rec1 = sup1.get(rid)
        if rec1 is None or norm_fields(rec0.get("fields")) != norm_fields(rec1.get("fields")):
            problems.append(f"supplier {rid} changed")
    did_work = bool(disc) or bool(hit) or a3
    g.add("A4.protect_base", 5, did_work and not problems,
          f"violations {problems[:8]}{'...' if len(problems) > 8 else ''}; target Airtable work done={did_work}")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
