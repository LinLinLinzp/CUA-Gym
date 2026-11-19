#!/usr/bin/env python3
"""World for the q4-renewals-closeout task (Salesforce + Yahoo Mail + Google Calendar + DocuSign + local CSV).

Writes into <out>/:
  seed/{salesforce,yahoo_mail,google_calendar,docusign}.json   initial state per site
  golden/{...}.json                                             state after a correct run
  golden_output/q4_renewals.csv                                 correct CLI deliverable
  input/cpq_quotes.csv                                          deal-desk quote export (agent-visible)
  expected.json                                                 hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/}   self-check fixtures

The story: Sarah Chen, senior account manager at
Acme Analytics in London, hands off the close-out of her Q4 FY27 renewals. Elena's checklist
(Yahoo Mail) defines the booking rules, Marcus's reply amends the kickoff rules (45 min, add
Marcus when ACV >= $60k). DocuSign shows which order form version was executed; amounts come
only from the CPQ export. Per renewal:
  Northwind   v1 envelope voided, v2 (36 mo, ACV 88,800 / TCV 266,400) completed Dec 9; draft v3 in CPQ
  Bluepeak    completed Dec 10, ACV 57,600 (SF still shows 54,000); kickoff 10:00 Eastern = 15:00 UK
  Harbor      customer signed, Marcus has NOT countersigned (status "signed") -> stays Negotiation
  Cobalt      early "send the paperwork" mail superseded by CFO's written non-renewal Dec 11 -> Closed Lost, void
  Summit Dental Group     completed Dec 8; kickoff moved from Fri 18 to Mon 21 13:30 in a later mail
  Summit Dental Partners  near-duplicate account, envelope still out -> untouched
  Pinecrest   already Closed Won + kickoff booked + filed -> untouched, no duplicate meeting
  Lakeside    completed Dec 11, 24 mo, ACV 63,000 / TCV 126,000; first proposed slot clashes with a QBR
"""

import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, product_image  # noqa: E402

CLOCK = "2026-12-14T09:15:00+00:00"
NOW_Z = "2026-12-14T09:40:00.000Z"
TZ = "Europe/London"
SARAH = ("Sarah Chen", "sarah.chen@acmecorp.com")
MARCUS = ("Marcus Reed", "marcus.reed@acmecorp.com")
ELENA = ("Elena Novak", "elena.novak@acmecorp.com")
PRIYA = ("Priya Desai", "priya.desai@acmecorp.com")
TOM = ("Tom Hartley", "tom.hartley@acmecorp.com")
COMPANY = "Acme Analytics Ltd"
FOLDER_FY27 = "folder_fy27"
FOLDER_FY26 = "folder_fy26"
CSV_NAME = "q4_renewals.csv"
CSV_HEADER = ["opportunity", "stage", "amount", "close_date", "kickoff"]
PROB = {"Prospecting": 10, "Qualification": 20, "Needs Analysis": 30, "Value Proposition": 50,
        "Proposal": 60, "Negotiation": 80, "Closed Won": 100, "Closed Lost": 0}

# ---------------------------------------------------------------- accounts
# key: (accountId, name, industry, city, country, website, owner)
ACCOUNTS = {
    "northwind": ("acc-101", "Northwind Logistics", "Transportation", "Manchester", "United Kingdom", "northwindlogistics.co.uk", "user-1"),
    "bluepeak": ("acc-102", "Bluepeak Health", "Healthcare", "Boston", "USA", "bluepeakhealth.com", "user-1"),
    "harbor": ("acc-103", "Harbor Freightways", "Transportation", "Southampton", "United Kingdom", "harborfreightways.co.uk", "user-1"),
    "cobalt": ("acc-104", "Cobalt Retail Group", "Retail", "Leeds", "United Kingdom", "cobaltretail.co.uk", "user-1"),
    "summitg": ("acc-105", "Summit Dental Group", "Healthcare", "Birmingham", "United Kingdom", "summitdentalgroup.co.uk", "user-1"),
    "summitp": ("acc-106", "Summit Dental Partners", "Healthcare", "Bristol", "United Kingdom", "summitdentalpartners.co.uk", "user-1"),
    "pinecrest": ("acc-107", "Pinecrest Software", "Technology", "Stockholm", "Sweden", "pinecrest.se", "user-1"),
    "lakeside": ("acc-108", "Lakeside Credit Union", "Financial Services", "Dublin", "Ireland", "lakesidecu.ie", "user-1"),
    "ferro": ("acc-109", "Ferro Components", "Manufacturing", "Turin", "Italy", "ferrocomponents.it", "user-1"),
    "driftwood": ("acc-110", "Driftwood Hotels", "Hospitality", "Brighton", "United Kingdom", "driftwoodhotels.co.uk", "user-1"),
    "halcyon": ("acc-111", "Halcyon Media", "Media", "London", "United Kingdom", "halcyonmedia.co.uk", "user-1"),
    "kestrel": ("acc-112", "Kestrel Insurance", "Financial Services", "Edinburgh", "United Kingdom", "kestrelinsurance.co.uk", "user-3"),
    "orbit": ("acc-113", "Orbit Telecom", "Telecommunications", "Amsterdam", "Netherlands", "orbittelecom.nl", "user-3"),
    "granite": ("acc-114", "Granite Bank", "Financial Services", "London", "United Kingdom", "granitebank.co.uk", "user-4"),
    "meridian": ("acc-115", "Meridian Foods", "Food & Beverage", "Cork", "Ireland", "meridianfoods.ie", "user-3"),
    "vantage": ("acc-116", "Vantage Energy", "Energy", "Aberdeen", "United Kingdom", "vantage-energy.co.uk", "user-4"),
    "quill": ("acc-117", "Quill Publishing", "Media", "Oxford", "United Kingdom", "quillpublishing.co.uk", "user-3"),
    "atlas": ("acc-118", "Atlas Robotics", "Manufacturing", "Munich", "Germany", "atlas-robotics.de", "user-4"),
    "sable": ("acc-119", "Sable Fashion", "Retail", "Paris", "France", "sablefashion.fr", "user-3"),
    "tidal": ("acc-120", "Tidal Water Services", "Utilities", "Cardiff", "United Kingdom", "tidalwater.co.uk", "user-4"),
    "crescent": ("acc-121", "Crescent Pharma", "Healthcare", "Cambridge", "United Kingdom", "crescentpharma.co.uk", "user-3"),
    "nimbus": ("acc-122", "Nimbus Travel", "Travel", "Lisbon", "Portugal", "nimbustravel.pt", "user-4"),
}

# key: (contactId, account key, first, last, title, email)
CONTACTS = {
    "dana": ("con-201", "northwind", "Dana", "Whitfield", "Chief Operating Officer", "dana.whitfield@northwindlogistics.co.uk"),
    "nw_it": ("con-202", "northwind", "Rob", "Ainsley", "Head of IT", "rob.ainsley@northwindlogistics.co.uk"),
    "jordan": ("con-203", "bluepeak", "Jordan", "Pierce", "VP Operations", "jordan.pierce@bluepeakhealth.com"),
    "bp_fin": ("con-204", "bluepeak", "Alicia", "Gomez", "Procurement Manager", "alicia.gomez@bluepeakhealth.com"),
    "liam": ("con-205", "harbor", "Liam", "Doyle", "Commercial Director", "liam.doyle@harborfreightways.co.uk"),
    "hannah": ("con-206", "cobalt", "Hannah", "Price", "Head of Ecommerce", "hannah.price@cobaltretail.co.uk"),
    "graham": ("con-207", "cobalt", "Graham", "Holt", "Chief Financial Officer", "graham.holt@cobaltretail.co.uk"),
    "megan": ("con-208", "summitg", "Megan", "Shaw", "Director of Practice Operations", "megan.shaw@summitdentalgroup.co.uk"),
    "ravi": ("con-209", "summitp", "Ravi", "Mehta", "Practice Manager", "ravi.mehta@summitdentalpartners.co.uk"),
    "sp_md": ("con-210", "summitp", "Claire", "Summers", "Managing Director", "claire.summers@summitdentalpartners.co.uk"),
    "oskar": ("con-211", "pinecrest", "Oskar", "Lind", "VP Engineering", "oskar.lind@pinecrest.se"),
    "aoife": ("con-212", "lakeside", "Aoife", "Brennan", "Chief Information Officer", "aoife.brennan@lakesidecu.ie"),
    "lk_ops": ("con-213", "lakeside", "Declan", "Murphy", "Data Platform Lead", "declan.murphy@lakesidecu.ie"),
    "giulia": ("con-214", "ferro", "Giulia", "Rossi", "Head of Analytics", "giulia.rossi@ferrocomponents.it"),
    "fiona": ("con-215", "driftwood", "Fiona", "Clarke", "Revenue Director", "fiona.clarke@driftwoodhotels.co.uk"),
    "ben": ("con-216", "halcyon", "Ben", "Achebe", "Head of Data", "ben.achebe@halcyonmedia.co.uk"),
    "kes": ("con-217", "kestrel", "Isla", "Fraser", "CTO", "isla.fraser@kestrelinsurance.co.uk"),
    "orb": ("con-218", "orbit", "Joost", "de Vries", "Director BI", "joost.devries@orbittelecom.nl"),
    "gra": ("con-219", "granite", "Oliver", "Grant", "Head of Analytics", "oliver.grant@granitebank.co.uk"),
    "mer": ("con-220", "meridian", "Niamh", "Walsh", "Operations Director", "niamh.walsh@meridianfoods.ie"),
    "van": ("con-221", "vantage", "Callum", "Reid", "Data Manager", "callum.reid@vantage-energy.co.uk"),
    "qui": ("con-222", "quill", "Hugo", "Bennett", "Digital Director", "hugo.bennett@quillpublishing.co.uk"),
    "atl": ("con-223", "atlas", "Lena", "Fischer", "COO", "lena.fischer@atlas-robotics.de"),
    "sab": ("con-224", "sable", "Camille", "Moreau", "Head of Merchandising", "camille.moreau@sablefashion.fr"),
    "tid": ("con-225", "tidal", "Gareth", "Evans", "Asset Data Lead", "gareth.evans@tidalwater.co.uk"),
    "cre": ("con-226", "crescent", "Anika", "Shah", "Head of Commercial Analytics", "anika.shah@crescentpharma.co.uk"),
    "nim": ("con-227", "nimbus", "Tiago", "Costa", "CIO", "tiago.costa@nimbustravel.pt"),
}

