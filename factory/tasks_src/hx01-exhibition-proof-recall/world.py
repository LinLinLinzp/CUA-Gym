"""Deterministic exhibition release, layered artwork, and publishing fixtures."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from struct import pack
import json
import os
import math
import random
import shutil
import sys
from zlib import compress

from PIL import Image, ImageDraw, ImageFont, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url


DATE = "2026-11-19T13:00:00Z"
STAMP = "2026-11-19T14:20:00Z"
MILLIS = 1795098000000
WIDTH, HEIGHT = 1600, 1440
INPUT = "tide-marks-working.psd"
PROOF = "curator-release-proof-17.png"
PRELIM = "curator-layout-draft-16.png"
CREDIT = "Tide Marks © Elin Vale / South Quay Print Collective"
STALE_CREDIT = "Tide Marks © Mara Keene / South Quay Print Collective"
TITLE = "Tide Marks: An Indoor Print Exhibition"
ALT = "Teal tidal lines and a gold sun surround a dark, stepped quay in an illustrated print."
PROJECT = "sq-gallery-release"
TASK = "task-tide-marks-release"
ACTOR = "user-dana"
POST = "post-tide-marks-gallery"
DECOY = "post-tide-marks-preview"
POST_URL = f"https://wordpress.com/preview/post/{POST}"
PIN = "p-tide-marks-release"
PIN_URL = f"https://www.pinterest.com/pin/{PIN}"
BOARD = "b-indoor-exhibitions"
DECOY_BOARD = "b-exhibition-previews"

GUIDES = "Proof frames - hide before export"
CREDIT_LAYER = "Reproduction credit"
TYPE = "Exhibition lettering"
DAY = "Plate A - ochre sun"
NIGHT = "Plate B - copper moon"
INK = "Quay and tidal ink"
PAPER = "Ivory print stock"


@dataclass(frozen=True)
class Format:
    key: str
    name: str
    box: tuple
    color: str

    @property
    def dims(self):
        x0, y0, x1, y1 = self.box
        return (x1 - x0, y1 - y0)

    @property
    def png(self):
        return f"tide-marks-{self.key}.png"

    @property
    def psd(self):
        return f"tide-marks-{self.key}.psd"


WEB = Format("feature", "WordPress feature", (194, 317, 1394, 947), "#a32979")
PIN_ART = Format("pin", "Pinterest pin", (459, 113, 1259, 1313), "#167544")
FORMATS = (WEB, PIN_ART)
REJECTED_CHANNEL = os.environ.get("HX01_REJECTED_CHANNEL", "wordpress_com")
REPAIR_FORMAT = WEB if REJECTED_CHANNEL == "wordpress_com" else PIN_ART


def font(size, serif=False, bold=False):
    family = "DejaVuSerif" if serif else "DejaVuSans"
    file = family + ("-Bold.ttf" if bold else ".ttf")
    return ImageFont.truetype(file, size)


def transparent():
    return Image.new("RGBA", (WIDTH, HEIGHT))


def wave(draw, y, phase, color, offset=0, width=4):
    points = [(x, y + int(33 * math.sin(x / 140 + phase) + 19 * math.cos(x / 260 + offset)))
              for x in range(0, WIDTH + 1, 5)]
    draw.line(points, fill=color, width=width)


def artwork():
    rng = random.Random(1947)
    paper = Image.new("RGBA", (WIDTH, HEIGHT), "#eddfc2")
    draw = ImageDraw.Draw(paper)
    for _ in range(18000):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        shade = rng.choice(("#e5d5b7", "#efdfbc", "#e9dabb", "#f5e6c9"))
        draw.line((x, y, x + rng.randrange(1, 6), y), fill=shade)
    for edge, alpha in [(21, 100), (36, 50), (58, 35)]:
        draw.rectangle((edge, edge, WIDTH - edge, HEIGHT - edge), outline=(82, 68, 45, alpha + 155), width=2)

    ink = transparent()
    draw = ImageDraw.Draw(ink)
    for i in range(13):
        wave(draw, 285 + i * 67, i / 5, "#285c58", i / 8, width=3 + i % 5)
    islands = [
        (160, 1100, 600, 1380), (578, 1040, 930, 1360), (918, 1030, 1440, 1380),
    ]
    for index, (x0, y0, x1, y1) in enumerate(islands):
        points = [(x0, y1), (x0 + 32, y0 + 75), (x0 + 106, y0 + 75),
                  (x0 + 106, y0 + 38), (x0 + 162, y0 + 38), (x0 + 162, y0),
                  (x1 - 81, y0), (x1 - 81, y0 + 54), (x1 - 24, y0 + 54), (x1, y1)]
        draw.polygon(points, fill=("#233f3e", "#152b2c", "#254541")[index])
        for k in range(5):
            x = x0 + 21 + k * 43
            draw.line((x, y0 + 124, x + 85, y1 - 10), fill="#69857b", width=4)
    dock = [(225, 886), (379, 782), (610, 782), (610, 739), (718, 739),
            (718, 694), (836, 694), (836, 641), (977, 641), (1178, 887)]
    draw.polygon(dock, fill="#193e3b")
    for k in range(14):
        x = 380 + 47 * k
        draw.line((x, 809 + 44 * math.sin(k / 2), x - 14, 870), fill="#85a08a", width=2)
    for x, y in ((154, 397), (1302, 374), (118, 580), (1471, 776), (1288, 981)):
        draw.ellipse((x, y, x + 16, y + 16), fill="#284b47")

    def plate(day):
        layer = transparent()
        d = ImageDraw.Draw(layer)
        area = (889, 414, 1101, 626)
        d.ellipse(area, fill="#d5a83a" if day else "#aa553a")
        if not day:
            d.ellipse((961, 427, 1100, 567), fill="#eddfc2")
        for j in range(7):
            y = 530 + j * 10
            dx = int(math.sqrt(106 ** 2 - (y - 520) ** 2))
            d.line((995 - dx, y, 995 + dx, y), fill="#b48835" if day else "#843f2e", width=2)
        return layer

    lettering = transparent()
    draw = ImageDraw.Draw(lettering)
    draw.text((553, 561), "Tide", font=font(115, serif=True, bold=True), fill="#162e2b", stroke_width=3, stroke_fill="#eddfc2")
    draw.text((549, 671), "Marks", font=font(115, serif=True, bold=True), fill="#162e2b", stroke_width=3, stroke_fill="#eddfc2")
    draw.line((569, 794, 777, 794), fill="#c59430", width=8)
    draw.text((569, 821), "S O U T H   Q U A Y", font=font(21, bold=True), fill="#fff0d6")
    draw.text((570, 853), "PRINT EXHIBITION", font=font(20, bold=True), fill="#fff0d6")
    credit_layer = transparent()
    credit_draw = ImageDraw.Draw(credit_layer)
    credit_draw.rectangle((665, 904, 1205, 935), fill="#eddfc2")
    credit_draw.text((670, 909), "ELIN VALE / SOUTH QUAY PRINT COLLECTIVE", font=font(18, bold=True), fill="#162e2b")

    guides = transparent()
    draw = ImageDraw.Draw(guides)
    for f in FORMATS:
        x0, y0, x1, y1 = f.box
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            draw.line((x, y + 48 * dy, x, y, x + 48 * dx, y), fill="white", width=11)
            draw.line((x, y + 48 * dy, x, y, x + 48 * dx, y), fill=f.color, width=7)
    draw.text((38, 75), "PRESS PROOF  /  ALIGN TO COLORED CORNERS", font=font(31, bold=True), fill="#aa2133")
    draw.text((88, 1343), "REVIEW MARKS — INTERNAL", font=font(32, bold=True), fill="#aa2133")
    return [(GUIDES, guides), (CREDIT_LAYER, credit_layer), (TYPE, lettering), (DAY, plate(True)),
            (NIGHT, plate(False)), (INK, ink), (PAPER, paper)]


def build_layers(original, plate=DAY, guides=False, box=None):
    return [(name, layer.crop(box) if box else layer,
             name in (CREDIT_LAYER, TYPE, INK, PAPER, plate) or (name == GUIDES and guides))
            for name, layer in original]


def composite(layers):
    image = Image.new("RGBA", layers[0][1].size)
    for _, layer, visible in reversed(layers):
        if visible:
            image = Image.alpha_composite(image, layer)
    return image


def write_psd(path, layers, *, bottom_first=False):
    """Write an RGB Photoshop document with normal RGBA layers and a composite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = composite(layers).convert("RGB")
    width, height = merged.size
    records, channels = [], []
    records_order = reversed(layers) if bottom_first else layers
    for name, layer, visible in records_order:
        raw_name = name.encode("ascii")
        pascal = bytes([len(raw_name)]) + raw_name
        extra = pack(">II", 0, 0) + pascal + bytes(-len(pascal) % 4)
        planes = [pack(">H", 2) + compress(channel.tobytes(), 6) for channel in layer.split()]
        channel_descriptors = b"".join(pack(">hI", code, len(plane))
                                       for code, plane in zip((0, 1, 2, -1), planes))
        records.append(
            pack(">iiiiH", 0, 0, height, width, len(planes)) + channel_descriptors
            + b"8BIMnorm" + pack(">BBBBI", 255, 0, 0 if visible else 2, 0, len(extra)) + extra
        )
        channels.extend(planes)
    layer_info = pack(">h", len(layers)) + b"".join(records + channels)
    layer_info += bytes(len(layer_info) % 2)
    layer_and_mask = pack(">I", len(layer_info)) + layer_info + pack(">I", 0)
    header = pack(">4sH6xHIIHH", b"8BPS", 1, 3, height, width, 8, 3)
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(pack(">III", 0, 0, len(layer_and_mask)))
        handle.write(layer_and_mask)
        handle.write(pack(">H", 0))
        for plane in merged.split():
            handle.write(plane.tobytes())


