#!/usr/bin/env python3
"""Deterministic Harbor checkout handoff state and independent scoring fixtures."""

import copy
import json
import os
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
if __name__ == "__main__" and sys.version_info < (3, 10):
    factory_python = FACTORY / ".venv" / "bin" / "python"
    if not factory_python.exists() or Path(sys.executable).resolve() == factory_python.resolve():
        raise SystemExit("worldkit requires Python 3.10 or later")
    os.execv(str(factory_python), [str(factory_python), *sys.argv])

sys.path.insert(0, str(FACTORY))
from worldkit import avatar

CLOCK = "2026-11-18T10:00:00.000Z"
BASE = "2026-10-21T09:00:00.000Z"
PRIOR = "2026-11-11T09:10:00.000Z"
PEOPLE = [
    ("alex", "Alex Morgan", "Delivery coordinator", "#505FD7"),
    ("priya", "Priya Raman", "Product lead", "#973DA4"),
    ("iris", "Iris Chen", "QA lead", "#2B7776"),
    ("leo", "Leo Martin", "Checkout engineer", "#5D6690"),
]

# Register order differs from the ClickUp list order. The prefix is the stable key.
TASKS = [
    (201, "Retry payment receipt"),
    (202, "Guest VAT summary"),
    (203, "Saved card keyboard navigation"),
    (204, "Receipt locale fallback"),
    (205, "Refund banner recovery"),
    (206, "Invoice address validation"),
    (207, "Wallet decline copy"),
]
ORDER = [205, 201, 206, 203, 207, 202, 204, 920]
HISTORY = [
    (181, "Checkout tax rounding", "accepted", 23, "Accepted", "Harbor 23"),
    (182, "Masked card announcement", "ready to resume", 24, "Continued", "Harbor 24"),
    (183, "Duplicate refund guard", "qa hold", 23, "Held", "Harbor 23"),
]
STATUS = [
    ("in review", "custom", "#4b74d8"),
    ("in progress", "custom", "#2778bc"),
    ("ready to resume", "open", "#8360d4"),
    ("qa hold", "custom", "#c97017"),
    ("blocked", "custom", "#b54848"),
    ("accepted", "done", "#30835a"),
    ("closed", "closed", "#437653"),
]
OUTCOMES = {
    "accept": ("accepted", 24, "Accepted", "Harbor 24"),
    "continue": ("ready to resume", 25, "Continued", "Harbor 25"),
    "hold": ("qa hold", 24, "Held", "Harbor 24"),
}
DECISIONS = {201: "accept", 202: "accept", 203: "continue",
             204: "continue", 205: "hold", 206: "hold"}
SITE_KEYS = ("clickup", "microsoft_excel_for_the_web", "mattermost")
BOOK = "wb-harbor-release"


def keyed(number):
    return f"HBR-{number}"


def sprint_id(number):
    return f"harbor-{number}"


