#!/usr/bin/env python3
"""Verifier for lsfs-december-programme. Checkpoints mirror rubric.json (G*, C*, R*, O*).

Expected programme, derived independently from the seeds and the input sheet:

Nomination thread p_nom, top-level comments only, net = upvotes - downvotes
(wiki "Programming rules" #1: duplicates are added together):
    Aftersun 57-5=52        -> quote is DCP only (rule #4)                    -> out
    Paris, Texas 29-2 + 22-1 = 27+21 = 48 (c_n02 + c_n09, same film)          -> 1st
    Solaris (Tarkovsky) 47-3=44 -> 1972 row: PG, Blu-ray, 140.00 <= 150        -> 2nd
    Stalker 41-2=39         -> licence_from 2027-01-22, not valid in Dec       -> out
    Portrait of a Lady on Fire 27-2=25 -> cert 15 (matinee needs U/PG)         -> out for 19th
    My Neighbour Totoro 26-2=24 -> screened 2025-06-19 (issue #12), < 2 years  -> out
    The Umbrellas of Cherbourg 24-1=23 -> fee 165.00 > 150                     -> out
    The Red Shoes 23-1=22   -> U, Blu-ray, 110.00, licence 2026-10-01..2027-09-30,
                               last shown 2024-11-28 (wiki Screening history),
                               eligible again from 2026-11-28                  -> 3rd (matinee)
    Paddington 2 15, Wings of Desire 11, Possession 9                          -> not reached
Dates: p_hall (stickied, Marta): 17 Dec cancelled, Sat 19 Dec doors 14:00, film 14:30;
c_h2: the 3rd and 10th keep the top two, the 19th gets best remaining U/PG.
Evenings: venue handbook "film 19:30". December London = GMT, so stored UTC == local.
Quotes (input/distributor_quotes.csv):
    Paris, Texas 1984 15 Blu-ray 130.00 | Solaris 1972 PG 140.00 | The Red Shoes 1948 U 110.00
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import InfraError, load_site, new_items, read_csv, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/lsfs-december-programme", "0.1.0"

# film key -> expected screening (see module docstring for the derivation)
FILMS = {
    "paris": {"needle": "paris texas", "date": "2026-12-03", "start": "2026-12-03T19:30:00+00:00",
              "time": "19:30", "title": "Paris, Texas", "year": 1984, "cert": "15", "votes": 48, "fee": 130.00},
    "solaris": {"needle": "solaris", "date": "2026-12-10", "start": "2026-12-10T19:30:00+00:00",
                "time": "19:30", "title": "Solaris", "year": 1972, "cert": "PG", "votes": 44, "fee": 140.00},
    "redshoes": {"needle": "red shoes", "date": "2026-12-19", "start": "2026-12-19T14:30:00+00:00",
                 "time": "14:30", "title": "The Red Shoes", "year": 1948, "cert": "U", "votes": 22, "fee": 110.00},
}
# Nominated films that must not be programmed (normalised, word-bounded needles).
NOT_SELECTED = ["aftersun", "stalker", "portrait of a lady", "totoro", "umbrellas of cherbourg",
                "paddington", "wings of desire", "possession"]
CANCELLED_DATE = "2026-12-17"
HOLD_IDS = {"evt_007", "evt_008", "evt_009"}  # "St Brigid's Hall hold (LSFS)" 3/10/17 Dec
PROJECT_ID = 1          # gitlab lsfs-programme
SUBREDDIT = "s_lsfs"    # r/LanternStreetFilms
POSTER = "u_hannah"
FLAIR = "f_prog"        # "Programme"
CSV_COLS = ["date", "start_time", "film", "year", "certificate", "votes", "licence_fee_gbp"]


# ------------------------------------------------------------------ helpers
def norm(text) -> str:
    """Lowercase, punctuation -> space, single spaces (so 'Paris, Texas' == 'paris texas')."""
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def has_word(text, needle) -> bool:
    return f" {needle} " in f" {norm(text)} "


def wrong_films(text):
    return [n for n in NOT_SELECTED if has_word(text, n)]


_NUM = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?!\d)")


def has_amount(text, value, tol=0.005) -> bool:
    """Number anywhere in text (handles £130, GBP130, GBP 130.00, 130 GBP)."""
    for whole, dec in _NUM.findall(str(text or "")):
        if abs(float(whole.replace(",", "") + "." + (dec or "0")) - value) <= tol:
            return True
    return False


def labels_of(issue):
    out = []
    for lab in issue.get("labels") or []:
        if isinstance(lab, dict):
            lab = lab.get("name") or lab.get("title") or ""
        out.append(str(lab).strip().lower())
    return out


def _last_sunday(year, month):
    d = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def london_offset(utc_dt):
    """UK civil time: BST (UTC+1) from last Sun of March 01:00 UTC to last Sun of October 01:00 UTC."""
    y = utc_dt.year
    start = _last_sunday(y, 3).replace(hour=1, tzinfo=timezone.utc)
    end = _last_sunday(y, 10).replace(hour=1, tzinfo=timezone.utc)
    return timedelta(hours=1) if start <= utc_dt < end else timedelta(0)


def parse_start(value):
    """Stored start -> aware UTC datetime; naive strings are taken as Europe/London wall time."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(re.sub(r"\.\d+", "", s))
    except ValueError:
        return None
    if dt.tzinfo is None:
        guess = dt.replace(tzinfo=timezone.utc)
        dt = guess - london_offset(guess)
    return dt.astimezone(timezone.utc)


