#!/usr/bin/env python3
"""World for the summit-run-of-show task (Trello + Yahoo Mail + Google Calendar + local CSV).

Writes into <out>/:
  seed/{trello,yahoo_mail,google_calendar}.json     initial state per site
  golden/{trello,yahoo_mail,google_calendar}.json   state after a correct run
  golden_output/run_of_show.csv                     correct CLI deliverable
  input/registrations_export.csv                    agent-visible workspace input
  expected.json                                     truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/run_of_show.csv}

Story: Rosa Delgado, a freelance event coordinator, runs the run-of-show Trello board for the
Northlight Product Summit (Thu 3 / Fri 4 Dec 2026, Brunel Rooms, London). The board still mirrors
the v2 draft agenda; the venue has since entered the confirmed bookings in a shared calendar
(system of record, some rooms/times differ). Speaker changes arrived by email: one swap whose
partner was corrected in a thread reply, one withdrawal whose replacement is chosen with a local
registration export (that also contains rows for a different event), one approved time move, and
one request that was declined. Every day/room list must end up holding the right cards in
start-time order, which needs drag-and-drop on the board.

London in December is UTC+0, so the calendar mock's local/UTC handling is neutral.
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T09:15:00+00:00"
NOW = "2026-11-18T09:15:00.000Z"
ROSA = {"name": "Rosa Delgado", "email": "rosa.delgado.events@yahoo.com"}
MARCUS = {"name": "Marcus Bell", "email": "marcus.bell@northlight.io"}
GEMMA = {"name": "Gemma Shaw", "email": "gemma.shaw@brunelrooms.co.uk"}

THU, FRI = "2026-12-03", "2026-12-04"
THAMES, MERCER = "Thames Hall", "Mercer Room"
DAY_LABEL = {THU: "Thu 3 Dec", FRI: "Fri 4 Dec"}

# ---------------------------------------------------------------- sessions
# card id -> (title, speaker, org, email, format, confirmed (day, room, start, end), draft (day, room, start))
SESSIONS = {
    "card-1": ("Opening Keynote: The Next Decade of Product", "Ama Mensah", "Northlight", "ama.mensah@northlight.io",
               "Keynote", (THU, THAMES, "09:00", "09:45"), (THU, THAMES, "09:00")),
    "card-2": ("Scaling Design Systems Without a Platform Team", "Priya Raman", "Lumenworks", "priya.raman@lumenworks.in",
               "Talk", (THU, THAMES, "10:00", "10:45"), (THU, THAMES, "10:00")),
    "card-3": ("Pricing Experiments That Didn't Lie", "Daniel Kowalski", "Fernhill", "d.kowalski@fernhill.co",
               "Talk", (THU, THAMES, "11:15", "12:00"), (THU, MERCER, "11:15")),
    "card-4": ("Roadmaps Are Promises: Saying No in Public", "Helen Achterberg", "Achterberg Advisory", "helen@achterberg.nl",
               "Talk", (THU, THAMES, "14:00", "14:45"), (THU, THAMES, "15:30")),
    "card-5": ("Fireside: Building for Regulated Markets", "Sanjay Iyer", "Clarity Bank", "sanjay.iyer@claritybank.com",
               "Fireside", (THU, THAMES, "15:30", "16:15"), (THU, THAMES, "14:00")),
    "card-6": ("Edge Caching Deep Dive", "Inés Duarte", "Cachefront", "ines.duarte@cachefront.pt",
               "Talk", (THU, MERCER, "10:00", "10:45"), (THU, MERCER, "10:00")),
    "card-7": ("Research Ops on a Shoestring", "Leah Okonjo", "Fieldnotes Studio", "leah.okonjo@fieldnotes.studio",
               "Talk", (THU, MERCER, "11:15", "12:00"), (THU, THAMES, "11:15")),
    "card-8": ("Instrumenting Onboarding Funnels", "Bartek Nowak", "Quantly", "bartek.nowak@quantly.pl",
               "Talk", (THU, MERCER, "14:00", "14:45"), (THU, MERCER, "14:00")),
    "card-9": ("Product Analytics Office Hours", "Mei Lin", "Northlight", "mei.lin@northlight.io",
               "Workshop", (THU, MERCER, "15:30", "16:15"), (THU, MERCER, "15:30")),
    "card-10": ("Day Two Keynote: Shipping with Small Teams", "Joaquín Ferrer", "Ferrer.dev", "joaquin@ferrer.dev",
                "Keynote", (FRI, THAMES, "09:00", "09:45"), (FRI, THAMES, "09:00")),
    "card-11": ("Platform Thinking for Product Managers", "Olu Adebayo", "Stackyard", "olu.adebayo@stackyard.io",
                "Talk", (FRI, THAMES, "10:00", "10:45"), (FRI, THAMES, "11:15")),
    "card-12": ("From Feature Factory to Outcomes", "Clara Jensen", "Outcome Lab", "clara.jensen@outcomelab.dk",
                "Talk", (FRI, THAMES, "11:15", "12:00"), (FRI, THAMES, "10:00")),
    "card-13": ("Designing for Trust in AI Features", "Nadia Haddad", "SignalHQ", "nadia.haddad@signalhq.com",
                "Talk", (FRI, THAMES, "14:00", "14:45"), (FRI, THAMES, "14:00")),
    "card-14": ("Closing Panel: What We Got Wrong", "Marcus Bell", "Northlight", "marcus.bell@northlight.io",
                "Panel", (FRI, THAMES, "15:30", "16:15"), (FRI, THAMES, "15:30")),
    "card-15": ("Accessible Data Visualisation", "Tomás Reyes", "DataViz Lab", "tomas.reyes@datavizlab.eu",
                "Talk", (FRI, MERCER, "10:00", "10:45"), (FRI, MERCER, "10:00")),
    "card-16": ("Writing PRDs Engineers Actually Read", "Grace Whitfield", "Parcelpoint", "grace.whitfield@parcelpoint.co.uk",
                "Talk", (FRI, MERCER, "11:15", "12:00"), (FRI, MERCER, "14:00")),
    "card-17": ("Migrating a Monolith, One Strangler at a Time", "Ravi Menon", "Tidewater", "ravi.menon@tidewater.io",
                "Talk", (FRI, MERCER, "14:00", "14:45"), (FRI, MERCER, "11:15")),
    "card-18": ("Customer Interviews at Scale", "Yusuf Demir", "Askwell", "yusuf.demir@askwell.com",
                "Talk", (FRI, MERCER, "15:30", "16:15"), (FRI, MERCER, "15:30")),
}
WAITLIST = {
    "card-19": ("Postmortems Without Blame", "Kirsten Holm", "RelayOps", "kirsten.holm@relayops.se", "Talk", 1, "2 Nov"),
    "card-20": ("Feature Flags as a Product Tool", "Arjun Patel", "Flagpole", "arjun.patel@flagpole.dev", "Talk", 2, "6 Nov"),
}
PULLED_OLD = ("card-21", "Growth Loops 101", "Ben Carver", "Loopwise", "ben@loopwise.co")

LIST_WAIT, LIST_THU_T, LIST_THU_M, LIST_FRI_T, LIST_FRI_M, LIST_PULLED, LIST_LOG = (
    "list-1", "list-2", "list-3", "list-4", "list-5", "list-6", "list-7")
DAY_ROOM_LIST = {(THU, THAMES): LIST_THU_T, (THU, MERCER): LIST_THU_M, (FRI, THAMES): LIST_FRI_T, (FRI, MERCER): LIST_FRI_M}
LIST_TITLES = {
    LIST_WAIT: "Waitlist", LIST_THU_T: "Thu 3 Dec · Thames Hall", LIST_THU_M: "Thu 3 Dec · Mercer Room",
    LIST_FRI_T: "Fri 4 Dec · Thames Hall", LIST_FRI_M: "Fri 4 Dec · Mercer Room", LIST_PULLED: "Pulled",
    LIST_LOG: "Production & logistics",
}
# The board as built from the v2 draft agenda.
INITIAL_ORDER = {
    LIST_WAIT: ["card-19", "card-20"],
    LIST_THU_T: ["card-1", "card-2", "card-7", "card-5", "card-4"],
    LIST_THU_M: ["card-6", "card-3", "card-8", "card-9"],
    LIST_FRI_T: ["card-10", "card-12", "card-11", "card-13", "card-14"],
    LIST_FRI_M: ["card-15", "card-17", "card-16", "card-18"],
    LIST_PULLED: ["card-21"],
}
EVENT_OF = {cid: f"evt_s{int(cid.split('-')[1]):02d}" for cid in SESSIONS}

LOGISTICS = [
    ("card-22", "Badge print file to Printwell", "Final attendee CSV + 30 blanks. Printwell needs it by 25 Nov.", "2026-11-25T12:00:00.000Z"),
    ("card-23", "Catering final numbers", "Brunel Rooms catering needs final headcount and dietary split 7 days out.", "2026-11-26T17:00:00.000Z"),
    ("card-24", "AV run sheet for Sam", "Sam Okoro (AV) builds cue sheets from this board once it is final. Mic count per session, playback needs.", "2026-11-27T12:00:00.000Z"),
    ("card-25", "Speaker gifts", "Notebook + Northlight tote, 22 sets. Delivery to venue Wed 2 Dec.", None),
    ("card-26", "Wayfinding signage proofs", "Thames Hall / Mercer Room door signs, foyer schedule boards.", "2026-11-24T12:00:00.000Z"),
    ("card-27", "Livestream encoder test", "Thames Hall only. Test with venue IT during tech rehearsal.", "2026-12-02T16:00:00.000Z"),
    ("card-28", "Green room rota", "Volunteers for speaker green room, both days.", None),
    ("card-29", "Lanyard colours", "Speakers orange, staff black, attendees teal.", None),
]
PARTNER_CARDS = [
    ("card-30", "list-8", "Postmortems Without Blame (Kirsten Holm)", "Kirsten pitched this for Partner Day too; check against Summit waitlist before confirming."),
    ("card-31", "list-8", "Partner pricing roundtable", "Invite-only, 20 seats."),
    ("card-32", "list-8", "Scaling Design Systems — encore session?", "Ask Priya after the Summit if she would repeat it in January."),
    ("card-33", "list-9", "Partner Day venue hold — Brunel Rooms, 21 Jan", "Mercer Room + foyer held until 4 Dec."),
    ("card-34", "list-9", "Partner Day welcome — Ama Mensah", "Confirmed 12 Nov."),
]
ADMIN_CARDS = [
    ("card-35", "list-10", "Invoice Northlight — deposit (50%)", "Sent 2 Nov, paid 9 Nov."),
    ("card-36", "list-10", "Quote for Halden Labs offsite (Feb)", "Two-day offsite, ~40 people."),
    ("card-37", "list-11", "Renew public liability insurance", "Renewal due 30 Nov."),
    ("card-38", "list-11", "Book accountant call", "Q3 VAT return."),
]

# ---------------------------------------------------------------- the correct outcome
GOLDEN_ORDER = {
    LIST_WAIT: ["card-19"],
    LIST_THU_T: ["card-1", "card-15", "card-3", "card-4", "card-5"],
    LIST_THU_M: ["card-8", "card-20", "card-7", "card-9"],
    LIST_FRI_T: ["card-10", "card-11", "card-12", "card-13", "card-14"],
    LIST_FRI_M: ["card-2", "card-16", "card-17", "card-18"],
    LIST_PULLED: ["card-21", "card-6"],
}
# event id -> new (title or None, day, room, start, end, description or None)
GOLDEN_EVENT_CHANGES = {
    "evt_s02": (None, FRI, MERCER, "10:00", "10:45", None),
    "evt_s15": (None, THU, THAMES, "10:00", "10:45", None),
    "evt_s08": (None, THU, MERCER, "09:00", "09:45", None),
    "evt_s06": ("Feature Flags as a Product Tool", THU, MERCER, "10:00", "10:45",
                "Speaker: Arjun Patel (Flagpole)\nReplaces Edge Caching Deep Dive (Inés Duarte withdrew 17 Nov).\nBooking ref BR-2291-06"),
}
SPEAKER_MAILS = {  # card -> (email, day, start, room)
    "card-2": ("priya.raman@lumenworks.in", FRI, "10:00", MERCER),
    "card-15": ("tomas.reyes@datavizlab.eu", THU, "10:00", THAMES),
    "card-20": ("arjun.patel@flagpole.dev", THU, "10:00", MERCER),
    "card-8": ("bartek.nowak@quantly.pl", THU, "09:00", MERCER),
}


def iso(day, hhmm):
    return f"{day}T{hhmm}:00.000Z"


def all_talks():
    talks = {cid: (s[0], s[1], s[2], s[3], s[4]) for cid, s in SESSIONS.items()}
    talks.update({cid: (w[0], w[1], w[2], w[3], w[4]) for cid, w in WAITLIST.items()})
    talks[PULLED_OLD[0]] = (PULLED_OLD[1], PULLED_OLD[2], PULLED_OLD[3], PULLED_OLD[4], "Talk")
    return talks


# ---------------------------------------------------------------- trello
USERS = {
    "u1": ("Rosa Delgado", "rosadelgado", "RD", ROSA["email"]),
    "u2": ("Marcus Bell", "marcusbell", "MB", MARCUS["email"]),
    "u3": ("Jo Pritchard", "jopritchard", "JP", "jo.pritchard@northlight.io"),
    "u4": ("Sam Okoro", "samokoro_av", "SO", "sam@okoro-av.co.uk"),
}
LABELS = [
    {"id": "lbl-1", "name": "Keynote", "color": "#eb5a46"},
    {"id": "lbl-2", "name": "Talk", "color": "#0079bf"},
    {"id": "lbl-3", "name": "Panel", "color": "#c377e0"},
    {"id": "lbl-4", "name": "Workshop", "color": "#61bd4f"},
    {"id": "lbl-5", "name": "Fireside", "color": "#ff9f1a"},
    {"id": "lbl-6", "name": "Production", "color": "#f2d600"},
]
FORMAT_LABEL = {"Keynote": "lbl-1", "Talk": "lbl-2", "Panel": "lbl-3", "Workshop": "lbl-4", "Fireside": "lbl-5"}
# createdAt is unrelated to slot order so "Sort by date" cannot produce the run of show.
CREATED = ["2026-10-21", "2026-10-14", "2026-10-28", "2026-10-09", "2026-10-30", "2026-10-12", "2026-10-26",
           "2026-10-16", "2026-10-23", "2026-10-11", "2026-10-29", "2026-10-15", "2026-10-20", "2026-10-27",
           "2026-10-13", "2026-10-31", "2026-10-18", "2026-10-24", "2026-11-02", "2026-11-06", "2026-10-19"]


def card(cid, title, list_id, board_id, description, labels, created, members=("u1",), due=None, comments=None,
         checklists=None, position=0, completed=False):
    return {"id": cid, "title": title, "description": description, "listId": list_id, "boardId": board_id,
            # The mock deep-merges the seed into its defaults and skips nulls, so "no value" is seeded
            # as "" (falsy in the UI) to keep default covers/due dates of card-1..14 from leaking in.
            "labelIds": list(labels), "memberIds": list(members), "dueDate": due or "", "startDate": "",
            "completed": completed, "cover": "", "checklists": checklists or [], "comments": comments or [],
            "attachments": [], "archived": False, "watching": False, "position": position, "createdAt": created}


def activity(aid, text, at, user="u1"):
    return {"id": aid, "type": "activity", "userId": user, "text": text, "createdAt": at, "editedAt": None}


def comment(cid, text, at, user):
    return {"id": cid, "type": "comment", "userId": user, "text": text, "createdAt": at, "editedAt": None}


def session_description(cid):
    if cid in SESSIONS:
        title, speaker, org, email, fmt, _conf, draft = SESSIONS[cid]
        role = "Moderator" if fmt == "Panel" else "Speaker"
        return (f"**{role}:** {speaker} — {org} ({email})\n**Format:** {fmt}, 45 min\n"
                f"**Draft v2 slot:** {DAY_LABEL[draft[0]]}, {draft[2]}, {draft[1]}\n\n"
                "AV: lapel mic, clicker, HDMI. Slides due Fri 27 Nov.")
    if cid in WAITLIST:
        title, speaker, org, email, fmt, rank, added = WAITLIST[cid]
        return (f"**Speaker:** {speaker} — {org} ({email})\n**Format:** {fmt}, 45 min\n"
                f"**Waitlist:** #{rank} (added {added})\n\nAbstract approved by the programme committee; "
                "slot to be confirmed if one opens up.")
    return (f"**Speaker:** {PULLED_OLD[2]} — {PULLED_OLD[3]} ({PULLED_OLD[4]})\n"
            "Pulled 5 Nov: speaker withdrew (new job). Slot reallocated in draft v2.")


def build_trello():
    users = {uid: {"id": uid, "name": n, "username": un, "initials": ini, "email": em, "avatarUrl": avatar(n)}
             for uid, (n, un, ini, em) in USERS.items()}
    talks = all_talks()
    cards = {}
    for list_id, ids in INITIAL_ORDER.items():
        for pos, cid in enumerate(ids):
            title, speaker, _org, _email, fmt = talks[cid]
            n = int(cid.split("-")[1])
            created = f"{CREATED[n - 1]}T{9 + n % 8:02d}:{(n * 7) % 60:02d}:00.000Z"
            comments = [activity(f"act-{cid}-0", f"added this card to {LIST_TITLES[list_id] if cid != 'card-21' else 'Thu 3 Dec · Mercer Room'}", created)]
            if cid == "card-21":
                comments.insert(0, activity("act-card-21-1", "moved this card from Thu 3 Dec · Mercer Room to Pulled", "2026-11-05T16:40:00.000Z"))
            if cid == "card-2":
                comments.insert(0, comment("com-p1", "Priya asked for a confidence monitor — Sam has it on the AV list.", "2026-11-10T10:12:00.000Z", "u4"))
            if cid == "card-13":
                comments.insert(0, comment("com-n1", "Sponsors want this one after lunch.", "2026-11-09T15:20:00.000Z", "u2"))
            if cid == "card-19":
                comments.insert(0, comment("com-k1", "First on the waitlist by date added.", "2026-11-02T11:00:00.000Z", "u3"))
            members = ["u1", "u4"] if fmt == "Keynote" else ["u1"]
            cards[cid] = card(cid, title, list_id, "board-1", session_description(cid), [FORMAT_LABEL[fmt]], created,
                              members=members, comments=comments, position=pos)
    for pos, (cid, title, desc, due) in enumerate(LOGISTICS):
        cards[cid] = card(cid, title, LIST_LOG, "board-1", desc, ["lbl-6"], f"2026-10-{10 + pos:02d}T10:00:00.000Z",
                          members=["u1", "u3"] if pos % 2 else ["u1"], due=due, position=pos,
                          comments=[activity(f"act-{cid}-0", "added this card to Production & logistics", f"2026-10-{10 + pos:02d}T10:00:00.000Z")])
    cards["card-24"]["checklists"] = [{"id": "cl-av", "title": "AV", "items": [
        {"id": "ci-av1", "text": "Mic count per room", "completed": True, "assigneeId": "u4", "dueDate": None},
        {"id": "ci-av2", "text": "Cue sheets from final board", "completed": False, "assigneeId": "u4", "dueDate": None}]}]
    for pos, (cid, lid, title, desc) in enumerate(PARTNER_CARDS):
        cards[cid] = card(cid, title, lid, "board-2", desc, [], f"2026-11-{3 + pos:02d}T14:00:00.000Z", position=pos)
    for pos, (cid, lid, title, desc) in enumerate(ADMIN_CARDS):
        cards[cid] = card(cid, title, lid, "board-3", desc, [], f"2026-11-{1 + pos:02d}T08:30:00.000Z", position=pos,
                          completed=cid == "card-35")
    lists = {lid: {"id": lid, "title": LIST_TITLES[lid], "boardId": "board-1", "cardIds": list(INITIAL_ORDER.get(lid, []))
                   if lid != LIST_LOG else [c[0] for c in LOGISTICS], "archived": False} for lid in LIST_TITLES}
    for lid, title, bid in (("list-8", "Ideas", "board-2"), ("list-9", "Confirmed", "board-2"),
                            ("list-10", "This week", "board-3"), ("list-11", "Admin", "board-3")):
        lists[lid] = {"id": lid, "title": title, "boardId": bid,
                      "cardIds": [c for c, v in cards.items() if v["listId"] == lid], "archived": False}
    boards = {
        "board-1": {"id": "board-1", "title": "Northlight Summit 2026 — Run of Show",
                    "description": "Run of show for the Northlight Product Summit, 3–4 Dec 2026, Brunel Rooms (London).\n\n"
                                   "One list per day and room; cards in each list run in start-time order (top = first session). "
                                   "Sam builds the AV cue sheets straight from this board.",
                    "background": "#1F4E79", "listIds": list(LIST_TITLES), "starred": True, "visibility": "workspace",
                    "archivedListIds": [], "archivedCardIds": [], "labels": LABELS, "memberIds": ["u1", "u2", "u3", "u4"],
                    "lastVisitedAt": "2026-11-13T17:02:00.000Z", "closed": False, "createdAt": "2026-10-08T09:00:00.000Z"},
        "board-2": {"id": "board-2", "title": "Northlight Partner Day — Jan 2027", "description": "21 Jan 2027, Brunel Rooms.",
                    "background": "#519839", "listIds": ["list-8", "list-9"], "starred": False, "visibility": "workspace",
                    "archivedListIds": [], "archivedCardIds": [], "labels": [], "memberIds": ["u1", "u2"],
                    "lastVisitedAt": "2026-11-12T11:00:00.000Z", "closed": False, "createdAt": "2026-11-03T14:00:00.000Z"},
        "board-3": {"id": "board-3", "title": "Delgado Events — Admin", "description": "", "background": "#89609E",
                    "listIds": ["list-10", "list-11"], "starred": False, "visibility": "private",
                    "archivedListIds": [], "archivedCardIds": [], "labels": [], "memberIds": ["u1"],
                    "lastVisitedAt": "2026-11-16T08:00:00.000Z", "closed": False, "createdAt": "2026-01-05T08:00:00.000Z"},
    }
    return {"currentUser": "u1", "users": users, "boards": boards, "lists": lists, "cards": cards,
            "boardOrder": ["board-1", "board-2", "board-3"], "lastReadNotificationAt": "2026-11-17T18:00:00.000Z"}


def apply_board(trello, order):
    """Rearrange board-1 the way MOVE_CARD does: cardIds per list, card.listId, and an activity on cross-list moves."""
    t = copy.deepcopy(trello)
    where = {cid: lid for lid, ids in INITIAL_ORDER.items() for cid in ids}
    for lid, ids in order.items():
        t["lists"][lid]["cardIds"] = list(ids)
        for k, cid in enumerate(ids):
            c = t["cards"][cid]
            if where[cid] != lid:
                c["comments"].insert(0, activity(f"act-move-{cid}", f"moved this card from {LIST_TITLES[where[cid]]} to {LIST_TITLES[lid]}",
                                                 f"2026-11-18T09:{30 + k:02d}:00.000Z"))
                c["listId"] = lid
    t["boards"]["board-1"]["lastVisitedAt"] = "2026-11-18T09:20:00.000Z"
    return t


# ---------------------------------------------------------------- google calendar
# Event colours are hex (week/agenda views and the popover use them as inline CSS); calendar colours stay
# Tailwind classes because the sidebar uses them as class names.
COLORS = {"c1": "#039BE5", "c2": "#33B679", "c3": "#8E24AA", "c4": "#F6BF26"}


def ev(eid, cal, title, start, end, location="", description="", recurring="none", all_day=False, guests=None, reminders=None):
    return {"id": eid, "calendarId": cal, "title": title, "start": start, "end": end, "allDay": all_day,
            "location": location, "description": description, "guests": guests or [], "color": COLORS[cal],
            "recurring": recurring, "reminders": reminders if reminders is not None else [{"type": "popup", "minutes": 10}]}


def build_calendar():
    events = []
    for cid, (title, speaker, org, _email, fmt, (day, room, start, end), _d) in SESSIONS.items():
        n = int(cid.split("-")[1])
        who = "Moderator" if fmt == "Panel" else "Speaker"
        events.append(ev(EVENT_OF[cid], "c2", title, iso(day, start), iso(day, end), location=room,
                         description=f"{who}: {speaker} ({org})\nBooking ref BR-2291-{n:02d}", reminders=[]))
    venue = [
        ("evt_v01", "Registration & coffee", THU, "08:00", "09:00", "Foyer"),
        ("evt_v02", "Morning break", THU, "10:45", "11:15", "Foyer"),
        ("evt_v03", "Lunch & sponsor expo", THU, "12:00", "14:00", "Foyer"),
        ("evt_v04", "Afternoon break", THU, "14:45", "15:30", "Foyer"),
        ("evt_v05", "Drinks reception", THU, "16:30", "19:00", "River Terrace"),
        ("evt_v06", "Registration & coffee", FRI, "08:15", "09:00", "Foyer"),
        ("evt_v07", "Morning break", FRI, "10:45", "11:15", "Foyer"),
        ("evt_v08", "Lunch & sponsor expo", FRI, "12:00", "14:00", "Foyer"),
        ("evt_v09", "Afternoon break", FRI, "14:45", "15:30", "Foyer"),
        ("evt_v10", "Venue get-out", FRI, "16:30", "19:00", "All rooms"),
        ("evt_v11", "Tech rehearsal — Thames Hall", "2026-12-02", "14:00", "18:00", THAMES),
        ("evt_v12", "Venue access: speaker gifts & signage delivery", "2026-12-02", "10:00", "12:00", "Loading bay"),
    ]
    for eid, title, day, s, e, loc in venue:
        events.append(ev(eid, "c2", title, iso(day, s), iso(day, e), location=loc,
                         description="Brunel Rooms booking BR-2291", reminders=[]))
    other = [
        ("evt_o01", "c3", "Northlight weekly sync", "2026-11-16T15:00:00.000Z", "2026-11-16T15:30:00.000Z", "Google Meet", "Marcus, Jo, Rosa", "weekly"),
        ("evt_o02", "c3", "Northlight budget check-in", "2026-11-25T15:00:00.000Z", "2026-11-25T15:30:00.000Z", "Google Meet", "Marcus, Rosa: AV and catering overages", "none"),
        ("evt_o03", "c3", "Site visit: Brunel Rooms with Gemma", "2026-11-20T11:00:00.000Z", "2026-11-20T12:30:00.000Z", "Brunel Rooms, Rotherhithe", "Walk the rooms, check signage points.", "none"),
        ("evt_o04", "c3", "Speaker prep call: Priya Raman", "2026-11-30T12:00:00.000Z", "2026-11-30T12:30:00.000Z", "Zoom", "Run through slides + AV needs.", "none"),
        ("evt_o05", "c3", "Speaker prep call: Joaquín Ferrer", "2026-11-26T16:00:00.000Z", "2026-11-26T16:30:00.000Z", "Zoom", "", "none"),
        ("evt_o06", "c3", "AV walkthrough with Sam Okoro", "2026-11-27T10:00:00.000Z", "2026-11-27T11:00:00.000Z", "Okoro AV studio", "Bring final run of show.", "none"),
        ("evt_o07", "c3", "Catering tasting", "2026-11-19T13:00:00.000Z", "2026-11-19T14:00:00.000Z", "Brunel Rooms", "", "none"),
        ("evt_o08", "c3", "Partner Day: content planning", "2026-12-09T14:00:00.000Z", "2026-12-09T15:00:00.000Z", "Northlight office", "", "none"),
        ("evt_o09", "c3", "Halden Labs offsite — intro call", "2026-11-24T10:00:00.000Z", "2026-11-24T10:30:00.000Z", "Phone", "", "none"),
        ("evt_o10", "c3", "Summit debrief", "2026-12-08T10:00:00.000Z", "2026-12-08T11:00:00.000Z", "Northlight office", "", "none"),
        ("evt_o11", "c1", "Pilates", "2026-11-18T18:30:00.000Z", "2026-11-18T19:30:00.000Z", "Frame Shoreditch", "", "weekly"),
        ("evt_o12", "c1", "Dentist", "2026-11-25T08:30:00.000Z", "2026-11-25T09:00:00.000Z", "Old St Dental", "", "none"),
        ("evt_o13", "c1", "Dinner with Inés & Paulo", "2026-11-21T19:30:00.000Z", "2026-11-21T22:00:00.000Z", "Bar Douro", "", "none"),
        ("evt_o14", "c1", "Mum's birthday lunch", "2026-12-06T12:30:00.000Z", "2026-12-06T15:00:00.000Z", "Richmond", "", "none"),
        ("evt_o15", "c1", "Accountant call (VAT)", "2026-11-19T09:00:00.000Z", "2026-11-19T09:30:00.000Z", "Phone", "", "none"),
        ("evt_o16", "c1", "Haircut", "2026-11-28T10:00:00.000Z", "2026-11-28T10:45:00.000Z", "", "", "none"),
    ]
    for eid, cal, title, s, e, loc, desc, rec in other:
        events.append(ev(eid, cal, title, s, e, location=loc, description=desc, recurring=rec))
    events.append(ev("evt_h01", "c4", "St Andrew's Day", "2026-11-30T00:00:00.000Z", "2026-12-01T00:00:00.000Z", all_day=True, reminders=[]))
    events.append(ev("evt_h02", "c4", "Christmas Day", "2026-12-25T00:00:00.000Z", "2026-12-26T00:00:00.000Z", all_day=True, reminders=[]))
    return {
        "user": {"id": "u1", "username": "Rosa Delgado", "email": ROSA["email"], "avatar": avatar("Rosa Delgado")},
        "calendars": [
            {"id": "c1", "name": "Rosa Delgado", "color": "bg-blue-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c2", "name": "Northlight Summit — rooms", "color": "bg-green-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c3", "name": "Clients & calls", "color": "bg-purple-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c4", "name": "UK holidays", "color": "bg-yellow-500", "textColor": "text-white", "visible": True, "userId": "u1"},
        ],
        "events": events,
        "view": "week",
        "currentDate": NOW,
        "sidebarOpen": True,
        "settings": {"weekStart": 0, "defaultDuration": 60, "defaultView": "week",
                     "defaultReminder": {"type": "popup", "minutes": 10}, "timeFormat": "12h",
                     "showWeekNumbers": False, "showDeclinedEvents": False},
        "otherCalendars": [],
    }


def apply_calendar(cal, changes):
    c = copy.deepcopy(cal)
    for e in c["events"]:
        if e["id"] in changes:
            title, day, room, s, en, desc = changes[e["id"]]
            if title:
                e["title"] = title
            if desc:
                e["description"] = desc
            e["start"], e["end"], e["location"] = iso(day, s), iso(day, en), room
    return c


# ---------------------------------------------------------------- yahoo mail
SYSTEM_FOLDERS = [("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"), ("spam", "Spam"), ("trash", "Trash")]
USER_FOLDERS = [("fld_northlight", "Northlight Summit"), ("fld_partnerday", "Partner Day"), ("fld_invoices", "Invoices"),
                ("fld_halden", "Halden Labs"), ("fld_personal", "Personal")]


def msg(mid, cnv, sender, subject, body, date, to=None, cc=None, folder="inbox", category="primary", read=True, starred=False):
    received = folder != "sent"
    frm = sender if received else ROSA
    return {"id": mid, "conversationId": cnv, "folderId": folder, "previousFolderId": None, "category": category,
            "from": dict(frm), "to": [dict(x) for x in (to or [ROSA])], "cc": [dict(x) for x in (cc or [])], "bcc": [],
            "replyTo": None, "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None,
            "date": date, "isRead": read, "isStarred": starred, "isDraft": False, "status": "received" if received else "sent",
            "attachments": [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"), "summary": None,
            "orderInfo": None, "travelInfo": None, "inReplyToId": None, "forwardedFromId": None, "replyType": None,
            "repliedAt": None, "forwardedAt": None, "sentAt": None if received else date, "movedAt": None,
            "appliedFilterId": None, "createdAt": date, "updatedAt": None}


def P(*paras):
    return "\n\n".join(paras)


PRIYA = {"name": "Priya Raman", "email": "priya.raman@lumenworks.in"}
INES = {"name": "Inés Duarte", "email": "ines.duarte@cachefront.pt"}
BARTEK = {"name": "Bartek Nowak", "email": "bartek.nowak@quantly.pl"}
NADIA = {"name": "Nadia Haddad", "email": "nadia.haddad@signalhq.com"}
SAM = {"name": "Sam Okoro", "email": "sam@okoro-av.co.uk"}
JO = {"name": "Jo Pritchard", "email": "jo.pritchard@northlight.io"}


def build_mail():
    m = []
    # --- the decisive Northlight threads (inbox) ---
    m.append(msg("msg_g1", "cnv_rooms", GEMMA, "Confirmed room bookings — Northlight Summit 3–4 Dec", P(
        "Hi Rosa,",
        "Following our call I've had to reshuffle a few sessions between Thames Hall and Mercer Room to match the expected numbers, and "
        "I've entered every confirmed booking in the shared \"Northlight Summit — rooms\" calendar. Those bookings are what our team "
        "will staff and set AV for, so please work from the calendar rather than the v2 draft agenda from October.",
        "One bit of good news: Mercer Room is now yours from 09:00 on Thursday 3 Dec (previously 10:00), at no extra cost, if you want "
        "to use the extra slot.",
        "Best,\nGemma Shaw\nEvents Manager, Brunel Rooms"), "2026-11-12T14:05:00.000Z", cc=[MARCUS]))
    m.append(msg("msg_g2", "cnv_rooms", MARCUS, "Re: Confirmed room bookings — Northlight Summit 3–4 Dec", P(
        "Thanks Gemma.",
        "Rosa — could you get the run-of-show board back in line with Gemma's calendar before it goes to Sam? Same layout as always: "
        "one list per day and room, sessions top to bottom in time order.",
        "Marcus"), "2026-11-12T15:40:00.000Z", cc=[GEMMA]))
    m.append(msg("msg_p1", "cnv_priya", PRIYA, "Change to my Thursday slot", P(
        "Hi Rosa,",
        "Bad news on my side: my flight from Bengaluru was rescheduled and now lands at Heathrow on Thursday 3 Dec at 13:05, so I'll "
        "miss my 10:00 Thursday slot in Thames Hall.",
        "Clara Jensen mentioned at the speaker dinner that she'd happily trade with me — her Friday 11:15 talk for my Thursday slot. "
        "Could we do that swap?",
        "Sorry for the hassle,\nPriya"), "2026-11-16T08:40:00.000Z", cc=[MARCUS], read=False))
    m.append(msg("msg_p2", "cnv_priya", MARCUS, "Re: Change to my Thursday slot", P(
        "Rosa — scratch the Clara idea. I checked with her and she isn't in London until Thursday evening, so she can't take a "
        "Thursday morning slot.",
        "Tomás Reyes is in town all week and has agreed to trade instead: Priya takes Tomás's Friday 10:00 slot in Mercer Room, and "
        "Tomás moves to Priya's Thursday 10:00 slot in Thames Hall. Please make that happen on the board and in the bookings calendar "
        "and confirm the new slots to both of them.",
        "Priya, hope the new flight is less painful!\nMarcus"), "2026-11-17T11:02:00.000Z", to=[ROSA], cc=[PRIYA], read=False))
    m.append(msg("msg_i1", "cnv_ines", INES, "Withdrawing from Northlight Summit", P(
        "Dear Rosa,",
        "I'm very sorry to do this so close to the event, but for family reasons I have to withdraw from the Summit. I won't be able "
        "to give Edge Caching Deep Dive on 3 December. I've let Marcus know as well.",
        "Apologies again and I hope it goes brilliantly,\nInés"), "2026-11-17T07:55:00.000Z", read=False))
    m.append(msg("msg_i2", "cnv_ines", MARCUS, "Re: Withdrawing from Northlight Summit", P(
        "Rosa,",
        "Sad, but understood. Please pull Edge Caching and fill Inés's Thursday 10:00 Mercer Room booking from the waitlist: take "
        "whichever of the two waitlisted Summit talks had more interested sign-ups in the registration export I sent on Monday (the "
        "one you saved as registrations_export.csv). Waitlist rank doesn't matter here, interest does. The other talk stays on the "
        "waitlist for now.",
        "Please let the speaker know they're in.\nMarcus"), "2026-11-17T12:30:00.000Z", read=False))
    m.append(msg("msg_b1", "cnv_bartek", BARTEK, "Earlier slot on Thursday?", P(
        "Hi Rosa,",
        "I've just been told I need to be in Manchester for 16:00 on Thursday 3 Dec, and my train leaves Euston at 13:40. My talk "
        "(Instrumenting Onboarding Funnels) is currently at 14:00. Is there any chance of a morning slot instead?",
        "Thanks,\nBartek"), "2026-11-16T18:20:00.000Z", cc=[MARCUS]))
    m.append(msg("msg_b2", "cnv_bartek", MARCUS, "Re: Earlier slot on Thursday?", P(
        "Rosa — yes, let's use the extra hour Gemma offered: move Bartek to Thursday 09:00–09:45 in Mercer Room. Leave his 14:00 "
        "booking free for now.",
        "Marcus"), "2026-11-17T09:10:00.000Z", cc=[BARTEK], read=False))
    m.append(msg("msg_n1", "cnv_nadia", NADIA, "Swap with Olu on Friday?", P(
        "Hi Rosa,",
        "Would it be possible to move my Friday talk to the morning? Olu Adebayo said he wouldn't mind swapping his 10:00 for my "
        "14:00 slot in Thames Hall.",
        "Best,\nNadia"), "2026-11-15T10:30:00.000Z", cc=[MARCUS]))
    m.append(msg("msg_n2", "cnv_nadia", MARCUS, "Re: Swap with Olu on Friday?", P(
        "Nadia, thanks for asking, but let's keep you at 14:00 — the sponsors specifically asked for the AI trust talk straight after "
        "lunch. Rosa, no change needed here.",
        "Marcus"), "2026-11-16T09:05:00.000Z", cc=[NADIA]))
    m.append(msg("msg_r1", "cnv_regs", MARCUS, "Registration export — interest per session", P(
        "Hi Rosa,",
        "Here's this morning's export from the registration platform with the number of attendees who marked each session as "
        "\"interested\". It covers the Summit (event code NLS26) and the early pipeline for January's Partner Day (NPD27), so mind "
        "the event column. Can you save it in the job folder?",
        "Marcus"), "2026-11-16T08:05:00.000Z"))
    m.append(msg("msg_r2", "cnv_regs", ROSA, "Re: Registration export — interest per session",
                 "Saved as registrations_export.csv in the Northlight job folder. Thanks!\n\nRosa",
                 "2026-11-16T08:30:00.000Z", to=[MARCUS], folder="sent"))
    m.append(msg("msg_s1", "cnv_sam", SAM, "Cue sheets — need final board by Friday", P(
        "Hi Rosa,",
        "I'll build the Thames Hall and Mercer Room cue sheets straight off the Trello lists, top to bottom, so please make sure each "
        "list is in the actual running order before Friday. I'll also need a flat CSV of the final programme for the stage managers.",
        "Cheers,\nSam"), "2026-11-17T16:45:00.000Z", read=False))
    # --- already handled ---
    m.append(msg("msg_h1", "cnv_ben", {"name": "Ben Carver", "email": "ben@loopwise.co"}, "Have to pull out — Growth Loops 101", P(
        "Hi Rosa, I've accepted a new role starting 1 December and can't do the Summit. Really sorry.", "Ben"),
        "2026-11-05T09:12:00.000Z", folder="fld_northlight"))
    m.append(msg("msg_h2", "cnv_ben", ROSA, "Re: Have to pull out — Growth Loops 101",
                 "Thanks for letting us know, Ben, and congratulations! I've taken the talk off the programme.\n\nRosa",
                 "2026-11-05T16:45:00.000Z", to=[{"name": "Ben Carver", "email": "ben@loopwise.co"}], folder="sent"))
    # --- Northlight noise ---
    noise_nl = [
        ("msg_x01", JO, "Speaker dinner — final list", "Twenty confirmed for Wednesday 2 Dec at Dock Kitchen. I'll send the seating plan Monday.", "2026-11-13T12:00:00.000Z"),
        ("msg_x02", {"name": "Printwell", "email": "orders@printwell.co.uk"}, "Badge proof ready for approval", "Your badge proof (job PW-88213) is ready. Please approve by 23 Nov for delivery on 1 Dec.", "2026-11-14T09:30:00.000Z"),
        ("msg_x03", GEMMA, "Catering numbers reminder", "Hi Rosa, a reminder that we need final catering numbers and dietary requirements by 26 Nov. Gemma", "2026-11-17T10:00:00.000Z"),
        ("msg_x04", SAM, "Mic count", "Thames Hall: 2 lapels + 4 handhelds for the panel. Mercer: 2 lapels. Shout if that changes.", "2026-11-11T15:10:00.000Z"),
        ("msg_x05", {"name": "Clara Jensen", "email": "clara.jensen@outcomelab.dk"}, "Slides for Friday", "Hi Rosa, attaching the final title slide shortly. Still on for Friday 11:15! Clara", "2026-11-13T08:20:00.000Z"),
        ("msg_x06", {"name": "Tomás Reyes", "email": "tomas.reyes@datavizlab.eu"}, "Accessibility checklist for my talk", "Hi Rosa, could the venue reserve two front-row seats for attendees using screen magnifiers? Thanks, Tomás", "2026-11-10T17:00:00.000Z"),
        ("msg_x07", JO, "Sponsor booth map v3", "Updated booth map attached in the shared drive. No changes to session rooms.", "2026-11-09T11:45:00.000Z"),
        ("msg_x08", {"name": "Kirsten Holm", "email": "kirsten.holm@relayops.se"}, "Any news on the waitlist?", "Hi Rosa, just checking whether a slot might open up for Postmortems Without Blame. Happy either way! Kirsten", "2026-11-14T13:25:00.000Z"),
        ("msg_x09", {"name": "Helen Achterberg", "email": "helen@achterberg.nl"}, "Travel booked", "Eurostar booked, arriving Wednesday evening. See you Thursday!", "2026-11-12T19:05:00.000Z"),
        ("msg_x10", MARCUS, "Livestream — Thames Hall only", "Confirmed with the board: we only stream Thames Hall. Mercer sessions get recorded audio.", "2026-11-10T09:00:00.000Z"),
    ]
    for mid, s, subj, body, date in noise_nl:
        m.append(msg(mid, "cnv_" + mid, s, subj, body, date))
    # --- Partner Day (other event) ---
    m.append(msg("msg_pd1", "cnv_pd1", MARCUS, "Partner Day — talk ideas", P(
        "Rosa, early thoughts for 21 Jan: Kirsten Holm's postmortems talk looks popular in the NPD27 pipeline, and Priya might do an "
        "encore of her design systems talk. Nothing to action until after the Summit.", "Marcus"), "2026-11-11T16:00:00.000Z",
        folder="fld_partnerday"))
    m.append(msg("msg_pd2", "cnv_pd2", GEMMA, "Partner Day hold — 21 Jan", "Mercer Room and foyer are held for 21 January until 4 December.",
                 "2026-11-06T10:00:00.000Z", folder="fld_partnerday"))
    # --- other clients, invoices, personal, newsletters ---
    other = [
        ("msg_y01", {"name": "Halden Labs", "email": "ops@haldenlabs.com"}, "Offsite in February — quote?", "Hi Rosa, we're looking at a two-day offsite for ~40 people in February. Could you send a rough quote?", "2026-11-15T14:00:00.000Z", "fld_halden", "primary"),
        ("msg_y02", {"name": "Northlight Accounts", "email": "accounts@northlight.io"}, "Remittance advice — INV-2026-031", "Payment of £6,400.00 has been made for invoice INV-2026-031 (deposit).", "2026-11-09T08:00:00.000Z", "fld_invoices", "primary"),
        ("msg_y03", {"name": "Hiscox", "email": "renewals@hiscox.co.uk"}, "Your public liability renewal", "Your policy renews on 30 November. Review your cover online.", "2026-11-08T07:30:00.000Z", "inbox", "primary"),
        ("msg_y04", {"name": "Mum", "email": "carmen.delgado@btinternet.com"}, "Sunday 6th", "Lunch at ours on the 6th? Your brother is bringing the kids.", "2026-11-14T20:10:00.000Z", "fld_personal", "primary"),
        ("msg_y05", {"name": "Inés & Paulo", "email": "paulo.m@gmail.com"}, "Saturday dinner", "Table at Bar Douro, 19:30 on Saturday 21st. (Different Inés, don't panic 😄)", "2026-11-13T18:00:00.000Z", "inbox", "primary"),
        ("msg_y06", {"name": "Eventbrite", "email": "noreply@eventbrite.com"}, "Your weekly organiser digest", "Ticket sales summary for your events this week.", "2026-11-16T06:00:00.000Z", "inbox", "newsletters"),
        ("msg_y07", {"name": "Event Industry News", "email": "news@eventindustrynews.com"}, "Venues brace for a busy December", "This week: venue pricing, sustainability rules and more.", "2026-11-17T06:30:00.000Z", "inbox", "newsletters"),
        ("msg_y08", {"name": "Bizzabo", "email": "hello@bizzabo.com"}, "Run-of-show templates that save hours", "Download our free run-of-show template pack.", "2026-11-12T13:00:00.000Z", "inbox", "offers"),
        ("msg_y09", {"name": "Trainline", "email": "noreply@trainline.com"}, "Your e-ticket: London → Bristol", "Your journey on 10 Dec is booked.", "2026-11-10T21:00:00.000Z", "inbox", "primary"),
        ("msg_y10", {"name": "LinkedIn", "email": "messages-noreply@linkedin.com"}, "You appeared in 14 searches this week", "See who's looking at your profile.", "2026-11-16T09:00:00.000Z", "inbox", "social"),
        ("msg_y11", {"name": "Okoro AV", "email": "accounts@okoro-av.co.uk"}, "Invoice OAV-1187 (deposit)", "Please find the deposit invoice for Northlight Summit AV.", "2026-11-03T12:00:00.000Z", "fld_invoices", "primary"),
        ("msg_y12", {"name": "Frame", "email": "hello@moveyourframe.com"}, "Your Pilates booking", "See you Wednesday 18:30 at Shoreditch.", "2026-11-15T07:00:00.000Z", "fld_personal", "primary"),
        ("msg_y13", {"name": "Canva", "email": "marketing@canva.com"}, "New: event signage templates", "Design wayfinding signs in minutes.", "2026-11-11T10:00:00.000Z", "inbox", "offers"),
        ("msg_y14", {"name": "Halden Labs", "email": "ops@haldenlabs.com"}, "Re: Offsite in February — quote?", "Also: could we do Bristol rather than London?", "2026-11-16T10:00:00.000Z", "fld_halden", "primary"),
        ("msg_y15", {"name": "Meetup", "email": "info@meetup.com"}, "London Event Pros: December social", "RSVP for the December social.", "2026-11-14T17:00:00.000Z", "inbox", "social"),
    ]
    for mid, s, subj, body, date, folder, cat in other:
        m.append(msg(mid, "cnv_" + mid, s, subj, body, date, folder=folder, category=cat, read=mid not in ("msg_y01", "msg_y14")))
    sent_noise = [
        ("msg_z01", GEMMA, "Re: Site visit", "Friday 20th at 11:00 works. See you then!", "2026-11-10T12:00:00.000Z"),
        ("msg_z02", SAM, "Re: Mic count", "Perfect, thanks Sam.", "2026-11-11T16:00:00.000Z"),
        ("msg_z03", {"name": "Kirsten Holm", "email": "kirsten.holm@relayops.se"}, "Re: Any news on the waitlist?", "Hi Kirsten, nothing yet — I'll let you know as soon as anything changes. Rosa", "2026-11-14T15:00:00.000Z"),
    ]
    for mid, to, subj, body, date in sent_noise:
        m.append(msg(mid, "cnv_" + mid, ROSA, subj, body, date, to=[to], folder="sent"))
    m.sort(key=lambda x: x["date"], reverse=True)
    folders = ([{"id": fid, "name": n, "type": "system", "parentId": None, "order": i, "createdAt": "2025-01-01T00:00:00.000Z"}
                for i, (fid, n) in enumerate(SYSTEM_FOLDERS)] +
               [{"id": fid, "name": n, "type": "user", "parentId": None, "order": i, "createdAt": "2026-01-05T00:00:00.000Z",
                 "updatedAt": None} for i, (fid, n) in enumerate(USER_FOLDERS)])
    people = [("Marcus", "Bell", MARCUS["email"], "Northlight"), ("Gemma", "Shaw", GEMMA["email"], "Brunel Rooms"),
              ("Jo", "Pritchard", JO["email"], "Northlight"), ("Sam", "Okoro", SAM["email"], "Okoro AV"),
              ("Priya", "Raman", PRIYA["email"], "Lumenworks"), ("Bartek", "Nowak", BARTEK["email"], "Quantly"),
              ("Nadia", "Haddad", NADIA["email"], "SignalHQ"), ("Inés", "Duarte", INES["email"], "Cachefront"),
              ("Clara", "Jensen", "clara.jensen@outcomelab.dk", "Outcome Lab"), ("Kirsten", "Holm", "kirsten.holm@relayops.se", "RelayOps"),
              ("Carmen", "Delgado", "carmen.delgado@btinternet.com", "")]
    contacts = [{"id": f"ct_{i + 1:04d}", "firstName": f, "lastName": l, "nickname": "", "emails": [{"type": "work", "address": e}],
                 "phones": [], "addresses": [], "company": co, "jobTitle": "", "birthday": "", "website": "", "notes": "",
                 "isFavorite": i < 2, "avatarColor": "#5C6BC0", "source": "manual", "createdAt": "2026-10-01T00:00:00.000Z",
                 "updatedAt": None} for i, (f, l, e, co) in enumerate(people)]
    return {
        "currentUser": {"id": "usr_rosa", "name": "Rosa Delgado", "firstName": "Rosa", "email": ROSA["email"], "aliases": [],
                        "avatarColor": "#00897B", "jobTitle": "Event coordinator", "company": "Delgado Events",
                        "location": "London, UK", "storage": {"usedBytes": 812345678, "totalBytes": 21474836480}},
        "folders": folders, "messages": m, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {
            "appearance": {"theme": "light", "themeColor": "blue", "density": "comfortable", "messageLayout": "list"},
            "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
            "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
            "writing": {"signature": {"enabled": False, "text": "Rosa Delgado\nDelgado Events · London"},
                        "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": ROSA["email"],
                        "sendWithCtrlEnter": True, "linkPreviews": True},
            "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "",
                                 "onlyContacts": False, "updatedAt": None},
            "notifications": {"browser": False, "sound": False}, "ai": {"messageSummaries": False},
            "keyboardShortcuts": True, "rightPanel": {"open": False, "tab": "starred"},
            "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False},
        },
    }


def fmt_day(day):
    return {"2026-12-03": "Thursday 3 December", "2026-12-04": "Friday 4 December"}[day]


def send_mail(mail, idx, to_email, to_name, subject, body):
    mm = copy.deepcopy(mail)
    at = f"2026-11-18T10:{10 + idx:02d}:00.000Z"
    sent = msg(f"msg_sent_{idx}", f"cnv_sent_{idx}", ROSA, subject, body, at, to=[{"name": to_name, "email": to_email}], folder="sent")
    sent["updatedAt"] = at
    mm["messages"].insert(0, sent)
    mm["activityLog"].append({"id": f"act_sent_{idx}", "type": "message.send", "actor": ROSA["email"], "createdAt": at,
                              "messageIds": [sent["id"]], "folderIds": ["sent"], "filterIds": [], "contactIds": [], "listIds": [],
                              "details": {"to": sent["to"], "cc": [], "bcc": [], "subject": subject, "attachmentIds": [],
                                          "originalMessageId": None, "incomingCopyIds": []}})
    return mm


def mail_with(mail, notices):
    """notices: list of (card id, day, start, room)."""
    talks = all_talks()
    for i, (cid, day, start, room) in enumerate(notices):
        title, speaker, _org, email, _fmt = talks[cid]
        first = speaker.split()[0]
        body = P(f"Hi {first},", f"Confirming your Northlight Summit slot for {title}: {fmt_day(day)}, {start}, {room} "
                 "(Brunel Rooms). The run of show has been updated accordingly.", "Best,\nRosa")
        mail = send_mail(mail, i, email, speaker, f"Your Northlight Summit slot: {fmt_day(day)}, {start}, {room}", body)
    return mail


# ---------------------------------------------------------------- registration export (input)
def registrations():
    interest = {"card-1": 284, "card-2": 104, "card-3": 176, "card-4": 152, "card-5": 131, "card-6": 69, "card-7": 63,
                "card-8": 77, "card-9": 41, "card-10": 236, "card-11": 119, "card-12": 141, "card-13": 167, "card-14": 198,
                "card-15": 88, "card-16": 72, "card-17": 95, "card-18": 84, "card-19": 58, "card-20": 71, "card-21": 22}
    talks = all_talks()
    rows = []
    for cid, n in interest.items():
        title, speaker, _o, _e, fmt = talks[cid]
        status = "waitlist" if cid in WAITLIST else "withdrawn" if cid == "card-21" else "scheduled"
        rows.append(["NLS26", f"NLS-{int(cid.split('-')[1]):03d}", title, speaker, fmt.lower(), status, str(n)])
    rows += [
        ["NPD27", "NPD-004", "Postmortems Without Blame", "Kirsten Holm", "talk", "proposed", "96"],
        ["NPD27", "NPD-001", "Partner Day Welcome", "Ama Mensah", "keynote", "scheduled", "143"],
        ["NPD27", "NPD-007", "Scaling Design Systems Without a Platform Team (encore)", "Priya Raman", "talk", "proposed", "81"],
        ["NPD27", "NPD-002", "Partner Pricing Roundtable", "Daniel Kowalski", "panel", "proposed", "37"],
        ["NPD27", "NPD-009", "Feature Flags for Partners", "Arjun Patel", "talk", "proposed", "29"],
        ["NPD27", "NPD-005", "Integrations Marketplace Update", "Jo Pritchard", "talk", "scheduled", "54"],
    ]
    rows.sort(key=lambda r: -int(r[6]))
    return [["event_code", "session_code", "session_title", "speaker", "format", "status", "interested"]] + rows


# ---------------------------------------------------------------- run of show (output)
def rows_from(trello, cal):
    """What a run that wrote the CSV from its own final board + calendar would produce."""
    by_title = {}
    for e in cal["events"]:
        by_title.setdefault(e["title"], e)
    out = [["day", "room", "start", "end", "session", "speaker"]]
    talks = all_talks()
    for (day, room), lid in DAY_ROOM_LIST.items():
        for cid in trello["lists"][lid]["cardIds"]:
            title = trello["cards"][cid]["title"]
            e = by_title.get(title)
            if e is None:
                continue
            out.append([e["start"][:10], room, e["start"][11:16], e["end"][11:16], title, talks[cid][1]])
    return out


def run(seed, order, cal_changes, notices):
    t = apply_board(seed["trello"], order)
    c = apply_calendar(seed["google_calendar"], cal_changes)
    y = mail_with(seed["yahoo_mail"], notices)
    return {"trello": t, "yahoo_mail": y, "google_calendar": c}, rows_from(t, c)


def golden_plan():
    return (copy.deepcopy(GOLDEN_ORDER), dict(GOLDEN_EVENT_CHANGES),
            [(cid, d, s, r) for cid, (_e, d, s, r) in SPEAKER_MAILS.items()])


def naive_plan():
    """First impressions everywhere: Priya<->Clara (the superseded proposal), Kirsten (waitlist #1 / Partner Day row),
    Nadia<->Olu (the declined request), board kept as the v2 draft otherwise; Bartek handled correctly."""
    order = {
        LIST_WAIT: ["card-20"],
        LIST_THU_T: ["card-1", "card-12", "card-7", "card-5", "card-4"],
        LIST_THU_M: ["card-8", "card-19", "card-3", "card-9"],
        LIST_FRI_T: ["card-10", "card-2", "card-13", "card-11", "card-14"],
        LIST_FRI_M: ["card-15", "card-17", "card-16", "card-18"],
        LIST_PULLED: ["card-21", "card-6"],
    }
    changes = {
        "evt_s02": (None, FRI, THAMES, "11:15", "12:00", None),
        "evt_s12": (None, THU, THAMES, "10:00", "10:45", None),
        "evt_s08": (None, THU, MERCER, "09:00", "09:45", None),
        "evt_s06": ("Postmortems Without Blame", THU, MERCER, "10:00", "10:45", "Speaker: Kirsten Holm (RelayOps)"),
        "evt_s13": (None, FRI, THAMES, "10:00", "10:45", None),
        "evt_s11": (None, FRI, THAMES, "14:00", "14:45", None),
    }
    notices = [("card-2", FRI, "11:15", THAMES), ("card-12", THU, "10:00", THAMES), ("card-19", THU, "10:00", MERCER),
               ("card-8", THU, "09:00", MERCER), ("card-13", FRI, "10:00", THAMES), ("card-11", FRI, "14:00", THAMES)]
    return order, changes, notices


def slip(kind):
    order, changes, notices = golden_plan()
    if kind == "swap_partner":  # follows Priya's own proposal (Clara) instead of Marcus's correction (Tomás)
        order[LIST_THU_T] = ["card-1", "card-12", "card-3", "card-4", "card-5"]
        order[LIST_FRI_T] = ["card-10", "card-11", "card-2", "card-13", "card-14"]
        order[LIST_FRI_M] = ["card-15", "card-16", "card-17", "card-18"]
        del changes["evt_s15"]
        changes["evt_s02"] = (None, FRI, THAMES, "11:15", "12:00", None)
        changes["evt_s12"] = (None, THU, THAMES, "10:00", "10:45", None)
        notices = [("card-2", FRI, "11:15", THAMES), ("card-12", THU, "10:00", THAMES)] + notices[2:]
    elif kind == "replacement":  # waitlist #1 / Partner Day row instead of NLS26 interest
        order[LIST_THU_M] = ["card-8", "card-19", "card-7", "card-9"]
        order[LIST_WAIT] = ["card-20"]
        changes["evt_s06"] = ("Postmortems Without Blame", THU, MERCER, "10:00", "10:45", "Speaker: Kirsten Holm (RelayOps)")
        notices = [n if n[0] != "card-20" else ("card-19", THU, "10:00", MERCER) for n in notices]
    elif kind == "declined":  # carries out Nadia's declined swap with Olu
        order[LIST_FRI_T] = ["card-10", "card-13", "card-12", "card-11", "card-14"]
        changes["evt_s13"] = (None, FRI, THAMES, "10:00", "10:45", None)
        changes["evt_s11"] = (None, FRI, THAMES, "14:00", "14:45", None)
        notices = notices + [("card-13", FRI, "10:00", THAMES), ("card-11", FRI, "14:00", THAMES)]
    elif kind == "draft":  # applies the e-mail changes but keeps the v2 draft rooms/order instead of the calendar
        order[LIST_THU_T] = ["card-1", "card-15", "card-7", "card-5", "card-4"]
        order[LIST_THU_M] = ["card-8", "card-20", "card-3", "card-9"]
        order[LIST_FRI_T] = ["card-10", "card-12", "card-11", "card-13", "card-14"]
        order[LIST_FRI_M] = ["card-2", "card-17", "card-16", "card-18"]
    elif kind == "noorder":  # right lists, but cards only appended via the Move dialog, never reordered
        order[LIST_THU_T] = ["card-1", "card-5", "card-4", "card-3", "card-15"]
        order[LIST_THU_M] = ["card-8", "card-9", "card-7", "card-20"]
        order[LIST_FRI_T] = ["card-10", "card-12", "card-11", "card-13", "card-14"]
        order[LIST_FRI_M] = ["card-17", "card-16", "card-18", "card-2"]
    return order, changes, notices


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def expected(golden_rows):
    talks = all_talks()
    return {
        "clock": CLOCK, "timezone": "Europe/London",
        "board_id": "board-1",
        "lists": {lid: {"title": LIST_TITLES[lid], "initial": INITIAL_ORDER.get(lid), "expected": GOLDEN_ORDER.get(lid)}
                  for lid in LIST_TITLES},
        "day_room_lists": {lid: {"day": d, "room": r} for (d, r), lid in DAY_ROOM_LIST.items()},
        "non_target_lists": {lid: ids for lid, ids in
                             [(LIST_LOG, [c[0] for c in LOGISTICS]), ("list-8", ["card-30", "card-31", "card-32"]),
                              ("list-9", ["card-33", "card-34"]), ("list-10", ["card-35", "card-36"]), ("list-11", ["card-37", "card-38"])]},
        "cards": {cid: {"title": v[0], "speaker": v[1], "email": v[3]} for cid, v in talks.items()},
        "calendar": {
            "bookings_calendar_id": "c2",
            "changed_events": {
                "evt_s02": {"title_contains": "Scaling Design Systems", "start": iso(FRI, "10:00"), "end": iso(FRI, "10:45"), "location_contains": "Mercer"},
                "evt_s15": {"title_contains": "Accessible Data Visualisation", "start": iso(THU, "10:00"), "end": iso(THU, "10:45"), "location_contains": "Thames"},
                "evt_s08": {"title_contains": "Instrumenting Onboarding Funnels", "start": iso(THU, "09:00"), "end": iso(THU, "09:45"), "location_contains": "Mercer"},
                "evt_s06": {"title_contains": "Feature Flags", "start": iso(THU, "10:00"), "end": iso(THU, "10:45"), "location_contains": "Mercer",
                            "old_title": "Edge Caching Deep Dive", "wrong_title_contains": "Postmortems"},
            },
            "unchanged_events": [e for e in [EVENT_OF[c] for c in SESSIONS] if e not in GOLDEN_EVENT_CHANGES]
                                + [f"evt_v{i:02d}" for i in range(1, 13)] + [f"evt_o{i:02d}" for i in range(1, 17)] + ["evt_h01", "evt_h02"],
        },
        "speaker_mails": {cid: {"to": e, "speaker": talks[cid][1], "day": d, "start": s, "room": r}
                          for cid, (e, d, s, r) in SPEAKER_MAILS.items()},
        "run_of_show_rows": golden_rows[1:],
        "run_of_show_columns": golden_rows[0],
        "registration_choice": {"chosen": "card-20", "not_chosen": "card-19",
                                "nls26_interest": {"card-19": 58, "card-20": 71}, "npd27_decoy": {"card-19": 96}},
    }


def main(out: Path):
    seed = {"trello": build_trello(), "yahoo_mail": build_mail(), "google_calendar": build_calendar()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, golden_rows = run(seed, *golden_plan())
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "run_of_show.csv", golden_rows)
    write_csv(out / "input" / "registrations_export.csv", registrations())
    write_json(out / "expected.json", expected(golden_rows))

    variants = {"golden": (golden, golden_rows), "nop": (seed, None), "naive": run(seed, *naive_plan())}
    for kind in ("swap_partner", "replacement", "declined", "draft"):
        variants[f"slip_{kind}"] = run(seed, *slip(kind))
    variants["append_only"] = run(seed, *slip("noorder"))
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "run_of_show.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
