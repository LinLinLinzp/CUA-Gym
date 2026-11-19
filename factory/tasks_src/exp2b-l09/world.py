#!/usr/bin/env python3
"""World for exp2b-l09 (cua-hard/summit-vendor-envelopes): DocuSign + Airtable + Yahoo Mail.

Nadia Okafor (Brightline Events, Santa Barbara) is sending the vendor contracts for
Halvorsen Biotech's 2027 Leadership Summit. Her assistant Theo built draft envelopes
in DocuSign from the Airtable vendor tracker on Nov 12; since then the client moved
the summit by a day, raised nothing but capped entertainment, a caterer revised the
headcount (crossing the client's $25k signing-authority line), the AV company changed
signer, the florist asked for a hold and Theo already sent the shuttle contract with
the old dates. Lever L09: a sent envelope is locked and can only be voided (which stays
on record), so every fix has to happen before Send.

Writes into <out>/:
  seed/{docusign,airtable,yahoo_mail}.json, seed/files/<site>/*    initial state + files
  golden/*.json, golden_output/summit_contracts.csv                 state after a correct run
  input/contracts/*.pdf                                             Theo's working copies (stale)
  expected.json                                                     truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/}     self-check fixtures

DocuSign golden state assumes the incremental-mock work in gaps.json: drafts can be
reopened in the editor, sent envelopes are read-only, and Send writes an immutable
`sentSnapshot` (also copied into the history "sent" event).
"""

import base64
import copy
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, long_pdf  # noqa: E402

CLOCK = "2026-11-18T10:00:00-08:00"
TZ = "America/Los_Angeles"
NOW = "2026-11-18T18:40:00.000Z"
TODAY = "2026-11-18"

NADIA = ("Nadia Okafor", "nadia.brightlineevents@yahoo.com")
THEO = ("Theo Marsh", "theo.brightlineevents@yahoo.com")
ELISE = ("Elise Brandt", "elise.brandt@halvorsenbio.com")
DANIEL = ("Daniel Moreau", "daniel.moreau@halvorsenbio.com")
EVENT = "Halvorsen Leadership Summit 2027"
CSV_NAME = "summit_contracts.csv"
CSV_HEADER = ["vendor", "action", "contract_total", "vendor_signer_email", "client_signer_email"]

# ---------------------------------------------------------------- vendors (truth + what Theo had on Nov 12)
# key: (vendor, service, signer(name,email), client signer, total, deposit, deposit_due, service_date, version)
V = {
    "venue": dict(vendor="Mirasol Hotel Santa Barbara", service="Venue", signer=("Camille Duarte", "cduarte@mirasolsb.com"),
                  client=DANIEL, total=48200, deposit=14460, due="2026-11-20", dates="Jan 21-23, 2027", version="v2"),
    "catering": dict(vendor="Coastline Catering Co.", service="Catering", signer=("Maria Delgado", "maria@coastlinecatering.com"),
                     client=ELISE, total=23800, deposit=7140, due="2026-12-04", dates="Jan 21-23, 2027", version="v2"),
    "av": dict(vendor="Lumen AV Productions", service="AV & Staging", signer=("Greg Whitfield", "greg.whitfield@lumenav.com"),
               client=DANIEL, total=31500, deposit=15750, due="2026-12-01", dates="Jan 21-23, 2027", version="v1"),
    "shuttle": dict(vendor="Pacific Shuttle Partners", service="Transportation", signer=("Luis Ortega", "luis@pacificshuttlepartners.com"),
                    client=ELISE, total=9750, deposit=2925, due="2026-12-01", dates="Jan 20-22, 2027", version="v1"),
    "floral": dict(vendor="Bloom & Vine Florals", service="Florals", signer=("Hazel Kim", "hazel@bloomandvine.com"),
                   client=ELISE, total=6200, deposit=3100, due="2026-12-10", dates="Jan 21-23, 2027", version="v1"),
    "photo": dict(vendor="Sandpiper Photo & Film", service="Photo & Video", signer=("Jonah Reyes", "jonah@sandpiperphoto.com"),
                  client=ELISE, total=4800, deposit=1200, due="2026-12-15", dates="Jan 21-23, 2027", version="v1"),
    "band": dict(vendor="Harbor Lights Entertainment", service="Entertainment", signer=("Marcus Bell", "marcus@harborlightsband.com"),
                 client=ELISE, total=7500, deposit=3750, due="2026-12-11", dates="Jan 22, 2027", version="v1"),
}
TRUTH = copy.deepcopy(V)
TRUTH["catering"].update(client=DANIEL, total=26350, deposit=7905, version="v3")
TRUTH["av"].update(signer=("Priya Raman", "priya.raman@lumenav.com"))
TRUTH["shuttle"].update(dates="Jan 21-23, 2027", due="2026-12-08", version="v2")
TRUTH["band"].update(total=5800, deposit=2900, dates="Jan 23, 2027", version="v2")

ACTIONS = {"venue": "already_signed", "catering": "sent", "av": "sent", "shuttle": "voided_and_resent",
           "floral": "on_hold", "photo": "sent", "band": "sent"}
SENT_KEYS = ["catering", "av", "shuttle", "photo", "band"]

DOCS = {  # file names
    "venue": "Mirasol_Venue_Agreement_HBLS27_v2.pdf",
    "catering_v2": "Coastline_Catering_Agreement_HBLS27_v2.pdf",
    "catering_v3": "Coastline_Catering_Agreement_HBLS27_v3.pdf",
    "catering_redline": "Coastline_Catering_Agreement_HBLS27_v3_redline.pdf",
    "av": "Lumen_AV_Production_Agreement_HBLS27.pdf",
    "shuttle_v1": "Pacific_Shuttle_Agreement_HBLS27_v1.pdf",
    "shuttle_v2": "Pacific_Shuttle_Agreement_HBLS27_v2.pdf",
    "floral": "Bloom_Vine_Floral_Agreement_HBLS27.pdf",
    "photo": "Sandpiper_Photo_Video_Agreement_HBLS27.pdf",
    "band_v1": "Harbor_Lights_Performance_Agreement_HBLS27_v1.pdf",
    "band_v2": "Harbor_Lights_Performance_Agreement_HBLS27_v2.pdf",
}
SEND_DOC = {"catering": "catering_v3", "av": "av", "shuttle": "shuttle_v2", "photo": "photo", "band": "band_v2"}
DRAFT_DOC = {"catering": "catering_v2", "av": "av", "shuttle": "shuttle_v1", "floral": "floral", "photo": "photo",
             "band": "band_v1", "venue": "venue"}


def money(v) -> str:
    return f"{float(v):,.2f}"


def long_date(iso_day: str) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(iso_day)
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


# ---------------------------------------------------------------- contract PDFs
def contract_sections(key, t, *, redline=False, extra=None):
    signer = t["signer"]
    parties = (f"This agreement is made between {t['vendor']} (\"Vendor\") and Halvorsen Biotech, Inc. (\"Client\"), "
               f"arranged by Brightline Events as the Client's event planner, for the {EVENT} at Mirasol Hotel Santa Barbara.")
    scope = {
        "venue": ["Exclusive use of the Pacific Ballroom, Terrace and three breakout rooms, Thursday January 21 through Saturday January 23, 2027.",
                  "Room block of 120 king/double rooms at the group rate, cut-off December 21, 2026."],
        "catering": [f"Catering for {155 if t['version'] == 'v3' else 140} guests: welcome reception (Thu Jan 21), breakfast, lunch and two breaks (Fri Jan 22), "
                     "awards gala dinner (Sat Jan 23). Per-guest package rate $170.00, service charge included.",
                     "Final guarantee due 10 days before the first event day; the guarantee may not be reduced below the contracted headcount."],
        "av": ["Main-stage audio, LED wall 6m x 3.5m, confidence monitors, breakout projection (3 rooms), two technicians on site all three days.",
               "Load-in Wednesday January 20, 2027 after 6:00 pm; strike Saturday January 23 after the gala."],
        "shuttle": [f"Airport (SBA) and hotel shuttle loops on {'January 21, 22 and 23, 2027' if t['version'] == 'v2' else 'January 20, 21 and 22, 2027'}; "
                    "two 28-passenger coaches, 6:30 am to 11:30 pm daily, plus the gala-night offsite return run.",
                    "Driver gratuity included. Overtime billed at $145.00 per coach-hour."],
        "floral": ["Centerpieces for 16 gala tables, stage arrangement, registration and terrace arrangements; protea and eucalyptus palette.",
                   "Delivery and setup Saturday January 23, 2027 by 2:00 pm; strike after the gala."],
        "photo": ["One lead photographer and one videographer, all three days; same-day social edit of 20 images; full gallery within 14 days.",
                  "Two-minute highlight film delivered within 21 days."],
        "band": [("Four-piece band (vocals, keys, bass, drums)" if t["version"] == "v2" else "Six-piece band with two horns") +
                 f" for the awards gala on {'Saturday, January 23, 2027' if t['version'] == 'v2' else 'Friday, January 22, 2027'}, "
                 "three 45-minute sets, DJ playlist between sets.", "Vendor provides its own backline; Client provides a 16' x 12' stage."],
    }[key]
    money_lines = [f"Contract total: ${money(t['total'])} (all-inclusive).",
                   f"Deposit: ${money(t['deposit'])} due {long_date(t['due'])}; balance due 7 days before the event.",
                   "Cancellation: deposit non-refundable within 30 days of the event."]
    sections = [("Parties", [parties]), ("Scope of services", scope), ("Fees and payment", money_lines)]
    if extra:
        sections.append(extra)
    sections.append(("Signatures", [f"Vendor: {signer[0]}, {t['vendor']}", "Client: authorized signatory, Halvorsen Biotech, Inc.",
                                    f"Agreement version {t['version']}."]))
    if redline:
        sections.insert(0, ("REDLINE - NOT FOR SIGNATURE", ["Changes from v2: headcount 140 -> 155; contract total $23,800.00 -> $26,350.00; "
                                                            "deposit $7,140.00 -> $7,905.00. Use the clean v3 for signature."]))
    return sections


