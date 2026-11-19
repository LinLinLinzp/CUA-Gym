#!/usr/bin/env python3
"""World for the december-film-programme task (Reddit + GitLab + Google Calendar + local CSV).

Writes into <out>/:
  seed/{reddit,gitlab,google_calendar}.json     initial state per site
  golden/{reddit,gitlab,google_calendar}.json   state after a correct run
  golden_output/december_programme.csv          correct CLI deliverable
  input/distributor_quotes.csv                  agent-visible workspace input
  expected.json                                 hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/december_programme.csv}

The story: Hannah Okoye programmes the Lantern Street Film Society, a volunteer
community cinema in London. Members nominate films in a Reddit thread; the
programming rules live on the GitLab wiki of the lsfs-programme project; the
licence quotes from distributors are a local CSV; screenings get a GitLab issue,
a calendar entry and a Reddit announcement.

Traps (all resolvable from visible material):
  * The same film (Paris, Texas) was nominated twice; the wiki says add the
    nominations together (27 + 21 = 48), which makes it the top film.
  * "Solaris (Tarkovsky)" must be matched to the 1972 row of the quotes sheet,
    not the 2002 Soderbergh row (different year, certificate and fee).
  * The third December night (Thu 17 Dec) was moved by the hall to a Saturday
    matinee (19 Dec, film 14:30) in a stickied Reddit post; the calendar holds
    and the wiki venue page still show 17 Dec. The co-mod's reply in that post
    adds that the matinee must be a U/PG film, chosen after the two evenings.
  * Two-year no-repeat rule: My Neighbour Totoro (shown 2025-06-19, on the issue
    board) is out; The Red Shoes (last shown 2024-11-28, only in the wiki's
    pre-2025 history) is eligible again from 2026-11-28. "The Red Turtle"
    (2025-03-13) is a near-duplicate title on the board.
Plain constraints: DCP-only (Aftersun), licence not open until 2027 (Stalker),
fee cap 150 (Umbrellas of Cherbourg 165, Possession 175).
"""

import copy
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

CLOCK = "2026-11-18T09:30:00+00:00"
TZ = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 18, 9, 30, tzinfo=TZ)


def utc(local: str) -> str:
    """'2026-12-03 19:30' (London) -> '2026-12-03T19:30:00.000Z'."""
    dt = datetime.fromisoformat(local).replace(tzinfo=TZ).astimezone(ZoneInfo("UTC"))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ago(days=0, hours=0, minutes=0) -> str:
    dt = (NOW - timedelta(days=days, hours=hours, minutes=minutes)).astimezone(ZoneInfo("UTC"))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------- distributor quotes (local CSV)
# distributor, title, year, director, certificate, format, fee_gbp, licence_from, licence_to, runtime_min
QUOTES = [
    ("Curzon Film", "Aftersun", 2022, "Charlotte Wells", "15", "DCP", "95.00", "2026-09-01", "2027-08-31", 102),
    ("Curzon Film", "Paris, Texas", 1984, "Wim Wenders", "15", "Blu-ray", "130.00", "2026-06-01", "2027-05-31", 145),
    ("Arrow Films", "Solaris", 1972, "Andrei Tarkovsky", "PG", "Blu-ray", "140.00", "2026-01-01", "2027-12-31", 167),
    ("Park Circus", "Solaris", 2002, "Steven Soderbergh", "12A", "Blu-ray", "85.00", "2026-01-01", "2027-12-31", 99),
    ("Curzon Film", "Stalker", 1979, "Andrei Tarkovsky", "PG", "Blu-ray", "120.00", "2027-01-22", "2028-01-21", 161),
    ("Curzon Film", "Portrait of a Lady on Fire", 2019, "Celine Sciamma", "15", "Blu-ray", "125.00", "2026-03-01", "2027-02-28", 122),
    ("StudioCanal", "My Neighbour Totoro", 1988, "Hayao Miyazaki", "U", "Blu-ray", "145.00", "2026-01-01", "2027-12-31", 86),
    ("Curzon Film", "The Umbrellas of Cherbourg", 1964, "Jacques Demy", "U", "Blu-ray", "165.00", "2026-04-01", "2027-03-31", 91),
    ("BFI Distribution", "The Red Shoes", 1948, "Michael Powell, Emeric Pressburger", "U", "Blu-ray", "110.00", "2026-10-01", "2027-09-30", 133),
    ("StudioCanal", "Paddington 2", 2017, "Paul King", "PG", "Blu-ray", "95.00", "2026-01-01", "2027-12-31", 103),
    ("Second Run", "Wings of Desire", 1987, "Wim Wenders", "12", "Blu-ray", "120.00", "2026-06-01", "2027-05-31", 128),
    ("Second Run", "Possession", 1981, "Andrzej Zulawski", "18", "Blu-ray", "175.00", "2026-01-01", "2027-06-30", 124),
    ("BFI Distribution", "Brief Encounter", 1945, "David Lean", "PG", "Blu-ray", "95.00", "2026-01-01", "2027-12-31", 86),
    ("BFI Distribution", "A Matter of Life and Death", 1946, "Michael Powell, Emeric Pressburger", "U", "DCP; Blu-ray", "115.00", "2026-01-01", "2027-12-31", 104),
    ("Park Circus", "The Apartment", 1960, "Billy Wilder", "PG", "Blu-ray", "120.00", "2026-01-01", "2027-12-31", 125),
    ("Park Circus", "Some Like It Hot", 1959, "Billy Wilder", "PG", "DCP", "120.00", "2026-01-01", "2027-12-31", 121),
    ("StudioCanal", "The Ladykillers", 1955, "Alexander Mackendrick", "U", "Blu-ray", "90.00", "2026-01-01", "2027-12-31", 91),
    ("Curzon Film", "Perfect Days", 2023, "Wim Wenders", "PG", "DCP", "140.00", "2026-01-01", "2027-06-30", 124),
    ("Second Run", "Daisies", 1966, "Vera Chytilova", "15", "ProRes file", "80.00", "2026-01-01", "2027-12-31", 76),
    ("Arrow Films", "Ivan's Childhood", 1962, "Andrei Tarkovsky", "PG", "Blu-ray", "110.00", "2026-01-01", "2027-12-31", 95),
]
QUOTE = {(q[1], q[2]): q for q in QUOTES}


def quote_rows():
    head = ["distributor", "title", "year", "director", "certificate", "format", "fee_gbp",
            "licence_from", "licence_to", "runtime_min"]
    return [head] + [list(q) for q in sorted(QUOTES, key=lambda q: (q[0], q[1], q[2]))]


