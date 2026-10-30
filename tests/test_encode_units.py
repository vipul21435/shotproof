from __future__ import annotations

import pytest
from PIL import Image

from shotproof.encode import draw_marker, merge_frames, parse_marker


def solid(colour, size=(40, 30)):
    return Image.new("RGB", size, colour)


def test_merge_collapses_noise_runs():
    frames = [solid((100, 100, 100)), solid((103, 101, 99)), solid((100, 100, 100)), solid((0, 0, 200)), solid((0, 0, 203))]
    kept, durations = merge_frames(frames, 125, tolerance=8, min_fraction=0.0005)
    assert len(kept) == 2
    assert durations == [375, 250]


def test_merge_keeps_real_changes():
    frames = [solid((0, 0, 0)), solid((255, 255, 255)), solid((0, 0, 0))]
    kept, durations = merge_frames(frames, 100, 8, 0.0005)
    assert len(kept) == 3 and durations == [100, 100, 100]


def test_merge_empty():
    assert merge_frames([], 100, 8, 0.0005) == ([], [])


def test_parse_marker():
    assert parse_marker("10, 20,30,40") == (10, 20, 30, 40)
    for bad in ("1,2,3", "a,b,c,d", "1,2,0,4"):
        with pytest.raises(ValueError):
            parse_marker(bad)


def test_draw_marker_rect_and_ellipse():
    base = solid((255, 255, 255))
    rect = draw_marker(base, (5, 5, 20, 10), "rect", (230, 40, 40), 2)
    assert rect.getpixel((5, 5)) == (230, 40, 40)
    assert rect.getpixel((15, 10)) == (255, 255, 255)  # interior untouched
    assert base.getpixel((5, 5)) == (255, 255, 255)  # input untouched
    ell = draw_marker(base, (5, 5, 20, 10), "ellipse", (230, 40, 40), 2)
    assert ell.getpixel((5, 5)) == (255, 255, 255)  # corner outside the ellipse
    assert ell.getpixel((15, 5)) == (230, 40, 40)  # top of the ellipse
