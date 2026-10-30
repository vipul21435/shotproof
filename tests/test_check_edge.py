"""Edge-case tests for ``check`` and ``measure``; every test builds its own GIF."""

from __future__ import annotations

from PIL import Image

from shotproof.check import Limits, check, measure

W, H = 64, 48


def _base(colour=(120, 120, 120)):
    return Image.new("RGB", (W, H), colour)


def _save(path, images, durations, **kw):
    images[0].save(str(path), save_all=True, append_images=images[1:], duration=durations, loop=0, **kw)
    return str(path)


def test_partial_canvas_updates_measure_full_canvas(tmp_path):
    first = _base()
    second = first.copy()
    second.paste((250, 20, 20), (10, 10, 30, 30))  # only this block differs
    third = second.copy()
    third.paste((20, 20, 250), (35, 5, 55, 25))
    path = _save(tmp_path / "partial.gif", [first, second, third], [200, 200, 800], disposal=1, optimize=True)
    m = measure(path)
    assert (m.width, m.height) == (W, H)
    assert m.frames == 3
    assert m.changed_frames == 2
    assert m.end_hold_s == 0.8


def test_disposal_restore_to_background(tmp_path):
    frames = []
    for i in range(4):
        im = _base((90, 90, 90))
        im.paste((255, 255, 0) if i % 2 else (0, 200, 200), (5, 5, 40, 40))
        frames.append(im)
    path = _save(tmp_path / "dispose.gif", frames, [100, 100, 100, 1000], disposal=2)
    m = measure(path)
    assert m.frames == 4
    assert m.changed_frames == 3
    assert m.end_hold_s == 1.0


def test_transparent_palette_gif_decodes(tmp_path):
    frames = []
    for colour in (1, 2):
        im = Image.new("P", (W, H), 0)
        im.putpalette([0, 0, 0, 255, 0, 0, 0, 0, 255] + [0] * (256 * 3 - 9))
        im.paste(colour, (8, 8, 40, 40))
        frames.append(im)
    path = _save(tmp_path / "transparent.gif", frames, [300, 300], transparency=0, disposal=2)
    m = measure(path)
    assert m.frames == 2
    assert (m.width, m.height) == (W, H)
    assert m.changed_frames == 1
    assert check(path, Limits()).ok


def test_single_frame(tmp_path):
    path = str(tmp_path / "one.gif")
    _base().save(path, duration=750)
    m = measure(path)
    assert m.frames == 1
    assert m.changed_frames == 0
    assert m.end_hold_s == 0.75
    assert m.duration_s == 0.75
    assert m.hold_at_end is True


def test_zero_duration_frames(tmp_path):
    a, b = _base((10, 10, 10)), _base((240, 240, 240))
    path = _save(tmp_path / "zero.gif", [a, b], [0, 0])
    m = measure(path)
    assert m.duration_s == 0.2  # a zero delay plays as 100 ms in browsers, and is measured that way
    assert m.frames == 2
    assert m.changed_frames == 1
    assert check(path, Limits()).measurements is not None


def _pair_with_block(tmp_path, name, delta, box):
    a = _base((100, 100, 100))
    b = a.copy()
    b.paste((100 + delta,) * 3, box)
    return _save(tmp_path / name, [a, b], [500, 500], disposal=1)


def test_tolerance_boundary_not_a_change(tmp_path):
    path = _pair_with_block(tmp_path, "at.gif", 8, (0, 0, 32, 24))
    assert measure(path, tolerance=8).changed_frames == 0


def test_just_over_tolerance_is_a_change(tmp_path):
    path = _pair_with_block(tmp_path, "over.gif", 9, (0, 0, 32, 24))
    assert measure(path, tolerance=8).changed_frames == 1


def test_single_pixel_is_below_min_fraction(tmp_path):
    a = _base((0, 0, 0))
    b = a.copy()
    b.putpixel((20, 20), (255, 255, 255))  # 1 of 3072 pixels, about 0.00033
    path = _save(tmp_path / "dot.gif", [a, b], [500, 500], disposal=1)
    assert measure(path).changed_frames == 0


def test_non_gif_file_fails_decode(tmp_path):
    path = str(tmp_path / "still.png")
    _base().save(path)
    r = check(path, Limits())
    assert r.measurements is None
    assert r.failures[0].startswith("decode:")


def test_missing_path_fails_decode(tmp_path):
    r = check(str(tmp_path / "nope.gif"), Limits())
    assert r.measurements is None
    assert r.failures[0].startswith("decode:")
