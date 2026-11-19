#!/usr/bin/env python3
"""Verifier for q4-renewal-closeout.

Checkpoint ids/weights mirror rubric.json. Every expected value below is derived
by hand from seed/*.json, input/cpq_quotes.csv and the rules in the seeded mail:
  msg_0001 (Elena's checklist): Closed Won only when the envelope is Completed;
      amount = annual fee of the executed quote version (file name -> CPQ);
      close date = UK date the envelope completed; written non-renewal ->
      Closed Lost on the email date, amount unchanged, void open envelope with
      reason "Customer not renewing"; file executed FY27 envelopes in
      "FY27 Renewals - Executed"; kickoff "FY27 Kickoff - <Account>" with the
      signer at the agreed UK time, not over existing events.
  msg_0002 (Marcus amendment): kickoffs are 45 minutes; add
      marcus.reed@acmecorp.com when annual fee >= $60k.
December in London is GMT, so UK wall time == UTC throughout.
"""

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, new_items, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/q4-renewal-closeout", "0.1.1"
SARAH = "sarah.chen@acmecorp.com"
MARCUS = "marcus.reed@acmecorp.com"

# ---------------------------------------------------------------- Salesforce outcomes
# opp-301 Northwind: env_402 completed 2026-12-09T15:42Z, file ..._Q-2291_v2.pdf ->
#   CPQ Q-2291 v2 annual_fee 88800 (TCV 266400; v1 96000 voided env_401; v3 draft).
# opp-302 Bluepeak: env_403 completed 2026-12-10T18:05Z (UK 18:05, still 12-10), Q-2307 v1 -> 57600.
# opp-305 Summit Dental Group: env_406 completed 2026-12-08T11:20Z, Q-2315 v1 -> 27600.
# opp-308 Lakeside: env_409 completed 2026-12-11T16:30Z, Q-2320 v1, 24 months -> annual 63000 (TCV 126000).
# opp-304 Cobalt: Graham Holt's formal non-renewal msg_0041 2026-12-11T14:20Z; amount stays 41000.
OUTCOMES = [
    ("C1.northwind_won", 10, "opp-301", "Closed Won", 88800, "2026-12-09"),
    ("C2.bluepeak_won", 8, "opp-302", "Closed Won", 57600, "2026-12-10"),
    ("C3.summit_group_won", 8, "opp-305", "Closed Won", 27600, "2026-12-08"),
    ("C4.lakeside_won", 8, "opp-308", "Closed Won", 63000, "2026-12-11"),
    ("C5.cobalt_lost", 8, "opp-304", "Closed Lost", 41000, "2026-12-11"),
]
# Harbor (customer-signed only, Marcus holding), Summit Dental Partners (unsigned),
# Pinecrest (already won), Ferro (2027-01), Driftwood (already lost), non-renewals 311/313.
UNTOUCHED_OPPS = ["opp-303", "opp-306", "opp-307", "opp-309", "opp-310", "opp-311", "opp-313"]

# ---------------------------------------------------------------- DocuSign
FY27_FOLDER = "folder_fy27"
EXECUTED = {"env_402", "env_403", "env_406", "env_409"}  # completed FY27 renewals not yet filed (env_408 already is)
COBALT_ENV = "env_405"
VOID_REASON = "customer not renewing"