# ---------------------------------------------------------------- plans
def slot(date, time, title, year, votes):
    q = QUOTE[(title, year)]
    return {"date": date, "start_time": time, "film": title, "year": year, "certificate": q[4],
            "votes": votes, "licence_fee_gbp": q[6], "distributor": q[0], "runtime_min": q[9]}


GOLDEN_PLAN = [
    slot("2026-12-03", "19:30", "Paris, Texas", 1984, 48),
    slot("2026-12-10", "19:30", "Solaris", 1972, 44),
    slot("2026-12-19", "14:30", "The Red Shoes", 1948, 22),
]
PLANS = {
    "golden": GOLDEN_PLAN,
    # no merging of duplicates, ignores the hall move and the matinee rule,
    # first Solaris row that fits the old evening rules, no repeat check
    "naive": [
        slot("2026-12-03", "19:30", "Solaris", 2002, 44),
        slot("2026-12-10", "19:30", "Paris, Texas", 1984, 27),
        slot("2026-12-17", "19:30", "Portrait of a Lady on Fire", 2019, 25),
    ],
    "slip_merge": [
        slot("2026-12-03", "19:30", "Solaris", 1972, 44),
        slot("2026-12-10", "19:30", "Paris, Texas", 1984, 27),
        slot("2026-12-19", "14:30", "The Red Shoes", 1948, 22),
    ],
    "slip_move": [
        slot("2026-12-03", "19:30", "Paris, Texas", 1984, 48),
        slot("2026-12-10", "19:30", "Solaris", 1972, 44),
        slot("2026-12-17", "19:30", "Portrait of a Lady on Fire", 2019, 25),
    ],
    "slip_repeat": [
        slot("2026-12-03", "19:30", "Paris, Texas", 1984, 48),
        slot("2026-12-10", "19:30", "Solaris", 1972, 44),
        slot("2026-12-19", "14:30", "My Neighbour Totoro", 1988, 24),
    ],
    "slip_boundary": [
        slot("2026-12-03", "19:30", "Paris, Texas", 1984, 48),
        slot("2026-12-10", "19:30", "Solaris", 1972, 44),
        slot("2026-12-19", "14:30", "Paddington 2", 2017, 15),
    ],
    "slip_solaris": [
        slot("2026-12-03", "19:30", "Paris, Texas", 1984, 48),
        slot("2026-12-10", "19:30", "Solaris", 2002, 44),
        slot("2026-12-19", "14:30", "The Red Shoes", 1948, 22),
    ],
}

# ---------------------------------------------------------------- reddit
ME = "u_hannah"
LSFS = "s_lsfs"
FLAIRS = [
    {"id": "f_prog", "text": "Programme", "color": "#FFFFFF", "bgColor": "#0079D3"},
    {"id": "f_nom", "text": "Nominations", "color": "#FFFFFF", "bgColor": "#FF4500"},
    {"id": "f_admin", "text": "Admin", "color": "#1C1C1C", "bgColor": "#FFD635"},
    {"id": "f_review", "text": "Review", "color": "#FFFFFF", "bgColor": "#46D160"},
    {"id": "f_vol", "text": "Volunteers", "color": "#FFFFFF", "bgColor": "#7193FF"},
]

R_USERS = [
    ("u_hannah", "hannah_lsfs", 1840, 6210, "2019-03-02", "Programming at Lantern Street Film Society. Bring a cushion."),
    ("u_marta", "marta_lsfs", 960, 4120, "2020-01-14", "LSFS co-mod, hall bookings and door rota."),
    ("u_desert", "desertmotel", 310, 2210, "2021-07-09", ""),
    ("u_koda", "kodachrome_kid", 1420, 5530, "2018-05-23", "35mm or bust"),
    ("u_sea", "oceanofsolaris", 220, 1890, "2022-02-11", ""),
    ("u_sunset", "sunsetmixtape", 540, 1320, "2023-08-30", ""),
    ("u_zone", "zone_wanderer", 180, 990, "2021-11-02", ""),
    ("u_celine", "celine_julie", 760, 3010, "2019-09-19", "Rivette apologist"),
    ("u_catbus", "catbus_rider", 95, 640, "2024-01-05", ""),
    ("u_raincoat", "yellow_raincoat", 130, 870, "2022-06-17", ""),
    ("u_pointe", "pointe_shoes_pls", 410, 1760, "2020-10-28", "ballet, Powell & Pressburger, tea"),
    ("u_marm", "marmalade_sandwich", 60, 410, "2024-09-12", ""),
    ("u_angel", "berlin_angel", 330, 1210, "2021-04-04", ""),
    ("u_isa", "isabelle_a_stan", 75, 520, "2023-02-20", ""),
    ("u_twokids", "twokids_onebike", 140, 760, "2022-12-01", "Walthamstow. Dad of two."),
    ("u_pete", "projector_pete", 690, 2240, "2019-06-21", "LSFS projectionist"),
    ("u_ldn1", "northern_line_nomad", 2210, 9800, "2017-03-30", ""),
    ("u_ldn2", "e17_bagel", 380, 1500, "2020-05-15", ""),
    ("u_tf1", "longtake_larry", 5120, 22040, "2016-08-08", ""),
    ("u_tf2", "academy_ratio", 1730, 8340, "2018-01-19", ""),
    ("u_crit1", "spine_number_1000", 940, 4410, "2019-12-12", ""),
]

SUBREDDITS = [
    ("s_tf", "TrueFilm", "In-depth discussion of film.", "#1A1A1B", 2310000, 2140,
     ["Be civil", "No low-effort posts", "Mark spoilers"], ["u_tf1"]),
    ("s_ldn", "london", "News, events and chat for London.", "#E2231A", 1840000, 3320,
     ["Must relate to London", "No selling", "Be nice"], ["u_ldn1"]),
    (LSFS, "LanternStreetFilms", "Lantern Street Film Society: community cinema at St Brigid's Hall, Walthamstow. "
     "Thursday screenings, members pick the films.", "#3B2F63", 1460, 38,
     ["Be kind", "One nomination per top-level comment", "No piracy links", "Spoilers in review threads only"],
     ["u_hannah", "u_marta"]),
    ("s_crit", "criterion", "Criterion Collection discussion.", "#111111", 412000, 520,
     ["Stay on topic", "No sales spam"], ["u_crit1"]),
    ("s_box", "boxoffice", "Box office numbers and discussion.", "#0B6E4F", 690000, 870, ["Cite sources"], ["u_tf2"]),
    ("s_ghibli", "ghibli", "Studio Ghibli fans.", "#4B8F29", 950000, 990, ["Be kind", "Credit artists"], ["u_catbus"]),
]


