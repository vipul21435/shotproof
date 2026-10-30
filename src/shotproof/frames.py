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
                frames.append(Frame(rgb, int(frame.info.get("duration", 0))))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    return frames


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
