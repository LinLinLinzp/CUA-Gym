"""Reference desktop replay for the escalation review.

Only the computer endpoint is used. Literal answer data stays in /solution,
which Harbor mounts for the oracle, never in the desktop image.
Coordinates target the packaged 1280 x 800 desktop.
"""

import argparse

from computer import act, click, key, type_text, wait


ROWS = [
    (3141, "FLD-412", "ACC-1013", "solved"),
    (3157, "FLD-412", "ACC-1011", "hold"),
    (3183, "FLD-412", "ACC-1009", "solved"),
    (3220, "FLD-412", "ACC-1012", "open"),
    (3222, "FLD-412", "ACC-1001", "pending"),
    (3233, "FLD-412", "ACC-1001", "open"),
    (3166, "FLD-398", "ACC-1006", "solved"),
    (3177, "FLD-398", "ACC-1005", "hold"),
    (3186, "FLD-398", "ACC-1017", "solved"),
    (3200, "FLD-398", "ACC-1018", "open"),
    (3236, "FLD-398", "ACC-1004", "open"),
    (3204, "FLD-447", "ACC-1012", "solved"),
    (3208, "FLD-447", "ACC-1007", "open"),
    (3210, "FLD-447", "ACC-1011", "pending"),
    (3218, "FLD-447", "ACC-1020", "hold"),
    (3230, "FLD-447", "ACC-1008", "open"),
    (3241, "FLD-447", "ACC-1011", "new"),
]
ARR = {"FLD-412": 287000, "FLD-398": 144500, "FLD-447": 158400}


def navigate(tab, url):
    key(f"Ctrl+{tab}")
    key("Ctrl+l")
    type_text(url)
    key("Return")
    wait(0.8)


def comment_text(bug):
    tickets = sorted(row[0] for row in ROWS if row[1] == bug)
    return (
        "Escalation review: Zendesk tickets opened since September 1 and "
        "escalated on this bug: "
        + ", ".join(f"#{ticket}" for ticket in tickets)
        + f". {len(tickets)} tickets, 5 distinct accounts, combined ARR ${ARR[bug]:,}."
    )


def zendesk():
    for ticket, bug, _, _ in ROWS:
        if ticket in (3220, 3222):
            continue
        navigate(1, f"https://acme.zendesk.com/tickets/{ticket}")
        # Tags save immediately; submitting would needlessly touch status.
        click(173, 531 if ticket == 3177 else 562)
        type_text(bug.lower())
        key("Return")
        wait(0.3)


def jira():
    for bug in ARR:
        navigate(3, "https://acme.atlassian.net/search")
        click(566, 197)
        type_text(bug)
        wait(0.3)
        click(478, 366)
        wait(0.4)
        if ARR[bug] >= 150000:
            click(943, 580)
            key("Home")
            key("Return")
        # Scroll the modal's left column to the comments composer.
        act("scroll", scroll_direction="down", scroll_amount=6, coordinate=[650, 606])
        click(481, 550 if bug == "FLD-447" else 490)
        type_text(comment_text(bug))
        key("Tab")
        key("Return")
        wait(0.4)


def slack():
    navigate(2, "https://app.slack.com/channel/support-escalations")
    # Open the four-reply thread attached to Tomas's review request.
    key("Ctrl+f")
    type_text("4 replies")
    key("Escape")
    key("Return")
    wait(0.5)
    click(1024, 658)
    type_text(
        "Done. FLD-412: 6 tickets, 5 distinct accounts, $287,000 ARR; bumped to Highest. "
        "FLD-398: 5 tickets, 5 distinct accounts, $144,500 ARR; stays High. "
        "FLD-447: 6 tickets, 5 distinct accounts, $158,400 ARR; bumped to Highest. "
        "Tickets are tagged in Zendesk."
    )
    key("Return")
    wait(0.5)


def csv():
    key("Alt+Tab")
    # The packaged desktop starts a blank Calc document before Chromium.
    key("Ctrl+Home")
    type_text(
        "ticket_id\tjira_key\taccount_id\tstatus\n"
        + "\n".join("\t".join(map(str, row)) for row in sorted(ROWS))
    )
    wait(0.4)
    key("Return")  # Accept Calc's tab-separated paste dialog if shown.
    key("Ctrl+Shift+s")
    wait(0.5)
    click(395, 666)
    key("Ctrl+a")
    type_text("/workspace/output/escalation_review.csv")
    click(510, 695)
    key("t")  # Native file-type list: Text CSV.
    key("Return")
    click(1224, 667)
    wait(0.5)
    # Export Text File: choose an explicit comma field delimiter.
    click(452, 86)
    key("Ctrl+a")
    type_text(",")
    key("Return")
    wait(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("zendesk", "jira", "slack", "csv", "all"), default="all")
    args = parser.parse_args()
    for name, function in (("zendesk", zendesk), ("jira", jira), ("slack", slack), ("csv", csv)):
        if args.stage in (name, "all"):
            function()


if __name__ == "__main__":
    main()
