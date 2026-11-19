"""Grade the Harborlight validation retry from persisted site state."""

import html
import json
import re
from urllib.parse import parse_qs, urlsplit

from cuaverify import InfraError, load_site, plain, run


TASK_ID = "cua-hard/harborlight-validation-retry"
VERSION = "0.1.2"

# The Mattermost QA reply corrects the preview batch. Batch Intake A9:D9
# maps the live batch to RV-6429, and Retry Approvals A9:H9 gives its target.
BATCH = "HBL-7116-Q"
PREVIEW_BATCH = "HBL-7116-O"
TASK = "rv-73mqd"
STEP_NAME = "Validate manifest bundle"
# Match Retry Approvals' full SHA against the Bitbucket seed's run records.
RUN = "run-manifest-validator-482"
STEP = "step-manifest-validator-482-validate"
IDENTITY = {
    "repositoryId": "repo-manifest-validator",
    "buildNumber": 482,
    "branchName": "release/nov-18",
    "commitId": "cmt-manifest-validator-7",
    "commitHash": "5e77be6ef6a39321d173d39f6dcee788bbf8913c",
    "definitionId": "def-manifest-validator",
}
ATTEMPT_PATH = "/copperline-engineering/manifest-validator/pipelines/results/482"
# Jules is the signed-in seed user. The run snapshot's validation retry
# fixture gives successful, 23 seconds and this receipt. Unpack takes 8s.
ACTOR = "usr-jules-moreno"
OUTCOME = "successful"
RETRY_SECONDS = 23
RUN_SECONDS = 31
RECEIPT = "Validation receipt: MV-482-Z9K2"
URL = re.compile(r"""https?://[^\s<>"'\x60\])}]+""", re.I)
ATTEMPT_TWO = (
    r"\b(?:attempt\s*(?:no\.?\s*|number\s*|[#:]\s*)?(?:2|two)\b"
    r"(?![.-]\d)|(?:second|2nd)\s+(?:validation\s+)?attempt\b)"
)
OUTCOME_SEPARATOR = (
    r"[\s,:·\-–—]+(?:(?:result|outcome|status)\s*[:=]?\s*)?"
    r"(?:(?:is|was|has|ended|finished)\s+)?"
)
SUCCESS_WORDS = r"(?:successful(?:ly)?|success|passed|succeeded|(?:completed|finished|ended)\s+successfully)"
FAILURE_WORDS = (
    rf"(?:failed|failure|unsuccessful|(?:not|never)\s+{SUCCESS_WORDS}"
    r"|(?:didn't|did not)\s+(?:pass|succeed))"
)


def canonical(value, field=None):
    """Compare collections without array order, retaining ordered logs/attempts."""
    if isinstance(value, dict):
        return {key: canonical(item, key) for key, item in value.items()}
    if isinstance(value, list):
        items = [canonical(item) for item in value]
        if field not in {"attempts", "logSections", "fixtureLogSections",
                         "retryFixtureLogSections", "lines"}:
            items.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return items
    return value


def same(before, after):
    # JSON also distinguishes integer state fields from booleans and floats.
    return json.dumps(canonical(before), sort_keys=True) == json.dumps(
        canonical(after), sort_keys=True
    )


def index(records, label):
    if not isinstance(records, list):
        raise InfraError(f"{label} must be a list")
    by_id = {}
    for record in records:
        if not isinstance(record, dict):
            raise InfraError(f"invalid record in {label}")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id or record_id in by_id:
            raise InfraError(f"missing or duplicate ID in {label}")
        by_id[record_id] = record
    return by_id


def remove_fields(record, *fields):
    return {key: value for key, value in record.items() if key not in fields}


def read_site(site, *collections):
    try:
        initial, current = load_site(site)
    except UnicodeError as exc:
        raise InfraError(f"invalid encoding in {site} state") from exc
    for state in (initial, current):
        if not isinstance(state, dict):
            raise InfraError(f"{site} state must be an object")
        for field in collections:
            index(state.get(field), f"{site}.{field}")
    return initial, current


def fields_match(record, expected):
    return same({key: record.get(key) for key in expected}, expected)


