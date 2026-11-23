"""Merge trusted, append-only channel announcements in Slack desktop tasks."""

from collections import defaultdict
import math
import re


CHANNEL_PATH = re.compile(r"messages\.([A-Za-z0-9_-]+)\Z")
MESSAGE_FIELDS = frozenset({"messageId", "senderId", "timestamp", "content"})


def live_targets(triggers, sites):
    """Return channel → reserved IDs for a supported Slack-only trigger world."""
    if "slack" not in sites or not isinstance(triggers, list) or not triggers:
        raise ValueError("Slack live events require a Slack site and nonempty trigger list")
    channels = defaultdict(set)
    trigger_ids = set()
    message_ids = set()
    for trigger in triggers:
        if not isinstance(trigger, dict):
            raise ValueError("Each Slack live trigger must be an object")
        when, targets, delay = trigger.get("when"), trigger.get("then"), trigger.get("delay_s", 15)
        trigger_id = trigger.get("id")
        if (not isinstance(trigger_id, str) or not trigger_id or trigger_id in trigger_ids
                or not isinstance(when, dict) or when.get("site") not in sites
                or not isinstance(when.get("path"), str) or not when["path"].strip(".")
                or not isinstance(when.get("match"), dict) or not when["match"]
                or not isinstance(targets, list) or not targets
                or type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0):
            raise ValueError(f"Invalid Slack live trigger {trigger_id!r}")
        trigger_ids.add(trigger_id)
        for target in targets:
            if not isinstance(target, dict) or not isinstance(target.get("path"), str):
                raise ValueError(f"Invalid Slack live target for {trigger_id!r}")
            channel = CHANNEL_PATH.fullmatch(target["path"])
            message = target.get("append")
            if (target.get("site") != "slack" or not channel or not isinstance(message, dict)
                    or message.get("threadId")
                    or not all(isinstance(message.get(key), str) and message[key] for key in MESSAGE_FIELDS)
                    or message["messageId"] in message_ids):
                raise ValueError(f"Trigger {trigger_id!r} must append a uniquely identified Slack channel message")
            message_id = message["messageId"]
            message_ids.add(message_id)
            channels[channel[1]].add(message_id)
    return dict(channels)


def channel_events(state, targets):
    """Extract only announcements the trusted server has already delivered."""
    messages = state.get("messages", {})
    return {key: [row for row in messages.get(key, []) if row.get("messageId") in ids]
            for key, ids in targets.items()}


def preserve_channel_events(incoming, current, targets):
    """Preserve original identity/body across whole-state writes by old browser tabs."""
    if (not isinstance(incoming, dict) or not isinstance(incoming.get("messages"), dict)
            or any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                   for rows in incoming["messages"].values())):
        raise ValueError("Expected a complete Slack message map")
    reserved = set().union(*targets.values())
    posted = incoming["messages"]
    messages = {channel: [row for row in rows if row.get("messageId") not in reserved]
                for channel, rows in posted.items()}
    for channel, events in channel_events(current, targets).items():
        if not events:
            continue
        client_events = {row.get("messageId"): row for row in posted.get(channel, [])
                         if row.get("messageId") in targets[channel]}
        rows = messages.setdefault(channel, [])
        for event in events:
            client = client_events.get(event["messageId"])
            if (client and isinstance(client.get("reactions"), list)
                    and all(client.get(key) == event[key] for key in MESSAGE_FIELDS)):
                event = {**event, "reactions": client["reactions"]}
            rows.append(event)
        # The Slack mock renders rows in supplied order; event/user timestamps use ISO UTC.
        rows.sort(key=lambda row: row.get("timestamp") or "")
    return {**incoming, "messages": messages}
