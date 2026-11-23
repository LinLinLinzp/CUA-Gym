"""Replay the Tide Marks release through the desktop UI."""

from computer import act, click, key, type_text, wait
from io import BytesIO
from PIL import Image


CREDIT = "Tide Marks © Elin Vale / South Quay Print Collective"
TITLE = "Tide Marks: An Indoor Print Exhibition"
WORKING = "/workspace/input/tide-marks-working.psd"


def double_click(x, y):
    act("double_click", coordinate=[x, y])


def scroll(x, y, direction, amount):
    act("scroll", coordinate=[x, y], scroll_direction=direction, scroll_amount=amount)


def drag(x, y, end_x, end_y):
    act("left_click_drag", start_coordinate=[x, y], coordinate=[end_x, end_y])


def checkpoint(name):
    with open(f"/logs/agent/{name}.png", "wb") as output:
        output.write(act("screenshot"))


def export(tag, extension, replace=False):
    key("Ctrl+Shift+e")
    wait(1.2)
    key("Ctrl+a")
    type_text(f"/workspace/output/tide-marks-{tag}.{extension}")
    key("Return")
    wait(3)
    if replace:
        click(836, 484)  # GIMP's centered overwrite-confirmation dialog.
        wait(3)
    if extension == "png":
        click(1222, 774)
        wait(2)


