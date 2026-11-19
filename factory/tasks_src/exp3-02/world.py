#!/usr/bin/env python3
"""Deterministic editorial desk fixtures for After the Last Tram."""
import copy
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url  # noqa: E402

ACTOR, EDITOR, DESIGNER = "usr-inez", "usr-mara", "usr-oscar"
PUB, TEAM, CHANNEL, ROOT = "pub-platform-letter", "team-platform", "ch-editorial", "post-tram-release"
CLOCK = "2026-11-18T15:00:00.000Z"
WEB, EMBARGO, SEND, PROOF = "post-map", "post-night", "post-depot", "post-depot-proof"
WEB_TITLE = "A Map of the Last Stops"
EMBARGO_TITLE = "The Night Inspector"
SEND_TITLE = "Inside the Bell Street Depot"
OLD_TIME = "2026-11-19T17:30:00.000Z"
NEW_TIME = "2026-11-19T18:30:00.000Z"
REVIEWED = "2026-11-18T14:40:00.000Z"
REPORT_WEB = f"{WEB_TITLE} — published on the web only. No email or app delivery."
REPORT_SCHEDULED = f"{EMBARGO_TITLE} — scheduled for November 19, 2026 at 18:30 UTC. It is not yet published. Email and Substack app delivery is queued for release."
REPORT_SENT = f"{SEND_TITLE} — published for paid subscribers and delivered via email and the Substack app."
PEOPLE = [(ACTOR, "Inez Ward", "inezw", "Release producer"),
          (EDITOR, "Mara Ellis", "marae", "Editor"),
          (DESIGNER, "Oscar Lin", "oscarl", "Photo editor")]

ARCHIVE = [
    ("When the Floodlights Came On", "The tennis courts stayed open through October under lamps reclaimed from a railway yard."),
    ("The Viaduct Garden", "A volunteer rota keeps the herb beds above the freight tracks watered."),
    ("Listening at Quarry Road", "The sound walk follows a stone wall that still carries the echo of the quarry."),
    ("The Ferry Waiting Room", "The old ticket window now lends blankets to passengers on the evening crossing."),
    ("Brass Numbers on the Bakery Door", "The enamel sign survived three owners and two changes of street name."),
    ("Small Museums of the North Loop", "A cabinet of bus transfers sits beside the library's lending desk."),
    ("Pigeon Loft Ledger", "The club's secretary still records each return in a blue exercise book."),
    ("An Hour at the Letterpress", "The printers keep replacement letters sorted in old tea tins."),
    ("Window Seats in Winter", "Each cafe on the route reserves a table near the glass for solo diners."),
    ("The Reading Room Key", "Two custodians share the brass key on alternating weekends."),
    ("Orchard Street after Rain", "Painters set up under the awning as runoff mirrored the market lights."),
    ("A Wall for Lost Notices", "A bicycle shop keeps the neighborhood's handwritten announcements in a frame."),
    ("The Secondhand Atlas", "A pencilled walking route runs off the edge of the city inset."),
    ("Sunday at the Clock Workshop", "The escapements on the bench tick at slightly different speeds."),
    ("Repairing the Pavilion", "A joiner matched the old floorboards using wood from the broken steps."),
    ("Songs under the Railway Arch", "The choir moves one arch down when the evening train passes."),
    ("An Inventory of Public Benches", "The survey follows repair dates stamped into the cast iron."),
    ("Market Day at East Basin", "The ceramics stall packs up just before the river mist arrives."),
    ("Glass Roofs of the Arcade", "The surviving panes carry the etched marks of three local glaziers."),
    ("An Empty Cinema on Mercer Lane", "The caretaker rolls the carpets back before testing the projector."),
    ("The Tram Depot Bell", "The restored bell is on loan to the transport museum through December."),
    ("The Bell Street Depot at Noon", "An unsigned photo study of the forecourt from the summer archive."),
    ("Winter Portraits at the Terminus", "Portrait proofs are with the photographer for January's issue."),
    ("A Guide to Night Buses", "Timetable illustrations are still being checked with the route planners."),
]


