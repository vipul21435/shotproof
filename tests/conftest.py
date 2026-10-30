from __future__ import annotations

from typing import List, Sequence, Tuple

import pytest
from PIL import Image, ImageDraw


def make_gif(path, frames: Sequence[Tuple[Tuple[int, int, int], int]], size=(64, 48)) -> str:
    """Write a GIF frame by frame. Each entry is (fill colour, duration ms)."""
    images: List[Image.Image] = []
    durations: List[int] = []
    for index, (colour, ms) in enumerate(frames):
        im = Image.new("RGB", size, colour)
        d = ImageDraw.Draw(im)
        d.rectangle((2, 2, 10, 10), fill=(255, 255, 255))  # a fixed detail so frames are not flat
        # One pixel wobbles by a level per frame: below any sane tolerance, but it stops
        # the writer from merging identical consecutive frames into one long frame.
        d.point((size[0] - 1, size[1] - 1), fill=(index % 4, index % 4, index % 4))
        images.append(im)
        durations.append(ms)
    images[0].save(str(path), save_all=True, append_images=images[1:], duration=durations, loop=0, disposal=2)
    return str(path)


@pytest.fixture
def gif_factory(tmp_path):
    counter = {"n": 0}

    def _make(frames, size=(64, 48)):
        counter["n"] += 1
        return make_gif(tmp_path / f"clip{counter['n']}.gif", frames, size)

    return _make