# ---------------------------------------------------------------- Calendar kickoffs
# (check id, title needle, signer, start UTC, end UTC, exact guest set excluding Sarah)
KICKOFFS = [
    # Dana: Tue 15 14:00 clashes evt_111 Forecast review 13:30-15:00 -> Wed 16 10:00; 88800 >= 60k -> Marcus.
    ("M1.kickoff_northwind", "northwind", "dana.whitfield@northwindlogistics.co.uk",
     "2026-12-16T10:00", "2026-12-16T10:45", {"dana.whitfield@northwindlogistics.co.uk", MARCUS}),
    # Jordan: Thu 17 10:00 am Eastern (EST, UTC-5) = 15:00 UK; 57600 < 60k -> no Marcus.
    ("M2.kickoff_bluepeak", "bluepeak", "jordan.pierce@bluepeakhealth.com",
     "2026-12-17T15:00", "2026-12-17T15:45", {"jordan.pierce@bluepeakhealth.com"}),
    # Megan moved Fri 18 13:30 to Mon 21 same time (msg_0052); 27600 < 60k.
    ("M3.kickoff_summit_group", "summit dental group", "megan.shaw@summitdentalgroup.co.uk",
     "2026-12-21T13:30", "2026-12-21T14:15", {"megan.shaw@summitdentalgroup.co.uk"}),
    # Aoife: Wed 16 15:00 clashes evt_114 QBR 14:30-15:30 -> Thu 17 11:00; annual 63000 >= 60k -> Marcus.
    ("M4.kickoff_lakeside", "lakeside", "aoife.brennan@lakesidecu.ie",
     "2026-12-17T11:00", "2026-12-17T11:45", {"aoife.brennan@lakesidecu.ie", MARCUS}),
]
# Renewals that must not get a (new) kickoff: (title needle, customer emails from seed mail/DocuSign).
NO_KICKOFF = [
    ("harbor", {"liam.doyle@harborfreightways.co.uk"}),
    ("cobalt", {"graham.holt@cobaltretail.co.uk", "hannah.price@cobaltretail.co.uk"}),
    ("summit dental partners", {"claire.summers@summitdentalpartners.co.uk", "ravi.mehta@summitdentalpartners.co.uk"}),
    ("pinecrest", {"oskar.lind@pinecrest.se"}),  # evt_112 already on 12-15 15:00
    ("ferro", {"giulia.rossi@ferrocomponents.it"}),
    ("driftwood", {"fiona.clarke@driftwoodhotels.co.uk"}),
]

# ---------------------------------------------------------------- CSV
# Sarah's (user-1) type=Renewal opportunities with seed closeDate in 2026-10..12 (9 rows);
# excludes FY26 renewals (2025), Ferro (2027-01) and the non-Renewal Northwind add-on.
CSV_HEADER = ["opportunity", "stage", "amount", "close_date", "kickoff"]
CSV_ROWS = {
    "Northwind Logistics - FY27 Renewal": ("Closed Won", 88800, "2026-12-09", "2026-12-16 10:00"),
    "Bluepeak Health - FY27 Renewal": ("Closed Won", 57600, "2026-12-10", "2026-12-17 15:00"),
    "Harbor Freightways - FY27 Renewal": ("Negotiation", 72000, "2026-12-18", ""),
    "Cobalt Retail Group - FY27 Renewal": ("Closed Lost", 41000, "2026-12-11", ""),
    "Summit Dental Group - FY27 Renewal": ("Closed Won", 27600, "2026-12-08", "2026-12-21 13:30"),
    "Summit Dental Partners - FY27 Renewal": ("Negotiation", 31200, "2026-12-22", ""),
    "Pinecrest Software - FY27 Renewal": ("Closed Won", 48000, "2026-12-03", "2026-12-15 15:00"),
    "Lakeside Credit Union - FY27 Renewal": ("Closed Won", 63000, "2026-12-11", "2026-12-17 11:00"),
    "Driftwood Hotels - FY27 Renewal": ("Closed Lost", 22000, "2026-10-20", ""),
}


# ================================================================ helpers
def num(value):
    """'$88,800', '88800.00', '88800 USD', 88800 -> 88800.0; None if unparseable."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = re.sub(r"(?i)usd|\$|,|\s", "", str(value or ""))
    try:
        return float(text)
    except ValueError:
        return None


def amount_eq(a, b, tol=0.5):
    x = num(a)
    return x is not None and abs(x - float(b)) <= tol


def utc(value):
    """ISO timestamp -> aware UTC datetime. Naive values are UK wall time (== UTC in December)."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.fromisoformat(text[:19])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def guest_set(event):
    out = set()
    for gst in event.get("guests") or []:
        email = gst.get("email") if isinstance(gst, dict) else gst
        email = re.sub(r"\s+", "", str(email or "")).lower()
        if email and email != SARAH:
            out.add(email)
    return out


