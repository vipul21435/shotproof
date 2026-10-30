from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from shotproof.check import Limits, check, measure
from shotproof.cli import main
from shotproof.encode import EncodeOptions, merge_frames
from shotproof.frames import diff_fraction, is_change, parse_rect


def frame(clock_text_colour, size=(200, 100)):
    im = Image.new("RGB", size, (240, 240, 240))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 199, 20), fill=(30, 30, 30))  # a status bar
    d.rectangle((150, 4, 190, 16), fill=clock_text_colour)  # a "clock" that ticks
    return im


def test_ignore_region_hides_a_ticking_clock():
    a, b = frame((200, 200, 200)), frame((90, 90, 90))
    assert is_change(a, b)
    assert not is_change(a, b, ignore=[(150, 4, 41, 13)])
    # the ignored area is also removed from the denominator
    assert diff_fraction(a, b, ignore=[(0, 0, 200, 100)]) == 0.0


def test_ignore_in_measure_and_cli(tmp_path, capsys):
    frames = [frame((200, 200, 200)), frame((90, 90, 90)), frame((200, 200, 200))]
    path = str(tmp_path / "clock.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[500, 500, 500], loop=0)
    assert measure(path).changed_frames == 2
    assert measure(path, ignore=[(150, 4, 41, 13)]).changed_frames == 0
    assert check(path, Limits(max_changes=0), ignore=[(150, 4, 41, 13)]).ok
    assert main(["check", path, "--max-changes", "0"]) == 1
    capsys.readouterr()
    assert main(["check", path, "--max-changes", "0", "--ignore", "150,4,41,13"]) == 0
    assert main(["check", path, "--ignore", "1,2,3"]) == 2


def test_merge_with_ignore():
    frames = [frame((200, 200, 200)), frame((90, 90, 90)), frame((200, 200, 200))]
    kept, durations = merge_frames(frames, 100, 8, 0.0005, ignore=[(150, 4, 41, 13)])
    assert len(kept) == 1 and durations == [300]


def test_parse_rect_errors():
    assert parse_rect(" 1, 2 ,3,4 ") == (1, 2, 3, 4)
    with pytest.raises(ValueError):
        parse_rect("1,2,3,0", "ignore")


def test_encode_options_carry_ignore():
    assert EncodeOptions(ignore=((1, 2, 3, 4),)).ignore == ((1, 2, 3, 4),)


def test_overlapping_ignore_rects_counted_once():
    a, b = frame((200, 200, 200)), frame((90, 90, 90))
    whole = [(0, 0, 200, 100), (0, 0, 200, 100), (50, 50, 400, 400)]
    assert diff_fraction(a, b, ignore=whole) == 0.0
    # half the canvas ignored twice over: the clock is still outside it, so the fraction doubles exactly
    assert diff_fraction(a, b, ignore=[(0, 50, 200, 50), (0, 50, 200, 50)]) == pytest.approx(2 * diff_fraction(a, b))
