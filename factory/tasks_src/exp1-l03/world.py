#!/usr/bin/env python3
"""World for exp1-l03 / escalation-review-prep (Zendesk + Slack + Jira + local CSV).

Writes into <out>/:
  seed/{zendesk,slack,jira}.json       initial state per site
  golden/{zendesk,slack,jira}.json     state after a correct run
  golden_output/escalation_review.csv  correct CLI deliverable
  input/billing_accounts.csv           agent-visible workspace input
  expected.json                        hidden truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json, output/escalation_review.csv}

Story: Dana Whitfield leads support at Acme Fieldwork (field-service SaaS). Tomás, the
engineering manager, wants the real customer footprint of three Jira bugs for Friday's
escalation review. Lever L03 (hidden data): escalated tickets are marked only by the
"Engineering Escalations" group and a "Jira issue" custom field (collapsed under "Show
more", not searchable). 8 of the 17 target tickets are solved or on hold, so the default
"Your unsolved tickets" view shows almost none of them and solved ones never appear in
any unsolved view; the September ones sit at the bottom of ~70-row lists.
Secondary traps: FLD-431 superseded by FLD-447 in the Slack thread; a ticket whose Jira
field is stale (re-triaged 412 -> 398 in an internal note and a Jira comment); a merged
duplicate (closed); an Aug 31 23:40 PT ticket (outside the Sept 1 window); Zendesk org
"Brightline" whose billing account must be matched by email domain (Brightline Electric
vs Brightline Solar); two tickets from one account (distinct-account count).
"""

import copy
import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")
CLOCK = "2026-11-18T09:20:00-08:00"
RUN_TS = "2026-11-18T17:45:00.000Z"   # when the golden run's writes happen (UTC)
THRESHOLD = 150_000


def pt(s: str) -> str:
    """'2026-09-01 00:20' Pacific -> UTC ISO Z."""
    d = datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=PT)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def shift(iso: str, **kw) -> str:
    d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") + timedelta(**kw)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- billing / orgs
# account_id, billing name, billing_domain, plan, arr, status
BILLING = [
    ("ACC-1001", "Copperline Plumbing & Heating LLC", "copperline.com", "Business", 42000, "active"),
    ("ACC-1002", "Northwind Field Services", "northwindfs.com", "Enterprise", 84000, "active"),
    ("ACC-1003", "Northwind Facilities Group", "northwindfacilities.com", "Starter", 12000, "active"),
    ("ACC-1004", "Brightline Electric Co.", "brightline-electric.com", "Business", 36000, "active"),
    ("ACC-1005", "Summit Roofing", "summitroofing.co", "Business", 18000, "active"),
    ("ACC-1006", "Harbor HVAC Services Inc.", "harborhvac.com", "Business", 27500, "active"),
    ("ACC-1007", "Greenleaf Landscaping", "greenleaflandscape.com", "Starter", 9600, "active"),
    ("ACC-1008", "Pinecrest Pest Control", "pinecrestpest.com", "Business", 15000, "active"),
    ("ACC-1009", "Atlas Appliance Repair", "atlasappliance.com", "Business", 21000, "active"),
    ("ACC-1010", "Bluewater Pools & Spas", "bluewaterpools.com", "Business", 30000, "active"),
    ("ACC-1011", "Redwood Elevator Company", "redwoodelevator.com", "Enterprise", 66000, "active"),
    ("ACC-1012", "Keystone Security Systems", "keystonesecurity.com", "Enterprise", 48000, "active"),
    ("ACC-1013", "Meridian Facility Partners", "meridianfp.com", "Enterprise", 110000, "active"),
    ("ACC-1014", "Lakeside Cleaning Co", "lakesideclean.com", "Starter", 7200, "active"),
    ("ACC-1015", "Ironwood Garage Doors", "ironwooddoors.com", "Starter", 11400, "active"),
    ("ACC-1016", "Brightline Solar", "brightlinesolar.com", "Business", 54000, "active"),
    ("ACC-1017", "Cascade Fire Protection", "cascadefire.com", "Business", 39000, "active"),
    ("ACC-1018", "Oakridge Property Maintenance", "oakridgepm.com", "Business", 24000, "active"),
    ("ACC-1019", "Sunset Septic Service", "sunsetseptic.com", "Starter", 6000, "active"),
    ("ACC-1020", "Vantage Glass & Glazing", "vantageglass.com", "Business", 19800, "active"),
    ("ACC-1021", "Summit Roofing & Gutters", "summitgutters.com", "Starter", 0, "churned"),
    ("ACC-1022", "Clearview Window Cleaning", "clearviewwc.com", "Starter", 4800, "active"),
    ("ACC-1023", "Granite State Elevator", "granitestateelevator.com", "Business", 33000, "active"),
    ("ACC-1024", "Copper Canyon Electric", "coppercanyonelectric.com", "Business", 28000, "active"),
]
ACCOUNT_BY_DOMAIN = {b[2]: b for b in BILLING}

# Zendesk organizations: id, display name, domain, tags
ORGS = [
    (1, "Copperline Plumbing", "copperline.com", ["business"]),
    (2, "Northwind", "northwindfs.com", ["enterprise"]),
    (3, "Northwind Facilities", "northwindfacilities.com", ["starter"]),
    (4, "Brightline", "brightline-electric.com", ["business"]),
    (5, "Harbor HVAC", "harborhvac.com", ["business"]),
    (6, "Greenleaf Landscaping", "greenleaflandscape.com", ["starter"]),
    (7, "Pinecrest Pest Control", "pinecrestpest.com", ["business"]),
    (8, "Atlas Appliance Repair", "atlasappliance.com", ["business"]),
    (9, "Bluewater Pools", "bluewaterpools.com", ["business"]),
    (10, "Redwood Elevator", "redwoodelevator.com", ["enterprise", "key-account"]),
    (11, "Keystone Security", "keystonesecurity.com", ["enterprise"]),
    (12, "Meridian Facility Partners", "meridianfp.com", ["enterprise", "key-account"]),
    (13, "Lakeside Cleaning", "lakesideclean.com", ["starter"]),
    (14, "Ironwood Garage Doors", "ironwooddoors.com", ["starter"]),
    (15, "Brightline Solar", "brightlinesolar.com", ["business"]),
    (16, "Cascade Fire Protection", "cascadefire.com", ["business"]),
    (17, "Oakridge Property Maintenance", "oakridgepm.com", ["business"]),
    (18, "Sunset Septic", "sunsetseptic.com", ["starter"]),
    (19, "Vantage Glass", "vantageglass.com", ["business"]),
    (20, "Clearview Window Cleaning", "clearviewwc.com", ["starter"]),
    (21, "Granite State Elevator", "granitestateelevator.com", ["business"]),
]
ORG_BY_DOMAIN = {o[2]: o[0] for o in ORGS}

# ---------------------------------------------------------------- people
AGENTS = [
    # id, name, email, group, tz, initials
    (1, "Dana Whitfield", "dana.whitfield@acmefieldwork.com", 2, "America/Los_Angeles", "DW"),
    (2, "Marcus Bell", "marcus.bell@acmefieldwork.com", 1, "America/Chicago", "MB"),
    (3, "Hannah Cho", "hannah.cho@acmefieldwork.com", 1, "America/Los_Angeles", "HC"),
    (4, "Diego Ferraz", "diego.ferraz@acmefieldwork.com", 2, "America/Denver", "DF"),
    (5, "Wen Liu", "wen.liu@acmefieldwork.com", 4, "America/Los_Angeles", "WL"),
    (6, "Priya Raman", "priya.raman@acmefieldwork.com", 3, "America/New_York", "PR"),
]
DANA, MARCUS, HANNAH, DIEGO, WEN, PRIYA = 1, 2, 3, 4, 5, 6
T1G, T2G, BILLG, ENG = 1, 2, 3, 4

# End users: key -> (name, email). org derived from domain unless listed in NO_ORG.
END_USERS = {
    "gloria": ("Gloria Estevez", "gloria.estevez@meridianfp.com"),
    "sam": ("Sam Okoro", "sam.okoro@redwoodelevator.com"),
    "lisa": ("Lisa Tran", "lisa.tran@redwoodelevator.com"),
    "paul": ("Paul Henning", "paul.henning@redwoodelevator.com"),
    "mark": ("Mark Ruiz", "mruiz@keystonesecurity.com"),
    "jenna": ("Jenna Ali", "jenna.ali@keystonesecurity.com"),
    "tony": ("Tony Brandt", "tony@copperline.com"),
    "kayla": ("Kayla Moss", "kayla.moss@copperline.com"),
    "ben": ("Ben Ito", "ben.ito@atlasappliance.com"),
    "rosa": ("Rosa Delgado", "rosa@atlasappliance.com"),
    "erin": ("Erin Walsh", "erin.walsh@brightline-electric.com"),
    "victor": ("Victor Hale", "victor.hale@harborhvac.com"),
    "amy": ("Amy Chen", "office@harborhvac.com"),
    "jake": ("Jake Moreno", "jake@summitroofing.co"),
    "nadia": ("Nadia Petrov", "nadia.petrov@oakridgepm.com"),
    "owen": ("Owen Price", "owen.price@cascadefire.com"),
    "ruth": ("Ruth Adeyemi", "ruth@pinecrestpest.com"),
    "leo": ("Leo Marsh", "leo.marsh@vantageglass.com"),
    "maya": ("Maya Lindgren", "maya@greenleaflandscape.com"),
    "chris": ("Chris Novak", "chris.novak@bluewaterpools.com"),
    "dee": ("Dee Harmon", "dee@lakesideclean.com"),
    "frank": ("Frank Ilic", "frank.ilic@ironwooddoors.com"),
    "hal": ("Hal Burke", "hal@sunsetseptic.com"),
    "tara": ("Tara Singh", "tara.singh@brightlinesolar.com"),
    "grant": ("Grant Hollis", "grant.hollis@northwindfs.com"),
    "ivy": ("Ivy Chen", "ivy.chen@northwindfacilities.com"),
    # noise-only customers
    "rick": ("Rick Salazar", "rick.salazar@meridianfp.com"),
    "joan": ("Joan Whitaker", "joan@clearviewwc.com"),
    "eli": ("Eli Brooks", "eli.brooks@granitestateelevator.com"),
    "nora": ("Nora Kemp", "nora.kemp@keystonesecurity.com"),
    "sid": ("Sid Patel", "sid@pinecrestpest.com"),
    "tess": ("Tess Monroe", "tess.monroe@cascadefire.com"),
    "will": ("Will Carver", "will.carver@vantageglass.com"),
    "gabe": ("Gabe Ortiz", "gabe@greenleaflandscape.com"),
    "lena": ("Lena Fox", "lena.fox@oakridgepm.com"),
    "carl": ("Carl Jensen", "carl.jensen@northwindfs.com"),
    "abby": ("Abby Shore", "abby@bluewaterpools.com"),
    "matt": ("Matt Greer", "matt.greer@brightline-electric.com"),
    "zoe": ("Zoe Laurent", "zoe@summitroofing.co"),
    "ray": ("Ray Dunn", "ray.dunn@ironwooddoors.com"),
    "kim": ("Kim Baptiste", "kim.b@lakesideclean.com"),
    "hugo": ("Hugo Brandt", "hugo@copperline.com"),
    "pia": ("Pia Novak", "pia@redwoodelevator.com"),
    "dave": ("Dave Ostrowski", "dave.ostrowski@harborhvac.com"),
    "lola": ("Lola Grant", "lola@atlasappliance.com"),
    "ned": ("Ned Farrow", "ned@sunsetseptic.com"),
}
NO_ORG = {"jake", "zoe"}   # Summit Roofing never got a Zendesk organization
USER_IDS = {k: 101 + i for i, k in enumerate(END_USERS)}


