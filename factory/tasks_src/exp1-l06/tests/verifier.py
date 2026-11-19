#!/usr/bin/env python3
"""Verifier for january-new-hire-records. Checkpoints mirror rubric.json (B*, G*, S*, C*).

Expected terms were derived independently from the seeds and input PDFs:
  * DocuSign envelopes: only `completed` envelopes bind; `voided` / `delivered` / `draft` don't.
      env_201 voided  Raman_Priya_Offer_Letter.pdf (165,000)     -> ignore
      env_202 complete Raman_Priya_Offer_Letter_rev1.pdf          -> Senior Data Engineer, 2027-01-11, 172,000
      env_203 complete Lindqvist_Marcus_Offer_Letter.pdf           -> Product Manager, 2027-01-04, 150,000
      env_204 complete Lindqvist_Marcus_Amendment_1.pdf (12/10)    -> start moved to 2027-01-19
      env_205 complete Petrova_Elena_Offer_Letter.pdf              -> Product Designer, 2027-01-11, 118,000
      env_206 delivered Petrova_Elena_Amendment_1.pdf (Sr/128k)    -> not signed, ignore
      env_207 complete Fischer_Leo_Offer_Letter_SAE.pdf            -> Senior Account Executive, 2027-01-04, 105,000
      env_208 complete Ortiz_Sam_Offer_Letter.pdf                  -> Backend Engineer, 2027-01-11, 140,000
      env_209 complete Sato_Hana_Offer_Letter.pdf                  -> Site Reliability Engineer, 2027-01-19, 155,000
      env_210 complete Avery_Jordan_Offer_Letter.pdf               -> Customer Success Manager, 2027-01-04, 85,000
      env_211 complete Haddad_Nadia (Jan 4) but Greenhouse app-8 rejected "Candidate withdrew" + pinned note -> not joining
      env_212 complete Brandt_Owen_Offer_Letter.pdf                -> start 2027-02-01 (not January)
      env_213 delivered Carvalho_Ines                              -> unsigned, not final
  * Sam Ortiz: only hearsay in #recruiting (m_r17); app-5 still active, 12/12 note confirms Jan 11 -> create.
  * Jordan Avery already exists in BambooHR (id 33, m_p02) -> no new record, but still Hired in Greenhouse + CSV.
  * Greenhouse vs signed mismatches (Theo's thread m_p04): Priya salary 165k->172k, Marcus start
    01-04->01-19, Leo title/salary AE 95k->SAE 105k, Owen start 01-25->02-01. Elena/Sam/Hana/Jordan match.
  * BambooHR department ids: Engineering=2, Product=3, Design=4, Sales=5 (seed/bamboohr.json departments).
  * Greenhouse Hired stage = stage-<jobId>-8 (seed jobStages, stageType "hired").
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, mentions_amount, new_items, plain, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/january-new-hire-records", "0.1.0"

# name -> (title, hireDate, payRate, BambooHR departmentId, department name, Greenhouse app id, jobId)
TARGETS = {
    "priya raman": ("Senior Data Engineer", "2027-01-11", 172000, 2, "engineering", "app-1", "job-1"),
    "marcus lindqvist": ("Product Manager", "2027-01-19", 150000, 3, "product", "app-2", "job-2"),
    "elena petrova": ("Product Designer", "2027-01-11", 118000, 4, "design", "app-3", "job-3"),
    "leo fischer": ("Senior Account Executive", "2027-01-04", 105000, 5, "sales", "app-4", "job-4"),
    "sam ortiz": ("Backend Engineer", "2027-01-11", 140000, 2, "engineering", "app-5", "job-5"),
    "hana sato": ("Site Reliability Engineer", "2027-01-19", 155000, 2, "engineering", "app-6", "job-6"),
}
JORDAN = ("jordan avery", "Customer Success Manager", "2027-01-04", 85000, "app-7", "job-7")
COHORT_CSV = {n: (t[0], t[1], t[2]) for n, t in TARGETS.items()}
COHORT_CSV[JORDAN[0]] = (JORDAN[1], JORDAN[2], JORDAN[3])
HIRED_APPS = {t[5]: t[6] for t in TARGETS.values()}
HIRED_APPS[JORDAN[4]] = JORDAN[5]
OWEN_APP = "app-9"  # moving Owen (Feb start, signed) is allowed either way
NEAR_NAME_EMPLOYEE = 14  # Priya Ramanathan, must stay untouched
JORDAN_EMPLOYEE = 33
ROSA = "U01"
THEO_PARENT = "m_p04"
CSV_HEADER = ["name", "title", "start_date", "base_salary"]

# All cohort first/last names: used to cut a Slack message into per-person windows.
COHORT_WORDS = ["priya", "raman", "marcus", "lindqvist", "elena", "petrova", "leo", "fischer", "sam", "ortiz",
                "hana", "sato", "jordan", "avery", "nadia", "haddad", "owen", "brandt", "ines", "carvalho"]
NAME_RE = re.compile(r"\b(" + "|".join(COHORT_WORDS) + r")\b")


# ------------------------------------------------------------------ normalisers
def norm_name(first, last):
    return f"{(first or '').strip()} {(last or '').strip()}".lower()


def norm_title(title):
    t = re.sub(r"\s+", " ", str(title or "").strip().lower())
    return re.sub(r"\bsr\b\.?", "senior", t)


def norm_date(value):
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})(?:$|[T ])", str(value or ""))
    return m.group(1) if m else str(value or "").strip()


def to_int(value):
    """172000, '172000', '$172,000', '172000.00' -> 172000; anything else -> None."""
    if value is None or isinstance(value, bool):
        return None
    s = re.sub(r"(?i)\s*(usd|per year|/yr|/year)\s*$", "", str(value).strip())
    s = s.replace("$", "").replace(",", "").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) else None


def pay_of(emp):
    pay = to_int(emp.get("payRate"))
    if pay is None:
        hist = emp.get("payChangeHistory") or []
        if hist:
            pay = to_int(hist[-1].get("amount"))
    return pay


def dept_ok(emp, dept_id, dept_name):
    d = emp.get("departmentId")
    return str(d).strip() == str(dept_id) or str(d).strip().lower() == dept_name


# ------------------------------------------------------------------ Slack matching
PATTERNS = {
    "priya": (("priya", "raman"), lambda s: mentions_amount(s, 172000) or re.search(r"\b172\s?k\b", s)),
    "marcus": (("marcus", "lindqvist"),
               lambda s: re.search(r"2027-01-19|\bjan(?:uary)?\.?\s+19(?:th)?\b|\b19(?:th)?\s+jan|(?<![\d/])0?1/19(?!\d)", s)),
    "leo": (("leo", "fischer"), lambda s: mentions_amount(s, 105000) or re.search(r"\b105\s?k\b", s)),
    "owen": (("owen", "brandt"),
             lambda s: re.search(r"2027-02-01|\bfeb(?:ruary)?\.?\s+0?1(?:st)?\b(?!/)|\b0?1(?:st)?\s+feb|(?<![\d/])0?2/0?1(?!\d)", s)),
}


def windows(text):
    """Text pieces that each talk about one person: name -> next cohort name, plus the clause around it."""
    body = plain(text)
    pieces = []
    hits = list(NAME_RE.finditer(body))
    for i, m in enumerate(hits):
        end = len(body)
        for nxt in hits[i + 1:]:
            if nxt.group(1) not in _same_person(m.group(1)):
                end = nxt.start()
                break
        pieces.append(body[m.start():end])
    pieces += re.split(r"\n|;|\||•|(?<=[a-z0-9)])\.\s", body)
    return pieces


def _same_person(word):
    for first, last in zip(COHORT_WORDS[::2], COHORT_WORDS[1::2]):
        if word in (first, last):
            return (first, last)
    return (word,)


def person_hit(text, key):
    names, value = PATTERNS[key]
    for piece in windows(text):
        if any(re.search(rf"\b{n}\b", piece) for n in names) and value(piece):
            return True
    return False


# ------------------------------------------------------------------ CSV
def read_cohort_csv():
    path = OUTPUT_DIR / "january_new_hires.csv"
    if not path.is_file() or path.is_symlink():
        return None, "missing"
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = [r for r in reader]
    except (UnicodeDecodeError, csv.Error) as exc:
        return None, f"unreadable: {exc}"
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return None, "empty"
    header = [h.strip().lower() for h in rows[0]]
    if sorted(header) != sorted(CSV_HEADER) or len(header) != len(CSV_HEADER):
        return None, f"header {rows[0]}"
    return [dict(zip(header, [c.strip() for c in r])) for r in rows[1:]], "ok"


# ------------------------------------------------------------------ evaluate
def evaluate(g):
    bh0, bh1 = load_site("bamboohr")
    gh0, gh1 = load_site("greenhouse")
    sl0, sl1 = load_site("slack")
    load_site("docusign")  # information source only; must still be readable

    # ---- integrity -------------------------------------------------------
    emp_before = {e.get("id"): e for e in bh0.get("employees") or []}
    emp_after = {e.get("id"): e for e in bh1.get("employees") or []}
    if not emp_before or set(emp_before) - set(emp_after):
        raise InfraError(f"seed employees missing from final state: {sorted(set(emp_before) - set(emp_after), key=str)}")
    app_before = {a.get("id"): a for a in gh0.get("applications") or []}
    app_after = {a.get("id"): a for a in gh1.get("applications") or []}
    if not app_before or set(app_before) - set(app_after):
        raise InfraError(f"seed applications missing from final state: {sorted(set(app_before) - set(app_after))}")
    if not isinstance(sl1.get("messages"), dict):
        raise InfraError("slack current state has no messages map")

    # ---- BambooHR: new employees ------------------------------------------
    created = new_items(bh0.get("employees"), bh1.get("employees"))
    by_name = {}
    for e in created:
        by_name.setdefault(norm_name(e.get("firstName"), e.get("lastName")), []).append(e)

    checks = (("B1.priya_revised_salary", 9, "priya raman"), ("B2.marcus_amended_start", 9, "marcus lindqvist"),
              ("B3.elena_unsigned_amendment", 9, "elena petrova"), ("B4.leo_signed_title_salary", 9, "leo fischer"),
              ("B5.sam_despite_hearsay", 7, "sam ortiz"), ("B6.hana_clean", 5, "hana sato"))
    for check_id, weight, name in checks:
        title, date, pay = TARGETS[name][:3]
        recs = by_name.get(name, [])
        if len(recs) != 1:
            g.add(check_id, weight, 0, f"{len(recs)} new BambooHR record(s) for {name}; expected exactly 1", core=check_id != "B6.hana_clean")
            continue
        e = recs[0]
        ok = (norm_title(e.get("jobTitle")) == norm_title(title) and norm_date(e.get("hireDate")) == date
              and pay_of(e) == pay)
        g.add(check_id, weight, ok,
              f"{name}: title={e.get('jobTitle')!r} hireDate={e.get('hireDate')!r} pay={e.get('payRate')!r}; "
              f"expected {title} / {date} / {pay}", core=check_id != "B6.hana_clean")

    n_created_targets = sum(1 for n in TARGETS if by_name.get(n))
    worked = n_created_targets >= 3
    pre = f"{n_created_targets}/6 targets created"

    nadia = by_name.get("nadia haddad", [])
    g.add("B7.nadia_withdrawn_not_created", 7, worked and not nadia,
          f"new Nadia Haddad records: {len(nadia)}; {pre}", core=True)
    wrong = {n: len(by_name.get(n, [])) for n in ("owen brandt", "ines carvalho") if by_name.get(n)}
    g.add("B8.owen_ines_not_created", 6, worked and not wrong, f"wrongly created: {wrong or 'none'}; {pre}", core=True)

    dup_jordan = len(by_name.get(JORDAN[0], []))
    near_same = emp_after[NEAR_NAME_EMPLOYEE] == emp_before[NEAR_NAME_EMPLOYEE]
    g.add("B9.no_duplicates", 4, worked and not dup_jordan and near_same,
          f"new Jordan Avery records: {dup_jordan}; Priya Ramanathan (id 14) unchanged: {near_same}; {pre}")

    good = []
    for name, (_, _, _, dept_id, dept_name, _, _) in TARGETS.items():
        recs = by_name.get(name, [])
        email = name.replace(" ", ".") + "@fernhill.io"
        if recs and all(dept_ok(e, dept_id, dept_name) and str(e.get("email") or "").strip().lower() == email
                        for e in recs):
            good.append(name)
    g.add("B10.department_email", 5, len(good) / 6, f"department+email right for {good}")

    # ---- Greenhouse ---------------------------------------------------------
    hired = [app for app, job in HIRED_APPS.items() if app_after[app].get("currentStageId") == f"stage-{job}-8"]
    g.add("G1.greenhouse_hired", 7, len(hired) / 7, f"moved to Hired: {hired}")
    touched = [a for a, before in app_before.items()
               if a not in HIRED_APPS and a != OWEN_APP
               and (app_after[a].get("currentStageId") != before.get("currentStageId")
                    or app_after[a].get("status") != before.get("status"))]
    g.add("G2.greenhouse_protect", 3, len(hired) >= 3 and not touched,
          f"non-target applications changed: {touched or 'none'}; {len(hired)} targets hired")

    # ---- Slack: reply in Theo's thread ------------------------------------------
    threads = sl1.get("threads") or {}

    def in_theo_thread(msg):
        tid = msg.get("threadId")
        if not tid:
            return False
        if tid == THEO_PARENT:
            return True
        t = threads.get(tid) if isinstance(threads, dict) else None
        return isinstance(t, dict) and t.get("parentMessageId") == THEO_PARENT

    seen_ids = {m.get("messageId") for m in (sl0.get("messages") or {}).get("people-ops") or []}
    posts = {m.get("messageId"): m for m in (sl1["messages"].get("people-ops") or [])
             if m.get("messageId") not in seen_ids and m.get("senderId") == ROSA}
    if isinstance(threads, dict):  # replies may also live only inside threads[...].replies
        for t in threads.values():
            if isinstance(t, dict) and t.get("parentMessageId") == THEO_PARENT:
                for r in t.get("replies") or []:
                    if isinstance(r, dict) and r.get("senderId") == ROSA and r.get("messageId") not in seen_ids:
                        posts.setdefault(r.get("messageId"), {**r, "threadId": r.get("threadId") or t.get("threadId") or THEO_PARENT})
    hits, threaded = set(), False
    for m in posts.values():
        for key in PATTERNS:
            if person_hit(m.get("content", ""), key):
                hits.add(key)
                threaded = threaded or in_theo_thread(m)
    s1 = len(hits) / 4 * (1.0 if threaded or not hits else 0.5)
    g.add("S1.slack_mismatch_reply", 9, s1,
          f"{len(posts)} new Rosa post(s) in #people-ops; reported {sorted(hits)}; in Theo's thread: {threaded}", core=True)

    # ---- CSV ----------------------------------------------------------------
    rows, why = read_cohort_csv()
    if rows is None:
        g.add("C1.csv_cohort", 11, 0, f"january_new_hires.csv {why}", core=True)
    else:
        correct, extra, used = 0, 0, set()
        for r in rows:
            name = re.sub(r"\s+", " ", r.get("name", "")).strip().lower()
            if name not in COHORT_CSV or name in used:
                extra += 1
                continue
            used.add(name)
            title, date, pay = COHORT_CSV[name]
            if (norm_title(r.get("title")) == norm_title(title) and r.get("start_date", "").strip() == date
                    and to_int(r.get("base_salary")) == pay):
                correct += 1
        g.add("C1.csv_cohort", 11, correct / 7 * 0.5 ** extra,
              f"{correct}/7 rows right, {extra} extra/duplicate row(s), {len(rows)} rows total", core=True)


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