def clickup():
    state = dict(
        currentUserId="alex",
        workspace=dict(id="harbor-studio", name="Harbor Studio", initials="HS",
                       color="#4b69aa", plan="Business",
                       clickApps=dict(sprintPoints=True, timeTracking=True, timeEstimates=True,
                                      multipleAssignees=True, billableDefault=False),
                       sprintPointScale=[1, 2, 3, 5, 8]),
        users=[dict(id=pid, name=name, initials="".join(word[0] for word in name.split()),
                    email=f"{pid}@harbor.example", title=title, color=color,
                    role="admin" if pid == "alex" else "member", timezone="Etc/UTC",
                    weeklyCapacityHours=40, status="online")
               for pid, name, title, color in PEOPLE],
        spaces=[dict(id="product", name="Harbor Product", color="#4b69aa",
                     icon="Layers", private=False, memberIds=[p[0] for p in PEOPLE],
                     orderIndex=0, createdAt=BASE,
                     statuses=[dict(id=f"st-{i}", name=name, type=kind, color=color, orderIndex=i)
                               for i, (name, kind, color) in enumerate(STATUS)])],
        folders=[dict(id="delivery", spaceId="product", name="Checkout Iterations",
                      isSprintFolder=True, orderIndex=0, hidden=False, createdAt=BASE,
                      sprintSettings=dict(nameTemplate="Harbor {index}", durationDays=7,
                                          startDay="wednesday", dateFormat="MMM d",
                                          measureOfEffort="sprint_points", nonWorkingDays=[0, 6],
                                          automations=dict(autoCreate=False, autoCreateCount=1,
                                                           autoMarkDone=False, moveSpilloverToNext=False),
                                          backlogListId="checkout"))],
        lists=[dict(id=id_, spaceId="product", folderId="delivery", name=name,
                    description=desc, isBacklog=backlog, orderIndex=i, createdAt=BASE, archived=False)
               for i, (id_, name, desc, backlog) in enumerate([
                   ("checkout", "Checkout Delivery", "Production checkout work.", True),
                   ("sandbox", "Checkout Sandbox", "Internal checkout rehearsals.", False),
                   ("research", "Product Discovery", "Candidate work beyond this handoff.", False),
               ])],
        sprints=[], tasks=[], activity=[], timer=None, viewSettings={},
        preferences=dict(theme="light", startOfWeek="monday", timeFormat="24h"),
        timesheetSettings=dict(approvalsEnabled=False, approvers={},
                               deadline=dict(day="monday", time="10:00"),
                               reminders=dict(before=True, after=True),
                               dailyCapacityHours=8, weeklyCapacityHours=40),
    )
    for collection in ("teams", "customFields", "tags", "comments", "docs", "docPages",
                       "timeEntries", "timeTags", "timesheets", "notifications", "favorites",
                       "trash", "dashboards"):
        state[collection] = []
    for number, start, end, status in [
        (22, "10-28", "11-04", "done"), (23, "11-04", "11-11", "done"),
        (24, "11-11", "11-18", "in_progress"), (25, "11-18", "11-25", "not_started"),
    ]:
        committed = ([keyed(i) for i in (181, 182, 183)] if number == 23 else
                     [keyed(i) for i, _ in TASKS] if number == 24 else [])
        state["sprints"].append(dict(
            id=sprint_id(number), folderId="delivery", spaceId="product", index=number,
            name=f"Harbor {number}", startDate=f"2026-{start}", endDate=f"2026-{end}",
            status=status, goal="Improve reliability of the checkout and refund journey.",
            forecastPoints=3 * len(committed) if status != "not_started" else None,
            startedAt=f"2026-{start}T09:00:00.000Z" if status != "not_started" else None,
            startedBy="priya" if status != "not_started" else None,
            completedAt=f"2026-{end}T09:30:00.000Z" if status == "done" else None,
            completedBy="priya" if status == "done" else None,
            completedPoints=(3 if number == 23 else 0) if status == "done" else None,
            committedTaskIds=committed, completedTaskIds=[keyed(181)] if number == 23 else [],
            spilloverTaskIds=[], spilloverToSprintId=None, createdAt=BASE, createdBy="priya"))

    def add(number, title, status, sprint, home="checkout", history=None, updated=BASE):
        closed = status in ("accepted", "closed")
        state["tasks"].append(dict(
            id=keyed(number), name=f"{keyed(number)} · {title}",
            description=f"{title}. Checkout tracking reference {keyed(number)}.",
            status=status, priority="normal", assigneeIds=["leo"], watcherIds=["iris"],
            tags=[], listId=home, sprintId=sprint_id(sprint) if sprint else None,
            sprintHistory=[sprint_id(value) for value in (history or ([sprint] if sprint else []))],
            parentId=None, startDate=None, dueDate=None, timeEstimate=None, sprintPoints=3,
            customFields={}, checklists=[], linkedDocIds=[], dependencies=dict(waitingOn=[], blocking=[]),
            orderIndex=len(state["tasks"]), createdBy="priya", createdAt=BASE,
            updatedAt=updated, dateClosed=updated if closed else None,
            closedBy="priya" if closed else None, archived=False, deleted=False,
            deletedAt=None, deletedBy=None, attachments=[]))

    for i, title in TASKS:
        add(i, title, "accepted" if i == 207 else "in review", 24,
            updated="2026-11-18T08:45:00.000Z" if i == 207 else BASE)
    activity(state, 207, "status_changed", "status", "in review", "accepted",
             "2026-11-18T08:45:00.000Z", "priya")
    for i, title, status, sprint, _, _ in HISTORY:
        add(i, title, status, sprint, history=[23, 24] if sprint == 24 else [23], updated=PRIOR)
        activity(state, i, "status_changed", "status", "in review", status, PRIOR, "priya")
        if sprint == 24:
            record_move(state, i, 23, 24, PRIOR, "priya")
    for i, title, status, sprint in [
        (911, "Discount display walkthrough", "closed", 23),
        (912, "Token refresh walkthrough", "in progress", 24),
        (913, "Invoice retry walkthrough", "blocked", 24),
    ]:
        at = "2026-11-12T10:00:00.000Z"
        add(i, title, status, sprint, "sandbox", history=[23, 24] if sprint == 24 else [23], updated=at)
        activity(state, i, "status_changed", "status", "in review", status, at, "priya")
        if sprint == 24:
            record_move(state, i, 23, 24, at, "priya")
    add(920, "Refund banner recovery", "in review", 24, "sandbox")
    add(921, "Retry payment receipt", "in review", 25)
    for i, title in enumerate([
        "Audit gift card icons", "Confirm settlement sample", "Review receipt typography",
        "Map regional payment errors", "Triage cashier feedback", "Compare tax provider traces",
        "Profile quote service", "Draft support escalation map", "Survey enterprise invoices",
        "Review order detail events", "Sketch multi-currency selector", "Inventory locale variants",
        "Document payment routing", "Explore chargeback inbox", "Inspect export permissions",
        "Review address autocomplete", "Retire legacy footer", "Plan fraud rules demo",
        "Normalize country labels", "Review masked account copy", "Benchmark card chooser",
        "Explore partial captures", "Plan weekend support test", "Define preview metrics",
    ], 301):
        add(i, title, "in progress", None, "research")
    return state


