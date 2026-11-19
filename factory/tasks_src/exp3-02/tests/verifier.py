"""Verify the After the Last Tram release reconciliation."""

import re
from datetime import datetime, timedelta, timezone

from cuaverify import InfraError, load_site, plain, run

TASK_ID = "cua-hard/after-the-last-tram"
VERSION = "0.1.2"

# The signed Word sheet (doc-signed) names these exact articles and moves the
# interview from 18:30 CET to 19:30 CET (18:30 UTC) on 19 November 2026.
TITLES = {
    "post-map": "a map of the last stops",
    "post-night": "the night inspector",
    "post-depot": "inside the bell street depot",
}
EMBARGO = datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc)
OLD_SLOT = EMBARGO - timedelta(hours=1)
# The task clock starts the immediate-publication window, which ends at embargo.
START = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)
# The seeded Editorial Desk handoff delegates closeout to Inez.
ROOT, CHANNEL, ACTOR = "post-tram-release", "ch-editorial", "usr-inez"
COPY_FIELDS = (
    "title", "subtitle", "bodyHtml", "slug", "authorId", "thumbnailPath",
    "tags", "commentPolicy",
)
DELIVERY_FIELDS = ("scheduledAt", "publishedAt", "deliveryAt")
COLLECTIONS = {
    "substack": "users posts subscribers compSubscriptions comments events",
    "microsoft_word_for_the_web": (
        "users documents shareGrants templates documentActivity commentThreads "
        "trackedChanges shareInvitations shareLinks"
    ),
    "mattermost": (
        "teams users teamMembers channels channelMembers posts threads "
        "sidebarCategories threadMemberships pins files drafts reactions "
        "savedPosts preferences activityLog"
    ),
}


def indexed(records, label):
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise InfraError(f"{label} contains a non-object record")
        key = record.get("id")
        if not isinstance(key, str) or not key or key in result:
            raise InfraError(f"{label} contains a missing or duplicate ID")
        result[key] = record
    return result


def read_states(site):
    try:
        before, after = load_site(site)
    except UnicodeError as exc:
        raise InfraError(f"{site} state is not valid UTF-8") from exc
    for state in (before, after):
        if not isinstance(state, dict):
            raise InfraError(f"{site} state is not an object")
        for key in COLLECTIONS[site].split():
            if not isinstance(state.get(key), list):
                raise InfraError(f"{site}.{key} is missing or is not an array")
            if not all(isinstance(record, dict) for record in state[key]):
                raise InfraError(f"{site}.{key} contains a non-object record")
    for key, value in before.items():
        if key not in after or (value is not None and type(after[key]) is not type(value)):
            raise InfraError(f"{site}.{key} is missing or has an invalid type")
    return before, after


def instant(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is not None:
            return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError, OverflowError):
        pass
    raise InfraError(f"Invalid persisted timestamp: {value!r}")


def validate_substack(posts):
    for record in posts.values():
        if record.get("status") not in ("draft", "scheduled", "published", "deleted"):
            raise InfraError(f"Invalid status on {record['id']}")
        if record.get("audience") not in ("everyone", "free", "paid", "founding"):
            raise InfraError(f"Invalid audience on {record['id']}")
        if type(record.get("sendByEmailAndApp")) is not bool:
            raise InfraError(f"Invalid delivery setting on {record['id']}")
        for field in DELIVERY_FIELDS:
            instant(record.get(field))


def without(record, *fields):
    return {key: value for key, value in record.items() if key not in fields}


def has(pattern, text):
    return re.search(pattern, text) is not None


def report_sections(message):
    # Accept either title placement on an individual line and title-first prose.
    titles = re.compile(r"\b(?:" + "|".join(TITLES.values()) + r")\b")
    sections = {title: [] for title in TITLES.values()}
    active = None
    for line in re.split(r"\n|<br\s*/?>|</p>", message, flags=re.I):
        normalized = re.sub(r"[*_`~]", "", plain(line)).replace("’", "'")
        matches = list(titles.finditer(normalized))
        if not matches:
            if active:
                sections[active].append(normalized)
            continue
        if len(matches) == 1:
            sections[matches[0].group()].append(normalized[:matches[0].start()])
        for index, match in enumerate(matches):
            active = match.group()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            sections[active].append(normalized[match.end():end])
    return {title: " ".join(parts) for title, parts in sections.items()}