# Sarah's renewal opportunities (the work) + noise.
# key: (oppId, name, account key, contact key, amount, closeDate, stage, type, owner, nextStep)
OPPS = {
    "northwind": ("opp-301", "Northwind Logistics - FY27 Renewal", "northwind", "dana", 96000, "2026-12-31", "Negotiation", "Renewal", "user-1", "Reissued order form on 36-month option"),
    "bluepeak": ("opp-302", "Bluepeak Health - FY27 Renewal", "bluepeak", "jordan", 54000, "2026-12-18", "Proposal", "Renewal", "user-1", "Order form out for signature"),
    "harbor": ("opp-303", "Harbor Freightways - FY27 Renewal", "harbor", "liam", 72000, "2026-12-18", "Negotiation", "Renewal", "user-1", "Legal reviewing liability cap redline"),
    "cobalt": ("opp-304", "Cobalt Retail Group - FY27 Renewal", "cobalt", "hannah", 41000, "2026-12-21", "Negotiation", "Renewal", "user-1", "Awaiting CFO signature"),
    "summitg": ("opp-305", "Summit Dental Group - FY27 Renewal", "summitg", "megan", 26400, "2026-12-15", "Negotiation", "Renewal", "user-1", "Order form out for signature"),
    "summitp": ("opp-306", "Summit Dental Partners - FY27 Renewal", "summitp", "ravi", 31200, "2026-12-22", "Negotiation", "Renewal", "user-1", "MD to sign on return (Dec 21)"),
    "pinecrest": ("opp-307", "Pinecrest Software - FY27 Renewal", "pinecrest", "oskar", 48000, "2026-12-03", "Closed Won", "Renewal", "user-1", "Kickoff booked Dec 15"),
    "lakeside": ("opp-308", "Lakeside Credit Union - FY27 Renewal", "lakeside", "aoife", 64000, "2026-12-16", "Negotiation", "Renewal", "user-1", "Order form out for signature"),
    "ferro": ("opp-309", "Ferro Components - FY27 Renewal", "ferro", "giulia", 38500, "2027-01-29", "Proposal", "Renewal", "user-1", "Renewal call in January"),
    "driftwood": ("opp-310", "Driftwood Hotels - FY27 Renewal", "driftwood", "fiona", 22000, "2026-10-20", "Closed Lost", "Renewal", "user-1", "Customer moved to in-house BI"),
    "nw_addon": ("opp-311", "Northwind Logistics - Fleet Analytics Add-on", "northwind", "nw_it", 18000, "2027-02-26", "Value Proposition", "Existing Business", "user-1", "Demo fleet module to IT"),
    "halcyon": ("opp-312", "Halcyon Media - Audience Insights Expansion", "halcyon", "ben", 52000, "2027-03-31", "Needs Analysis", "Existing Business", "user-1", "QBR Dec 16"),
    "lk_addon": ("opp-313", "Lakeside Credit Union - Fraud Module Pilot", "lakeside", "lk_ops", 15000, "2027-03-15", "Qualification", "New Business", "user-1", "Scope pilot with data platform team"),
    "kestrel": ("opp-314", "Kestrel Insurance - FY27 Renewal", "kestrel", "kes", 86000, "2026-12-10", "Closed Won", "Renewal", "user-3", "Kickoff done"),
    "orbit": ("opp-315", "Orbit Telecom - FY27 Renewal", "orbit", "orb", 120000, "2026-12-23", "Negotiation", "Renewal", "user-3", "Procurement review"),
    "granite": ("opp-316", "Granite Bank - Enterprise Platform", "granite", "gra", 240000, "2027-03-31", "Proposal", "New Business", "user-4", "Security questionnaire"),
    "meridian": ("opp-317", "Meridian Foods - FY27 Renewal", "meridian", "mer", 33000, "2026-12-18", "Negotiation", "Renewal", "user-3", "Order form out for signature"),
    "vantage": ("opp-318", "Vantage Energy - Asset Analytics", "vantage", "van", 76000, "2027-02-12", "Needs Analysis", "New Business", "user-4", "Discovery workshop"),
    "quill": ("opp-319", "Quill Publishing - FY27 Renewal", "quill", "qui", 19500, "2026-11-27", "Closed Won", "Renewal", "user-3", "Kickoff done"),
    "atlas": ("opp-320", "Atlas Robotics - Pilot", "atlas", "atl", 28000, "2027-01-22", "Qualification", "New Business", "user-4", "Intro call with COO"),
    "sable": ("opp-321", "Sable Fashion - FY27 Renewal", "sable", "sab", 44000, "2026-12-30", "Proposal", "Renewal", "user-3", "Pricing approval"),
    "tidal": ("opp-322", "Tidal Water Services - Expansion", "tidal", "tid", 61000, "2027-01-15", "Value Proposition", "Existing Business", "user-4", "ROI deck"),
    "crescent": ("opp-323", "Crescent Pharma - FY27 Renewal", "crescent", "cre", 97000, "2026-12-17", "Closed Won", "Renewal", "user-3", "Kickoff Jan 6"),
    "nimbus": ("opp-324", "Nimbus Travel - Platform Migration", "nimbus", "nim", 135000, "2027-04-30", "Prospecting", "New Business", "user-4", "Initial discovery"),
    "orbit2": ("opp-325", "Orbit Telecom - Network Analytics Add-on", "orbit", "orb", 42000, "2027-02-27", "Proposal", "Existing Business", "user-3", "Proposal sent"),
    "granite2": ("opp-326", "Granite Bank - Data Residency Pilot", "granite", "gra", 25000, "2026-11-30", "Closed Lost", "New Business", "user-4", "Lost to incumbent"),
    "halcyon26": ("opp-327", "Halcyon Media - FY26 Renewal", "halcyon", "ben", 47000, "2025-12-12", "Closed Won", "Renewal", "user-1", "Renewed"),
    "northwind26": ("opp-328", "Northwind Logistics - FY26 Renewal", "northwind", "dana", 91000, "2025-12-12", "Closed Won", "Renewal", "user-1", "Renewed"),
}

# Q4 renewals in scope of the CSV deliverable (Sarah's, Renewal type, seed close date Oct-Dec 2026).
CSV_OPPS = ["northwind", "bluepeak", "harbor", "cobalt", "summitg", "summitp", "pinecrest", "lakeside", "driftwood"]

# ---------------------------------------------------------------- truth
# Outcome per opp key: stage, amount, closeDate.  None = unchanged from seed.
OUTCOMES = {
    "northwind": ("Closed Won", 88800, "2026-12-09"),
    "bluepeak": ("Closed Won", 57600, "2026-12-10"),
    "summitg": ("Closed Won", 27600, "2026-12-08"),
    "lakeside": ("Closed Won", 63000, "2026-12-11"),
    "cobalt": ("Closed Lost", 41000, "2026-12-11"),
}
UNTOUCHED_OPPS = ["harbor", "summitp", "pinecrest", "ferro", "driftwood", "nw_addon", "lk_addon"]

# Kickoffs: account key -> (title, start UTC, end UTC, guests). UK time == UTC in December.
KICKOFFS = {
    "northwind": ("FY27 Kickoff - Northwind Logistics", "2026-12-16T10:00:00.000Z", "2026-12-16T10:45:00.000Z",
                  ["dana.whitfield@northwindlogistics.co.uk", MARCUS[1]]),
    "bluepeak": ("FY27 Kickoff - Bluepeak Health", "2026-12-17T15:00:00.000Z", "2026-12-17T15:45:00.000Z",
                 ["jordan.pierce@bluepeakhealth.com"]),
    "summitg": ("FY27 Kickoff - Summit Dental Group", "2026-12-21T13:30:00.000Z", "2026-12-21T14:15:00.000Z",
                ["megan.shaw@summitdentalgroup.co.uk"]),
    "lakeside": ("FY27 Kickoff - Lakeside Credit Union", "2026-12-17T11:00:00.000Z", "2026-12-17T11:45:00.000Z",
                 ["aoife.brennan@lakesidecu.ie", MARCUS[1]]),
}
PINECREST_KICKOFF = "2026-12-15T15:00:00.000Z"
FILE_ENVELOPES = ["env_402", "env_403", "env_406", "env_409"]
VOID_ENVELOPE = ("env_405", "Customer not renewing")