def org_of(key):
    if key in NO_ORG:
        return None
    return ORG_BY_DOMAIN[END_USERS[key][1].split("@")[1]]


def account_of(key):
    return ACCOUNT_BY_DOMAIN[END_USERS[key][1].split("@")[1]]


# ---------------------------------------------------------------- escalated tickets
# Each spec: label, requester, subject, created (PT), status, assignee, jira field,
# area, version, tags, priority, final update (PT) and a conversation script.
# Conversation lines: (who, offset_hours, public, text); who = "req" or agent id.
REVIEW = ("FLD-412", "FLD-398", "FLD-447")

ESC = [
    # ---------------- FLD-412 recurring series duplicates
    dict(label="T1", who="gloria", subject="Edited our weekly PM series and now every visit shows up twice",
         created="2026-09-01 00:20", status="solved", assignee=DIEGO, jira="FLD-412", area="Scheduling",
         version="4.16.3", tags=["scheduling", "recurring-jobs"], priority="high", updated="2026-09-19 14:10",
         convo=[("req", 0, True, "We moved our weekly preventive-maintenance series for the Alder St. portfolio from Tuesdays to Wednesdays last night. This morning every visit through December is on the calendar twice, once on Tuesday and once on Wednesday, and both are assigned to techs."),
                (DIEGO, 7, True, "Thanks Gloria, I can reproduce this on a copy of your series. I'm getting this in front of our engineers today. In the meantime please don't delete the duplicates one by one, it can also drop the original visit."),
                (DIEGO, 8, False, "Escalating to Engineering. Repro: edit day-of-week on a series with > 20 future visits. Jira linked in the ticket fields."),
                (WEN, 120, True, "Hi Gloria, engineering gave us a safe cleanup: end the series on today's date and recreate it from tomorrow. I've done that for the Alder St. series with your OK from the call. The permanent fix is still in progress."),
                ("req", 400, True, "Calendar looks right now, thanks. Fine to close this one.")]),
    dict(label="T2", who="sam", subject="Duplicate maintenance visits on our elevator inspection contract",
         created="2026-09-15 08:45", status="hold", assignee=WEN, jira="FLD-412", area="Scheduling",
         version="4.16.3", tags=["scheduling", "recurring-jobs", "key-account"], priority="high", updated="2026-10-02 11:30",
         convo=[("req", 0, True, "Our monthly inspection series for 14 buildings doubled after we changed the time window. Techs are getting two jobs per building and our state inspection log is now wrong."),
                (DIEGO, 3, True, "Sorry Sam, that's the same series-edit problem a few customers have hit. I'm escalating it and will keep you posted."),
                (DIEGO, 4, False, "Escalating to Engineering, same pattern as the Meridian case. Jira linked in fields."),
                (WEN, 400, False, "Putting this on hold until the series-edit fix ships, Sam asked us not to touch the inspection series ourselves in the meantime.")]),
    dict(label="T3", who="mark", subject="Recurring jobs doubled after changing the technician on the series",
         created="2026-11-03 10:05", status="open", assignee=DANA, jira="FLD-412", area="Scheduling",
         version="4.18.1", tags=["scheduling", "recurring-jobs", "fld-412"], priority="high", updated="2026-11-16 15:20",
         convo=[("req", 0, True, "Reassigned the quarterly alarm-test series from Jorge to Priscilla and now both of them have every job. 60+ duplicates."),
                (DANA, 2, True, "Hi Mark, thanks for the detail. This looks like a known scheduling bug, I've raised it with engineering."),
                (DANA, 2.5, False, "Escalating to Engineering (series edit duplicates). Jira linked."),
                ("req", 300, True, "Any update? Our techs keep showing up together.")]),
    dict(label="T4", who="tony", subject="Weekly service series created double visits",
         created="2026-11-04 07:40", status="pending", assignee=DIEGO, jira="FLD-412", area="Scheduling",
         version="4.18.1", tags=["scheduling", "recurring-jobs", "fld-412"], priority="normal", updated="2026-11-12 09:00",
         convo=[("req", 0, True, "After I extended our weekly drain-service series to the end of the year, every Thursday has two visits."),
                (DIEGO, 4, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 190, True, "Hi Tony, could you tell us whether the duplicates are still being created for new weeks? Engineering wants to know if it stops after the first edit.")]),
    dict(label="T5", who="kayla", subject="Doubled appointments on our recurring maintenance plans",
         created="2026-11-10 13:15", status="open", assignee=WEN, jira="FLD-412", area="Scheduling",
         version="4.18.1", tags=["scheduling", "recurring-jobs"], priority="normal", updated="2026-11-17 10:40",
         convo=[("req", 0, True, "Hi, I'm the office manager at Copperline. Tony already wrote in about this but now it's happening on our residential plans too, any series we edit gets copied."),
                (MARCUS, 5, False, "Same bug as Tony's ticket, escalating to Engineering. Jira linked."),
                (WEN, 160, True, "Hi Kayla, the engineers have a fix in testing. Until then please avoid editing existing series; create a new one instead.")]),
    dict(label="T6", who="ben", subject="Series edit duplicated all our dryer-vent jobs",
         created="2026-10-07 09:30", status="solved", assignee=HANNAH, jira="FLD-412", area="Scheduling",
         version="4.17.2", tags=["scheduling", "recurring-jobs"], priority="normal", updated="2026-11-09 16:05",
         convo=[("req", 0, True, "We changed the duration on our recurring dryer-vent cleaning series and it made a second copy of every future job."),
                (HANNAH, 3, False, "Escalating to Engineering, looks like the series edit duplication. Jira linked."),
                (HANNAH, 50, True, "Ben, we've removed the duplicate copies from your calendar using the cleanup script engineering gave us. Please let us know if any reappear."),
                ("req", 800, True, "None came back, thanks. You can close it.")]),
    # ---------------- FLD-398 invoice PDF export timeouts
    dict(label="T7", who="erin", subject="Invoice PDF export spins and then fails for our commercial job",
         created="2026-11-12 11:20", status="open", assignee=DIEGO, jira="FLD-398", area="Invoicing",
         version="4.18.1", tags=["invoicing", "pdf-export"], priority="high", updated="2026-11-17 13:30",
         convo=[("req", 0, True, "The invoice for the hospital rewire has 260 line items. Every time we click Export PDF it spins for a minute and shows 'Something went wrong'. The customer needs it for their AP run Friday."),
                (DIEGO, 2, False, "Escalating to Engineering, invoice PDF timeout with 260 lines. Jira linked."),
                (DIEGO, 3, True, "Hi Erin, I've passed this to our engineers. As a stopgap, the CSV export works for large invoices if their AP team can take that.")]),
    dict(label="T8", who="victor", subject="Can't export big invoices to PDF",
         created="2026-09-22 14:00", status="solved", assignee=DIEGO, jira="FLD-398", area="Invoicing",
         version="4.16.3", tags=["invoicing", "pdf-export"], priority="normal", updated="2026-10-06 10:15",
         convo=[("req", 0, True, "Our monthly maintenance-agreement invoices (300+ lines) won't export to PDF anymore, they time out."),
                (DIEGO, 4, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 30, True, "Victor, while engineering works on it: splitting the invoice into two by agreement group exports fine. I've split September's for you."),
                ("req", 300, True, "That works for now. Thanks Diego.")]),
    dict(label="T9", who="jake", subject="PDF of invoice times out",
         created="2026-10-02 08:10", status="hold", assignee=WEN, jira="FLD-398", area="Invoicing",
         version="4.17.2", tags=["invoicing", "pdf-export"], priority="normal", updated="2026-10-20 12:00",
         convo=[("req", 0, True, "Trying to send the PDF invoice for the Hillcrest reroof. 240 lines, it never finishes."),
                (HANNAH, 2, False, "Escalating to Engineering, PDF timeout. Jira linked."),
                (WEN, 430, False, "On hold until the PDF export fix lands. Jake is OK sending the CSV meanwhile.")]),
    dict(label="T10", who="nadia", subject="Visits showing twice and the invoice for them won't export",
         created="2026-10-20 09:50", status="open", assignee=WEN, jira="FLD-412", area="Scheduling",
         version="4.17.2", tags=["scheduling", "invoicing"], priority="high", updated="2026-11-13 09:30",
         convo=[("req", 0, True, "For our biggest HOA client the October visits look doubled on the job list, and the monthly invoice for them (around 410 lines) fails when we export it to PDF."),
                (DIEGO, 3, False, "Escalating to Engineering, looks like the series duplication. Jira linked."),
                (WEN, 170, False, "Looked at this with Karthik. There are no duplicated visits: their office copied the jobs by hand. The real problem is the 410-line invoice timing out on PDF export, so this belongs to FLD-398, not FLD-412. I've linked it on FLD-398 in Jira; the Jira field here is still the old one, I can't edit it."),
                (WEN, 172, True, "Hi Nadia, thanks for your patience. The doubled visits were manual copies, which we've cleaned up. The PDF export failure is a known issue that engineering is fixing; meanwhile CSV export works.")]),
    dict(label="T11", who="owen", subject="Inspection invoices fail to generate as PDF",
         created="2026-10-08 15:35", status="solved", assignee=MARCUS, jira="FLD-398", area="Invoicing",
         version="4.17.2", tags=["invoicing", "pdf-export"], priority="normal", updated="2026-10-29 10:45",
         convo=[("req", 0, True, "Our annual sprinkler-inspection invoices list every head as a line, so 220 to 500 lines. None of them export to PDF."),
                (MARCUS, 2, False, "Escalating to Engineering. Jira linked."),
                (MARCUS, 26, True, "Owen, a workaround until the fix: use the 'summarize by location' invoice template, it exports fine."),
                ("req", 400, True, "Summarized template is fine for our clients. Thanks!")]),
    # ---------------- FLD-447 offline signature queue after 4.18
    dict(label="T12", who="ruth", subject="Technician signatures missing after the app update",
         created="2026-11-09 07:55", status="open", assignee=DANA, jira="FLD-447", area="Mobile",
         version="4.18.1", tags=["mobile", "signatures", "offline"], priority="high", updated="2026-11-17 08:30",
         convo=[("req", 0, True, "Since our techs updated the app last week, customer signatures captured in basements (no signal) don't show up on the work order once they're back online."),
                (DANA, 2, False, "Escalating to Engineering. 4.18.1, offline capture. Jira linked."),
                (DANA, 3, True, "Thanks Ruth, engineering is on it. Please ask techs not to log out of the app until the queue clears.")]),
    dict(label="T13", who="lisa", subject="Signed work orders lose the signature when synced later",
         created="2026-10-28 12:30", status="pending", assignee=DIEGO, jira="FLD-447", area="Mobile",
         version="4.18.0", tags=["mobile", "signatures", "offline"], priority="high", updated="2026-11-11 15:00",
         convo=[("req", 0, True, "After 4.18, signatures from machine rooms without coverage disappear when the phone syncs. We need signed records for compliance."),
                (DIEGO, 3, False, "Escalating to Engineering. New since 4.18. Jira linked."),
                (DIEGO, 200, True, "Hi Lisa, could you send us the device model and OS version of the two techs affected most? Engineering asked for it.")]),
    dict(label="T14", who="paul", subject="Offline signatures not syncing (Redwood dispatch)",
         created="2026-11-16 06:40", status="new", assignee=None, jira="FLD-447", area="Mobile",
         version="4.18.1", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-11-16 10:05",
         convo=[("req", 0, True, "Our dispatch team sees work orders marked signed with no signature image. Lisa reported this already for the north region; now it's the south crews too."),
                (WEN, 3, False, "Same as Lisa's ticket, routing to Engineering. Jira linked.")]),
    dict(label="T15", who="jenna", subject="Customer signatures dropped from completed jobs",
         created="2026-10-23 10:10", status="solved", assignee=HANNAH, jira="FLD-447", area="Mobile",
         version="4.18.0", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-11-05 11:20",
         convo=[("req", 0, True, "Several jobs completed in parking garages lost their signatures after the update."),
                (HANNAH, 2, False, "Escalating to Engineering. Jira linked."),
                (HANNAH, 60, True, "Jenna, we recovered the 9 missing signatures from the device logs and re-attached them. Engineering is still fixing the root cause."),
                ("req", 300, True, "All 9 are back, thank you. Closing from our side.")]),
    dict(label="T16", who="leo", subject="Signature capture lost offline on iPad",
         created="2026-11-02 14:25", status="hold", assignee=WEN, jira="FLD-447", area="Mobile",
         version="4.18.1", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-11-10 09:00",
         convo=[("req", 0, True, "Our glaziers use iPads on high-rise jobs with no signal. Since 4.18 the signature is gone when the iPad reconnects."),
                (MARCUS, 4, False, "Escalating to Engineering. Jira linked."),
                (WEN, 160, False, "On hold until the offline queue fix ships. Leo's crews are capturing paper sign-offs for now.")]),
    dict(label="T17", who="maya", subject="Signatures not saving when crew is out of range",
         created="2026-10-26 08:00", status="open", assignee=MARCUS, jira="FLD-447", area="Mobile",
         version="4.18.0", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-11-14 12:15",
         convo=[("req", 0, True, "Crews out at rural properties have no signal. The signature shows on the phone but never reaches the office after they get back."),
                (MARCUS, 3, False, "Escalating to Engineering. Jira linked."),
                (MARCUS, 450, True, "Hi Maya, still being worked on by engineering. I'll update you as soon as there's a fix date.")]),
    # ---------------- escalated but NOT on the review list
    dict(label="X_merged", who="amy", subject="Invoice PDF won't download",
         created="2026-09-23 09:15", status="closed", assignee=DIEGO, jira="FLD-398", area="Invoicing",
         version="4.16.3", tags=["invoicing", "pdf-export"], priority="normal", updated="2026-09-24 10:00",
         convo=[("req", 0, True, "Hi, office here at Harbor HVAC. The PDF for our big monthly invoice just times out."),
                (DIEGO, 2, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 24.75, False, "MERGE_NOTE")]),
    dict(label="X_boundary", who="chris", subject="Pool route invoice PDF export failing",
         created="2026-08-31 23:40", status="solved", assignee=MARCUS, jira="FLD-398", area="Invoicing",
         version="4.16.2", tags=["invoicing", "pdf-export"], priority="normal", updated="2026-09-16 13:00",
         convo=[("req", 0, True, "Our end-of-month route invoice (280 stops) won't export to PDF. It's the last day of the month and we need it out tonight."),
                (MARCUS, 9, False, "Escalating to Engineering. Jira linked."),
                (MARCUS, 10, True, "Chris, as a workaround you can split by route day; I've split August for you."),
                ("req", 200, True, "Got it out, thanks.")]),
    dict(label="X_431a", who="dee", subject="Signatures lost after working offline (iPhone)",
         created="2026-09-09 10:00", status="solved", assignee=HANNAH, jira="FLD-431", area="Mobile",
         version="4.17.0", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-10-21 09:30",
         convo=[("req", 0, True, "Our cleaners' iPhones drop the customer signature if they were offline at the time."),
                (HANNAH, 2, False, "Escalating to Engineering. Jira linked."),
                (HANNAH, 1000, True, "Dee, the fix shipped in app version 4.18. Please have your team update and let us know if it happens again.")]),
    dict(label="X_431b", who="frank", subject="iOS app not keeping signatures offline",
         created="2026-09-28 13:45", status="solved", assignee=DIEGO, jira="FLD-431", area="Mobile",
         version="4.17.1", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-10-22 08:45",
         convo=[("req", 0, True, "Signatures vanish when our installers sync after a job in a dead zone."),
                (DIEGO, 3, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 570, True, "Frank, fixed in 4.18, which is in the App Store now.")]),
    dict(label="X_431c", who="rosa", subject="Signature image blank on synced work orders",
         created="2026-10-12 11:00", status="solved", assignee=HANNAH, jira="FLD-431", area="Mobile",
         version="4.17.2", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-10-23 10:00",
         convo=[("req", 0, True, "Some synced work orders show a blank signature box."),
                (HANNAH, 2, False, "Escalating to Engineering. Jira linked."),
                (HANNAH, 260, True, "Rosa, this was fixed in 4.18. Updating the app on your techs' phones resolves it.")]),
    dict(label="X_431d", who="abby", subject="Signatures missing on service tickets from the field",
         created="2026-10-15 09:20", status="pending", assignee=DIEGO, jira="FLD-431", area="Mobile",
         version="4.17.2", tags=["mobile", "signatures", "offline"], priority="normal", updated="2026-11-06 14:00",
         convo=[("req", 0, True, "Our pool techs' signatures don't come through when they were offline."),
                (DIEGO, 2, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 520, True, "Hi Abby, the fix is in 4.18. Your techs are still on 4.17.2 per our logs; could you confirm once they've updated?")]),
    dict(label="X_aug412", who="hal", subject="Recurring pump-out series made duplicate jobs",
         created="2026-08-14 10:30", status="solved", assignee=DIEGO, jira="FLD-412", area="Scheduling",
         version="4.16.2", tags=["scheduling", "recurring-jobs"], priority="normal", updated="2026-08-28 15:00",
         convo=[("req", 0, True, "Edited our quarterly pump-out series and got two of every job."),
                (DIEGO, 4, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 100, True, "Hal, cleaned up the duplicates for you. Engineering is working on the underlying bug.")]),
    dict(label="X_405a", who="will", subject="Map view tiles blank in Safari",
         created="2026-11-05 09:00", status="open", assignee=WEN, jira="FLD-405", area="Dispatch",
         version="4.18.1", tags=["dispatch", "map"], priority="normal", updated="2026-11-13 11:00",
         convo=[("req", 0, True, "The dispatch map is just grey squares in Safari on our office Macs."),
                (MARCUS, 3, False, "Escalating to Engineering. Jira linked.")]),
    dict(label="X_405b", who="gabe", subject="Dispatch map doesn't load on Mac",
         created="2026-09-10 14:00", status="solved", assignee=MARCUS, jira="FLD-405", area="Dispatch",
         version="4.17.0", tags=["dispatch", "map"], priority="low", updated="2026-09-12 10:00",
         convo=[("req", 0, True, "Map tiles never load in Safari."),
                (MARCUS, 2, False, "Escalating to Engineering. Jira linked."),
                (MARCUS, 40, True, "Gabe, Chrome works fine as a workaround while engineering looks at Safari.")]),
    dict(label="X_422a", who="tess", subject="QuickBooks sync rounding tax by a cent",
         created="2026-10-30 10:30", status="pending", assignee=PRIYA, jira="FLD-422", area="Integrations",
         version="4.18.0", tags=["quickbooks", "integration"], priority="normal", updated="2026-11-12 16:00",
         convo=[("req", 0, True, "Invoices synced to QuickBooks are off by $0.01 on tax for multi-rate jobs."),
                (PRIYA, 3, False, "Escalating to Engineering. Jira linked."),
                (PRIYA, 300, True, "Tess, can you share two invoice numbers where it happened in November?")]),
    dict(label="X_422b", who="sid", subject="Tax totals differ between Fieldwork and QuickBooks",
         created="2026-09-18 12:00", status="solved", assignee=PRIYA, jira="FLD-422", area="Integrations",
         version="4.17.0", tags=["quickbooks", "integration"], priority="low", updated="2026-10-02 09:00",
         convo=[("req", 0, True, "Our QuickBooks tax totals are a cent off from Fieldwork on some invoices."),
                (PRIYA, 2, False, "Escalating to Engineering. Jira linked."),
                (PRIYA, 330, True, "Sid, we adjusted the two affected invoices manually. The rounding fix is scheduled.")]),
    dict(label="X_388", who="hugo", subject="Estimate approval link returns 404",
         created="2026-07-14 09:00", status="solved", assignee=DIEGO, jira="FLD-388", area="Estimates",
         version="4.15.4", tags=["estimates"], priority="normal", updated="2026-07-20 10:00",
         convo=[("req", 0, True, "Customers clicking 'Approve estimate' in the email get a 404."),
                (DIEGO, 2, False, "Escalating to Engineering. Jira linked."),
                (DIEGO, 140, True, "Hugo, fixed in 4.15.5. Links work again.")]),
]

