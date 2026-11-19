"""Render the two deterministic floor plans for the Riverside venue email."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).parent
INK, MUTED, BLUE, TEAL = "#203247", "#52677b", "#325771", "#087b75"
PAPER, WALL, LIGHT = "#f9faf7", "#607383", "#e8f0f1"


def art(revision):
    img = Image.new("RGB", (1320, 860), PAPER)
    d = ImageDraw.Draw(img)
    fonts = {n: ImageFont.load_default(size=n) for n in (16, 19, 22, 27, 37)}

    def label(point, text, size=22, fill=INK, anchor=None):
        d.text(point, text, font=fonts[size], fill=fill, anchor=anchor)

    def arrow(x, start, end, color=TEAL):
        d.line((x, start, x, end), fill=color, width=6)
        inside = end - 15 if end > start else end + 15
        d.polygon(((x, end), (x - 11, inside), (x + 11, inside)), fill=color)

    def outlet(x, y):
        d.ellipse((x - 16, y - 16, x + 16, y + 16), outline=TEAL, width=3, fill="white")
        for delta in (-5, 5):
            d.line((x + delta, y - 6, x + delta, y + 3), fill=TEAL, width=3)
        d.ellipse((x - 2, y + 6, x + 2, y + 10), fill=TEAL)

    d.rectangle((0, 0, 1319, 14), fill=TEAL)
    label((52, 39), "RIVERSIDE HALL", 19, TEAL)
    label((52, 70), "Showcase load-in plan", 37)
    label((54, 120), "Ground floor  /  staging and north receiving", 19, MUTED)
    d.rounded_rectangle((1099, 49, 1262, 122), 8, fill=LIGHT, outline=WALL, width=2)
    label((1180, 68), f"REV {revision}", 27, BLUE, "mt")
    label((1180, 103), f"NOV {18 if revision == 'C' else 16}, 2026", 16, MUTED, "mt")
    d.rectangle((50, 160, 1270, 661), fill="#fffefa", outline=INK, width=4)
    for x in range(65, 1270, 28):
        d.line((x, 167, x, 655), fill="#edf0ec")
    for y in range(174, 655, 28):
        d.line((57, y, 1264, y), fill="#edf0ec")

    d.rectangle((222, 430, 1240, 470), fill="#f5ead5", outline="#8f744c", width=2)
    for x in range(222, 1240, 15):
        d.line((x, 469, min(x + 29, 1240), max(431, 469 - max(0, 1240 - x))), fill="#be9d63", width=2)
    label((1219, 451), "VISITOR AISLE", 16, "#715a34", "rm")
    # A single receiving lane supplies the four branch doors.
    d.line((118, 550, 1120, 550), fill=BLUE, width=7)
    d.polygon(((1138, 550), (1118, 539), (1118, 561)), fill=BLUE)
    label((659, 591), "Back-of-house cart lane", 22, MUTED, "mt")
    d.rectangle((61, 179, 190, 232), fill=LIGHT, outline=WALL, width=2)
    label((126, 189), "NORTH", 19, INK, "mt")
    label((126, 212), "RECEIVING", 16, INK, "mt")
    arrow(118, 239, 550, BLUE)

    bays = [
        (240, 414, "B1", "1.25 m", True, True, 448 if revision == "C" else 365),
        (492, 666, "B2", "0.90 m", True, True, 365),
        (744, 918, "B3", "1.20 m" if revision == "C" else "0.95 m", False, True, 365),
        (996, 1170, "B4", "1.25 m", True, revision == "B", 365),
    ]
    for left, right, bay, width, powered, inbound, bottom in bays:
        middle = (left + right) // 2
        d.rectangle((left, 239, right, min(bottom, 429)), fill="#e5eef0")
        d.line((left, bottom, left, 239, right, 239, right, bottom), fill=INK, width=4)
        d.line((left, bottom, middle - 23, bottom), fill=INK, width=4)
        d.line((middle + 23, bottom, right, bottom), fill=INK, width=4)
        label((middle, 263), bay, 37, INK, "mt")
        if powered:
            outlet(middle, 326)
        for edge in (middle - 22, middle + 22):
            d.line((edge, bottom - 7, edge, bottom + 7), fill=WALL, width=3)
        # The tip is deliberately well clear of the aisle hatching.
        if inbound:
            arrow(middle, 534, bottom + 4)
        else:
            arrow(middle, bottom + 4, 534)
        label((middle + 31, bottom + 24), width, 19, INK, "lm")

    label((53, 707), "KEY", 19, TEAL)
    outlet(119, 756)
    label((149, 756), "Powered outlet", 19, INK, "lm")
    d.rectangle((350, 741, 403, 772), fill="#f5ead5", outline="#8f744c", width=2)
    for x in range(353, 398, 9):
        d.line((x, 769, min(x + 15, 399), 744), fill="#be9d63", width=2)
    label((419, 756), "Protected visitor aisle", 19, INK, "lm")
    arrow(737, 781, 731)
    label((762, 756), "Permitted cart direction", 19, INK, "lm")
    d.line((1052, 745, 1052, 771), fill=WALL, width=3)
    d.line((1089, 745, 1089, 771), fill=WALL, width=3)
    label((1106, 756), "Door clear width", 19, INK, "lm")
    d.line((52, 809, 1266, 809), fill="#c1ced1", width=2)
    label((53, 827), "Riverside Venue Operations  ·  loading desk drawing", 16, MUTED)
    label((1267, 827), "Diagrammatic plan  /  use dimension labels", 16, MUTED, "ra")
    img.save(HERE / f"riverside-floor-plan-rev-{revision.lower()}.png", optimize=True)


if __name__ == "__main__":
    for revision in ("B", "C"):
        art(revision)