def r_post(pid, sub, user, title, content, created, up, down=0, flair=None, sticky=False, locked=False):
    return {"id": pid, "subredditId": sub, "userId": user, "title": title, "content": content, "type": "text",
            "url": None, "flairId": flair, "upvotes": up, "downvotes": down, "created": created,
            "isStickied": sticky, "isLocked": locked, "isSpoiler": False, "isNSFW": False,
            "commentIds": [], "awards": [], "pollOptions": None}


def r_comment(cid, post, user, content, created, up, down=0, parent=None, edited=False, mod=False):
    return {"id": cid, "postId": post, "parentId": parent, "userId": user, "content": content,
            "upvotes": up, "downvotes": down, "created": created, "isEdited": edited,
            "isDistinguished": mod, "awards": []}


# Top-level nominations in the December thread: (id, user, text, up, down, days_ago)
NOMINATIONS = [
    ("c_n01", "u_sunset", "Aftersun (2022). Still can't listen to Under Pressure without crying. Needs a room full of people.", 57, 5, 16),
    ("c_n02", "u_desert", "Paris, Texas (1984). Harry Dean Stanton walking out of the desert, that red light in the peep-show booth. "
     "December is the right month for it.", 29, 2, 16),
    ("c_n03", "u_sea", "Solaris (Tarkovsky). Three hours of ocean and grief, perfect for the darkest month of the year.", 47, 3, 15),
    ("c_n04", "u_zone", "Stalker (1979), heard there's a new 4K restoration coming.", 41, 2, 15),
    ("c_n05", "u_celine", "Portrait of a Lady on Fire (2019). The last shot. That's the pitch.", 27, 2, 14),
    ("c_n06", "u_catbus", "My Neighbour Totoro! Something for the little ones before Christmas?", 26, 2, 13),
    ("c_n07", "u_raincoat", "The Umbrellas of Cherbourg (1964). It's basically a Christmas film if you squint.", 24, 1, 12),
    ("c_n08", "u_pointe", "The Red Shoes (1948). I know we showed it a while back but the restoration is gorgeous and it has been ages.", 23, 1, 11),
    ("c_n09", "u_koda", "Paris Texas (Wenders) - Ry Cooder's slide guitar through the hall speakers, please.", 22, 1, 9),
    ("c_n10", "u_marm", "Paddington 2. Don't @ me, it's a perfect film.", 17, 2, 8),
    ("c_n11", "u_angel", "Wings of Desire (1987)", 12, 1, 6),
    ("c_n12", "u_isa", "Possession (1981). For the brave.", 10, 1, 4),
]
NOMINATION_REPLIES = [
    ("c_r01", "c_n01", "u_pete", "Pretty sure Curzon only has it on DCP at the moment. We can't play DCP at St Brigid's.", 18, 0, 15),
    ("c_r02", "c_n01", "u_sunset", "ugh, fair. Leaving it up anyway in case that changes.", 6, 0, 15),
    ("c_r03", "c_n03", "u_koda", "Seconded. Bring a flask.", 9, 0, 14),
    ("c_r04", "c_n02", "u_celine", "Yes yes yes", 4, 0, 13),
    ("c_r05", "c_n06", "u_twokids", "My two would love this", 7, 0, 12),
    ("c_r06", "c_n09", "u_desert", "Ha, I already nominated it further up, but the more the merrier", 8, 0, 9),
    ("c_r07", "c_n10", "u_ldn2", "Correct opinion.", 5, 0, 8),
    ("c_r08", "c_n12", "u_twokids", "Maybe not for the matinee crowd :)", 6, 0, 4),
]