def activity(state, number, kind, field, before, after, timestamp, actor):
    event = dict(id=f"ac-{len(state['activity']) + 1}", taskId=keyed(number),
                 actorId=actor, type=kind, field=field, to=after, createdAt=timestamp)
    event["from"] = before
    state["activity"].append(event)


def record_move(state, number, before, after, at, actor):
    activity(state, number, "sprint_removed", "sprintId", sprint_id(before), None, at, actor)
    activity(state, number, "sprint_added", "sprintId", sprint_id(before), sprint_id(after), at, actor)


def mattermost():
    team = "team-harbor"
    created = dict(createdAt=BASE, updatedAt=BASE)
    state = dict(schemaVersion=1, currentUserId="alex", currentTeamId=team,
                 teams=[dict(id=team, name="harbor", displayName="Harbor Studio",
                             description="Checkout delivery", iconUrl=avatar("Harbor Studio"), **created)])
    for key in ("users", "teamMembers", "channels", "channelMembers", "posts", "threads",
                "threadMemberships", "pins", "files", "drafts", "reactions", "savedPosts",
                "sidebarCategories", "preferences", "activityLog"):
        state[key] = []
    for pid, name, title, _ in PEOPLE:
        first, last = name.split()
        state["users"].append(dict(id=pid, username=pid, firstName=first, lastName=last,
                                   email=f"{pid}@harbor.example", position=title, avatarUrl=avatar(name),
                                   status="active", presence="online", isGuest=False, **created))
        state["teamMembers"].append(dict(id=f"tm-{pid}", teamId=team, userId=pid,
                                         role="team_user", status="active", **created))
    for channel in ("town-square", "harbor-delivery", "qa-bench", "sandbox-rehearsal"):
        state["channels"].append(dict(
            id=channel, teamId=team, name=channel, displayName=channel.replace("-", " ").title(),
            type="O", purpose="Checkout team coordination", header="", status="active",
            isDefault=channel == "town-square", createdBy="priya",
            archivedBy=None, archivedAt=None, **created))
        for pid, *_ in PEOPLE:
            state["channelMembers"].append(dict(
                id=f"cm-{channel}-{pid}", channelId=channel, userId=pid, role="channel_user",
                status="active", addedBy="priya", joinedAt=BASE, leftAt=None, isFavorite=False,
                muted=False, lastViewedAt=BASE, lastReadPostId=None, **created))

    def post(id_, channel, actor, at, message, root=None, pinned=False):
        state["posts"].append(dict(id=id_, channelId=channel, userId=actor, rootId=root,
                                   message=message, fileIds=[], mentionedUserIds=[], isPinned=pinned,
                                   editedAt=None, deletedAt=None, deletedBy=None, createdAt=at, updatedAt=at))

    prior = "harbor23-handoff"
    post(prior, "harbor-delivery", "priya", "2026-11-11T08:15:00.000Z",
         "Harbor 23 handoff draft for Checkout Delivery. HBR-181 has its sign-off. "
         "HBR-182 and HBR-183 are still open. I was going to put both unfinished tickets into Harbor 24.",
         pinned=True)
    post("harbor23-qa", "harbor-delivery", "iris", "2026-11-11T08:43:00.000Z",
         "HBR-182 is ordinary unfinished implementation with no acceptance blocker. "
         "HBR-183 is an acceptance blocker. Support still owns that exception against Harbor 23.",
         root=prior)
    post("harbor23-posted", "harbor-delivery", "priya", PRIOR,
         "Posted the production handoff after Iris's correction. Use those three Checkout Delivery tickets "
         "and the H23 Posted tab as examples next time. For handoff, a pass with an advisory is still a pass. "
         "A reopened acceptance blocker stays a blocker until QA records a replacement pass.",
         root=prior)
    state["threads"].append(dict(id=prior, rootPostId=prior, channelId="harbor-delivery",
                                  replyCount=2, lastReplyAt=PRIOR, participantIds=["priya", "iris"],
                                  createdAt="2026-11-11T08:15:00.000Z", updatedAt=PRIOR))
    state["pins"].append(dict(id="pin-h23", channelId="harbor-delivery", postId=prior,
                               status="active", pinnedBy="priya", pinnedAt=PRIOR, unpinnedBy=None,
                               unpinnedAt=None, createdAt=PRIOR, updatedAt=PRIOR))
    post("harbor24-cutoff", "harbor-delivery", "iris", "2026-11-18T09:30:00.000Z",
         "Harbor 24 production handoff uses the latest QA entry per Checkout Delivery key in H24 Evidence "
         "through 09:00 UTC today, inclusive. Entries after cutoff are for tomorrow's review. "
         "The H24 Handoff tab is Support's live ledger. Its blank disposition rows for Checkout Delivery are the handoff queue.")
    post("sandbox-closeout", "harbor-delivery", "leo", "2026-11-12T10:18:00.000Z",
         "Sandbox rehearsal closeout posted after yesterday's production pass. HBR-911, HBR-912 "
         "and HBR-913 were the examples. I moved both open rehearsal tickets to Harbor 24 so the demo could continue.")
    for i, message in enumerate([
        "The tax fixture now covers the three decimal rounding examples.",
        "Staging receipts are available again after the certificate refresh.",
        "Support has the latest draft of the wallet decline wording.",
        "The masked card video is in the internal demo folder.",
        "The nightly replay finished with both test currencies enabled.",
        "Legal approved the short VAT label for the guest flow.",
        "The translation vendor sent the updated French address strings.",
        "QA has the latest payment simulator build.",
        "I booked a room for Wednesday's Support handoff.",
        "We have test accounts for all seven VAT jurisdictions.",
        "The finance group confirmed the sandbox invoice series.",
        "Operations can reproduce the refund timeout on staging.",
        "I refreshed the iOS capture for the receipt footer.",
        "The alerting dashboard now includes invoice delivery retries.",
        "Open office hours will start after checkout standup.",
        "The test devices are charging at the front desk.",
        "I've added guest checkout to next week's accessibility review.",
        "Staging traffic is back to its usual level.",
        "The keyboard walkthrough recording is ready for review.",
        "The demo team is using sample receipts with fictional addresses.",
        "A fresh test card batch is available from the QA desk.",
        "The draft escalation map is ready for Leo's comments.",
        "The regional rollout discussion is on tomorrow's calendar.",
        "I checked the screenshot crop on the wallet decline article.",
    ]):
        channel = ("town-square", "qa-bench", "sandbox-rehearsal")[i % 3]
        post(f"checkout-note-{i}", channel, PEOPLE[i % len(PEOPLE)][0],
             f"2026-11-{12 + i // 5:02}T{10+i % 5:02}:00:00.000Z", message)
    return state