def proof(path, layers, preliminary=False):
    """Make a press proof with graphical crop frames and a visible approval stamp."""
    page = Image.new("RGB", (1280, 960), "#f4f0e8")
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, 1280, 142), fill="#223e3d")
    draw.text((38, 35), "SOUTH QUAY  /  CURATOR PRESS PROOF", font=font(39, serif=True, bold=True), fill="#fff0db")
    draw.text((41, 96), "Tide Marks   •   Indoor gallery artwork", font=font(22), fill="#f5e6c9")
    plate = NIGHT if preliminary else DAY
    sample = composite(build_layers(layers, plate=plate)).convert("RGB")
    preview = sample.resize((760, 684), Image.Resampling.LANCZOS)
    page.paste(preview, (29, 177))
    draw.rectangle((28, 176, 790, 861), outline="#787267", width=2)
    for fmt in FORMATS:
        x0, y0, x1, y1 = fmt.box
        boundary = (29 + round(x0 * 0.475), 177 + round(y0 * 0.475),
                    29 + round(x1 * 0.475), 177 + round(y1 * 0.475))
        draw.rectangle(boundary, outline="#fffaf0", width=9)
        draw.rectangle(boundary, outline=fmt.color, width=5)
    draw.rectangle((824, 179, 1242, 289), outline="#8b2d2f" if preliminary else "#167544", width=5)
    draw.text((851, 202), "DRAFT  /  R16" if preliminary else "APPROVED  /  R17", font=font(35, bold=True),
              fill="#8b2d2f" if preliminary else "#167544")
    draw.text((850, 250), "Curator sign-off: Mireya Long" if not preliminary else "Studio proof • no release",
              font=font(22), fill="#223e3d")
    draw.text((827, 324), "AUTHORIZED PLATE", font=font(23, bold=True), fill="#223e3d")
    swatch = sample.crop((886, 412, 1103, 628)).resize((78, 78), Image.Resampling.LANCZOS)
    page.paste(swatch, (830, 362))
    draw.multiline_text((930, 369), "Copper moon\nPlate B" if preliminary else "Ochre full sun\nPlate A",
                        font=font(24), fill="#223e3d", spacing=5)
    draw.text((827, 478), "REPRODUCTION CREDIT", font=font(23, bold=True), fill="#223e3d")
    credit = STALE_CREDIT if preliminary else CREDIT
    draw.multiline_text((827, 516), credit.replace(" / ", " /\n"), font=font(22), fill="#223e3d", spacing=7)
    for i, fmt in enumerate(FORMATS):
        y = 625 + i * 78
        draw.rectangle((827, y, 862, y + 25), outline=fmt.color, width=5)
        draw.text((877, y - 1), fmt.name, font=font(24, bold=True), fill="#223e3d")
        draw.text((878, y + 32), f"{fmt.dims[0]} × {fmt.dims[1]} px", font=font(19), fill="#223e3d")
    draw.text((827, 823), "Match the corresponding corners.", font=font(19), fill="#223e3d")
    draw.text((827, 853), "Omit press marks from release art.", font=font(19), fill="#223e3d")
    draw.text((31, 904), "PRESS AND WEB RIGHTS  /  SOUTH QUAY INDOOR GALLERY ONLY", font=font(20, bold=True), fill="#223e3d")
    path.parent.mkdir(parents=True, exist_ok=True)
    page.save(path)


