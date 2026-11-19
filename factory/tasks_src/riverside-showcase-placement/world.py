"""Build Riverside's email, load register, and project checklist."""

import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url

ASSETS = Path(__file__).parent / "assets" / "floor-plans"
SEED_TIME = "2026-11-17T15:00:00Z"
RUN_TIME = "2026-11-19T14:12:00Z"
PROJECT = "project-riverside"
TODO = "todo-riverside-load-in"
TABLE = "tbl_riverside_load"
ME = "person-alex"
FACILITY = "person-jordan"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def gmail():
    mail = "alex@riverside.example"
    sender = dict(name="Jordan Reyes", email="jordan@riverside-venue.example", avatar=avatar("Jordan Reyes"))

    def message(revision, at, body):
        name = f"riverside-floor-plan-rev-{revision.lower()}.png"
        return dict(id=f"message-rev-{revision.lower()}", threadId="riverside-loading-plan",
                    sender=sender, **{"from": sender}, to=[{"email": mail, "name": "Alex Rivera"}],
                    cc=[], bcc=[], subject="Riverside loading plan", body=f"<p>{body}</p>",
                    snippet=body, timestamp=at, read=False, starred=False, important=False, labels=[],
                    category="primary", folder="inbox", attachments=[dict(
                        id=f"attach-rev-{revision.lower()}", name=name, size=(ASSETS / name).stat().st_size,
                        type="image/png", url=file_url(name))])

    return dict(
        user=dict(userId="gmail-alex", username="Alex Rivera", email=mail, avatar=avatar("Alex Rivera")),
        emails=[
            message("B", "2026-11-16T18:00:00Z", "Here's Rev B for the walkthrough. We are still signing off the load-in plan."),
            message("C", "2026-11-18T21:00:00Z", "Facilities approved the attached Rev C for Friday's setup. It supersedes Rev B."),
        ], labels=[], drafts=[], settings=dict(undoSend=5),
    )


def airtable():
    user = dict(id="at-alex", name="Alex Rivera", email="alex@riverside.example", avatar=avatar("Alex Rivera"))

    def options(values):
        return [dict(id=f"opt-{name.lower()}", name=name, color=color) for name, color in values]

    fields = [
        dict(id="kit", name="Kit", type="text", primary=True),
        dict(id="description", name="Equipment", type="text"),
        dict(id="width", name="Transport width (m)", type="number"),
        dict(id="power", name="Needs power", type="checkbox"),
        dict(id="release", name="Release", type="single_select",
             options=options([("Approved", "green"), ("Pending", "yellow")])),
        dict(id="bay", name="Bay", type="single_select",
             options=options([(f"B{i}", "blue") for i in range(1, 6)])),
        dict(id="disposition", name="Disposition", type="single_select",
             options=options([("Needs assignment", "gray"), ("Assigned", "green"), ("Hold", "orange"), ("Locked", "purple")])),
    ]

    def record(kit, label, width, power, release, bay=None, disposition="Needs assignment"):
        return dict(id=f"rec-{kit.lower()}", createdTime=SEED_TIME,
                    fields=dict(kit=kit, description=label, width=width, power=power,
                                release=release, bay=bay, disposition=disposition))

    view = dict(id="grid-load", name="Load List", type="grid", filters=[], sorts=[], groupBy=[],
                hiddenFieldIds=[], fieldWidths={"kit": 135, "description": 200, "width": 145, "power": 120,
                                                "release": 120, "bay": 115, "disposition": 165}, rowHeight="short")
    table = dict(id=TABLE, name="Riverside Load List", baseId="base-riverside", fields=fields,
                 records=[record("K17", "Interactive kiosk", 0.75, True, "Approved"),
                          record("K24", "Display wall case", 1.00, False, "Approved"),
                          record("K31", "Sample cart", 0.65, False, "Pending"),
                          record("K09", "Welcome desk box", 0.60, False, "Approved", bay="B5", disposition="Locked")],
                 views=[view], activeViewId=view["id"])
    return dict(currentUser=user, collaborators=[user],
                bases={"base-riverside": dict(id="base-riverside", name="Riverside Showcase",
                                             color="bg-teal-600", tables=[TABLE])},
                tables={TABLE: table}, activeBaseId="base-riverside", activeTableId=TABLE,
                ui=dict(viewSidebarOpen=False, expandedRecordId=None, searchQuery="",
                        isSearching=False, buttonActionLog=[]))


def stamp(ident, actor=FACILITY, at=SEED_TIME):
    return dict(id=ident, createdById=actor, createdAt=at, updatedById=actor, updatedAt=at)