def ago(days=0, minutes=0):
    return (datetime.fromisoformat(CLOCK.replace("Z", "+00:00")) - timedelta(days=days, minutes=minutes)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def stamp(time):
    return {"createdAt": time, "updatedAt": time}


def post(pid, slug, title, subtitle, body, status, *, audience="everyone", send=False, schedule=None, day=1, author=EDITOR):
    when = ago(day)
    return dict(id=pid, publicationId=PUB, authorId=author, slug=slug, title=title,
                subtitle=subtitle, bodyHtml=f"<p>{body}</p>", thumbnailPath="/images/city.webp",
                tags=["After the Last Tram"] if pid in (WEB, EMBARGO, SEND, PROOF) else ["City notebook"],
                status=status, audience=audience, commentPolicy="disabled", sendByEmailAndApp=send,
                **stamp(when), createdById=author, updatedById=author, scheduledAt=schedule,
                publishedAt=when if status == "published" else None,
                deliveryAt=when if status == "published" and send else None,
                deletedAt=None, metrics=None, duplicatedFromId=None)


def substack():
    rows = [
        post(WEB, "a-map-of-the-last-stops", WEB_TITLE, "Illustrations by Safiya Bell",
             "The route ends are marked in cobalt ink. At each stop the map shows where the last tram turns back.", "published"),
        post(EMBARGO, "the-night-inspector", EMBARGO_TITLE, "An interview by Mara Ellis",
             "Clara Reeve starts her shift at dusk, checking the platform lamps before the final eastbound service.", "scheduled",
             audience="everyone", send=True, schedule=OLD_TIME),
        post(SEND, "inside-the-bell-street-depot", SEND_TITLE, "Photo essay by Oscar Lin",
             "At Bell Street the inspection pits run below a row of tiled bays. Staff clean each car by hand after midnight.", "draft", author=DESIGNER),
        post(PROOF, "inside-the-bell-street-depot-layout-proof", SEND_TITLE + " — layout proof", "Alternate contact sheet",
             "Uncleared contact sheet captions from the first depot walk. For internal layout only.", "draft", send=True, author=DESIGNER),
    ]
    for i, (title, body) in enumerate(ARCHIVE):
        status = "draft" if i >= 22 else "published"
        rows.append(post(f"post-archive-{i:02}", title.lower().replace(" ", "-"), title,
                         "From the Platform Letter notebook", body, status, send=i % 4 != 0, day=i + 2))
    subscribers = []
    for i, (name, tier) in enumerate([
        ("Safiya Bell", "paid"), ("Clara Reeve", "free"), ("Dina Moss", "paid"),
        ("Ari Cohen", "founding"), ("Hugo Chen", "free"), ("Sana Kapoor", "paid"),
        ("Theo Flynn", "free"), ("Nina Costa", "free"), ("Yusuf Holt", "paid"),
        ("Ivy Shah", "free"), ("Miro Reed", "free"), ("June Patel", "paid"),
    ]):
        joined = ago(15 + i)
        subscribers.append(dict(id=f"sub-{i:02}", publicationId=PUB, userId=None, name=name,
                                email=name.lower().replace(" ", ".") + "@example.org", status="active",
                                baseType=tier, source="web", joinedAt=joined, **stamp(joined),
                                createdById=ACTOR, updatedById=ACTOR))
    return dict(currentUserId=ACTOR, publication=dict(id=PUB, ownerId=ACTOR, name="Platform Letter",
                slug="platform-letter", description="A journal of city life after dark.", currency="USD",
                commentsEnabled=True, **stamp(ago(180)), updatedById=ACTOR),
                users=[dict(id=uid, name=name, handle=handle, role="owner" if uid == ACTOR else "contributor")
                       for uid, name, handle, _ in PEOPLE],
                posts=rows, subscribers=subscribers, compSubscriptions=[], comments=[], events=[])


def word_doc(doc_id, title, paragraphs, time, owner=EDITOR):
    meta = dict(**stamp(time), createdByUserId=owner, updatedByUserId=owner)
    blocks = [dict(id=f"{doc_id}_b{i}", style="title" if i == 0 else "normal", list=None,
                   alignment="left", runs=[dict(text=line, marks=[])])
              for i, line in enumerate([title, *paragraphs])]
    return dict(id=doc_id, title=title, ownerId=owner, locationLabel="OneDrive · Documents",
                status="active", revision=0, body={"blocks": blocks}, tracking=dict(mode="off", **meta),
                originTemplateId=None, copiedFromDocumentId=None, deletedAt=None, deletedByUserId=None, **meta)


def word():
    documents = [
        word_doc("doc-signed", "After the Last Tram — signed release sheet", [
            "Approved by Mara Ellis, 18 November 2026 at 14:40 UTC. This sheet supersedes the production run sheet. Scope: the three exact article titles below.",
            f"{WEB_TITLE} (Illustrations by Safiya Bell). Live on the public web for Everyone. The illustration license allows web publication only. Keep email and Substack app delivery off.",
            f"{EMBARGO_TITLE} (An interview by Mara Ellis). Embargo lift: 19 November 2026 at 19:30 CET (UTC+01:00). Keep the article scheduled at that instant for Everyone, with email and Substack app delivery enabled for release. The 18:30 CET slot on the run sheet was withdrawn by the archive. The release desk uses UTC.",
            f"{SEND_TITLE} (Photo essay by Oscar Lin). Approved for immediate publication once this sheet is signed. Paid subscribers only. Send via email and the Substack app with publication. The separately titled layout proof is internal and has no release clearance.",
            "Keep the existing article copy, tags and closed comments. Confirm actual release status in the original Editorial Desk handoff thread."
        ], REVIEWED),
        word_doc("doc-run-sheet", "After the Last Tram — production run sheet", [
            "Planning copy, 17 November. The tentative interview slot is 19 November at 18:30 CET. Use Everyone and check the shared delivery bundle on each piece at QA. Final distribution is subject to the signed release sheet."
        ], ago(1)),
    ]
    for i, (title, body) in enumerate(ARCHIVE[:15]):
        documents.append(word_doc(f"doc-notes-{i:02}", f"{title} — copy notes", [body], ago(i + 3), ACTOR))
    grants = [dict(id=f"grant-{doc}", documentId=doc, email="inezw@platform-letter.example", userId=ACTOR,
                   permission="view", status="active", invitationId=None, revokedAt=None, revokedByUserId=None,
                   **stamp(ago(2)), createdByUserId=EDITOR, updatedByUserId=EDITOR)
              for doc in ("doc-signed", "doc-run-sheet")]
    return dict(currentUserId=ACTOR, users=[dict(id=uid, name=name, email=f"{handle}@platform-letter.example",
                initials="".join(part[0] for part in name.split()), organizationId=TEAM)
                for uid, name, handle, _ in PEOPLE], documents=documents, shareGrants=grants,
                **{key: [] for key in ("templates", "documentActivity", "commentThreads", "trackedChanges",
                                       "shareInvitations", "shareLinks")})


def message(pid, who, channel, body, time, root=None):
    return dict(id=pid, channelId=channel, userId=who, rootId=root, message=body, fileIds=[],
                mentionedUserIds=[], isPinned=False, editedAt=None, deletedAt=None, deletedBy=None, **stamp(time))


def mattermost():
    when = ago(180)
    channels = []
    for cid, name, display, purpose in [
        (CHANNEL, "editorial-desk", "Editorial Desk", "Copy approvals and release handoffs"),
        ("ch-production", "production", "Production", "Art, rights and production logistics"),
    ]:
        channels.append(dict(id=cid, teamId=TEAM, name=name, displayName=display, purpose=purpose,
                             header=purpose, type="O", status="active", isDefault=cid == CHANNEL,
                             createdBy=EDITOR, archivedAt=None, archivedBy=None, **stamp(when)))
    posts = [
        message(ROOT, EDITOR, CHANNEL, "After the Last Tram | release handoff\nAll three pieces are live according to the production board. Inez, please own the closeout here before I brief the contributors.", ago(minutes=66)),
        message("post-tram-qa", DESIGNER, CHANNEL, "The depot layout proof is still on the dashboard for the design archive. The approved photo essay has my byline in the subtitle.", ago(minutes=52), ROOT),
        message("post-tram-sheet", EDITOR, CHANNEL, "The signed release sheet is now in Word and is the one to use for closeout. Please reply here with what is on the web, what is scheduled and what actually went out.", ago(minutes=19), ROOT),
        message("post-tram-art", DESIGNER, "ch-production", "After the Last Tram | artwork handoff\nHigh-res endpaper art is with Safiya. Keep printing questions in this thread.", ago(minutes=15)),
    ]
    for i, (title, body) in enumerate(ARCHIVE):
        posts.append(message(f"post-desk-{i:02}", PEOPLE[1 + i % 2][0],
                             CHANNEL if i % 3 == 0 else "ch-production",
                             f"{title} — background for the copy desk. {body}", ago(1 + i)))
    return dict(schemaVersion=1, currentUserId=ACTOR, currentTeamId=TEAM,
                teams=[dict(id=TEAM, name="platform-letter", displayName="Platform Letter",
                            description="Editorial workspace", iconUrl=file_url("team.svg"), **stamp(when))],
                users=[dict(id=uid, username=handle, firstName=name.split()[0], lastName=name.split()[1],
                            email=f"{handle}@platform-letter.example", position=role, avatarUrl=file_url(f"{uid}.svg"),
                            status="active", presence="online", isGuest=False, **stamp(when))
                       for uid, name, handle, role in PEOPLE],
                teamMembers=[dict(id=f"team-{uid}", teamId=TEAM, userId=uid, role="team_admin" if uid == EDITOR else "team_user",
                                  status="active", **stamp(when)) for uid, *_ in PEOPLE],
                channels=channels,
                channelMembers=[dict(id=f"{cid}-{uid}", channelId=cid, userId=uid, role="channel_admin" if uid == EDITOR else "channel_user",
                                     status="active", addedBy=EDITOR, joinedAt=when, leftAt=None, isFavorite=False,
                                     muted=False, lastViewedAt=None, lastReadPostId=None, **stamp(when))
                                for cid in (CHANNEL, "ch-production") for uid, *_ in PEOPLE],
                posts=posts, threads=[dict(id=ROOT, rootPostId=ROOT, channelId=CHANNEL, replyCount=2,
                                          lastReplyAt=posts[2]["createdAt"], participantIds=[EDITOR, DESIGNER],
                                          createdAt=posts[1]["createdAt"], updatedAt=posts[2]["createdAt"])],
                sidebarCategories=[dict(id="cat-editorial", userId=ACTOR, teamId=TEAM, name="Channels",
                                        type="channels", channelIds=[CHANNEL, "ch-production"], order=0, collapsed=False, **stamp(when))],
                **{key: [] for key in ("threadMemberships", "pins", "files", "drafts", "reactions",
                                       "savedPosts", "preferences", "activityLog")})


def event(state, action, target, details, time):
    events = state["events"]
    events.append(dict(id=f"evt-fixture-{len(events) + 1}", type=action, publicationId=PUB,
                       actorId=ACTOR, createdAt=time, entityId=target["id"],
                       details=dict(postId=target["id"], **details)))
    target.update(updatedAt=time, updatedById=ACTOR)


def settings(state, target, time, **changes):
    target.update(changes)
    event(state, "post.updated", target, {"changedFields": list(changes)}, time)


def publish(state, target, time, audience, send):
    previous = target["status"]
    delivery = time if send else None
    target.update(status="published", audience=audience, sendByEmailAndApp=send,
                  scheduledAt=None, publishedAt=time, deliveryAt=delivery)
    event(state, "post.published", target,
          dict(previousStatus=previous, publishedAt=time, audience=audience, deliveryAt=delivery), time)


def schedule(state, target, time):
    prior = target["scheduledAt"]
    target["scheduledAt"] = NEW_TIME
    event(state, "post.scheduled", target,
          dict(previousScheduledAt=prior, scheduledAt=NEW_TIME, audience=target["audience"]), time)


def action_time(seconds):
    return (datetime.fromisoformat(CLOCK.replace("Z", "+00:00")) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def thread_reply(state, body, time):
    reply_id = "post-fixture-release-update"
    state["posts"].append(message(reply_id, ACTOR, CHANNEL, body, time, ROOT))
    state["threads"][0].update(replyCount=3, lastReplyAt=time, updatedAt=time,
                               participantIds=[EDITOR, DESIGNER, ACTOR])
    state["threadMemberships"].append(dict(id="tmbr-fixture-update", threadId=ROOT, userId=ACTOR,
                                           following=True, followedAt=time, unfollowedAt=None,
                                           lastReadAt=time, lastReadPostId=reply_id, **stamp(time)))
    cursor = next(member for member in state["channelMembers"]
                  if member["channelId"] == CHANNEL and member["userId"] == ACTOR)
    cursor.update(lastViewedAt=time, lastReadPostId=reply_id, updatedAt=time)
    state["activityLog"].append(dict(id="evt-fixture-reply", action="thread.reply", actorId=ACTOR,
                                    entityType="post", entityId=reply_id, channelId=CHANNEL,
                                    relatedIds=[ROOT], details=dict(rootId=ROOT, fileIds=[], mentionedUserIds=[]),
                                    createdAt=time))


def finish(initial, variant):
    states = copy.deepcopy(initial)
    if variant == "nop":
        return states
    stack = states["substack"]
    web, embargo, approved, proof = stack["posts"][:4]
    word_state = states["microsoft_word_for_the_web"]
    open_time = action_time(25)
    doc_id = "doc-run-sheet" if variant == "naive" else "doc-signed"
    word_state["documentActivity"].append(dict(id="activity_fixture_sheet", documentId=doc_id, userId=ACTOR,
                                               openedAt=open_time, isFavorite=False, **stamp(open_time),
                                               createdByUserId=ACTOR, updatedByUserId=ACTOR))
    web_report, schedule_report, send_report = REPORT_WEB, REPORT_SCHEDULED, REPORT_SENT
    if variant == "naive":
        settings(stack, web, action_time(60), sendByEmailAndApp=True)
        publish(stack, embargo, action_time(90), "everyone", True)
        publish(stack, proof, action_time(120), "everyone", True)
        web_report = f"{WEB_TITLE} — delivered by email and app."
        schedule_report = f"{EMBARGO_TITLE} — live and delivered."
        send_report = f"{SEND_TITLE} — published and sent to everyone."
    else:
        if variant == "slip_web_only_delivery":
            settings(stack, web, action_time(60), sendByEmailAndApp=True)
            web_report = f"{WEB_TITLE} — live and distributed by email and app."
        if variant == "slip_old_embargo":
            schedule_report = f"{EMBARGO_TITLE} — scheduled for November 19 at 17:30 UTC, with email and app delivery queued. Neither has gone live yet."
        else:
            schedule(stack, embargo, action_time(120))
        if variant == "slip_saved_without_sending":
            settings(stack, approved, action_time(120), audience="paid", sendByEmailAndApp=True)
            send_report = f"{SEND_TITLE} — draft saved for paid subscribers with email and app selected."
        else:
            publish(stack, approved, action_time(90), "paid", True)
    thread_reply(states["mattermost"], " ".join([web_report, schedule_report, send_report]), action_time(150))
    return states


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(out):
    initial = {"substack": substack(), "microsoft_word_for_the_web": word(), "mattermost": mattermost()}
    spec = json.loads(Path(__file__).with_name("spec.json").read_text())
    for site, state in initial.items():
        write(out / "seed" / f"{site}.json", state)
    media = out / "seed" / "files" / "mattermost"
    media.mkdir(parents=True, exist_ok=True)
    for key, name in [("team", "Platform Letter"), *((uid, name) for uid, name, *_ in PEOPLE)]:
        (media / f"{key}.svg").write_text(unquote(avatar(name).split(",", 1)[1]), encoding="utf-8")
    (out / "input").mkdir(parents=True, exist_ok=True)
    for variant in spec["fixture_expectations"]:
        current = finish(initial, variant)
        variant_dir = out / "variants" / variant
        (variant_dir / "output").mkdir(parents=True, exist_ok=True)
        for site, state in current.items():
            base = variant_dir / "state" / site
            write(base / "initial.json", initial[site])
            write(base / "current.json", state)
            if variant == "golden":
                write(out / "golden" / f"{site}.json", state)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