def build_reddit():
    users = [{"id": uid, "username": name, "avatar": avatar(name), "postKarma": pk, "commentKarma": ck,
              "cakeDay": f"{cake}T12:00:00.000Z", "about": about} for uid, name, pk, ck, cake, about in R_USERS]
    me = users[0]
    current = {**me, "joinedSubreddits": ["s_tf", LSFS, "s_ldn", "s_crit"],
               "savedPosts": ["p_tf2"], "savedComments": [], "hiddenPosts": [], "reportedPosts": []}
    subs = []
    for sid, name, desc, color, members, online, rules, mods in SUBREDDITS:
        subs.append({"id": sid, "name": name, "description": desc, "icon": avatar(name), "bannerColor": color,
                     "members": members, "online": online, "created": "2015-06-01T12:00:00.000Z" if sid != LSFS else "2019-03-02T12:00:00.000Z",
                     "rules": rules, "moderators": mods, "flairs": FLAIRS if sid == LSFS else []})

    posts, comments = [], []
    # --- r/LanternStreetFilms
    hall = r_post("p_hall", LSFS, "u_marta", "Change for December: no screening on Thu 17 Dec",
                  "Parish office rang this morning: St Brigid's needs the hall on the evening of Thursday 17 December for the "
                  "carol service rehearsal, so our third December night can't happen there.\n\n"
                  "They've offered us **Saturday 19 December, 14:00-17:00** instead and I've said yes. Doors 14:00, "
                  "film starts 14:30, we need to be packed up by 17:00.\n\n"
                  "3 and 10 December are unchanged (Thursday evenings as usual). I'll update the venue page on the wiki "
                  "when I get a minute.",
                  ago(days=1, hours=15), 64, 1, flair="f_admin", sticky=True)
    hall_comments = [
        r_comment("c_h1", "p_hall", "u_twokids", "A Saturday afternoon! Does that make it a family matinee? Mine could actually come for once.",
                  ago(days=1, hours=14), 21),
        r_comment("c_h2", "p_hall", "u_marta", "Yes, it's a matinee, so whatever we show on the 19th has to be a U or PG. "
                  "The evenings on the 3rd and 10th still go to the two top-voted films as usual, and the 19th gets the "
                  "best-voted U/PG nomination that's left after those two.",
                  ago(days=1, hours=13), 33, parent="c_h1", mod=True),
        r_comment("c_h3", "p_hall", "u_koda", "Saturday works much better for me tbh", ago(days=1, hours=10), 9),
        r_comment("c_h4", "p_hall", "u_pete", "I'll bring the small speakers for the afternoon, the hall's echoey when it's light out.",
                  ago(days=1, hours=8), 6),
    ]
    nom = r_post("p_nom", LSFS, ME, "December 2026 nominations (closed)",
                 "One film per top-level comment. If someone has already nominated your film, upvote theirs instead of "
                 "posting it again. Voting closes Sunday 15 Nov at midnight, then we tally per the Programming rules "
                 "on the wiki.\n\nEdit: closed! Thanks everyone, programme coming this week.",
                 ago(days=17, hours=1), 88, 2, flair="f_nom", locked=True)
    nom_comments = [r_comment(cid, "p_nom", u, text, ago(days=d, hours=3), up, down)
                    for cid, u, text, up, down, d in NOMINATIONS]
    nom_comments += [r_comment(cid, "p_nom", u, text, ago(days=d, hours=1), up, down, parent=parent)
                     for cid, parent, u, text, up, down, d in NOMINATION_REPLIES]
    nom_comments.append(r_comment("c_nmod", "p_nom", ME, "Nominations are closed, thanks all! Tally this week.",
                                  ago(days=2, hours=9), 14, mod=True))
    nov = r_post("p_nov", LSFS, ME, "November 2026 programme",
                 "Thu 5 Nov - Persepolis (2007)\nThu 12 Nov - Close-Up (1990)\nThu 19 Nov - The Night of the Hunter (1955)\n\n"
                 "Doors 19:00, film 19:30 at St Brigid's Hall, 14 Lantern Street. GBP 5 on the door, members free.",
                 ago(days=28), 71, 1, flair="f_prog")
    octo = r_post("p_oct", LSFS, ME, "October 2026 programme",
                  "Thu 1 Oct - Cleo from 5 to 7 (1962)\nThu 8 Oct - Picnic at Hanging Rock (1975)\nThu 15 Oct - The Wicker Man (1973)\n\n"
                  "Doors 19:00, film 19:30 at St Brigid's Hall. GBP 5 on the door, members free.",
                  ago(days=57), 66, 2, flair="f_prog")
    others = [
        r_post("p_hunter", LSFS, "u_pete", "Night of the Hunter tomorrow - bring a cushion, the new chairs haven't arrived",
               "Sorry all. Supplier says first week of December.", ago(hours=14), 23, flair="f_admin"),
        r_post("p_vol", LSFS, "u_marta", "Volunteers needed: December door shifts",
               "Need two people per night on the door and one on tea. Reply here or ping me.", ago(days=5), 19, flair="f_vol"),
        r_post("p_closeup", LSFS, "u_celine", "Review thread: Close-Up (12 Nov)",
               "What did everyone make of it? The ending on the motorbike wrecked me.", ago(days=6), 31, flair="f_review"),
        r_post("p_fund", LSFS, ME, "Projector fund: we hit GBP 1,200!",
               "Thank you to everyone who chipped in at the door. New lamp ordered.", ago(days=24), 102, flair="f_admin"),
        r_post("p_scarf", LSFS, "u_twokids", "Lost: green scarf after Persepolis",
               "Left it on a chair near the back. Anyone see it?", ago(days=12), 7),
        r_post("p_persep", LSFS, "u_koda", "Review thread: Persepolis (5 Nov)", "Thoughts?", ago(days=13), 18, flair="f_review"),
    ]
    # --- other subs (noise)
    noise = [
        r_post("p_tf1", "s_tf", "u_tf1", "Why does Tarkovsky's sense of time still feel radical?",
               "Rewatched Stalker last week and the dolly shots feel longer every time.", ago(days=2), 1840, 40),
        r_post("p_tf2", "s_tf", "u_tf2", "The best final shots in cinema - a thread",
               "Portrait of a Lady on Fire, Call Me by Your Name, The Third Man...", ago(days=3), 3420, 120),
        r_post("p_tf3", "s_tf", "u_celine", "Rivette's Celine and Julie is the most fun three hours you'll have",
               "Fight me.", ago(days=4), 640, 22),
        r_post("p_ldn1", "s_ldn", "u_ldn1", "Victoria line suspended this weekend",
               "Walthamstow to Seven Sisters, replacement buses.", ago(days=1), 920, 15),
        r_post("p_ldn2", "s_ldn", "u_ldn2", "Best community cinemas in London?",
               "Moved here recently, looking for cheap, friendly screenings.", ago(days=3), 410, 9),
        r_post("p_ldn3", "s_ldn", "u_ldn1", "Christmas markets worth the trip", "Not Winter Wonderland please.", ago(days=2), 288, 31),
        r_post("p_crit1", "s_crit", "u_crit1", "Barnes & Noble 50% off sale starts Friday", "Usual drill.", ago(days=1), 1210, 18),
        r_post("p_crit2", "s_crit", "u_crit1", "New Powell & Pressburger box announced", "Includes The Red Shoes and A Matter of Life and Death.", ago(days=6), 760, 12),
        r_post("p_box1", "s_box", "u_tf2", "Weekend box office: holiday season kicks off early", "Numbers inside.", ago(days=2), 530, 44),
        r_post("p_gh1", "s_ghibli", "u_catbus", "Totoro re-release screenings in the UK?", "Anyone know if there are any this winter?", ago(days=9), 340, 4),
    ]
    noise_comments = [
        r_comment("c_x1", "p_ldn2", "u_ldn1", "Lantern Street in Walthamstow is lovely, GBP 5 and they do tea.", ago(days=3), 88),
        r_comment("c_x2", "p_ldn2", ME, "Thanks! We're on r/LanternStreetFilms, programme goes up there every month.", ago(days=2, hours=20), 41, parent="c_x1"),
        r_comment("c_x3", "p_tf1", "u_tf2", "The time is the point.", ago(days=2), 310),
        r_comment("c_x4", "p_tf2", "u_celine", "Portrait's last shot is unbeatable.", ago(days=3), 220),
        r_comment("c_x5", "p_closeup", "u_koda", "Best thing we've shown this year.", ago(days=6), 12),
        r_comment("c_x6", "p_vol", "u_angel", "I can do the 3rd.", ago(days=4), 4),
        r_comment("c_x7", "p_gh1", "u_ldn2", "Check Lantern Street, they did Spirited Away last summer.", ago(days=8), 15),
        r_comment("c_x8", "p_hunter", "u_koda", "Bringing two.", ago(hours=12), 5),
    ]
    posts = [hall, others[0], nom, others[1], others[2], others[4], others[5], nov, others[3], octo] + noise
    comments = hall_comments + nom_comments + noise_comments
    by_post = {}
    for c in comments:
        by_post.setdefault(c["postId"], []).append(c["id"])
    for p in posts:
        p["commentIds"] = by_post.get(p["id"], [])
    posts.sort(key=lambda p: p["created"], reverse=True)

    votes = [
        {"id": "v1", "userId": ME, "targetId": "c_n03", "targetType": "comment", "value": 1},
        {"id": "v2", "userId": ME, "targetId": "p_hall", "targetType": "post", "value": 1},
        {"id": "v3", "userId": ME, "targetId": "p_tf2", "targetType": "post", "value": 1},
        {"id": "v4", "userId": ME, "targetId": "c_h2", "targetType": "comment", "value": 1},
    ]
    notifications = [
        {"id": "n1", "type": "reply", "fromUserId": "u_twokids", "postId": "p_hall", "commentId": "c_h1",
         "content": "A Saturday afternoon! Does that make it a family matinee?", "read": False, "created": ago(days=1, hours=14)},
        {"id": "n2", "type": "post_reply", "fromUserId": "u_isa", "postId": "p_nom", "commentId": "c_n12",
         "content": "Possession (1981). For the brave.", "read": True, "created": ago(days=4)},
        {"id": "n3", "type": "reply", "fromUserId": "u_ldn1", "postId": "p_ldn2", "commentId": "c_x1",
         "content": "Lantern Street in Walthamstow is lovely", "read": True, "created": ago(days=3)},
        {"id": "n4", "type": "upvote", "fromUserId": "u_koda", "postId": "p_fund", "commentId": None,
         "content": "Your post reached 100 upvotes", "read": True, "created": ago(days=20)},
    ]
    awards = [
        {"id": "silver", "name": "Silver", "icon": "\U0001F948", "cost": 100},
        {"id": "gold", "name": "Gold", "icon": "\U0001F947", "cost": 500},
        {"id": "wholesome", "name": "Wholesome", "icon": "\U0001F9AD", "cost": 125},
        {"id": "helpful", "name": "Helpful", "icon": "\U0001F91D", "cost": 150},
    ]
    return {"currentUser": current, "users": users, "subreddits": subs, "posts": posts, "comments": comments,
            "votes": votes, "notifications": notifications, "awards": awards}