def stamps(actor=ACTOR, at=DATE):
    return dict(createdBy=actor, updatedBy=actor, createdAt=at, updatedAt=at)


def make_wordpress(old_image):
    def post(pid, title, slug, status, blocks):
        return dict(id=pid, title=title, slug=slug, excerpt="", blocks=blocks, authorId=ACTOR,
                    featuredImageId="media-rehearsal", commentsOpen=False, status=status,
                    publishedAt=DATE if status == "published" else None, scheduledAt=None,
                    trashedAt=None, categoryIds=["cat-arts"], tagIds=[], **stamps())
    main = post(POST, TITLE, "tide-marks-indoor-exhibition", "published", [
        dict(id="visit", type="paragraph", text="South Quay Gallery presents Tide Marks, an indoor exhibition of printed waterfront studies. Visit the North Hall from 20 November to 8 December."),
        dict(id="access", type="paragraph", text="Admission is free. Enter through the main lobby for step-free access."),
        dict(id="credit", type="paragraph", text="Artwork credit pending."),
    ])
    rehearsal = post(DECOY, "Tide Marks: Studio Preview", "tide-marks-studio-preview", "draft", [
        dict(id="studio", type="paragraph", text="Rehearsal notes for the studio team. This draft is for internal discussion."),
    ])
    queue = [post(f"post-gallery-{i:02}", name, f"gallery-note-{i:02}", "published", [
        dict(id="summary", type="paragraph", text=f"{name} is a past gallery program."),
    ]) for i, name in enumerate((
        "Night Ceramics", "Paper Studies", "Drypoint Primer", "Spaced Type", "Field Plates",
        "Archive Week", "Clay Stories", "Mended Cloth", "Kitchen Lithography", "North Hall Guide",
        "Marginal Notes", "Proofing Room",
    ) + ("Gallery Dispatch",) * 16)]
    return dict(
        site=dict(id="site-south-quay", name="South Quay Gallery", tagline="Print and material culture",
                  locale="en-US", timezone="America/New_York"),
        currentUserId=ACTOR, users=[dict(id=ACTOR, name="Dana Holt", username="danah",
                                       email="dana@southquay.example", role="editor")],
        posts=[main, rehearsal, *queue], categories=[
            dict(id="cat-arts", name="Exhibitions", slug="exhibitions", **stamps()),
            dict(id="cat-uncategorized", name="Uncategorized", slug="uncategorized", **stamps()),
        ],
        pages=[], tags=[], comments=[], activity=[],
        media=[dict(id="media-rehearsal", fileName=old_image.name, url=file_url(old_image.name),
                    mimeType="image/png", sizeBytes=old_image.stat().st_size, width=420, height=320,
                    title="Studio setup", altText="Framed art in the gallery hall.",
                    caption="South Quay Gallery archive", description="Reusable rehearsal still.",
                    authorId=ACTOR, uploadedTo=None, **stamps())],
    )


