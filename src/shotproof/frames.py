"""Shared frame helpers: decode a GIF into full-canvas RGB frames and compare them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageSequence

Rect = Tuple[int, int, int, int]  # x, y, w, h


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


def diff_fraction(a: Image.Image, b: Image.Image, tolerance: int = 8, ignore: Optional[Sequence[Rect]] = None) -> float:
    """Fraction of compared pixels whose largest channel difference exceeds ``tolerance``.

    Pixels inside any ``ignore`` rectangle are left out of both the count and the total, so a clock or a
    status indicator can tick without counting as a change.
    """
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b)
    r, g, bl = diff.split()
    biggest = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    mask = biggest.point(lambda v: 255 if v > tolerance else 0)
    total = a.size[0] * a.size[1]
    if ignore:
        from PIL import ImageDraw

        keep = Image.new("L", a.size, 255)  # 255 where pixels are compared
        draw = ImageDraw.Draw(keep)
        for x, y, w, h in ignore:
            draw.rectangle((x, y, x + w - 1, y + h - 1), fill=0)
        mask = ImageChops.multiply(mask, keep)
        total = keep.histogram()[255]  # counted from the drawing, so overlaps and off-canvas parts are exact
    changed = mask.histogram()[255]
    return changed / total if total > 0 else 0.0


def is_change(a: Image.Image, b: Image.Image, tolerance: int = 8, min_fraction: float = 0.0005,
              ignore: Optional[Sequence[Rect]] = None) -> bool:
    """True when ``b`` differs from ``a`` by more than codec noise outside the ignored regions."""
    return diff_fraction(a, b, tolerance, ignore) > min_fraction


def parse_rect(text: str, what: str = "region") -> Rect:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError(f"{what} must be X,Y,W,H")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f"{what} must be four integers X,Y,W,H") from None
    if w <= 0 or h <= 0:
        raise ValueError(f"{what} width and height must be positive")
    return x, y, w, h


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