def basecamp():
    notes = (
        "<p>Use the approved venue drawing, not the walkthrough draft. Bring each kit in from North Receiving, "
        "following the drawing's one-way cart arrows. A door must clear the kit's transport width plus 0.10 m. "
        "During load-in, carts may cross the protected visitor aisle where a route arrow crosses it. "
        "Keep all staged and installed equipment outside the hatched area. Powered kits need a bay with its own outlet. "
        "One kit per bay, including existing locked allocations.</p>"
        "<p>Only approved releases go to the floor. Record Hold and leave the bay blank for pending kits. "
        "Leave one comment here with the assignments, route rationale and anything the crew should hold back.</p>"
    )

    def todo(ident, title, details, position):
        return dict(**stamp(ident), projectId=PROJECT, listId="list-riverside-ops", title=title, notes=details,
                    assigneeIds=[ME], completionNotifyIds=[], startsOn=None, dueOn="2026-11-20",
                    position=position, completed=False, completedById=None, completedAt=None, status="active")

    return dict(workspace=dict(id="workspace-venue", name="Riverside Operations", currentUserId=ME,
                               timeZone="America/New_York"),
                people=[dict(id=ME, name="Alex Rivera", email="alex@riverside.example",
                             role="Operations", avatarColor="#305f67", isAdmin=False),
                        dict(id=FACILITY, name="Jordan Reyes", email="jordan@riverside-venue.example",
                             role="Venue Lead", avatarColor="#82602d", isAdmin=True)],
                projects=[dict(id=PROJECT, name="Riverside Showcase", description="Two-day public showcase.",
                               memberIds=[ME, FACILITY], color="#305f67")],
                todoLists=[dict(**stamp("list-riverside-ops"), projectId=PROJECT, name="Installation checklist",
                                description="Riverside setup", position=1, status="active")],
                todos=[todo(TODO, "Riverside load-in", notes, 1),
                       todo("todo-riverside-strike", "Riverside strike and load-out", "<p>Leave this open for Saturday.</p>", 2)],
                messageBoards=[dict(id="riverside-board", projectId=PROJECT, title="Message Board", sortOrder="newest")],
                messageCategories=[], messages=[], schedules=[dict(id="riverside-schedule", projectId=PROJECT, title="Schedule")],
                scheduleEntries=[], comments=[])


GOOD = {"K17": ("B2", "Assigned"), "K24": ("B3", "Assigned"), "K31": (None, "Hold")}
COMMENT = "K17 → B2: powered bay and 0.90 m inbound clearance. K24 → B3: 1.20 m inbound clearance. K31: Hold pending release approval."
SEMICOLON_COMMENT = (
    "K17 → B2: powered bay and 0.90 m inbound clearance. "
    "K24 → B3: inbound arrow permits entry; Rev C widened the B3 door to 1.20 m; "
    "the kit does not need an outlet and its footprint clears the aisle. "
    "K31: Hold pending release approval."
)


def outcome(initial, assignments=None, comment=None):
    states = deepcopy(initial)
    for row in states["airtable"]["tables"][TABLE]["records"]:
        fields = row["fields"]
        if assignments and fields["kit"] in assignments:
            fields["bay"], fields["disposition"] = assignments[fields["kit"]]
    if comment:
        states["basecamp"]["comments"].append(dict(
            **stamp("handoff-note", actor=ME, at=RUN_TIME), projectId=PROJECT,
            parentType="todo", parentId=TODO, bodyHtml=f"<p>{comment}</p>", status="active"))
    return states


def main(out):
    initial = {"gmail": gmail(), "airtable": airtable(), "basecamp": basecamp()}
    for site, state in initial.items():
        dump(out / "seed" / f"{site}.json", state)
    files = out / "seed" / "files" / "gmail"
    files.mkdir(parents=True)
    for image in sorted(ASSETS.glob("*.png")):
        shutil.copyfile(image, files / image.name)
    golden = outcome(initial, GOOD, COMMENT)
    for site, state in golden.items():
        dump(out / "golden" / f"{site}.json", state)
    unintended_write = outcome(initial, GOOD, SEMICOLON_COMMENT)
    basecamp_state = unintended_write["basecamp"]
    basecamp_state["todos"].append({
        **basecamp_state["todos"][0],
        **stamp("todo-unintended-fragment", actor=ME, at=RUN_TIME),
        "title": "route yet - held until its release is approved.", "position": 3,
    })
    variants = {
        "golden": golden,
        "nop": initial,
        "naive": outcome(initial, {"K17": ("B1", "Assigned"), "K24": ("B4", "Assigned"),
                                   "K31": ("B3", "Assigned")}, "K17 B1; K24 B4; K31 B3."),
        "slip_width": outcome(initial, {**GOOD, "K24": ("B2", "Assigned")},
                              "K17 B2 has power. K24 B2 has access. K31 hold for approval."),
        "slip_approval": outcome(initial, {**GOOD, "K31": ("B4", "Assigned")},
                                 "K17 B2 has power. K24 B3 has 1.20 m clearance. K31 B4."),
        "slip_arrow": outcome(initial, {**GOOD, "K17": ("B4", "Assigned")},
                              "K17 B4 has power. K24 B3 has 1.20 m clearance. K31 hold for approval."),
        "advice_only": outcome(initial, comment=COMMENT),
        "semicolon_comment": outcome(initial, GOOD, SEMICOLON_COMMENT),
        "semicolon_with_extra_todo": unintended_write,
        "neighbor_reason_only": outcome(
            initial, GOOD, "K17 B2 has power. K24 B3: inbound arrow permits entry; "
            "K31 hold pending release approval; its width fits."
        ),
        "wrong_bay_reason": outcome(
            initial, GOOD, "K17 B2 has power. K24 B3: inbound arrow permits entry; "
            "B4 has 1.25 m of clearance. K31 hold pending release approval."
        ),
    }
    for name, states in variants.items():
        for site, state in states.items():
            path = out / "variants" / name / "state" / site
            dump(path / "initial.json", initial[site])
            dump(path / "current.json", state)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