def excel():
    audit = dict(createdAt=BASE, updatedAt=BASE, createdBy="alex", updatedBy="alex")
    state = dict(
        schemaVersion=1, currentUserId="alex", preferences=dict(ribbonMode="classic", zoom=100),
        users=[dict(id=pid, displayName=name, email=f"{pid}@harbor.example",
                    initials="".join(word[0] for word in name.split()), avatarColor=color,
                    organization="Harbor Studio", jobTitle=title)
               for pid, name, title, color in PEOPLE],
        workbooks=[dict(id=BOOK, name="Harbor Release Register", ownerId="alex",
                        location="OneDrive / Documents / Checkout", status="active", favoriteUserIds=["alex"],
                        activeSheetId="h24-handoff", lastOpenedAt=BASE, **audit)],
        sheets=[], cells=[])
    for key in ("tables", "filters", "sorts", "shares", "shareLinks", "comments", "charts",
                "operations", "conditionalFormats", "validationRules"):
        state[key] = []

    def sheet(id_, name, widths, rows):
        state["sheets"].append(dict(id=id_, workbookId=BOOK, name=name, position=len(state["sheets"]),
                                    visibility="visible", status="active", tabColor=None,
                                    autoFilterRange=None, frozenRows=1,
                                    columnWidths={str(i): width for i, width in enumerate(widths, 1)}, **audit))
        for row, values in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                if value is None:
                    continue
                address = f"{chr(64 + col)}{row}"
                state["cells"].append(dict(id=f"cell-{id_}-{address}", workbookId=BOOK,
                                           sheetId=id_, row=row, column=col, address=address,
                                           input=value, formula=None, value=value, valueType="string",
                                           error=None, dependencies=[], **audit))

    names = dict(TASKS)
    names[920] = names[205]
    sheet("h24-handoff", "H24 Handoff", (116, 268, 126, 140), [
        ("Checkout Key", "ClickUp Task", "Disposition", "Sprint Ledger"),
        *((keyed(i), names[i], "Accepted" if i == 207 else None, "Harbor 24" if i == 207 else None)
          for i in ORDER),
    ])
    sheet("h24-evidence", "H24 Evidence", (116, 172, 158, 495), [
        ("Checkout Key", "QA time (UTC)", "Acceptance result", "QA evidence"),
        (keyed(205), "2026-11-17 15:52", "Pass", "Refund succeeds on retry in staging."),
        (keyed(201), "2026-11-18 08:10", "Pass", "Receipt delivered on retry in both regions."),
        (keyed(203), "2026-11-18 08:12", "Pending", "Engineer still wiring focus order. No blocker reported."),
        (keyed(206), "2026-11-18 08:16", "Blocker", "QA rejected invoices with amended postal codes."),
        (keyed(207), "2026-11-18 08:20", "Pass", "QA verified wallet decline copy on mobile."),
        (keyed(204), "2026-11-18 08:25", "Pending", "Locale fallback implementation still unfinished. No acceptance blocker."),
        (keyed(202), "2026-11-18 09:00", "Pass with advisory", "All launch criteria met. Capture the spacing suggestion for later."),
        (keyed(920), "2026-11-18 08:29", "Pass", "Rehearsal simulator sample in Checkout Sandbox."),
        (keyed(205), "2026-11-18 08:54", "Reopened blocker", "Refund timeout returned in the production-like checkout replay."),
        (keyed(206), "2026-11-18 09:12", "Pass", "Fixed build passed the postal-code case."),
        (keyed(921), "2026-11-18 08:48", "Pending", "Follow-up for Harbor 25 only."),
    ])
    sheet("h23-posted", "H23 Posted", (116, 268, 126, 140), [
        ("Checkout Key", "ClickUp Task", "Disposition", "Sprint Ledger"),
        *((keyed(i), title, disposition, ledger) for i, title, _, _, disposition, ledger in HISTORY),
    ])
    sheet("sandbox", "Rehearsal Log", (116, 281, 126, 140), [
        ("Checkout Key", "ClickUp Task", "Disposition", "Sprint Ledger"),
        (keyed(911), "Discount display walkthrough", "Closed", "Harbor 23"),
        (keyed(912), "Token refresh walkthrough", "Moved", "Harbor 24"),
        (keyed(913), "Invoice retry walkthrough", "Moved", "Harbor 24"),
    ])
    return state