# ---------------------------------------------------------------- gitlab
ME_GL = {"id": 7, "name": "Hannah Okoye", "username": "hokoye", "avatarUrl": avatar("Hannah Okoye")}
PROG = 1  # lsfs-programme

# Board history since the move to GitLab (Jan 2025): two screenings a month, three from Sep 2026.
HISTORY = [
    ("2025-01-09", "Tokyo Story"), ("2025-01-23", "Brief Encounter"),
    ("2025-02-06", "Chungking Express"), ("2025-02-20", "The Third Man"),
    ("2025-03-13", "The Red Turtle"), ("2025-03-27", "La Haine"),
    ("2025-04-10", "Kes"), ("2025-04-24", "Rear Window"),
    ("2025-05-08", "Stop Making Sense"), ("2025-05-22", "Do the Right Thing"),
    ("2025-06-05", "Local Hero"), ("2025-06-19", "My Neighbour Totoro"),
    ("2025-07-10", "Some Like It Hot"), ("2025-07-24", "Jaws"),
    ("2025-08-07", "Withnail and I"), ("2025-08-21", "Moonlight"),
    ("2025-09-04", "Rashomon"), ("2025-09-18", "Wadjda"),
    ("2025-10-02", "Black Narcissus"), ("2025-10-16", "Don't Look Now"),
    ("2025-11-06", "Pather Panchali"), ("2025-11-20", "The Apartment"),
    ("2025-12-04", "It's a Wonderful Life"), ("2025-12-11", "The Muppet Christmas Carol"),
    ("2026-01-08", "Wild Strawberries"), ("2026-01-22", "Ratcatcher"),
    ("2026-02-05", "In the Mood for Love"), ("2026-02-19", "Lady Bird"),
    ("2026-03-05", "Bicycle Thieves"), ("2026-03-19", "The 400 Blows"),
    ("2026-04-09", "Mustang"), ("2026-04-23", "Ugetsu"),
    ("2026-05-07", "Seven Samurai"), ("2026-05-21", "Babette's Feast"),
    ("2026-06-04", "The Ladykillers"), ("2026-06-18", "Spirited Away"),
    ("2026-07-09", "Yi Yi"), ("2026-07-23", "Amelie"),
    ("2026-08-06", "Happy Together"), ("2026-08-20", "The Lives of Others"),
    ("2026-09-03", "Celine and Julie Go Boating"), ("2026-09-10", "Pan's Labyrinth"), ("2026-09-17", "Breathless"),
    ("2026-10-01", "Cleo from 5 to 7"), ("2026-10-08", "Picnic at Hanging Rock"), ("2026-10-15", "The Wicker Man"),
    ("2026-11-05", "Persepolis"), ("2026-11-12", "Close-Up"),
]
UPCOMING = ("2026-11-19", "The Night of the Hunter")

PRE_2025_HISTORY = """# Screening history (before the issue board)

We moved screening tracking to the issue board in January 2025. Everything before that is listed here.

## 2024
| Date | Film |
|---|---|
| 2024-01-11 | Paths of Glory |
| 2024-01-25 | Cinema Paradiso |
| 2024-02-08 | Groundhog Day |
| 2024-02-22 | The Lady Vanishes |
| 2024-03-14 | Nausicaa of the Valley of the Wind |
| 2024-03-28 | Paper Moon |
| 2024-04-11 | The Gleaners and I |
| 2024-04-25 | Sweet Smell of Success |
| 2024-05-09 | Playtime |
| 2024-05-23 | Daughters of the Dust |
| 2024-06-13 | The Railway Children |
| 2024-06-27 | Jeanne Dielman |
| 2024-07-11 | Singin' in the Rain |
| 2024-07-25 | Beau Travail |
| 2024-09-12 | A Matter of Life and Death |
| 2024-09-26 | Cure |
| 2024-10-10 | Nosferatu (1922) |
| 2024-10-24 | Carnival of Souls |
| 2024-11-14 | Whisky Galore! |
| 2024-11-28 | The Red Shoes |
| 2024-12-05 | Meet Me in St. Louis |
| 2024-12-12 | Tokyo Godfather |

## 2023
| Date | Film |
|---|---|
| 2023-09-14 | Taste of Cherry |
| 2023-09-28 | The Long Day Closes |
| 2023-10-12 | Eyes Without a Face |
| 2023-10-26 | Night of the Living Dead |
| 2023-11-09 | Two Days, One Night |
| 2023-11-23 | All That Heaven Allows |
| 2023-12-07 | The Shop Around the Corner |
| 2023-12-14 | Home Alone |
"""