# ---------------------------------------------------------------- CPQ export
# quote, version, account, created, status, term_months, seats, annual_fee, tcv, prepared_by
QUOTES = [
    ("Q-2271", 1, "Kestrel Insurance", "2026-10-28", "Presented", 12, 110, 86000, 86000, "Priya Desai"),
    ("Q-2276", 1, "Quill Publishing", "2026-10-30", "Presented", 12, 24, 19500, 19500, "Priya Desai"),
    ("Q-2280", 1, "Crescent Pharma", "2026-11-02", "Presented", 12, 120, 97000, 97000, "Priya Desai"),
    ("Q-2284", 1, "Orbit Telecom", "2026-11-03", "Presented", 12, 150, 120000, 120000, "Priya Desai"),
    ("Q-2288", 1, "Pinecrest Software", "2026-11-05", "Presented", 12, 60, 48000, 48000, "Sarah Chen"),
    ("Q-2291", 1, "Northwind Logistics", "2026-11-09", "Presented", 12, 80, 96000, 96000, "Sarah Chen"),
    ("Q-2294", 1, "Meridian Foods", "2026-11-10", "Presented", 12, 40, 33000, 33000, "Priya Desai"),
    ("Q-2296", 1, "Cobalt Retail Group", "2026-11-12", "Presented", 12, 50, 41000, 41000, "Sarah Chen"),
    ("Q-2298", 1, "Sable Fashion", "2026-11-13", "Presented", 12, 55, 44000, 44000, "Priya Desai"),
    ("Q-2302", 1, "Harbor Freightways", "2026-11-16", "Presented", 12, 93, 74400, 74400, "Sarah Chen"),
    ("Q-2305", 1, "Tidal Water Services", "2026-11-17", "Draft", 12, 75, 61000, 61000, "Tom Hartley"),
    ("Q-2307", 1, "Bluepeak Health", "2026-11-18", "Presented", 12, 64, 57600, 57600, "Sarah Chen"),
    ("Q-2309", 1, "Orbit Telecom", "2026-11-19", "Draft", 12, 50, 42000, 42000, "Priya Desai"),
    ("Q-2311", 1, "Granite Bank", "2026-11-20", "Presented", 36, 300, 240000, 720000, "Tom Hartley"),
    ("Q-2315", 1, "Summit Dental Group", "2026-11-23", "Presented", 12, 34, 27600, 27600, "Sarah Chen"),
    ("Q-2318", 1, "Summit Dental Partners", "2026-11-24", "Presented", 12, 39, 31200, 31200, "Sarah Chen"),
    ("Q-2320", 1, "Lakeside Credit Union", "2026-11-25", "Presented", 24, 78, 63000, 126000, "Sarah Chen"),
    ("Q-2291", 2, "Northwind Logistics", "2026-12-03", "Presented", 36, 80, 88800, 266400, "Sarah Chen"),
    ("Q-2323", 1, "Ferro Components", "2026-12-04", "Draft", 12, 48, 38500, 38500, "Sarah Chen"),
    ("Q-2325", 1, "Atlas Robotics", "2026-12-07", "Draft", 6, 20, 28000, 14000, "Tom Hartley"),
    ("Q-2291", 3, "Northwind Logistics", "2026-12-10", "Draft", 36, 95, 101460, 304380, "Sarah Chen"),
    ("Q-2327", 1, "Halcyon Media", "2026-12-11", "Draft", 12, 65, 52000, 52000, "Sarah Chen"),
]


def money(value) -> str:
    return f"{value}"


# ---------------------------------------------------------------- salesforce
SF_USERS = [
    ("user-1", "Sarah", "Chen", SARAH[1], "Senior Account Manager", "Sales", "Account Manager"),
    ("user-2", "Marcus", "Reed", MARCUS[1], "VP Sales, EMEA", "Sales", "Manager"),
    ("user-3", "Priya", "Desai", PRIYA[1], "Account Manager", "Sales", "Account Manager"),
    ("user-4", "Tom", "Hartley", TOM[1], "Account Executive", "Sales", "Account Executive"),
    ("user-5", "Elena", "Novak", ELENA[1], "Sales Operations Manager", "Sales Operations", "Operations"),
]


def sf_user(uid, first, last, email, title, dept, role):
    return {"userId": uid, "firstName": first, "lastName": last, "email": email, "phone": f"+44 20 7946 0{uid[-1]}21",
            "title": title, "department": dept, "role": role, "avatar": avatar(f"{first} {last}"),
            "timezone": TZ, "locale": "en-GB", "theme": "lightning"}


def build_salesforce():
    users = [sf_user(*u) for u in SF_USERS]
    accounts = []
    for i, (key, (aid, name, industry, city, country, site, owner)) in enumerate(ACCOUNTS.items()):
        accounts.append({
            "accountId": aid, "name": name, "phone": f"+44 161 555 0{100 + i}", "website": f"https://www.{site}",
            "type": "Customer", "industry": industry, "revenue": 5000000 + i * 1750000, "employees": 120 + i * 85,
            "description": f"{name} - Acme Analytics customer since {2019 + i % 5}.", "ownerId": owner,
            "billingStreet": f"{10 + i} Market Street", "billingCity": city, "billingState": "", "billingZip": "",
            "billingCountry": country, "shippingStreet": f"{10 + i} Market Street", "shippingCity": city,
            "shippingState": "", "shippingZip": "", "shippingCountry": country,
            "createdDate": f"20{20 + i % 5}-0{1 + i % 9}-15T10:00:00.000Z", "modifiedDate": "2026-11-30T10:00:00.000Z"})
    contacts = []
    for key, (cid, acc, first, last, title, email) in CONTACTS.items():
        a = ACCOUNTS[acc]
        contacts.append({"contactId": cid, "accountId": a[0], "firstName": first, "lastName": last, "title": title,
                         "department": "", "email": email, "phone": "", "mobile": "", "mailingStreet": "",
                         "mailingCity": a[3], "mailingState": "", "mailingZip": "", "mailingCountry": a[4],
                         "ownerId": a[6], "createdDate": "2024-02-01T10:00:00.000Z", "modifiedDate": "2026-10-01T10:00:00.000Z"})
    opps = []
    for key, (oid, name, acc, con, amount, close, stage, otype, owner, nxt) in OPPS.items():
        closed = stage.startswith("Closed")
        opps.append({"opportunityId": oid, "name": name, "accountId": ACCOUNTS[acc][0], "contactId": CONTACTS[con][0],
                     "amount": amount, "closeDate": f"{close}T12:00:00.000Z", "stage": stage, "probability": PROB[stage],
                     "type": otype, "leadSource": "Existing Customer" if otype != "New Business" else "Referral",
                     "nextStep": nxt, "description": f"{name}.", "ownerId": owner,
                     "createdDate": "2026-09-01T10:00:00.000Z" if "FY27" in name or otype != "Renewal" else "2025-09-01T10:00:00.000Z",
                     "modifiedDate": (f"{close}T17:00:00.000Z" if closed else "2026-12-04T16:00:00.000Z")})
    opps[0]["description"] = "FY27 renewal. Customer asked for a 36-month option on Dec 2; order form reissued Dec 3."
    leads = []
    lead_rows = [("Hamish", "Gray", "Thistle Distilling", "Head of Ops", "Working", "Warm"),
                 ("Sofia", "Lindgren", "Fjord Freight", "CFO", "New", "Hot"),
                 ("Mateo", "Ruiz", "Solano Logistics", "IT Director", "Working", "Cold"),
                 ("Chloe", "Dubois", "Lumiere Hotels", "Revenue Manager", "New", "Warm"),
                 ("Ewan", "Campbell", "Highland Rail", "Data Lead", "Qualified", "Hot"),
                 ("Ines", "Navarro", "Brisa Telecom", "BI Manager", "Unqualified", "Cold"),
                 ("Kai", "Becker", "Rhein Chemicals", "COO", "New", "Warm"),
                 ("Amara", "Okafor", "Lagos Fintech UK", "CTO", "Working", "Hot")]
    for i, (f, l, co, ti, st, ra) in enumerate(lead_rows):
        leads.append({"leadId": f"lead-{401 + i}", "firstName": f, "lastName": l, "company": co, "title": ti,
                      "email": f"{f.lower()}.{l.lower()}@{co.lower().replace(' ', '')}.com", "phone": "", "mobile": "",
                      "status": st, "source": "Website", "rating": ra, "street": "", "city": "London", "state": "",
                      "zip": "", "country": "United Kingdom", "industry": "Technology", "employees": 200 + i * 40,
                      "revenue": 8000000 + i * 1000000, "website": "", "description": "", "ownerId": ["user-1", "user-3", "user-4"][i % 3],
                      "createdDate": f"2026-11-{10 + i}T10:00:00.000Z", "modifiedDate": f"2026-12-0{1 + i % 8}T10:00:00.000Z"})
    cases = []
    case_rows = [("Dashboard refresh delays", "Working", "Medium", "northwind"),
                 ("SSO certificate renewal", "Closed", "High", "bluepeak"),
                 ("Export to Snowflake failing", "New", "High", "lakeside"),
                 ("Add 5 viewer seats", "Closed", "Low", "summitg"),
                 ("API rate limit question", "Working", "Low", "halcyon"),
                 ("Data retention request", "Escalated", "Medium", "cobalt")]
    for i, (subj, st, pr, acc) in enumerate(case_rows):
        cases.append({"caseId": f"case-{501 + i}", "caseNumber": f"CASE-{10421 + i:05d}", "subject": subj, "status": st,
                      "priority": pr, "origin": "Email", "accountId": ACCOUNTS[acc][0],
                      "contactId": next(c[0] for c in CONTACTS.values() if c[1] == acc), "description": subj + ".",
                      "ownerId": "user-1", "createdDate": f"2026-11-{12 + i}T10:00:00.000Z",
                      "modifiedDate": f"2026-12-0{2 + i}T10:00:00.000Z",
                      **({"closedDate": f"2026-12-0{2 + i}T10:00:00.000Z"} if st == "Closed" else {})})
    activities = [
        {"activityId": "act-601", "type": "task", "subject": "Send Northwind v2 order form", "status": "Completed", "priority": "High",
         "dueDate": "2026-12-03", "relatedToType": "Opportunity", "relatedToId": "opp-301", "assignedToId": "user-1", "description": "", "createdDate": "2026-12-02T15:00:00.000Z"},
        {"activityId": "act-602", "type": "task", "subject": "Chase Cobalt signature", "status": "Not Started", "priority": "Medium",
         "dueDate": "2026-12-14", "relatedToType": "Opportunity", "relatedToId": "opp-304", "assignedToId": "user-1", "description": "", "createdDate": "2026-12-01T15:00:00.000Z"},
        {"activityId": "act-603", "type": "task", "subject": "Prep Halcyon QBR deck", "status": "In Progress", "priority": "Medium",
         "dueDate": "2026-12-15", "relatedToType": "Opportunity", "relatedToId": "opp-312", "assignedToId": "user-1", "description": "", "createdDate": "2026-12-07T15:00:00.000Z"},
        {"activityId": "act-604", "type": "task", "subject": "Ferro renewal pricing review", "status": "Not Started", "priority": "Low",
         "dueDate": "2027-01-08", "relatedToType": "Opportunity", "relatedToId": "opp-309", "assignedToId": "user-1", "description": "", "createdDate": "2026-12-04T15:00:00.000Z"},
        {"activityId": "act-605", "type": "task", "subject": "Pinecrest kickoff agenda", "status": "Completed", "priority": "Medium",
         "dueDate": "2026-12-11", "relatedToType": "Opportunity", "relatedToId": "opp-307", "assignedToId": "user-1", "description": "", "createdDate": "2026-12-04T15:00:00.000Z"},
        {"activityId": "act-606", "type": "task", "subject": "Orbit procurement docs", "status": "In Progress", "priority": "High",
         "dueDate": "2026-12-16", "relatedToType": "Opportunity", "relatedToId": "opp-315", "assignedToId": "user-3", "description": "", "createdDate": "2026-12-04T15:00:00.000Z"},
    ]
    chatter = [
        {"postId": "post-701", "userId": "user-2", "content": "Great work on Pinecrest and Kestrel, team. Let's get the rest of the Q4 renewals over the line this week.",
         "createdDate": "2026-12-04T17:00:00.000Z", "likeCount": 2, "commentCount": 0, "likes": ["user-1", "user-3"], "comments": []},
        {"postId": "post-702", "userId": "user-5", "content": "Reminder: Q4 renewal close-out checklist went out by email. Finance locks FY26 bookings on Dec 31.",
         "createdDate": "2026-12-07T11:00:00.000Z", "likeCount": 1, "commentCount": 0, "likes": ["user-2"], "comments": []},
        {"postId": "post-703", "userId": "user-3", "content": "Crescent Pharma renewed for FY27 - kickoff Jan 6.",
         "createdDate": "2026-12-08T15:00:00.000Z", "likeCount": 3, "commentCount": 0, "likes": ["user-1", "user-2", "user-5"], "comments": []},
    ]
    return {"user": copy.deepcopy(users[0]), "users": users, "leads": leads, "accounts": accounts, "contacts": contacts,
            "opportunities": opps, "cases": cases, "activities": activities, "chatterPosts": chatter, "files": [],
            "dashboards": [], "following": ["user-2", "user-5"], "recentlyViewed": [], "dismissedNotifications": []}