def source_preserved(bitbucket, excel, mattermost, clickup):
    old_bb, new_bb = bitbucket
    old_xl, new_xl = excel
    old_mm, new_mm = mattermost
    old_cu, new_cu = clickup
    protected_excel = ("cells", "sheets", "tables", "filters", "sorts",
                       "shares", "shareLinks")
    old_books, new_books = (
        [remove_fields(book, "lastOpenedAt", "activeSheetId")
         for book in state["workbooks"]]
        for state in excel
    )
    old_ops, new_ops = (index(state["operations"], "Excel operations") for state in excel)
    old_comments, new_comments = (
        index(state["comments"], "ClickUp comments") for state in clickup
    )
    old_run, new_run = (
        next((record for record in state["pipelineRuns"] if record["id"] == RUN), {})
        for state in bitbucket
    )
    return (
        same(remove_fields(old_bb, "pipelineRuns"), remove_fields(new_bb, "pipelineRuns"))
        and same(old_run.get("variables"), new_run.get("variables"))
        and all(same(old_xl[key], new_xl[key]) for key in protected_excel)
        and same(old_books, new_books)
        and all(same(op, new_ops.get(key)) for key, op in old_ops.items())
        and all(new_ops[key].get("type") in {"workbook.open", "sheet.select"}
                for key in new_ops.keys() - old_ops.keys())
        and all(same(old_mm[key], new_mm[key]) for key in ("posts", "pins", "files"))
        and same(old_cu["tasks"], new_cu["tasks"])
        and all(same(comment, new_comments.get(key)) for key, comment in old_comments.items())
    )


def check_retry(bitbucket):
    old_runs, new_runs = (
        index(state["pipelineRuns"], "Bitbucket pipelineRuns") for state in bitbucket
    )
    original = old_runs.get(RUN)
    if original is None or not fields_match(original, IDENTITY):
        raise InfraError("approved build missing or mismatched in initial Bitbucket state")
    if not isinstance(original.get("definitionSnapshot"), dict):
        raise InfraError("approved build's initial definition snapshot is missing or invalid")
    current = new_runs.get(RUN)
    if current is None:
        return (False,) * 5

    old_groups, new_groups = (
        index(record.get("retries", []), "approved build retries")
        for record in (original, current)
    )
    old_steps, new_steps = (
        index(record.get("steps"), "approved build steps")
        for record in (original, current)
    )
    if STEP not in old_steps:
        raise InfraError("approved step missing in initial Bitbucket state")
    old_attempts = old_steps[STEP].get("attempts")
    old_attempt_ids = index(old_attempts, "initial validation attempts")
    if not old_attempts:
        raise InfraError("initial validation attempt missing")
    attempts = new_steps[STEP].get("attempts") if STEP in new_steps else []
    index(attempts, "current validation attempts")
    added_groups = [new_groups[key] for key in new_groups.keys() - old_groups.keys()]

    approved = (
        bool(added_groups)
        and all(same(group, new_groups.get(key)) for key, group in old_groups.items())
        and fields_match(current, IDENTITY)
        and same(original["definitionSnapshot"], current.get("definitionSnapshot"))
    )
    if not approved:
        return (False,) * 5

    one_group = len(added_groups) == 1 and fields_match(added_groups[0], {
        "number": 1, "stepIds": [STEP], "createdBy": ACTOR,
        "status": OUTCOME, "durationSeconds": RETRY_SECONDS,
    })
    new_attempt = (
        one_group
        and len(attempts) == len(old_attempts) + 1
        and [item["id"] for item in attempts[:-1]] == list(old_attempt_ids)
        and fields_match(attempts[-1], {
            "number": 2, "retryId": added_groups[0]["id"], "createdBy": ACTOR,
            "status": OUTCOME, "durationSeconds": RETRY_SECONDS,
        })
        and receipt_in_log(attempts[-1])
        and fields_match(current, {"status": OUTCOME, "durationSeconds": RUN_SECONDS})
    )
    preserve_attempts = (
        old_steps.keys() == new_steps.keys()
        and all(same(step, new_steps[key]) for key, step in old_steps.items() if key != STEP)
        and bool(attempts)
        and same(old_attempts[0], attempts[0])
    )
    preserve_runs = old_runs.keys() == new_runs.keys() and all(
        same(record, new_runs[key]) for key, record in old_runs.items() if key != RUN
    )
    return approved, one_group, new_attempt, preserve_attempts, preserve_runs