def pinterest_messages():
    # Preserve the clone's stock conversations while replacing its
    # render-time clock with the fixed task-session clock.
    stock = [
        ('conv1', 'u2', [
            ('msg1', 'u2', 'Hey Sarah! Love your latest pin on the Scandinavian kitchen.', 1795089600000),
            ('msg2', 'u1', 'Thanks Marco! I found it on Architectural Digest.', 1795091400000),
            ('msg3', 'u2', 'I should make a recipe inspired by that vibe!', 1795093200000),
            ('msg4', 'u1', 'That would be amazing! Let me know when you do.', 1795095000000),
        ]),
        ('conv2', 'u3', [
            ('msg5', 'u3', 'Are you going to Santorini this year?', 1795010400000),
            ('msg6', 'u1', 'I wish! Maybe next spring. Your photos are inspiring me.', 1795014000000),
            ('msg7', 'u3', 'Let me know if you need any recommendations!', 1795017600000),
        ]),
        ('conv3', 'u5', [
            ('msg8', 'u5', 'Love your fashion board! Can I collaborate?', 1794924000000),
            ('msg9', 'u1', 'Of course! I just sent you an invite.', 1794927600000),
        ]),
        ('conv4', 'u6', [
            ('msg10', 'u6', 'Thanks for following my art board!', 1794837600000),
            ('msg11', 'u1', 'Your work is amazing! Do you take commissions?', 1794841200000),
            ('msg12', 'u6', 'Yes! DM me anytime for details.', 1794844800000),
        ]),
    ]
    return [
        dict(id=conversation_id, participants=["u1", participant],
             messages=[dict(id=message_id, senderId=sender, text=text, createdAt=at)
                       for message_id, sender, text, at in rows],
             updatedAt=rows[-1][3])
        for conversation_id, participant, rows in stock
    ]


