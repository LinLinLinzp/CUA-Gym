"""Verify Riverside assignments against the approved plan and the original job records."""

import re

from cuaverify import InfraError, load_site, new_items, plain, run

TABLE = "tbl_riverside_load"
PROJECT = "project-riverside"
TODO = "todo-riverside-load-in"
KIT_ID = re.compile(r"\bk(?:17|24|31)\b")
BAY_ID = re.compile(r"\bb[1-5]\b")
# Independent reading of the approved Rev C attachment and load-in checklist:
# B1 intersects the protected route, and B4's arrow points toward the corridor.
# B2 is powered and admits 0.90 m. B3 admits 1.20 m with no outlet.
TARGETS = {
    "K17": ("B2", "Assigned"),
    "K24": ("B3", "Assigned"),
    "K31": ("", "Hold"),
}


def records(state):
    try:
        return {record["id"]: record["fields"] for record in state["tables"][TABLE]["records"]}
    except (KeyError, TypeError) as exc:
        raise InfraError("Riverside Load List is missing") from exc


def placement(fields):
    return (str(fields.get("bay") or "").strip().upper(),
            str(fields.get("disposition") or "").strip().lower())


def placement_score(before, after, target):
    bay, disposition = target
    return float(
        placement(before) != placement(after) and
        placement(after) == (bay.upper(), disposition.lower())
    )


def explains_assignment(segments, kit, assignment, reason):
    for index, segment in enumerate(segments):
        if set(KIT_ID.findall(segment)) != {kit} or not re.search(assignment, segment):
            continue
        if re.search(reason, segment):
            return True
        assignment_bays = set(BAY_ID.findall(segment))
        for continuation in segments[index + 1:]:
            if set(KIT_ID.findall(continuation)) - {kit}:
                break
            mentioned_bays = set(BAY_ID.findall(continuation))
            if mentioned_bays and not mentioned_bays.intersection(assignment_bays):
                continue
            if re.search(reason, continuation):
                return True
    return False


def reply_score(before, after):
    comments = new_items(before["comments"], after["comments"])
    if len(comments) != 1:
        return 0
    note = comments[0]
    if (note.get("parentType") != "todo" or note.get("parentId") != TODO
            or note.get("projectId") != PROJECT or note.get("status", "active") != "active"
            or note.get("createdById") != before["workspace"]["currentUserId"]):
        return 0
    body = plain(note.get("bodyHtml"))
    # The assignment identifies its kit. Following clauses can explain it until another kit starts.
    segments = re.split(r"[\n;]|(?<!\d)\.\s|(?<=\w)\.\s(?=[A-Za-z])", body)
    found = {}
    patterns = {
        "K17": (r"\bb2\b", r"power|outlet|socket|0\.9\d*|90\s*cm"),
        "K24": (r"\bb3\b", r"1\.2\d*|120\s*cm|clearance|wide|width|room"),
        "K31": (r"hold|wait|pending|release", r"approv|release|clearance"),
    }
    for kit, (assignment, reason) in patterns.items():
        found[kit] = explains_assignment(segments, kit.lower(), assignment, reason)
    return sum((0.35, 0.35, 0.30)[i] for i, ok in enumerate(found.values()) if ok)


def evaluate(g):
    initial, current = load_site("airtable")
    base_initial, base_current = load_site("basecamp")
    load_site("gmail")
    before, after = records(initial), records(current)
    seed_ids = {fields["kit"]: ident for ident, fields in before.items()
                if fields.get("kit") in TARGETS}
    if seed_ids.keys() != TARGETS.keys() or not any(row["id"] == TODO for row in base_initial["todos"]):
        raise InfraError("Riverside task seed is incomplete")
    results = []
    for index, (kit, expected) in enumerate(TARGETS.items(), 1):
        ident = seed_ids[kit]
        score = placement_score(before[ident], after.get(ident, {}), expected)
        results.append(score)
        g.add(f"V{index}", {"K17": 25, "K24": 25, "K31": 15}[kit], score,
              f"{kit}: {placement(after.get(ident, {}))} expected {expected}")
    g.add("B1", 20, reply_score(base_initial, base_current), "Original Basecamp to-do and route rationale")
    unchanged = before.keys() == after.keys()
    for ident, fields in before.items():
        allowed = {"bay", "disposition"} if ident in seed_ids.values() else set()
        unchanged &= ({key: val for key, val in fields.items() if key not in allowed}
                      == {key: val for key, val in after.get(ident, {}).items() if key not in allowed})
    keys = ("projects", "todoLists", "todos", "messageBoards", "messages", "scheduleEntries")
    unchanged &= all(base_initial[key] == base_current[key] for key in keys)
    existing = {row["id"]: row for row in base_initial["comments"]}
    unchanged &= existing == {row["id"]: row for row in base_current["comments"] if row["id"] in existing}
    g.add("P1", 15, bool(any(results[:2]) and unchanged), "Business inputs and protected records unchanged")


if __name__ == "__main__":
    run("cua-hard/riverside-showcase-placement", "0.1.2", evaluate)
