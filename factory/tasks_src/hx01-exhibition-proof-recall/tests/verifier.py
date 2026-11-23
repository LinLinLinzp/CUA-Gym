"""Verify image release against the signed R17 proof and persistent site assets."""

import json
import hashlib
import copy
import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import struct
from urllib.parse import unquote, urlsplit
import zlib

from PIL import Image, ImageChops, ImageCms

from cuaverify import InfraError, OUTPUT_DIR, VAR_DIR, load_site, plain, run


TITLE = "Tide Marks: An Indoor Print Exhibition"
CREDIT_WORDS = "tide marks elin vale south quay print collective"
WORKING_NAME = "tide-marks-working.psd"
# Proof R17 specifies the dimensions and colors. The midpoint of each
# registration corner stroke on the source Proof frames layer gives its origin.
CROPS = {
    "feature": (194, 317, 1200, 630),
    "pin": (459, 113, 800, 1200),
}
LAYER_VISIBILITY = (False, True, True, True, False, True, True)
INPUT_DIR = Path(os.environ.get("CUA_INPUT_DIR", Path(__file__).resolve().parent / "reference-input"))
IMAGE_ERRORS = (OSError, ValueError, IndexError, TypeError, OverflowError, struct.error, zlib.error)
UPLOAD_LIMIT = 30 * 1024 * 1024
REFERENCE_BEFORE_REVIEW = None


@dataclass
class Layer:
    name: str
    x: int
    y: int
    image: Image.Image
    visible: bool
    opacity: int
    blend_mode: bytes


def packbits(data, length):
    result = bytearray()
    offset = 0
    while offset < len(data) and len(result) <= length:
        code = data[offset]
        offset += 1
        if code < 128:
            size = code + 1
            result.extend(data[offset:offset + size])
            offset += size
        elif code > 128:
            result.extend(data[offset:offset + 1] * (257 - code))
            offset += 1
    if len(result) != length or offset != len(data):
        raise ValueError("invalid PSD PackBits row")
    return bytes(result)


def plane(data, width, height):
    compression = struct.unpack_from(">H", data)[0]
    if compression == 0:
        pixels = data[2:]
    elif compression == 1:
        lengths = struct.unpack_from(f">{height}H", data, 2)
        offset = 2 + height * 2
        rows = []
        for length in lengths:
            rows.append(packbits(data[offset:offset + length], width))
            offset += length
        pixels = b"".join(rows)
    elif compression in (2, 3):
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(data[2:], width * height + 1)
        if not decoder.eof:
            raise ValueError("truncated or oversized PSD ZIP channel")
        if compression == 3:
            pixels = bytearray(pixels)
            for start in range(0, len(pixels), width):
                for index in range(start + 1, start + width):
                    pixels[index] = (pixels[index] + pixels[index - 1]) & 255
    else:
        raise ValueError("unsupported PSD channel compression")
    if len(pixels) != width * height:
        raise ValueError("PSD channel size mismatch")
    return Image.frombytes("L", (width, height), bytes(pixels))