def make_pinterest():
    user = dict(id="u-gallery", username="southquaygallery", name="South Quay Gallery",
                avatar=avatar("South Quay Gallery"), bio="Print and material culture", website="https://wordpress.com",
                followers=[], following=[], monthlyViews=1250, createdAt=MILLIS)
    board_specs = [
        (BOARD, "South Quay Indoor Exhibitions", "Current public exhibition posts", "public"),
        (DECOY_BOARD, "South Quay Indoor Exhibitions — Preview", "Embargoed composition reviews", "secret"),
        ("b-archive", "South Quay Archive", "Past exhibition highlights", "public"),
    ]
    boards = []
    pins = []
    for n, (bid, name, description, privacy) in enumerate(board_specs):
        old = f"p-gallery-{n}"
        boards.append(dict(id=bid, userId=user["id"], name=name, description=description,
                           privacy=privacy, coverPinId=old, pins=[old], sections=[],
                           collaborators=[], createdAt=MILLIS, updatedAt=MILLIS))
        pins.append(dict(id=old, userId=user["id"], title=["Tide studies archive", "Tide Marks: plate preview", "Studio archive"][n],
                         description="Past studio study. Preserve this pin.", image=file_url("south-quay-archive.png"),
                         imageWidth=420, imageHeight=320, url=POST_URL if n == 0 else "https://wordpress.com/",
                         boardId=bid, sectionId=None, altText="South Quay archive artwork", tags=[],
                         likes=0, likedBy=[], commentCount=0, saves=0, createdAt=MILLIS))
    return dict(currentUser=user, users=[user], pins=pins, boards=boards, comments=[], notifications=[],
                messages=pinterest_messages(), searchQuery="", searchFilters=[], selectedCategory=None,
                lastUsedBoardId=DECOY_BOARD)


def asana_person(uid, name, title):
    return dict(userId=uid, name=name, title=title, email=f"{uid}@southquay.example", avatar=avatar(name),
                department="Gallery", location="South Quay", timezone="America/New_York", theme="light")


def make_asana(proofs):
    dana = asana_person(ACTOR, "Dana Holt", "Digital Producer")
    curator = asana_person("user-mireya", "Mireya Long", "Curator")
    ids = [dana["userId"], curator["userId"]]
    description = (
        "Release the finished artwork for Tide Marks: An Indoor Print Exhibition. Curatorial rights apply to the approved indoor release proof only. "
        "Use the approved print layer and reproduction credit shown on the signed proof. The two drawn frames are the intended channel crops, "
        "matched to the same-color registration corners in the working artwork. Remove the press marks from both deliverables. Keep the original working layers in the editable handoff.\n\n"
        "Use the existing published WordPress.com post of the same title. Replace its featured image and the artwork credit placeholder only. "
        "Write useful alt text for the featured media and put the approved credit in its caption. Use the public South Quay Indoor Exhibitions board on Pinterest. "
        "Title the Pin Tide Marks: An Indoor Print Exhibition, include the proof credit and a short invitation to the free indoor exhibition, "
        "and use the WordPress Posts list’s View link for this article as the destination.\n\n"
        "Before closing, post both live links here to request a placement check. Mireya replies with screenshots of those exact uploaded versions. Keep an accepted channel unchanged. Repair only the rejected placement from the layered original, preserving the print layers and approved plate. The reproduction credit layer may be repositioned to restore credit clearance. Resubmit both links for final sign-off, and close only after acceptance."
    )
    selected = "section-release"
    tasks = [
        dict(taskId=TASK, name="Tide Marks — artwork release", projectId=PROJECT, sectionId=selected,
             description=description, assigneeId=ACTOR, creatorId=curator["userId"], dueDate="2026-11-19",
             startDate=None, completed=False, completedDate=None, parentTaskId=None, dependencies=[],
             tags=[], attachmentIds=["proof-draft", "proof-approved"], customFieldValues={}, likeCount=0,
             createdDate=DATE, modifiedDate=DATE),
    ]
    for n, name in enumerate(("Confirm plinth labels", "Set lobby map", "Digitize proof sheets", "Count print racks",
                              "Proof lighting card", "Archive opening remarks", "Rehearse welcome", "Check access route",
                              "Print guide for front desk", "Preview board audit", "Schedule volunteer brief")):
        tasks.append(dict(tasks[0], taskId=f"task-gallery-{n}", name=name, description=f"Gallery checklist: {name}.",
                          attachmentIds=[], completed=n < 5, completedDate=DATE if n < 5 else None))
    attachments = [
        dict(attachmentId=key, taskId=TASK, fileName=path.name, fileType="image/png",
             fileSize=path.stat().st_size, fileUrl=file_url(path.name), uploaderId=curator["userId"],
             uploadDate=DATE)
        for key, path in zip(("proof-draft", "proof-approved"), proofs)
    ]
    return dict(
        currentUser=dana, users=[dana, curator],
        teams=[dict(teamId="team-south-quay", name="South Quay Gallery", description="Exhibition operations",
                    memberIds=ids, ownerId=curator["userId"], privacy="private", createdDate=DATE)],
        projects=[dict(projectId=PROJECT, name="South Quay • November releases", teamId="team-south-quay",
                       description="Indoor exhibits", color="teal", icon="project", ownerId=curator["userId"],
                       memberIds=ids, sections=[dict(sectionId=selected, name="Release queue", collapsed=False)],
                       customFields=[], privacy="private", startDate="2026-11-01", dueDate="2026-11-30",
                       archived=False, starred=True, createdDate=DATE, modifiedDate=DATE)],
        tasks=tasks, comments=[dict(commentId="comment-curator", taskId=TASK, userId=curator["userId"],
                                  content="Use signed release proof R17 for the first submission. Its reproduction line is in the reproduction credit layer. A placement check follows your comment with both live links; the press proof alone is not final channel acceptance.",
                                  createdDate=DATE, likedBy=[])],
        portfolios=[], goals=[], notifications=[], attachments=attachments,
    )


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive_picture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (420, 320), "#c6bb9f")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 228, 420, 320), fill="#887454")
    for x, y, c in ((102, 29, "#768c8b"), (247, 51, "#875846")):
        draw.rectangle((x, y, x + 72, y + 140), outline="#2e3530", width=6, fill="#eee1bb")
        draw.polygon([(x + 16, y + 103), (x + 60, y + 43), (x + 57, y + 127)], fill=c)
    image.save(path)


