#!/usr/bin/env python3
"""Verifier for summit-run-of-show. Checkpoints mirror rubric.json (B*, C*, M*, O1).

Expected values are derived by hand from the seeds:
  * seed/google_calendar.json "Northlight Summit — rooms" (c2) = confirmed bookings
    (Gemma, msg_g1: "work from the calendar rather than the v2 draft").
  * msg_p2 (Marcus): scratch Clara; Priya <-> Tomás: Priya -> Fri 10:00 Mercer,
    Tomás -> Thu 10:00 Thames.
  * msg_i1/msg_i2: Inés withdraws; Edge Caching -> Pulled; her Thu 10:00 Mercer booking
    goes to the NLS26 waitlisted talk with more "interested": registrations_export.csv
    NLS-020 Arjun Patel 71 > NLS-019 Kirsten Holm 58 (NPD27 rows are another event).
  * msg_b2: Bartek -> Thu 09:00-09:45 Mercer (Mercer free from 09:00 per msg_g1).
  * msg_n2: Nadia/Olu swap declined -> no change.
  * card-21 (Ben Carver) was already pulled on 5 Nov (msg_h2) -> stays in Pulled.
"""

import csv
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import OUTPUT_DIR, InfraError, load_site, plain, run  # noqa: E402

TASK_ID, VERSION = "cua-hard/summit-run-of-show", "0.1.0"

# ----------------------------------------------------------------- expected board
# list id -> (seed cardIds, expected cardIds in start-time order)
LISTS = {
    # Thu Thames (calendar): 09:00 Ama c1, 10:00 Tomás c15 (swap), 11:15 Kowalski c3,
    # 14:00 Achterberg c4, 15:30 Iyer c5
    "B1.thu_thames_order": ("list-2", 14, ["card-1", "card-2", "card-7", "card-5", "card-4"],
                            ["card-1", "card-15", "card-3", "card-4", "card-5"]),
    # Thu Mercer: 09:00 Bartek c8, 10:00 Arjun c20 (replaces Inés), 11:15 Okonjo c7, 15:30 Mei Lin c9
    "B2.thu_mercer_order": ("list-3", 12, ["card-6", "card-3", "card-8", "card-9"],
                            ["card-8", "card-20", "card-7", "card-9"]),
    # Fri Thames: 09:00 Ferrer c10, 10:00 Olu c11, 11:15 Clara c12, 14:00 Nadia c13, 15:30 panel c14
    "B3.fri_thames_order": ("list-4", 10, ["card-10", "card-12", "card-11", "card-13", "card-14"],
                            ["card-10", "card-11", "card-12", "card-13", "card-14"]),
    # Fri Mercer: 10:00 Priya c2 (swap), 11:15 Whitfield c16, 14:00 Menon c17, 15:30 Demir c18
    "B4.fri_mercer_order": ("list-5", 12, ["card-15", "card-17", "card-16", "card-18"],
                            ["card-2", "card-16", "card-17", "card-18"]),
}
WAITLIST, PULLED = "list-1", "list-6"
NON_TARGET_LISTS = ["list-7", "list-8", "list-9", "list-10", "list-11"]
SESSION_CARDS = [f"card-{i}" for i in range(1, 22)]

# ----------------------------------------------------------------- expected calendar
# (check id, weight, title needle, start UTC, end UTC, room keyword)
BOOKINGS = [
    ("C1.priya_booking", 4, "scaling design systems", "2026-12-04T10:00", "2026-12-04T10:45", "mercer"),
    ("C2.tomas_booking", 4, "accessible data visualisation", "2026-12-03T10:00", "2026-12-03T10:45", "thames"),
    ("C3.replacement_booking", 5, "feature flags", "2026-12-03T10:00", "2026-12-03T10:45", "mercer"),
    ("C4.bartek_booking", 4, "instrumenting onboarding funnels", "2026-12-03T09:00", "2026-12-03T09:45", "mercer"),
]
CHANGED_EVENTS = {"evt_s02", "evt_s06", "evt_s08", "evt_s15"}  # Priya, Inés->Arjun, Bartek, Tomás

