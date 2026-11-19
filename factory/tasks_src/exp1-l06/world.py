#!/usr/bin/env python3
"""World for the january-new-hire-records task (Greenhouse + DocuSign + Slack + BambooHR + local PDFs).

Writes into <out>/:
  seed/{greenhouse,docusign,slack,bamboohr}.json   initial state per site
  golden/{...}.json                                 state after a correct run
  golden_output/january_new_hires.csv               correct CLI deliverable
  input/offer_letters/*.pdf                         letters People Ops generated (agent-visible)
  expected.json                                     hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/}   self-check fixtures

The story: Rosa runs People Ops at Fernhill Labs. Before the holidays she has to set up the
January 2027 starters in BambooHR, close their applications out as Hired in Greenhouse and
tell the recruiter which Greenhouse offers don't match what was actually signed. Recruiter
chat, the Greenhouse offer form, the generated letter PDFs and the DocuSign envelopes all
disagree in places, and nothing says which source wins (lever L06):
  Priya   Greenhouse/Slack 165k, first envelope voided, revised letter (172k) completed
  Marcus  original letter Jan 4 completed, later amendment (Jan 19) completed
  Elena   Slack claims a bump to Senior PD / 128k; amendment sent but never signed
  Leo     Greenhouse/Slack/draft PDF say AE 95k; the completed envelope holds the SAE 105k letter
  Sam     hearsay in Slack says he may not show; nothing official, recruiter note confirms start
  Nadia   signed letter, listed in an old roundup, but withdrew (Greenhouse rejection + note)
  Owen    Greenhouse start Jan 25, signed letter Feb 1 -> not January
  Ines    Greenhouse offer with a January start but only "sent"; envelope unsigned
  Jordan  already created in BambooHR on Dec 10 (Slack note) -> no duplicate
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, long_pdf, product_image  # noqa: E402

CLOCK = "2026-12-14T09:30:00-08:00"
NOW_Z = "2026-12-14T17:30:00Z"
DOMAIN = "fernhill.io"
COMPANY = "Fernhill Labs, Inc."
ROSA_EMAIL = f"rosa.delgado@{DOMAIN}"
CSV_NAME = "january_new_hires.csv"
CSV_HEADER = ["name", "title", "start_date", "base_salary"]

# ---------------------------------------------------------------- people
# key: (first, last, greenhouse job title, department, location, recruiter-side "ATS" terms)
# ats = what the Greenhouse offer form says; signed = executed terms (truth).
HIRES = {
    "priya": dict(first="Priya", last="Raman", dept="Engineering", loc="San Francisco HQ",
                  ats=dict(title="Senior Data Engineer", start="2027-01-11", salary=165000),
                  signed=dict(title="Senior Data Engineer", start="2027-01-11", salary=172000)),
    "marcus": dict(first="Marcus", last="Lindqvist", dept="Product", loc="San Francisco HQ",
                   ats=dict(title="Product Manager", start="2027-01-04", salary=150000),
                   signed=dict(title="Product Manager", start="2027-01-19", salary=150000)),
    "elena": dict(first="Elena", last="Petrova", dept="Design", loc="Remote",
                  ats=dict(title="Product Designer", start="2027-01-11", salary=118000),
                  signed=dict(title="Product Designer", start="2027-01-11", salary=118000)),
    "leo": dict(first="Leo", last="Fischer", dept="Sales", loc="New York Office",
                ats=dict(title="Account Executive", start="2027-01-04", salary=95000),
                signed=dict(title="Senior Account Executive", start="2027-01-04", salary=105000)),
    "sam": dict(first="Sam", last="Ortiz", dept="Engineering", loc="Remote",
                ats=dict(title="Backend Engineer", start="2027-01-11", salary=140000),
                signed=dict(title="Backend Engineer", start="2027-01-11", salary=140000)),
    "hana": dict(first="Hana", last="Sato", dept="Engineering", loc="San Francisco HQ",
                 ats=dict(title="Site Reliability Engineer", start="2027-01-19", salary=155000),
                 signed=dict(title="Site Reliability Engineer", start="2027-01-19", salary=155000)),
    "jordan": dict(first="Jordan", last="Avery", dept="Customer Success", loc="New York Office",
                   ats=dict(title="Customer Success Manager", start="2027-01-04", salary=85000),
                   signed=dict(title="Customer Success Manager", start="2027-01-04", salary=85000)),
    "nadia": dict(first="Nadia", last="Haddad", dept="Finance", loc="San Francisco HQ",
                  ats=dict(title="Data Analyst", start="2027-01-04", salary=98000),
                  signed=dict(title="Data Analyst", start="2027-01-04", salary=98000)),
    "owen": dict(first="Owen", last="Brandt", dept="Sales", loc="San Francisco HQ",
                 ats=dict(title="Solutions Engineer", start="2027-01-25", salary=132000),
                 signed=dict(title="Solutions Engineer", start="2027-02-01", salary=132000)),
    "ines": dict(first="Ines", last="Carvalho", dept="Engineering", loc="Remote",
                 ats=dict(title="QA Engineer", start="2027-01-19", salary=125000),
                 signed=None),
}
NEW_IN_BAMBOO = ["priya", "marcus", "elena", "leo", "sam", "hana"]       # must be created
JANUARY = NEW_IN_BAMBOO + ["jordan"]                                      # CSV rows + Greenhouse Hired
NOT_HIRES = ["nadia", "owen", "ines"]                                     # must not be created
MISMATCH = {"priya": "salary", "marcus": "start_date", "leo": "title+salary", "owen": "start_date"}


def full(k):
    return f"{HIRES[k]['first']} {HIRES[k]['last']}"


def work_email(k):
    return f"{HIRES[k]['first'].lower()}.{HIRES[k]['last'].lower()}@{DOMAIN}"


def personal_email(k):
    return f"{HIRES[k]['first'].lower()}.{HIRES[k]['last'].lower()}@gmail.com"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def long_date(iso):
    import datetime as dt
    d = dt.date.fromisoformat(iso)
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


def money(n):
    return f"${n:,.0f}"


# ---------------------------------------------------------------- offer letter PDFs
# (filename, person key, kind, terms, letter date)
LETTERS = [
    ("Raman_Priya_Offer_Letter.pdf", "priya", "offer", dict(title="Senior Data Engineer", start="2027-01-11", salary=165000), "2026-11-24"),
    ("Raman_Priya_Offer_Letter_rev1.pdf", "priya", "offer", dict(title="Senior Data Engineer", start="2027-01-11", salary=172000), "2026-12-01"),
    ("Lindqvist_Marcus_Offer_Letter.pdf", "marcus", "offer", dict(title="Product Manager", start="2027-01-04", salary=150000), "2026-11-21"),
    ("Lindqvist_Marcus_Amendment_1.pdf", "marcus", "amend_start", dict(old="2027-01-04", new="2027-01-19", base="2026-11-21"), "2026-12-08"),
    ("Petrova_Elena_Offer_Letter.pdf", "elena", "offer", dict(title="Product Designer", start="2027-01-11", salary=118000), "2026-11-27"),
    ("Petrova_Elena_Amendment_1.pdf", "elena", "amend_comp", dict(title="Senior Product Designer", salary=128000, base="2026-11-27"), "2026-12-09"),
    ("Fischer_Leo_Offer_Letter.pdf", "leo", "offer", dict(title="Account Executive", start="2027-01-04", salary=95000), "2026-11-20"),
    ("Fischer_Leo_Offer_Letter_SAE.pdf", "leo", "offer", dict(title="Senior Account Executive", start="2027-01-04", salary=105000), "2026-11-25"),
    ("Ortiz_Sam_Offer_Letter.pdf", "sam", "offer", dict(title="Backend Engineer", start="2027-01-11", salary=140000), "2026-11-30"),
    ("Sato_Hana_Offer_Letter.pdf", "hana", "offer", dict(title="Site Reliability Engineer", start="2027-01-19", salary=155000), "2026-12-02"),
    ("Avery_Jordan_Offer_Letter.pdf", "jordan", "offer", dict(title="Customer Success Manager", start="2027-01-04", salary=85000), "2026-11-17"),
    ("Haddad_Nadia_Offer_Letter.pdf", "nadia", "offer", dict(title="Data Analyst", start="2027-01-04", salary=98000), "2026-11-18"),
    ("Brandt_Owen_Offer_Letter.pdf", "owen", "offer", dict(title="Solutions Engineer", start="2027-02-01", salary=132000), "2026-12-03"),
    ("Carvalho_Ines_Offer_Letter.pdf", "ines", "offer", dict(title="QA Engineer", start="2027-01-19", salary=125000), "2026-12-08"),
    ("Zhang_Wei_Offer_Letter.pdf", None, "offer_other", dict(name="Wei Zhang", title="Frontend Engineer", dept="Engineering",
                                                              loc="San Francisco HQ", start="2026-12-07", salary=148000), "2026-11-02"),
]
MANAGERS = {"Engineering": "Dev Okafor, Director of Engineering", "Product": "Nina Albright, Head of Product",
            "Design": "Carmen Ruiz, Head of Design", "Sales": "Grant Hollis, VP Sales",
            "Customer Success": "Mei Tanaka, Head of Customer Success", "Finance": "Paul Iverson, Controller"}


def letter_sections(key, kind, t, date):
    if kind == "offer_other":
        first, dept, loc = t["name"].split()[0], t["dept"], t["loc"]
    else:
        first, dept, loc = HIRES[key]["first"], HIRES[key]["dept"], HIRES[key]["loc"]
    if kind in ("offer", "offer_other"):
        return f"{COMPANY} - Offer of Employment", [
            ("", [f"Date: {long_date(date)}", f"Dear {first},",
                  f"On behalf of {COMPANY} (\"Fernhill\"), I am pleased to offer you employment on the terms below. "
                  "This letter, once signed by you and countersigned by Fernhill, sets out the terms of your employment."]),
            ("1. Position", [f"Title: {t['title']}", f"Department: {dept}", f"Reporting to: {MANAGERS[dept]}",
                             f"Work location: {loc}", "Employment type: Full-time, exempt"]),
            ("2. Start date", [f"Your first day of employment will be {long_date(t['start'])}."]),
            ("3. Compensation", [f"Base salary: {money(t['salary'])} per year, paid semi-monthly in accordance with "
                                 "Fernhill's normal payroll practices and subject to applicable withholdings.",
                                 "You will be eligible for Fernhill's standard benefits from your first day."]),
            ("4. Equity", ["Subject to Board approval, you will be granted an option under the Fernhill 2021 Equity "
                           "Incentive Plan. Details will follow in a separate grant notice."]),
            ("5. Conditions", ["This offer is contingent on satisfactory reference checks and proof of your eligibility "
                               "to work in the United States. Employment with Fernhill is at will."]),
            ("6. Acceptance", ["Please sign below to accept this offer.",
                               "For Fernhill Labs, Inc.: Alicia Moreno, VP People ______________________",
                               f"Accepted: {first if kind == 'offer_other' else full(key)} ______________________  Date: __________"]),
        ]
    if kind == "amend_start":
        return f"{COMPANY} - Amendment No. 1 to Offer Letter", [
            ("", [f"Date: {long_date(date)}", f"Dear {first},",
                  f"This amendment modifies the offer letter between you and {COMPANY} dated {long_date(t['base'])} "
                  "(the \"Offer Letter\")."]),
            ("1. Start date", [f"Section 2 of the Offer Letter is amended so that your first day of employment will be "
                               f"{long_date(t['new'])} instead of {long_date(t['old'])}."]),
            ("2. Other terms", ["All other terms of the Offer Letter, including title and base salary, remain unchanged."]),
            ("3. Acceptance", ["For Fernhill Labs, Inc.: Alicia Moreno, VP People ______________________",
                               f"Accepted: {full(key)} ______________________  Date: __________"]),
        ]
    return f"{COMPANY} - Amendment No. 1 to Offer Letter", [
        ("", [f"Date: {long_date(date)}", f"Dear {first},",
              f"This amendment modifies the offer letter between you and {COMPANY} dated {long_date(t['base'])} "
              "(the \"Offer Letter\")."]),
        ("1. Position", [f"Section 1 of the Offer Letter is amended so that your title will be {t['title']}."]),
        ("2. Compensation", [f"Section 3 of the Offer Letter is amended so that your base salary will be "
                             f"{money(t['salary'])} per year, effective on your first day of employment."]),
        ("3. Other terms", ["All other terms of the Offer Letter, including your start date, remain unchanged."]),
        ("4. Acceptance", ["For Fernhill Labs, Inc.: Alicia Moreno, VP People ______________________",
                           f"Accepted: {full(key)} ______________________  Date: __________"]),
    ]


def write_letters(folder: Path):
    from reportlab import rl_config
    rl_config.invariant = 1  # byte-stable PDFs across runs
    for name, key, kind, terms, date in LETTERS:
        title, sections = letter_sections(key, kind, terms, date)
        long_pdf(folder / name, title, sections)


# ---------------------------------------------------------------- greenhouse
GH_USERS = [
    ("user-1", "Rosa", "Delgado", "admin", "People Operations", "People Operations Manager"),
    ("user-2", "Theo", "Marsh", "recruiter", "People Operations", "Senior Recruiter"),
    ("user-3", "Dev", "Okafor", "hiring_manager", "Engineering", "Director of Engineering"),
    ("user-4", "Carmen", "Ruiz", "hiring_manager", "Design", "Head of Design"),
    ("user-5", "Nina", "Albright", "hiring_manager", "Product", "Head of Product"),
    ("user-6", "Grant", "Hollis", "hiring_manager", "Sales", "VP Sales"),
    ("user-7", "Jamie", "Cho", "coordinator", "People Operations", "Recruiting Coordinator"),
    ("user-8", "Alicia", "Moreno", "admin", "People Operations", "VP People"),
    ("user-9", "Mei", "Tanaka", "hiring_manager", "Customer Success", "Head of Customer Success"),
    ("user-10", "Paul", "Iverson", "hiring_manager", "Finance", "Controller"),
]
GH_DEPTS = [("dept-1", "Engineering"), ("dept-2", "Design"), ("dept-3", "Product"), ("dept-4", "Finance"),
            ("dept-5", "Sales"), ("dept-6", "Customer Success"), ("dept-7", "People Operations"), ("dept-8", "Marketing")]
GH_OFFICES = [("office-1", "San Francisco HQ", "San Francisco, CA"), ("office-2", "New York Office", "New York, NY"),
              ("office-3", "Remote - US", "Remote")]
DEPT_ID = {name: did for did, name in GH_DEPTS}
HM = {"Engineering": "user-3", "Design": "user-4", "Product": "user-5", "Sales": "user-6",
      "Customer Success": "user-9", "Finance": "user-10", "People Operations": "user-8", "Marketing": "user-8"}
# (job id, title, dept, office, openings, status, openDate)
GH_JOBS = [
    ("job-1", "Senior Data Engineer", "Engineering", "office-1", 1, "open", "2026-08-03"),
    ("job-2", "Product Manager", "Product", "office-1", 1, "open", "2026-08-17"),
    ("job-3", "Product Designer", "Design", "office-3", 1, "open", "2026-09-01"),
    ("job-4", "Account Executive", "Sales", "office-2", 3, "open", "2026-07-20"),
    ("job-5", "Backend Engineer", "Engineering", "office-3", 2, "open", "2026-08-10"),
    ("job-6", "Site Reliability Engineer", "Engineering", "office-1", 1, "open", "2026-09-14"),
    ("job-7", "Customer Success Manager", "Customer Success", "office-2", 1, "open", "2026-09-08"),
    ("job-8", "Data Analyst", "Finance", "office-1", 1, "open", "2026-09-21"),
    ("job-9", "Solutions Engineer", "Sales", "office-1", 1, "open", "2026-09-28"),
    ("job-10", "QA Engineer", "Engineering", "office-3", 1, "open", "2026-10-05"),
    ("job-11", "Frontend Engineer", "Engineering", "office-1", 2, "open", "2026-07-06"),
    ("job-12", "Marketing Manager", "Marketing", "office-1", 1, "open", "2026-10-12"),
]
JOB_OF = {"priya": "job-1", "marcus": "job-2", "elena": "job-3", "leo": "job-4", "sam": "job-5", "hana": "job-6",
          "jordan": "job-7", "nadia": "job-8", "owen": "job-9", "ines": "job-10"}
STAGES = ["Application Review", "Recruiter Phone Screen", "Hiring Manager Screen", "Technical Interview",
          "Take Home Test", "Onsite Interview", "Offer", "Hired"]
STAGE_TYPES = ["application_review", "phone_screen", "phone_screen", "interview", "take_home", "onsite", "offer", "hired"]
PREV = {"priya": ("Lyft", "Data Engineer", "Oakland, CA"), "marcus": ("Atlassian", "Product Manager", "San Francisco, CA"),
        "elena": ("Canva", "Product Designer", "Austin, TX"), "leo": ("HubSpot", "Account Executive", "Brooklyn, NY"),
        "sam": ("Ridgeway Systems", "Software Engineer", "Denver, CO"), "hana": ("Cloudflare", "SRE", "San Jose, CA"),
        "jordan": ("Zendesk", "Customer Success Lead", "Jersey City, NJ"), "nadia": ("Intuit", "Analyst", "Mountain View, CA"),
        "owen": ("Twilio", "Sales Engineer", "San Francisco, CA"), "ines": ("Shopify", "QA Analyst", "Portland, OR")}
OFFER_DATES = {"priya": "2026-11-24", "marcus": "2026-11-21", "elena": "2026-11-27", "leo": "2026-11-20",
               "sam": "2026-11-30", "hana": "2026-12-02", "jordan": "2026-11-17", "nadia": "2026-11-18",
               "owen": "2026-12-03", "ines": "2026-12-08"}
# Noise candidates: (first, last, job, stage index 1-8, status, company, title, location)
NOISE = [
    ("Wei", "Zhang", "job-11", 8, "hired", "Figma", "Frontend Engineer", "San Francisco, CA"),
    ("Tariq", "Bello", "job-4", 8, "hired", "Gong", "Account Executive", "New York, NY"),
    ("Chloe", "Martin", "job-11", 6, "active", "Airbnb", "Software Engineer", "San Francisco, CA"),
    ("Ravi", "Shankar", "job-11", 4, "active", "Square", "Frontend Engineer", "Oakland, CA"),
    ("Isabel", "Ferreira", "job-12", 3, "active", "Mailchimp", "Marketing Lead", "Atlanta, GA"),
    ("Ben", "Whitaker", "job-12", 2, "active", "Hootsuite", "Content Marketer", "Seattle, WA"),
    ("Aisha", "Khan", "job-4", 6, "active", "Salesforce", "Account Executive", "New York, NY"),
    ("Diego", "Navarro", "job-4", 3, "active", "Outreach", "SDR Manager", "Hoboken, NJ"),
    ("Lena", "Hoffmann", "job-4", 2, "rejected", "Gusto", "Account Manager", "Boston, MA"),
    ("Kenji", "Watanabe", "job-5", 5, "active", "Datadog", "Backend Engineer", "Remote"),
    ("Ruth", "Okonkwo", "job-5", 4, "active", "Plaid", "Software Engineer", "Remote"),
    ("Mateo", "Silva", "job-5", 2, "rejected", "Rappi", "Developer", "Miami, FL"),
    ("Grace", "Liu", "job-6", 3, "active", "PagerDuty", "SRE", "San Francisco, CA"),
    ("Omar", "Haddad", "job-8", 4, "active", "Brex", "Financial Analyst", "San Francisco, CA"),
    ("Sofia", "Romano", "job-3", 6, "rejected", "IDEO", "Designer", "Chicago, IL"),
    ("Hannah", "Sato", "job-10", 3, "active", "Etsy", "QA Engineer", "Brooklyn, NY"),
    ("Liam", "O'Connor", "job-9", 4, "active", "Segment", "Solutions Consultant", "San Francisco, CA"),
    ("Yara", "Mansour", "job-7", 5, "active", "Intercom", "CSM", "New York, NY"),
    ("Peter", "Novak", "job-2", 4, "active", "Asana", "Associate PM", "San Francisco, CA"),
    ("Zoe", "Adams", "job-1", 3, "active", "Snowflake", "Data Engineer", "Remote"),
    ("Kai", "Nakamura", "job-6", 7, "rejected", "Netflix", "Senior SRE", "Los Gatos, CA"),
    ("Fatima", "Diallo", "job-12", 1, "active", "Glossier", "Brand Manager", "New York, NY"),
    ("Arjun", "Mehta", "job-1", 1, "active", "Uber", "Analytics Engineer", "San Francisco, CA"),
    ("Clara", "Jensen", "job-3", 2, "active", "Spotify", "UX Designer", "Remote"),
]


def gh_ts(date, hour=17):
    return f"{date}T{hour:02d}:00:00Z"


def build_greenhouse():
    users = [{"id": uid, "firstName": f, "lastName": l, "name": f"{f} {l}", "email": f"{f.lower()}.{l.lower()}@{DOMAIN}",
              "role": role, "avatarUrl": avatar(f"{f} {l}"), "department": dept, "title": title}
             for uid, f, l, role, dept, title in GH_USERS]
    stages, jobs = [], []
    for jid, title, dept, office, openings, status, opened in GH_JOBS:
        js = [{"id": f"stage-{jid}-{i + 1}", "jobId": jid, "name": n, "orderIndex": i, "stageType": t}
              for i, (n, t) in enumerate(zip(STAGES, STAGE_TYPES))]
        stages += js
        jobs.append({"id": jid, "title": title, "status": status, "departmentId": DEPT_ID[dept], "officeId": office,
                     "hiringManagerId": HM[dept], "recruiterId": "user-2", "coordinatorId": "user-7", "openings": openings,
                     "openDate": opened, "closeDate": None,
                     "description": f"Fernhill Labs is hiring a {title} to join the {dept} team.",
                     "requirements": ["Relevant experience for the level", "Clear written communication", "Ownership mindset"],
                     "stages": [s["id"] for s in js], "candidateCount": 0,
                     "createdAt": gh_ts(opened, 16), "updatedAt": gh_ts(opened, 16)})
    cands, apps, offers, notes, acts = [], [], [], [], []
    n = 0
    for k in HIRES:
        n += 1
        h, (comp, ctitle, cloc) = HIRES[k], PREV[k]
        cid, aid, jid = f"cand-{n}", f"app-{n}", JOB_OF[k]
        od = OFFER_DATES[k]
        cands.append({"id": cid, "firstName": h["first"], "lastName": h["last"], "name": full(k), "email": personal_email(k),
                      "phone": f"(415) 555-01{n:02d}", "location": cloc, "currentCompany": comp, "currentTitle": ctitle,
                      "resumeUrl": "#", "linkedinUrl": "#", "source": "referral" if k in ("sam", "hana") else "applied",
                      "referrerId": None, "tags": [], "createdAt": gh_ts("2026-09-15"), "updatedAt": gh_ts(od)})
        rejected = k == "nadia"
        apps.append({"id": aid, "candidateId": cid, "jobId": jid, "currentStageId": f"stage-{jid}-7",
                     "status": "rejected" if rejected else "active", "appliedAt": gh_ts("2026-09-15"),
                     "rejectedAt": "2026-12-07T19:12:00Z" if rejected else None,
                     "rejectionReason": "Candidate withdrew" if rejected else None, "hiredAt": None,
                     "lastActivityAt": "2026-12-07T19:12:00Z" if rejected else gh_ts(od), "source": "applied",
                     "creditedTo": "user-2", "recruiterId": "user-2", "coordinatorId": "user-7",
                     "actionRequired": None, "daysInCurrentStage": 14})
        a = h["ats"]
        offers.append({"id": f"offer-{n}", "applicationId": aid, "jobId": jid, "candidateId": cid,
                       "status": "sent" if k == "ines" else "accepted", "salary": a["salary"], "equity": "Standard grant",
                       "signingBonus": 0, "currency": "USD", "startDate": f"{a['start']}T00:00:00", "expiresAt": gh_ts("2026-12-18", 8),
                       "createdBy": "user-2", "approvers": [{"userId": "user-8", "status": "approved", "respondedAt": gh_ts(od, 15)}],
                       "createdAt": gh_ts(od, 14), "updatedAt": gh_ts(od, 15)})
        acts.append({"id": f"act-{n}", "candidateId": cid, "applicationId": aid, "type": "stage_change", "actorId": "user-2",
                     "description": "Moved to Offer", "metadata": {"fromStage": "Onsite Interview", "toStage": "Offer"},
                     "createdAt": gh_ts(od, 13)})
    for f, l, jid, st, status, comp, ctitle, cloc in NOISE:
        n += 1
        cid, aid = f"cand-{n}", f"app-{n}"
        cands.append({"id": cid, "firstName": f, "lastName": l, "name": f"{f} {l}", "email": f"{f.lower()}.{l.lower().replace(chr(39), '')}@gmail.com",
                      "phone": f"(628) 555-02{n:02d}", "location": cloc, "currentCompany": comp, "currentTitle": ctitle,
                      "resumeUrl": "#", "linkedinUrl": "#", "source": "applied", "referrerId": None, "tags": [],
                      "createdAt": gh_ts("2026-10-01"), "updatedAt": gh_ts("2026-12-01")})
        apps.append({"id": aid, "candidateId": cid, "jobId": jid, "currentStageId": f"stage-{jid}-{st}", "status": status,
                     "appliedAt": gh_ts("2026-10-01"), "rejectedAt": gh_ts("2026-11-12") if status == "rejected" else None,
                     "rejectionReason": "Better qualified candidate" if status == "rejected" else None,
                     "hiredAt": gh_ts("2026-11-06") if status == "hired" else None, "lastActivityAt": gh_ts("2026-12-01"),
                     "source": "applied", "creditedTo": "user-2", "recruiterId": "user-2", "coordinatorId": "user-7",
                     "actionRequired": "needs_scorecard" if st in (4, 6) and status == "active" else None,
                     "daysInCurrentStage": 6})
        if status == "hired":
            offers.append({"id": f"offer-{n}", "applicationId": aid, "jobId": jid, "candidateId": cid, "status": "accepted",
                           "salary": 148000 if f == "Wei" else 92000, "equity": "Standard grant", "signingBonus": 0,
                           "currency": "USD", "startDate": "2026-12-07T00:00:00", "expiresAt": gh_ts("2026-11-09", 8),
                           "createdBy": "user-2", "approvers": [{"userId": "user-8", "status": "approved", "respondedAt": gh_ts("2026-11-02")}],
                           "createdAt": gh_ts("2026-11-02", 14), "updatedAt": gh_ts("2026-11-05")})
    cid_of = {k: f"cand-{i + 1}" for i, k in enumerate(HIRES)}
    notes = [
        {"id": "note-1", "candidateId": cid_of["nadia"], "authorId": "user-2",
         "body": "Nadia emailed this morning to withdraw - she accepted a counteroffer from Intuit. Offer is void, closing her out. "
                 "Confirmed by email, copy saved to her file.",
         "visibility": "public", "isPinned": True, "createdAt": "2026-12-07T19:10:00Z", "updatedAt": "2026-12-07T19:10:00Z"},
        {"id": "note-2", "candidateId": cid_of["sam"], "authorId": "user-2",
         "body": "Spoke with Sam today. He confirmed his laptop shipping address and is all set for his Jan 11 start.",
         "visibility": "public", "isPinned": False, "createdAt": "2026-12-12T00:40:00Z", "updatedAt": "2026-12-12T00:40:00Z"},
        {"id": "note-3", "candidateId": cid_of["priya"], "authorId": "user-3",
         "body": "Strong pipeline design background, great onsite. Excited to have her on the platform team.",
         "visibility": "public", "isPinned": False, "createdAt": "2026-11-19T22:00:00Z", "updatedAt": "2026-11-19T22:00:00Z"},
        {"id": "note-4", "candidateId": cid_of["leo"], "authorId": "user-6",
         "body": "Panel loved his enterprise deal stories. Strong closer.",
         "visibility": "public", "isPinned": False, "createdAt": "2026-11-18T21:00:00Z", "updatedAt": "2026-11-18T21:00:00Z"},
        {"id": "note-5", "candidateId": "cand-13", "authorId": "user-3",
         "body": "Good onsite, waiting on the last scorecard before we decide.",
         "visibility": "public", "isPinned": False, "createdAt": "2026-12-09T20:00:00Z", "updatedAt": "2026-12-09T20:00:00Z"},
    ]
    acts.append({"id": f"act-{n + 1}", "candidateId": cid_of["nadia"], "applicationId": "app-8", "type": "rejected",
                 "actorId": "user-2", "description": "Rejected: Candidate withdrew", "metadata": {}, "createdAt": "2026-12-07T19:12:00Z"})
    for j in jobs:
        j["candidateCount"] = sum(1 for a in apps if a["jobId"] == j["id"])
    interviews = [
        {"id": "int-1", "applicationId": "app-13", "stageId": "stage-job-11-6", "interviewerIds": ["user-3"],
         "scheduledAt": "2026-12-15T18:00:00Z", "duration": 60, "location": "Video Call", "status": "scheduled",
         "meetingUrl": None, "notes": "Final onsite loop"},
        {"id": "int-2", "applicationId": "app-17", "stageId": "stage-job-4-6", "interviewerIds": ["user-6"],
         "scheduledAt": "2026-12-16T17:00:00Z", "duration": 45, "location": "Video Call", "status": "scheduled",
         "meetingUrl": None, "notes": "Sales role play"},
    ]
    notifications = [
        {"id": "notif-1", "type": "offer_accepted", "title": "Offer accepted: Hana Sato", "message": "Hana Sato accepted the Site Reliability Engineer offer",
         "isRead": True, "link": f"/candidates/{cid_of['hana']}", "createdAt": "2026-12-04T19:00:00Z"},
        {"id": "notif-2", "type": "application_rejected", "title": "Nadia Haddad withdrew", "message": "Theo Marsh rejected Nadia Haddad (Candidate withdrew)",
         "isRead": False, "link": f"/candidates/{cid_of['nadia']}", "createdAt": "2026-12-07T19:12:00Z"},
        {"id": "notif-3", "type": "scorecard_due", "title": "Scorecard due: Chloe Martin", "message": "Onsite scorecard for Chloe Martin is due",
         "isRead": False, "link": "/candidates/cand-13", "createdAt": "2026-12-10T16:00:00Z"},
    ]
    rosa = users[0]
    return {
        "currentUser": rosa, "users": users,
        "departments": [{"id": d, "name": nm, "parentId": None} for d, nm in GH_DEPTS],
        "offices": [{"id": o, "name": nm, "location": loc} for o, nm, loc in GH_OFFICES],
        "jobs": jobs, "jobStages": stages, "candidates": cands, "applications": apps, "scorecards": [],
        "interviews": interviews, "offers": offers, "notes": notes, "activityFeed": acts, "notifications": notifications,
        "sources": [{"id": "src-1", "name": "Applied"}, {"id": "src-2", "name": "Referral"}, {"id": "src-3", "name": "LinkedIn"},
                    {"id": "src-4", "name": "Agency"}],
        "rejectionReasons": [{"id": "rr-1", "name": "Lacking technical skills"}, {"id": "rr-2", "name": "Lacking culture fit"},
                             {"id": "rr-3", "name": "Position filled"}, {"id": "rr-4", "name": "Candidate withdrew"},
                             {"id": "rr-7", "name": "Better qualified candidate"}, {"id": "rr-8", "name": "Compensation mismatch"}],
        "ui": {"searchQuery": "", "activeJobId": None, "activeCandidateId": None,
               "modals": {"addCandidate": False, "createJob": False, "scheduleInterview": False, "rejectCandidate": False,
                          "moveStage": False, "search": False, "notifications": False}},
    }


def gh_app_id(k):
    return f"app-{list(HIRES).index(k) + 1}"


def gh_move_hired(gh, k, ts=NOW_Z, n=0):
    """Same mutation as MoveStageModal: MOVE_APPLICATION_STAGE + ADD_ACTIVITY."""
    aid = gh_app_id(k)
    app = next(a for a in gh["applications"] if a["id"] == aid)
    app.update(currentStageId=f"stage-{app['jobId']}-8", daysInCurrentStage=0, lastActivityAt=ts, actionRequired=None)
    gh["activityFeed"].insert(0, {"id": f"golden-act-{k}", "candidateId": app["candidateId"], "applicationId": aid,
                               "type": "stage_change", "actorId": "user-1", "description": "Moved to Hired",
                               "metadata": {"fromStage": "Offer", "toStage": "Hired"}, "createdAt": ts})


# ---------------------------------------------------------------- docusign
ALICIA = ("Alicia Moreno", f"alicia.moreno@{DOMAIN}")


def ds_envelope(eid, subject, docs, signer, status, created, sent=None, completed=None, voided=None,
                void_reason=None, viewed=None, folder="folder_offers", message=None, countersign=True):
    """docs = [(name, pages)], signer = (name, email)."""
    name, email = signer
    hist = [{"id": f"evt_{eid}_1", "timestamp": created, "action": "created", "actorName": "Rosa Delgado",
             "actorEmail": ROSA_EMAIL, "details": "Envelope created"}]
    signed = status == "completed"
    recips = [{"id": f"rec_{eid}_1", "name": name, "email": email, "role": "signer", "routingOrder": 1,
               "status": "completed" if signed else ("delivered" if status in ("sent", "delivered") else ("created" if status == "draft" else "delivered")),
               "signedAt": completed if signed else None, "viewedAt": viewed or (completed if signed else None),
               "deliveredAt": sent, "declinedAt": None, "declineReason": None}]
    if countersign:
        recips.append({"id": f"rec_{eid}_2", "name": ALICIA[0], "email": ALICIA[1], "role": "signer", "routingOrder": 2,
                       "status": "completed" if signed else "created", "signedAt": completed if signed else None,
                       "viewedAt": completed if signed else None, "deliveredAt": completed if signed else None,
                       "declinedAt": None, "declineReason": None})
    if sent:
        hist.append({"id": f"evt_{eid}_2", "timestamp": sent, "action": "sent", "actorName": "Rosa Delgado",
                     "actorEmail": ROSA_EMAIL, "details": f"Envelope sent to {len(recips)} recipient{'s' if len(recips) > 1 else ''}"})
        hist.append({"id": f"evt_{eid}_3", "timestamp": sent, "action": "delivered", "actorName": name, "actorEmail": email,
                     "details": f"Envelope delivered to {name}"})
    if viewed:
        hist.append({"id": f"evt_{eid}_4", "timestamp": viewed, "action": "viewed", "actorName": name, "actorEmail": email,
                     "details": f"{name} viewed the document"})
    if signed:
        hist.append({"id": f"evt_{eid}_5", "timestamp": completed, "action": "signed", "actorName": name, "actorEmail": email,
                     "details": f"{name} signed the document"})
        if countersign:
            hist.append({"id": f"evt_{eid}_6", "timestamp": completed, "action": "signed", "actorName": ALICIA[0],
                         "actorEmail": ALICIA[1], "details": f"{ALICIA[0]} signed the document"})
        hist.append({"id": f"evt_{eid}_7", "timestamp": completed, "action": "completed", "actorName": "System",
                     "actorEmail": "", "details": "Envelope completed - all recipients signed"})
    if voided:
        hist.append({"id": f"evt_{eid}_8", "timestamp": voided, "action": "voided", "actorName": "Rosa Delgado",
                     "actorEmail": ROSA_EMAIL, "details": f"Envelope voided: {void_reason}"})
    last = voided or completed or viewed or sent or created
    return {"id": eid, "subject": subject, "message": message or f"Hi {name.split()[0]}, please review and sign. Thank you!",
            "status": status, "createdAt": created, "sentAt": sent, "completedAt": completed, "voidedAt": voided,
            "declinedAt": None, "lastActivityAt": last, "expiresAt": None if status in ("completed", "voided") else "2027-01-08T08:00:00Z",
            "senderId": "user_1", "folderId": folder, "templateId": "tmpl_offer" if "Offer" in subject else None,
            "reminderEnabled": status in ("sent", "delivered"), "reminderDays": 3, "reminderFrequency": 2,
            "documents": [{"id": f"doc_{eid}_{i + 1}", "name": d, "pageCount": p, "order": i + 1,
                           "fileUrl": product_image(d.replace("_", " ").replace(".pdf", "")), "fileType": "pdf"}
                          for i, (d, p) in enumerate(docs)],
            "recipients": recips, "fields": [], "history": hist}


def build_docusign():
    P = lambda k: (full(k), personal_email(k))  # noqa: E731
    env = [
        ds_envelope("env_201", "Offer Letter - Priya Raman", [("Raman_Priya_Offer_Letter.pdf", 2)], P("priya"), "voided",
                    "2026-11-24T18:00:00Z", sent="2026-11-24T18:05:00Z", viewed="2026-11-25T02:10:00Z",
                    voided="2026-12-01T17:20:00Z", void_reason="Replaced by revised offer letter"),
        ds_envelope("env_202", "Offer Letter - Priya Raman", [("Raman_Priya_Offer_Letter_rev1.pdf", 2)], P("priya"), "completed",
                    "2026-12-01T17:30:00Z", sent="2026-12-01T17:32:00Z", viewed="2026-12-02T16:00:00Z", completed="2026-12-03T18:41:00Z"),
        ds_envelope("env_203", "Offer Letter - Marcus Lindqvist", [("Lindqvist_Marcus_Offer_Letter.pdf", 2)], P("marcus"), "completed",
                    "2026-11-21T19:00:00Z", sent="2026-11-21T19:02:00Z", viewed="2026-11-22T17:00:00Z", completed="2026-11-24T20:15:00Z"),
        ds_envelope("env_204", "Offer Letter Amendment - Marcus Lindqvist", [("Lindqvist_Marcus_Amendment_1.pdf", 1)], P("marcus"),
                    "completed", "2026-12-08T18:00:00Z", sent="2026-12-08T18:03:00Z", viewed="2026-12-09T15:30:00Z",
                    completed="2026-12-10T16:52:00Z"),
        ds_envelope("env_205", "Offer Letter - Elena Petrova", [("Petrova_Elena_Offer_Letter.pdf", 2)], P("elena"), "completed",
                    "2026-11-27T17:00:00Z", sent="2026-11-27T17:04:00Z", viewed="2026-11-28T19:00:00Z", completed="2026-11-30T21:08:00Z"),
        ds_envelope("env_206", "Offer Letter Amendment - Elena Petrova", [("Petrova_Elena_Amendment_1.pdf", 1)], P("elena"),
                    "delivered", "2026-12-09T22:00:00Z", sent="2026-12-09T22:04:00Z", viewed="2026-12-10T17:45:00Z"),
        ds_envelope("env_207", "Offer Letter - Leo Fischer", [("Fischer_Leo_Offer_Letter_SAE.pdf", 2)], P("leo"), "completed",
                    "2026-11-25T16:00:00Z", sent="2026-11-25T16:02:00Z", viewed="2026-11-25T20:00:00Z", completed="2026-11-27T17:30:00Z"),
        ds_envelope("env_208", "Offer Letter - Sam Ortiz", [("Ortiz_Sam_Offer_Letter.pdf", 2)], P("sam"), "completed",
                    "2026-11-30T18:00:00Z", sent="2026-11-30T18:01:00Z", viewed="2026-12-01T03:00:00Z", completed="2026-12-02T01:20:00Z"),
        ds_envelope("env_209", "Offer Letter - Hana Sato", [("Sato_Hana_Offer_Letter.pdf", 2)], P("hana"), "completed",
                    "2026-12-02T18:00:00Z", sent="2026-12-02T18:02:00Z", viewed="2026-12-03T17:00:00Z", completed="2026-12-04T18:55:00Z"),
        ds_envelope("env_210", "Offer Letter - Jordan Avery", [("Avery_Jordan_Offer_Letter.pdf", 2)], P("jordan"), "completed",
                    "2026-11-17T17:00:00Z", sent="2026-11-17T17:03:00Z", viewed="2026-11-18T14:00:00Z", completed="2026-11-19T16:10:00Z"),
        ds_envelope("env_211", "Offer Letter - Nadia Haddad", [("Haddad_Nadia_Offer_Letter.pdf", 2)], P("nadia"), "completed",
                    "2026-11-18T18:00:00Z", sent="2026-11-18T18:02:00Z", viewed="2026-11-19T16:00:00Z", completed="2026-11-20T19:30:00Z"),
        ds_envelope("env_212", "Offer Letter - Owen Brandt", [("Brandt_Owen_Offer_Letter.pdf", 2)], P("owen"), "completed",
                    "2026-12-03T18:00:00Z", sent="2026-12-03T18:02:00Z", viewed="2026-12-04T16:00:00Z", completed="2026-12-05T00:45:00Z"),
        ds_envelope("env_213", "Offer Letter - Ines Carvalho", [("Carvalho_Ines_Offer_Letter.pdf", 2)], P("ines"), "delivered",
                    "2026-12-08T19:00:00Z", sent="2026-12-08T19:03:00Z", viewed="2026-12-09T18:20:00Z"),
        ds_envelope("env_214", "Offer Letter - Wei Zhang", [("Zhang_Wei_Offer_Letter.pdf", 2)], ("Wei Zhang", "wei.zhang@gmail.com"),
                    "completed", "2026-11-02T18:00:00Z", sent="2026-11-02T18:02:00Z", viewed="2026-11-03T16:00:00Z",
                    completed="2026-11-05T17:00:00Z"),
        ds_envelope("env_215", "Offer Letter - Tariq Bello", [("Bello_Tariq_Offer_Letter.pdf", 2)], ("Tariq Bello", "tariq.bello@gmail.com"),
                    "completed", "2026-11-03T18:00:00Z", sent="2026-11-03T18:02:00Z", viewed="2026-11-04T16:00:00Z",
                    completed="2026-11-05T22:00:00Z"),
        ds_envelope("env_216", "Offer Letter - Kai Nakamura", [("Nakamura_Kai_Offer_Letter.pdf", 2)], ("Kai Nakamura", "kai.nakamura@gmail.com"),
                    "voided", "2026-11-10T18:00:00Z", sent="2026-11-10T18:02:00Z", viewed="2026-11-11T16:00:00Z",
                    voided="2026-11-13T19:00:00Z", void_reason="Candidate declined offer"),
        ds_envelope("env_217", "Mutual NDA - Lattice Analytics", [("Fernhill_Mutual_NDA.pdf", 3)], ("Jon Pratt", "jon@latticeanalytics.com"),
                    "completed", "2026-10-14T17:00:00Z", sent="2026-10-14T17:01:00Z", completed="2026-10-15T20:00:00Z",
                    folder="folder_vendors", countersign=False),
        ds_envelope("env_218", "Benefits Broker Agreement 2027", [("Harbor_Benefits_Agreement_2027.pdf", 6)],
                    ("Lisa Moon", "lisa.moon@harborbenefits.com"), "delivered", "2026-12-09T18:00:00Z",
                    sent="2026-12-09T18:05:00Z", viewed="2026-12-11T17:00:00Z", folder="folder_vendors", countersign=False),
        ds_envelope("env_219", "Contractor Agreement - Bright Pixel Studio", [("BrightPixel_SOW_Q1.pdf", 4)],
                    ("Ama Owusu", "ama@brightpixel.studio"), "draft", "2026-12-11T21:00:00Z", folder="folder_vendors", countersign=False),
        ds_envelope("env_220", "Offer Letter - Marcus Lindqvist", [("Lindqvist_Marcus_Offer_Letter.pdf", 2)], P("marcus"), "draft",
                    "2026-11-21T18:40:00Z", folder=None, message="(duplicate draft - do not send)"),
        ds_envelope("env_221", "Remote Work Stipend Acknowledgement - Q4", [("Remote_Stipend_Ack.pdf", 1)],
                    ("Mei Tanaka", f"mei.tanaka@{DOMAIN}"), "completed", "2026-10-01T16:00:00Z", sent="2026-10-01T16:01:00Z",
                    completed="2026-10-02T17:00:00Z", folder=None, countersign=False),
    ]
    audit = []
    for i, e in enumerate(sorted(env, key=lambda e: e["createdAt"])):
        audit.append({"id": f"audit_{i + 1}", "timestamp": e["createdAt"], "action": "CREATE_ENVELOPE",
                      "details": f"Created envelope: {e['subject']}", "envelopeId": e["id"]})
    return {
        "user": {"id": "user_1", "name": "Rosa Delgado", "email": ROSA_EMAIL, "title": "People Operations Manager",
                 "company": COMPANY, "avatar": avatar("Rosa Delgado"), "memberSince": "2023-02-06",
                 "settings": {"defaultReminderDays": 3, "defaultExpirationDays": 30, "timezone": "America/Los_Angeles"}},
        "envelopes": env,
        "templates": [{"id": "tmpl_offer", "name": "Fernhill Offer Letter", "description": "Offer letter with candidate + VP People signature",
                       "createdAt": "2024-03-01T12:00:00Z", "lastUsedAt": "2026-12-08T19:00:00Z", "usageCount": 41,
                       "ownerId": "user_1", "shared": True,
                       "documents": [{"id": "tdoc_offer_1", "name": "Fernhill_Offer_Letter_Template.pdf", "pageCount": 2, "order": 1,
                                      "fileUrl": product_image("Fernhill Offer Letter Template"), "fileType": "pdf"}],
                       "roles": [{"id": "role_offer_1", "name": "Candidate", "role": "signer", "routingOrder": 1},
                                 {"id": "role_offer_2", "name": "VP People", "role": "signer", "routingOrder": 2}],
                       "fields": []}],
        "folders": [{"id": "folder_offers", "name": "Offer Letters 2026", "parentFolder": None, "createdAt": "2026-01-05T17:00:00Z"},
                    {"id": "folder_vendors", "name": "Vendor Agreements", "parentFolder": None, "createdAt": "2025-03-10T17:00:00Z"}],
        "contacts": [{"id": f"contact_{i + 1}", "name": nm, "email": em, "company": co, "title": ti} for i, (nm, em, co, ti) in enumerate([
            (ALICIA[0], ALICIA[1], COMPANY, "VP People"), ("Theo Marsh", f"theo.marsh@{DOMAIN}", COMPANY, "Senior Recruiter"),
            ("Lisa Moon", "lisa.moon@harborbenefits.com", "Harbor Benefits", "Account Manager"),
            ("Jon Pratt", "jon@latticeanalytics.com", "Lattice Analytics", "COO")])],
        "auditLog": audit,
    }


# ---------------------------------------------------------------- slack
SLACK_USERS = [
    ("U01", "Rosa Delgado", "rosa", "People Operations Manager"),
    ("U02", "Theo Marsh", "theo", "Senior Recruiter"),
    ("U03", "Dev Okafor", "dev", "Director of Engineering"),
    ("U04", "Alicia Moreno", "alicia", "VP People"),
    ("U05", "Jamie Cho", "jamie", "Recruiting Coordinator"),
    ("U06", "Marco Bianchi", "marco", "IT Lead"),
    ("U07", "Grant Hollis", "grant", "VP Sales"),
    ("U08", "Carmen Ruiz", "carmen", "Head of Design"),
]


def slack_msg(mid, sender, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": sender, "content": text, "timestamp": ts, "threadId": thread,
            "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack():
    users = [{"userId": uid, "fullName": fn, "displayName": dn, "email": f"{fn.split()[0].lower()}.{fn.split()[1].lower()}@{DOMAIN}",
              "avatar": avatar(fn), "title": t, "status": "online" if uid in ("U01", "U02") else "away",
              "statusMessage": "", "statusEmoji": "", "timeZone": "America/Los_Angeles"} for uid, fn, dn, t in SLACK_USERS]
    everyone = [u[0] for u in SLACK_USERS]

    def channel(cid, desc, members=None):
        return {"channelId": cid, "name": cid, "description": desc, "topic": desc, "isPrivate": False,
                "isStarred": cid == "people-ops", "members": members or everyone, "createdBy": "U04",
                "createdAt": "2024-02-01T17:00:00Z", "pinnedMessages": [], "unreadCount": 0}

    tada = lambda *u: [{"emoji": "tada", "users": list(u), "count": len(u)}]  # noqa: E731
    recruiting = [
        slack_msg("m_r01", "U02", "2026-11-06T18:10:00Z", "Wei Zhang (Frontend) and Tariq Bello (AE) both signed, Dec 7 starts.", reactions=tada("U01", "U03")),
        slack_msg("m_r02", "U02", "2026-11-19T17:30:00Z", "Jordan Avery signed for CSM, starting Jan 4.", reactions=tada("U01")),
        slack_msg("m_r03", "U02", "2026-11-23T18:00:00Z",
                  "January cohort so far: Priya Raman (Sr Data Engineer, Jan 11), Marcus Lindqvist (PM, Jan 4), "
                  "Leo Fischer (AE, Jan 4), Nadia Haddad (Data Analyst, Jan 4), Jordan Avery (CSM, Jan 4). More coming."),
        slack_msg("m_r04", "U02", "2026-11-24T18:20:00Z", "Priya's offer is out, $165k base. Fingers crossed."),
        slack_msg("m_r05", "U02", "2026-11-24T20:30:00Z", "Marcus signed! Starting Jan 4.", reactions=tada("U01", "U05")),
        slack_msg("m_r06", "U02", "2026-11-27T18:00:00Z", "Leo's in for the AE role, signed this morning.", reactions=tada("U07")),
        slack_msg("m_r07", "U07", "2026-11-27T18:05:00Z", "Huge. Welcome Leo."),
        slack_msg("m_r08", "U02", "2026-11-30T21:20:00Z", "Elena Petrova signed for Product Designer, Jan 11.", reactions=tada("U08")),
        slack_msg("m_r09", "U02", "2026-12-02T01:30:00Z", "Sam Ortiz signed, Backend, Jan 11."),
        slack_msg("m_r10", "U02", "2026-12-03T19:00:00Z", "Priya signed!", reactions=tada("U01", "U03")),
        slack_msg("m_r11", "U02", "2026-12-04T19:10:00Z", "Hana Sato signed for SRE, Jan 19."),
        slack_msg("m_r12", "U02", "2026-12-05T01:00:00Z", "Owen Brandt signed for Solutions Engineer, he starts end of January."),
        slack_msg("m_r13", "U02", "2026-12-08T17:40:00Z",
                  "Heads up, Marcus asked to push his start, he has to work out a notice period. Sending him an amendment today."),
        slack_msg("m_r14", "U02", "2026-12-08T19:10:00Z", "Ines Carvalho has her QA offer, expecting an answer by Friday."),
        slack_msg("m_r15", "U02", "2026-12-10T00:15:00Z",
                  "Elena's bump to Senior Product Designer at $128k is done, Alicia approved it. Amendment went out."),
        slack_msg("m_r16", "U08", "2026-12-10T00:20:00Z", "Amazing, thank you Theo!"),
        slack_msg("m_r17", "U03", "2026-12-11T22:05:00Z",
                  "Random, but a friend at Ridgeway says Sam Ortiz is taking a counteroffer and won't show. "
                  "I'd hold off on setting him up."),
    ]
    people_ops = [
        slack_msg("m_p01", "U04", "2026-12-01T17:00:00Z", "Reminder: all January starters need to be in Bamboo by Dec 18 so payroll and IT can prep."),
        slack_msg("m_p02", "U01", "2026-12-10T18:30:00Z",
                  "Created Jordan Avery in Bamboo already so IT can ship her laptop early. The rest of the January group I'll do next week."),
        slack_msg("m_p03", "U06", "2026-12-10T18:45:00Z", "Thanks, laptop for Jordan ordered."),
        slack_msg("m_p04", "U02", "2026-12-11T23:30:00Z",
                  "Rosa, when you do the January setups, can you reply here with any January offers where what's in Greenhouse "
                  "doesn't match what was actually signed (title, salary or start date) and what the signed version says? "
                  "I'll fix the offer records after."),
        slack_msg("m_p05", "U05", "2026-12-12T00:10:00Z", "Background checks for the January group are all clear, FYI."),
    ]
    it = [
        slack_msg("m_i01", "U06", "2026-12-02T18:00:00Z", "Laptop order cutoff for January starters is Dec 18. I pull the list from Bamboo."),
        slack_msg("m_i02", "U06", "2026-12-09T17:20:00Z", "Remote starters: shipping labels need a home address, I'll ask People Ops for those."),
    ]
    general = [
        slack_msg("m_g01", "U04", "2026-12-07T17:00:00Z", "Holiday party is Dec 17 at the SF office, remote folks get a DoorDash credit."),
        slack_msg("m_g02", "U03", "2026-12-09T20:00:00Z", "Platform migration is done, thanks everyone who stayed late."),
    ]
    return {
        "currentUser": users[0],
        "workspace": {"workspaceId": "ws_fernhill", "workspaceName": "Fernhill Labs", "icon": avatar("Fernhill Labs")},
        "users": users,
        "channels": [channel("general", "Company-wide"), channel("people-ops", "People Ops requests and onboarding"),
                     channel("recruiting", "Offers, closes and hiring updates"), channel("it-onboarding", "Laptops and accounts for new hires")],
        "messages": {"general": general, "people-ops": people_ops, "recruiting": recruiting, "it-onboarding": it},
        "threads": {}, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


THREAD_PARENT = "m_p04"
GOLDEN_REPLY = (
    "January offers where Greenhouse doesn't match what was signed:\n"
    "Priya Raman - Greenhouse has $165,000; the revised letter she signed Dec 3 says $172,000 base (the first envelope was voided).\n"
    "Marcus Lindqvist - Greenhouse has a Jan 4 start; his signed amendment moves it to 2027-01-19.\n"
    "Leo Fischer - Greenhouse has Account Executive at $95,000; the signed letter is Senior Account Executive at $105,000.\n"
    "Owen Brandt - Greenhouse has Jan 25; the signed letter says February 1, 2027, so he's not part of January."
)


def slack_reply(slack, text, ts="2026-12-14T19:05:00Z", mid="msg_golden_reply", in_thread=True):
    """Same shape as AppContext createThread + addMessage."""
    if in_thread:
        tid = "thread_golden"
        slack["threads"][tid] = {"threadId": tid, "parentMessageId": THREAD_PARENT, "channelId": "people-ops", "dmId": None,
                                 "replies": [mid], "followers": ["U01"]}
    else:
        tid = None
    slack["messages"]["people-ops"].append(slack_msg(mid, "U01", ts, text, thread=tid))


# ---------------------------------------------------------------- bamboohr
BH_DEPTS = [(1, "People Operations", 3), (2, "Engineering", 6), (3, "Product", 9), (4, "Design", 11), (5, "Sales", 13),
            (6, "Customer Success", 16), (7, "Marketing", 19), (8, "Finance", 21), (9, "Leadership", 1)]
BH_DEPT_ID = {n: i for i, n, _ in BH_DEPTS}
BH_LOCS = [(1, "San Francisco HQ", "500 Howard St, San Francisco, CA 94105", "America/Los_Angeles"),
           (2, "New York Office", "85 Broad St, New York, NY 10004", "America/New_York"),
           (3, "Remote", "", "")]
BH_LOC_ID = {n: i for i, n, _, _ in BH_LOCS}
# (id, first, last, title, dept, loc, hire, pay, reportsTo)
BH_STAFF = [
    (1, "Hugo", "Lindgren", "Chief Executive Officer", "Leadership", "San Francisco HQ", "2019-03-04", 240000, None),
    (2, "Alicia", "Moreno", "VP People", "People Operations", "San Francisco HQ", "2020-06-15", 185000, 1),
    (3, "Rosa", "Delgado", "People Operations Manager", "People Operations", "San Francisco HQ", "2023-02-06", 118000, 2),
    (4, "Theo", "Marsh", "Senior Recruiter", "People Operations", "New York Office", "2022-09-12", 105000, 2),
    (5, "Jamie", "Cho", "Recruiting Coordinator", "People Operations", "San Francisco HQ", "2024-04-01", 72000, 4),
    (6, "Dev", "Okafor", "Director of Engineering", "Engineering", "San Francisco HQ", "2020-01-13", 215000, 1),
    (7, "Marco", "Bianchi", "IT Lead", "Engineering", "San Francisco HQ", "2021-05-03", 128000, 6),
    (8, "Sana", "Iqbal", "Staff Software Engineer", "Engineering", "Remote", "2020-11-02", 205000, 6),
    (9, "Nina", "Albright", "Head of Product", "Product", "San Francisco HQ", "2021-02-22", 198000, 1),
    (10, "Tom", "Becker", "Product Manager", "Product", "San Francisco HQ", "2023-07-10", 145000, 9),
    (11, "Carmen", "Ruiz", "Head of Design", "Design", "Remote", "2021-08-16", 176000, 1),
    (12, "Ivy", "Chen", "Product Designer", "Design", "San Francisco HQ", "2024-01-08", 112000, 11),
    (13, "Grant", "Hollis", "VP Sales", "Sales", "New York Office", "2020-04-20", 190000, 1),
    (14, "Priya", "Ramanathan", "Data Engineer", "Engineering", "San Francisco HQ", "2024-03-18", 152000, 6),
    (15, "Sean", "Murphy", "Account Executive", "Sales", "New York Office", "2023-10-02", 92000, 13),
    (16, "Mei", "Tanaka", "Head of Customer Success", "Customer Success", "New York Office", "2021-06-07", 150000, 1),
    (17, "Rachel", "Green", "Customer Success Manager", "Customer Success", "New York Office", "2024-05-13", 84000, 16),
    (18, "Luis", "Ortega", "Senior Account Executive", "Sales", "New York Office", "2022-03-07", 110000, 13),
    (19, "Megan", "Price", "Head of Marketing", "Marketing", "San Francisco HQ", "2022-01-10", 165000, 1),
    (20, "Andre", "Dubois", "Content Marketing Manager", "Marketing", "Remote", "2024-08-05", 98000, 19),
    (21, "Paul", "Iverson", "Controller", "Finance", "San Francisco HQ", "2021-09-13", 168000, 1),
    (22, "Elena", "Petrakis", "Accountant", "Finance", "San Francisco HQ", "2023-04-03", 88000, 21),
    (23, "Noah", "Kim", "Backend Engineer", "Engineering", "Remote", "2022-06-20", 142000, 6),
    (24, "Olivia", "Brooks", "Senior Backend Engineer", "Engineering", "San Francisco HQ", "2021-10-11", 172000, 6),
    (25, "Ethan", "Ward", "Site Reliability Engineer", "Engineering", "San Francisco HQ", "2023-01-17", 158000, 6),
    (26, "Maya", "Patel", "Data Analyst", "Finance", "San Francisco HQ", "2024-09-09", 96000, 21),
    (27, "Lucas", "Moreau", "Frontend Engineer", "Engineering", "San Francisco HQ", "2025-02-03", 140000, 6),
    (28, "Ava", "Johnson", "Sales Development Rep", "Sales", "New York Office", "2025-06-16", 68000, 13),
    (29, "Daniel", "Osei", "QA Engineer", "Engineering", "Remote", "2025-04-07", 118000, 6),
    (30, "Lily", "Zhou", "Senior Product Designer", "Design", "Remote", "2022-11-14", 135000, 11),
    (31, "Wei", "Zhang", "Frontend Engineer", "Engineering", "San Francisco HQ", "2026-12-07", 148000, 6),
    (32, "Tariq", "Bello", "Account Executive", "Sales", "New York Office", "2026-12-07", 92000, 13),
    (33, "Jordan", "Avery", "Customer Success Manager", "Customer Success", "New York Office", "2027-01-04", 85000, 16),
]


def bh_employee(eid, first, last, title, dept, loc, hire, pay, mgr):
    return {"id": eid, "firstName": first, "middleName": "", "lastName": last, "preferredName": "",
            "displayName": f"{first} {last}", "avatar": avatar(f"{first} {last}"),
            "email": f"{first.lower()}.{last.lower()}@{DOMAIN}", "homeEmail": "", "workPhone": f"415-555-{3000 + eid}",
            "workPhoneExt": "", "mobilePhone": "", "homePhone": "", "dateOfBirth": "", "gender": "", "maritalStatus": "",
            "address1": "", "address2": "", "city": "", "state": "", "zipcode": "", "country": "United States",
            "hireDate": hire, "terminationDate": None, "terminationType": None, "terminationReason": None,
            "regrettable": None, "rehireEligible": None, "status": "Active", "employmentStatus": "Full-Time",
            "jobTitle": title, "departmentId": BH_DEPT_ID[dept], "locationId": BH_LOC_ID[loc], "divisionId": None,
            "reportsToId": mgr, "employeeNumber": str(eid), "payRate": pay, "payType": "Salary",
            "payFrequency": "Twice a Month", "standardHoursPerWeek": 40,
            "socialMediaLinks": {"linkedin": "", "twitter": "", "facebook": ""},
            "emergencyContactName": "", "emergencyContactPhone": "", "emergencyContactRelation": "", "ssn": "",
            "payChangeHistory": [{"date": hire, "description": "Hire", "amount": pay, "payType": "Salary"}]}


def build_bamboohr():
    emps = [bh_employee(*row) for row in BH_STAFF]
    notifs = [
        {"id": 1, "type": "new_employee", "message": "New employee added: Jordan Avery", "timestamp": "2026-12-10T18:20:00Z",
         "isRead": True, "icon": "user", "linkTo": "/people/33", "isPastDue": False, "dueDate": None},
        {"id": 2, "type": "time_off_request", "message": "Noah Kim requested 3 days of vacation", "timestamp": "2026-12-11T16:00:00Z",
         "isRead": False, "icon": "calendar", "linkTo": "/time-off", "isPastDue": False, "dueDate": None},
        {"id": 3, "type": "task_due", "message": "Year-end compensation review closes Dec 20", "timestamp": "2026-12-08T16:00:00Z",
         "isRead": False, "icon": "check", "linkTo": "/reports", "isPastDue": False, "dueDate": "2026-12-20"},
        {"id": 4, "type": "new_employee", "message": "New employee added: Wei Zhang", "timestamp": "2026-11-09T18:00:00Z",
         "isRead": True, "icon": "user", "linkTo": "/people/31", "isPastDue": False, "dueDate": None},
        {"id": 5, "type": "new_employee", "message": "New employee added: Tariq Bello", "timestamp": "2026-11-09T18:10:00Z",
         "isRead": True, "icon": "user", "linkTo": "/people/32", "isPastDue": False, "dueDate": None},
    ]
    return {
        "currentUser": {"employeeId": 3, "role": "admin", "companyName": "Fernhill Labs", "companyLogo": None},
        "departments": [{"id": i, "name": n, "headId": h} for i, n, h in BH_DEPTS],
        "locations": [{"id": i, "name": n, "address": a, "timezone": tz} for i, n, a, tz in BH_LOCS],
        "divisions": [{"id": 1, "name": "North America"}],
        "employees": emps,
        "timeOffRequests": [
            {"id": 1, "employeeId": 23, "policyId": 1, "startDate": "2026-12-28", "endDate": "2026-12-30", "hours": 24,
             "status": "pending", "note": "Family trip", "reviewedBy": None, "reviewedAt": None, "createdAt": "2026-12-11T16:00:00Z"},
            {"id": 2, "employeeId": 12, "policyId": 1, "startDate": "2026-12-21", "endDate": "2026-12-24", "hours": 32,
             "status": "approved", "note": "Holidays", "reviewedBy": 11, "reviewedAt": "2026-12-02T17:00:00Z", "createdAt": "2026-11-30T17:00:00Z"},
        ],
        "timeOffBalances": [{"employeeId": e["id"], "policyId": 1, "available": 80, "scheduled": 0, "used": 24} for e in emps],
        "jobOpenings": [], "candidates": [],
        "announcements": [{"id": 1, "title": "Holiday schedule", "body": "Office closed Dec 24 - Jan 1. Payroll runs Dec 23.",
                           "authorId": 2, "createdAt": "2026-12-01T17:00:00Z", "isPinned": True}],
        "notifications": notifs, "notes": [], "documents": [], "trainings": [], "assets": [], "goals": [],
        "performanceReviews": [], "benefitEnrollments": [],
    }


def bh_create(bh, k, terms, n_offset=0, eff=None):
    """NewEmployeeModal ADD_EMPLOYEE + notification, then CompensationChangeModal UPDATE_EMPLOYEE + notification."""
    h = HIRES[k]
    eid = max(e["id"] for e in bh["employees"]) + 1
    emp = {"id": eid, "firstName": h["first"], "middleName": "", "lastName": h["last"], "preferredName": "",
           "displayName": full(k), "avatar": None, "email": work_email(k), "homeEmail": "", "workPhone": "", "workPhoneExt": "",
           "mobilePhone": "", "homePhone": "", "dateOfBirth": "", "gender": "", "maritalStatus": "", "address1": "",
           "address2": "", "city": "", "state": "", "zipcode": "", "country": "", "hireDate": terms["start"],
           "terminationDate": None, "status": "Active", "employmentStatus": "Full-Time", "jobTitle": terms["title"],
           "departmentId": BH_DEPT_ID[h["dept"]], "locationId": BH_LOC_ID[h["loc"]], "divisionId": None, "reportsToId": None,
           "employeeNumber": str(eid), "payRate": None, "payType": "Salary", "payFrequency": "Twice a Month",
           "standardHoursPerWeek": 40, "socialMediaLinks": {"linkedin": "", "twitter": "", "facebook": ""},
           "emergencyContactName": "", "emergencyContactPhone": "", "emergencyContactRelation": "", "ssn": ""}
    bh["employees"].append(emp)

    def notify(kind, msg, icon, link):
        nid = max([0] + [x["id"] for x in bh["notifications"]]) + 1
        bh["notifications"].insert(0, {"id": nid, "type": kind, "message": msg, "timestamp": NOW_Z, "isRead": False, "icon": icon,
                                    "linkTo": link, "isPastDue": False, "dueDate": None})
    notify("new_employee", f"New employee added: {full(k)}", "user", f"/people/{eid}")
    eff = eff or terms["start"]
    emp["payRate"] = terms["salary"]
    emp["payChangeHistory"] = [{"date": eff, "description": "Compensation change", "amount": terms["salary"], "payType": "Salary"}]
    notify("compensation_change", f"Compensation change requested for {full(k)}: ${terms['salary']:,} effective {eff}",
           "dollar", f"/people/{eid}/job")
    return emp


# ---------------------------------------------------------------- golden / variants
def correct_terms():
    return {k: dict(HIRES[k]["signed"]) for k in JANUARY}


def csv_rows(terms):
    rows = [CSV_HEADER]
    for k, t in terms.items():
        name = full(k) if k in HIRES else k
        rows.append([name, t["title"], t["start"], str(t["salary"])])
    return rows


def apply_run(seed, *, create, move, reply, reply_in_thread=True, dup_jordan=False):
    """create: {key: terms} for BambooHR; move: [keys] for Greenhouse Hired; reply: Slack text or None."""
    st = copy.deepcopy(seed)
    for k, t in create.items():
        bh_create(st["bamboohr"], k, t)
    if dup_jordan:
        bh_create(st["bamboohr"], "jordan", HIRES["jordan"]["signed"])
    for k in move:
        gh_move_hired(st["greenhouse"], k)
    if reply:
        slack_reply(st["slack"], reply, in_thread=reply_in_thread)
    return st


def golden_states(seed):
    return apply_run(seed, create={k: HIRES[k]["signed"] for k in NEW_IN_BAMBOO}, move=JANUARY, reply=GOLDEN_REPLY)


def naive_variant(seed):
    """Trusts Greenhouse/Slack/the first PDF found: ATS terms, Elena bump, skips Sam, adds Nadia/Owen/Ines, dup Jordan."""
    terms = {k: dict(HIRES[k]["ats"]) for k in ["priya", "marcus", "elena", "leo", "hana", "nadia", "owen", "ines"]}
    terms["elena"] = dict(title="Senior Product Designer", start="2027-01-11", salary=128000)
    states = apply_run(seed, create=terms, move=["priya", "marcus", "elena", "leo", "hana", "jordan", "owen", "ines"],
                       reply="Only mismatch I see: Elena Petrova - Greenhouse still has Product Designer at $118,000, "
                             "she's now Senior Product Designer at $128,000.", dup_jordan=True)
    rows = dict(terms)
    rows["jordan"] = HIRES["jordan"]["signed"]
    return states, csv_rows(rows)


def slip_variant(seed, key, wrong, drop_reply_line=None, include_extra=None):
    """Careful run except one trap: `key` gets `wrong` terms (or extra person created)."""
    create = {k: dict(HIRES[k]["signed"]) for k in NEW_IN_BAMBOO}
    move = list(JANUARY)
    rows = correct_terms()
    if wrong is not None:
        create[key] = wrong
        rows[key] = wrong
    if include_extra:
        create[include_extra] = dict(HIRES[include_extra]["signed"])
        rows[include_extra] = dict(HIRES[include_extra]["signed"])
    lines = GOLDEN_REPLY.split("\n")
    if drop_reply_line:
        lines = [ln for ln in lines if not ln.startswith(drop_reply_line)]
    states = apply_run(seed, create=create, move=move, reply="\n".join(lines))
    return states, csv_rows(rows)


def expected():
    return {
        "clock": CLOCK,
        "csv": {"path": f"/workspace/output/{CSV_NAME}", "header": CSV_HEADER},
        "new_hires": {full(k): {"title": HIRES[k]["signed"]["title"], "hireDate": HIRES[k]["signed"]["start"],
                                "payRate": HIRES[k]["signed"]["salary"], "departmentId": BH_DEPT_ID[HIRES[k]["dept"]],
                                "department": HIRES[k]["dept"], "email": work_email(k),
                                "greenhouse_application": gh_app_id(k)} for k in NEW_IN_BAMBOO},
        "january_starters": {full(k): {"title": HIRES[k]["signed"]["title"], "start_date": HIRES[k]["signed"]["start"],
                                       "base_salary": HIRES[k]["signed"]["salary"], "greenhouse_application": gh_app_id(k),
                                       "greenhouse_hired_stage": f"stage-{JOB_OF[k]}-8"} for k in JANUARY},
        "already_in_bamboohr": {"Jordan Avery": 33},
        "near_duplicate_protected": {"id": 14, "name": "Priya Ramanathan", "payRate": 152000, "jobTitle": "Data Engineer",
                                     "hireDate": "2024-03-18"},
        "must_not_create": {full(k): {"why": w, "greenhouse_application": gh_app_id(k)} for k, w in
                            [("nadia", "withdrew Dec 7 (Greenhouse rejection + note) despite signed letter"),
                             ("owen", "signed letter starts 2027-02-01, not January"),
                             ("ines", "offer only sent, envelope not signed")]},
        "greenhouse_must_not_move": [gh_app_id("ines"), gh_app_id("nadia")],
        "wrong_values_trap": {
            "Priya Raman": {"payRate": 165000, "source": "Greenhouse offer + Slack + voided envelope"},
            "Marcus Lindqvist": {"hireDate": "2027-01-04", "source": "Greenhouse + original letter + Slack"},
            "Elena Petrova": {"jobTitle": "Senior Product Designer", "payRate": 128000, "source": "unsigned amendment + Slack"},
            "Leo Fischer": {"jobTitle": "Account Executive", "payRate": 95000, "source": "Greenhouse + unsent draft PDF + Slack"},
        },
        "slack": {"channel": "people-ops", "thread_parent_message": THREAD_PARENT, "author": "U01",
                  "mismatches": {"Priya Raman": {"names": ["Priya", "Raman"], "value": "172,000 (accept 172000 / 172k)"},
                                 "Marcus Lindqvist": {"names": ["Marcus", "Lindqvist"], "value": "2027-01-19 (Jan 19 / January 19 / 1/19)"},
                                 "Leo Fischer": {"names": ["Leo", "Fischer"], "value": "105,000 (accept 105000 / 105k)"},
                                 "Owen Brandt": {"names": ["Owen", "Brandt"], "value": "2027-02-01 (Feb 1 / February 1 / 2/1)"}}},
    }


def main(out: Path):
    seed = {"greenhouse": build_greenhouse(), "docusign": build_docusign(), "slack": build_slack(), "bamboohr": build_bamboohr()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    write_letters(out / "input" / "offer_letters")
    golden = golden_states(seed)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    gold_rows = csv_rows(correct_terms())
    write_csv(out / "golden_output" / CSV_NAME, gold_rows)
    write_json(out / "expected.json", expected())

    variants = {
        "golden": (golden, gold_rows),
        "nop": (seed, None),
        "naive": naive_variant(seed),
        "slip_priya_voided": slip_variant(seed, "priya", dict(HIRES["priya"]["ats"]), drop_reply_line="Priya"),
        "slip_marcus_amendment": slip_variant(seed, "marcus", dict(HIRES["marcus"]["ats"]), drop_reply_line="Marcus"),
        "slip_elena_unsigned": slip_variant(seed, "elena", dict(title="Senior Product Designer", start="2027-01-11", salary=128000)),
        "slip_leo_draft": slip_variant(seed, "leo", dict(HIRES["leo"]["ats"]), drop_reply_line="Leo"),
        "slip_nadia_withdrawn": slip_variant(seed, None, None, include_extra="nadia"),
    }
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / CSV_NAME, rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