# ---------------------------------------------------------------- docusign
def ds_envelope(eid, subject, doc, signer, status, created, sent=None, completed=None, voided=None, void_reason=None,
                customer_signed=None, folder=None, message=None, viewed=None):
    name, email = signer
    hist = [{"id": f"evt_{eid}_1", "timestamp": created, "action": "created", "actorName": SARAH[0],
             "actorEmail": SARAH[1], "details": "Envelope created"}]
    cust_signed_at = completed or customer_signed
    recips = [
        {"id": f"rec_{eid}_1", "name": name, "email": email, "role": "signer", "routingOrder": 1,
         "status": "signed" if cust_signed_at else ("created" if status == "draft" else ("delivered" if viewed else "sent")),
         "signedAt": cust_signed_at, "viewedAt": viewed or cust_signed_at, "deliveredAt": sent,
         "declinedAt": None, "declineReason": None},
        {"id": f"rec_{eid}_2", "name": MARCUS[0], "email": MARCUS[1], "role": "signer", "routingOrder": 2,
         "status": "signed" if completed else ("delivered" if customer_signed else "created"),
         "signedAt": completed, "viewedAt": completed or customer_signed, "deliveredAt": completed or customer_signed,
         "declinedAt": None, "declineReason": None},
    ]
    if sent:
        hist.append({"id": f"evt_{eid}_2", "timestamp": sent, "action": "sent", "actorName": SARAH[0], "actorEmail": SARAH[1],
                     "details": "Envelope sent to 2 recipients"})
        hist.append({"id": f"evt_{eid}_3", "timestamp": sent, "action": "delivered", "actorName": name, "actorEmail": email,
                     "details": f"Envelope delivered to {name}"})
    if viewed:
        hist.append({"id": f"evt_{eid}_4", "timestamp": viewed, "action": "viewed", "actorName": name, "actorEmail": email,
                     "details": f"{name} viewed the document"})
    if cust_signed_at:
        hist.append({"id": f"evt_{eid}_5", "timestamp": cust_signed_at, "action": "signed", "actorName": name,
                     "actorEmail": email, "details": f"{name} signed the document"})
    if customer_signed and not completed:
        hist.append({"id": f"evt_{eid}_6", "timestamp": customer_signed, "action": "delivered", "actorName": MARCUS[0],
                     "actorEmail": MARCUS[1], "details": f"Envelope delivered to {MARCUS[0]} for countersignature"})
    if completed:
        hist.append({"id": f"evt_{eid}_7", "timestamp": completed, "action": "signed", "actorName": MARCUS[0],
                     "actorEmail": MARCUS[1], "details": f"{MARCUS[0]} signed the document"})
        hist.append({"id": f"evt_{eid}_8", "timestamp": completed, "action": "completed", "actorName": "System",
                     "actorEmail": "", "details": "All recipients have completed signing"})
    if voided:
        hist.append({"id": f"evt_{eid}_9", "timestamp": voided, "action": "voided", "actorName": SARAH[0],
                     "actorEmail": SARAH[1], "details": f"Envelope voided: {void_reason}"})
    last = voided or completed or customer_signed or viewed or sent or created
    return {"id": eid, "subject": subject, "message": message or f"Hi {name.split()[0]}, here is the renewal order form for signature. Thanks, Sarah",
            "status": status, "createdAt": created, "sentAt": sent, "completedAt": completed, "voidedAt": voided,
            "declinedAt": None, "lastActivityAt": last,
            "expiresAt": None if status in ("completed", "voided", "draft") else "2027-01-15T00:00:00.000Z",
            "senderId": "user_1", "folderId": folder, "templateId": "tmpl_renewal" if "Renewal" in subject else None,
            "reminderEnabled": status in ("sent", "delivered", "signed"), "reminderDays": 3, "reminderFrequency": 2,
            "documents": [{"id": f"doc_{eid}_1", "name": doc, "pageCount": 4, "order": 1,
                           "fileUrl": product_image(doc.replace("_", " ").replace(".pdf", "")), "fileType": "pdf"}],
            "recipients": recips, "fields": [], "history": hist}


def C(key):
    c = CONTACTS[key]
    return (f"{c[2]} {c[3]}", c[5])