def read_psd(path):
    if path.stat().st_size > UPLOAD_LIMIT:
        raise ValueError("PSD exceeds limit")
    data = path.read_bytes()
    signature, version, _, height, width, depth, mode = struct.unpack_from(">4sH6xHIIHH", data)
    if (signature, version, depth, mode) != (b"8BPS", 1, 8, 3) or not (0 < width * height <= 5_000_000):
        raise ValueError("expected 8-bit RGB PSD")
    offset = 26

    def unpack(fmt):
        nonlocal offset
        result = struct.unpack_from(">" + fmt, data, offset)
        offset += struct.calcsize(">" + fmt)
        return result

    def skip_section():
        nonlocal offset
        length, = unpack("I")
        offset += length

    skip_section()  # Color-mode data
    skip_section()  # Image resources
    mask_size, = unpack("I")
    mask_end = offset + mask_size
    if mask_end > len(data):
        raise ValueError("truncated PSD layer and mask section")
    layers_size, = unpack("I")
    if not layers_size:
        return (width, height), []
    layers_end = offset + layers_size
    count, = unpack("h")
    if not 0 < abs(count) <= 32 or layers_end > mask_end:
        raise ValueError("invalid PSD layer count or section")
    records = []
    for _ in range(abs(count)):
        top, left, bottom, right, channel_count = unpack("iiiiH")
        descriptors = [unpack("hI") for _ in range(channel_count)]
        signature, mode, opacity, _, flags, _ = unpack("4s4sBBBB")
        extra, = unpack("I")
        end = offset + extra
        if signature != b"8BIM" or end > layers_end:
            raise ValueError("invalid PSD layer record")
        skip_section()  # Layer mask
        skip_section()  # Blending ranges
        name_length, = unpack("B")
        name = data[offset:offset + name_length].decode("mac_roman")
        offset += name_length + (-(name_length + 1) % 4)
        while offset + 12 <= end:
            sig, key, length = unpack("4s4sI")
            if sig != b"8BIM" or offset + length > end:
                break
            if key == b"luni" and length >= 4:
                chars = struct.unpack_from(">I", data, offset)[0]
                if 4 + chars * 2 <= length:
                    name = data[offset + 4:offset + 4 + chars * 2].decode("utf-16-be").rstrip("\0")
            offset += length + length % 2
        offset = end
        records.append((name, left, top, right - left, bottom - top, descriptors, not flags & 2, opacity, mode))

    layers = []
    for name, x, y, layer_width, layer_height, descriptors, visible, opacity, mode in records:
        if not (0 <= layer_width * layer_height <= 12_000_000) or min(layer_width, layer_height) < 0:
            raise ValueError("invalid PSD layer bounds")
        bands = {}
        for channel, length in descriptors:
            if offset + length > layers_end or length < 2:
                raise ValueError("truncated PSD channel")
            if channel in (-1, 0, 1, 2) and layer_width and layer_height:
                bands[channel] = plane(data[offset:offset + length], layer_width, layer_height)
            offset += length
        if all(channel in bands for channel in (0, 1, 2)):
            alpha = bands.get(-1) or Image.new("L", (layer_width, layer_height), 255)
            image = Image.merge("RGBA", (bands[0], bands[1], bands[2], alpha))
        else:
            image = Image.new("RGBA", (layer_width, layer_height))
        layers.append(Layer(name, x, y, image, visible, opacity, mode))
    return (width, height), layers


def read_psd_merged(path):
    """Read the stored RGB composite without Pillow's unsupported layer codecs."""
    data = path.read_bytes()
    signature, version, channels, height, width, depth, mode = struct.unpack_from(">4sH6xHIIHH", data)
    if (signature,version,depth,mode) != (b"8BPS",1,8,3) or channels not in (3,4):
        raise ValueError("expected RGB PSD composite")
    offset = 26
    for _ in range(3):
        length = struct.unpack_from(">I",data,offset)[0]
        offset += 4+length
        if offset > len(data):
            raise ValueError("truncated PSD section")
    compression = struct.unpack_from(">H",data,offset)[0]
    offset += 2
    pixels = width*height
    if compression == 0:
        raw = data[offset:]
    elif compression == 1:
        lengths = struct.unpack_from(f">{channels*height}H",data,offset)
        offset += 2*channels*height
        rows=[]
        for length in lengths:
            rows.append(packbits(data[offset:offset+length],width))
            offset += length
        raw = b"".join(rows)
    elif compression in (2,3):
        decoder=zlib.decompressobj()
        raw=decoder.decompress(data[offset:],pixels*channels+1)
        if not decoder.eof:
            raise ValueError("invalid PSD ZIP composite")
        if compression == 3:
            raw=bytearray(raw)
            for start in range(0,len(raw),width):
                for index in range(start+1,start+width):
                    raw[index]=(raw[index]+raw[index-1])&255
            raw=bytes(raw)
    else:
        raise ValueError("unsupported PSD composite compression")
    if len(raw) != pixels*channels:
        raise ValueError("PSD composite size mismatch")
    bands=[Image.frombytes("L",(width,height),raw[i*pixels:(i+1)*pixels]) for i in range(channels)]
    return Image.merge("RGBA",bands if channels==4 else [*bands,Image.new("L",(width,height),255)])