def upload(path, directory, site, serial):
    stored = f"{serial}_{path.name}"
    dest = directory / "files" / site / "fixture" / stored
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, dest)
    return dict(url=f"/files/fixture/{stored}", original_name=path.name, stored_name=stored,
                size=path.stat().st_size, content_type="image/png")


def wordpress_release(state, payload, credit, mode):
    with Image.open(payload["path"]) as art:
        width, height = art.size
    media = dict(id="media-tide-marks", fileName=payload["original_name"], url=payload["url"],
                 mimeType=payload["content_type"], sizeBytes=payload["size"], width=width, height=height,
                 title="tide marks feature", altText=ALT, caption=credit, description="",
                 authorId=ACTOR, uploadedTo=None, **stamps(at=STAMP))
    state["media"].append(media)
    target = DECOY if mode in ("wrong_post", "naive") else POST
    post = next(row for row in state["posts"] if row["id"] == target)
    post.update(featuredImageId=media["id"], updatedAt=STAMP, updatedBy=ACTOR)
    if target == POST:
        post["blocks"][-1]["text"] = credit


def pinterest_release(state, payload, credit, mode, alternate):
    target = DECOY_BOARD if mode in ("wrong_board", "naive") else BOARD
    title = TITLE
    invitation = ("Visit the North Hall for a free indoor exhibition of waterfront print studies."
                  if not alternate else "See the waterfront prints indoors at South Quay Gallery. Admission is free.")
    pin = dict(id=PIN, userId=state["currentUser"]["id"], imageWidth=400, imageHeight=500,
               altText="", tags=[], likes=0, likedBy=[], commentCount=0, saves=0, source="",
               sectionId=None, createdAt=MILLIS + 668000, title=title,
               description=f"{invitation} {credit}", url=POST_URL, image=payload["url"],
               boardId=target, sourceFile={k: v for k, v in payload.items() if k != "path"})
    state["pins"].insert(0, pin)
    board = next(row for row in state["boards"] if row["id"] == target)
    board["pins"].append(PIN)
    board["updatedAt"] = pin["createdAt"]
    state["lastUsedBoardId"] = target


def handoff(state, alternate=False):
    content = (f"Published gallery art on WordPress ({POST_URL}) and Pinterest ({PIN_URL}). "
               "The layered crops are in the release handoff.")
    if alternate:
        content = f"The portrait pin is live at {PIN_URL}. The updated indoor exhibition article is at {POST_URL}."
    state["comments"].append(dict(commentId="comment-release", taskId=TASK, userId=ACTOR,
                                  content=content, createdDate=STAMP, likedBy=[]))
    state["tasks"][0].update(completed=True, completedDate=STAMP, modifiedDate=STAMP)


