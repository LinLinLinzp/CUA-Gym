"""Maple House author replay using only native desktop input and screenshots."""
from pathlib import Path

from computer import act, click, key, type_text, wait

OUTPUT_NAME = "Maple-Reading-Room-Delivery.drawio"
OUTPUT_PATH = "/workspace/output/" + OUTPUT_NAME
DRIVER = (
    "Maple House Reading Room 103: enter South Gate, check in at Receiving, "
    "then use Service Hall and Freight Lift. Keep the crate upright."
)
NOTES = (
    "\n\nDelivery confirmed for WF-9400461 (long sideboard), Tuesday, Nov 24, noon–4 pm ET. "
    "Use South Gate, check in at Receiving, then take Service Hall and Freight Lift to Reading Room 103. "
    "Keep the crate upright. The installation crew is booked for Wednesday, Nov 25."
)
REPLY = (
    "The long sideboard freight is confirmed for Tuesday, Nov 24, noon–4 pm ET via South Gate. "
    "The editable " + OUTPUT_NAME
    + " is attached to Install long sideboard — Reading Room 103 in Asana / Maple House Fit-out."
)


def shot(name):
    folder = Path("/logs/agent/desktop")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.png").write_bytes(act("screenshot"))


def dbl(x, y):
    act("double_click", coordinate=[x, y])


def drag(x1, y1, x2, y2):
    act("left_click_drag", start_coordinate=[x1, y1], coordinate=[x2, y2])


def right(x, y):
    act("right_click", coordinate=[x, y])


def scroll(x, y, direction, count):
    act("scroll", coordinate=[x, y], scroll_direction=direction, scroll_amount=count)


def teams_sources():
    click(601, 20)
    wait(.5)
    shot("01-crew-and-facilities")
    scroll(810, 425, "up", 16)
    wait(.3)
    shot("02-original-sideboard-and-north-suggestion")


def reschedule():
    click(137, 20)
    wait(.35)
    shot("03-wayfair-deliveries")
    click(1144, 538)
    wait(.3)
    click(439, 613)
    wait(.35)
    shot("04-original-and-offered-windows")
    click(400, 532)
    click(502, 683)
    key("Ctrl+a")
    type_text(DRIVER)
    key("Tab")
    wait(.3)
    click(760, 735)
    wait(.35)
    shot("05-wayfair-review")
    click(801, 648)
    wait(.7)
    shot("06-wayfair-confirmed")


def verify_carrier():
    # Check the reload retains the booking, the superseded appointment and
    # the order's split shipment details through ordinary account pages.
    key("Ctrl+r")
    wait(1)
    shot("06a-persisted-carrier-window")
    scroll(827, 670, "down", 15)
    wait(.35)
    shot("06b-original-appointment-history")
    scroll(827, 670, "up", 20)
    wait(.35)
    click(1014, 541)
    wait(.45)
    shot("06c-sideboard-order-and-crate-variant")
    scroll(826, 650, "down", 9)
    wait(.35)
    shot("06d-separate-chair-shipment")
    key("Alt+Left")
    wait(.45)


def drawing():
    key("Alt+Tab")
    wait(.4)
    key("Ctrl+o")
    wait(.55)
    click(69, 153)
    wait(.25)
    dbl(209, 124)
    wait(.25)
    click(1232, 775)
    wait(1.4)
    shot("07-native-original-plan")
    # The formal environment mounts the drawing source read-only.
    key("Ctrl+Shift+s")
    wait(.6)
    key("Ctrl+a")
    type_text(OUTPUT_PATH)
    click(1232, 777)
    wait(1)
    click(1103, 184)
    click(1197, 152)

    # Change each connector's existing terminal. The first and third turns
    # autoroute outside the glazing once the old North waypoints are cleared.
    click(381, 405)
    drag(405, 357, 406, 523)
    wait(.2)
    right(381, 400)
    click(475, 677)
    click(545, 358)
    drag(512, 357, 511, 523)
    wait(.2)
    drag(577, 358, 577, 523)
    wait(.2)
    click(719, 390)
    drag(690, 357, 690, 523)
    wait(.2)
    right(718, 405)
    click(810, 676)
    click(775, 563)
    key("Ctrl+s")
    wait(1)
    shot("08-native-editable-south-route")
    click(405, 480)
    shot("08a-truck-to-south-gate-terminals")
    click(544, 523)
    shot("08b-south-gate-to-service-hall-terminals")
    click(745, 484)
    shot("08c-service-hall-to-freight-lift-terminals")
    click(775, 563)
    key("Alt+Tab")
    wait(.4)


def install_task():
    click(380, 20)
    wait(.5)
    click(442, 334)
    wait(.45)
    click(495, 476)
    wait(.35)
    shot("09-original-installation-task")
    click(1000, 300)
    click(1169, 299)
    wait(.25)
    click(963, 486)
    wait(.3)
    click(1032, 699)
    key("Ctrl+End")
    type_text(NOTES)
    key("Tab")
    wait(.5)
    click(1190, 299)
    wait(.55)
    click(64, 154)
    wait(.25)
    dbl(211, 147)
    wait(.25)
    click(327, 101)
    click(1230, 776)
    wait(1)
    shot("10-installation-task-attachment-and-notes")


def verify_install_task():
    # Reopen the task details and inspect the persisted date in the native
    # date control. The summary label applies the browser's time offset.
    scroll(1030, 468, "up", 18)
    wait(.35)
    click(1232, 122)
    click(495, 476)
    wait(.45)
    shot("10a-reopened-installation-task")
    click(1000, 300)
    shot("10b-persisted-installation-date-field")
    click(916, 535)
    wait(.65)
    shot("10c-download-from-original-task")


def teams_handoff():
    click(601, 20)
    wait(.35)
    scroll(810, 425, "up", 16)
    wait(.3)
    act("mouse_move", coordinate=[650, 324])
    wait(.25)
    click(1208, 282)
    wait(.3)
    click(981, 729)
    type_text(REPLY)
    shot("11-thread-handoff-draft")
    click(1243, 774)
    wait(.7)
    shot("12-thread-reply-sent")
    click(1254, 248)
    key("Ctrl+r")
    wait(.9)
    scroll(810, 425, "up", 16)
    wait(.4)
    shot("13-original-thread-persisted-reply-count")


def main():
    teams_sources()
    reschedule()
    verify_carrier()
    drawing()
    install_task()
    verify_install_task()
    teams_handoff()


if __name__ == "__main__":
    main()