# ----------------------------------------------------------------- expected mails
# (check id, address, day, hour, room)
MAILS = [
    ("M1.mail_priya", "priya.raman@lumenworks.in", "fri", 10, "mercer"),
    ("M2.mail_tomas", "tomas.reyes@datavizlab.eu", "thu", 10, "thames"),
    ("M3.mail_arjun", "arjun.patel@flagpole.dev", "thu", 10, "mercer"),
    ("M4.mail_bartek", "bartek.nowak@quantly.pl", "thu", 9, "mercer"),
]

# ----------------------------------------------------------------- expected CSV
# Card titles from seed/trello.json; times from the confirmed calendar + agreed changes;
# card-14's "speaker" is its moderator Marcus Bell.
RUN_OF_SHOW = [
    ("2026-12-03", "Thames Hall", "09:00", "09:45", "Opening Keynote: The Next Decade of Product", "Ama Mensah"),
    ("2026-12-03", "Thames Hall", "10:00", "10:45", "Accessible Data Visualisation", "Tomás Reyes"),
    ("2026-12-03", "Thames Hall", "11:15", "12:00", "Pricing Experiments That Didn't Lie", "Daniel Kowalski"),
    ("2026-12-03", "Thames Hall", "14:00", "14:45", "Roadmaps Are Promises: Saying No in Public", "Helen Achterberg"),
    ("2026-12-03", "Thames Hall", "15:30", "16:15", "Fireside: Building for Regulated Markets", "Sanjay Iyer"),
    ("2026-12-03", "Mercer Room", "09:00", "09:45", "Instrumenting Onboarding Funnels", "Bartek Nowak"),
    ("2026-12-03", "Mercer Room", "10:00", "10:45", "Feature Flags as a Product Tool", "Arjun Patel"),
    ("2026-12-03", "Mercer Room", "11:15", "12:00", "Research Ops on a Shoestring", "Leah Okonjo"),
    ("2026-12-03", "Mercer Room", "15:30", "16:15", "Product Analytics Office Hours", "Mei Lin"),
    ("2026-12-04", "Thames Hall", "09:00", "09:45", "Day Two Keynote: Shipping with Small Teams", "Joaquín Ferrer"),
    ("2026-12-04", "Thames Hall", "10:00", "10:45", "Platform Thinking for Product Managers", "Olu Adebayo"),
    ("2026-12-04", "Thames Hall", "11:15", "12:00", "From Feature Factory to Outcomes", "Clara Jensen"),
    ("2026-12-04", "Thames Hall", "14:00", "14:45", "Designing for Trust in AI Features", "Nadia Haddad"),
    ("2026-12-04", "Thames Hall", "15:30", "16:15", "Closing Panel: What We Got Wrong", "Marcus Bell"),
    ("2026-12-04", "Mercer Room", "10:00", "10:45", "Scaling Design Systems Without a Platform Team", "Priya Raman"),
    ("2026-12-04", "Mercer Room", "11:15", "12:00", "Writing PRDs Engineers Actually Read", "Grace Whitfield"),
    ("2026-12-04", "Mercer Room", "14:00", "14:45", "Migrating a Monolith, One Strangler at a Time", "Ravi Menon"),
    ("2026-12-04", "Mercer Room", "15:30", "16:15", "Customer Interviews at Scale", "Yusuf Demir"),
]
CSV_HEADER = ["day", "room", "start", "end", "session", "speaker"]


# ================================================================= helpers
def norm(text) -> str:
    """strip, lowercase, drop accents, curly quotes -> straight, collapse whitespace."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def instant(value):
    """ISO string -> 'YYYY-MM-DDTHH:MM' in UTC (naive = London = GMT in December)."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})", s)
        if not m:
            return None
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}"
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M")


def live_card_ids(trello, list_id):
    """cardIds of a list, without archived (or deleted) cards."""
    cards = trello.get("cards") or {}
    board = (trello.get("boards") or {}).get("board-1") or {}
    archived_ids = set(board.get("archivedCardIds") or [])
    out = []
    for cid in (trello["lists"][list_id].get("cardIds") or []):
        card = cards.get(cid)
        if card is None or card.get("archived") or cid in archived_ids:
            continue
        out.append(cid)
    return out


def order_score(act, seed, expected):
    if act == seed:
        return 0.0
    want = set(expected)
    good = [c for c in act if c in want]
    frac = len(good) / max(len(expected), len(act))
    in_order = good == [c for c in expected if c in set(good)]
    return frac if in_order else 0.0