RULES = """# Programming rules

How we turn the members' nomination thread on r/LanternStreetFilms into a month's programme. Agreed at the AGM, March 2025.

1. **Score.** A nomination's score is the net votes it shows in the thread once voting has closed. Only top-level comments are nominations; replies don't count. If the same film was nominated more than once, add those nominations together and treat them as one.
2. **No repeats within two years.** A film isn't eligible again until two years after its last LSFS screening. Screenings since January 2025 are the issues on our board; older ones are on the Screening history page.
3. **Licence.** We only programme films we have a current licence quote for, valid on the screening date. Quotes come in through the distributors' quote sheet that Hannah keeps. Maximum licence fee is GBP 150 per screening.
4. **Format.** St Brigid's has a Blu-ray player and a laptop, no DCP server. Blu-ray or a digital file only; DCP-only titles are out.
5. **Order.** The highest-scoring eligible film takes the first date of the month, the next one the second date, and so on.
6. **Paperwork.** Every programmed screening gets an issue on this board titled `Screening YYYY-MM-DD: Film title` with the label `screening`. Put the distributor and the licence fee in the description so Marta can raise the PO. Close the issue after the night.
"""

VENUE = """# Venue handbook: St Brigid's Hall

14 Lantern Street, London E17. Parish office: 020 7946 0321 (Mon-Thu mornings).

## Evening screenings
- Hall from 18:30, doors 19:00, **film 19:30**, out by 22:30.
- Chairs are stacked in the side room; put them back in rows of ten.
- Projector, screen and Blu-ray player live in the locked cupboard (code on the volunteer sheet).

## December 2026 hall bookings
Thursdays 3, 10 and 17 December, 18:30-22:30.

## Accessibility
Step-free from the side entrance. Hearing loop works in the front four rows.
"""

LICENSING = """# Licensing

- Non-theatrical licence per screening, flat fee, invoiced after the night.
- Distributors send quotes as a sheet (title, year, certificate, formats, fee, licence window). Hannah keeps the latest export.
- Certificates are BBFC ones as listed by the distributor.
- Raise a PO with Marta once a screening is confirmed; she needs the distributor and the fee.
"""

HOME = """# lsfs-programme

Planning space for the Lantern Street Film Society programme.

- [Programming rules](Programming rules)
- [Venue handbook](Venue handbook)
- [Licensing](Licensing)
- [Screening history](Screening history)
"""


def build_gitlab():
    projects = [
        {"id": 1, "name": "lsfs-programme", "description": "Programme planning, licensing and the screening log for Lantern Street Film Society.",
         "visibility": "private", "stars": 4, "forks": 0, "updatedAt": ago(days=1),
         "branches": ["main"],
         "files": [
             {"name": "README.md", "type": "file", "content": "# lsfs-programme\n\nScreening issues live on the board, rules on the wiki.\n"},
             {"name": "templates", "type": "folder", "children": [
                 {"name": "programme_notes.md", "type": "file", "content": "# {Film} ({Year})\n\nIntro: 3 minutes max.\n"},
                 {"name": "door_sheet.md", "type": "file", "content": "# Door sheet\n\n| Name | Member? | Paid |\n|---|---|---|\n"},
             ]},
         ]},
        {"id": 2, "name": "lsfs-website", "description": "Static site for lanternstreetfilms.org.uk (Eleventy).",
         "visibility": "public", "stars": 6, "forks": 1, "updatedAt": ago(days=3),
         "branches": ["main", "december-listings", "fix/mobile-nav"],
         "files": [{"name": "README.md", "type": "file", "content": "# lsfs-website\n\n`npm run build`\n"},
                   {"name": "package.json", "type": "file", "content": "{\n  \"name\": \"lsfs-website\",\n  \"private\": true\n}"}]},
        {"id": 3, "name": "projector-kit", "description": "Inventory and setup notes for the projection kit.",
         "visibility": "private", "stars": 1, "forks": 0, "updatedAt": ago(days=20),
         "branches": ["main"], "files": [{"name": "README.md", "type": "file", "content": "# projector-kit\n\nLamp hours log and cable list.\n"}]},
        {"id": 4, "name": "zine-archive", "description": "Scans of the LSFS paper zine, 2019-2023.",
         "visibility": "public", "stars": 3, "forks": 0, "updatedAt": ago(days=90),
         "branches": ["main"], "files": [{"name": "README.md", "type": "file", "content": "# zine-archive\n"}]},
    ]
    issues, nid = [], 1
    for date, film in HISTORY:
        issues.append({"id": nid, "projectId": PROG, "title": f"Screening {date}: {film}",
                       "description": "Licence confirmed. Closed after the night.", "status": "closed",
                       "labels": ["screening"], "assignee": "Hannah Okoye"})
        nid += 1
    issues.append({"id": nid, "projectId": PROG, "title": f"Screening {UPCOMING[0]}: {UPCOMING[1]}",
                   "description": "Distributor: BFI Distribution. Licence fee GBP 95.00.", "status": "in_progress",
                   "labels": ["screening"], "assignee": "Hannah Okoye"})
    nid += 1
    for title, desc, status, labels, who in [
        ("Volunteer rota: December door shifts", "Marta is collecting names on Reddit.", "open", ["volunteers"], "Marta Silva"),
        ("Replace the long HDMI cable (flaky)", "Drops signal if anyone steps on it.", "open", ["kit"], "Pete Adeyemi"),
        ("Aftersun: ask Curzon when the Blu-ray licence opens (DCP only for now)", "Members keep nominating it.", "open", ["licensing"], "Hannah Okoye"),
        ("Renew public liability insurance before January", "Policy ends 31 Dec.", "open", ["admin"], "Marta Silva"),
        ("Programme notes template for 2027", "Shorter intros, add certificate.", "in_progress", ["admin"], "Hannah Okoye"),
        ("Order 20 more chairs", "Done via parish grant.", "closed", ["kit"], "Marta Silva"),
    ]:
        issues.append({"id": nid, "projectId": PROG, "title": title, "description": desc, "status": status,
                       "labels": labels, "assignee": who})
        nid += 1
    for pid, title, status, labels in [
        (2, "Update listings page for December", "open", ["content"]),
        (2, "Mobile nav overlaps logo", "in_progress", ["bug"]),
        (2, "Add accessibility page", "closed", ["content"]),
        (3, "Log lamp hours after Night of the Hunter", "open", ["kit"]),
        (4, "Scan issue 14", "open", ["scanning"]),
    ]:
        issues.append({"id": nid, "projectId": pid, "title": title, "description": "", "status": status,
                       "labels": labels, "assignee": None})
        nid += 1

    wiki = [
        {"id": 1, "projectId": PROG, "title": "Home", "content": HOME},
        {"id": 2, "projectId": PROG, "title": "Programming rules", "content": RULES},
        {"id": 3, "projectId": PROG, "title": "Venue handbook", "content": VENUE},
        {"id": 4, "projectId": PROG, "title": "Licensing", "content": LICENSING},
        {"id": 5, "projectId": PROG, "title": "Screening history", "content": PRE_2025_HISTORY},
        {"id": 6, "projectId": 2, "title": "Home", "content": "# lsfs-website\n\nDeploys from main via CI."},
    ]

    def stage(i, name, status, job, dur):
        return {"id": i, "name": name, "status": status, "jobs": [{"id": i, "name": job, "status": status, "duration": dur}]}

    pipelines = [
        {"id": 301, "projectId": 2, "status": "success", "branch": "main", "commit": "4be91c2", "message": "November listings",
         "duration": "1m 12s", "createdAt": ago(days=28), "stages": [stage(1, "build", "success", "eleventy", "48s"), stage(2, "deploy", "success", "pages", "24s")]},
        {"id": 302, "projectId": 2, "status": "failed", "branch": "fix/mobile-nav", "commit": "a07de11", "message": "try flex wrap",
         "duration": "51s", "createdAt": ago(days=3), "stages": [stage(3, "build", "failed", "eleventy", "51s")]},
        {"id": 303, "projectId": 2, "status": "success", "branch": "december-listings", "commit": "c13f0aa", "message": "placeholder December page",
         "duration": "1m 05s", "createdAt": ago(days=2), "stages": [stage(4, "build", "success", "eleventy", "47s")]},
    ]
    merge_requests = [
        {"id": 11, "projectId": 2, "title": "December listings page", "sourceBranch": "december-listings", "targetBranch": "main",
         "status": "open", "author": "Pete Adeyemi", "createdAt": ago(days=2), "reviewers": []},
        {"id": 10, "projectId": 2, "title": "Fix mobile nav", "sourceBranch": "fix/mobile-nav", "targetBranch": "main",
         "status": "open", "author": "Pete Adeyemi", "createdAt": ago(days=3), "reviewers": []},
        {"id": 9, "projectId": 2, "title": "November listings", "sourceBranch": "november-listings", "targetBranch": "main",
         "status": "merged", "author": "Hannah Okoye", "createdAt": ago(days=29), "reviewers": []},
    ]
    return {
        "currentUser": ME_GL, "projects": projects, "pipelines": pipelines, "issues": issues,
        "mergeRequests": merge_requests, "registry": [],
        "snippets": [{"id": 1, "title": "Door count tally", "code": "awk -F, '{s+=$3} END {print s}' door.csv", "language": "bash", "author": "Hannah Okoye"}],
        "wiki": wiki, "vulnerabilities": [],
        "milestones": [{"id": 1, "projectId": PROG, "title": "Spring 2027 season", "dueDate": "2027-03-01", "progress": 10}],
        "releases": [],
    }


