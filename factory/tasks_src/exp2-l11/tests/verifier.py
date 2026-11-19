#!/usr/bin/env python3
"""Verifier for psyc3150-late-resubmission-grading. Checkpoint ids/weights mirror rubric.json.

Expected values were derived independently from the seeds and inputs:
  * Lab 3 deadline: Canvas assignment 3103 due_at 2026-11-07T05:59Z (= Fri 11/6 23:59 CST; DST ended 11/1).
  * Policy PDF (Course Policies, linked from the Syllabus page):
      7.2  -10% of 50 = -5 pts per started 24 h late;  7.3  > 120 h late -> 0
      9.2/9.3  only instructor extensions count (Kevin's "take the weekend" is void)
      10.2 resub window = 7 calendar days after release, to 23:59 CT on day 7
      10.3 resub capped at 42.5;  10.4 one graded resub per term;  10.5 higher of original / capped resub
      11.2 SAS flexible deadlines = +48 h;  11.3 lateness counted from end of window
      11.4 SAS letter not retroactive;  12.2 Dean-verified absence waives Section 7 penalties
      14.2 latest attempt's timestamp;  14.3 <= 15 min after deadline is on time
  * Submission times: input/submissions_export.csv (UTC, max attempt).
  * Gmail: Herrera ext. -> Sun 11/8 23:59 CST = 11-09T05:59Z (g02); Aisha ext. corrected from Bello to
    Rahman -> Mon 11/9 23:59 CST = 11-10T05:59Z (g03/g04); SAS letters Okonkwo 9/14, Novak 9/21, Brandt 11/10;
    Dean notice Owen Park absence 11/4-11/8 (g10); Lab 2 released 10/30 afternoon (n11) -> window to
    11/6 23:59 CST = 11-07T05:59Z.
  * Sheets: rubric scores (Lab 3 col E, Lab 2 Resubmissions cols C/D), "Resubmissions Used" (Priya, Lab 1).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/psyc3150-late-resubmission-grading", "0.1.0"
TOL = 0.01

LAB2, LAB3 = 3102, 3103
COURSE = 31

# sis -> (canvas user_id, name, rubric, expected days late, expected final)
LAB3_TODO = {
    "LS2210388": (102, "Diego Alvarez", 42, 1, 37),   # attempt 2 11-07T19:20Z, 13.4 h late -> 1 day (14.2)
    "LS2210417": (101, "Aisha Bello", 44, 2, 34),     # no extension (corrected); 11-08T16:05Z, 34.1 h -> 2
    "LS2210921": (104, "Hannah Cho", 45, 2, 35),      # 11-08T14:30Z, 32.5 h -> 2
    "LS2211052": (103, "Ben Fischer", 39, 2, 29),     # TA promise void (9.3); 11-08T22:00Z, 40 h -> 2
    "LS2211376": (105, "Marcus Lee", 41, 0, 41),      # 11-07T06:09Z, 10 min -> grace (14.3)
    "LS2211008": (111, "Chloe Martin", 38, 0, 38),    # 11-06T18:00Z on time
    "LS2211423": (109, "Ethan Moore", 41, 7, 0),      # 11-13T15:00Z, 153 h > 120 h -> 0 (7.3)
    "LS2211190": (107, "Liam Novak", 43, 1, 38),      # SAS 9/21; window end 11-09T05:59Z; 11-09T20:00Z 14 h -> 1
    "LS2210644": (106, "Grace Okonkwo", 48, 0, 48),   # SAS 9/14; 11-08T23:30Z inside 48 h window
    "LS2210735": (108, "Owen Park", 37, 0, 37),       # Dean-verified 11/4-11/8 covers deadline; sub 11/10 <= 11/15
    "LS2210579": (112, "Isaac Turner", 33, 0, 33),    # 11-06T15:45Z on time
    "LS2210862": (110, "Lena Vogel", 45, 0, 45),      # 11-07T04:48Z = 11/6 22:48 CST, on time
    "LS2211134": (115, "Sofia Brandt", 40, 1, 35),    # SAS 11/10 not retroactive (11.4); 11-08T03:00Z 21 h -> 1
    "LS2210716": (116, "Samir Haddad", 49, 0, 49),    # 11-05T23:12Z on time
    "LS2210493": (114, "Tomás Herrera", 46, 0, 46),   # extension to 11-09T05:59Z; sub 11-09T03:15Z
    "LS2211341": (117, "Nadia Petrova", 36, 0, 36),   # 11-06T22:30Z on time
    "LS2211287": (113, "Aisha Rahman", 47, 0, 47),    # extension to 11-10T05:59Z; sub 11-10T02:40Z
}
ETHAN = "LS2211423"  # any integer >= 6 accepted for days late (cut-off case)

# sis -> (user_id, name, original, resub rubric, expected final)
LAB2_RESUB = {
    "LS2210921": (104, "Hannah Cho", 31, 46, 42.5),   # 11-04 in window; capped 42.5 (10.3)
    "LS2211376": (105, "Marcus Lee", 38, 41, 41),     # 11-05T03:30Z in window, under cap
    "LS2210958": (118, "Priya Shah", 29, 44, 29),     # Lab 1 resub already graded 10/09 (10.4)
    "LS2211065": (119, "Julia Santos", 44, 48, 44),   # capped 42.5 < 44 -> keep 44 (10.5)
    "LS2210602": (120, "Kofi Mensah", 33, 40, 33),    # 11-09T15:00Z after window close 11-07T05:59Z (10.2)
    "LS2211219": (121, "Ryan Doyle", 35, 39, 39),     # 11-06T23:10Z in window, under cap
}

# Kevin's already-posted section 02 Lab 3 rows: sis -> (user_id, score)
KEVIN_DONE = {
    "LS2210958": (118, 42), "LS2211065": (119, 46), "LS2210602": (120, 35), "LS2211219": (121, 40),
    "LS2210827": (122, 44), "LS2211398": (123, 39), "LS2210541": (124, 47),
}

_NUM = re.compile(r"\s*\$?\s*(-?\d+(?:\.\d+)?)\s*(?:pts?\.?|points?|/\s*50)?\s*", re.I)


def num(value):
    """Parse a score-ish value ('42.5', 42.5, '42.5 pts') to float, else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM.fullmatch(str(value))
    return float(m.group(1)) if m else None


