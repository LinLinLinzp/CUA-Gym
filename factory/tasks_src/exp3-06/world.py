"""Deterministic offline release-validation handoff."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar

ACTOR = "usr-jules-moreno"
LEAD = "usr-priya-das"
REVIEWER = "usr-amira-wong"
PEOPLE = [(ACTOR, "Jules Moreno"), (LEAD, "Priya Das"), (REVIEWER, "Amira Wong")]
STAMP = "2026-11-17T15:00:00.000Z"
NOW = "2026-11-18T15:20:00.000Z"
BATCH = "HBL-7116-Q"
OLD_BATCH = "HBL-7116-O"
APPROVAL = "RV-6429"
OLD_APPROVAL = "RV-6249"
TICKET = "rv-73mqd"
MIRROR = "rv-73mdq"
OLD_TICKET = "rv-41xkj"
REPO = "manifest-validator"
SHADOW = "manifest-validator-preview"
BRANCH = "release/nov-18"
CANDIDATE = "release/nov-18-rc"
STEP = "Validate manifest bundle"
WORKSPACE = "copperline-engineering"
EXCEL = "microsoft_excel_for_the_web"


def audit(when=STAMP, person=ACTOR):
    return dict(createdAt=when, createdBy=person, updatedAt=when, updatedBy=person)


def digest(label):
    return hashlib.sha1(label.encode()).hexdigest()


APPROVED_HASH = digest("manifest production-validation sample 7")
TIP_HASH = APPROVED_HASH[:7] + digest("normalization of fixture labels")[7:]


def build_mattermost():
    team = "team-acme"
    channels = ["town-square", "release-handoffs", "build-observations"]
    state = {key: [] for key in (
        "threads", "threadMemberships", "pins", "files", "drafts", "reactions",
        "savedPosts", "preferences", "activityLog",
    )}
    state.update(schemaVersion=1, currentUserId=ACTOR, currentTeamId=team,
                 teams=[dict(id=team, name="acme", displayName="Copperline Engineering",
                             description="Release operations", iconUrl=avatar("Copperline Engineering"),
                             createdAt=STAMP, updatedAt=STAMP)],
                 users=[], teamMembers=[], channelMembers=[], channels=[], posts=[])
    for uid, name in PEOPLE:
        first, last = name.split()
        state["users"].append(dict(id=uid, username=(first + last).lower(), firstName=first,
                                   lastName=last, email=f"{first.lower()}@copperline.example",
                                   position="Release Operations", avatarUrl=avatar(name),
                                   status="active", presence="online", isGuest=False,
                                   createdAt=STAMP, updatedAt=STAMP))
        state["teamMembers"].append(dict(id=f"member-{uid}", teamId=team, userId=uid,
                                         role="team_user", status="active", createdAt=STAMP,
                                         updatedAt=STAMP))
    for slug, name in zip(channels, ["Town Square", "Release Handoffs", "Build Observations"]):
        cid = f"ch-{slug}"
        state["channels"].append(dict(id=cid, teamId=team, name=slug, displayName=name, type="O",
                                      purpose="Internal release coordination", header="",
                                      status="active", isDefault=slug == "town-square",
                                      createdBy=LEAD, archivedBy=None, archivedAt=None,
                                      createdAt=STAMP, updatedAt=STAMP))
        for uid, _ in PEOPLE:
            state["channelMembers"].append(dict(
                id=f"{cid}-{uid}", channelId=cid, userId=uid, role="channel_user", status="active",
                addedBy=LEAD, joinedAt=STAMP, leftAt=None, isFavorite=False, muted=False,
                lastViewedAt=STAMP, lastReadPostId=None, createdAt=STAMP, updatedAt=STAMP))
    state["sidebarCategories"] = [
        dict(id="cat-channels", userId=ACTOR, teamId=team, name="Channels", type="channels",
             channelIds=[f"ch-{slug}" for slug in channels], order=0, collapsed=False,
             createdAt=STAMP, updatedAt=STAMP)
    ]

    def post(pid, message, when, author, channel="release-handoffs", root=None):
        state["posts"].append(dict(id=pid, channelId=f"ch-{channel}", userId=author,
                                   rootId=root, message=message, fileIds=[], mentionedUserIds=[],
                                   isPinned=False, editedAt=None, deletedAt=None, deletedBy=None,
                                   createdAt=when, updatedAt=when))

    for index, customer in enumerate(("Bellwether", "Meridian", "Peregrine", "Seabrook",
                                       "Kestrel", "Lakeshore", "Redwood", "Juniper")):
        for offset, message in enumerate((
            f"{customer} sample bundle cleared intake. QA will post follow-up if a replay is needed.",
            f"{customer} schema snapshot archived with the morning manifest exports.",
            f"{customer} receipt reconciled. Keep the existing report with the release record.",
        )):
            post(f"post-{index}-{offset}", message,
                 f"2026-11-18T{10 + offset:02}:{index * 5:02}:00.000Z", PEOPLE[offset][0],
                 channels[[1, 2, 0][offset]])
    root = "post-harborlight-handoff"
    post(root, f"Harborlight November validation handoff. Intake gave me batch {OLD_BATCH}. "
         "Jules, please pick up the validation-only retry using the November Release Register "
         "in Excel once QA confirms the customer manifest.", "2026-11-18T14:03:00.000Z", LEAD)
    reply_time = "2026-11-18T14:26:00.000Z"
    post("post-harborlight-confirmed",
         f"QA checked the customer manifest. The live Harborlight batch is {BATCH} (ends in Q). "
         f"Intake's {OLD_BATCH} came from the preview shipment. Start in Batch Intake and use "
         "the approval key there to find the run and work item in Retry Approvals.",
         reply_time, REVIEWER, root=root)
    state["threads"].append(dict(id=root, rootPostId=root, channelId="ch-release-handoffs",
                                 replyCount=1, lastReplyAt=reply_time, participantIds=[LEAD, REVIEWER],
                                 createdAt=reply_time, updatedAt=reply_time))
    post("post-courier", "Courier handoff moved to 11:30. Keep the receiving window on the board.",
         "2026-11-18T14:38:00.000Z", LEAD)
    return state


def build_excel():
    book = "wb-november-release"
    state = {key: [] for key in ("tables", "filters", "sorts", "shares", "shareLinks",
                                "comments", "charts", "operations", "conditionalFormats",
                                "validationRules")}
    state.update(schemaVersion=1, currentUserId=ACTOR, preferences=dict(ribbonMode="classic", zoom=100),
                 users=[dict(id=uid, displayName=name, email=f"{name.split()[0].lower()}@copperline.example",
                             initials="".join(part[0] for part in name.split()), avatarColor="#235579")
                        for uid, name in PEOPLE],
                 workbooks=[dict(id=book, name="November Release Register", ownerId=ACTOR,
                                 location="OneDrive / Documents / Release Operations", status="active",
                                 favoriteUserIds=[ACTOR], activeSheetId="sheet-intake",
                                 lastOpenedAt=STAMP, **audit())], sheets=[], cells=[])
    intake = [["Customer batch", "Customer", "Disposition", "Approval key", "Environment"]]
    approvals = [["Approval key", "Decision", "Repository", "Branch", "Full commit SHA",
                  "Pipeline", "Allowed failed step", "ClickUp work item"]]
    for index, customer in enumerate(("Kestrel", "Seabrook", "Lakeshore", "Meridian", "Redwood",
                                       "Juniper", "Bellwether", "Peregrine") * 4):
        key = f"RV-{6500 + index}"
        intake.append([f"{customer[:3].upper()}-{7210 + index}-A", customer, "Filed", key,
                       "Validation sandbox"])
        approvals.append([key, "Closed", REPO, BRANCH, digest(f"filed-{index}"),
                          "Manifest validation", STEP, f"https://app.clickup.com/t/rv-closed-{index}"])
    # These independent approvals share the same pipeline label and validation step.
    for index, row_key, branch, sha in (
        (2, "RV-6502", CANDIDATE, APPROVED_HASH),
        (4, "RV-6504", BRANCH, TIP_HASH),
    ):
        intake[index + 1][2] = "Released to QA"
        approvals[index + 1] = [
            row_key, "Approved", REPO, branch, sha, "Manifest validation", STEP,
            f"https://app.clickup.com/t/rv-closed-{index}",
        ]
    intake[7:7] = [[OLD_BATCH, "Harborlight", "Preview only", OLD_APPROVAL, "Preview sandbox"],
                   [BATCH, "Harborlight", "Released to QA", APPROVAL, "Validation sandbox"]]
    approvals[7:7] = [
        [OLD_APPROVAL, "Preview approval", SHADOW, BRANCH, APPROVED_HASH,
         "Manifest validation", STEP, f"https://app.clickup.com/t/{OLD_TICKET}"],
        [APPROVAL, "Approved", REPO, BRANCH, APPROVED_HASH, "Manifest validation", STEP,
         f"https://app.clickup.com/t/{TICKET}"],
    ]
    for position, (sheet, name, rows, widths) in enumerate([
        ("sheet-intake", "Batch Intake", intake, [155, 125, 164, 125, 170]),
        ("sheet-approvals", "Retry Approvals", approvals, [100, 135, 200, 130, 306, 155, 180, 270]),
    ]):
        state["sheets"].append(dict(id=sheet, workbookId=book, name=name, position=position,
                                    visibility="visible", status="active", tabColor=None,
                                    autoFilterRange=None, frozenRows=1, frozenColumns=1,
                                    columnWidths={str(i): w for i, w in enumerate(widths, 1)}, **audit()))
        for row, values in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                address = f"{chr(64 + col)}{row}"
                state["cells"].append(dict(id=f"cell-{sheet}-{address}", workbookId=book, sheetId=sheet,
                                           row=row, column=col, address=address, input=value,
                                           value=value, valueType="string", formula=None, error=None,
                                           dependencies=[], **audit()))
    return state


def section(label, status, duration, *lines):
    return dict(id=label.lower().replace(" ", "-"), label=label, status=status,
                durationSeconds=duration, lines=list(lines))


def receipt(repo, number):
    return f"Validation receipt: MV-{number}-{('Z9K2' if repo == REPO else 'P4C7')}"


def build_bitbucket():
    ws, project = "ws-copperline", "prj-release"
    state = {key: [] for key in (
        "repositoryStars", "branches", "commits", "pullRequests", "pullRequestComments",
        "pullRequestTasks", "pullRequestReviews", "pullRequestActivity",
        "repositories", "pipelineDefinitions", "pipelineRuns",
    )}
    state.update(currentUserId=ACTOR,
                 workspaces=[dict(id=ws, slug=WORKSPACE, name="Copperline Engineering")],
                 projects=[dict(id=project, workspaceId=ws, key="REL", name="Release Engineering")],
                 users=[dict(id=uid, name=name, username=name.lower().replace(" ", ""),
                             workspaceIds=[ws], avatarColor="#235579", avatarUrl=avatar(name))
                        for uid, name in PEOPLE])
    for repo in (REPO, SHADOW, "schema-diff", "fixture-catalog"):
        rid = f"repo-{repo}"
        main, release, rc = (f"br-{repo}-{suffix}" for suffix in ("main", "release", "rc"))
        commits = [(f"cmt-{repo}-{i}", digest(f"{repo}-{i}")) for i in range(19)]
        commits[7] = (commits[7][0], APPROVED_HASH)
        commits[-1] = (commits[-1][0], TIP_HASH)
        state["repositories"].append(dict(
            id=rid, workspaceId=ws, projectId=project, name=repo, slug=repo,
            description="Offline sample and schema validation", visibility="private",
            defaultBranchId=main, pipelinesEnabled=True, pipelineConfiguredAt=STAMP,
            pipelineConfiguredBy=LEAD, **audit()))
        for branch_id, name, head, parent in (
            (main, "main", commits[0][0], None), (release, BRANCH, commits[-1][0], main),
            (rc, CANDIDATE, commits[7][0], release),
        ):
            state["branches"].append(dict(id=branch_id, repositoryId=rid, name=name,
                                          headCommitId=head, sourceBranchId=parent, **audit()))
        for i, (cid, sha) in enumerate(commits):
            state["commits"].append(dict(
                id=cid, repositoryId=rid, branchId=release if i else main, hash=sha,
                message="Refresh sample manifest fixtures" if i else "Initialize offline manifest checks",
                parentIds=[commits[i - 1][0]] if i else [],
                changes=[dict(path="fixtures/manifest-cases.txt", operation="modify" if i else "add",
                              content=f"Offline validation case set {i}\n")], createdAt=STAMP, createdBy=LEAD))
        definition = f"def-{repo}"
        unpack = dict(key="unpack", name="Unpack sample fixtures", fixtureStatus="successful",
                      fixtureDurationSeconds=8, fixtureLogSections=[
                          section("Fixture intake", "successful", 8, "Loaded 18 offline sample fixtures.")])
        validate = dict(key="validate", name=STEP, fixtureStatus="successful", fixtureDurationSeconds=23,
                        fixtureLogSections=[section("Manifest check", "successful", 23,
                                                    "18 manifests checked. No differences.")])
        state["pipelineDefinitions"].append(dict(id=definition, repositoryId=rid, name="Manifest validation",
                                                  type="branch", configPath="bitbucket-pipelines.yml",
                                                  configCommitId=commits[0][0], steps=[unpack, validate],
                                                  **audit()))
        nums = list(range(475, 489)) if repo in (REPO, SHADOW) else list(range(304, 316))
        for i, number in enumerate(nums):
            near = repo in (REPO, SHADOW) and number in (482, 484, 487)
            cid, sha = commits[7 if near and number != 487 else -1 if near else min(i, 17)]
            branch_id, branch_name = (rc, CANDIDATE) if near and number == 484 else (release, BRANCH)
            status = "failed" if near else "successful"
            snapshot_step = copy.deepcopy(validate)
            if near:
                snapshot_step.update(fixtureStatus="failed", retryFixtureStatus="successful",
                                     fixtureLogSections=[section(
                                         "Manifest check", "failed", 23,
                                         "Fixture volume returned a transient read timeout.",
                                         f"Validation receipt: MV-{number}-PENDING")],
                                     retryFixtureLogSections=[section(
                                         "Manifest check", "successful", 23,
                                         "18 manifests checked. No differences.", receipt(repo, number))])
            templates = [copy.deepcopy(unpack), snapshot_step]
            when = f"2026-11-18T13:{i * 3:02}:00.000Z"
            finished = (datetime.fromisoformat(when) + timedelta(seconds=31)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            run_id = f"run-{repo}-{number}"
            steps = []
            for template in templates:
                sid = f"step-{repo}-{number}-{template['key']}"
                steps.append(dict(id=sid, definitionStepKey=template["key"], name=template["name"],
                                  attempts=[dict(id=f"att-{sid}-1", number=1, status=template["fixtureStatus"],
                                                 startedAt=when, finishedAt=finished,
                                                 durationSeconds=template["fixtureDurationSeconds"],
                                                 logSections=template["fixtureLogSections"], **audit(when, REVIEWER))]))
            state["pipelineRuns"].append(dict(
                id=run_id, repositoryId=rid, buildNumber=number, definitionId=definition,
                definitionSnapshot=dict(name="Manifest validation", type="branch", steps=templates),
                branchId=branch_id, branchName=branch_name, commitId=cid, commitHash=sha, trigger="push",
                variables={}, status=status, startedAt=when, finishedAt=finished,
                durationSeconds=31, steps=steps, retries=[], **audit(when, REVIEWER)))
    return state


def make_comment(comment_id, task, text, author, when):
    return dict(id=comment_id, parentType="task", parentId=task, pageId=None, blockId=None, quote=None, authorId=author,
                text=text, mentions=[], assigneeId=None, replyToId=None, reactions=[],
                resolved=False, createdAt=when, updatedAt=None)


def build_clickup():
    space, validation, archive = "space-release", "list-validation", "list-audit"
    state = {key: [] for key in ("teams", "folders", "sprints", "customFields", "tags", "activity",
                                "docs", "docPages", "timeEntries", "timeTags", "timesheets",
                                "notifications", "favorites", "trash", "dashboards")}
    state.update(currentUserId=ACTOR, timer=None, viewSettings={},
                 preferences=dict(theme="light", startOfWeek="monday", timeFormat="12h"),
                 timesheetSettings=dict(approvalsEnabled=False, approvers={uid: [LEAD] for uid in (ACTOR, REVIEWER)}, dailyCapacityHours=8,
                                        weeklyCapacityHours=40, deadline=dict(day="monday", time="10:00"),
                                        reminders=dict(before=True, after=True)),
                 workspace=dict(id="cu-copperline", name="Copperline Engineering", initials="CE",
                                color="#235579", plan="Business", clickApps=dict(
                                    sprintPoints=True, timeTracking=True, timeEstimates=True,
                                    multipleAssignees=True, billableDefault=False), sprintPointScale=[1, 2, 3, 5, 8]),
                 users=[dict(id=uid, name=name, email=f"{name.split()[0].lower()}@copperline.example",
                             initials="".join(part[0] for part in name.split()), color="#235579",
                             role="member", title="Release Operations", timezone="America/New_York",
                             weeklyCapacityHours=40, status="online") for uid, name in PEOPLE],
                 spaces=[dict(id=space, name="Release Operations", color="#235579", icon="rocket",
                              private=False, memberIds=[p[0] for p in PEOPLE], orderIndex=0,
                              createdAt=STAMP, statuses=[dict(id="st-open", name="Open", color="#717784",
                                                              type="open", orderIndex=0)])],
                 lists=[dict(id=lid, spaceId=space, folderId=None, name=name, color="#235579",
                             isBacklog=False, orderIndex=i, createdAt=STAMP, archived=False)
                        for i, (lid, name) in enumerate([(validation, "Validation Queue"), (archive, "Audit Intake")])],
                 tasks=[], comments=[])
    items = [
        (TICKET, "Harborlight · November manifest validation", validation,
         "Customer validation work item. QA will use the evidence here during receipt reconciliation."),
        (MIRROR, "Harborlight · November manifest validation (audit copy)", archive,
         "Audit intake mirror for tracking assignment history."),
        (OLD_TICKET, "Harborlight · Preview manifest validation", validation,
         "Internal preview bundle. Keep evidence here for preview-only work."),
    ]
    for index, customer in enumerate(("Kestrel", "Seabrook", "Lakeshore", "Meridian", "Redwood",
                                      "Juniper", "Bellwether", "Peregrine") * 4):
        items.append((f"rv-closed-{index}", f"{customer} · Manifest validation {index + 1}", validation,
                      "Filed with customer operations."))
    for i, (tid, name, lid, description) in enumerate(items):
        state["tasks"].append(dict(
            id=tid, name=name, description=description, status="open", priority="normal",
            assigneeIds=[ACTOR], watcherIds=[], tags=[], listId=lid, sprintId=None,
            sprintHistory=[], parentId=None, startDate=None, dueDate=None, timeEstimate=None,
            sprintPoints=None, customFields={}, checklists=[], linkedDocIds=[],
            dependencies=dict(waitingOn=[], blocking=[]), orderIndex=i, createdBy=LEAD,
            createdAt=STAMP, updatedAt=STAMP, dateClosed=None, closedBy=None, archived=False,
            deleted=False, deletedAt=None, deletedBy=None, attachments=[]))
        if i < 3:
            state["comments"].append(make_comment(
                f"cm-intake-{i}", tid, "Intake recorded. Keep this work item open for the reconciliation team.",
                LEAD, STAMP))
    return state


def retry(states, repo, number):
    run = next(r for r in states["bitbucket"]["pipelineRuns"] if r["id"] == f"run-{repo}-{number}")
    step = next(s for s in run["steps"] if s["definitionStepKey"] == "validate")
    template = next(s for s in run["definitionSnapshot"]["steps"] if s["key"] == "validate")
    retry_id = f"retry-{repo}-{number}-1"
    duration = template["fixtureDurationSeconds"]
    step["attempts"].append(dict(id=f"att-{step['id']}-2", number=2, retryId=retry_id,
                                 status="successful", startedAt=NOW, finishedAt=NOW,
                                 durationSeconds=duration, logSections=template["retryFixtureLogSections"],
                                 **audit(NOW)))
    run["retries"].append(dict(id=retry_id, number=1, stepIds=[step["id"]], status="successful",
                               finishedAt=NOW, durationSeconds=duration, createdAt=NOW, createdBy=ACTOR))
    run.update(status="successful", finishedAt=NOW, durationSeconds=31, updatedAt=NOW, updatedBy=ACTOR)
    return step["id"]


def view_register(excel):
    workbook = excel["workbooks"][0]
    book_id = workbook["id"]
    previous_open = workbook["lastOpenedAt"]
    previous_sheet = workbook["activeSheetId"]
    workbook.update(lastOpenedAt=NOW, activeSheetId="sheet-approvals")
    excel["operations"].extend([
        dict(id="op-open-register", type="workbook.open", actorId=ACTOR, createdAt=NOW,
             workbookId=book_id, sheetId=None, targetIds=[book_id],
             details=dict(before=previous_open, lastOpenedAt=NOW)),
        dict(id="op-select-approvals", type="sheet.select", actorId=ACTOR, createdAt=NOW,
             workbookId=book_id, sheetId="sheet-approvals", targetIds=["sheet-approvals"],
             details=dict(before=previous_sheet, activeSheetId="sheet-approvals")),
    ])


def run_variant(seed, repo=REPO, number=482, batch=BATCH, ticket=TICKET, old_receipt=False):
    result = copy.deepcopy(seed)
    view_register(result[EXCEL])
    step = retry(result, repo, number)
    url = (f"https://bitbucket.org/{WORKSPACE}/{repo}/pipelines/results/{number}"
           f"?step={step}&attempt=2")
    line = f"Validation receipt: MV-{number}-PENDING" if old_receipt else receipt(repo, number)
    text = f"{batch} | {STEP} | Attempt 2 successful | {line} | {url}"
    result["clickup"]["comments"].append(make_comment("cm-retry-evidence", ticket, text, ACTOR, NOW))
    return result


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(out):
    seed = {"bitbucket": build_bitbucket(), "mattermost": build_mattermost(),
            EXCEL: build_excel(), "clickup": build_clickup()}
    golden = run_variant(seed)
    variants = {
        "golden": golden,
        "nop": seed,
        "naive": run_variant(seed, SHADOW, 487, OLD_BATCH, OLD_TICKET, old_receipt=True),
        "slip_old_receipt": run_variant(seed, old_receipt=True),
        "slip_mirror_ticket": run_variant(seed, ticket=MIRROR),
    }
    for site in seed:
        write(out / "seed" / f"{site}.json", seed[site])
        write(out / "golden" / f"{site}.json", golden[site])
        for name, states in variants.items():
            root = out / "variants" / name
            (root / "output").mkdir(parents=True, exist_ok=True)
            write(root / "state" / site / "initial.json", seed[site])
            write(root / "state" / site / "current.json", states[site])
    for directory in ("input", "golden_output"):
        (out / directory).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