def receipt_in_log(attempt):
    sections = index(attempt.get("logSections", []), "retry log sections")
    for section in sections.values():
        lines = section.get("lines", [])
        if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
            raise InfraError("invalid retry log lines")
        if RECEIPT in lines:
            return True
    return False


def has_attempt_link(body):
    for match in URL.finditer(html.unescape(body)):
        try:
            url = urlsplit(match.group().rstrip(".,;:!?"))
            query = parse_qs(url.query, keep_blank_values=True)
            if (url.scheme == "https" and url.hostname == "bitbucket.org"
                    and url.username is None and url.port in (None, 443)
                    and url.path == ATTEMPT_PATH and query.get("step") == [STEP]
                    and query.get("attempt") == ["2"]):
                return True
        except ValueError:
            continue
    return False


def successful_attempt_summary(prose):
    """Bind the result to attempt 2 in either common word order."""
    def reports(outcome):
        return re.search(
            rf"(?:{ATTEMPT_TWO}{OUTCOME_SEPARATOR}\b{outcome}\b"
            rf"|\b{outcome}\s+(?:on|in|for)\s+(?:the\s+)?{ATTEMPT_TWO})",
            prose,
        )

    return bool(
        re.search(rf"\b{STEP_NAME.lower()}\b", prose)
        and reports(SUCCESS_WORDS)
        and not reports(FAILURE_WORDS)
    )


def check_comment(clickup, new_attempt):
    initial, current = clickup
    old_comments = index(initial["comments"], "initial ClickUp comments")
    added = [row for row in current["comments"] if row["id"] not in old_comments]
    if len(added) != 1:
        return (False,) * 5
    comment = added[0]
    body = comment.get("text")
    if not isinstance(body, str):
        raise InfraError("ClickUp comment text is missing or invalid")
    destination = (
        any(task["id"] == TASK for task in initial["tasks"])
        and any(task["id"] == TASK for task in current["tasks"])
        and fields_match(comment, {"parentType": "task", "parentId": TASK, "authorId": ACTOR})
        and comment.get("replyToId") in (None, "")
        and bool(plain(body))
    )
    if not destination:
        return (False,) * 5

    # Keep query parameters out of the prose checks and remove formatting.
    prose = plain(URL.sub(" ", body)).replace("*", "").replace("`", "")
    batch = (
        bool(re.search(rf"(?<![\w-]){BATCH}(?![\w-])", prose, re.I))
        and re.search(rf"(?<![\w-]){PREVIEW_BATCH}(?![\w-])", prose, re.I) is None
    )
    summary = successful_attempt_summary(prose)
    receipt = bool(re.search(
        rf"(?<![\w-]){re.escape(RECEIPT.lower())}(?![\w-])", prose
    ))
    return destination, batch, new_attempt and has_attempt_link(body), summary, new_attempt and receipt


def evaluate(g):
    bitbucket = read_site("bitbucket", "pipelineRuns")
    excel = read_site("microsoft_excel_for_the_web", "workbooks", "operations",
                      "cells", "sheets", "tables", "filters", "sorts", "shares", "shareLinks")
    mattermost = read_site("mattermost", "posts", "pins", "files")
    clickup = read_site("clickup", "tasks", "comments")

    approved, group, attempt, steps, builds = check_retry(bitbucket)
    sources = source_preserved(bitbucket, excel, mattermost, clickup)
    destination, batch, link, summary, receipt = check_comment(clickup, attempt)

    g.add("B1.approved_build", 15, approved, "New retry group on approved build #482")
    g.add("B2.one_retry_group", 15, group, "Exactly one successful validation retry group")
    g.add("B3.new_attempt", 15, attempt, "Linked attempt 2 completed with its validation receipt")
    g.add("B4.preserve_attempts", 8, steps, "Original failure and other steps preserved")
    g.add("B5.preserve_other_builds", 8, builds, "Other runs preserved and no new build")
    g.add("B6.preserve_sources", 5, approved and sources, "Protected source and task records preserved")
    g.add("C1.comment_destination", 6, destination, "One standalone comment on rv-73mqd")
    g.add("C2.batch", 3, batch, "Live batch HBL-7116-Q")
    g.add("C3.attempt_link", 3, link, "Link to the actual validation attempt 2")
    g.add("C4.attempt_summary", 2, summary, "Step name, attempt number and successful outcome")
    g.add("C5.actual_receipt", 20, receipt, "New validation receipt quoted in the comment")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