def eq(a, b):
    a = num(a)
    return a is not None and abs(a - float(b)) <= TOL


# ------------------------------------------------------------------ canvas
def sub_score(subs, assignment_id, user_id):
    """Score of the (latest) submission for assignment/user; None if ungraded/excused/absent."""
    rows = [s for s in subs if s.get("assignment_id") == assignment_id and s.get("user_id") == user_id]
    if not rows:
        return None
    rows.sort(key=lambda s: (str(s.get("graded_at") or ""), s.get("id") or 0))
    s = rows[-1]
    if s.get("excused"):
        return None
    score = num(s.get("score"))
    if score is None:
        score = num(s.get("grade"))
    return score


# ------------------------------------------------------------------ sheets
def cell(sheet, ref):
    d = (sheet or {}).get("data", {}).get(ref)
    if not d:
        return ""
    v = d.get("value")
    if isinstance(v, str) and v.startswith("=") or v in (None, ""):
        c = d.get("computed")
        if c not in (None, ""):
            v = c
    return "" if v is None else str(v).strip()


def find_sheet(wb, sheet_id, name):
    sheets = (wb or {}).get("sheets") or []
    for s in sheets:
        if s.get("id") == sheet_id:
            return s
    for s in sheets:
        if (s.get("name") or "").strip().lower() == name.lower():
            return s
    return None


def find_row(sheet, sis, name):
    """Row number whose column B holds the SIS id (fallback: column A holds the name)."""
    if not sheet:
        return None
    rows = sorted({int(m.group(1)) for k in sheet.get("data", {}) for m in [re.fullmatch(r"[A-Z]+(\d+)", k)] if m})
    for r in rows:
        if cell(sheet, f"B{r}").upper() == sis:
            return r
    for r in rows:
        if cell(sheet, f"A{r}").lower() == name.lower():
            return r
    return None


def is_y(text):
    return str(text).strip().lower() in ("y", "yes")