# Tickets that look like the bugs but were never escalated (Tier 1/2, no Jira field).
LOOKALIKES = [
    dict(label="L_dup", who="kim", subject="Recurring visits doubled on our calendar", created="2026-10-30 08:30",
         status="solved", assignee=HANNAH, group=T1G, area="Scheduling", version="4.18.0",
         tags=["scheduling", "recurring-jobs"], priority="normal", updated="2026-10-31 09:00",
         convo=[("req", 0, True, "All our recurring cleanings show twice this week."),
                (HANNAH, 3, True, "Hi Kim, you have two overlapping series for the same customers (one created in August, one in October). I've ended the older one, so the calendar shows each visit once now."),
                ("req", 20, True, "Oh, that was us. Thanks!")]),
    dict(label="L_pdf", who="matt", subject="Invoice PDF won't generate", created="2026-11-06 13:00",
         status="solved", assignee=MARCUS, group=T1G, area="Invoicing", version="4.18.1",
         tags=["invoicing", "pdf-export"], priority="normal", updated="2026-11-07 10:00",
         convo=[("req", 0, True, "Export PDF on a 12-line invoice fails with an error."),
                (MARCUS, 4, True, "Hi Matt, your company logo link had expired, which breaks the PDF template. I re-uploaded the logo from your settings and the export works now."),
                ("req", 20, True, "Confirmed, thanks.")]),
    dict(label="L_sig", who="ray", subject="Signature pad not showing on Android", created="2026-11-11 10:15",
         status="open", assignee=HANNAH, group=T1G, area="Mobile", version="4.18.1",
         tags=["mobile", "signatures"], priority="normal", updated="2026-11-17 09:10",
         convo=[("req", 0, True, "One of our techs doesn't get the signature pad at all on his Android phone."),
                (HANNAH, 5, True, "Ray, signature capture is turned off for that technician's role. You can enable it under Settings > Roles > Field Tech.")]),
    dict(label="L_dup2", who="ned", subject="Same job appearing twice for one tech", created="2026-09-03 11:00",
         status="solved", assignee=MARCUS, group=T1G, area="Scheduling", version="4.17.0",
         tags=["scheduling"], priority="low", updated="2026-09-04 08:00",
         convo=[("req", 0, True, "A job shows twice in one technician's day."),
                (MARCUS, 3, True, "Ned, the job had the same tech added as both lead and helper. I removed the helper entry."),
                ("req", 16, True, "Thanks.")]),
]