def build_docusign():
    env = [
        # ---- FY26 renewals, executed last December (near-duplicate subjects, other year)
        ds_envelope("env_301", "Northwind Logistics - FY26 Renewal Order Form", "Northwind_FY26_Renewal_Q-1904_v1.pdf", C("dana"),
                    "completed", "2025-12-01T10:00:00.000Z", sent="2025-12-01T10:05:00.000Z", completed="2025-12-12T14:30:00.000Z", folder=FOLDER_FY26),
        ds_envelope("env_302", "Bluepeak Health - FY26 Renewal Order Form", "Bluepeak_FY26_Renewal_Q-1911_v1.pdf", C("jordan"),
                    "completed", "2025-12-02T10:00:00.000Z", sent="2025-12-02T10:05:00.000Z", completed="2025-12-09T19:10:00.000Z", folder=FOLDER_FY26),
        ds_envelope("env_303", "Lakeside Credit Union - FY26 Renewal Order Form", "Lakeside_FY26_Renewal_Q-1915_v1.pdf", C("aoife"),
                    "completed", "2025-12-03T10:00:00.000Z", sent="2025-12-03T10:05:00.000Z", completed="2025-12-15T16:00:00.000Z", folder=FOLDER_FY26),
        ds_envelope("env_304", "Summit Dental Group - FY26 Renewal Order Form", "SummitDentalGroup_FY26_Renewal_Q-1920_v1.pdf", C("megan"),
                    "completed", "2025-12-04T10:00:00.000Z", sent="2025-12-04T10:05:00.000Z", completed="2025-12-10T11:00:00.000Z", folder=FOLDER_FY26),
        ds_envelope("env_305", "Halcyon Media - FY26 Renewal Order Form", "Halcyon_FY26_Renewal_Q-1922_v1.pdf", C("ben"),
                    "completed", "2025-12-05T10:00:00.000Z", sent="2025-12-05T10:05:00.000Z", completed="2025-12-12T12:00:00.000Z", folder=FOLDER_FY26),
        ds_envelope("env_306", "Harbor Freightways - FY26 Renewal Order Form", "Harbor_FY26_Renewal_Q-1925_v1.pdf", C("liam"),
                    "completed", "2025-12-05T11:00:00.000Z", sent="2025-12-05T11:05:00.000Z", completed="2025-12-16T09:40:00.000Z", folder=FOLDER_FY26),
        # ---- FY27 renewals
        ds_envelope("env_401", "Northwind Logistics - FY27 Renewal Order Form", "Northwind_FY27_Renewal_Q-2291_v1.pdf", C("dana"),
                    "voided", "2026-11-10T10:00:00.000Z", sent="2026-11-10T10:04:00.000Z", viewed="2026-11-12T09:15:00.000Z",
                    voided="2026-12-03T10:20:00.000Z", void_reason="Customer asked for 36-month term - reissuing order form"),
        ds_envelope("env_402", "Northwind Logistics - FY27 Renewal Order Form", "Northwind_FY27_Renewal_Q-2291_v2.pdf", C("dana"),
                    "completed", "2026-12-03T10:30:00.000Z", sent="2026-12-03T10:34:00.000Z", viewed="2026-12-04T08:50:00.000Z",
                    completed="2026-12-09T15:42:00.000Z",
                    message="Hi Dana, as discussed, here is the reissued renewal order form on the 36-month option. Thanks, Sarah"),
        ds_envelope("env_403", "Bluepeak Health - FY27 Renewal Order Form", "Bluepeak_FY27_Renewal_Q-2307_v1.pdf", C("jordan"),
                    "completed", "2026-11-19T15:00:00.000Z", sent="2026-11-19T15:03:00.000Z", viewed="2026-11-20T14:00:00.000Z",
                    completed="2026-12-10T18:05:00.000Z"),
        ds_envelope("env_404", "Harbor Freightways - FY27 Renewal Order Form", "Harbor_FY27_Renewal_Q-2302_v1.pdf", C("liam"),
                    "signed", "2026-11-17T11:00:00.000Z", sent="2026-11-17T11:02:00.000Z", viewed="2026-11-18T09:30:00.000Z",
                    customer_signed="2026-12-11T09:12:00.000Z"),
        ds_envelope("env_405", "Cobalt Retail Group - FY27 Renewal Order Form", "Cobalt_FY27_Renewal_Q-2296_v1.pdf", C("graham"),
                    "delivered", "2026-11-24T10:00:00.000Z", sent="2026-11-24T10:02:00.000Z", viewed="2026-11-26T16:40:00.000Z",
                    message="Hi Graham, Hannah asked me to route the FY27 renewal order form to you for signature. Thanks, Sarah"),
        ds_envelope("env_406", "Summit Dental Group - FY27 Renewal Order Form", "SummitDentalGroup_FY27_Renewal_Q-2315_v1.pdf", C("megan"),
                    "completed", "2026-11-24T12:00:00.000Z", sent="2026-11-24T12:03:00.000Z", viewed="2026-11-25T10:00:00.000Z",
                    completed="2026-12-08T11:20:00.000Z"),
        ds_envelope("env_407", "Summit Dental Partners - FY27 Renewal Order Form", "SummitDentalPartners_FY27_Renewal_Q-2318_v1.pdf", C("sp_md"),
                    "sent", "2026-12-04T10:00:00.000Z", sent="2026-12-04T10:02:00.000Z"),
        ds_envelope("env_408", "Pinecrest Software - FY27 Renewal Order Form", "Pinecrest_FY27_Renewal_Q-2288_v1.pdf", C("oskar"),
                    "completed", "2026-11-06T09:00:00.000Z", sent="2026-11-06T09:02:00.000Z", viewed="2026-11-07T08:00:00.000Z",
                    completed="2026-12-03T14:10:00.000Z", folder=FOLDER_FY27),
        ds_envelope("env_409", "Lakeside Credit Union - FY27 Renewal Order Form", "Lakeside_FY27_Renewal_Q-2320_v1.pdf", C("aoife"),
                    "completed", "2026-11-26T10:00:00.000Z", sent="2026-11-26T10:05:00.000Z", viewed="2026-11-27T09:00:00.000Z",
                    completed="2026-12-11T16:30:00.000Z"),
        ds_envelope("env_410", "Ferro Components - FY27 Renewal Order Form", "Ferro_FY27_Renewal_Q-2323_v1.pdf", C("giulia"),
                    "draft", "2026-12-04T15:00:00.000Z", message="Draft - hold until January pricing call"),
        ds_envelope("env_411", "Driftwood Hotels - FY27 Renewal Order Form", "Driftwood_FY27_Renewal_Q-2262_v1.pdf", C("fiona"),
                    "voided", "2026-10-01T10:00:00.000Z", sent="2026-10-01T10:03:00.000Z", viewed="2026-10-02T09:00:00.000Z",
                    voided="2026-10-20T13:00:00.000Z", void_reason="Customer not renewing"),
        # ---- other paperwork
        ds_envelope("env_501", "Halcyon Media - Mutual NDA (Audience Insights)", "Halcyon_Mutual_NDA_2026.pdf", C("ben"),
                    "completed", "2026-11-02T10:00:00.000Z", sent="2026-11-02T10:01:00.000Z", completed="2026-11-04T12:00:00.000Z",
                    folder="folder_legal"),
        ds_envelope("env_502", "Halcyon Media - Data Processing Addendum", "Halcyon_DPA_v3.pdf", C("ben"),
                    "delivered", "2026-12-07T10:00:00.000Z", sent="2026-12-07T10:02:00.000Z", viewed="2026-12-08T15:00:00.000Z",
                    folder="folder_legal"),
        ds_envelope("env_503", "Lakeside Credit Union - Fraud Module Pilot SOW", "Lakeside_FraudPilot_SOW_draft.pdf", C("lk_ops"),
                    "draft", "2026-12-10T14:00:00.000Z"),
        ds_envelope("env_504", "Harbor Freightways - Liability Cap Side Letter", "Harbor_SideLetter_LiabilityCap_v2.pdf", C("liam"),
                    "delivered", "2026-12-10T16:00:00.000Z", sent="2026-12-10T16:02:00.000Z", viewed="2026-12-11T08:30:00.000Z",
                    folder="folder_legal"),
    ]
    audit = []
    for i, e in enumerate(sorted(env, key=lambda e: e["createdAt"])):
        audit.append({"id": f"audit_{i + 1}", "timestamp": e["createdAt"], "action": "CREATE_ENVELOPE",
                      "details": f"Created envelope: {e['subject']}", "envelopeId": e["id"]})
    audit.reverse()
    contacts = [{"id": f"contact_{i + 1}", "name": f"{c[2]} {c[3]}", "email": c[5], "company": ACCOUNTS[c[1]][1], "title": c[4]}
                for i, c in enumerate(CONTACTS.values()) if ACCOUNTS[c[1]][6] == "user-1"]
    contacts.append({"id": "contact_m", "name": MARCUS[0], "email": MARCUS[1], "company": COMPANY, "title": "VP Sales, EMEA"})
    return {
        "user": {"id": "user_1", "name": SARAH[0], "email": SARAH[1], "title": "Senior Account Manager", "company": COMPANY,
                 "avatar": avatar(SARAH[0]), "signatureDataUrl": None, "initialsDataUrl": None, "memberSince": "2022-03-14",
                 "settings": {"defaultReminderDays": 3, "defaultExpirationDays": 45, "timezone": TZ}},
        "envelopes": env,
        "templates": [{"id": "tmpl_renewal", "name": "Acme Renewal Order Form", "description": "Customer signer + VP Sales countersign",
                       "createdAt": "2024-09-01T10:00:00.000Z", "lastUsedAt": "2026-12-04T10:00:00.000Z", "usageCount": 64,
                       "ownerId": "user_1", "shared": True,
                       "documents": [{"id": "tdoc_renewal_1", "name": "Acme_Renewal_Order_Form_Template.pdf", "pageCount": 4, "order": 1,
                                      "fileUrl": product_image("Acme Renewal Order Form"), "fileType": "pdf"}],
                       "roles": [{"id": "role_r1", "name": "Customer Signer", "role": "signer", "routingOrder": 1},
                                 {"id": "role_r2", "name": "VP Sales", "role": "signer", "routingOrder": 2}],
                       "fields": []}],
        "folders": [{"id": FOLDER_FY26, "name": "FY26 Renewals - Executed", "parentFolder": None, "createdAt": "2025-11-20T10:00:00.000Z"},
                    {"id": FOLDER_FY27, "name": "FY27 Renewals - Executed", "parentFolder": None, "createdAt": "2026-11-20T10:00:00.000Z"},
                    {"id": "folder_legal", "name": "NDAs & Legal", "parentFolder": None, "createdAt": "2024-05-02T10:00:00.000Z"}],
        "contacts": contacts,
        "auditLog": audit,
    }


# ---------------------------------------------------------------- yahoo mail
FOLDERS_SYS = ["inbox", "draft", "sent", "archive", "spam", "trash"]