def evaluate(g):
    cv0, cv1 = load_site("canvas_lms")
    load_site("gmail")  # must exist; nothing is graded from it
    sh0, sh1 = load_site("google_sheets")

    subs0 = cv0.get("submissions")
    subs1 = cv1.get("submissions")
    if not isinstance(subs0, list) or not isinstance(subs1, list):
        raise InfraError("canvas_lms state has no submissions list")
    # Sanity: the seed must be the one these constants were derived from.
    for sis, (uid, score) in KEVIN_DONE.items():
        if not eq(sub_score(subs0, LAB3, uid), score):
            raise InfraError(f"unexpected initial Lab 3 score for user {uid}")
    for sis, (uid, _, orig, _, _) in LAB2_RESUB.items():
        if not eq(sub_score(subs0, LAB2, uid), orig):
            raise InfraError(f"unexpected initial Lab 2 score for user {uid}")
    lab3_0 = find_sheet(sh0, "sheet_lab3", "Lab 3")
    l2r_0 = find_sheet(sh0, "sheet_lab2r", "Lab 2 Resubmissions")
    if lab3_0 is None or l2r_0 is None:
        raise InfraError("initial google_sheets state lacks the Lab 3 / Lab 2 Resubmissions tabs")
    if not isinstance(sh1, dict) or not isinstance(sh1.get("sheets"), list):
        raise InfraError("current google_sheets state has no sheets list")

    lab3_1 = find_sheet(sh1, "sheet_lab3", "Lab 3")
    l2r_1 = find_sheet(sh1, "sheet_lab2r", "Lab 2 Resubmissions")

    def lab3(sis):
        return sub_score(subs1, LAB3, LAB3_TODO[sis][0])

    def lab2(sis):
        return sub_score(subs1, LAB2, LAB2_RESUB[sis][0])

    def l2r_final(sis):
        _, name, *_ = LAB2_RESUB[sis]
        r = find_row(l2r_1, sis, name)
        return cell(l2r_1, f"E{r}") if r else ""

    # ---- Canvas Lab 3 single-student checks --------------------------------
    for cid, w, sis in (("K1.grace_period", 6, "LS2211376"), ("K2.latest_attempt", 6, "LS2210388"),
                        ("K3.ta_extension_void", 6, "LS2211052"), ("K4.accommodation_within_window", 5, "LS2210644"),
                        ("K5.accommodation_after_window", 6, "LS2211190"),
                        ("K6.accommodation_not_retroactive", 6, "LS2211134"),
                        ("K7.dean_verified_waiver", 6, "LS2210735"), ("K8.five_day_cutoff", 6, "LS2211423")):
        exp = LAB3_TODO[sis][4]
        got = lab3(sis)
        g.add(cid, w, eq(got, exp), f"{LAB3_TODO[sis][1]} Lab 3 = {got}; expected {exp}")

    # ---- Canvas Lab 2 resubmissions ------------------------------------------
    got = lab2("LS2210921")
    g.add("K9.resub_cap", 6, eq(got, 42.5), f"Hannah Cho Lab 2 = {got}; expected 42.5")

    # "Original stands" checks need the tracker Final too, so a no-op run earns nothing.
    for cid, w, sis in (("K10.resub_once_per_term", 6, "LS2210958"), ("K11.resub_higher_of", 5, "LS2211065")):
        exp = LAB2_RESUB[sis][4]
        got, fin = lab2(sis), l2r_final(sis)
        g.add(cid, w, eq(got, exp) and eq(fin, exp),
              f"{LAB2_RESUB[sis][1]} Lab 2 Canvas = {got}, tracker Final = {fin!r}; expected {exp} in both")

    # ---- More Lab 3 ------------------------------------------------------------
    got = lab3("LS2210862")
    g.add("S1.utc_boundary", 4, eq(got, 45), f"Lena Vogel Lab 3 = {got}; expected 45")
    got = lab3("LS2210493")
    g.add("S2.instructor_extension", 4, eq(got, 46), f"Tomás Herrera Lab 3 = {got}; expected 46")
    rah, bel = lab3("LS2211287"), lab3("LS2210417")
    g.add("S3.corrected_extension", 5, 0.5 * eq(rah, 47) + 0.5 * eq(bel, 34),
          f"Aisha Rahman = {rah} (exp 47), Aisha Bello = {bel} (exp 34)")

    got, fin = lab2("LS2210602"), l2r_final("LS2210602")
    g.add("S4.resub_window_closed", 4, eq(got, 33) and eq(fin, 33),
          f"Kofi Mensah Lab 2 Canvas = {got}, tracker Final = {fin!r}; expected 33 in both")

    plain_rows = [(LAB3, sis) for sis in ("LS2211008", "LS2210579", "LS2210716", "LS2211341", "LS2210921")] + \
                 [(LAB2, sis) for sis in ("LS2211376", "LS2211219")]
    ok, notes = 0, []
    for aid, sis in plain_rows:
        table = LAB3_TODO if aid == LAB3 else LAB2_RESUB
        exp = table[sis][-1]
        got = sub_score(subs1, aid, table[sis][0])
        ok += eq(got, exp)
        notes.append(f"{table[sis][1]}/{'L3' if aid == LAB3 else 'L2'}={got}(exp {exp})")
    g.add("S5.plain_rows", 5, ok / len(plain_rows), f"{ok}/{len(plain_rows)}: " + ", ".join(notes))

    # ---- Sheets sync --------------------------------------------------------
    ok, bad = 0, []
    for sis, (_, name, _, days, final) in LAB3_TODO.items():
        r = find_row(lab3_1, sis, name)
        if not r:
            bad.append(f"{name}:no row")
            continue
        f, gv, h = cell(lab3_1, f"F{r}"), cell(lab3_1, f"G{r}"), cell(lab3_1, f"H{r}")
        d = num(f)
        d_ok = d is not None and d == int(d) and ((d >= 6) if sis == ETHAN else int(d) == days)
        if d_ok and eq(gv, final) and is_y(h):
            ok += 1
        else:
            bad.append(f"{name}:F={f!r},G={gv!r},H={h!r}")
    g.add("T1.lab3_sheet_sync", 5, ok / len(LAB3_TODO), f"{ok}/{len(LAB3_TODO)} rows right; wrong: {bad}")

    ok, bad = 0, []
    for sis, (_, name, _, _, final) in LAB2_RESUB.items():
        r = find_row(l2r_1, sis, name)
        e, f = (cell(l2r_1, f"E{r}"), cell(l2r_1, f"F{r}")) if r else ("", "")
        if r and eq(e, final) and is_y(f):
            ok += 1
        else:
            bad.append(f"{name}:E={e!r},F={f!r}")
    g.add("T2.lab2r_sheet_sync", 3, ok / len(LAB2_RESUB), f"{ok}/{len(LAB2_RESUB)} rows right; wrong: {bad}")

    # ---- CLI deliverable ------------------------------------------------------
    rows = read_csv("grade_entries.csv")
    expected = {(sis, "lab3"): v[4] for sis, v in LAB3_TODO.items()}
    expected.update({(sis, "lab2resub"): v[4] for sis, v in LAB2_RESUB.items()})
    if rows is None:
        g.add("D1.grade_entries_csv", 4, 0, "grade_entries.csv missing")
    elif not rows or not {"sis_id", "assignment", "final_score"} <= set(rows[0]):
        g.add("D1.grade_entries_csv", 4, 0, f"bad header/empty file: {sorted(rows[0]) if rows else []}")
    else:
        found = {}
        for row in rows:
            key = (row.get("sis_id", "").strip().upper(),
                   re.sub(r"[\s_\-]", "", row.get("assignment", "").lower()))
            found.setdefault(key, []).append(row.get("final_score"))
        correct = sum(1 for k, v in expected.items() if len(found.get(k, [])) == 1 and eq(found[k][0], v))
        g.add("D1.grade_entries_csv", 4, correct / max(len(expected), len(rows)),
              f"{correct}/{len(expected)} rows right, {len(rows)} rows total")

    # ---- Protection (only judged once real Lab 3 work was done) ----------------
    lab3_right = sum(eq(lab3(sis), v[4]) for sis, v in LAB3_TODO.items())
    problems = []
    if lab3_right >= 5:
        targets = {(LAB3, v[0]) for v in LAB3_TODO.values()} | {(LAB2, v[0]) for v in LAB2_RESUB.values()}
        pairs = {(s.get("assignment_id"), s.get("user_id")) for s in subs0}
        for aid, uid in sorted(pairs):
            if (aid, uid) in targets:
                continue
            a, b = sub_score(subs0, aid, uid), sub_score(subs1, aid, uid)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > TOL):
                problems.append(f"asg {aid} user {uid}: {a}->{b}")
        for sis, (uid, score) in KEVIN_DONE.items():
            r0 = find_row(lab3_0, sis, "")
            r1 = find_row(lab3_1, sis, "")
            before = [cell(lab3_0, f"{c}{r0}") for c in "FGHI"]
            after = [cell(lab3_1, f"{c}{r1}") for c in "FGHI"] if r1 else None
            if after != before:
                problems.append(f"tracker Lab 3 {sis}: {before}->{after}")
        g.add("P1.protect_non_targets", 2, not problems,
              f"{lab3_right} Lab 3 scores right; changes to protected data: {problems[:8]}")
    else:
        g.add("P1.protect_non_targets", 2, 0, f"not judged: only {lab3_right}/17 Lab 3 scores right (need 5)")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