def normalize_rgb(image):
    converted = image.convert("RGBA")
    if image.info.get("icc_profile"):
        try:
            converted = ImageCms.profileToProfile(
                converted, BytesIO(image.info["icc_profile"]), ImageCms.createProfile("sRGB"), outputMode="RGBA",
            )
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return converted


def read_png_bytes(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("asset is not PNG")
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 5_000_000 or getattr(source, "n_frames", 1) != 1:
            raise ValueError("unexpected PNG size or frame count")
        return normalize_rgb(source)


def output_path(name):
    path = OUTPUT_DIR / name
    return path if path.is_file() and not path.is_symlink() else None


def valid_file(path):
    return path is not None and path.is_file() and not path.is_symlink() and path.stat().st_size <= UPLOAD_LIMIT


def layer_on_canvas(layer, size, origin=(0, 0)):
    result = Image.new("RGBA", size)
    result.paste(layer.image, (layer.x - origin[0], layer.y - origin[1]))
    return result


def compose(size, layers, visibility):
    result = Image.new("RGBA", size)
    for layer, visible in reversed(list(zip(layers, visibility))):
        if visible:
            result = Image.alpha_composite(result, layer_on_canvas(layer, size))
    return result


def average_difference(left, right, mask=None):
    rgb_diff = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
    histogram = rgb_diff.histogram(mask)
    return sum((index % 256) * count for index, count in enumerate(histogram)) / max(1, sum(histogram))


def opaque_similar(left, right, mean_limit):
    if left.size != right.size or left.getchannel("A").getextrema() != (255, 255):
        return False
    return average_difference(left, right) <= mean_limit


def opacity_threshold(image, minimum):
    return image.point([0] * minimum + [255] * (256 - minimum))


def separation_mask(clean, other):
    diff = ImageChops.difference(clean.convert("RGB"), other.convert("RGB"))
    red, green, blue = diff.split()
    return opacity_threshold(ImageChops.lighter(red, ImageChops.lighter(green, blue)), 45)


def crop_box(origin, size):
    x, y = origin
    return x, y, x + size[0], y + size[1]


def matching_crop(image, crop, reference, stale, marked):
    x0, y0, width, height = crop
    if image.size != (width, height) or image.getchannel("A").getextrema() != (255, 255):
        return None
    source_pixels, image_pixels = reference.load(), image.load()
    points = [(x, y, image_pixels[x, y]) for x in range(17, width, 37) for y in range(19, height, 39)]

    def distance(x, y):
        error = 0
        for u, v, actual in points:
            expected = source_pixels[x + u, y + v]
            error += abs(actual[0] - expected[0]) + abs(actual[1] - expected[1]) + abs(actual[2] - expected[2])
        return error

    origins = [(distance(x, y), abs(x - x0) + abs(y - y0), x, y)
               for y in range(max(0, y0 - 20), min(reference.height - height, y0 + 20) + 1)
               for x in range(max(0, x0 - 20), min(reference.width - width, x0 + 20) + 1)]
    closest = [(average_difference(image, reference.crop(crop_box((x, y), image.size))), x, y)
               for _, _, x, y in sorted(origins)[:5]]
    error, x, y = min(closest)
    if error > 4.0 or abs(x - x0) > 12 or abs(y - y0) > 12:
        return None
    box = crop_box((x, y), image.size)
    expected = reference.crop(box)
    alternatives = [stale, marked]
    if REFERENCE_BEFORE_REVIEW is not None:
        alternatives.append(REFERENCE_BEFORE_REVIEW)
    if any(average_difference(image, expected, separation_mask(expected, alternative.crop(box))) > 9.0
           for alternative in alternatives):
        return None
    return x, y


def check_psd(path, image, origin, original_layers):
    size, layers = read_psd(path)
    if size != image.size or len(layers) != len(original_layers):
        return False
    if [layer.name for layer in layers] == [layer.name for layer in reversed(original_layers)]:
        # GIMP writes the stack bottom-first in the PSD record, unlike the
        # reference writer. Require its persistent merged image to agree too.
        if not opaque_similar(read_psd_merged(path), image, 4.0):
            return False
        layers.reverse()
    for expected, actual, visible in zip(original_layers, layers, LAYER_VISIBILITY):
        if (expected.name != actual.name or actual.visible != visible
                or actual.opacity != expected.opacity or actual.blend_mode != expected.blend_mode):
            return False
        reference = layer_on_canvas(expected, size, origin)
        target = layer_on_canvas(actual, size)
        alpha = reference.getchannel("A")
        found_alpha = target.getchannel("A")
        alpha_error = ImageChops.difference(alpha, found_alpha)
        if alpha_error.getextrema()[1] and sum(value * count for value, count in enumerate(alpha_error.histogram())) > (
                size[0] * size[1] * 0.9):
            return False
        if average_difference(target, reference, opacity_threshold(alpha, 48)) > 7:
            return False
    return opaque_similar(compose(size, layers, LAYER_VISIBILITY), image, 4.0)


def upload_bytes(value, site):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", value, flags=re.I)
    if match and len(match[1]) <= UPLOAD_LIMIT * 2:
        try:
            return base64.b64decode(re.sub(r"\s+", "", match[1]), validate=True)
        except binascii.Error:
            return None
    path = unquote(urlsplit(value).path)
    match = re.fullmatch(r"/files/([\w.-]+)/([\w.() ~+@-]+)", path)
    if not match or any(part in (".", "..") for part in match.groups()):
        return None
    sid, filename = match.groups()
    roots = (VAR_DIR / "uploads" / site, VAR_DIR / "files" / site,
             VAR_DIR / "state" / site / "files", VAR_DIR / "state" / site / "uploads",
             VAR_DIR / site / "uploads", VAR_DIR / site / "files")
    for root in roots:
        for candidate in (root / sid / filename, root / filename):
            if valid_file(candidate) and root.resolve() in candidate.resolve().parents:
                return candidate.read_bytes()
    # Some sitehost runs use one shared store. The session in the saved URL
    # still selects the actual uploaded file.
    for root in (VAR_DIR / "uploads", VAR_DIR / "files"):
        candidate = root / sid / filename
        if valid_file(candidate) and root.resolve() in candidate.resolve().parents:
            return candidate.read_bytes()
    return None


def uploaded_crop(value, site, crop, local, reference, stale, marked):
    try:
        data = upload_bytes(value, site)
        if not data:
            return False
        uploaded = read_png_bytes(data)
        if local is not None and not opaque_similar(uploaded, local, 1.0):
            return False
        return matching_crop(uploaded, crop, reference, stale, marked) is not None
    except IMAGE_ERRORS:
        return False


def words(value):
    value = re.sub(r"\(c\)|\bcopyright\b", " ", plain(value))
    return " ".join(re.findall(r"[\w]+", value.replace("©", " ")))


def has_credit(value):
    return bool(re.search(rf"(?:^| ){CREDIT_WORDS}(?: |$)", words(value)))


def index(records, key="id"):
    return {item[key]: item for item in records}


def without(record, *keys):
    return {key: value for key, value in record.items() if key not in keys}


def article_link(value, post_id):
    try:
        parts = urlsplit(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return (parts.scheme in ("http", "https") and parts.hostname in {"wordpress.com", "www.wordpress.com"} and not parts.username
            and unquote(parts.path).rstrip("/") == f"/preview/post/{post_id}")


def pin_link(value, pin_id):
    try:
        parts = urlsplit(value)
    except (ValueError, TypeError, AttributeError):
        return False
    if (parts.scheme not in ("http", "https") or parts.hostname not in {"pinterest.com", "www.pinterest.com"}
            or parts.username):
        return False
    path = unquote(parts.path).rstrip("/")
    if path == f"/pin/{pin_id}":
        return True
    return not path and any(term == f"pin={pin_id}" for term in unquote(parts.query).split("&"))


def links(value):
    return [url.rstrip(".,;:") for url in re.findall(r'https?://[^\s<>()\[\]"\']+', str(value))]


def assess_wordpress(before, after, local, reference, stale, marked):
    originals = index(before["posts"])
    posts = index(after["posts"])
    original = next(post for post in originals.values()
                    if post["title"] == TITLE and post["status"] == "published")
    post_id = original["id"]
    post = posts.get(post_id, {})
    previous_media = index(before["media"])
    media = index(after["media"]).get(post.get("featuredImageId"), {})
    featured = (post.get("status") == "published" and media and media.get("id") not in previous_media
                and uploaded_crop(media.get("url"), "wordpress_com", CROPS["feature"], local, reference, stale, marked))
    featured = bool(featured)
    alt = words(media.get("altText"))
    useful_alt = bool(re.search(r"\b(?:tidal|tide lines|waterlines?|waves?|pier|quay|wharf|"
                                r"waterfront|dock|jetty|sun|ochre|harbor|harbour)\b", alt))
    accessible = featured and useful_alt and has_credit(media.get("caption"))
    old_blocks = original["blocks"]
    new_blocks = post.get("blocks", [])
    credit = next(i for i, block in enumerate(old_blocks) if block.get("text") == "Artwork credit pending.")
    credit_supplied = (
        featured and len(new_blocks) == len(old_blocks) and new_blocks[credit].get("type") == "paragraph"
        and has_credit(new_blocks[credit].get("text"))
        and "artwork credit pending" not in words(new_blocks[credit].get("text"))
        and new_blocks[:credit] + new_blocks[credit + 1:] == old_blocks[:credit] + old_blocks[credit + 1:]
        and without(post, "blocks", "featuredImageId", "updatedAt", "updatedBy")
        == without(original, "blocks", "featuredImageId", "updatedAt", "updatedBy")
        and {key: without(value, "updatedAt", "updatedBy") for key, value in originals.items() if key != post_id}
        == {key: without(value, "updatedAt", "updatedBy") for key, value in posts.items() if key != post_id}
    )
    return post_id, (featured, accessible, credit_supplied)


def board_business(board):
    return {"archived": False, "mergedIntoBoardId": None, **without(board, "updatedAt")}


def assess_pinterest(before, after, post_id, local, reference, stale, marked):
    previous = index(before["pins"])
    actor = before["currentUser"]["id"]
    candidates = [pin for pin in after["pins"] if pin["id"] not in previous and pin["userId"] == actor
                  and re.search(r"\btide marks\b", words(pin.get("title")) + " " + words(pin.get("description")))]
    if len(candidates) != 1:
        return None, (False, False, False)
    pin = candidates[0]
    pin_id = pin["id"]
    asset = uploaded_crop(pin.get("image"), "pinterest", CROPS["pin"], local, reference, stale, marked)
    old_boards, boards = index(before["boards"]), index(after["boards"])
    original = next(board for board in old_boards.values()
                    if board["name"] == "South Quay Indoor Exhibitions" and board["privacy"] == "public")
    board_id = original["id"]
    saved_board = boards.get(board_id, {})
    board_placement = (
        asset and pin.get("boardId") == board_id and saved_board.get("privacy") == "public"
        and saved_board.get("name") == original["name"] and saved_board.get("userId") == actor
        and sorted(saved_board.get("pins", [])) == sorted(original["pins"] + [pin_id])
        and not saved_board.get("archived") and not saved_board.get("mergedIntoBoardId")
        and {key: board_business(value) for key, value in old_boards.items() if key != board_id}
        == {key: board_business(value) for key, value in boards.items() if key != board_id}
    )
    description = words(pin.get("description"))
    invited = (bool(re.search(r"\b(?:free|no charge|complimentary)\b", description))
               and bool(re.search(r"\b(?:indoors?|inside|north hall|gallery)\b", description))
               and bool(re.search(r"\b(?:exhibition|exhibit|visit|see|show|view|explore|join)\b", description)))
    copy_and_link = (asset and words(pin.get("title")) == words(TITLE) and has_credit(pin.get("description"))
                     and invited and article_link(pin.get("url", ""), post_id))
    return pin_id, (asset, board_placement, copy_and_link)


def task_business(task):
    normalized = {"startDate": None, "parentTaskId": None, "completedDate": None, **task}
    normalized["attachmentIds"] = [x for x in normalized.get("attachmentIds",[]) if not x.startswith("hx01-")]
    return without(normalized, "modifiedDate")


def assess_asana(before, after, post_id, pin_id, published):
    if not published:
        return False, False
    original = next(task for task in before["tasks"] if task["name"] == "Tide Marks — artwork release")
    task_id = original["taskId"]
    after_tasks = index(after["tasks"], "taskId")
    task = after_tasks.get(task_id, {})
    actor = before["currentUser"]["userId"]
    previous = index(before["comments"], "commentId")
    comment_links = False
    for comment in after["comments"]:
        if (comment["commentId"] in previous or comment.get("taskId") != task_id
                or comment.get("userId") != actor):
            continue
        urls = links(comment.get("content"))
        if any(article_link(url, post_id) for url in urls) and any(pin_link(url, pin_id) for url in urls):
            comment_links = True
    original_tasks = index(before["tasks"], "taskId")
    complete = (
        comment_links and not original["completed"] and task.get("completed") is True
        and without(task_business(task), "completed", "completedDate")
        == without(task_business(original), "completed", "completedDate")
        and {key: task_business(value) for key, value in original_tasks.items() if key != task_id}
        == {key: task_business(value) for key, value in after_tasks.items() if key != task_id}
        and all(index(after["attachments"], "attachmentId").get(k) == v for k,v in index(before["attachments"], "attachmentId").items())
    )
    return comment_links, complete


def working_psd():
    path = INPUT_DIR / WORKING_NAME
    if not path.is_file():
        path = Path(__file__).with_name("reference-input") / WORKING_NAME
    if not path.is_file():
        path = Path(__file__).resolve().parents[1] / "input" / WORKING_NAME
    try:
        size, original = read_psd(path)
        expected_names = ("Proof frames", "Reproduction credit", "Exhibition lettering", "Plate A", "Plate B", "Quay and tidal ink",
                          "Ivory print stock")
        if len(original) == len(expected_names) and all(
                layer.name.startswith(prefix) for layer, prefix in zip(reversed(original), expected_names)):
            original.reverse()
        if len(original) != len(expected_names) or any(
                not layer.name.startswith(prefix) for layer, prefix in zip(original, expected_names)):
            raise ValueError("working PSD layers do not match the R17 proof")
    except IMAGE_ERRORS as exc:
        raise InfraError(f"cannot read trusted working PSD: {exc}") from exc
    return size, original


def assess_review(asana, wordpress, pinterest, post_id, pin_id):
    reviews=asana.get('artworkReviews', [])
    if len(reviews)<2 or not pin_id:return False
    first=reviews[0]; last=reviews[-1]
    post=index(wordpress['posts']).get(post_id,{})
    media=index(wordpress['media']).get(post.get('featuredImageId'),{})
    pin=index(pinterest['pins']).get(pin_id,{})
    wp=upload_bytes(media.get('url'),'wordpress_com'); pp=upload_bytes(pin.get('image'),'pinterest')
    if not wp or not pp:return False
    changed=first.get('rejectedChannel')
    wb=hashlib.sha256(wp).hexdigest(); pb=hashlib.sha256(pp).hexdigest()
    kept=(first.get('pinterestPinId')==pin_id and first.get('pinterestUrl')==pin.get('image') and first.get('pinterestSha256')==pb) if changed=='wordpress_com' else (first.get('wordpressMediaId')==media.get('id') and first.get('wordpressUrl')==media.get('url') and first.get('wordpressSha256')==wb)
    revised=(first.get('wordpressSha256')!=wb) if changed=='wordpress_com' else (first.get('pinterestSha256')!=pb)
    return (first.get('result')=='changes_requested' and kept and revised
      and last.get('result')=='accepted' and last.get('round',0)>first.get('round',0)
      and last.get('pinterestSha256')==pb and last.get('wordpressSha256')==wb
      and last.get('wordpressMediaId')==media.get('id') and last.get('wordpressUrl')==media.get('url'))



def evaluate(grader):
    global REFERENCE_BEFORE_REVIEW
    wordpress_before, wordpress = load_site("wordpress_com")
    pinterest_before, pinterest = load_site("pinterest")
    asana_before, asana = load_site("asana")
    size, original = working_psd()
    reference = compose(size, original, LAYER_VISIBILITY)
    REFERENCE_BEFORE_REVIEW = reference
    stale = compose(size, original, (False, True, True, False, True, True, True))
    marked = compose(size, original, (True, True, True, True, False, True, True))
    images = {}
    crops = {}
    layers = {}
    originals = {tag: copy.deepcopy(original) for tag in CROPS}
    policy=json.loads((INPUT_DIR / "channel-display-spec.json").read_text())
    repair_tag="feature" if policy["rejectedChannel"]=="wordpress_com" else "pin"
    dx,dy = (-400,-480) if repair_tag=="feature" else (0,-580)
    originals[repair_tag][1].x += dx
    originals[repair_tag][1].y += dy
    references = {tag: compose(size, value, LAYER_VISIBILITY) for tag,value in originals.items()}
    stales = {tag: compose(size, value, (False, True, True, False, True, True, True)) for tag,value in originals.items()}
    marked_versions = {tag: compose(size, value, (True, True, True, True, False, True, True)) for tag,value in originals.items()}
    for tag, expected in CROPS.items():
        png = output_path(f"tide-marks-{tag}.png")
        psd = output_path(f"tide-marks-{tag}.psd")
        images[tag] = None
        crops[tag] = layers[tag] = False
        try:
            if valid_file(png):
                image = read_png_bytes(png.read_bytes())
                origin = matching_crop(image, expected, references[tag], stales[tag], marked_versions[tag])
                if origin is not None:
                    crops[tag] = True
                    images[tag] = image
                    if valid_file(psd):
                        layers[tag] = check_psd(psd, image, origin, originals[tag])
        except IMAGE_ERRORS:
            pass

    for check, tag in (("G1.wordpress_crop", "feature"), ("G2.pinterest_crop", "pin")):
        grader.add(check, 6, crops[tag], f"R17-approved {tag} PNG")
    for check, tag in (("G3.wordpress_layers", "feature"), ("G4.pinterest_layers", "pin")):
        grader.add(check, 6, layers[tag], f"Seven original editable layers in the {tag} PSD")
    post_id, wordpress_scores = assess_wordpress(
        wordpress_before, wordpress, images["feature"], references["feature"], stales["feature"], marked_versions["feature"])
    pin_id, pinterest_scores = assess_pinterest(
        pinterest_before, pinterest, post_id, images["pin"], references["pin"], stales["pin"], marked_versions["pin"])
    review_ok = bool(assess_review(asana, wordpress, pinterest, post_id, pin_id)
                     and wordpress_scores[0] and pinterest_scores[0])
    asana_scores = assess_asana(asana_before, asana, post_id, pin_id, all(wordpress_scores + pinterest_scores) and review_ok)
    grader.add("R1.version_bound_review", 12, review_ok, "Selective revision accepted against exact submitted image versions")

    checks = (
        ("W1.featured", 10, "Actual landscape upload on the published exhibition article"),
        ("W2.accessibility_and_credit", 6, "Descriptive alt text and signed media credit"),
        ("W3.visible_credit", 4, "Signed article credit and preserved published material"),
        ("P1.portrait_asset", 10, "One new Tide Marks Pin with actual portrait artwork"),
        ("P2.board", 5, "Pin on the public exhibition board"),
        ("P3.copy_and_destination", 5, "Approved Pin copy and public article destination"),
        ("A1.release_links", 12, "Article and actual Pin URLs on the original release task"),
        ("A2.close_release", 12, "Original task completed and source attachments retained"),
    )
    for (check, weight, detail), passed in zip(checks, wordpress_scores + pinterest_scores + asana_scores):
        grader.add(check, weight, passed, detail)


if __name__ == "__main__":
    run("hx01-exhibition-proof-recall", "1.0.0", evaluate)