def make_artifact(path, original, fmt, mode):
    crop = fmt.box
    if fmt == REPAIR_FORMAT and mode not in ("initial_submission", "unrepaired_review", "bypass", "naive"):
        dx,dy = (-400,-480) if fmt == WEB else (0,-580)
        original = [(name, ImageChops.offset(layer, dx, dy) if name == CREDIT_LAYER else layer) for name, layer in original]
    if mode in ("wrong_portrait_safety", "bypass") and (fmt == PIN_ART or mode == "bypass"):
        x0, y0, x1, y1 = crop
        crop = x0 - 116, y0 + 21, x1 - 116, y1 + 21
    if mode == "legal_alternative":
        x0, y0, x1, y1 = crop
        crop = x0 + 4, y0 - 4, x1 + 4, y1 - 4
    stale_plate = mode in ("stale_approval", "naive") or (mode == "stale_portrait_plate" and fmt == PIN_ART)
    plate = NIGHT if stale_plate else DAY
    layers = build_layers(original, plate=plate, guides=mode == "visible_press_marks", box=crop)
    merged = composite(layers)
    path.mkdir(parents=True, exist_ok=True)
    merged.convert("RGB").save(path / fmt.png)
    if mode == "flattened_sources":
        layers = [(TYPE, merged, True)]
    write_psd(path / fmt.psd, layers, bottom_first=True)


def add_review_fixture(current, variant, original, name):
    import hashlib
    wp=current['wordpress_com']; ps=current['pinterest']; a=current['asana']
    media=wp['media'][-1]; pin=next(p for p in ps['pins'] if p['id']==PIN)
    first=variant/'first-submission'
    for fmt in FORMATS: make_artifact(first,original,fmt,'initial_submission')
    first_wp=upload(first/WEB.png,variant,'wordpress_com','proof01')
    pin_bytes=(variant/'files'/'pinterest'/'fixture'/Path(pin['image']).name).read_bytes()
    final_wp_bytes=(variant/'files'/'wordpress_com'/'fixture'/Path(media['url']).name).read_bytes()
    receipt=dict(taskId=TASK,round=1,rejectedChannel=REJECTED_CHANNEL,wordpressMediaId='media-proof-first',wordpressUrl=first_wp['url'],wordpressSha256=hashlib.sha256((first/WEB.png).read_bytes()).hexdigest(),pinterestPinId=PIN,pinterestUrl=pin['image'],pinterestSha256=hashlib.sha256(pin_bytes).hexdigest(),result='changes_requested')
    if REJECTED_CHANNEL == 'pinterest':
        receipt.update(wordpressMediaId=media['id'],wordpressUrl=media['url'],wordpressSha256=hashlib.sha256(final_wp_bytes).hexdigest(),pinterestSha256=hashlib.sha256((first/PIN_ART.png).read_bytes()).hexdigest(),pinterestUrl='/files/fixture/proof01_pin.png')
    a['artworkReviews']=[receipt]
    a['comments'].append(dict(commentId='hx01-review-1',taskId=TASK,userId='user-mireya',content='Pinterest accepted. WordPress reproduction line falls outside the visible feature viewport. Raise its reproduction credit layer to the clear upper-left tide band (WordPress X=-400,Y=-480; portrait contrast X=0,Y=-580). Keep the accepted Pin asset unchanged.',createdDate=STAMP,likedBy=[]))
    if name not in ('unrepaired_review','bypass','naive','stale_approval','visible_press_marks'):
        a['artworkReviews'].append(dict(receipt,round=2,result='accepted',wordpressMediaId=media['id'],wordpressUrl=media['url'],wordpressSha256=hashlib.sha256(final_wp_bytes).hexdigest(),pinterestSha256=hashlib.sha256(pin_bytes).hexdigest()))
    if name=='changed_accepted_channel':
        if REJECTED_CHANNEL=='wordpress_com':
            old=variant/'files/pinterest/fixture'/Path(pin['image']).name
            new=old.with_name('replacement_'+old.name);shutil.copyfile(old,new)
            pin['image']='/files/fixture/'+new.name
        else:
            media['id']='media-replacement-accepted'
            next(p for p in wp['posts'] if p['id']==POST)['featuredImageId']=media['id']
        a['artworkReviews'][-1]['result']='changes_requested'



