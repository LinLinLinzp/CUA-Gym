#!/usr/bin/env python3
"""Reference handoff performed only with the desktop computer MCP.

The reference uses the same browser tabs, native selects and comment editor
available to an agent. The reference saves key full-desktop screenshots as evidence.
"""
from pathlib import Path
from computer import act, click, key, type_text, wait


COMMENT = (
    "K17 → B2: powered bay and 0.90 m inbound clearance. "
    "K24 → B3: 1.20 m inbound clearance. "
    "K31: Hold pending release approval."
)


def shot(name):
    evidence = Path("/logs/agent/desktop")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / name).write_bytes(act("screenshot"))


def navigate(url):
    key("Alt+d")
    wait(0.2)
    type_text(url)
    key("Return")
    wait(1.5)


def choose(x, y, index):
    """Open the native select, then choose a numbered visible option."""
    click(x, y)
    wait(0.25)
    key("space")
    wait(0.15)
    key("Home")
    key("Down", repeat=index)
    key("Return")
    wait(0.4)


def main():
    key("Ctrl+1")
    wait(0.5)
    click(650, 312)
    wait(0.6)
    shot("01-gmail-approved-thread.png")
    act("scroll", coordinate=[1000, 600], scroll_direction="down", scroll_amount=5)
    shot("02-gmail-approved-attachment.png")
    click(434, 545)
    wait(0.8)
    key("Super+e")
    wait(0.8)
    key("Ctrl+l")
    type_text("/workspace/downloads")
    key("Return")
    wait(0.4)
    act("double_click", coordinate=[226, 130])
    wait(1.5)
    shot("02-approved-floor-plan.png")
    key("Alt+F4")
    wait(0.3)
    key("Alt+F4")
    wait(0.3)

    key("Ctrl+3")
    navigate("https://3.basecamp.com/projects/project-riverside/todos/items/todo-riverside-load-in")
    shot("03-installation-checklist.png")

    key("Ctrl+2")
    wait(0.6)
    # Show the Bay and Disposition columns at the right edge of the load list.
    act("scroll", coordinate=[900, 300], scroll_direction="right", scroll_amount=20)
    wait(0.3)
    # Native selects include a blank first option. Bays are B1 through B5;
    # dispositions are Needs assignment, Assigned, Hold, Locked.
    choose(1000, 279, 2)
    choose(1160, 279, 2)
    choose(1000, 312, 3)
    choose(1160, 312, 2)
    choose(1160, 345, 3)
    shot("04-airtable-assignments.png")

    key("Ctrl+3")
    wait(0.4)
    click(1060, 580)
    key("Ctrl+End")
    wait(0.3)
    click(470, 635)
    type_text(COMMENT)
    click(339, 734)
    wait(1.2)
    shot("05-basecamp-handoff.png")


if __name__ == "__main__":
    main()