# ---------------------------------------------------------------- noise tickets
NOISE_SUBJECTS = {
    T1G: [
        ("How do I add another technician seat?", "Account", "question"),
        ("Customer portal link expired for a client", "Customer portal", "question"),
        ("Change the logo on our estimates", "Estimates", "question"),
        ("Dispatcher locked out after password reset", "Account", "problem"),
        ("Export timesheets to CSV for payroll", "Timesheets", "question"),
        ("Technician can't see today's jobs on the app", "Mobile", "problem"),
        ("Appointment reminder texts going out an hour early", "Notifications", "problem"),
        ("Add a custom field to work orders", "Work orders", "question"),
        ("Calendar color coding by job type", "Scheduling", "question"),
        ("Move a job to another technician", "Scheduling", "question"),
        ("Price book import template", "Price book", "question"),
        ("Estimate approval email not received by customer", "Estimates", "problem"),
        ("Duplicate customer records after CSV import", "Customers", "problem"),
        ("Map pin shows the wrong address", "Dispatch", "problem"),
        ("Two-factor code not arriving by SMS", "Account", "problem"),
        ("How to set up a service agreement renewal", "Agreements", "question"),
        ("Can techs see job notes offline?", "Mobile", "question"),
        ("Booking widget on our website", "Online booking", "question"),
        ("Change company time zone", "Account", "question"),
        ("Tags not showing on the job board", "Dispatch", "problem"),
    ],
    T2G: [
        ("Webhook to our CRM stopped firing", "Integrations", "problem"),
        ("429 errors from the /jobs API endpoint", "API", "problem"),
        ("QuickBooks customer sync skipped some records", "Integrations", "problem"),
        ("GPS breadcrumbs have gaps on Android", "Mobile", "problem"),
        ("Revenue report totals don't match invoices", "Reporting", "problem"),
        ("Inventory counts wrong after truck transfer", "Inventory", "problem"),
        ("SSO login loop with Okta", "Account", "problem"),
        ("Zapier trigger missing new estimates", "Integrations", "problem"),
        ("Bulk job import fails at row 500", "Work orders", "problem"),
        ("Custom report builder timing out", "Reporting", "problem"),
    ],
    BILLG: [
        ("October invoice for seats looks too high", "Billing", "question"),
        ("Update the card on file", "Billing", "task"),
        ("Switch us to annual billing", "Billing", "task"),
        ("Refund for seats we removed", "Billing", "question"),
        ("Need a W-9 for our vendor setup", "Billing", "task"),
        ("Mark our account tax exempt", "Billing", "task"),
        ("Receipt for last payment", "Billing", "question"),
    ],
}
NOISE_CUSTOMERS = [k for k in END_USERS]
NOISE_AGENTS = {T1G: [MARCUS, HANNAH, DANA], T2G: [DIEGO, DANA], BILLG: [PRIYA]}


def noise_specs():
    rng = random.Random(20261118)
    start = datetime(2026, 7, 6, 8, 0, tzinfo=PT)
    end = datetime(2026, 11, 18, 8, 30, tzinfo=PT)
    specs = []
    n = 110
    for i in range(n):
        frac = (i + rng.random() * 0.6) / n
        created = start + (end - start) * (frac ** 0.8)
        created = created.replace(minute=rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]))
        group = rng.choices([T1G, T2G, BILLG], weights=[6, 3, 2])[0]
        subj, area, typ = rng.choice(NOISE_SUBJECTS[group])
        who = rng.choice(NOISE_CUSTOMERS)
        age = (end - created).days
        if age > 45:
            status = rng.choices(["solved", "closed"], weights=[3, 2])[0]
        elif age > 14:
            status = rng.choices(["solved", "pending", "open", "hold"], weights=[6, 2, 2, 1])[0]
        else:
            status = rng.choices(["open", "pending", "new", "solved"], weights=[5, 3, 2, 3])[0]
        assignee = None if status == "new" else rng.choice(NOISE_AGENTS[group])
        cap = datetime(2026, 11, 18, 9, 5, tzinfo=PT)
        if status in ("solved", "closed"):
            upd = created + timedelta(hours=rng.randint(6, 240))
        else:
            upd = created + timedelta(hours=rng.randint(2, 200))
        upd = max(created + timedelta(minutes=20), min(cap, upd))
        specs.append(dict(label=f"N{i:03d}", who=who, subject=subj, created=created.strftime("%Y-%m-%d %H:%M"),
                          status=status, assignee=assignee, group=group, area=area, type=typ,
                          version=rng.choice(["4.16.3", "4.17.2", "4.18.0", "4.18.1"]) if created.month >= 9 else "4.16.2",
                          tags=[area.lower().replace(" ", "-")], priority=rng.choices(["low", "normal", "high"], weights=[2, 6, 1])[0],
                          updated=upd.strftime("%Y-%m-%d %H:%M"), noise=True))
    return specs


# Escalation notes are phrased differently by each agent, so no single search phrase lists
# every escalated ticket (search covers comment bodies).
ESC_PHRASES = [
    ("Escalating to Engineering.", "Jira linked."),
    ("Sending this over to the platform team.", "Key is in the ticket fields."),
    ("Moved to Eng Escalations.", ""),
    ("Raised with the dev team.", "Field set."),
    ("Handing off to the platform bug queue.", "Linked the bug in the sidebar."),
    ("Routing to eng.", ""),
]