EMAIL = r"\be[ -]?mail(?:s|ed)?\b"
APP = r"\b(?:substack[ -])?apps?\b"
LIVE = r"\b(?:published|live|online|available on the (?:public )?web)\b"
UNLIVE = (
    r"\b(?:not|never|isn't|hasn't|has not)\s+(?:yet\s+)?(?:been\s+)?"
    r"(?:gone live|live|published|online|on the web)\b|\bunpublished\b|"
    r"\b(?:has|have) yet to (?:appear on the (?:public )?web|go live|be published)\b"
)
SEND = r"\b(?:sent|delivered|distributed|e[ -]?mailed|went out|has gone out)\b"
NEGATIVE_DELIVERY = (
    r"\b(?:not|never|no|none|neither|without|wasn't|weren't|hasn't|haven't|didn't|disabled|off)\b"
)
FUTURE = (
    r"\b(?:will|queued|pending|scheduled|at (?:the scheduled|that) time|"
    r"to (?:go out|be sent|be delivered)|"
    r"(?:at|on|for|upon|with) (?:the )?(?:release|publication|launch|embargo lift)|"
    r"when (?:it |the post )?(?:goes live|publishes|is published))\b"
)


def delivery_clauses(section):
    return [
        clause for clause in re.split(
            r"[;!?]|\.(?=\s|$)|\b(?:but|however)\b|\band\s+(?=no\b)", section
        )
        if has(EMAIL, clause) or has(APP, clause)
    ]


def covers_channels(clauses):
    combined = " ".join(clauses)
    return has(EMAIL, combined) and has(APP, combined)


def correct_slot(text):
    date = (
        r"\b(?:2026[-/]11[-/]19|11[-/]19(?:[-/]2026)?|19/11(?:/2026)?|"
        r"(?:19(?:th)?\s+nov(?:ember)?\.?|nov(?:ember)?\.?\s+19(?:th)?)(?:,?\s+2026)?)"
    )
    dates = list(re.finditer(date + r"(?!\d)", text))
    if not dates or has(r"\b(?:202[0-57-9]|20[013-9]\d)\b", text):
        return False
    clock = (
        r"(?<!\d)(\d{1,2}):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?"
        r"\s*([ap]\.?m\.?)?\s*\(?\s*"
        r"(utc\s*[+-]\s*\d{1,2}(?::?\d{2})?|gmt\s*[+-]\s*\d{1,2}(?::?\d{2})?|"
        r"[+-]\d{2}(?::?\d{2})?|central european time|cet|utc|gmt|z|est|pst)"
        r"(?![\w:+-])"
    )
    offsets = {"central european time": 60, "cet": 60, "utc": 0, "gmt": 0,
               "z": 0, "est": -300, "pst": -480}
    for match in re.finditer(clock, text):
        hour, minute, second, fraction, meridiem, zone = match.groups()
        hour = int(hour)
        if meridiem:
            if not 1 <= hour <= 12:
                continue
            hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
        if hour > 23 or int(second or 0) or int(fraction or 0):
            continue
        offset = offsets.get(zone)
        if offset is None:
            raw = re.sub(r"utc|gmt|\s|:", "", zone)
            sign, digits = raw[0], raw[1:]
            offset = int(digits[:-2] or digits) * 60 + (int(digits[-2:]) if len(digits) > 2 else 0)
            if sign == "-":
                offset = -offset
        if hour * 60 + int(minute) - offset == 18 * 60 + 30:
            return True
    return False


def web_report(section):
    clauses = delivery_clauses(section)
    negative = [clause for clause in clauses if has(NEGATIVE_DELIVERY, clause)]
    return (
        has(LIVE + r"|\bon the (?:public )?web\b", section) and not has(UNLIVE, section)
        and (covers_channels(negative) or (
            has(r"\bweb[ -]only\b|\b(?:on the )?web only\b", section)
            and covers_channels(clauses)
        ))
        and not any(has(SEND, clause) and clause not in negative for clause in clauses)
    )


def schedule_report(section):
    clauses = delivery_clauses(section)
    planned = [
        clause for clause in clauses
        if has(FUTURE, clause) and not has(
            r"\b(?:off|disabled|not (?:queued|scheduled|enabled)|won't)\b", clause
        )
    ]
    # "Scheduled to go live" and "scheduled to be published" describe
    # the web slot. They do not assert a second, already-live web state.
    web_status = re.sub(
        r"\b(?:will|to|when (?:it|the post))\s+"
        r"(?:be\s+|go(?:es)?\s+)?(?:live|published|online)\b",
        "", section
    )
    return (
        has(r"\b(?:scheduled|queued|slated|(?:set to|will) (?:publish|go live|be published))\b", section)
        and not has(LIVE, re.sub(UNLIVE, "", web_status))
        and correct_slot(section)
        and (
            covers_channels(planned)
            or covers_channels([
                clause for clause in clauses
                if has(r"\b(?:enabled|on|ready)\b", re.sub(UNLIVE, "", clause))
                and not has(NEGATIVE_DELIVERY, re.sub(UNLIVE, "", clause))
                and not has(SEND, clause)
            ])
        )
        and not any(has(SEND, clause) and clause not in planned
                    and not has(NEGATIVE_DELIVERY, clause) for clause in clauses)
    )