def update_task(state, number, status, sprint):
    task = next(task for task in state["tasks"] if task["id"] == keyed(number))
    if task["status"] != status:
        activity(state, number, "status_changed", "status", task["status"], status, CLOCK, "alex")
        task.update(status=status, dateClosed=CLOCK if status in ("accepted", "closed") else None,
                    closedBy="alex" if status in ("accepted", "closed") else None)
    if task["sprintId"] != sprint_id(sprint):
        previous = int(task["sprintId"].rsplit("-", 1)[-1])
        record_move(state, number, previous, sprint, CLOCK, "alex")
        task["sprintId"] = sprint_id(sprint)
        if task["sprintId"] not in task["sprintHistory"]:
            task["sprintHistory"].append(task["sprintId"])
    task["updatedAt"] = CLOCK


def operation(state, kind, sheet, targets, details):
    state["operations"].append(dict(
        id=f"op-{len(state['operations']) + 1}", type=kind, actorId="alex", createdAt=CLOCK,
        workbookId=BOOK, sheetId=sheet, targetIds=targets, details=details))


def write_ledger(state, number, disposition, ledger):
    book = state["workbooks"][0]
    sheet = "h24-handoff"
    row = ORDER.index(number) + 2
    for col, value in [(3, disposition), (4, ledger)]:
        address = f"{chr(64 + col)}{row}"
        cell = next((c for c in state["cells"] if c["sheetId"] == sheet and c["address"] == address), None)
        if not cell:
            cell = dict(id=f"cell-{sheet}-{address}", workbookId=BOOK, sheetId=sheet, row=row,
                        column=col, address=address, input="", formula=None, error=None,
                        dependencies=[], createdAt=CLOCK, createdBy="alex")
            state["cells"].append(cell)
        prior = cell["input"]
        if prior == value:
            continue
        cell.update(input=value, value=value, valueType="string", updatedAt=CLOCK, updatedBy="alex")
        book.update(updatedAt=CLOCK, updatedBy="alex")
        change = dict(id=cell["id"], address=address, before=dict(input=prior, format=None),
                      after=dict(input=value, format=None))
        operation(state, "cell.edit", sheet, [cell["id"]],
                  dict(range=address, changes=[change], recalculatedCellIds=[cell["id"]]))