def rephrase(text, n):
    for lead in ("Escalating to Engineering", "Same bug as Tony's ticket, escalating to Engineering",
                 "Same as Lisa's ticket, routing to Engineering"):
        if text.startswith(lead):
            head, tail = ESC_PHRASES[n % len(ESC_PHRASES)]
            rest = text[len(lead):].lstrip(".,").strip()
            rest = rest.replace("Jira linked in fields.", "").replace("Jira linked in the ticket fields.", "").replace("Jira linked.", "").strip()
            prefix = {"Same bug as Tony's ticket": "Same bug as Tony's ticket. ", "Same as Lisa's ticket": "Same as Lisa's ticket. "}
            pre = next((v for k, v in prefix.items() if lead.startswith(k)), "")
            rest = rest[:1].upper() + rest[1:]
            return " ".join(x for x in (pre + head, rest, tail) if x)
    return text


NOISE_BODIES = {
    "question": ("Hi team, quick question: {s}. Thanks!", "Hi {first}, here's how: open Settings and look under {area}. I've added a help-center link below as well."),
    "problem": ("Hello, we're having an issue: {s}. Can you take a look?", "Thanks {first}, I'm looking into this now and will follow up shortly."),
    "problem_eng": ("Hello, we're having an issue: {s}. Can you take a look?", "Thanks {first}, I checked with our engineering team: this is a configuration issue on our side, not a bug. I've corrected it, please try again."),
    "task": ("Hi, could you help with this: {s}?", "Hi {first}, done. Let me know if anything else is needed."),
}