def sent_report(section):
    clauses = delivery_clauses(section)
    sent = [clause for clause in clauses if has(SEND, clause)
            and not has(NEGATIVE_DELIVERY, clause)
            and not has(r"\b(?:will|queued|pending|scheduled)\b", clause)]
    return (
        not has(r"^\W*(?:the\s+)?layout[ -]proof\b", section)
        and has(LIVE, section) and not has(UNLIVE, section)
        and covers_channels(sent)
        and has(r"\b(?:paid(?:-tier)?\s+(?:subscribers|members|readers)|paying\s+(?:subscribers|members|readers)|(?:to|for)\s+(?:the\s+)?paid(?:\s+only)?)\b", section)
        and not has(r"\b(?:to|for)\s+(?:everyone|all subscribers|free subscribers)\b", section)
    )


def protected_substack(before, after, old_posts, posts):
    return (
        without(before, "posts", "events") == without(after, "posts", "events")
        and old_posts.keys() == posts.keys()
        and all(
            all(old.get(field) == posts[key].get(field) for field in COPY_FIELDS)
            if key in TITLES else old == posts[key]
            for key, old in old_posts.items()
        )
    )


def protected_mattermost(before, after, old_posts, posts, reply):
    if not all(posts.get(key) == row for key, row in old_posts.items()):
        return False
    if posts.keys() - old_posts.keys() != {reply["id"]}:
        return False
    derived = ("posts", "threads", "threadMemberships", "channelMembers",
               "activityLog", "drafts")
    if without(before, *derived) != without(after, *derived):
        return False

    def other_threads(state):
        return {key: record for key, record in indexed(state["threads"], "threads").items()
                if record.get("rootPostId") != ROOT}

    def channel_members(state):
        return {key: without(record, "lastViewedAt", "lastReadPostId", "updatedAt")
                for key, record in indexed(state["channelMembers"], "channelMembers").items()}

    def other_memberships(state):
        active_threads = {row["id"] for row in state["threads"] if row.get("rootPostId") == ROOT}
        return {key: without(record, "lastReadAt", "lastReadPostId", "updatedAt")
                for key, record in indexed(state["threadMemberships"], "threadMemberships").items()
                if record.get("threadId") not in active_threads}

    def other_drafts(state):
        return {key: record for key, record in indexed(state["drafts"], "drafts").items()
                if (record.get("userId"), record.get("channelId"), record.get("rootId"))
                != (ACTOR, CHANNEL, ROOT)}

    return all(project(before) == project(after)
               for project in (other_threads, channel_members, other_memberships, other_drafts))