def open_handoff_sources(workbook, mattermost_state, historical_sheet):
    channel = "harbor-delivery"
    last_post = "harbor24-cutoff"
    member = next(row for row in mattermost_state["channelMembers"]
                  if row["channelId"] == channel and row["userId"] == "alex")
    member.update(lastViewedAt=CLOCK, lastReadPostId=last_post, updatedAt=CLOCK)
    mattermost_state["activityLog"].append(dict(
        id="evt-handoff-read", action="channel.read", actorId="alex",
        entityType="channelMember", entityId=member["id"], channelId=channel,
        relatedIds=[last_post], details=dict(lastReadPostId=last_post), createdAt=CLOCK))

    book = workbook["workbooks"][0]
    operation(workbook, "workbook.open", None, [BOOK],
              dict(before=book["lastOpenedAt"], lastOpenedAt=CLOCK))
    book["lastOpenedAt"] = CLOCK
    for sheet in (historical_sheet, "h24-evidence", "h24-handoff"):
        operation(workbook, "sheet.select", sheet, [sheet],
                  dict(before=book["activeSheetId"], activeSheetId=sheet))
        book["activeSheetId"] = sheet


def outcome(initial, variant):
    worlds = copy.deepcopy(initial)
    if variant == "nop":
        return worlds
    cups, workbook, chat = (worlds[site] for site in SITE_KEYS)
    open_handoff_sources(workbook, chat, "sandbox" if variant == "naive" else "h23-posted")
    decisions = DECISIONS.copy()
    rules = OUTCOMES
    if variant in ("slip_reopened", "naive"):
        decisions[205] = "accept"
    if variant in ("slip_cutoff", "naive"):
        decisions[206] = "accept"
    if variant == "naive":
        decisions.update({207: "accept", 202: "hold"})
        rules = {"accept": ("closed", 24, "Closed", "Harbor 24"),
                 "continue": ("in progress", 25, "Moved", "Harbor 25"),
                 "hold": ("blocked", 25, "Moved", "Harbor 25")}
    for number, decision in decisions.items():
        status, sprint, disposition, ledger = rules[decision]
        target = 920 if variant in ("naive", "slip_duplicate") and number == 205 else number
        update_task(cups, target, status, sprint)
        write_ledger(workbook, target, disposition, ledger)
    return worlds


def dump(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(out):
    initial = dict(zip(SITE_KEYS, (clickup(), excel(), mattermost())))
    golden = outcome(initial, "golden")
    for site in SITE_KEYS:
        dump(out / "seed" / f"{site}.json", initial[site])
        dump(out / "golden" / f"{site}.json", golden[site])
    for name in ("golden", "nop", "naive", "slip_reopened", "slip_cutoff", "slip_duplicate"):
        current = golden if name == "golden" else outcome(initial, name)
        folder = out / "variants" / name
        (folder / "output").mkdir(parents=True, exist_ok=True)
        for site in SITE_KEYS:
            dump(folder / "state" / site / "initial.json", initial[site])
            dump(folder / "state" / site / "current.json", current[site])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