# ---------------------------------------------------------------- zendesk build
def build_zendesk():
    users = []
    for aid, name, em, grp, tz, ini in AGENTS:
        users.append({"id": aid, "name": name, "email": em, "role": "agent", "phone": f"+1-555-02{aid:02d}",
                      "photo": avatar(name), "organization_id": None, "group_id": grp, "time_zone": tz,
                      "locale": "en-US", "signature": f"Thanks,\n{name.split()[0]}\nAcme Fieldwork Support",
                      "notes": "", "suspended": False, "verified": True, "active": True,
                      "created_at": "2024-02-01T17:00:00Z", "updated_at": "2026-11-10T17:00:00Z",
                      "last_login_at": "2026-11-18T16:50:00Z", "initials": ini})
    for key, (name, em) in END_USERS.items():
        uid = USER_IDS[key]
        users.append({"id": uid, "name": name, "email": em, "role": "end-user", "phone": f"+1-555-{3000 + uid}",
                      "photo": avatar(name), "organization_id": org_of(key), "group_id": None,
                      "time_zone": "America/Los_Angeles", "locale": "en-US", "signature": "", "notes": "",
                      "suspended": False, "verified": True, "active": True,
                      "created_at": "2025-03-10T17:00:00Z", "updated_at": "2026-10-01T17:00:00Z",
                      "last_login_at": "2026-11-15T17:00:00Z",
                      "initials": "".join(p[0] for p in name.split()[:2]).upper()})
    orgs = []
    for oid, name, dom, tags in ORGS:
        orgs.append({"id": oid, "name": name, "domain_names": [dom], "details": "Acme Fieldwork customer",
                     "notes": "", "group_id": T1G, "shared_tickets": False, "shared_comments": False,
                     "tags": tags, "created_at": "2025-01-15T17:00:00Z", "updated_at": "2026-09-01T17:00:00Z"})
    groups = [
        {"id": T1G, "name": "Tier 1 Support", "description": "Front-line support", "default": True},
        {"id": T2G, "name": "Tier 2 Support", "description": "Technical issues and integrations", "default": False},
        {"id": BILLG, "name": "Billing", "description": "Subscriptions, invoices and payments", "default": False},
        {"id": ENG, "name": "Engineering Escalations", "description": "Tickets escalated to the Fieldwork Platform engineering team (Jira)", "default": False},
    ]
    for g in groups:
        g.update({"created_at": "2024-01-01T17:00:00Z", "updated_at": "2026-06-01T17:00:00Z"})

    specs = []
    for s in ESC:
        specs.append({**s, "group": ENG, "type": "problem" if s["status"] != "hold" else "incident"})
    for s in LOOKALIKES:
        specs.append({**s, "type": "problem"})
    specs.extend(noise_specs())
    specs.sort(key=lambda s: (pt(s["created"]), s["label"]))

    ids = {}
    for i, s in enumerate(specs):
        ids[s["label"]] = 3101 + i

    tickets, comments = [], {}
    cid = 900001
    for s in specs:
        tid = ids[s["label"]]
        key = s["who"]
        req = USER_IDS[key]
        created = pt(s["created"])
        updated = pt(s["updated"])
        first = END_USERS[key][0].split()[0]
        convo = s.get("convo")
        if convo is None:
            q, a = NOISE_BODIES["problem_eng" if s["type"] == "problem" and tid % 4 == 1 else s["type"]]
            span = (datetime.fromisoformat(updated.replace("Z", "+00:00")) - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 3600
            convo = [("req", 0, True, q.format(s=s["subject"][0].lower() + s["subject"][1:], first=first, area=s["area"]))]
            if s["status"] != "new" and s["assignee"]:
                convo.append((s["assignee"], span * 0.3, True, a.format(first=first, area=s["area"])))
            if s["status"] in ("solved", "closed") and s["assignee"]:
                convo.append(("req", span, True, "That sorted it, thanks."))
        clist = []
        esc_n = 0
        for who, off, public, text in convo:
            if s.get("jira") and not public:
                new = rephrase(text, tid + esc_n)
                if new != text:
                    esc_n += 1
                text = new
            if text == "MERGE_NOTE":
                text = f"This ticket was merged into #{ids['T8']}."
            author = req if who == "req" else who
            ts = shift(created, minutes=int(off * 60))
            clist.append({"id": cid, "ticket_id": tid, "author_id": author, "body": text,
                          "html_body": "<p>" + text.replace("\n", "<br>") + "</p>", "public": public,
                          "type": "Comment", "attachments": [], "created_at": ts})
            cid += 1
        if s["label"] == "T8":
            ts = pt("2026-09-24 10:00")
            text = f"Merged tickets #{ids['X_merged']} into this ticket."
            clist.append({"id": cid, "ticket_id": tid, "author_id": DIEGO, "body": text, "html_body": f"<p>{text}</p>",
                          "public": False, "type": "Comment", "attachments": [], "created_at": ts})
            cid += 1
        clist.sort(key=lambda c: c["created_at"])
        comments[str(tid)] = clist
        fields = [{"id": "product_area", "title": "Product area", "value": s["area"]},
                  {"id": "app_version", "title": "App version", "value": s["version"]}]
        if s.get("jira"):
            fields.append({"id": "jira_issue", "title": "Jira issue", "value": s["jira"]})
        last = max(updated, clist[-1]["created_at"])
        agent_replies = [c for c in clist if c["author_id"] <= 6 and c["public"]]
        tickets.append({
            "id": tid, "subject": s["subject"], "description": clist[0]["body"], "status": s["status"],
            "type": s.get("type", "problem"), "priority": s["priority"], "requester_id": req, "submitter_id": req,
            "assignee_id": s["assignee"], "group_id": s["group"], "organization_id": org_of(key),
            "collaborator_ids": [], "follower_ids": [WEN] if s["group"] == ENG and s["status"] not in ("solved", "closed") else [],
            "tags": list(s["tags"]), "via": {"channel": "email" if tid % 3 else "web"},
            "satisfaction_rating": {"score": "good", "comment": ""} if s["status"] == "solved" and tid % 4 == 0 else None,
            "due_at": None, "is_public": True, "custom_fields": fields,
            "created_at": created, "updated_at": last, "comment_count": len(clist),
            "sla": {"first_reply_at": agent_replies[0]["created_at"] if agent_replies else None,
                    "next_reply_due": shift(last, hours=24) if s["status"] in ("new", "open") else None,
                    "breached": False},
        })
    tickets.sort(key=lambda t: t["id"])

    def view(vid, title, all_, typ="standard", any_=()):
        return {"id": vid, "title": title, "description": title, "active": True, "position": vid - 1,
                "type": typ, "conditions": {"all": list(all_), "any": list(any_)}}

    unsolved = {"field": "status", "operator": "less_than", "value": "solved"}
    views = [
        view(1, "Your unsolved tickets", [{"field": "assignee_id", "operator": "is", "value": "current_user"}, unsolved]),
        view(2, "Unassigned tickets", [{"field": "assignee_id", "operator": "is", "value": None}, unsolved]),
        view(3, "All unsolved tickets", [unsolved]),
        view(4, "Recently updated tickets", [{"field": "updated_at", "operator": "within", "value": "7_days"}]),
        view(5, "Recently solved tickets", [{"field": "status", "operator": "is", "value": "solved"}]),
        view(6, "Pending tickets", [{"field": "status", "operator": "is", "value": "pending"}]),
        view(7, "New tickets", [{"field": "status", "operator": "is", "value": "new"}], typ="shared"),
        view(8, "Urgent & High priority", [unsolved], typ="personal",
             any_=[{"field": "priority", "operator": "is", "value": "urgent"}, {"field": "priority", "operator": "is", "value": "high"}]),
    ]
    macros = [
        {"id": 1, "title": "Escalate to Engineering", "description": "Move to Engineering Escalations with an internal note",
         "active": True, "position": 0, "restriction": None,
         "actions": [{"field": "group_id", "value": ENG}, {"field": "comment_mode", "value": "internal"},
                     {"field": "comment_value", "value": "Escalating to Engineering. Jira linked in the ticket fields."}]},
        {"id": 2, "title": "Request more information", "description": "Set pending and ask for details", "active": True,
         "position": 1, "restriction": None,
         "actions": [{"field": "status", "value": "pending"}, {"field": "comment_mode", "value": "public"},
                     {"field": "comment_value", "value": "Thanks for reaching out! Could you share a screenshot and the job or invoice number so we can look into this?"}]},
        {"id": 3, "title": "Assign to me", "description": "Assign to current agent and open", "active": True, "position": 2,
         "restriction": None, "actions": [{"field": "assignee_id", "value": "current_user"}, {"field": "status", "value": "open"}]},
        {"id": 4, "title": "Close and point to help center", "description": "Solve with help-center link", "active": True,
         "position": 3, "restriction": None,
         "actions": [{"field": "status", "value": "solved"}, {"field": "comment_mode", "value": "public"},
                     {"field": "comment_value", "value": "Here's the help-center article that walks through this: https://help.acmefieldwork.com. I'll mark this solved, just reply if you need anything else."}]},
        {"id": 5, "title": "Transfer to Billing", "description": "Move to Billing group", "active": True, "position": 4,
         "restriction": None, "actions": [{"field": "group_id", "value": BILLG}, {"field": "comment_mode", "value": "internal"},
                                          {"field": "comment_value", "value": "Transferring to Billing."}]},
    ]
    tags = sorted({t for tk in tickets for t in tk["tags"]} | {"key-account", "enterprise", "workaround", "vip"})
    current = next(u for u in users if u["id"] == DANA)
    state = {
        "currentUser": current, "users": users, "organizations": orgs, "groups": groups, "tickets": tickets,
        "comments": comments, "views": views, "macros": macros, "tags": tags,
        "ui": {"activeView": 1, "openTicketTabs": [], "activeTicketId": None, "searchQuery": "",
               "selectedTicketIds": [], "replyMode": "public", "sidebarCollapsed": False},
    }
    return state, ids


# ---------------------------------------------------------------- slack
SLACK_USERS = [
    ("U01", "Dana Whitfield", "Dana", "dana.whitfield@acmefieldwork.com", "Support Lead"),
    ("U02", "Tomás Reyes", "Tomás", "tomas.reyes@acmefieldwork.com", "Engineering Manager, Fieldwork Platform"),
    ("U03", "Wen Liu", "Wen", "wen.liu@acmefieldwork.com", "Support Engineer (Escalations)"),
    ("U04", "Diego Ferraz", "Diego", "diego.ferraz@acmefieldwork.com", "Tier 2 Support"),
    ("U05", "Marcus Bell", "Marcus", "marcus.bell@acmefieldwork.com", "Tier 1 Support"),
    ("U06", "Hannah Cho", "Hannah", "hannah.cho@acmefieldwork.com", "Tier 1 Support"),
    ("U07", "Priya Raman", "Priya", "priya.raman@acmefieldwork.com", "Billing Operations"),
    ("U08", "Karthik Rao", "Karthik", "karthik.rao@acmefieldwork.com", "Senior Engineer"),
]
THREAD = "th_review"
CHANNEL = "support-escalations"


def smsg(mid, sender, ts, text, thread=None, reactions=None):
    return {"messageId": mid, "senderId": sender, "content": text, "timestamp": ts, "threadId": thread,
            "reactions": reactions or [], "attachments": [], "isEdited": False}


def build_slack(ids):
    users = [{"userId": uid, "fullName": full, "displayName": short, "email": em, "avatar": avatar(full),
              "title": title, "status": "online" if uid in ("U01", "U02", "U03") else "away",
              "statusMessage": "", "statusEmoji": "", "timeZone": "America/Los_Angeles"}
             for uid, full, short, em, title in SLACK_USERS]
    everyone = [u[0] for u in SLACK_USERS]

    def channel(cid, name, desc, pinned=()):
        return {"channelId": cid, "name": name, "description": desc, "topic": desc, "isPrivate": False,
                "isStarred": cid == CHANNEL, "members": everyone, "createdBy": "U01",
                "createdAt": "2025-02-01T17:00:00Z", "pinnedMessages": list(pinned), "unreadCount": 0}

    request = (
        "Escalation review is this Friday (11/20). For FLD-412, FLD-398 and FLD-431 I want the real customer footprint, "
        "not just the one or two tickets that got linked when each bug was filed. @Dana can you pull every Zendesk ticket "
        "we escalated to engineering on those bugs that was opened since September 1, whatever state it's in now (plenty "
        "of them were solved with a workaround or parked on hold)?\n"
        "1. Tag each of those tickets in Zendesk with the bug key in lowercase (fld-412, ...) so we can pull them up in the meeting.\n"
        "2. Leave a comment on each Jira bug with the ticket numbers, how many distinct customer accounts that is, and their combined ARR from the billing export.\n"
        "3. Any bug whose affected accounts add up to $150k ARR or more goes to Highest priority. Leave the others at the priority they have.\n"
        "Reply here when it's done with the numbers per bug. Thanks!"
    )
    msgs = [
        smsg("m_e1", "U03", "2026-11-03T18:10:00Z", "Heads up, seeing more series-edit duplicate reports this week. They're all going to Engineering Escalations with the Jira key in the ticket field."),
        smsg("m_e2", "U02", "2026-11-03T18:40:00Z", "Thanks Wen, Karthik is on FLD-412."),
        smsg("m_e3", "U04", "2026-11-10T22:05:00Z", f"FYI #{ids['X_405a']} (Safari map tiles) is FLD-405, low priority on their side, not in any review."),
        smsg("m_e4", "U02", "2026-11-16T17:05:00Z", request, reactions=[{"emoji": "👀", "users": ["U01"]}]),
    ]
    replies = [
        smsg("m_r1", "U04", "2026-11-16T18:12:00Z", "I already tagged the two open 412 tickets I was working on last week with fld-412. Everything else still needs doing.", thread=THREAD),
        smsg("m_r2", "U03", "2026-11-17T01:30:00Z", "FLD-431 shipped in 4.18 and is closed. What people have been hitting since the 4.18 update is a different bug, FLD-447 (offline signature queue drops entries). New root cause, its own tickets.", thread=THREAD),
        smsg("m_r3", "U02", "2026-11-17T16:02:00Z", "Thanks Wen. Then drop FLD-431 from the review and do FLD-447 in its place, same treatment. Leave the 431 tickets alone, those customers are fixed.", thread=THREAD),
        smsg("m_r4", "U07", "2026-11-17T16:20:00Z", "Billing export with current ARR is on the support laptop as `billing_accounts.csv`. Heads up, the account names there don't always match the Zendesk org names, billing keys accounts on `billing_domain`.", thread=THREAD),
    ]
    messages = {
        "general": [
            smsg("m_g1", "U02", "2026-11-12T17:00:00Z", "4.18.1 is rolling out to all customers today. Release notes in #eng-releases."),
            smsg("m_g2", "U07", "2026-11-14T00:30:00Z", "Reminder: November billing run is on the 1st, any seat changes need to be in by the 28th."),
        ],
        "support-team": [
            smsg("m_t1", "U05", "2026-11-17T15:10:00Z", "Covering the phones 9-12 today, Hannah has the afternoon."),
            smsg("m_t2", "U06", "2026-11-17T15:12:00Z", "👍"),
            smsg("m_t3", "U01", "2026-11-17T19:30:00Z", "Reminder: please keep the Jira issue field filled in whenever you escalate to engineering."),
        ],
        CHANNEL: msgs[:3] + [msgs[3]] + replies,
        "eng-releases": [
            smsg("m_x1", "U08", "2026-10-19T20:00:00Z", "4.18.0 released: offline signature capture rewrite (fixes FLD-431), faster schedule board, new invoice templates."),
            smsg("m_x2", "U08", "2026-11-12T16:55:00Z", "4.18.1 released: crash fixes on Android 15, map clustering tweaks."),
        ],
    }
    threads = {THREAD: {"threadId": THREAD, "parentMessageId": "m_e4", "channelId": CHANNEL, "dmId": None,
                        "replies": [r["messageId"] for r in replies], "followers": ["U01", "U02", "U03"]}}
    return {
        "currentUser": users[0],
        "workspace": {"workspaceId": "ws_acme", "workspaceName": "Acme Fieldwork", "icon": avatar("Acme Fieldwork")},
        "users": users,
        "channels": [channel("general", "general", "Company-wide"),
                     channel("support-team", "support-team", "Support team chatter"),
                     channel(CHANNEL, CHANNEL, "Support <> engineering escalations"),
                     channel("eng-releases", "eng-releases", "Release announcements")],
        "messages": messages, "threads": threads, "dms": [], "bookmarkedMessages": [], "callHistory": [],
        "settings": {"theme": "light", "notifications": "all", "displayDensity": "comfortable", "showAvatars": True, "use24Hour": False},
        "invitations": [], "notifications": [],
    }


# ---------------------------------------------------------------- jira
JIRA_USERS = [
    ("ju1", "Dana Whitfield", "dana.whitfield@acmefieldwork.com"),
    ("ju2", "Tomás Reyes", "tomas.reyes@acmefieldwork.com"),
    ("ju3", "Wen Liu", "wen.liu@acmefieldwork.com"),
    ("ju4", "Karthik Rao", "karthik.rao@acmefieldwork.com"),
    ("ju5", "Ana Souza", "ana.souza@acmefieldwork.com"),
    ("ju6", "Lena Fischer", "lena.fischer@acmefieldwork.com"),
]


def build_jira(ids):
    users = [{"id": uid, "name": n, "email": e, "avatar": avatar(n)} for uid, n, e in JIRA_USERS]
    projects = [{"id": "p1", "key": "FLD", "name": "Fieldwork Platform", "leadId": "ju2", "category": "Software",
                 "icon": avatar("FLD"), "description": "Core web app, scheduling, invoicing and the field mobile app."}]
    sprints = [
        {"id": "s45", "projectId": "p1", "name": "FLD Sprint 45", "goal": "4.18 release hardening", "startDate": "2026-10-12T16:00:00.000Z", "endDate": "2026-10-25T16:00:00.000Z", "state": "closed"},
        {"id": "s46", "projectId": "p1", "name": "FLD Sprint 46", "goal": "Invoicing performance", "startDate": "2026-10-26T16:00:00.000Z", "endDate": "2026-11-08T16:00:00.000Z", "state": "closed"},
        {"id": "s47", "projectId": "p1", "name": "FLD Sprint 47", "goal": "Series editing + offline queue", "startDate": "2026-11-09T16:00:00.000Z", "endDate": "2026-11-22T16:00:00.000Z", "state": "active"},
        {"id": "s48", "projectId": "p1", "name": "FLD Sprint 48", "goal": "", "startDate": "2026-11-23T16:00:00.000Z", "endDate": "2026-12-06T16:00:00.000Z", "state": "future"},
    ]
    z = ids
    core = {
        388: ("Estimate approval link returns 404 for some customers", "Bug", "Done", "High", "ju5", "s45", "2026-07-15T17:00:00.000Z", ["estimates", "customer-facing"],
              f"Approve-estimate links built with the legacy host 404.\n\nZendesk: #{z['X_388']}"),
        398: ("Invoice PDF export times out for invoices with 200+ line items", "Bug", "To Do", "High", "ju4", "s47", "2026-09-23T17:00:00.000Z", ["invoicing", "performance", "customer-facing"],
              f"PDF rendering is synchronous and hits the 60s gateway timeout once an invoice has roughly 200 line items.\n\nWorkarounds: split the invoice, CSV export, or the 'summarize by location' template.\n\nZendesk: #{z['T8']} (Harbor HVAC)"),
        405: ("Map tiles render blank in Safari 17", "Bug", "To Do", "Low", "ju6", None, "2026-09-11T17:00:00.000Z", ["dispatch", "safari"],
              f"Tile requests are blocked by Safari's ITP when the map runs inside the dispatch iframe.\n\nZendesk: #{z['X_405b']}"),
        412: ("Recurring job series creates duplicate visits after the series is edited", "Bug", "In Progress", "High", "ju4", "s47", "2026-09-02T17:00:00.000Z", ["scheduling", "customer-facing"],
              f"Editing day, time window, duration or technician on a series with future visits regenerates the visits without deleting the old ones.\n\nCleanup: end the series today and recreate it from tomorrow.\n\nZendesk: #{z['T1']} (Meridian)"),
        422: ("QuickBooks sync rounds multi-rate tax per line instead of per invoice", "Bug", "To Do", "Medium", "ju5", "s48", "2026-09-19T17:00:00.000Z", ["integrations", "quickbooks"],
              f"Off-by-one-cent tax totals on invoices with more than one tax rate.\n\nZendesk: #{z['X_422b']}"),
        431: ("iOS: technician signatures lost when syncing after an offline period", "Bug", "Done", "Medium", "ju6", "s45", "2026-09-10T17:00:00.000Z", ["mobile", "ios", "signatures"],
              f"Signatures captured offline were written to a temp directory iOS purges.\n\nZendesk: #{z['X_431a']}"),
        447: ("Offline signature queue drops entries after updating to 4.18", "Bug", "In Progress", "Medium", "ju6", "s47", "2026-10-29T17:00:00.000Z", ["mobile", "signatures", "offline"],
              f"After the 4.18 migration, queued signature uploads are dropped when the queue is replayed in a different order than captured.\n\nZendesk: #{z['T13']} (Redwood)"),
    }
    noise = [
        (380, "Schedule board drag-and-drop lag with 50+ technicians", "Story", "Done", "Medium"),
        (383, "Add 'summarize by location' invoice template", "Story", "Done", "Medium"),
        (386, "Upgrade map SDK to v5", "Task", "Done", "Low"),
        (390, "Customer portal: show paid invoices", "Story", "Done", "Medium"),
        (392, "Android 15 crash when opening camera from job", "Bug", "Done", "High"),
        (394, "Price book bulk edit", "Story", "In Review", "Medium"),
        (396, "Migrate notification service to new queue", "Task", "In Progress", "Medium"),
        (399, "Add audit log for invoice edits", "Story", "To Do", "Low"),
        (401, "Technician skill tags on dispatch board", "Story", "To Do", "Medium"),
        (403, "Async PDF rendering service (spike)", "Task", "In Progress", "High"),
        (404, "Improve series edit preview dialog", "Story", "To Do", "Medium"),
        (406, "Estimate templates: optional line items", "Story", "In Review", "Low"),
        (408, "Flaky e2e test: invoice CSV export", "Task", "To Do", "Low"),
        (409, "API: pagination cursor for /visits", "Story", "Done", "Medium"),
        (410, "Timesheet export includes deleted entries", "Bug", "To Do", "Medium"),
        (413, "Series regeneration: delete-then-create in one transaction", "Task", "In Progress", "High"),
        (415, "Online booking widget: custom colors", "Story", "To Do", "Low"),
        (417, "SMS reminders use company time zone", "Bug", "Done", "Medium"),
        (419, "Reporting: revenue by technician", "Story", "To Do", "Medium"),
        (420, "Offline queue: persist order index", "Task", "In Progress", "High"),
        (424, "Okta SSO: handle IdP-initiated login", "Story", "In Review", "Medium"),
        (426, "Inventory transfer recount job", "Bug", "To Do", "Low"),
        (428, "Dark mode for mobile app", "Story", "To Do", "Lowest"),
        (430, "Zapier: new estimate trigger", "Story", "To Do", "Low"),
        (433, "Bulk job import: stream rows", "Task", "To Do", "Medium"),
        (435, "Dispatch board keyboard shortcuts", "Story", "To Do", "Low"),
        (437, "Customer portal: card on file update", "Story", "Done", "Medium"),
        (439, "Webhook retries with backoff", "Story", "In Progress", "Medium"),
        (441, "Agreement renewals: reminder emails", "Story", "To Do", "Medium"),
        (443, "Remove legacy estimate host", "Task", "Done", "Low"),
        (445, "Job notes visible offline", "Story", "To Do", "Medium"),
        (449, "Upgrade React Native to 0.81", "Task", "To Do", "Medium"),
    ]
    rng = random.Random(447)
    issues = []
    for num, (summary, typ, status, prio, assignee, sprint, created, labels, desc) in core.items():
        issues.append({"id": f"i{num}", "key": f"FLD-{num}", "projectId": "p1", "summary": summary, "description": desc,
                       "type": typ, "status": status, "priority": prio, "storyPoints": 5, "reporterId": "ju3",
                       "assigneeId": assignee, "sprintId": sprint, "epicId": None, "createdAt": created,
                       "updatedAt": "2026-11-12T18:00:00.000Z" if status != "Done" else "2026-10-21T18:00:00.000Z",
                       "labels": labels, "subtasks": [], "linkedIssueIds": []})
    for num, summary, typ, status, prio in noise:
        created = f"2026-{rng.choice(['08', '09', '10', '11'])}-{rng.randint(1, 15):02d}T17:00:00.000Z"
        sprint = "s45" if status == "Done" and num < 400 else ("s46" if status == "Done" else ("s47" if status in ("In Progress", "In Review") else rng.choice([None, "s48"])))
        issues.append({"id": f"i{num}", "key": f"FLD-{num}", "projectId": "p1", "summary": summary,
                       "description": f"{summary}.", "type": typ, "status": status, "priority": prio,
                       "storyPoints": rng.choice([1, 2, 3, 5, 8]), "reporterId": rng.choice(["ju2", "ju4", "ju5", "ju6"]),
                       "assigneeId": rng.choice(["ju4", "ju5", "ju6", None]), "sprintId": sprint, "epicId": None,
                       "createdAt": created, "updatedAt": created, "labels": [], "subtasks": [], "linkedIssueIds": []})
    links = {"i412": ["i413", "i404"], "i398": ["i403", "i383"], "i447": ["i420", "i431"], "i431": ["i447"]}
    for i in issues:
        i["linkedIssueIds"] = links.get(i["id"], [])
    issues.sort(key=lambda i: int(i["key"].split("-")[1]))
    comments = [
        {"id": "jc1", "issueId": "i412", "userId": "ju4", "content": "Root cause found: regeneration inserts the new visits before deleting the old ones and the delete is skipped when the series has a time-window change. Fix in FLD-413.", "createdAt": "2026-11-05T19:00:00.000Z"},
        {"id": "jc2", "issueId": "i412", "userId": "ju2", "content": "Targeting the 4.19 release.", "createdAt": "2026-11-06T17:00:00.000Z"},
        {"id": "jc3", "issueId": "i398", "userId": "ju4", "content": "Spike on async rendering in FLD-403. Not scheduled for 4.19 yet.", "createdAt": "2026-10-28T18:00:00.000Z"},
        {"id": "jc4", "issueId": "i398", "userId": "ju3", "content": f"Oakridge (Zendesk #{z['T10']}) is this bug too, the 410-line HOA invoice. It was escalated against FLD-412 by mistake; no duplicated visits there.", "createdAt": "2026-10-27T20:30:00.000Z"},
        {"id": "jc5", "issueId": "i431", "userId": "ju6", "content": "Fixed in 4.18.0, closing. Post-4.18 offline signature reports are a different root cause, see FLD-447.", "createdAt": "2026-10-21T18:00:00.000Z"},
        {"id": "jc6", "issueId": "i447", "userId": "ju6", "content": "Repro'd on iOS and Android: queue replay sorts by upload time, entries with equal timestamps get dropped. Fix in FLD-420.", "createdAt": "2026-11-07T18:00:00.000Z"},
        {"id": "jc7", "issueId": "i405", "userId": "ju6", "content": "Low impact, Chrome works. Parking.", "createdAt": "2026-09-20T18:00:00.000Z"},
    ]
    workflows = [{"id": "w1", "name": "Software Workflow", "transitions": [
        {"from": "To Do", "to": ["In Progress"]}, {"from": "In Progress", "to": ["In Review", "To Do", "Done"]},
        {"from": "In Review", "to": ["Done", "In Progress"]}, {"from": "Done", "to": ["In Progress", "To Do"]}]}]
    notifications = [
        {"id": "jn1", "type": "mention", "issueId": "i412", "actorId": "ju2", "message": "Tomás Reyes mentioned you on FLD-412", "read": False, "createdAt": "2026-11-16T17:10:00.000Z"},
        {"id": "jn2", "type": "comment", "issueId": "i447", "actorId": "ju6", "message": "Lena Fischer commented on FLD-447", "read": True, "createdAt": "2026-11-07T18:00:00.000Z"},
    ]
    return {"users": users, "projects": projects, "issues": issues, "sprints": sprints, "comments": comments,
            "workflows": workflows, "notifications": notifications, "currentUser": users[0]}


# ---------------------------------------------------------------- truth
def truth(ids):
    by_key = {k: [] for k in REVIEW}
    for s in ESC:
        if not s["label"].startswith("T"):
            continue
        key = "FLD-398" if s["label"] == "T10" else s["jira"]
        by_key[key].append(s)
    out = {}
    for key, specs in by_key.items():
        accts = {}
        for s in specs:
            a = account_of(s["who"])
            accts[a[0]] = a[4]
        arr = sum(accts.values())
        out[key] = {"tickets": sorted(ids[s["label"]] for s in specs), "accounts": sorted(accts),
                    "account_count": len(accts), "arr": arr,
                    "priority": "Highest" if arr >= THRESHOLD else {"FLD-412": "High", "FLD-398": "High", "FLD-447": "Medium"}[key]}
    return out


def ticket_rows(ids, plan):
    """plan: {jira_key: [(ticket label, account_id)]} -> CSV rows."""
    status = {s["label"]: s["status"] for s in ESC}
    rows = [["ticket_id", "jira_key", "account_id", "status"]]
    for key in sorted(plan):
        for label, acct in sorted(plan[key], key=lambda x: ids[x[0]]):
            rows.append([str(ids[label]), key, acct, status[label]])
    return rows


def golden_plan():
    plan = {k: [] for k in REVIEW}
    for s in ESC:
        if s["label"].startswith("T"):
            key = "FLD-398" if s["label"] == "T10" else s["jira"]
            plan[key].append((s["label"], account_of(s["who"])[0]))
    return plan


ARR_OF = {b[0]: b[4] for b in BILLING}
SEED_PRIORITY = {"FLD-412": "High", "FLD-398": "High", "FLD-447": "Medium", "FLD-431": "Medium"}


def fmt_money(v):
    return f"${v:,.0f}"


def apply_run(seed, ids, plan, *, slack=True, csv_out=True):
    z, s, j = (copy.deepcopy(seed[k]) for k in ("zendesk", "slack", "jira"))
    tickets = {t["id"]: t for t in z["tickets"]}
    for key, items in plan.items():
        tag = key.lower()
        for label, _ in items:
            t = tickets[ids[label]]
            if tag not in t["tags"]:
                t["tags"] = t["tags"] + [tag]
                t["updated_at"] = RUN_TS
    summary = []
    issues = {i["key"]: i for i in j["issues"]}
    for n, (key, items) in enumerate(sorted(plan.items())):
        tids = sorted(ids[label] for label, _ in items)
        accts = sorted({a for _, a in items})
        arr = sum(ARR_OF[a] for a in accts)
        issue = issues[key]
        content = (f"Escalation review: Zendesk tickets opened since Sep 1 and escalated on this bug: "
                   f"{', '.join('#' + str(t) for t in tids)}. {len(tids)} tickets, {len(accts)} distinct accounts, "
                   f"combined ARR {fmt_money(arr)}.")
        j["comments"].append({"id": f"gold-{n}", "issueId": issue["id"], "userId": "ju1", "content": content,
                              "createdAt": RUN_TS})
        if arr >= THRESHOLD and issue["priority"] != "Highest":
            issue["priority"] = "Highest"
            issue["updatedAt"] = RUN_TS
        summary.append(f"{key}: {len(tids)} tickets, {len(accts)} accounts, {fmt_money(arr)} ARR"
                       + (" -> bumped to Highest" if arr >= THRESHOLD else f" -> stays {issue['priority']}"))
    if slack:
        msg = smsg("m_done", "U01", RUN_TS.replace(".000", ""), "Done. " + "; ".join(summary) + ". Tickets are tagged in Zendesk.", thread=THREAD)
        s["messages"][CHANNEL].append(msg)
        s["threads"][THREAD]["replies"].append("m_done")
    rows = ticket_rows(ids, plan) if csv_out else None
    return {"zendesk": z, "slack": s, "jira": j}, rows


# ---------------------------------------------------------------- variants
def acct(label):
    who = next(s["who"] for s in ESC if s["label"] == label)
    return account_of(who)[0]


def naive_plan():
    """First-screen run: only unsolved, not-on-hold tickets; uses FLD-431 from the original message;
    trusts the stale Jira field on T10; matches 'Brightline' to Brightline Solar by name."""
    return {
        "FLD-412": [("T3", acct("T3")), ("T4", acct("T4")), ("T5", acct("T5")), ("T10", acct("T10"))],
        "FLD-398": [("T7", "ACC-1016")],
        "FLD-431": [("X_431d", acct("X_431d"))],
    }


def slip_superseded_plan():
    plan = golden_plan()
    del plan["FLD-447"]
    plan["FLD-431"] = [("X_431a", acct("X_431a")), ("X_431b", acct("X_431b")), ("X_431c", acct("X_431c")), ("X_431d", acct("X_431d"))]
    return plan


def slip_retriage_plan():
    plan = golden_plan()
    plan["FLD-398"] = [x for x in plan["FLD-398"] if x[0] != "T10"]
    plan["FLD-412"] = plan["FLD-412"] + [("T10", acct("T10"))]
    return plan


def slip_hold_plan():
    plan = golden_plan()
    for k in plan:
        plan[k] = [x for x in plan[k] if x[0] not in ("T2", "T9", "T16")]
    return plan


def slip_brightline_plan():
    plan = golden_plan()
    plan["FLD-398"] = [(l, "ACC-1016" if l == "T7" else a) for l, a in plan["FLD-398"]]
    return plan


def slip_window_plan():
    """Careful run that counts the Aug 31 23:40 PT ticket and the merged duplicate."""
    plan = golden_plan()
    plan["FLD-398"] = plan["FLD-398"] + [("X_boundary", acct("X_boundary")), ("X_merged", acct("X_merged"))]
    return plan


def visible_only_plan():
    """Careful about every trap but never looks past unsolved/non-hold lists (the L03 lever alone)."""
    plan = golden_plan()
    for k in plan:
        plan[k] = [x for x in plan[k] if x[0] not in HIDDEN]
    return plan


HIDDEN = ("T1", "T2", "T6", "T8", "T9", "T11", "T15", "T16")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    zendesk, ids = build_zendesk()
    seed = {"zendesk": zendesk, "slack": build_slack(ids), "jira": build_jira(ids)}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, gold_rows = apply_run(seed, ids, golden_plan())
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "escalation_review.csv", gold_rows)
    write_csv(out / "input" / "billing_accounts.csv",
              [["account_id", "account_name", "billing_domain", "plan", "arr_usd", "status"]]
              + [[a, n, d, p, str(v), st] for a, n, d, p, v, st in BILLING])

    t = truth(ids)
    status = {s["label"]: s["status"] for s in ESC}
    hidden = sorted(ids[l] for l in HIDDEN)
    excluded = {
        "merged_duplicate": ids["X_merged"], "aug31_boundary": ids["X_boundary"],
        "fld431": sorted(ids[l] for l in ("X_431a", "X_431b", "X_431c", "X_431d")),
        "aug_fld412": ids["X_aug412"], "retriaged_not_412": ids["T10"],
        "other_bugs": sorted(ids[l] for l in ("X_405a", "X_405b", "X_422a", "X_422b", "X_388")),
        "lookalikes_not_escalated": sorted(ids[l] for l in ("L_dup", "L_pdf", "L_sig", "L_dup2")),
    }
    write_json(out / "expected.json", {
        "clock": CLOCK, "timezone": "America/Los_Angeles", "window_start_pt": "2026-09-01T00:00:00-07:00",
        "threshold_arr": THRESHOLD, "review_keys": list(REVIEW), "superseded_key": "FLD-431",
        "bugs": t, "jira_issue_ids": {k: f"i{k.split('-')[1]}" for k in REVIEW + ("FLD-431",)},
        "seed_priority": SEED_PRIORITY,
        "ticket_status": {str(ids[s['label']]): status[s['label']] for s in ESC if s['label'].startswith('T')},
        "ticket_account": {str(ids[l]): a for k, items in golden_plan().items() for l, a in items},
        "pretagged": {"fld-412": sorted([ids["T3"], ids["T4"]])},
        "hidden_targets": hidden, "excluded": excluded,
        "slack": {"channel": CHANNEL, "thread": THREAD, "parent": "m_e4", "me": "U01"},
        "jira_me": "ju1", "zendesk_me": DANA,
        "labels": {s["label"]: ids[s["label"]] for s in ESC + LOOKALIKES},
    })

    variants = {"golden": (golden, gold_rows), "nop": (seed, None)}
    variants["naive"] = apply_run(seed, ids, naive_plan())
    variants["slip_superseded"] = apply_run(seed, ids, slip_superseded_plan())
    variants["slip_retriage"] = apply_run(seed, ids, slip_retriage_plan())
    variants["slip_hold"] = apply_run(seed, ids, slip_hold_plan())
    variants["slip_brightline"] = apply_run(seed, ids, slip_brightline_plan())
    variants["slip_window"] = apply_run(seed, ids, slip_window_plan())
    variants["visible_only"] = apply_run(seed, ids, visible_only_plan())
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "escalation_review.csv", rows)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