def write_contracts(out: Path):
    """PDFs for DocuSign seeds, Yahoo attachments and the stale input folder. Returns {doc_key: path}."""
    tmp = out / "_pdf"
    paths = {}
    jobs = {
        "venue": ("venue", TRUTH["venue"], {}),
        "catering_v2": ("catering", V["catering"], {}),
        "catering_v3": ("catering", TRUTH["catering"], {}),
        "catering_redline": ("catering", TRUTH["catering"], {"redline": True}),
        "av": ("av", V["av"], {}),
        "shuttle_v1": ("shuttle", V["shuttle"], {}),
        "shuttle_v2": ("shuttle", TRUTH["shuttle"], {}),
        "floral": ("floral", V["floral"], {}),
        "photo": ("photo", V["photo"], {}),
        "band_v1": ("band", V["band"], {}),
        "band_v2": ("band", TRUTH["band"], {}),
    }
    for dk, (key, t, kw) in jobs.items():
        title = f"{t['vendor']} - {t['service']} Agreement ({t['version']}{' REDLINE' if kw.get('redline') else ''})"
        paths[dk] = long_pdf(tmp / DOCS[dk], title, contract_sections(key, t, **kw))
    return paths


def page_png(path: Path, title: str, lines):
    """Clean first-page preview used as the DocuSign canvas image for seeded documents."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = 850, 1100
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    big, body = ImageFont.load_default(size=26), ImageFont.load_default(size=17)
    d.text((70, 70), title, fill="#111", font=big)
    d.line((70, 112, w - 70, 112), fill="#999", width=1)
    y = 140
    for line in lines:
        words, cur = line.split(), ""
        for word in words:
            if d.textlength(cur + " " + word, font=body) > w - 150:
                d.text((70, y), cur.strip(), fill="#222", font=body)
                y += 26
                cur = ""
            cur += " " + word
        d.text((70, y), cur.strip(), fill="#222", font=body)
        y += 38
    d.text((70, h - 220), "Vendor signature: ______________________", fill="#222", font=body)
    d.text((70, h - 160), "Client signature: ______________________", fill="#222", font=body)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def preview_lines(key, t):
    secs = contract_sections(key, t)
    return [p for _, ps in secs for p in ps][:8]


# ---------------------------------------------------------------- DocuSign
def recip(rid, person, order, status="created", role="signer", **ts):
    return {"id": rid, "name": person[0], "email": person[1], "role": role, "routingOrder": order, "status": status,
            "signedAt": ts.get("signed"), "viewedAt": ts.get("viewed"), "deliveredAt": ts.get("delivered"),
            "declinedAt": None, "declineReason": None}


def sig_fields(eid, doc_id, recipients):
    fields = []
    for i, r in enumerate(recipients):
        y = 880 + 60 * i
        fields.append({"id": f"fld_{eid}_{i}_s", "type": "signature", "recipientId": r["id"], "documentId": doc_id, "pageNumber": 1,
                       "x": 300, "y": y, "width": 200, "height": 50, "value": "", "required": True, "label": "",
                       "readOnly": False, "fontSize": 14, "fontColor": "#000000"})
        fields.append({"id": f"fld_{eid}_{i}_d", "type": "dateSigned", "recipientId": r["id"], "documentId": doc_id, "pageNumber": 1,
                       "x": 560, "y": y + 10, "width": 120, "height": 30, "value": "", "required": True, "label": "",
                       "readOnly": False, "fontSize": 14, "fontColor": "#000000"})
    return fields


def hist(eid, n, ts, action, details, actor=NADIA):
    return {"id": f"evt_{eid}_{n}", "timestamp": ts, "action": action, "actorName": actor[0], "actorEmail": actor[1], "details": details}


def ds_doc(eid, name, sizes):
    return {"id": f"doc_{eid}_1", "name": name, "pageCount": 4, "order": 1, "fileUrl": file_url(name.replace(".pdf", ".png")),
            "downloadUrl": file_url(name), "fileType": "pdf", "fileSize": sizes.get(name)}


def draft_message(key, t):
    first = t["signer"][0].split()[0]
    extra = {"band": f" Performance for the awards gala on Friday, January 22, 2027."}.get(key, "")
    dates = "January 20-22, 2027" if t["dates"].startswith("Jan 20") else "January 21-23, 2027"
    return (f"Hi {first}, please review and sign the {t['service'].lower()} agreement for the Halvorsen Biotech Leadership Summit "
            f"({dates}, Mirasol Hotel Santa Barbara). Contract total ${money(t['total'])}; deposit of ${money(t['deposit'])} "
            f"due {long_date(t['due'])}.{extra} Thanks, Nadia")


def summit_subject(key, t):
    kind = {"venue": "Venue Agreement", "catering": "Catering Agreement", "av": "AV Production Agreement",
            "shuttle": "Ground Transportation Agreement", "floral": "Floral Agreement", "photo": "Photo & Video Agreement",
            "band": "Entertainment Agreement"}[key]
    return f"{EVENT} - {kind} - {t['vendor']}"


def envelope(eid, subject, message, docs, recipients, status, created, *, sent=None, completed=None, voided=None,
             void_reason=None, viewed=None, folder=None, template=None):
    h = [hist(eid, 1, created, "created", "Envelope created")]
    if sent:
        h.append(hist(eid, 2, sent, "sent", f"Envelope sent to {len(recipients)} recipient(s)"))
        h.append(hist(eid, 3, sent, "delivered", f"Envelope delivered to {recipients[0]['name']}",
                      (recipients[0]["name"], recipients[0]["email"])))
    if viewed:
        h.append(hist(eid, 4, viewed, "viewed", f"{recipients[0]['name']} viewed the document", (recipients[0]["name"], recipients[0]["email"])))
    if completed:
        for i, r in enumerate(recipients):
            h.append(hist(eid, 5 + i, completed, "signed", f"{r['name']} signed the document", (r["name"], r["email"])))
        h.append(hist(eid, 9, completed, "completed", "All recipients have completed signing", ("System", "")))
    if voided:
        h.append(hist(eid, 10, voided, "voided", f"Envelope voided: {void_reason}"))
    last = voided or completed or viewed or sent or created
    env = {"id": eid, "subject": subject, "message": message, "status": status, "createdAt": created, "sentAt": sent,
           "completedAt": completed, "voidedAt": voided, "declinedAt": None, "lastActivityAt": last,
           "expiresAt": None if status in ("draft", "completed", "voided") else "2027-03-17T18:00:00.000Z",
           "senderId": "user_1", "folderId": folder, "templateId": template, "reminderEnabled": status in ("sent", "delivered"),
           "reminderDays": 3, "reminderFrequency": 2, "documents": docs, "recipients": recipients,
           "fields": sig_fields(eid, docs[0]["id"], [r for r in recipients if r["role"] == "signer"]) if docs else [],
           "history": h}
    if void_reason:
        env["voidReason"] = void_reason
    if sent:  # pre-existing sends carry the same immutable snapshot the patched mock writes
        env["sentSnapshot"] = snapshot(env, sent)
        h[1]["snapshot"] = env["sentSnapshot"]
    return env


def snapshot(env, ts):
    return {"sentAt": ts, "subject": env["subject"], "message": env["message"],
            "documents": [{"id": d["id"], "name": d["name"], "fileSize": d.get("fileSize")} for d in env["documents"]],
            "recipients": [{"id": r["id"], "name": r["name"], "email": r["email"], "role": r["role"],
                            "routingOrder": r["routingOrder"]} for r in env["recipients"]]}


SUMMIT_ENV = {"venue": "env_hb_venue", "catering": "env_hb_catering", "av": "env_hb_av", "shuttle": "env_hb_shuttle",
              "floral": "env_hb_floral", "photo": "env_hb_photo", "band": "env_hb_band"}
DUP_VENUE = "env_hb_venue_2"
WEDDING = ["env_mw_floral", "env_mw_venue"]


def build_docusign(sizes):
    envs = []
    created = "2026-11-12T22:10:00.000Z"
    for key in ["catering", "av", "floral", "photo", "band"]:
        t, eid = V[key], SUMMIT_ENV[key]
        r = [recip(f"rec_{eid}_1", t["signer"], 1), recip(f"rec_{eid}_2", t["client"], 2)]
        envs.append(envelope(eid, summit_subject(key, t), draft_message(key, t), [ds_doc(eid, DOCS[DRAFT_DOC[key]], sizes)], r,
                             "draft", created))
    # Theo sent the shuttle contract yesterday morning, still on the pre-move dates and v1.
    t, eid = V["shuttle"], SUMMIT_ENV["shuttle"]
    r = [recip(f"rec_{eid}_1", t["signer"], 1, "delivered", delivered="2026-11-17T16:05:00.000Z", viewed="2026-11-17T23:31:00.000Z"),
         recip(f"rec_{eid}_2", t["client"], 2)]
    sh = envelope(eid, summit_subject("shuttle", t), draft_message("shuttle", t), [ds_doc(eid, DOCS["shuttle_v1"], sizes)], r,
                  "delivered", "2026-11-09T19:20:00.000Z", sent="2026-11-17T16:05:00.000Z", viewed="2026-11-17T23:31:00.000Z")
    sh["history"][1]["actorName"], sh["history"][1]["actorEmail"] = THEO
    envs.append(sh)
    # Venue: signed and completed on Nov 12; plus Theo's accidental second draft of it.
    t, eid = TRUTH["venue"], SUMMIT_ENV["venue"]
    r = [recip(f"rec_{eid}_1", t["signer"], 1, "signed", signed="2026-11-11T17:02:00.000Z", viewed="2026-11-10T16:40:00.000Z",
               delivered="2026-11-09T18:00:00.000Z"),
         recip(f"rec_{eid}_2", t["client"], 2, "signed", signed="2026-11-12T19:45:00.000Z", viewed="2026-11-12T19:30:00.000Z",
               delivered="2026-11-11T17:02:00.000Z")]
    envs.append(envelope(eid, summit_subject("venue", t), draft_message("venue", t), [ds_doc(eid, DOCS["venue"], sizes)], r,
                         "completed", "2026-11-09T17:40:00.000Z", sent="2026-11-09T18:00:00.000Z",
                         viewed="2026-11-10T16:40:00.000Z", completed="2026-11-12T19:45:00.000Z"))
    r = [recip(f"rec_{DUP_VENUE}_1", t["signer"], 1), recip(f"rec_{DUP_VENUE}_2", t["client"], 2)]
    envs.append(envelope(DUP_VENUE, summit_subject("venue", t), draft_message("venue", t), [ds_doc(DUP_VENUE, DOCS["venue"], sizes)],
                         r, "draft", "2026-11-12T22:40:00.000Z"))
    # Marlowe-Chen wedding (another client, June 2027) - drafts waiting on the couple.
    hazel = V["floral"]["signer"]
    envs.append(envelope("env_mw_floral", "Marlowe-Chen Wedding - Floral Agreement - Bloom & Vine Florals",
                         "Hi Hazel, here is the floral agreement for the Marlowe-Chen wedding (June 12, 2027, El Encanto). "
                         "Contract total $9,400.00. Thanks, Nadia",
                         [ds_doc("env_mw_floral", "Bloom_Vine_Floral_Agreement_MarloweChen.pdf", sizes)],
                         [recip("rec_mw_f1", hazel, 1), recip("rec_mw_f2", ("Olivia Marlowe", "olivia.marlowe@gmail.com"), 2)],
                         "draft", "2026-11-06T20:15:00.000Z"))
    envs.append(envelope("env_mw_venue", "Marlowe-Chen Wedding - Venue Agreement - El Encanto",
                         "Hi Renata, venue agreement for June 12, 2027 attached. Thanks, Nadia",
                         [ds_doc("env_mw_venue", "El_Encanto_Wedding_Agreement_MarloweChen.pdf", sizes)],
                         [recip("rec_mw_v1", ("Renata Solis", "rsolis@elencanto.example"), 1),
                          recip("rec_mw_v2", ("Olivia Marlowe", "olivia.marlowe@gmail.com"), 2)],
                         "draft", "2026-11-06T20:30:00.000Z"))
    # Past events (noise): completed / voided / declined.
    past = [
        ("env_tc_cater", "Tidewater Credit Union Holiday Party 2026 - Catering Agreement - Coastline Catering Co.",
         ("Maria Delgado", "maria@coastlinecatering.com"), ("Rob Tanaka", "rtanaka@tidewatercu.org"), "completed", "2026-10-02T17:00:00.000Z"),
        ("env_tc_venue", "Tidewater Credit Union Holiday Party 2026 - Venue Agreement - The Granada Loft",
         ("June Park", "events@granadaloft.example"), ("Rob Tanaka", "rtanaka@tidewatercu.org"), "completed", "2026-09-21T17:00:00.000Z"),
        ("env_oj_lodge", "Ojai Leadership Retreat - Lodging Agreement - Ojai Valley Ranch",
         ("Peter Vance", "pvance@ojaivalleyranch.example"), ("Sana Iqbal", "sana.iqbal@quillworks.example"), "completed", "2026-08-30T17:00:00.000Z"),
        ("env_oj_av", "Ojai Leadership Retreat - AV Agreement - Coastal Stageworks",
         ("Priya Raman", "priya@coastalstageworks.com"), ("Sana Iqbal", "sana.iqbal@quillworks.example"), "completed", "2026-08-28T17:00:00.000Z"),
        ("env_oj_photo", "Ojai Leadership Retreat - Photo Agreement - Sandpiper Photo & Film",
         ("Jonah Reyes", "jonah@sandpiperphoto.com"), ("Sana Iqbal", "sana.iqbal@quillworks.example"), "completed", "2026-08-28T18:00:00.000Z"),
        ("env_hb_av_old", "Halvorsen Leadership Summit 2027 - AV Production Agreement - Lumen AV Productions",
         ("Greg Whitfield", "greg.whitfield@lumenav.com"), DANIEL, "voided", "2026-10-20T17:00:00.000Z"),
        ("env_gv_dj", "Goleta Valley Gala 2026 - Entertainment Agreement - Harbor Lights Entertainment",
         ("Marcus Bell", "marcus@harborlightsband.com"), ("Amy Chu", "amy.chu@goletavalleyfoundation.example"), "declined", "2026-09-05T17:00:00.000Z"),
        ("env_sy_tasting", "Santa Ynez Wine Weekend - Tasting Room Agreement - Vista Oaks Winery",
         ("Carla Mendes", "carla@vistaoaks.example"), ("Ben Shaw", "ben.shaw@redlineventures.example"), "completed", "2026-07-14T17:00:00.000Z"),
    ]
    for eid, subj, v, c, status, sent in past:
        r = [recip(f"rec_{eid}_1", v, 1, "signed" if status == "completed" else "delivered", signed=sent if status == "completed" else None),
             recip(f"rec_{eid}_2", c, 2, "signed" if status == "completed" else "created", signed=sent if status == "completed" else None)]
        comp = sent.replace("T17", "T23") if status == "completed" else None
        voided = "2026-10-22T18:00:00.000Z" if status == "voided" else None
        e = envelope(eid, subj, f"Hi {v[0].split()[0]}, agreement attached for signature. Thanks, Nadia",
                     [ds_doc(eid, subj.split(" - ")[-2].replace(" ", "_").replace("&", "and") + ".pdf", sizes)], r,
                     status, sent.replace("T17", "T16"), sent=sent, completed=comp, voided=voided,
                     void_reason="Quote superseded - Lumen reissuing with the 3-room breakout package" if voided else None)
        if status == "declined":
            e["declinedAt"] = "2026-09-07T20:00:00.000Z"
            e["recipients"][0].update(status="declined", declinedAt="2026-09-07T20:00:00.000Z", declineReason="Date no longer available")
            e["history"].append(hist(eid, 11, "2026-09-07T20:00:00.000Z", "declined", "Marcus Bell declined: Date no longer available", v))
        envs.append(e)

    contacts = [
        ("ct_1", "Maria Delgado", "maria@coastlinecatering.com", "Coastline Catering Co.", "Owner"),
        ("ct_2", "Greg Whitfield", "greg.whitfield@lumenav.com", "Lumen AV Productions", "Account Manager"),
        ("ct_3", "Priya Raman", "priya@coastalstageworks.com", "Coastal Stageworks", "Production Manager"),
        ("ct_4", "Luis Ortega", "luis@pacificshuttlepartners.com", "Pacific Shuttle Partners", "Operations"),
        ("ct_5", "Hazel Kim", "hazel@bloomandvine.com", "Bloom & Vine Florals", "Lead Designer"),
        ("ct_6", "Jonah Reyes", "jonah@sandpiperphoto.com", "Sandpiper Photo & Film", "Owner"),
        ("ct_7", "Marcus Bell", "marcus@harborlightsband.com", "Harbor Lights Entertainment", "Bandleader"),
        ("ct_8", "Elise Brandt", ELISE[1], "Halvorsen Biotech", "Director, Corporate Events"),
        ("ct_9", "Daniel Moreau", DANIEL[1], "Halvorsen Biotech", "Chief Financial Officer"),
        ("ct_10", "Camille Duarte", "cduarte@mirasolsb.com", "Mirasol Hotel Santa Barbara", "Director of Sales"),
        ("ct_11", "Olivia Marlowe", "olivia.marlowe@gmail.com", None, None),
        ("ct_12", "Rob Tanaka", "rtanaka@tidewatercu.org", "Tidewater Credit Union", "HR Manager"),
        ("ct_13", "Sana Iqbal", "sana.iqbal@quillworks.example", "Quillworks", "Chief of Staff"),
        ("ct_14", "Theo Marsh", THEO[1], "Brightline Events", "Planner"),
    ]
    templates = [{
        "id": "tmpl_vendor", "name": "Brightline Vendor Agreement (2 signers)", "description": "Vendor signs first, client signatory second.",
        "createdAt": "2025-01-14T18:00:00.000Z", "lastUsedAt": "2026-11-12T22:10:00.000Z", "usageCount": 31, "ownerId": "user_1",
        "shared": True, "documents": [{"id": "tdoc_1", "name": "Vendor_Agreement_Template.pdf", "pageCount": 3, "order": 1,
                                       "fileUrl": file_url("Vendor_Agreement_Template.png"), "fileType": "pdf"}],
        "roles": [{"id": "role_v", "name": "Vendor", "role": "signer", "routingOrder": 1},
                  {"id": "role_c", "name": "Client signatory", "role": "signer", "routingOrder": 2}],
        "fields": [{"id": "tf1", "type": "signature", "roleId": "role_v", "documentId": "tdoc_1", "pageNumber": 1, "x": 300, "y": 880,
                    "width": 200, "height": 50, "required": True, "label": ""},
                   {"id": "tf2", "type": "signature", "roleId": "role_c", "documentId": "tdoc_1", "pageNumber": 1, "x": 300, "y": 940,
                    "width": 200, "height": 50, "required": True, "label": ""}]}]
    audit = []
    for e in envs:
        audit.append({"id": f"aud_{e['id']}_c", "timestamp": e["createdAt"], "action": "CREATE_ENVELOPE",
                      "details": f"Created envelope: {e['subject']}", "envelopeId": e["id"]})
        if e["sentAt"]:
            audit.append({"id": f"aud_{e['id']}_s", "timestamp": e["sentAt"], "action": "SEND_ENVELOPE",
                          "details": f"Sent envelope {e['id']}", "envelopeId": e["id"]})
    audit.sort(key=lambda a: a["timestamp"], reverse=True)
    return {
        "user": {"id": "user_1", "name": NADIA[0], "email": NADIA[1], "title": "Founder & Lead Planner", "company": "Brightline Events",
                 "avatar": avatar(NADIA[0]), "signatureDataUrl": None, "initialsDataUrl": None, "memberSince": "2021-03-02",
                 "settings": {"defaultReminderDays": 3, "defaultExpirationDays": 120, "timezone": TZ}},
        "envelopes": envs,
        "templates": templates,
        "folders": [{"id": "fold_hb", "name": "Halvorsen Summit 2027", "parentFolder": None, "createdAt": "2026-10-01T17:00:00.000Z"},
                    {"id": "fold_mw", "name": "Marlowe-Chen Wedding", "parentFolder": None, "createdAt": "2026-10-15T17:00:00.000Z"}],
        "contacts": [{"id": i, "name": n, "email": e, "company": c, "title": t} for i, n, e, c, t in contacts],
        "auditLog": audit,
    }


# ---------------------------------------------------------------- Airtable
F = {  # field id -> (name, type, extra)
    "fld_vendor": ("Vendor", "text", {"primary": True}),
    "fld_service": ("Service", "single_select", {"options": ["Venue", "Catering", "AV & Staging", "Transportation", "Florals",
                                                             "Photo & Video", "Entertainment", "Signage", "Rentals"]}),
    "fld_signer": ("Vendor Signer", "text", {}),
    "fld_signer_email": ("Signer Email", "email", {}),
    "fld_client_signer": ("Client Signer", "single_select", {"options": ["Elise Brandt", "Daniel Moreau"]}),
    "fld_total": ("Contract Total", "currency", {}),
    "fld_deposit": ("Deposit", "currency", {}),
    "fld_due": ("Deposit Due", "date", {}),
    "fld_dates": ("Service Dates", "text", {}),
    "fld_version": ("Contract Version", "text", {}),
    "fld_status": ("Envelope Status", "single_select", {"options": ["Not started", "Draft ready", "Sent", "Signed", "On hold", "Voided"]}),
    "fld_sent": ("Sent On", "date", {}),
    "fld_notes": ("Notes", "long_text", {}),
}
COLORS = ["bg-blue-100 text-blue-800", "bg-green-100 text-green-800", "bg-yellow-100 text-yellow-800", "bg-purple-100 text-purple-800",
          "bg-pink-100 text-pink-800", "bg-orange-100 text-orange-800", "bg-red-100 text-red-800", "bg-gray-100 text-gray-800"]
REC = {"venue": "rec_hb_venue", "catering": "rec_hb_catering", "av": "rec_hb_av", "shuttle": "rec_hb_shuttle",
       "floral": "rec_hb_floral", "photo": "rec_hb_photo", "band": "rec_hb_band", "signage": "rec_hb_signage", "rentals": "rec_hb_rentals"}


def at_fields(spec):
    out = []
    for fid, (name, typ, extra) in spec.items():
        f = {"id": fid, "name": name, "type": typ}
        if extra.get("primary"):
            f["primary"] = True
        if "options" in extra:
            f["options"] = [{"id": f"{fid}_o{i}", "name": o, "color": COLORS[i % len(COLORS)]} for i, o in enumerate(extra["options"])]
        out.append(f)
    return out


def vendor_row(key, t, status, sent=None, notes=""):
    return {"fld_vendor": t["vendor"], "fld_service": t["service"], "fld_signer": t["signer"][0], "fld_signer_email": t["signer"][1],
            "fld_client_signer": t["client"][0], "fld_total": t["total"], "fld_deposit": t["deposit"], "fld_due": t["due"],
            "fld_dates": t["dates"], "fld_version": t["version"], "fld_status": status, "fld_sent": sent, "fld_notes": notes}


def build_airtable():
    rows = {
        "venue": vendor_row("venue", TRUTH["venue"], "Signed", "2026-11-09", "Fully signed 11/12. Deposit invoice received."),
        "catering": vendor_row("catering", V["catering"], "Draft ready", None, "Draft in DocuSign 11/12."),
        "av": vendor_row("av", V["av"], "Draft ready", None, "Reissued quote (3 breakouts). Draft in DocuSign 11/12."),
        "shuttle": vendor_row("shuttle", V["shuttle"], "Sent", "2026-11-17", "Sent 11/17 so Luis can sign before Thanksgiving week."),
        "floral": vendor_row("floral", V["floral"], "Draft ready", None, "Protea palette per Elise."),
        "photo": vendor_row("photo", V["photo"], "Draft ready", None, ""),
        "band": vendor_row("band", V["band"], "Draft ready", None, "Gala band."),
        "signage": {"fld_vendor": "Seaside Signs & Print", "fld_service": "Signage", "fld_signer": "Tom Alvarez",
                    "fld_signer_email": "tom@seasidesigns.example", "fld_client_signer": "Elise Brandt", "fld_total": None,
                    "fld_deposit": None, "fld_due": None, "fld_dates": "Jan 21-23, 2027", "fld_version": "",
                    "fld_status": "Not started", "fld_sent": None, "fld_notes": "Waiting on final quote; no contract yet."},
        "rentals": {"fld_vendor": "Gold Coast Event Rentals", "fld_service": "Rentals", "fld_signer": "Dana Whitaker",
                    "fld_signer_email": "orders@goldcoastrentals.example", "fld_client_signer": "Elise Brandt", "fld_total": 3180,
                    "fld_deposit": 3180, "fld_due": "2026-12-20", "fld_dates": "Jan 21-23, 2027", "fld_version": "online order",
                    "fld_status": "Signed", "fld_sent": None, "fld_notes": "Ordered through their portal (no DocuSign)."},
    }
    order = ["venue", "catering", "av", "shuttle", "floral", "photo", "band", "signage", "rentals"]
    summit = {"id": "tbl_hb_vendors", "name": "Halvorsen Summit Vendors", "baseId": "base_brightline", "fields": at_fields(F),
              "records": [{"id": REC[k], "createdTime": "2026-10-01T17:00:00.000Z", "fields": rows[k]} for k in order],
              "views": [{"id": "view_hb_grid", "name": "All vendors", "type": "grid", "filters": [], "sorts": [], "groupBy": [],
                         "hiddenFieldIds": [], "fieldWidths": {}, "rowHeight": "short"},
                        {"id": "view_hb_kanban", "name": "By envelope status", "type": "kanban", "groupFieldId": "fld_status"}],
              "activeViewId": "view_hb_grid"}
    wf = {k: v for k, v in F.items() if k not in ("fld_client_signer",)}
    wed_rows = [
        ("rec_mw_1", "El Encanto", "Venue", "Renata Solis", "rsolis@elencanto.example", 22000, "Draft ready"),
        ("rec_mw_2", "Bloom & Vine Florals", "Florals", "Hazel Kim", "hazel@bloomandvine.com", 9400, "Draft ready"),
        ("rec_mw_3", "Sandpiper Photo & Film", "Photo & Video", "Jonah Reyes", "jonah@sandpiperphoto.com", 6900, "Not started"),
        ("rec_mw_4", "Coastline Catering Co.", "Catering", "Maria Delgado", "maria@coastlinecatering.com", 18500, "Not started"),
    ]
    wedding = {"id": "tbl_mw_vendors", "name": "Marlowe-Chen Wedding Vendors", "baseId": "base_brightline", "fields": at_fields(wf),
               "records": [{"id": rid, "createdTime": "2026-10-15T17:00:00.000Z",
                            "fields": {"fld_vendor": n, "fld_service": s, "fld_signer": sg, "fld_signer_email": em, "fld_total": tot,
                                       "fld_deposit": round(tot * 0.3), "fld_due": "2027-01-15", "fld_dates": "Jun 12, 2027",
                                       "fld_version": "v1", "fld_status": st, "fld_sent": None,
                                       "fld_notes": "Hold until the couple confirms the final count."}}
                           for rid, n, s, sg, em, tot, st in wed_rows],
               "views": [{"id": "view_mw_grid", "name": "Grid view", "type": "grid"}], "activeViewId": "view_mw_grid"}
    cf = {"fld_c_name": ("Name", "text", {"primary": True}), "fld_c_org": ("Organization", "text", {}),
          "fld_c_role": ("Role", "text", {}), "fld_c_email": ("Email", "email", {}), "fld_c_phone": ("Phone", "phone", {})}
    people = [("Elise Brandt", "Halvorsen Biotech", "Director, Corporate Events (day-to-day client)", ELISE[1], "(805) 555-0142"),
              ("Daniel Moreau", "Halvorsen Biotech", "CFO", DANIEL[1], "(805) 555-0107"),
              ("Kara Lindgren", "Halvorsen Biotech", "Executive Assistant to the CEO", "kara.lindgren@halvorsenbio.com", "(805) 555-0150"),
              ("Olivia Marlowe", "Marlowe-Chen Wedding", "Bride", "olivia.marlowe@gmail.com", "(310) 555-0188"),
              ("Rob Tanaka", "Tidewater Credit Union", "HR Manager", "rtanaka@tidewatercu.org", "(805) 555-0119")]
    contacts = {"id": "tbl_contacts", "name": "Client Contacts", "baseId": "base_brightline", "fields": at_fields(cf),
                "records": [{"id": f"rec_c{i}", "createdTime": "2026-01-05T17:00:00.000Z",
                             "fields": dict(zip(cf, p))} for i, p in enumerate(people)],
                "views": [{"id": "view_c_grid", "name": "Grid view", "type": "grid"}], "activeViewId": "view_c_grid"}
    me = {"id": "user_1", "name": NADIA[0], "email": NADIA[1], "avatar": avatar(NADIA[0])}
    return {
        "currentUser": me,
        "collaborators": [me, {"id": "user_2", "name": THEO[0], "email": THEO[1], "avatar": avatar(THEO[0])}],
        "bases": {"base_brightline": {"id": "base_brightline", "name": "Brightline Events - 2027 Season", "color": "bg-teal-600",
                                      "tables": ["tbl_hb_vendors", "tbl_mw_vendors", "tbl_contacts"]}},
        "tables": {"tbl_hb_vendors": summit, "tbl_mw_vendors": wedding, "tbl_contacts": contacts},
        "activeBaseId": "base_brightline", "activeTableId": "tbl_hb_vendors",
        "ui": {"searchQuery": ""}, "activityLog": [],
    }


# ---------------------------------------------------------------- Yahoo Mail
def ym(mid, sender, subject, body, date, *, folder="inbox", to=None, cc=None, category="primary", read=True, conv=None,
       attachments=None, reply_to_id=None):
    received = folder != "sent"
    return {"id": mid, "conversationId": conv or f"cnv_{mid}", "folderId": folder, "previousFolderId": None,
            "category": category if received else None, "from": {"name": sender[0], "email": sender[1]},
            "to": [{"name": t[0], "email": t[1]} for t in (to or [NADIA])], "cc": [{"name": t[0], "email": t[1]} for t in (cc or [])],
            "bcc": [], "replyTo": None, "subject": subject, "body": body, "snippet": " ".join(body.split())[:140], "bodyHtml": None,
            "date": date, "isRead": read, "isStarred": False, "isDraft": False, "status": "received" if received else "sent",
            "attachments": attachments or [], "hasImages": False, "listUnsubscribe": category in ("newsletters", "offers"),
            "summary": None, "orderInfo": None, "travelInfo": None, "inReplyToId": reply_to_id, "forwardedFromId": None,
            "replyType": "reply" if reply_to_id and not received else None, "repliedAt": None, "forwardedAt": None,
            "sentAt": None if received else date, "movedAt": None, "appliedFilterId": None, "createdAt": date, "updatedAt": None}


def att(aid, name, sizes):
    return {"id": aid, "name": name, "size": sizes[name], "mimeType": "application/pdf", "kind": "document", "url": file_url(name),
            "source": "seed", "sourceMessageId": None, "sourceAttachmentId": None, "uploadedAt": None}


def build_yahoo(sizes):
    LUIS, MARIA, GREG, PRIYA = V["shuttle"]["signer"], V["catering"]["signer"], V["av"]["signer"], TRUTH["av"]["signer"]
    HAZEL, JONAH, MARCUS = V["floral"]["signer"], V["photo"]["signer"], V["band"]["signer"]
    DSN = ("DocuSign", "dse_na4@docusign.net")
    m = [
        ym("msg_001", ELISE, "Signing authority for summit vendor agreements",
           "Hi Nadia,\n\nQuick reminder before the vendor contracts go out. Under our delegation of authority I can sign vendor agreements "
           "up to $25,000 total contract value. Anything above $25,000 has to be signed by Daniel Moreau, our CFO "
           "(daniel.moreau@halvorsenbio.com) - please route those to him instead of me, not to both of us.\n\n"
           "And as before, please have the vendor sign first and put our signer last in the routing order.\n\nThanks!\nElise",
           "2026-11-05T17:12:00.000Z", cc=[DANIEL]),
        ym("msg_002", ELISE, "Summit dates moving one day - now Jan 21-23",
           "Hi Nadia,\n\nMirasol confirmed the swap, so the summit moves one day later:\n\n"
           "Thu Jan 21 - arrivals and welcome reception\nFri Jan 22 - general sessions and breakouts\nSat Jan 23 - awards gala\n\n"
           "(Previously Wed Jan 20 to Fri Jan 22.) Camille says the venue agreement already reflects the new dates. "
           "Can you make sure every other vendor contract does too?\n\nElise",
           "2026-11-10T18:40:00.000Z"),
        ym("msg_003", ELISE, "Re: Summit vendor budget",
           "Nadia - finance went through the vendor list. Everything is approved as quoted except entertainment: "
           "we're capping the gala band at $6,000 all-in. Could you ask Harbor Lights for a smaller package before we sign "
           "anything with them?\n\nElise",
           "2026-11-12T20:05:00.000Z", conv="cnv_budget"),
        ym("msg_004", THEO, "Summit DocuSign drafts",
           "Hi Nadia,\n\nI built the DocuSign drafts for the summit vendors off the tracker this afternoon (catering, AV, florals, "
           "photo/video, entertainment), all on our usual vendor-then-client routing. Mirasol is fully signed as of today. "
           "Shuttle I'll send separately once Luis confirms his coach count.\n\nTheo",
           "2026-11-12T23:20:00.000Z", read=True),
        ym("msg_005", GREG, "Lumen AV - account handover",
           "Hi Nadia,\n\nI wanted to let you know personally that Friday is my last day at Lumen. Priya Raman, our Director of "
           "Operations, is taking over the Halvorsen summit and will be signing the agreement on our side - please send the "
           "contract to her at priya.raman@lumenav.com rather than to me. Nothing changes on scope or pricing.\n\n"
           "It's been a pleasure working with you!\nGreg Whitfield\nLumen AV Productions",
           "2026-11-13T19:02:00.000Z", cc=[PRIYA]),
        ym("msg_006", ELISE, "Final headcount for the summit",
           "Hi Nadia, RSVPs are closed - final headcount is 155 (up from the 140 we planned). Please let Coastline know. Elise",
           "2026-11-14T00:30:00.000Z"),
        ym("msg_007", JONAH, "Halvorsen summit - all set on our end",
           "Hi Nadia, the shot list looks great and we're holding all three days. Send the agreement over whenever you're ready. Jonah",
           "2026-11-15T18:15:00.000Z"),
        ym("msg_008", HAZEL, "Marlowe-Chen wedding florals",
           "Hi Nadia! The Marlowe-Chen floral agreement looks perfect on our side - go ahead and send it whenever Olivia is ready. Hazel",
           "2026-11-16T17:40:00.000Z"),
        ym("msg_009", MARIA, "Halvorsen summit - revised catering agreement (155 guests)",
           "Hi Nadia,\n\nThanks for the updated count. I've revised the agreement for 155 guests - attached is the clean v3 for "
           "signature, plus a redline against v2 so you can see exactly what changed. Deposit due date is unchanged.\n\n"
           "Best,\nMaria Delgado\nCoastline Catering Co.",
           "2026-11-16T21:25:00.000Z",
           attachments=[att("att_009a", DOCS["catering_v3"], sizes), att("att_009b", DOCS["catering_redline"], sizes)]),
        ym("msg_010", MARCUS, "Re: Halvorsen gala - smaller package",
           "Hi Nadia,\n\nNo problem - we can do the gala as a four-piece (vocals, keys, bass, drums) for $5,800 all-in, and I've "
           "moved it to Saturday January 23 per the new schedule. Revised agreement v2 attached; please use that one.\n\nMarcus\n"
           "Harbor Lights Entertainment",
           "2026-11-16T23:50:00.000Z", attachments=[att("att_010a", DOCS["band_v2"], sizes)]),
        ym("msg_011", THEO, "Shuttle contract sent",
           "Morning - Luis confirmed two coaches so I sent the Pacific Shuttle agreement from DocuSign so he can sign before "
           "their office closes for Thanksgiving week. I'm at the Ojai site visit through Friday with patchy signal; the other "
           "summit drafts are yours to review and send. Theo",
           "2026-11-17T16:20:00.000Z", read=True),
        ym("msg_012", DSN, "Luis Ortega viewed: Halvorsen Leadership Summit 2027 - Ground Transportation Agreement - Pacific Shuttle Partners",
           "Luis Ortega viewed the envelope sent by Theo Marsh (Brightline Events).", "2026-11-17T23:31:00.000Z", category="primary"),
        ym("msg_013", LUIS, "Re: DocuSign - Ground Transportation Agreement",
           "Hi Nadia,\n\nI just opened the DocuSign Theo sent this morning, but it's still our v1 with the old Jan 20-22 service dates. "
           "We updated the agreement for Jan 21-23 last week - v2 is attached. Same price, $9,750, but the deposit is now due "
           "December 8. I'd rather not sign the old one; can you send v2 instead?\n\nThanks,\nLuis Ortega\nPacific Shuttle Partners",
           "2026-11-17T23:44:00.000Z", attachments=[att("att_013a", DOCS["shuttle_v2"], sizes)]),
        ym("msg_014", HAZEL, "Halvorsen summit florals - please hold",
           "Hi Nadia,\n\nCould you hold off on sending the Halvorsen floral agreement for now? Our protea grower isn't sure they can "
           "deliver in late January and I don't want you to sign something we'd have to change. I'll confirm one way or the other "
           "by Friday 11/20.\n\nHazel\nBloom & Vine Florals",
           "2026-11-18T01:10:00.000Z", read=False),
        ym("msg_015", DSN, "Completed: Halvorsen Leadership Summit 2027 - Venue Agreement - Mirasol Hotel Santa Barbara",
           "All parties have completed the envelope. Camille Duarte and Daniel Moreau signed.", "2026-11-12T19:46:00.000Z"),
        ym("msg_016", ("Camille Duarte", "cduarte@mirasolsb.com"), "Mirasol - deposit invoice",
           "Hi Nadia, thanks for the signed agreement. Deposit invoice #MS-20931 for $14,460.00 is attached in our portal, due Nov 20. Camille",
           "2026-11-13T17:05:00.000Z"),
        ym("msg_017", ("Olivia Marlowe", "olivia.marlowe@gmail.com"), "guest count update",
           "Hi Nadia! Still waiting on two families to RSVP - we'll have the final count by Dec 1. Can we hold the contracts until then? xo Olivia",
           "2026-11-15T03:22:00.000Z"),
        ym("msg_018", ("Sana Iqbal", "sana.iqbal@quillworks.example"), "Ojai retreat - photos",
           "Nadia, the team loved the gallery. Thanks again for a smooth retreat! Sana", "2026-11-11T20:00:00.000Z"),
        ym("msg_019", ("Rob Tanaka", "rtanaka@tidewatercu.org"), "Holiday party timeline",
           "Hi Nadia, attaching nothing yet - just confirming doors at 6:30 on Dec 12. Rob", "2026-11-16T16:45:00.000Z"),
        ym("msg_020", ("Gold Coast Event Rentals", "orders@goldcoastrentals.example"), "Order GC-55812 confirmed",
           "Your order GC-55812 (Halvorsen Biotech, Jan 21-23, 2027) is confirmed. Total $3,180.00.", "2026-11-08T15:00:00.000Z"),
        ym("msg_021", ("Seaside Signs & Print", "tom@seasidesigns.example"), "Summit signage quote - coming Monday",
           "Hi Nadia, I'll have the signage quote to you Monday 11/23 once the printer confirms vinyl pricing. Tom", "2026-11-17T20:10:00.000Z"),
        ym("msg_022", ("Event Planner Weekly", "news@eventplannerweekly.example"), "10 venue trends for 2027",
           "Biophilic ballrooms, silent discos and more.", "2026-11-17T13:00:00.000Z", category="newsletters"),
        ym("msg_023", ("Yahoo", "no-reply@yahoo.com"), "Your account storage is 62% full",
           "Upgrade to Yahoo Mail Plus for more storage.", "2026-11-14T12:00:00.000Z", category="offers"),
        ym("msg_024", ("Costco Business Center", "deals@costcobusiness.example"), "Holiday catering trays",
           "Order party platters for pickup.", "2026-11-16T12:00:00.000Z", category="offers"),
        ym("msg_025", ("LinkedIn", "messages-noreply@linkedin.example"), "Greg Whitfield started a new position",
           "Greg Whitfield is now Senior Producer at Coastal Stageworks.", "2026-11-17T15:00:00.000Z", category="social"),
        ym("msg_026", ("Santa Barbara Chamber", "events@sbchamber.example"), "Mixer this Thursday",
           "Join us at the harbor for networking.", "2026-11-16T14:00:00.000Z", category="newsletters"),
        ym("msg_027", NADIA, "Re: Summit vendor budget",
           "Thanks Elise - I'll ask Harbor Lights for a four-piece option and loop back. Nadia", "2026-11-12T21:00:00.000Z",
           folder="sent", to=[ELISE], conv="cnv_budget", reply_to_id="msg_003"),
        ym("msg_028", NADIA, "Halvorsen gala - smaller package?",
           "Hi Marcus, Halvorsen capped the gala entertainment at $6,000 all-in. Could you put together a smaller package? "
           "Also note the gala moved to Saturday Jan 23. Thanks, Nadia", "2026-11-13T17:30:00.000Z", folder="sent", to=[MARCUS]),
        ym("msg_029", NADIA, "Updated headcount: 155",
           "Hi Maria, Halvorsen's final count is 155. Can you send a revised agreement? Thanks, Nadia", "2026-11-14T01:00:00.000Z",
           folder="sent", to=[MARIA]),
    ]
    m[9]["conversationId"] = "cnv_msg_028"
    m[27]["conversationId"] = "cnv_msg_028"
    m[8]["conversationId"] = "cnv_msg_029"
    m[28]["conversationId"] = "cnv_msg_029"
    for x in m:
        if x["folderId"] == "inbox" and x["date"] < "2026-11-17":
            x["isRead"] = True
    fixed = "2024-01-10T10:00:00.000Z"
    folders = [{"id": fid, "name": n, "type": "system", "parentId": None, "order": i, "createdAt": fixed}
               for i, (fid, n) in enumerate([("inbox", "Inbox"), ("draft", "Drafts"), ("sent", "Sent"), ("archive", "Archive"),
                                             ("spam", "Spam"), ("trash", "Trash")])]
    folders += [{"id": "fld_halvorsen", "name": "Halvorsen Summit", "type": "user", "parentId": None, "order": 0, "createdAt": fixed, "updatedAt": None},
                {"id": "fld_marlowe", "name": "Marlowe-Chen Wedding", "type": "user", "parentId": None, "order": 1, "createdAt": fixed, "updatedAt": None}]
    people = [ELISE, DANIEL, THEO, MARIA, GREG, PRIYA, LUIS, HAZEL, JONAH, MARCUS, ("Camille Duarte", "cduarte@mirasolsb.com")]
    contacts = [{"id": f"ct_{i + 1:04d}", "firstName": p[0].split()[0], "lastName": p[0].split()[1], "nickname": "",
                 "emails": [{"type": "work", "address": p[1]}], "phones": [], "addresses": [], "company": "", "jobTitle": "",
                 "birthday": "", "website": "", "notes": "", "isFavorite": i < 3, "avatarColor": "#5B8DB8", "source": "manual",
                 "createdAt": fixed, "updatedAt": None} for i, p in enumerate(people)]
    return {
        "currentUser": {"id": "usr_nadia", "name": NADIA[0], "firstName": "Nadia", "email": NADIA[1], "aliases": [],
                        "avatarColor": "#2E7D6B", "jobTitle": "Founder & Lead Planner", "company": "Brightline Events",
                        "location": "Santa Barbara, CA", "storage": {"usedBytes": 13314398617, "totalBytes": 21474836480}},
        "folders": folders, "messages": m, "contacts": contacts, "contactLists": [], "filters": [],
        "blockedAddresses": [], "unsubscribes": [], "activityLog": [],
        "settings": {"appearance": {"theme": "light", "themeColor": "purple", "density": "comfortable", "messageLayout": "list"},
                     "inbox": {"categoriesEnabled": True, "defaultCategory": "primary", "showUnreadCount": True, "sort": "date_desc"},
                     "viewing": {"conversations": True, "showImages": "ask", "markAsRead": "immediately", "afterMove": "next"},
                     "writing": {"signature": {"enabled": True, "text": "Nadia Okafor\nBrightline Events - Santa Barbara\n(805) 555-0133"},
                                 "defaultFont": "sans-serif", "defaultFontSize": "medium", "defaultFrom": NADIA[1],
                                 "sendWithCtrlEnter": True, "linkPreviews": True},
                     "vacationResponse": {"enabled": False, "startDate": "", "endDate": "", "subject": "", "message": "",
                                          "onlyContacts": False, "updatedAt": None},
                     "notifications": {"browser": False, "sound": False}, "ai": {"messageSummaries": False},
                     "keyboardShortcuts": True, "rightPanel": {"open": False, "tab": "starred"},
                     "sidebar": {"compact": False, "viewsExpanded": True, "foldersExpanded": True, "moreExpanded": False}},
    }


# ---------------------------------------------------------------- golden mutations (mirror the patched mock)
def corrected_message(key, t):
    first = t["signer"][0].split()[0]
    extra = {"band": " Four-piece band for the awards gala on Saturday, January 23, 2027."}.get(key, "")
    return (f"Hi {first}, please review and sign the {t['service'].lower()} agreement for the Halvorsen Biotech Leadership Summit "
            f"(January 21-23, 2027, Mirasol Hotel Santa Barbara). Contract total ${money(t['total'])}; deposit of "
            f"${money(t['deposit'])} due {long_date(t['due'])}.{extra} Thanks, Nadia")


def uploaded_doc(doc_id, name, blobs, order=1):
    data = blobs[name]
    return {"id": doc_id, "name": name, "pageCount": 1, "order": order,
            "fileUrl": "data:application/pdf;base64," + base64.b64encode(data).decode(),
            "downloadUrl": f"/files/__SID__/up_{doc_id}.pdf", "fileType": "pdf", "fileSize": len(data),
            "contentType": "application/pdf", "storedName": f"up_{doc_id}.pdf"}


def send(env, ts=NOW):
    env["status"] = "sent"
    env["sentAt"] = ts
    env["lastActivityAt"] = ts
    env["expiresAt"] = "2027-03-18T18:40:00.000Z"
    for r in env["recipients"]:
        if r["status"] == "created":
            r["status"] = "sent"
    env["sentSnapshot"] = snapshot(env, ts)
    env["history"].append({"id": f"evt_{env['id']}_send_{len(env['history'])}", "timestamp": ts, "action": "sent",
                           "actorName": NADIA[0], "actorEmail": NADIA[1],
                           "details": f"Envelope sent to {len(env['recipients'])} recipient(s)", "snapshot": env["sentSnapshot"]})


def void(env, reason, ts=NOW):
    env.update(status="voided", voidedAt=ts, lastActivityAt=ts, voidReason=reason)
    env["history"].append({"id": f"evt_{env['id']}_void", "timestamp": ts, "action": "voided", "actorName": NADIA[0],
                           "actorEmail": NADIA[1], "details": f"Envelope voided: {reason}"})


def correct(env, recipients, ts=NOW):
    before = copy.deepcopy(env["recipients"])
    env["recipients"] = recipients
    env["lastActivityAt"] = ts
    env["history"].append({"id": f"evt_{env['id']}_corr", "timestamp": ts, "action": "corrected", "actorName": NADIA[0],
                           "actorEmail": NADIA[1], "details": "Envelope corrected - recipients updated",
                           "before": before, "after": copy.deepcopy(recipients)})


def audit(ds, action, eid, details):
    ds["auditLog"].insert(0, {"id": f"aud_g_{action}_{eid}", "timestamp": NOW, "action": action, "details": details, "envelopeId": eid})


def set_doc(env, doc):
    env["documents"] = [doc]
    signers = [r for r in env["recipients"] if r["role"] == "signer"]
    env["fields"] = sig_fields(env["id"] + "_g", doc["id"], signers)


def set_recipients(env, people):
    env["recipients"] = [recip(f"rec_{env['id']}_g{i}", p, i + 1) for i, p in enumerate(people)]
    env["fields"] = sig_fields(env["id"] + "_g", env["documents"][0]["id"], env["recipients"])


def apply_docusign(ds, blobs, plan):
    """plan[key] = dict(send=bool, doc=doc_key|None, people=[...]|None, message=str|None, correct_after=[...]|None);
    plan['shuttle'] = dict(void=bool, resend=dict(doc, people, message)|None); plan['extra_sends'] = [eids]."""
    envs = {e["id"]: e for e in ds["envelopes"]}
    for key in ["catering", "av", "floral", "photo", "band"]:
        p = plan.get(key)
        if not p or not p.get("send"):
            continue
        env = envs[SUMMIT_ENV[key]]
        if p.get("doc"):
            set_doc(env, uploaded_doc(f"doc_{env['id']}_up", DOCS[p["doc"]], blobs))
        if p.get("people"):
            set_recipients(env, p["people"])
        if p.get("message"):
            env["message"] = p["message"]
        send(env)
        audit(ds, "SEND_ENVELOPE", env["id"], f"Sent envelope {env['id']}")
        if p.get("correct_after"):
            correct(env, [recip(f"rec_{env['id']}_c{i}", pp, i + 1, "sent") for i, pp in enumerate(p["correct_after"])])
            audit(ds, "CORRECT_ENVELOPE", env["id"], f"Corrected envelope {env['id']}")
    sp = plan.get("shuttle") or {}
    if sp.get("void"):
        void(envs[SUMMIT_ENV["shuttle"]], "Wrong service dates (Jan 20-22) - reissuing v2 for Jan 21-23")
        audit(ds, "VOID_ENVELOPE", SUMMIT_ENV["shuttle"], "Voided envelope: wrong dates")
    if sp.get("resend"):
        r = sp["resend"]
        eid = "env_new_shuttle"
        new = {"id": eid, "subject": summit_subject("shuttle", TRUTH["shuttle"]), "message": r["message"], "status": "draft",
               "createdAt": NOW, "sentAt": None, "completedAt": None, "voidedAt": None, "declinedAt": None, "lastActivityAt": NOW,
               "expiresAt": None, "senderId": "user_1", "folderId": None, "templateId": None, "reminderEnabled": False,
               "reminderDays": 3, "reminderFrequency": 2, "documents": [uploaded_doc(f"doc_{eid}_up", DOCS[r["doc"]], blobs)],
               "recipients": [], "fields": [],
               "history": [{"id": f"evt_{eid}_1", "timestamp": NOW, "action": "created", "actorName": NADIA[0],
                            "actorEmail": NADIA[1], "details": "Envelope created"}]}
        set_recipients(new, r["people"])
        send(new)
        ds["envelopes"].append(new)
        audit(ds, "CREATE_ENVELOPE", eid, f"Created envelope: {new['subject']}")
        audit(ds, "SEND_ENVELOPE", eid, f"Sent envelope {eid}")
    for eid in plan.get("extra_sends", []):
        send(envs[eid])
        audit(ds, "SEND_ENVELOPE", eid, f"Sent envelope {eid}")


def golden_plan():
    T = TRUTH
    return {
        "catering": dict(send=True, doc="catering_v3", people=[T["catering"]["signer"], DANIEL], message=corrected_message("catering", T["catering"])),
        "av": dict(send=True, people=[T["av"]["signer"], DANIEL], message=corrected_message("av", T["av"])),
        "photo": dict(send=True),
        "band": dict(send=True, doc="band_v2", message=corrected_message("band", T["band"])),
        "shuttle": dict(void=True, resend=dict(doc="shuttle_v2", people=[T["shuttle"]["signer"], ELISE],
                                               message=corrected_message("shuttle", T["shuttle"]))),
    }


def apply_airtable(at, updates):
    recs = {r["id"]: r for r in at["tables"]["tbl_hb_vendors"]["records"]}
    for key, fields in updates.items():
        recs[REC[key]]["fields"].update(fields)


def golden_airtable_updates():
    T = TRUTH
    sent = {"fld_status": "Sent", "fld_sent": TODAY}
    return {
        "catering": {**sent, "fld_total": T["catering"]["total"], "fld_deposit": T["catering"]["deposit"],
                     "fld_client_signer": "Daniel Moreau", "fld_version": "v3"},
        "av": {**sent, "fld_signer": "Priya Raman", "fld_signer_email": "priya.raman@lumenav.com"},
        "shuttle": {**sent, "fld_version": "v2", "fld_dates": "Jan 21-23, 2027", "fld_due": "2026-12-08"},
        "floral": {"fld_status": "On hold"},
        "photo": dict(sent),
        "band": {**sent, "fld_total": 5800, "fld_deposit": 2900, "fld_version": "v2", "fld_dates": "Jan 23, 2027"},
    }


def csv_rows(truth=TRUTH, actions=ACTIONS):
    rows = [CSV_HEADER]
    for key in ["venue", "catering", "av", "shuttle", "floral", "photo", "band"]:
        t = truth[key]
        rows.append([t["vendor"], actions[key], f"{t['total']:.2f}", t["signer"][1], t["client"][1]])
    return rows


# ---------------------------------------------------------------- variants
def variant(seed, blobs, plan, at_updates, rows):
    ds, at, ym_ = copy.deepcopy(seed["docusign"]), copy.deepcopy(seed["airtable"]), copy.deepcopy(seed["yahoo_mail"])
    apply_docusign(ds, blobs, plan)
    apply_airtable(at, at_updates)
    return {"docusign": ds, "airtable": at, "yahoo_mail": ym_}, rows


def naive_variant(seed, blobs):
    """Trusts the drafts: sends every summit draft as built (incl. the held florals and the duplicate venue), leaves the shuttle."""
    plan = {k: dict(send=True) for k in ["catering", "av", "floral", "photo", "band"]}
    plan["extra_sends"] = [DUP_VENUE]
    sent = {"fld_status": "Sent", "fld_sent": TODAY}
    ups = {k: dict(sent) for k in ["catering", "av", "floral", "photo", "band"]}
    actions = {**ACTIONS, "shuttle": "sent", "floral": "sent"}
    return variant(seed, blobs, plan, ups, csv_rows(V, actions))


def slip_authority(seed, blobs):
    """Careful run, but keeps Elise on the revised catering contract ($26,350 > $25,000)."""
    plan = golden_plan()
    plan["catering"]["people"] = [TRUTH["catering"]["signer"], ELISE]
    ups = golden_airtable_updates()
    ups["catering"]["fld_client_signer"] = "Elise Brandt"
    truth = copy.deepcopy(TRUTH)
    truth["catering"]["client"] = ELISE
    return variant(seed, blobs, plan, ups, csv_rows(truth))


def slip_floral(seed, blobs):
    """Careful run that misses Hazel's hold and sends the summit florals."""
    plan = golden_plan()
    plan["floral"] = dict(send=True)
    ups = golden_airtable_updates()
    ups["floral"] = {"fld_status": "Sent", "fld_sent": TODAY}
    return variant(seed, blobs, plan, ups, csv_rows(actions={**ACTIONS, "floral": "sent"}))