# ---------------------------------------------------------------- google calendar
CAL_LSFS = "c2"
HALL = "St Brigid's Hall, 14 Lantern Street"


def g_event(eid, cal, title, start_local, end_local, location="", description="", recurring="none", all_day=False,
            color=None, guests=None):
    colors = {"c1": "bg-blue-500", "c2": "bg-green-500", "c3": "bg-purple-500", "c4": "bg-yellow-500"}
    return {"id": eid, "calendarId": cal, "title": title, "start": utc(start_local), "end": utc(end_local),
            "allDay": all_day, "location": location, "description": description, "guests": guests or [],
            "color": color or colors[cal], "recurring": recurring, "reminders": [{"type": "popup", "minutes": 30}]}


def build_calendar():
    ev = []
    n = 0

    def add(*a, **k):
        nonlocal n
        n += 1
        ev.append(g_event(f"evt_{n:03d}", *a, **k))

    for date, film in [("2026-10-01", "Cleo from 5 to 7"), ("2026-10-08", "Picnic at Hanging Rock"),
                       ("2026-10-15", "The Wicker Man"), ("2026-11-05", "Persepolis"),
                       ("2026-11-12", "Close-Up"), ("2026-11-19", "The Night of the Hunter")]:
        add(CAL_LSFS, f"LSFS: {film}", f"{date} 19:30", f"{date} 22:00", location=HALL,
            description="Doors 19:00. Hall from 18:30.")
    stale_ids = {}
    for date in ("2026-12-03", "2026-12-10", "2026-12-17"):
        add(CAL_LSFS, "St Brigid's Hall hold (LSFS)", f"{date} 18:30", f"{date} 22:30", location=HALL,
            description="Hall booked for screening night. Parish office 020 7946 0321.")
        stale_ids[date] = ev[-1]["id"]
    add(CAL_LSFS, "LSFS committee", "2026-11-24 19:00", "2026-11-24 20:30", location="The Crown & Anchor, Hoe St")
    add(CAL_LSFS, "LSFS committee", "2026-12-15 19:00", "2026-12-15 20:30", location="The Crown & Anchor, Hoe St")
    add(CAL_LSFS, "Pick up new chairs (van)", "2026-12-02 10:00", "2026-12-02 11:30", location="Parish storage")
    add("c1", "Yoga", "2026-11-03 07:30", "2026-11-03 08:30", location="Leyton Leisure Centre", recurring="weekly")
    add("c1", "Dentist", "2026-11-20 08:40", "2026-11-20 09:20", location="Hoe St Dental")
    add("c1", "Work: quarterly review", "2026-11-23 14:00", "2026-11-23 15:00", location="Office")
    add("c1", "Haircut", "2026-11-27 12:30", "2026-11-27 13:15")
    add("c1", "Secret Santa drinks", "2026-12-18 18:00", "2026-12-18 21:00", location="The Bell, E17")
    add("c1", "Lunch with Priya", "2026-12-19 12:00", "2026-12-19 13:30", location="Eat 17")
    add("c1", "Barbican: Kubrick talk", "2026-12-05 18:30", "2026-12-05 20:30", location="Barbican Cinema 1")
    add("c1", "Work: team offsite", "2026-12-09 09:00", "2026-12-09 17:00", location="Shoreditch")
    add("c1", "Boiler service", "2026-11-25 08:00", "2026-11-25 10:00")
    add("c3", "Mum's birthday dinner", "2026-11-28 19:00", "2026-11-28 22:00", location="Dalston")
    add("c3", "Train to Leeds", "2026-12-23 10:03", "2026-12-23 12:20", location="King's Cross")
    add("c3", "Christmas at Mum's", "2026-12-24 00:00", "2026-12-27 00:00", all_day=True)
    add("c4", "Christmas Day", "2026-12-25 00:00", "2026-12-26 00:00", all_day=True)
    add("c4", "Boxing Day", "2026-12-26 00:00", "2026-12-27 00:00", all_day=True)
    add("c4", "New Year's Day", "2027-01-01 00:00", "2027-01-02 00:00", all_day=True)
    add("c4", "Remembrance Sunday", "2026-11-08 00:00", "2026-11-09 00:00", all_day=True)

    state = {
        "user": {"id": "u1", "username": "Hannah Okoye", "email": "hannah.okoye@lanternstreetfilms.org.uk",
                 "avatar": avatar("Hannah Okoye")},
        "calendars": [
            {"id": "c1", "name": "Hannah Okoye", "color": "bg-blue-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c2", "name": "Lantern Street FS", "color": "bg-green-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c3", "name": "Family", "color": "bg-purple-500", "textColor": "text-white", "visible": True, "userId": "u1"},
            {"id": "c4", "name": "UK holidays", "color": "bg-yellow-500", "textColor": "text-white", "visible": True, "userId": "u1"},
        ],
        "otherCalendars": [],
        "events": ev,
        "view": "month",
        "currentDate": "2026-11-18T09:30:00.000Z",
        "sidebarOpen": True,
        "settings": {"weekStart": 1, "defaultDuration": 60},
    }
    return state, stale_ids