def main(out):
    original = artwork()
    write_json(out / "input" / "channel-display-spec.json", dict(rejectedChannel=REJECTED_CHANNEL, featureViewport=[1200,440 if REJECTED_CHANNEL=="wordpress_com" else 630], pinViewport=[800,1200 if REJECTED_CHANNEL=="wordpress_com" else 700]))
    seed = out / "seed"
    proof_approved = seed / "files" / "asana" / PROOF
    proof_prelim = seed / "files" / "asana" / PRELIM
    proof(proof_approved, original)
    proof(proof_prelim, original, preliminary=True)
    for site in ("wordpress_com", "pinterest"):
        archive_picture(seed / "files" / site / "south-quay-archive.png")
    # GIMP inserts each imported PSD record above the previous one.
    write_psd(out / "input" / INPUT, build_layers(original, plate=NIGHT, guides=True), bottom_first=True)
    initial = dict(
        wordpress_com=make_wordpress(seed / "files" / "wordpress_com" / "south-quay-archive.png"),
        pinterest=make_pinterest(),
        asana=make_asana((proof_prelim, proof_approved)),
    )
    initial["asana"]["artworkReviewChannel"] = REJECTED_CHANNEL
    initial["wordpress_com"]["posts"][0]["galleryFeatureViewport"] = [1200,440 if REJECTED_CHANNEL=="wordpress_com" else 630]
    initial["pinterest"]["galleryPlacementViewport"] = [800,1200 if REJECTED_CHANNEL=="wordpress_com" else 700]
    for site, state in initial.items():
        write_json(seed / f"{site}.json", state)

    plans = {
        "golden": (FORMATS, True, True, True),
        "unrepaired_review": (FORMATS, True, True, True),
        "changed_accepted_channel": (FORMATS, True, True, True),
        "legal_alternative": (FORMATS, True, True, True),
        "nop": ((), False, False, False),
        "bypass": (FORMATS, True, True, True),
        "one_core": ((WEB,), True, False, False),
        "false_completion": ((), False, False, True),
        "naive": (FORMATS, True, True, True),
        "wrong_portrait_safety": (FORMATS, True, True, True),
        "stale_approval": (FORMATS, True, True, True),
        "stale_portrait_plate": (FORMATS, True, True, True),
        "flattened_sources": (FORMATS, True, True, True),
        "wrong_board": (FORMATS, True, True, True),
        "wrong_post": (FORMATS, True, True, True),
        "visible_press_marks": (FORMATS, True, True, True),
        "marked_pin_upload": (FORMATS, True, True, True),
        "partial_local_only": (FORMATS, False, False, False),
        "partial_wordpress_only": ((WEB,), True, False, False),
    }
    for name, (formats, web, pin, done) in plans.items():
        variant = out / "variants" / name
        current = deepcopy(initial)
        output = variant / "output"
        output.mkdir(parents=True, exist_ok=True)
        artwork_mode = name
        alternate = name == "legal_alternative"
        for fmt in formats:
            make_artifact(output, original, fmt, artwork_mode)
        credit = STALE_CREDIT if artwork_mode in ("naive", "stale_approval") else CREDIT
        if web:
            path = output / WEB.png
            payload = upload(path, variant, "wordpress_com", "wp19-first" if name=="unrepaired_review" and REJECTED_CHANNEL=="wordpress_com" else "wp19")
            wordpress_release(current["wordpress_com"], dict(payload, path=path), credit, name)
        if pin:
            path = output / PIN_ART.png
            if name == "marked_pin_upload":
                marked_crop = build_layers(original, plate=DAY, guides=True, box=PIN_ART.box)
                path = variant / "upload-source" / PIN_ART.png
                path.parent.mkdir(parents=True, exist_ok=True)
                composite(marked_crop).convert("RGB").save(path)
            payload = upload(path, variant, "pinterest", "pin19-first" if name=="unrepaired_review" and REJECTED_CHANNEL=="pinterest" else "pin19")
            pinterest_release(current["pinterest"], payload, credit, name, alternate)
        if done:
            handoff(current["asana"], alternate)
        if web and pin:
            add_review_fixture(current, variant, original, name)
        for site, state in current.items():
            root = variant / "state" / site
            write_json(root / "initial.json", initial[site])
            write_json(root / "current.json", state)
        if name == "golden":
            for site, state in current.items():
                write_json(out / "golden" / f"{site}.json", state)
            shutil.copytree(output, out / "golden_output", dirs_exist_ok=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))