def slip_send_then_correct(seed, blobs):
    """Sends the AV draft to Greg, then uses Correct to swap in Priya: final recipients look right, the send record does not."""
    plan = golden_plan()
    plan["av"] = dict(send=True, correct_after=[TRUTH["av"]["signer"], DANIEL])
    return variant(seed, blobs, plan, golden_airtable_updates(), csv_rows())


def slip_shuttle(seed, blobs):
    """Everything right except the already-sent shuttle envelope, which is left out with the old dates."""
    plan = golden_plan()
    plan["shuttle"] = {}
    ups = golden_airtable_updates()
    del ups["shuttle"]
    return variant(seed, blobs, plan, ups, csv_rows(actions={**ACTIONS, "shuttle": "sent"}))


# ---------------------------------------------------------------- io
def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def expected(blobs):
    def person(p):
        return {"name": p[0], "email": p[1]}
    return {
        "clock": CLOCK, "timezone": TZ, "today": TODAY, "csv": CSV_NAME, "csv_header": CSV_HEADER,
        "signing_threshold": 25000,
        "envelopes": SUMMIT_ENV, "duplicate_venue": DUP_VENUE, "wedding": WEDDING,
        "documents": {k: {"name": n, "size": len(blobs[n]), "sha256": sha(blobs[n])} for k, n in DOCS.items()},
        "send": {k: {"doc": DOCS[SEND_DOC[k]], "vendor_signer": person(TRUTH[k]["signer"]), "client_signer": person(TRUTH[k]["client"]),
                     "total": TRUTH[k]["total"], "stale_total": V[k]["total"] if V[k]["total"] != TRUTH[k]["total"] else None}
                 for k in SENT_KEYS},
        "stale": {"catering_doc": DOCS["catering_v2"], "catering_redline": DOCS["catering_redline"], "catering_client": person(ELISE),
                  "av_signer": person(V["av"]["signer"]), "av_stale_contact": "priya@coastalstageworks.com",
                  "shuttle_doc": DOCS["shuttle_v1"], "band_doc": DOCS["band_v1"],
                  "shuttle_bad_dates": [r"Jan(uary)?\.?\s*20\b"], "band_bad_dates": [r"Jan(uary)?\.?\s*22\b"]},
        # regexes that must NOT appear in the subject/message frozen at first send (stale facts from Theo's drafts)
        "stale_message_patterns": {
            "catering": [r"23,?800", r"7,?140"],
            "av": [r"Greg\b"],
            "shuttle": [r"Jan(uary)?\.?\s*20\b", r"December\s+1,", r"Dec\.?\s+1\b"],
            "photo": [],
            "band": [r"7,?500", r"3,?750", r"Jan(uary)?\.?\s*22\b"],
        },
        "hold": {"key": "floral", "envelope": SUMMIT_ENV["floral"], "vendor_email": V["floral"]["signer"][1]},
        "airtable": {"table": "tbl_hb_vendors", "records": REC, "fields": {k: v[0] for k, v in F.items()},
                     "updates": golden_airtable_updates()},
        "csv_rows": csv_rows()[1:],
    }