def ym(mid, conv, sender, subject, body, date, *, folder="inbox", to=None, cc=None, category="primary", read=True,
       starred=False, reply_to_id=None):
    received = folder != "sent"
    frm = {"name": sender[0], "email": sender[1]}
    return {"id": mid, "conversationId": conv, "folderId": folder, "previousFolderId": None, "category": category if received else None,
            "from": frm, "to": [{"name": t[0], "email": t[1]} for t in (to or [SARAH])],
            "cc": [{"name": t[0], "email": t[1]} for t in (cc or [])], "bcc": [], "replyTo": None,
            "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None, "date": date,
            "isRead": read, "isStarred": starred, "isDraft": False, "status": "received" if received else "sent",
            "attachments": [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"), "summary": None,
            "orderInfo": None, "travelInfo": None, "inReplyToId": reply_to_id, "forwardedFromId": None,
            "replyType": "reply" if reply_to_id and not received else None, "repliedAt": None, "forwardedAt": None,
            "sentAt": None if received else date, "movedAt": None, "appliedFilterId": None, "createdAt": date, "updatedAt": None}


DSE = ("DocuSign", "dse@docusign.net")


def build_yahoo():
    reps = [SARAH, MARCUS, ELENA, PRIYA, TOM]
    checklist = (
        "Hi all,\n\nFinance locks FY26 bookings on Dec 31, so every Q4 renewal has to be in its final state in Salesforce "
        "this week. Same rules for everyone:\n\n"
        "1. Closed Won only once the renewal order form is fully executed in DocuSign, i.e. the envelope is Completed: "
        "the customer has signed AND Marcus has countersigned. A customer signature on its own does not count - leave "
        "those in Negotiation until Marcus signs.\n"
        "2. Amount = the annual fee on the quote version that was actually executed. The quote number and version are in "
        "the order form file name on the envelope (e.g. ..._Q-2100_v2.pdf); look them up in the CPQ export. For multi-year "
        "terms book the annual fee, not the total contract value.\n"
        "3. Close Date = the day the envelope was completed (UK date).\n"
        "4. If the customer has told us in writing that they are not renewing: Closed Lost, close date = the date of that "
        "email, leave the amount as it is, and void any renewal envelope still out for signature with the reason "
        "\"Customer not renewing\".\n"
        "5. File every executed FY27 renewal envelope in the \"FY27 Renewals - Executed\" folder in DocuSign.\n"
        "6. Book a 30-minute kickoff call for every newly won renewal: title \"FY27 Kickoff - <Account Name>\", invite the "
        "customer's signer, at the time you agreed with them by email (the calendar is on UK time). Don't book over "
        "anything already in your calendar.\n\nThanks,\nElena\n\nElena Novak | Sales Operations | Acme Analytics")
    marcus_amend = (
        "All - one change to point 6 after the leadership offsite: kickoff calls are 45 minutes from now on (the 30-minute "
        "ones kept running over), and add me (marcus.reed@acmecorp.com) to the invite for any renewal with an annual fee "
        "of $60k or more. Everything else in Elena's list stands.\n\nMarcus")
    msgs = [
        # ---- rules
        ym("msg_0001", "cnv_rules", ELENA, "Q4 renewal close-out checklist", checklist, "2026-12-07T09:05:00.000Z",
           to=reps, starred=True),
        ym("msg_0002", "cnv_rules", MARCUS, "Re: Q4 renewal close-out checklist", marcus_amend, "2026-12-11T17:48:00.000Z",
           to=reps, read=False, reply_to_id="msg_0001"),
        # ---- Northwind
        ym("msg_0010", "cnv_nw", C("dana"), "FY27 renewal - term question",
           "Hi Sarah,\n\nWe've had a look at the renewal order form. Before I sign: we'd rather lock pricing in for three "
           "years. Could you reissue it on the 36-month option we talked about?\n\nThanks,\nDana", "2026-12-02T14:10:00.000Z"),
        ym("msg_0011", "cnv_nw", SARAH, "Re: FY27 renewal - term question",
           "Hi Dana,\n\nNo problem - I've voided the 12-month version and sent the 36-month order form through DocuSign.\n\nBest,\nSarah",
           "2026-12-03T10:40:00.000Z", folder="sent", to=[C("dana")], reply_to_id="msg_0010"),
        ym("msg_0012", "cnv_nw", C("dana"), "Re: FY27 renewal - term question",
           "Hi Sarah,\n\nSigned the 36-month version this afternoon. For the kickoff I can do Tuesday 15 December at 14:00 or "
           "Wednesday 16 December at 10:00, both UK time. Whichever suits you.\n\nDana", "2026-12-09T16:05:00.000Z", read=False),
        # ---- Bluepeak
        ym("msg_0020", "cnv_bp", C("jordan"), "Bluepeak renewal - signed",
           "Hi Sarah,\n\nAll signed on our end. For the kickoff, Thursday December 17 at 10:00 am Eastern is the only slot "
           "where I can get the whole ops team together - hope that works on your side.\n\nBest,\nJordan Pierce\nVP Operations, Bluepeak Health\nBoston, MA",
           "2026-12-10T18:30:00.000Z", read=False),
        # ---- Harbor
        ym("msg_0030", "cnv_hb", C("liam"), "Harbor renewal",
           "Morning Sarah,\n\nI've signed the FY27 renewal this morning. Shall we pencil in the kickoff for Monday 21 December "
           "at 11:00?\n\nCheers,\nLiam", "2026-12-11T09:20:00.000Z", read=False),
        ym("msg_0031", "cnv_hbm", MARCUS, "Harbor countersign",
           "Sarah - saw Liam signed Harbor this morning. I'm holding my countersignature until legal closes out the "
           "liability cap side letter; realistically that's the week of the 21st. Leave it open until then.\n\nM",
           "2026-12-11T11:02:00.000Z", read=False),
        # ---- Cobalt
        ym("msg_0040", "cnv_cb1", C("hannah"), "Re: Cobalt FY27 renewal",
           "Hi Sarah,\n\nTerms look fine from our side. Send the paperwork over and I'll route it to Graham for "
           "signature.\n\nHannah", "2026-11-23T13:15:00.000Z"),
        ym("msg_0041", "cnv_cb2", C("graham"), "Acme Analytics renewal",
           "Dear Sarah,\n\nFollowing our board review we have decided not to renew our Acme Analytics subscription; we are "
           "consolidating reporting onto our new ERP vendor's tooling. Please take this email as our formal notice. We'll "
           "use the service through the end of the current term on 31 December.\n\nThank you for your help over the last "
           "three years.\n\nKind regards,\nGraham Holt\nCFO, Cobalt Retail Group", "2026-12-11T14:20:00.000Z",
           cc=[C("hannah")], read=False),
        # ---- Summit Dental Group
        ym("msg_0050", "cnv_sg", C("megan"), "Signed!",
           "Hi Sarah,\n\nSigned and done. Would Friday 18 December at 13:30 work for the kickoff?\n\nMegan",
           "2026-12-08T11:45:00.000Z"),
        ym("msg_0051", "cnv_sg", SARAH, "Re: Signed!",
           "Hi Megan,\n\nFriday 18th at 13:30 works - I'll send an invite.\n\nSarah", "2026-12-08T12:10:00.000Z",
           folder="sent", to=[C("megan")], reply_to_id="msg_0050"),
        ym("msg_0052", "cnv_sg", C("megan"), "Re: Signed!",
           "Hi Sarah,\n\nSorry to do this - Friday has fallen apart (we've got a CQC inspection that day). Could we move the "
           "kickoff to Monday 21 December, same time?\n\nThanks,\nMegan", "2026-12-11T15:35:00.000Z", read=False),
        # ---- Summit Dental Partners
        ym("msg_0055", "cnv_sp", C("ravi"), "Renewal paperwork",
           "Hi Sarah,\n\nThanks for sending the renewal over. Claire (our MD) is away until the 21st and will sign when she's "
           "back.\n\nRavi", "2026-12-10T10:05:00.000Z"),
        # ---- Pinecrest (already handled)
        ym("msg_0060", "cnv_pc", C("oskar"), "Re: FY27 kickoff",
           "Hi Sarah,\n\nGot the invite - see you on 15 December at 15:00 UK.\n\nOskar", "2026-12-04T08:30:00.000Z"),
        # ---- Lakeside
        ym("msg_0070", "cnv_lk", C("aoife"), "Lakeside renewal",
           "Hi Sarah,\n\nSigned, and I see Marcus's countersignature came through this afternoon as well. For the kickoff: "
           "Wednesday 16 December at 15:00 or Thursday 17 December at 11:00 (Dublin time, so same as yours).\n\nAoife",
           "2026-12-11T16:52:00.000Z", read=False),
        # ---- Ferro (next quarter)
        ym("msg_0075", "cnv_fe", C("giulia"), "Renewal timing",
           "Ciao Sarah,\n\nOur budget for 2027 is approved in mid-January, so let's talk about the renewal after that. Our "
           "current term runs until 31 January.\n\nGiulia", "2026-12-04T09:10:00.000Z"),
        # ---- DocuSign notifications
        ym("msg_0080", "cnv_d1", DSE, "Completed: Pinecrest Software - FY27 Renewal Order Form",
           "All parties have completed Pinecrest Software - FY27 Renewal Order Form.", "2026-12-03T14:11:00.000Z", category="primary"),
        ym("msg_0081", "cnv_d2", DSE, "Completed: Summit Dental Group - FY27 Renewal Order Form",
           "All parties have completed Summit Dental Group - FY27 Renewal Order Form.", "2026-12-08T11:21:00.000Z"),
        ym("msg_0082", "cnv_d3", DSE, "Completed: Northwind Logistics - FY27 Renewal Order Form",
           "All parties have completed Northwind Logistics - FY27 Renewal Order Form.", "2026-12-09T15:43:00.000Z"),
        ym("msg_0083", "cnv_d4", DSE, "Completed: Bluepeak Health - FY27 Renewal Order Form",
           "All parties have completed Bluepeak Health - FY27 Renewal Order Form.", "2026-12-10T18:06:00.000Z"),
        ym("msg_0084", "cnv_d5", DSE, "Liam Doyle signed: Harbor Freightways - FY27 Renewal Order Form",
           "Liam Doyle has signed Harbor Freightways - FY27 Renewal Order Form. The envelope has been sent to the next recipient.",
           "2026-12-11T09:13:00.000Z", read=False),
        ym("msg_0085", "cnv_d6", DSE, "Completed: Lakeside Credit Union - FY27 Renewal Order Form",
           "All parties have completed Lakeside Credit Union - FY27 Renewal Order Form.", "2026-12-11T16:31:00.000Z", read=False),
        # ---- internal noise
        ym("msg_0100", "cnv_n1", PRIYA, "Halcyon QBR deck",
           "Hey, I dropped last quarter's usage charts into the Halcyon QBR deck. Wednesday 14:30 still on?\n\nP", "2026-12-10T12:00:00.000Z"),
        ym("msg_0101", "cnv_n2", ("Acme Travel Desk", "travel@acmecorp.com"), "Itinerary: EMEA Sales Kickoff, Barcelona (14 Dec)",
           "Flight BA478 LHR 06:55 -> BCN 10:05, return BA483 BCN 19:40 -> LHR 21:05. Venue: Hotel Arts, Barcelona.",
           "2026-12-01T09:00:00.000Z"),
        ym("msg_0102", "cnv_n3", ("Acme Finance", "finance@acmecorp.com"), "December expense deadline",
           "Please submit all December expenses by Friday 18 December.", "2026-12-09T08:00:00.000Z"),
        ym("msg_0103", "cnv_n4", TOM, "Granite security questionnaire",
           "Sarah, any chance you can share the questionnaire answers we used for Lakeside? Granite asked the same things.\n\nTom",
           "2026-12-10T15:20:00.000Z"),
        ym("msg_0104", "cnv_n5", ELENA, "CPQ export for close-out",
           "Hi Sarah, the deal desk CPQ export (all quote versions, Q4) is the one I dropped on your laptop - every quote "
           "version is a row. Shout if anything's missing.\n\nElena", "2026-12-07T09:20:00.000Z"),
        ym("msg_0105", "cnv_n6", ("Acme People Team", "people@acmecorp.com"), "Office closure 24 Dec - 1 Jan",
           "The London office is closed from 24 December and reopens on 4 January.", "2026-12-02T10:00:00.000Z"),
        ym("msg_0106", "cnv_n7", PRIYA, "Kestrel kickoff notes",
           "Notes from the Kestrel kickoff are in the shared drive if you want a template.", "2026-12-11T10:00:00.000Z"),
        ym("msg_0107", "cnv_n8", ("SaaStr Weekly", "newsletter@saastr.com"), "Net revenue retention benchmarks for 2027",
           "This week: NRR benchmarks, renewal playbooks and more.", "2026-12-12T07:00:00.000Z", category="newsletters"),
        ym("msg_0108", "cnv_n9", ("LinkedIn", "messages-noreply@linkedin.com"), "You appeared in 14 searches this week",
           "See who's looking at your profile.", "2026-12-13T08:00:00.000Z", category="social"),
        ym("msg_0109", "cnv_n10", ("Eurostar", "offers@eurostar.example.com"), "Winter fares to Paris from 39",
           "Book by Sunday.", "2026-12-12T09:00:00.000Z", category="offers"),
        ym("msg_0110", "cnv_n11", ("Acme IT", "it@acmecorp.com"), "Laptop OS update this weekend",
           "Please leave your laptop on and connected on Saturday night.", "2026-12-11T13:00:00.000Z"),
        ym("msg_0111", "cnv_n12", C("ben"), "QBR Wednesday",
           "Looking forward to Wednesday at 14:30. I'll bring our analytics lead.\n\nBen", "2026-12-11T12:30:00.000Z"),
        ym("msg_0112", "cnv_n13", C("fiona"), "Re: Driftwood renewal",
           "Hi Sarah, as discussed we're moving to in-house BI, so we won't renew. Thanks for everything.\n\nFiona",
           "2026-10-20T12:30:00.000Z", folder="archive"),
        ym("msg_0113", "cnv_n14", ("Gartner", "events@gartner.example.com"), "Data & Analytics Summit London",
           "Early-bird pricing ends soon.", "2026-12-08T09:00:00.000Z", category="newsletters"),
        ym("msg_0114", "cnv_n15", MARCUS, "Forecast review Tuesday",
           "Moving the EMEA forecast review to Tuesday 13:30-15:00 this week. Bring your Q4 renewal list.\n\nM",
           "2026-12-10T09:00:00.000Z"),
        ym("msg_0115", "cnv_n16", C("dana"), "Re: Fleet analytics demo",
           "Rob would love to see the fleet module in the new year.\n\nDana", "2026-11-27T11:00:00.000Z"),
    ]
    contacts = []
    for i, c in enumerate(list(CONTACTS.values())[:16]):
        contacts.append({"id": f"ct_{i + 1:04d}", "firstName": c[2], "lastName": c[3], "nickname": "",
                         "emails": [{"type": "work", "address": c[5]}], "phones": [], "addresses": [],
                         "company": ACCOUNTS[c[1]][1], "jobTitle": c[4], "birthday": "", "website": "", "notes": "",
                         "isFavorite": False, "avatarColor": "#5B8DB8", "source": "manual",
                         "createdAt": "2025-01-10T10:00:00.000Z", "updatedAt": None})
    for j, p in enumerate([MARCUS, ELENA, PRIYA, TOM]):
        f, l = p[0].split()
        contacts.append({"id": f"ct_{20 + j:04d}", "firstName": f, "lastName": l, "nickname": "",
                         "emails": [{"type": "work", "address": p[1]}], "phones": [], "addresses": [], "company": COMPANY,
                         "jobTitle": "", "birthday": "", "website": "", "notes": "", "isFavorite": True,
                         "avatarColor": "#7E57C2", "source": "manual", "createdAt": "2024-01-10T10:00:00.000Z", "updatedAt": None})
    fixed = "2024-01-10T10:00:00.000Z"
    folders = [{"id": fid, "name": ["Inbox", "Drafts", "Sent", "Archive", "Spam", "Trash"][i], "type": "system",
                "parentId": None, "order": i, "createdAt": fixed} for i, fid in enumerate(FOLDERS_SYS)]
    folders += [{"id": "fld_customers", "name": "Customers", "type": "user", "parentId": None, "order": 0, "createdAt": fixed, "updatedAt": None},
                {"id": "fld_internal", "name": "Acme internal", "type": "user", "parentId": None, "order": 1, "createdAt": fixed, "updatedAt": None}]
    return {
        "currentUser": {"id": "usr_sarah", "name": SARAH[0], "firstName": "Sarah", "email": SARAH[1],
                        "aliases": ["sarahchen.acme@yahoo.com"], "avatarColor": "#7E57C2", "jobTitle": "Senior Account Manager",
                        "company": COMPANY, "location": "London, UK", "storage": {"usedBytes": 2288490188, "totalBytes": 21474836480}},
        "folders": folders, "messages": msgs, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {"appearance": {"theme": "light", "themeColor": "purple", "density": "comfortable", "messageLayout": "list"},
                     "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
                     "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
                     "writing": {"signature": {"enabled": True, "text": "Sarah Chen\nSenior Account Manager - Acme Analytics\n+44 20 7946 0121"},
                                 "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": SARAH[1],
                                 "sendWithCtrlEnter": True, "linkPreviews": True},
                     "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "", "onlyContacts": False, "updatedAt": None},
                     "notifications": {"browser": False, "sound": False}, "ai": {"messageSummaries": False},
                     "keyboardShortcuts": True, "rightPanel": {"open": False, "tab": "starred"},
                     "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False}},
    }


# ---------------------------------------------------------------- google calendar
def gc_event(eid, title, start, end, *, cal="c1", guests=(), location="", description="", recurring="none", all_day=False):
    colors = {"c1": "#039BE5", "c2": "#33B679", "c3": "#8E24AA", "c4": "#F4511E", "c5": "#E67C73"}
    return {"id": eid, "calendarId": cal, "title": title, "start": start, "end": end, "allDay": all_day,
            "location": location, "description": description, "guests": list(guests), "color": colors[cal],
            "recurring": recurring, "reminders": [{"type": "popup", "minutes": 10}], "meetLink": "", "status": "confirmed"}


def build_calendar():
    Z = lambda d, t: f"2026-12-{d:02d}T{t}:00.000Z"  # noqa: E731  (UK time == UTC in December)
    ev = [
        gc_event("evt_101", "EMEA sales standup", Z(7, "09:30"), Z(7, "10:00"), cal="c2", recurring="weekly",
                 guests=[MARCUS[1], PRIYA[1], TOM[1]]),
        gc_event("evt_102", "Pipeline hygiene with Elena", Z(8, "11:00"), Z(8, "11:30"), guests=[ELENA[1]]),
        gc_event("evt_103", "Northwind - order form walkthrough", Z(2, "13:00"), Z(2, "13:30"), guests=["dana.whitfield@northwindlogistics.co.uk"]),
        gc_event("evt_104", "Bluepeak procurement call", Z(9, "16:00"), Z(9, "16:30"), guests=["alicia.gomez@bluepeakhealth.com"]),
        gc_event("evt_105", "Dentist", Z(10, "08:00"), Z(10, "09:00"), cal="c3"),
        gc_event("evt_106", "Harbor - legal redline call", Z(10, "14:00"), Z(10, "15:00"), guests=["liam.doyle@harborfreightways.co.uk"]),
        gc_event("evt_107", "EMEA Sales Kickoff - Barcelona", "2026-12-14T00:00:00.000Z", "2026-12-15T00:00:00.000Z",
                 cal="c2", all_day=True, location="Hotel Arts, Barcelona"),
        gc_event("evt_108", "Flight BA478 LHR -> BCN", Z(14, "06:55"), Z(14, "09:05"), cal="c3"),
        gc_event("evt_109", "Flight BA483 BCN -> LHR", Z(14, "18:40"), Z(14, "21:05"), cal="c3"),
        gc_event("evt_110", "1:1 Marcus / Sarah", Z(15, "10:00"), Z(15, "10:30"), guests=[MARCUS[1]]),
        gc_event("evt_111", "Forecast review - EMEA", Z(15, "13:30"), Z(15, "15:00"), cal="c2",
                 guests=[MARCUS[1], PRIYA[1], TOM[1], ELENA[1]], location="Thames room"),
        gc_event("evt_112", "FY27 Kickoff - Pinecrest Software", PINECREST_KICKOFF, "2026-12-15T15:30:00.000Z",
                 guests=["oskar.lind@pinecrest.se"], description="FY27 renewal kickoff"),
        gc_event("evt_113", "Lunch with Priya", Z(16, "12:00"), Z(16, "13:00"), cal="c3"),
        gc_event("evt_114", "QBR - Halcyon Media", Z(16, "14:30"), Z(16, "15:30"),
                 guests=["ben.achebe@halcyonmedia.co.uk", PRIYA[1]], location="Halcyon, Kings Cross"),
        gc_event("evt_115", "Deal desk office hours", Z(17, "09:00"), Z(17, "10:00"), cal="c2", guests=[ELENA[1]]),
        gc_event("evt_116", "Ferro renewal prep", Z(17, "13:00"), Z(17, "14:00")),
        gc_event("evt_117", "Expense report", Z(18, "09:00"), Z(18, "09:30"), cal="c3"),
        gc_event("evt_118", "Acme EMEA holiday lunch", Z(18, "12:00"), Z(18, "13:00"), cal="c2", location="Dishoom Shoreditch"),
        gc_event("evt_119", "Gym", Z(18, "17:30"), Z(18, "18:30"), cal="c3"),
        gc_event("evt_120", "Granite security review (Tom)", Z(21, "10:00"), Z(21, "11:00"), guests=[TOM[1]]),
        gc_event("evt_121", "Halcyon expansion follow-up", Z(22, "11:00"), Z(22, "11:30"), guests=["ben.achebe@halcyonmedia.co.uk"]),
        gc_event("evt_122", "Q1 territory planning", Z(22, "14:00"), Z(22, "15:30"), cal="c2", guests=[MARCUS[1]]),
        gc_event("evt_123", "Out of office", "2026-12-23T00:00:00.000Z", "2026-12-25T00:00:00.000Z", cal="c3", all_day=True),
        gc_event("evt_124", "Christmas Day", "2026-12-25T00:00:00.000Z", "2026-12-26T00:00:00.000Z", cal="c4", all_day=True),
        gc_event("evt_125", "Boxing Day", "2026-12-26T00:00:00.000Z", "2026-12-27T00:00:00.000Z", cal="c4", all_day=True),
        gc_event("evt_126", "Kestrel kickoff (Priya)", Z(9, "10:00"), Z(9, "10:30"), cal="c2", guests=[PRIYA[1]]),
        gc_event("evt_127", "Book club", Z(16, "19:00"), Z(16, "21:00"), cal="c3"),
        gc_event("evt_128", "Lakeside data platform sync", Z(4, "11:00"), Z(4, "11:30"), guests=["declan.murphy@lakesidecu.ie"]),
    ]
    return {
        "user": {"id": "u1", "username": SARAH[0], "email": SARAH[1], "avatar": avatar(SARAH[0])},
        "calendars": [{"id": "c1", "name": SARAH[0], "color": "#039BE5", "visible": True, "userId": "u1", "isDefault": True},
                      {"id": "c2", "name": "Acme EMEA Sales", "color": "#33B679", "visible": True, "userId": "u1", "isDefault": False},
                      {"id": "c3", "name": "Personal", "color": "#8E24AA", "visible": True, "userId": "u1", "isDefault": False},
                      {"id": "c4", "name": "UK Holidays", "color": "#F4511E", "visible": True, "userId": "u1", "isDefault": False}],
        "otherCalendars": [{"id": "oc1", "name": "Holidays in United Kingdom", "color": "#0B8043", "visible": False}],
        "events": ev, "view": "week", "currentDate": "2026-12-14T09:15:00.000Z", "sidebarOpen": True,
        "settings": {"weekStart": 1, "defaultDuration": 60, "defaultView": "week", "defaultReminder": {"type": "popup", "minutes": 10},
                     "timeFormat": "24h", "showWeekNumbers": False, "showDeclinedEvents": False},
    }


# ---------------------------------------------------------------- golden mutations
def apply_salesforce(sf, outcomes):
    for key, (stage, amount, close) in outcomes.items():
        oid = OPPS[key][0]
        o = next(x for x in sf["opportunities"] if x["opportunityId"] == oid)
        o.update({"stage": stage, "probability": PROB[stage], "amount": amount, "closeDate": close, "modifiedDate": NOW_Z})


def apply_docusign(ds, file_ids, void=VOID_ENVELOPE):
    by = {e["id"]: e for e in ds["envelopes"]}
    n = len(ds["auditLog"])
    for i, eid in enumerate(file_ids):
        by[eid]["folderId"] = FOLDER_FY27
        ds["auditLog"].insert(0, {"id": f"audit_g{n + i}", "timestamp": NOW_Z, "action": "MOVE_ENVELOPE",
                                  "details": f"Moved envelope {eid} to folder {FOLDER_FY27}", "envelopeId": eid})
    if void:
        eid, reason = void
        e = by[eid]
        e.update({"status": "voided", "voidedAt": NOW_Z, "lastActivityAt": NOW_Z})
        e["history"].append({"id": f"evt_{eid}_gv", "timestamp": NOW_Z, "action": "voided", "actorName": SARAH[0],
                             "actorEmail": SARAH[1], "details": f"Envelope voided: {reason}"})
        ds["auditLog"].insert(0, {"id": "audit_gv", "timestamp": NOW_Z, "action": "VOID_ENVELOPE",
                                  "details": f"Voided envelope {eid}: {reason}", "envelopeId": eid})


def apply_calendar(gc, kickoffs):
    for i, (key, (title, start, end, guests)) in enumerate(kickoffs.items()):
        gc["events"].append({"title": title, "start": start, "end": end, "allDay": False, "location": "", "description": "",
                             "calendarId": "c1", "guests": list(guests), "color": "bg-blue-500", "recurring": "none",
                             "reminders": [{"type": "popup", "minutes": 10}], "id": f"k{i}x9f2a7c1"})


def uk(start_iso):
    return start_iso[:10] + " " + start_iso[11:16] if start_iso else ""


def csv_rows(outcomes, kickoffs):
    rows = [CSV_HEADER]
    for key in CSV_OPPS:
        _, name, _, _, amount, close, stage, *_ = OPPS[key]
        if key in outcomes:
            stage, amount, close = outcomes[key]
        kick = kickoffs[key][1] if key in kickoffs else (PINECREST_KICKOFF if key == "pinecrest" else "")
        rows.append([name, stage, str(amount), close, uk(kick)])
    return rows


# ---------------------------------------------------------------- variants
def build_variant(seed, outcomes=OUTCOMES, kickoffs=KICKOFFS, file_ids=FILE_ENVELOPES, void=VOID_ENVELOPE):
    st = copy.deepcopy(seed)
    apply_salesforce(st["salesforce"], outcomes)
    apply_docusign(st["docusign"], file_ids, void)
    apply_calendar(st["google_calendar"], kickoffs)
    return st, csv_rows(outcomes, kickoffs)


def with_kick(key, start, end, guests=None):
    k = dict(KICKOFFS)
    k[key] = (k[key][0], start, end, guests if guests is not None else k[key][3])
    return k


def variants(seed):
    out = {}
    out["golden"] = build_variant(seed)
    out["nop"] = (copy.deepcopy(seed), None)
    # naive: trusts badges + first emails, ignores Marcus's amendment, takes TCV/old quote, books first-offered slots.
    naive_out = {
        "northwind": ("Closed Won", 96000, "2026-12-09"),
        "bluepeak": ("Closed Won", 57600, "2026-12-10"),
        "harbor": ("Closed Won", 74400, "2026-12-11"),
        "summitg": ("Closed Won", 27600, "2026-12-08"),
        "lakeside": ("Closed Won", 126000, "2026-12-11"),
    }
    naive_kick = {
        "northwind": ("FY27 Kickoff - Northwind Logistics", "2026-12-15T14:00:00.000Z", "2026-12-15T14:30:00.000Z", ["dana.whitfield@northwindlogistics.co.uk"]),
        "bluepeak": ("FY27 Kickoff - Bluepeak Health", "2026-12-17T10:00:00.000Z", "2026-12-17T10:30:00.000Z", ["jordan.pierce@bluepeakhealth.com"]),
        "harbor": ("FY27 Kickoff - Harbor Freightways", "2026-12-21T11:00:00.000Z", "2026-12-21T11:30:00.000Z", ["liam.doyle@harborfreightways.co.uk"]),
        "summitg": ("FY27 Kickoff - Summit Dental Group", "2026-12-18T13:30:00.000Z", "2026-12-18T14:00:00.000Z", ["megan.shaw@summitdentalgroup.co.uk"]),
        "lakeside": ("FY27 Kickoff - Lakeside Credit Union", "2026-12-16T15:00:00.000Z", "2026-12-16T15:30:00.000Z", ["aoife.brennan@lakesidecu.ie"]),
    }
    st, rows = build_variant(seed, naive_out, naive_kick, ["env_402", "env_403", "env_404", "env_406", "env_409"], None)
    out["naive"] = (st, rows)
    # Slips: careful runs that miss a workflow rule.
    out["slip_timezone"] = build_variant(seed, kickoffs=with_kick("bluepeak", "2026-12-17T10:00:00.000Z", "2026-12-17T10:45:00.000Z"))
    out["slip_reschedule"] = build_variant(seed, kickoffs=with_kick("summitg", "2026-12-18T13:30:00.000Z", "2026-12-18T14:15:00.000Z"))
    out["slip_conflict"] = build_variant(seed, kickoffs=with_kick("lakeside", "2026-12-16T15:00:00.000Z", "2026-12-16T15:45:00.000Z"))
    thirty = {k: (t, s, s[:11] + f"{int(s[11:13]) + (1 if s[14:16] == '30' else 0):02d}:{'00' if s[14:16] == '30' else '30'}:00.000Z",
                  [g for g in gs if g != MARCUS[1]]) for k, (t, s, e, gs) in KICKOFFS.items()}
    out["slip_amendment"] = build_variant(seed, kickoffs=thirty)
    # Salesforce errors and their corresponding downstream artifacts.
    harbor_out = dict(OUTCOMES, harbor=("Closed Won", 74400, "2026-12-11"))
    harbor_kick = dict(KICKOFFS, harbor=naive_kick["harbor"][:2] + ("2026-12-21T11:45:00.000Z", ["liam.doyle@harborfreightways.co.uk"]))
    out["slip_harbor"] = build_variant(seed, harbor_out, harbor_kick, FILE_ENVELOPES + ["env_404"])
    out["slip_tcv"] = build_variant(seed, dict(OUTCOMES, lakeside=("Closed Won", 126000, "2026-12-11")))
    return out


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def quotes_csv():
    rows = [["quote_number", "version", "account", "created_date", "status", "term_months", "seats",
             "annual_fee_usd", "total_contract_value_usd", "prepared_by"]]
    rows += [[q, v, a, d, s, t, n, f, tcv, p] for q, v, a, d, s, t, n, f, tcv, p in QUOTES]
    return rows


def expected():
    return {
        "clock": CLOCK, "timezone": TZ, "csv_name": CSV_NAME, "csv_header": CSV_HEADER,
        "outcomes": {OPPS[k][0]: {"name": OPPS[k][1], "stage": s, "amount": a, "closeDate": c} for k, (s, a, c) in OUTCOMES.items()},
        "untouched_opps": {OPPS[k][0]: OPPS[k][1] for k in UNTOUCHED_OPPS},
        "kickoffs": {k: {"account": ACCOUNTS[k][1], "title": t, "start": s, "end": e, "guests": g,
                         "signer": g[0]} for k, (t, s, e, g) in KICKOFFS.items()},
        "no_kickoff_accounts": {"harbor": ["Harbor Freightways", "liam.doyle@harborfreightways.co.uk"],
                                "cobalt": ["Cobalt Retail Group", "graham.holt@cobaltretail.co.uk", "hannah.price@cobaltretail.co.uk"],
                                "summitp": ["Summit Dental Partners", "ravi.mehta@summitdentalpartners.co.uk", "claire.summers@summitdentalpartners.co.uk"],
                                "pinecrest": ["Pinecrest Software", "oskar.lind@pinecrest.se"]},
        "marcus_email": MARCUS[1], "sarah_email": SARAH[1],
        "file_envelopes": FILE_ENVELOPES, "fy27_folder": FOLDER_FY27, "void_envelope": VOID_ENVELOPE[0],
        "protected_envelopes": ["env_401", "env_404", "env_407", "env_408", "env_410", "env_502", "env_504"],
        "csv_rows": csv_rows(OUTCOMES, KICKOFFS)[1:],
    }


def main(out: Path):
    seed = {"salesforce": build_salesforce(), "yahoo_mail": build_yahoo(), "google_calendar": build_calendar(),
            "docusign": build_docusign()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, rows = build_variant(seed)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / CSV_NAME, rows)
    write_csv(out / "input" / "cpq_quotes.csv", quotes_csv())
    write_json(out / "expected.json", expected())
    for name, (states, vrows) in variants(seed).items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if vrows:
            write_csv(out / "variants" / name / "output" / CSV_NAME, vrows)
        else:
            (out / "variants" / name / "output").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