# ---------------------------------------------------------------- apply a plan (same mutations the UIs make)
DAY = {"2026-12-03": "Thu 3 Dec", "2026-12-10": "Thu 10 Dec", "2026-12-17": "Thu 17 Dec", "2026-12-19": "Sat 19 Dec"}


def apply_plan(states, plan, tag):
    reddit, gitlab, cal = states["reddit"], states["gitlab"], states["google_calendar"]
    # GitLab: Issues.jsx createIssue
    for s in plan:
        gitlab["issues"].append({
            "id": max(i["id"] for i in gitlab["issues"]) + 1, "projectId": PROG,
            "title": f"Screening {s['date']}: {s['film']}",
            "description": f"Distributor: {s['distributor']}. Licence fee GBP {s['licence_fee_gbp']}.",
            "status": "open", "labels": ["screening"], "assignee": ME_GL["name"]})
    # Calendar: EventModal create mode
    for i, s in enumerate(plan):
        start = f"{s['date']} {s['start_time']}"
        end = f"{s['date']} {'17:00' if s['start_time'] == '14:30' else '22:00'}"
        cal["events"].append({
            "title": f"LSFS: {s['film']}", "start": utc(start), "end": utc(end),
            "allDay": False, "location": HALL, "description": "", "calendarId": CAL_LSFS, "guests": [],
            "color": "bg-blue-500", "recurring": "none", "reminders": [{"type": "popup", "minutes": 10}],
            "id": f"{tag}-0000-4000-8000-00000000000{i}"})
    # Reddit: CreatePostPage -> addPost
    lines = []
    for s in plan:
        extra = ", family matinee, doors 14:00, film 14:30" if s["start_time"] == "14:30" else ""
        lines.append(f"{DAY[s['date']]} - {s['film']} ({s['year']}){extra}")
    body = "\n".join(lines) + "\n\nEvenings: doors 19:00, film 19:30 at St Brigid's Hall, 14 Lantern Street. GBP 5 on the door, members free."
    reddit["posts"].insert(0, {
        "id": f"{tag[:3]}post1", "subredditId": LSFS, "userId": ME, "title": "December 2026 programme",
        "content": body, "type": "text", "url": None, "flairId": "f_prog", "upvotes": 1, "downvotes": 0,
        "created": "2026-11-18T10:15:00.000Z", "isStickied": False, "isLocked": False, "isSpoiler": False,
        "isNSFW": False, "commentIds": [], "awards": [], "pollOptions": None})


def programme_rows(plan):
    rows = [["date", "start_time", "film", "year", "certificate", "votes", "licence_fee_gbp"]]
    for s in plan:
        rows.append([s["date"], s["start_time"], s["film"], s["year"], s["certificate"], s["votes"], s["licence_fee_gbp"]])
    return rows


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    cal, stale_ids = build_calendar()
    seed = {"reddit": build_reddit(), "gitlab": build_gitlab(), "google_calendar": cal}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)

    golden = copy.deepcopy(seed)
    apply_plan(golden, GOLDEN_PLAN, "golden")
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "december_programme.csv", programme_rows(GOLDEN_PLAN))
    write_csv(out / "input" / "distributor_quotes.csv", quote_rows())

    nominated = ["Aftersun", "Paris, Texas", "Solaris", "Stalker", "Portrait of a Lady on Fire", "My Neighbour Totoro",
                 "The Umbrellas of Cherbourg", "The Red Shoes", "Paddington 2", "Wings of Desire", "Possession"]
    golden_titles = {s["film"] for s in GOLDEN_PLAN}
    write_json(out / "expected.json", {
        "clock": CLOCK, "timezone": "Europe/London",
        "screenings": GOLDEN_PLAN,
        "not_selected_nominations": [t for t in nominated if t not in golden_titles],
        "wrong_solaris": {"year": 2002, "certificate": "12A", "licence_fee_gbp": "85.00"},
        "gitlab": {"project_id": PROG, "label": "screening", "title_format": "Screening YYYY-MM-DD: Film title",
                   "seed_issue_ids": [i["id"] for i in seed["gitlab"]["issues"]]},
        "google_calendar": {"calendar_id": CAL_LSFS, "location_contains": "St Brigid",
                            "stale_hold_ids": stale_ids, "seed_event_ids": [e["id"] for e in cal["events"]]},
        "reddit": {"subreddit_id": LSFS, "flair_id": "f_prog", "user_id": ME,
                   "seed_post_ids": [p["id"] for p in seed["reddit"]["posts"]]},
        "output_file": "/workspace/output/december_programme.csv",
    })

    for name, plan in PLANS.items():
        if name == "golden":
            states = golden
        else:
            states = copy.deepcopy(seed)
            apply_plan(states, plan, name.replace("_", ""))
        for site in seed:
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
            write_json(out / "variants" / name / "state" / site / "current.json", states[site])
        write_csv(out / "variants" / name / "output" / "december_programme.csv", programme_rows(plan))
    for site in seed:
        write_json(out / "variants" / "nop" / "state" / site / "initial.json", seed[site])
        write_json(out / "variants" / "nop" / "state" / site / "current.json", seed[site])


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