def main(out: Path):
    pdfs = write_contracts(out)
    blobs = {DOCS[k]: p.read_bytes() for k, p in pdfs.items()}
    sizes = {n: len(b) for n, b in blobs.items()}
    files = out / "seed" / "files"
    # DocuSign: page previews for every seeded document + the PDFs themselves for download.
    previews = {DOCS["venue"]: ("venue", TRUTH["venue"]), DOCS["catering_v2"]: ("catering", V["catering"]),
                DOCS["av"]: ("av", V["av"]), DOCS["shuttle_v1"]: ("shuttle", V["shuttle"]), DOCS["floral"]: ("floral", V["floral"]),
                DOCS["photo"]: ("photo", V["photo"]), DOCS["band_v1"]: ("band", V["band"])}
    for name, (key, t) in previews.items():
        page_png(files / "docusign" / name.replace(".pdf", ".png"), f"{t['vendor']} - {t['service']} Agreement", preview_lines(key, t))
        (files / "docusign" / name).write_bytes(blobs[name])
    ds = build_docusign(sizes)
    for e in ds["envelopes"]:
        for d in e["documents"]:
            png = files / "docusign" / d["fileUrl"].split("/")[-1]
            if not png.exists():
                page_png(png, d["name"].replace("_", " ").replace(".pdf", ""), [e["subject"], e["message"]])
            pdf = files / "docusign" / d["name"]
            if not pdf.exists():
                pdf.write_bytes(blobs.get(d["name"]) or long_pdf(out / "_pdf" / d["name"], d["name"], [("Agreement", [e["subject"]])]).read_bytes())
            d["fileSize"] = pdf.stat().st_size
    page_png(files / "docusign" / "Vendor_Agreement_Template.png", "Brightline Vendor Agreement", ["[Vendor]", "[Client]", "[Scope]", "[Fees]"])
    for k in ["catering_v3", "catering_redline", "band_v2", "shuttle_v2"]:
        (files / "yahoo_mail" / DOCS[k]).parent.mkdir(parents=True, exist_ok=True)
        (files / "yahoo_mail" / DOCS[k]).write_bytes(blobs[DOCS[k]])
    # Theo's local working copies as of Nov 12 (stale for catering/shuttle/band).
    for k in ["catering_v2", "av", "shuttle_v1", "floral", "photo", "band_v1"]:
        (out / "input" / "contracts" / DOCS[k]).parent.mkdir(parents=True, exist_ok=True)
        (out / "input" / "contracts" / DOCS[k]).write_bytes(blobs[DOCS[k]])

    seed = {"docusign": ds, "airtable": build_airtable(), "yahoo_mail": build_yahoo(sizes)}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    golden, rows = variant(seed, blobs, golden_plan(), golden_airtable_updates(), csv_rows())
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / CSV_NAME, rows)
    write_json(out / "expected.json", expected(blobs))

    variants = {"golden": (golden, rows), "nop": (seed, None), "naive": naive_variant(seed, blobs),
                "slip_authority": slip_authority(seed, blobs), "slip_floral": slip_floral(seed, blobs),
                "slip_send_then_correct": slip_send_then_correct(seed, blobs), "slip_shuttle": slip_shuttle(seed, blobs)}
    for name, (states, vrows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if vrows:
            write_csv(out / "variants" / name / "output" / CSV_NAME, vrows)
    import shutil
    shutil.rmtree(out / "_pdf", ignore_errors=True)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