def by_id(items, key, site):
    if not isinstance(items, list):
        raise InfraError(f"{site}: expected a list of records")
    return {item.get(key): item for item in items if isinstance(item, dict)}


def opportunity_changed(before, after):
    return (before.get("stage") != after.get("stage")
            or not amount_eq(after.get("amount"), num(before.get("amount")) or 0)
            or str(before.get("closeDate") or "")[:10] != str(after.get("closeDate") or "")[:10])


# ================================================================ evaluate
def evaluate(g):
    sf0, sf1 = load_site("salesforce")
    ds0, ds1 = load_site("docusign")
    cal0, cal1 = load_site("google_calendar")
    load_site("yahoo_mail")  # read-only in this task, but its state must exist

    # ---- Salesforce ---------------------------------------------------------
    opp0 = by_id(sf0.get("opportunities"), "opportunityId", "salesforce initial")
    opp1 = by_id(sf1.get("opportunities"), "opportunityId", "salesforce current")
    needed = [o for _, _, o, *_ in OUTCOMES] + UNTOUCHED_OPPS
    missing = [o for o in needed if o not in opp0 or o not in opp1]
    if missing:
        raise InfraError(f"opportunities missing from salesforce state: {missing}")

    changed = {oid for oid in needed if opportunity_changed(opp0[oid], opp1[oid])}
    protected_changed = sorted(changed.intersection(UNTOUCHED_OPPS))
    for check_id, weight, oid, stage, amount, close in OUTCOMES:
        o = opp1[oid]
        ok = (o.get("stage") == stage and amount_eq(o.get("amount"), amount)
              and str(o.get("closeDate") or "")[:10] == close)
        g.add(check_id, weight, 1.0 if ok else 0.0,
              f"{oid}: stage={o.get('stage')!r} amount={o.get('amount')!r} close={str(o.get('closeDate'))[:10]}; "
              f"expected {stage}/{amount}/{close}")

    # ---- DocuSign -----------------------------------------------------------
    env0 = by_id(ds0.get("envelopes"), "id", "docusign initial")
    env1 = by_id(ds1.get("envelopes"), "id", "docusign current")
    gone = [e for e in env0 if e not in env1]
    if gone:
        raise InfraError(f"envelopes missing from docusign state: {sorted(gone)}")

    filed = {eid for eid, e in env1.items()
             if e.get("folderId") == FY27_FOLDER and (env0.get(eid) or {}).get("folderId") != FY27_FOLDER}
    k1 = max(0.0, (len(filed & EXECUTED) - len(filed - EXECUTED)) / len(EXECUTED))
    g.add("K1.file_executed", 6, k1, f"newly filed in FY27 folder: {sorted(filed)}; expected {sorted(EXECUTED)}")

    cob0, cob1 = env0[COBALT_ENV], env1[COBALT_ENV]
    k2 = 0.0
    reason_ok = False
    if cob1.get("status") == "voided":
        k2 = 0.6
        texts = [str(h.get("details") or "") for h in new_items(cob0.get("history"), cob1.get("history"))
                 if str(h.get("action") or "").lower() == "voided"]
        texts += [str(cob1.get(k) or "") for k in ("voidReason", "voidedReason") if cob1.get(k) != cob0.get(k)]
        texts += [str(a.get("details") or "") for a in new_items(ds0.get("auditLog"), ds1.get("auditLog"))
                  if a.get("envelopeId") == COBALT_ENV and "void" in str(a.get("action") or "").lower()]
        reason_ok = any(VOID_REASON in t.lower() for t in texts)
        if reason_ok:
            k2 = 1.0
    g.add("K2.void_cobalt", 6, k2, f"env_405 status={cob1.get('status')!r}; reason recorded: {reason_ok}")

    altered = [eid for eid, e in env0.items() if eid != COBALT_ENV and env1[eid].get("status") != e.get("status")]
    sent_new = [e.get("id") for e in new_items(ds0.get("envelopes"), ds1.get("envelopes"))
                if str(e.get("status") or "draft").lower() != "draft"]  # e.g. re-sent order forms
    moved = any(e.get("folderId") != env1[eid].get("folderId") for eid, e in env0.items())

    # ---- Calendar -----------------------------------------------------------
    if not isinstance(cal1.get("events"), list) or not isinstance(cal0.get("events"), list):
        raise InfraError("google_calendar: events list missing")
    fresh = [e for e in new_items(cal0["events"], cal1["events"])
             if isinstance(e, dict) and str(e.get("status") or "confirmed").lower() != "cancelled"]

    kickoff_observed = False
    for check_id, needle, signer, start, end, guests in KICKOFFS:
        cands = [e for e in fresh if needle in str(e.get("title") or "").lower() or signer in guest_set(e)]
        best, info = 0.0, "no candidate"
        for e in cands:
            if utc(e.get("start")) != at(start):
                continue
            s = 0.5 + (0.25 if utc(e.get("end")) == at(end) else 0) + (0.25 if guest_set(e) == guests else 0)
            if s > best:
                best, info = s, f"start ok, end={e.get('end')}, guests={sorted(guest_set(e))}"
        if cands and best == 0.0:
            info = "candidates at " + ", ".join(str(e.get("start")) for e in cands)
        if len(cands) > 1:
            best *= 0.5
            info += f" ({len(cands)} candidates, halved)"
        kickoff_observed = kickoff_observed or bool(cands)
        g.add(check_id, 6, best, f"{info}; expected {start}-{end[11:]}Z with {sorted(guests)}")

    bad = []
    for needle, emails in NO_KICKOFF:
        if any(needle in str(e.get("title") or "").lower() or (guest_set(e) & emails) for e in fresh):
            bad.append(needle)
    # Protection checks each use their own violations. Only an untouched task earns none.
    csv_path = OUTPUT_DIR / "q4_renewals.csv"
    task_started = bool(changed or filed or moved or altered or sent_new or cob0.get("status") != cob1.get("status")
                        or kickoff_observed or bad or csv_path.is_file())
    g.add("C6.protect_open_renewals", 6, task_started and not protected_changed,
          f"changed protected opps: {protected_changed}; task activity={task_started}")
    violations = len(altered) + len(sent_new)
    g.add("K3.protect_envelopes", 3, max(0.0, 1.0 - 0.5 * violations) if task_started else 0.0,
          f"status changed: {altered}; new sent envelopes: {sent_new}; task activity={task_started}")
    g.add("M5.no_extra_kickoffs", 5, max(0.0, 1.0 - 0.5 * len(bad)) if task_started else 0.0,
          f"kickoffs for not-to-book renewals: {bad}; task activity={task_started}")
    g.add("O1.closeout_csv", 8, *csv_score(csv_path))


def csv_score(path):
    if not path.is_file() or path.is_symlink():
        return 0.0, "q4_renewals.csv missing"
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        return 0.0, f"unreadable csv: {exc}"
    if not table or [h.strip().lower() for h in table[0]] != CSV_HEADER:
        return 0.0, f"bad header: {table[0] if table else None}"
    rows = [r for r in table[1:] if any(c.strip() for c in r)]
    correct, seen = 0, set()
    for r in rows:
        r = [c.strip() for c in r] + [""] * (5 - len(r))
        name, stage, amount, close, kickoff = r[:5]
        exp = CSV_ROWS.get(name)
        if not exp or name in seen:
            continue
        if (stage.lower() == exp[0].lower() and amount_eq(amount, exp[1])
                and close == exp[2] and kickoff == exp[3]):
            correct += 1
            seen.add(name)
    return correct / max(len(CSV_ROWS), len(rows)), f"{correct}/{len(CSV_ROWS)} rows right, {len(rows)} data rows"


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
