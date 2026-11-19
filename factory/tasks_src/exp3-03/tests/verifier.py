"""Grade the Harbor 24 handoff from the three persisted site snapshots."""

from collections import defaultdict

from cuaverify import InfraError, load_site, run

TASK_ID = "cua-hard/harbor-iteration-handoff"
VERSION = "0.1.1"
EXCEL = "microsoft_excel_for_the_web"
BOOK = "wb-harbor-release"
HANDOFF = "h24-handoff"

# Harbor 23's posted Mattermost thread, ClickUp activity for HBR-181–183,
# and H23 Posted give the status/disposition pairs and sprint routing.
ACCEPTED = ("accepted", "harbor-24", "Accepted", "Harbor 24")
CONTINUED = ("ready to resume", "harbor-25", "Continued", "Harbor 25")
HELD = ("qa hold", "harbor-24", "Held", "Harbor 24")

# Rows come from H24 Handoff's blank production queue. The 09:00 UTC
# inclusive cutoff comes from Mattermost's harbor24-cutoff post.
EXPECTED = {
    "201": (3, ACCEPTED),   # H24 Evidence: 08:10 Pass
    "202": (7, ACCEPTED),   # 09:00 Pass with advisory
    "203": (5, CONTINUED),  # 08:12 Pending, implementation unfinished
    "204": (8, CONTINUED),  # 08:25 Pending, implementation unfinished
    "205": (2, HELD),       # 08:54 Reopened blocker supersedes yesterday's Pass
    "206": (4, HELD),       # 08:16 Blocker, replacement Pass at 09:12
}
EDITABLE_CELLS = {
    (BOOK, HANDOFF, f"{column}{row}")
    for row, _ in EXPECTED.values()
    for column in "CD"
}
TASK_EDIT_FIELDS = {"status", "sprintId", "sprintHistory", "updatedAt", "dateClosed", "closedBy"}
SHEET_VIEW_FIELDS = {"lastViewedAt", "lastOpenedAt"}


def load_collections(site, **collections):
    """Validate the snapshot structure used for grading and group records by identity."""
    try:
        snapshots = load_site(site)
    except UnicodeError as exc:
        raise InfraError(f"{site}: invalid snapshot encoding") from exc

    indexed = []
    for label, snapshot in zip(("initial", "current"), snapshots):
        if not isinstance(snapshot, dict):
            raise InfraError(f"{site}/{label}: expected an object")
        state = {}
        for name, fields in collections.items():
            records = snapshot.get(name)
            if not isinstance(records, list):
                raise InfraError(f"{site}/{label}: missing or invalid {name} collection")
            groups = defaultdict(list)
            for record in records:
                if not isinstance(record, dict) or any(
                    not isinstance(record.get(field), str) or not record[field]
                    for field in fields
                ):
                    raise InfraError(f"{site}/{label}: invalid identity in {name}")
                key = tuple(record[field] for field in fields)
                groups[key[0] if len(key) == 1 else key].append(record)
            state[name] = groups
        indexed.append(state)
    return indexed


def only(groups, key):
    records = groups.get(key, [])
    return records[0] if len(records) == 1 else {}


def without(record, fields):
    return {key: value for key, value in record.items() if key not in fields}


def active(groups, key):
    return only(groups, key).get("status") == "active"


def completed_task(before, after, key, status, sprint):
    old, new = only(before, key), only(after, key)
    history = ["harbor-24"] if sprint == "harbor-24" else ["harbor-24", sprint]
    business_fields = ("status", "sprintId", "sprintHistory")
    return bool(
        old and new
        and new.get("status") == status
        and new.get("sprintId") == sprint
        and new.get("sprintHistory") == history
        and new.get("listId") == "checkout"
        and new.get("archived") is False
        and new.get("deleted") is False
        and any(old.get(field) != new.get(field) for field in business_fields)
    )


def literal(cell, expected):
    return (
        cell.get("input") == expected
        and cell.get("formula") is None
        and cell.get("valueType", "string") == "string"
    )


def completed_row(before, after, row, key, disposition, ledger):
    if not active(after["workbooks"], BOOK) or not active(after["sheets"], (BOOK, HANDOFF)):
        return False
    cells_before, cells_after = before["cells"], after["cells"]
    if only(cells_after, (BOOK, HANDOFF, f"A{row}")).get("input") != key:
        return False
    for column, expected in (("C", disposition), ("D", ledger)):
        address = (BOOK, HANDOFF, f"{column}{row}")
        if not literal(only(cells_after, address), expected):
            return False
        if literal(only(cells_before, address), expected):
            return False
    return True


def clickup_preserved(before, after):
    tasks_before, tasks_after = before["tasks"], after["tasks"]
    if tasks_before.keys() != tasks_after.keys() or before["sprints"] != after["sprints"]:
        return False
    editable = {f"HBR-{suffix}" for suffix in EXPECTED}
    for key, records in tasks_before.items():
        final = tasks_after[key]
        if key in editable:
            if len(records) != 1 or len(final) != 1:
                return False
            if without(records[0], TASK_EDIT_FIELDS) != without(final[0], TASK_EDIT_FIELDS):
                return False
        elif records != final:
            return False
    return True


def excel_preserved(before, after):
    old_book, new_book = (only(state["workbooks"], BOOK) for state in (before, after))
    if new_book.get("status") != "active" or new_book.get("name") != old_book.get("name"):
        return False
    old_sheets, new_sheets = before["sheets"], after["sheets"]
    if old_sheets.keys() != new_sheets.keys():
        return False
    for key in old_sheets:
        old_sheet, new_sheet = only(old_sheets, key), only(new_sheets, key)
        if new_sheet.get("status") != "active":
            return False
        if without(old_sheet, SHEET_VIEW_FIELDS) != without(new_sheet, SHEET_VIEW_FIELDS):
            return False
    return without(before["cells"], EDITABLE_CELLS) == without(after["cells"], EDITABLE_CELLS)


def evaluate(g):
    cu_before, cu_after = load_collections("clickup", tasks=("id",), sprints=("id",))
    xl_before, xl_after = load_collections(
        EXCEL, workbooks=("id",), sheets=("workbookId", "id"),
        cells=("workbookId", "sheetId", "address"),
    )
    mm_before, mm_after = load_collections(
        "mattermost", posts=("id",), threads=("id",), pins=("id",),
    )

    any_cu = any_xl = False
    for suffix, (row, (status, sprint, disposition, ledger)) in EXPECTED.items():
        key = f"HBR-{suffix}"
        cu = completed_task(cu_before["tasks"], cu_after["tasks"], key, status, sprint)
        xl = completed_row(xl_before, xl_after, row, key, disposition, ledger)
        g.add(f"CU.{suffix}", 8, cu, f"{key} expects {status} in {sprint}", core=True)
        g.add(f"XL.{suffix}", 7, xl, f"Row {row} expects {disposition} and {ledger}", core=True)
        any_cu |= cu
        any_xl |= xl

    gate = any_cu and any_xl
    protections = (
        ("P.clickup", 6, clickup_preserved(cu_before, cu_after), "Task identities, protected fields and sprints"),
        ("P.excel", 3, excel_preserved(xl_before, xl_after), "Register, sheets and protected cells"),
        ("P.mattermost", 1, mm_before == mm_after, "Posts, threads and pins"),
    )
    for check, weight, preserved, detail in protections:
        if not gate:
            detail = "Requires one completed ClickUp task and one completed Excel row"
        elif not preserved:
            detail += " changed"
        else:
            detail += " preserved"
        g.add(check, weight, gate and preserved, detail)


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
