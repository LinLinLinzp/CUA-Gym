"""Helpers for world builders: offline images so seeded pages never show broken
<img> tags (the browser has no internet at rollout time)."""

import hashlib
from pathlib import Path
from urllib.parse import quote

PALETTE = ["#1a73e8", "#d93025", "#188038", "#e37400", "#9334e6", "#007b83", "#c5221f", "#5f6368",
           "#b06000", "#3949ab", "#00897b", "#6d4c41"]


def _color(seed: str) -> str:
    return PALETTE[int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(PALETTE)]


def _uri(svg: str) -> str:
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def avatar(name: str, size: int = 96) -> str:
    """Round avatar with initials, colour stable per name."""
    initials = "".join(part[0] for part in name.replace("&", " ").split()[:2]).upper() or "?"
    return _uri(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 96 96">'
        f'<circle cx="48" cy="48" r="48" fill="{_color(name)}"/>'
        f'<text x="48" y="60" font-family="Arial,Helvetica,sans-serif" font-size="38" fill="#fff" '
        f'text-anchor="middle">{initials}</text></svg>'
    )


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def product_image(title: str, size: int = 400) -> str:
    """Soft square tile with the product name, for catalog thumbnails."""
    words = title.split(" - ")[0].split()
    lines = [" ".join(words[i:i + 2]) for i in range(0, min(len(words), 6), 2)]
    text = "".join(f'<tspan x="200" dy="{0 if i == 0 else 34}">{_xml(line)}</tspan>' for i, line in enumerate(lines))
    return _uri(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 400 400">'
        f'<rect width="400" height="400" fill="{_color(title)}" opacity="0.18"/>'
        f'<text x="200" y="{200 - 17 * (len(lines) - 1)}" font-family="Arial,Helvetica,sans-serif" font-size="28" '
        f'fill="#333" text-anchor="middle">{text}</text></svg>'
    )


# ---------------------------------------------------------------- media (levers L02/L11)
# Need Pillow + reportlab: run world.py with factory/.venv/bin/python.
# Attach files by writing them to <out>/seed/files/<site>/<name> and referencing them in
# seed state as file_url(name); the runtime swaps __SID__ for the task's session id.


def file_url(name: str) -> str:
    return f"/files/__SID__/{name}"


def scan_document(lines, path, *, seed: int = 0, width: int = 1240, title: str | None = None, stamp: str | None = None):
    """Render text as a slightly rotated, noisy scan (PNG or PDF by suffix). Text is not selectable."""
    import random
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

    rng = random.Random(seed)
    body, head = ImageFont.load_default(size=26), ImageFont.load_default(size=40)
    height = 220 + 42 * len(lines)
    page = Image.new("L", (width, max(height, 900)), 248)
    draw = ImageDraw.Draw(page)
    y = 90
    if title:
        draw.text((90, y), title, fill=25, font=head)
        y += 80
    for line in lines:
        draw.text((90 + rng.randint(-2, 2), y), line, fill=30 + rng.randint(0, 25), font=body)
        y += 42
    if stamp:
        mark = Image.new("L", (520, 120), 255)
        ImageDraw.Draw(mark).text((20, 30), stamp, fill=90, font=head)
        mark = mark.rotate(rng.uniform(-12, 12), expand=True, fillcolor=255)
        page.paste(mark, (width - 620, y - 40), mark.point(lambda p: 255 - p))
    # Light paper grain, a small skew and blur so it reads like a scan.
    grain = Image.effect_noise(page.size, 24).point(lambda p: 236 + p * 19 // 255)
    page = ImageChops.multiply(page, grain)
    page = page.rotate(rng.uniform(-1.4, 1.4), expand=True, fillcolor=235).filter(ImageFilter.GaussianBlur(0.6))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.convert("RGB").save(path, "PDF" if path.suffix == ".pdf" else None, resolution=150)
    return path


def long_pdf(path, title: str, sections):
    """Multi-page policy/contract PDF; sections = [(heading, [paragraph, ...]), ...]."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for heading, paragraphs in sections:
        story.append(Paragraph(heading, styles["Heading2"]))
        story += [Paragraph(p, styles["BodyText"]) for p in paragraphs]
        story.append(Spacer(1, 8))
    SimpleDocTemplate(str(path), pagesize=LETTER, title=title).build(story)
    return path


def bar_chart(path, title: str, labels, values, *, unit: str = ""):
    """Plain bar chart PNG whose values must be read off the bars and labels."""
    from PIL import Image, ImageDraw, ImageFont

    w, h, pad = 1100, 640, 90
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    font, big = ImageFont.load_default(size=18), ImageFont.load_default(size=26)
    d.text((pad, 24), title, fill="black", font=big)
    top = max(values) * 1.15 or 1
    bw = (w - 2 * pad) / max(len(values), 1)
    for i, (label, v) in enumerate(zip(labels, values)):
        x0 = pad + i * bw + bw * 0.15
        y0 = h - pad - (h - 2 * pad) * v / top
        d.rectangle([x0, y0, x0 + bw * 0.7, h - pad], fill="#3b6ea8")
        d.text((x0, h - pad + 10), str(label), fill="black", font=font)
        d.text((x0, y0 - 24), f"{v:g}{unit}", fill="#333", font=font)
    d.line([pad, h - pad, w - pad, h - pad], fill="black", width=2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