DAY_PATTERNS = {
    "thu": [r"\bthu(rs(day)?)?\b", r"\b0?3(rd)?\s+dec(ember)?\b", r"\bdec(ember)?\.?\s+0?3(rd)?\b",
            r"2026-12-03", r"\b0?3/12(/(20)?26)?\b"],
    "fri": [r"\bfri(day)?\b", r"\b0?4(th)?\s+dec(ember)?\b", r"\bdec(ember)?\.?\s+0?4(th)?\b",
            r"2026-12-04", r"\b0?4/12(/(20)?26)?\b"],
}


def mentions_day(text, day):
    return any(re.search(p, text) for p in DAY_PATTERNS[day])


def mentions_time(text, hour):
    h = rf"0?{hour}" if hour < 10 else str(hour)
    return bool(re.search(rf"(?<![\d:.]){h}[:.]00(?!\d)", text)
                or re.search(rf"(?<![\d:.]){h}\s?a\.?m\b", text))


def strip_quoted(body: str) -> str:
    """Drop quoted history from a reply body (lines starting with '>' and anything after 'On … wrote:')."""
    lines = []
    for line in str(body or "").splitlines():
        if re.match(r"\s*(-{3,}\s*original message|on .{0,200} wrote:\s*$)", line, flags=re.I):
            break
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines)


def addresses(msg):
    out = set()
    for field in ("to", "cc", "bcc"):
        for r in msg.get(field) or []:
            email = r.get("email") if isinstance(r, dict) else r
            if email:
                out.add(str(email).strip().lower())
    return out


def norm_time(value):
    v = norm(value)
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?::00)?", v)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else v


def norm_row(row):
    day, room, start, end, session, speaker = (list(row) + [""] * 6)[:6]
    return (norm(day), norm(room), norm_time(start), norm_time(end), norm(session), norm(speaker))