def london_date(dt):
    return (dt + london_offset(dt)).date().isoformat() if dt else ""


# ------------------------------------------------------------------ evaluate
def evaluate(g):
    gl0, gl1 = load_site("gitlab")
    cal0, cal1 = load_site("google_calendar")
    rd0, rd1 = load_site("reddit")

    # ---- integrity -----------------------------------------------------------
    issues0, issues1 = gl0.get("issues") or [], gl1.get("issues")
    events0, events1 = cal0.get("events") or [], cal1.get("events")
    posts0, posts1 = rd0.get("posts") or [], rd1.get("posts")
    for name, before, after in (("gitlab issues", issues0, issues1), ("calendar events", events0, events1),
                                ("reddit posts", posts0, posts1)):
        if not isinstance(after, list) or not before:
            raise InfraError(f"{name} missing from state")
        ids_after = {x.get("id") for x in after if isinstance(x, dict)}
        if not ids_after & {x.get("id") for x in before}:
            raise InfraError(f"all seeded {name} missing from current state")

    # ---- GitLab ---------------------------------------------------------------
    added_issues = new_items(issues0, issues1)
    prog_issues = [i for i in added_issues if i.get("projectId") == PROJECT_ID]

    def issues_for(key):
        f = FILMS[key]
        return [i for i in prog_issues
                if has_word(i.get("title"), f["needle"]) and f["date"] in str(i.get("title") or "")]

    g_hits = 0
    for cid, w, key in (("G1.issue_paris", 7, "paris"), ("G2.issue_solaris", 7, "solaris"),
                        ("G3.issue_redshoes", 8, "redshoes")):
        found = issues_for(key)
        g_hits += bool(found)
        g.add(cid, w, bool(found), f"{len(found)} new issue(s) titled with {FILMS[key]['title']!r} + {FILMS[key]['date']}")

    fee_hits = []
    for key in FILMS:
        if any(has_amount(i.get("description"), FILMS[key]["fee"]) for i in issues_for(key)):
            fee_hits.append(key)
    g.add("G4.issue_fees", 6, len(fee_hits) / 3, f"fee in description for {fee_hits}; expected 130/140/110")

    labelled = [i for i in prog_issues if "screening" in labels_of(i)]
    g5 = len(labelled) / len(prog_issues) if prog_issues and g_hits else 0.0
    g.add("G5.issue_labels", 4, g5, f"{len(labelled)}/{len(prog_issues)} new board issues labelled screening; G1-G3 hits={g_hits}")

    bad_new = []
    for i in added_issues:
        wrong = wrong_films(f"{i.get('title', '')} {i.get('description', '')}")
        if wrong or CANCELLED_DATE in str(i.get("title") or ""):
            bad_new.append((i.get("id"), wrong or [CANCELLED_DATE]))
    now_by_id = {i.get("id"): i for i in issues1}
    altered = []
    for old in issues0:
        cur = now_by_id.get(old.get("id"))
        if cur is None or any(cur.get(k) != old.get(k) for k in ("title", "status", "description")) \
                or sorted(labels_of(cur)) != sorted(labels_of(old)):
            altered.append(old.get("id"))
    g.add("G6.issue_no_extras", 4, g_hits > 0 and not bad_new and not altered,
          f"bad new issues {bad_new}; altered/deleted seed issues {altered}; G1-G3 hits={g_hits}")

    # ---- Google Calendar --------------------------------------------------------
    seed_ev = {e.get("id"): e for e in events0}
    added_ev = new_items(events0, events1)
    # A hold re-titled into the screening is an equivalent outcome to a new event.
    retitled_holds = [e for e in events1 if e.get("id") in HOLD_IDS
                      and e.get("title") != seed_ev[e.get("id")].get("title")]
    candidates = added_ev + retitled_holds

    c_matches = {}
    for cid, w, key in (("C1.event_paris", 7, "paris"), ("C2.event_solaris", 7, "solaris"),
                        ("C3.event_redshoes", 8, "redshoes")):
        target = parse_start(FILMS[key]["start"])
        found = [e for e in candidates if has_word(e.get("title"), FILMS[key]["needle"])
                 and parse_start(e.get("start")) is not None
                 and abs((parse_start(e.get("start")) - target).total_seconds()) <= 60]
        titled = [e.get("start") for e in candidates if has_word(e.get("title"), FILMS[key]["needle"])]
        if found:
            c_matches[key] = found
        g.add(cid, w, bool(found), f"{len(found)} event(s) at {FILMS[key]['start']}; titled events start at {titled}")

    good_loc = [k for k, evs in c_matches.items()
                if any(e.get("calendarId") == "c2" and "st brigid" in str(e.get("location") or "").lower() for e in evs)]
    g.add("C4.event_calendar_location", 5, len(good_loc) / len(c_matches) if c_matches else 0.0,
          f"on Lantern Street FS (c2) with St Brigid's location: {good_loc} of {sorted(c_matches)}")

    bad_ev = []
    for e in added_ev:
        wrong = wrong_films(e.get("title"))
        if wrong or london_date(parse_start(e.get("start"))) == CANCELLED_DATE:
            bad_ev.append((e.get("id"), e.get("title"), e.get("start")))
    for e in retitled_holds:
        if wrong_films(e.get("title")):
            bad_ev.append((e.get("id"), e.get("title"), e.get("start")))
    cur_ev = {e.get("id"): e for e in events1}
    altered_ev = [eid for eid, old in seed_ev.items() if eid not in HOLD_IDS and (
        eid not in cur_ev or any(cur_ev[eid].get(k) != old.get(k) for k in ("title", "start", "end", "calendarId")))]
    g.add("C5.no_wrong_events", 4, bool(c_matches) and not bad_ev and not altered_ev,
          f"bad events {bad_ev}; altered/deleted seed events {altered_ev}; C1-C3 hits={len(c_matches)}")

    # ---- Reddit announcement -----------------------------------------------------
    posts = [p for p in new_items(posts0, posts1)
             if p.get("subredditId") == SUBREDDIT and p.get("userId") == POSTER]

    def r1_score(p):
        text = f"{p.get('title', '')} {p.get('content', '')}"
        low = text.lower()
        hits = [k for k in FILMS if has_word(text, FILMS[k]["needle"])]
        if "solaris" in hits and ("2002" in low or "soderbergh" in low):
            hits.remove("solaris")
        wrong = wrong_films(text)
        score = len(hits) / max(3, len(hits) + len(wrong))
        if p.get("flairId") != FLAIR:
            score *= 0.5
        return score, hits, wrong

    best = max(posts, key=lambda p: r1_score(p)[0], default=None)
    if best is None:
        g.add("R1.announcement_films", 12, 0, "no new post by u_hannah in r/LanternStreetFilms")
        g.add("R2.announcement_dates", 5, 0, "no announcement post")
    else:
        s, hits, wrong = r1_score(best)
        g.add("R1.announcement_films", 12, s,
              f"post {best.get('id')}: films {hits}, wrong {wrong}, flair {best.get('flairId')}")
        text = re.sub(r"\s+", " ", f"{best.get('title', '')} {best.get('content', '')}".lower())
        date_ok = re.search(r"\b19(st|nd|rd|th)?\s*(of\s+)?dec|\bdec(ember)?\.?\s+19\b|2026-12-19|\b19/12\b"
                            r"|\bsat(urday)?\.?,?\s+19\b", text)
        time_ok = re.search(r"\b14[:.]30\b|\b2[:.]30\s*(pm|p\.m\.)", text)
        g.add("R2.announcement_dates", 5, bool(date_ok and time_ok),
              f"19 Dec mentioned={bool(date_ok)}, 14:30 mentioned={bool(time_ok)}")

    # ---- CSV deliverable -----------------------------------------------------------
    rows = read_csv("december_programme.csv")
    if rows is None:
        g.add("O1.programme_csv", 16, 0, "december_programme.csv missing")
    elif not rows or any(c not in rows[0] for c in CSV_COLS):
        g.add("O1.programme_csv", 16, 0, f"missing columns; header {list(rows[0]) if rows else []}")
    else:
        def as_int(v):
            try:
                return int(float(str(v).replace(",", "").strip()))
            except ValueError:
                return None

        def as_money(v):
            try:
                return float(re.sub(r"(?i)gbp|£|,", "", str(v)).strip())
            except ValueError:
                return None

        def row_ok(r, f):
            fee = as_money(r.get("licence_fee_gbp"))
            return (r.get("date") == f["date"] and r.get("start_time") == f["time"]
                    and norm(r.get("film")).replace(" ", "") == norm(f["title"]).replace(" ", "")
                    and as_int(r.get("year")) == f["year"] and r.get("certificate", "").upper() == f["cert"]
                    and as_int(r.get("votes")) == f["votes"] and fee is not None and abs(fee - f["fee"]) <= 0.005)

        used, correct = set(), []
        for key, f in FILMS.items():
            for idx, r in enumerate(rows):
                if idx not in used and row_ok(r, f):
                    used.add(idx)
                    correct.append(key)
                    break
        g.add("O1.programme_csv", 16, len(correct) / max(3, len(rows)),
              f"correct rows {correct}; {len(rows)} row(s) total")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