def layer_rows(thumbnail_x, top):
    """Locate visible layer thumbnails from the desktop screenshot only."""
    picture = Image.open(BytesIO(act("screenshot"))).convert("RGB")
    background = picture.getpixel((thumbnail_x - 25, top + 5))
    ranges = []
    start = None
    for y in range(top, 780):
        thumbnail = any(max(abs(a-b) for a,b in zip(picture.getpixel((x,y)), background)) > 12
                        for x in (thumbnail_x-1, thumbnail_x, thumbnail_x+1))
        if thumbnail and start is None:
            start = y
        if not thumbnail and start is not None:
            if y-start >= 8:
                ranges.append((start+y-1)//2)
            start = None
    if start is not None and 780-start >= 8:
        ranges.append((start+779)//2)
    return ranges


def browser_in_front():
    picture = Image.open(BytesIO(act("screenshot"))).convert("RGB")
    return picture.getpixel((1080, 24)) == (211, 227, 253)


def show_browser(close_file_manager=False):
    """Switch from GIMP back to Chromium through the window manager."""
    key("Alt+Tab")
    wait(0.6)
    if close_file_manager and not browser_in_front():
        key("Alt+F4")
        wait(0.6)
    if not browser_in_front():
        key("Alt+Tab")
        wait(0.6)
    if not browser_in_front():
        checkpoint("browser-handoff")
        raise RuntimeError("Chromium did not come to the foreground")

def approved_plate():
    scroll(1180, 650, "up", 20)
    rows = layer_rows(1118, 540)
    if len(rows) < 5:
        raise RuntimeError("The seven-layer source stack is not visible")
    click(1039, rows[0])  # Hide Proof frames.
    click(1039, rows[3])  # Show Plate A.
    click(1039, rows[4])  # Hide Plate B.


def matching_posts():
    click(1035, 292)
    type_text("Tide Marks")
    click(1194, 292)
    wait(0.6)


def prepare_artwork():
    key("Super+e")
    wait(2)
    key("Ctrl+l")
    type_text(WORKING)
    key("Return")
    wait(8)
    checkpoint("working-psd-open")
    key("Shift+c")
    approved_plate()
    drag(503, 326, 903, 536)
    key("Return")
    export("feature", "psd")
    export("feature", "png")
    checkpoint("gimp-feature")
    key("Ctrl+o")
    wait(0.5)
    key("Ctrl+l")
    type_text(WORKING)
    key("Return")
    wait(3)
    approved_plate()
    drag(591, 258, 858, 658)
    click(245, 530)
    key("Ctrl+a")
    type_text("800")
    key("Tab")
    click(731, 450)
    export("pin", "psd")
    export("pin", "png")
    checkpoint("gimp-portrait")
    show_browser(close_file_manager=True)


def open_release_task():
    click(625, 20)
    wait(1)
    click(113, 410)
    wait(0.65)
    click(487, 477)
    wait(0.6)
    checkpoint("asana-release-authority")
    click(909, 596)
    view_downloaded_proofs("curator-release-proof-17.png")


def view_downloaded_proofs(filename, previous=None):
    key("Super+e")
    wait(1.2)
    key("Ctrl+l")
    type_text(f"/workspace/downloads/{filename}")
    key("Return")
    wait(1.2)
    checkpoint(filename.removesuffix(".png"))
    if previous:
        click(583, 65)  # Ristretto's Previous Image button.
        wait(0.5)
        checkpoint(previous.removesuffix(".png"))
    key("Alt+F4")
    wait(0.5)
    key("Alt+F4")
    wait(0.5)


def choose_upload(tag):
    click(76, 155)  # Workspace bookmark in the native Chromium file chooser.
    wait(0.4)
    double_click(208, 148)  # Output folder below downloads and input.
    wait(0.6)
    click(260, 103 if tag == "feature" else 125)
    click(1230, 778)
    wait(1.5)


def publish_article(revised=False):
    key("Ctrl+1")
    key("Ctrl+l")
    type_text("https://wordpress.com/wp-admin/")
    key("Return")
    wait(1)
    click(74, 326)
    wait(0.65)
    click(530, 193)
    wait(0.55)
    click(758, 353)
    wait(1)
    checkpoint("wordpress-file-chooser")
    choose_upload("feature")
    checkpoint("wordpress-uploaded-media")
    click(336, 536)
    wait(0.45)
    click(881, 478)
    type_text("Ochre sun over dark quay silhouettes and curved tidal lines, with Tide Marks lettering.")
    click(878, 555)
    type_text(CREDIT)
    click(1132, 710)
    wait(0.45)
    click(1058, 713)
    click(65, 280)
    wait(0.5)
    matching_posts()
    click(478, 390)
    wait(0.6)
    if not revised:
        click(346, 614)
        key("Ctrl+a")
        type_text(CREDIT)
    scroll(1168, 658, "down", 13)
    wait(0.5)
    click(1094, 559)
    wait(0.55)
    click(645 if revised else 456, 437)
    click(1054, 631)
    click(1176, 116)
    wait(1)
    click(65, 114)
    wait(0.7)
    matching_posts()
    click(1202, 390)
    wait(0.4)
    click(1121, 507)
    wait(0.8)
    checkpoint("wordpress-visitor-article")
    if not revised:
        key("Ctrl+l")
        key("Ctrl+c")


def publish_pin():
    click(372, 19)
    wait(0.8)
    click(278, 114)
    wait(0.7)
    click(665, 628)
    key("Ctrl+v")
    click(651, 320)
    type_text(TITLE)
    click(652, 488)
    type_text("Visit South Quay Gallery’s North Hall for a free indoor exhibition of waterfront print studies. "
              + CREDIT + ".")
    click(354, 515)
    wait(0.85)
    choose_upload("pin")
    click(848, 728)
    wait(0.35)
    click(689, 641)
    wait(0.3)
    click(1002, 223)
    wait(1.4)
    click(1119, 445)
    wait(0.65)
    checkpoint("pinterest-published-pin")
    click(680, 175)
    wait(0.4)


def submit_review(revised=False):
    click(625, 20)
    wait(0.5)
    scroll(1266, 706, "down", 16)
    wait(0.5)
    click(953, 755)
    type_text("Please recheck the WordPress credit. The accepted Pin image is unchanged. Pin: "
              if revised else "Release verified. Pin: ")
    key("Ctrl+v")
    type_text(" | Article: ")
    click(148, 20)
    key("Ctrl+l")
    key("Ctrl+c")
    click(625, 20)
    click(1030, 760)
    key("End")
    key("Ctrl+v")
    click(1203, 759)
    wait(3)
    if not revised:
        click(909, 341)
        click(909, 395)
        view_downloaded_proofs("hx01-review-1-wordpress.png", "hx01-review-1-pinterest.png")
    scroll(1266, 706, "down", 16)
    wait(0.5)
    checkpoint("curator-final-placement-acceptance" if revised else "curator-placement-rejection")


def complete_task():
    scroll(1266, 486, "up", 25)
    wait(0.45)
    click(814, 125)
    wait(0.55)
    checkpoint("asana-completed")


def repair_feature():
    key("Alt+Tab")
    wait(0.6)
    click(420, 107)  # The existing landscape document is the first GIMP tab.
    scroll(1180, 650, "up", 20)
    rows = layer_rows(1118, 540)
    if len(rows) < 2:
        raise RuntimeError("The reproduction credit layer is not visible")
    click(1150, rows[1])
    key("Ctrl+Shift+o")
    wait(0.7)
    key("Tab")  # Native dialog starts on Presets; Tab reaches X.
    key("Ctrl+a")
    type_text("-400")
    key("Tab")
    key("Ctrl+a")
    type_text("-480")
    key("Tab")
    click(1230, 779)
    wait(1.2)
    checkpoint("feature-lettering-repositioned")
    export("feature", "psd", replace=True)
    export("feature", "png", replace=True)
    show_browser()


if __name__ == "__main__":
    open_release_task()
    prepare_artwork()
    publish_article()
    publish_pin()
    submit_review()
    repair_feature()
    publish_article(revised=True)
    click(372, 19)
    wait(0.6)
    click(680, 175)
    wait(0.4)
    submit_review(revised=True)
    complete_task()