def evaluate(g):
    sub_before, sub_after = read_states("substack")
    word_before, word_after = read_states("microsoft_word_for_the_web")
    mm_before, mm_after = read_states("mattermost")
    old_posts = indexed(sub_before["posts"], "initial Substack posts")
    posts = indexed(sub_after["posts"], "current Substack posts")
    old_messages = indexed(mm_before["posts"], "initial Mattermost posts")
    messages = indexed(mm_after["posts"], "current Mattermost posts")
    validate_substack(old_posts)
    validate_substack(posts)
    if not TITLES.keys() <= old_posts.keys() or ROOT not in old_messages:
        raise InfraError("Initial state lacks the approved articles or handoff")
    for row in messages.values():
        if not isinstance(row.get("message"), str) or not all(
            isinstance(row.get(key), str) for key in ("userId", "channelId")
        ):
            raise InfraError(f"Invalid Mattermost post {row['id']}")
    original_thread = {key: row for key, row in old_messages.items()
                       if key == ROOT or row.get("rootId") == ROOT}
    if len(original_thread) != 3:
        raise InfraError("Initial state lacks the three handoff messages")

    before_events = indexed(sub_before["events"], "initial Substack events")
    after_events = indexed(sub_after["events"], "current Substack events")
    release_actions = {"post.published", "post.scheduled", "post.unscheduled"}
    changes = [
        event for key, event in after_events.items()
        if key not in before_events and event.get("type") in release_actions
    ]
    release_times = [
        instant(event.get("createdAt")) for event in changes if event.get("entityId") in TITLES
    ]
    added = [row for key, row in messages.items() if key not in old_messages]
    reply = added[0] if len(added) == 1 else {}
    reply_at = instant(reply.get("createdAt"))
    thread = (
        (reply.get("userId"), reply.get("channelId"), reply.get("rootId"))
        == (ACTOR, CHANNEL, ROOT)
        and reply.get("deletedAt") is None
        and bool(reply["message"].strip())
        and reply_at is not None
        and all(time is not None and time <= reply_at for time in release_times)
        and all(key in messages and messages[key].get("deletedAt") is None
                for key in original_thread)
    )
    sections = report_sections(reply["message"] if thread else "")
    map_post = posts.get("post-map", {})
    night = posts.get("post-night", {})
    depot = posts.get("post-depot", {})
    map_ok = (
        map_post.get("status") == "published" and map_post.get("audience") == "everyone"
        and map_post.get("sendByEmailAndApp") is False and map_post.get("deliveryAt") is None
    )
    scheduled = (
        old_posts["post-night"]["status"] == night.get("status") == "scheduled"
        and instant(old_posts["post-night"].get("scheduledAt")) == OLD_SLOT
        and instant(night.get("scheduledAt")) == EMBARGO
        and any(event.get("entityId") == "post-night" and event["type"] == "post.scheduled"
                and instant(event.get("details", {}).get("scheduledAt")) == EMBARGO for event in changes)
        and not any(event.get("entityId") == "post-night" and event["type"] == "post.published"
                    for event in changes)
    )
    queued = (
        scheduled and night.get("audience") == "everyone"
        and night.get("sendByEmailAndApp") is True
        and night.get("publishedAt") is None and night.get("deliveryAt") is None
    )
    published_at = instant(depot.get("publishedAt"))
    publication = next((
        event.get("details", {}) for event in changes
        if event.get("entityId") == "post-depot" and event["type"] == "post.published"
        and instant(event.get("details", {}).get("publishedAt")) == published_at
    ), None)
    live = (
        old_posts["post-depot"]["status"] == "draft" and depot.get("status") == "published"
        and depot.get("scheduledAt") is None and published_at is not None
        and START <= published_at < EMBARGO
        and publication is not None
    )
    paid = live and depot.get("audience") == publication.get("audience") == "paid"
    delivered = (
        live and depot.get("sendByEmailAndApp") is True
        and instant(depot.get("deliveryAt")) == published_at
        and instant(publication.get("deliveryAt")) == published_at
    )
    reported_web = thread and map_ok and web_report(sections[TITLES["post-map"]])
    reported_slot = thread and queued and schedule_report(sections[TITLES["post-night"]])
    reported_sent = thread and paid and delivered and sent_report(sections[TITLES["post-depot"]])
    protected = (
        thread and (scheduled or live)
        and not any(event["type"] == "post.published" and event.get("entityId") != "post-depot"
                    for event in changes)
        and protected_substack(sub_before, sub_after, old_posts, posts)
        and without(word_before, "documentActivity") == without(word_after, "documentActivity")
        and protected_mattermost(mm_before, mm_after, old_messages, messages, reply)
    )

    g.add("S1.web_only", 10, reported_web and map_post == old_posts["post-map"],
          "Original public web-only record preserved and reported")
    g.add("S2.embargo_slot", 15, scheduled, "Interview rescheduled to 19 Nov 18:30 UTC")
    g.add("S3.embargo_queued", 8, queued, "Public email and app delivery queued for embargo")
    g.add("S4.approved_live", 14, live, "Original photo essay published in the release window")
    g.add("S5.approved_audience", 7, paid, "Published photo essay restricted to paid subscribers")
    g.add("S6.approved_delivery", 12, delivered, "Photo essay delivered at publication")
    g.add("M1.thread_update", 8, thread, "One new reply by Inez in the original handoff after release changes")
    g.add("M2.report_web", 5, reported_web, "Reply accurately reports the web-only map")
    g.add("M3.report_schedule", 5, reported_slot, "Reply reports the embargo time and queued delivery")
    g.add("M4.report_sent", 6, reported_sent, "Reply confirms delivery of the formal essay to paid subscribers")
    g.add("P1.protect_records", 10, protected, "Article copy and unrelated editorial records preserved")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