# ================================================================= evaluate
def evaluate(g):
    tr0, tr1 = load_site("trello")
    cal0, cal1 = load_site("google_calendar")
    mail0, mail1 = load_site("yahoo_mail")

    # ---- integrity ----------------------------------------------------------------
    if not isinstance(tr1.get("boards"), dict) or "board-1" not in tr1["boards"]:
        raise InfraError("trello board-1 missing from final state")
    lists1 = tr1.get("lists")
    needed = [f"list-{i}" for i in range(1, 12)]
    if not isinstance(lists1, dict) or any(l not in lists1 for l in needed):
        raise InfraError("trello run-of-show lists missing from final state")
    if not isinstance(tr1.get("cards"), dict):
        raise InfraError("trello cards missing from final state")
    if not isinstance(cal1.get("events"), list):
        raise InfraError("calendar events missing from final state")
    if not isinstance(mail1.get("messages"), list):
        raise InfraError("mail messages missing from final state")

    # ---- B1-B4: day/room list membership and order (core, L08) -------------------
    exact_lists = 0
    for check_id, (list_id, weight, seed_ids, expected) in LISTS.items():
        if tr0["lists"][list_id]["cardIds"] != seed_ids:
            raise InfraError(f"unexpected seed for {list_id}")
        act = live_card_ids(tr1, list_id)
        score = order_score(act, seed_ids, expected)
        exact_lists += act == expected
        g.add(check_id, weight, score, f"{list_id}={act}; expected {expected}", core=True)

    # ---- B5: Waitlist / Pulled ----------------------------------------------------
    wait = live_card_ids(tr1, WAITLIST)
    pulled = live_card_ids(tr1, PULLED)
    b5 = 0.5 * (wait == ["card-19"]) + 0.5 * (set(pulled) == {"card-21", "card-6"} and len(pulled) == 2)
    g.add("B5.waitlist_pulled", 6, b5, f"waitlist={wait} (want [card-19]); pulled={pulled} (want card-21, card-6)")

    # ---- B6: non-target lists/cards untouched (only after real board work) ---------
    changed_lists = [l for l in NON_TARGET_LISTS if lists1[l].get("cardIds") != tr0["lists"][l]["cardIds"]]
    cards1 = tr1["cards"]
    bad_cards = [c for c in SESSION_CARDS if c not in cards1 or cards1[c].get("archived")]
    other_cards = [c for l in NON_TARGET_LISTS for c in tr0["lists"][l]["cardIds"]]
    bad_cards += [c for c in other_cards if c not in cards1 or bool(cards1[c].get("archived")) != bool(tr0["cards"][c].get("archived"))]
    b6 = exact_lists > 0 and not changed_lists and not bad_cards
    g.add("B6.board_non_targets", 3, b6,
          f"exact day/room lists={exact_lists}; changed non-target lists={changed_lists}; missing/archived cards={bad_cards}")

    # ---- C1-C4: rooms calendar bookings --------------------------------------------
    events = cal1["events"]
    titles = [norm(e.get("title")) for e in events]
    c_scores = []
    for check_id, weight, needle, start, end, room in BOOKINGS:
        hits = [e for e in events if needle in norm(e.get("title"))
                and instant(e.get("start")) == start and instant(e.get("end")) == end
                and room in norm(e.get("location"))]
        ok = bool(hits)
        detail = f"{len(hits)} event(s) '{needle}' {start}-{end} @{room}"
        if check_id.startswith("C3"):
            edge = [t for t in titles if "edge caching" in t]
            ok = ok and not edge
            detail += f"; 'Edge Caching' events left: {len(edge)}"
        c_scores.append(g.add(check_id, weight, ok, detail))

    # ---- C5: other calendar events untouched -----------------------------------------
    def sig(e):
        return (norm(e.get("title")), instant(e.get("start")), instant(e.get("end")), norm(e.get("location")))

    by_id = {e.get("id"): e for e in events}
    current_sigs = {sig(e) for e in events}
    unchanged = [e for e in cal0["events"] if e["id"] not in CHANGED_EVENTS]
    if len(unchanged) != 44:
        raise InfraError(f"expected 44 non-target seed events, found {len(unchanged)}")
    broken = []
    for e in unchanged:
        now = by_id.get(e["id"])
        if not ((now is not None and sig(now) == sig(e)) or sig(e) in current_sigs):
            broken.append(e["id"])
    c5 = any(s > 0 for s in c_scores) and not broken
    g.add("C5.calendar_non_targets", 3, c5,
          f"calendar work done={any(s > 0 for s in c_scores)}; altered/missing non-target events={broken}")

    # ---- M1-M4: notification emails ---------------------------------------------------
    seed_msgs = {m.get("id"): m for m in mail0.get("messages") or []}
    sent = []
    for m in mail1["messages"]:
        is_sent = m.get("folderId") == "sent" or (m.get("status") == "sent" and not m.get("isDraft"))
        if not is_sent:
            continue
        old = seed_msgs.get(m.get("id"))
        if old is not None and (old.get("folderId") == "sent" or old.get("status") == "sent"):
            continue  # pre-existing sent mail earns nothing
        sent.append(m)
    for check_id, address, day, hour, room in MAILS:
        mine = [m for m in sent if address in addresses(m)]
        good = 0
        for m in mine:
            text = norm(m.get("subject")) + " \n " + norm(strip_quoted(m.get("body")))
            if not (m.get("body") or "").strip() and m.get("bodyHtml"):
                text += " " + norm(plain(m.get("bodyHtml")))
            if mentions_day(text, day) and mentions_time(text, hour) and room in text:
                good += 1
        g.add(check_id, 2.5, good > 0, f"{len(mine)} new sent mail(s) to {address}, {good} with {day} {hour}:00 {room}")

    # ---- O1: run_of_show.csv ------------------------------------------------------------
    path = OUTPUT_DIR / "run_of_show.csv"
    if not path.is_file() or path.is_symlink():
        g.add("O1.run_of_show_csv", 13, 0, "run_of_show.csv missing")
        return
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    except (UnicodeDecodeError, csv.Error) as exc:
        g.add("O1.run_of_show_csv", 13, 0, f"unreadable CSV: {exc}")
        return
    if not rows or [norm(h) for h in rows[0]] != CSV_HEADER:
        g.add("O1.run_of_show_csv", 13, 0, f"header {rows[0] if rows else None} != {CSV_HEADER}")
        return
    data = [norm_row(r) for r in rows[1:]]
    expected_rows = {norm_row(r) for r in RUN_OF_SHOW}
    hit = len(set(data) & expected_rows)
    g.add("O1.run_of_show_csv", 13, hit / max(len(expected_rows), len(data)),
          f"{hit}/{len(expected_rows)} expected rows present, {len(data)} data rows")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
