"""Shared frame helpers: decode a GIF into full-canvas RGB frames and compare them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PIL import Image, ImageChops, ImageSequence


@dataclass
class Frame:
    image: Image.Image  # RGB, full canvas
    duration_ms: int


def load_frames(path: str) -> List[Frame]:
    """Decode every frame of a GIF, composited to the full canvas.

    Raises ``ValueError`` if any frame fails to decode.
    """
    frames: List[Frame] = []
    try:
        with Image.open(path) as im:
            if im.format != "GIF":
                raise ValueError(f"not a GIF: {im.format}")
            for index, frame in enumerate(ImageSequence.Iterator(im)):
                try:
                    rgb = frame.convert("RGB")
                    rgb.load()
                except Exception as exc:  # truncated or corrupt data
                    raise ValueError(f"frame {index} failed to decode: {exc}") from exc
                frames.append(Frame(rgb, effective_delay(int(frame.info.get("duration", 0)))))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    return frames


def effective_delay(duration_ms: int) -> int:
    """The delay a browser actually plays: a delay under 20 ms is shown for 100 ms, as browsers do."""
    return 100 if duration_ms < 20 else duration_ms


def diff_fraction(a: Image.Image, b: Image.Image, tolerance: int = 8) -> float:
    """Fraction of pixels whose largest channel difference exceeds ``tolerance``."""
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b)
    r, g, bl = diff.split()
    biggest = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    mask = biggest.point(lambda v: 255 if v > tolerance else 0)
    changed = mask.histogram()[255]
    total = a.size[0] * a.size[1]
    return changed / total if total else 0.0


def is_change(a: Image.Image, b: Image.Image, tolerance: int = 8, min_fraction: float = 0.0005) -> bool:
    """True when ``b`` differs from ``a`` by more than codec noise."""
    return diff_fraction(a, b, tolerance) > min_fraction


def contact_sheet(frames: List[Frame], columns: int = 3, thumb_width: int = 320) -> Image.Image:
    """One image with every frame as a thumbnail and its duration printed under it."""
    from PIL import ImageDraw

    if not frames:
        raise ValueError("no frames")
    w, h = frames[0].image.size
    tw = min(thumb_width, w)
    th = max(1, round(h * tw / w))
    pad, label = 8, 16
    columns = max(1, min(columns, len(frames)))
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (tw + pad) + pad, rows * (th + label + pad) + pad), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        x = pad + (i % columns) * (tw + pad)
        y = pad + (i // columns) * (th + label + pad)
        sheet.paste(f.image.resize((tw, th)), (x, y))
        draw.rectangle((x - 1, y - 1, x + tw, y + th), outline=(180, 180, 180))
        draw.text((x, y + th + 2), f"{i}  {f.duration_ms} ms", fill=(40, 40, 40))
    return sheet
