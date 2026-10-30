"""End-to-end encode on a short synthetic clip built from PNG frames with the bundled ffmpeg."""

from __future__ import annotations

import json
import subprocess

import pytest
from PIL import Image, ImageDraw

from shotproof.check import Limits, check
from shotproof.cli import main
from shotproof.encode import EncodeOptions, encode

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """Three seconds at 10 fps, 160x120: a box moves at 1.0 s and again at 2.0 s, still otherwise."""
    d = tmp_path_factory.mktemp("clip")
    for i in range(30):
        im = Image.new("RGB", (160, 120), (240, 240, 240))
        dr = ImageDraw.Draw(im)
        x = 10 if i < 10 else (60 if i < 20 else 110)
        dr.rectangle((x, 40, x + 30, 70), fill=(20, 90, 200))
        dr.rectangle((0, 100, 159, 119), fill=(60, 60, 60))
        im.save(d / f"f{i:03d}.png")
    out = d / "clip.mp4"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", "10", "-i", str(d / "f%03d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(out)],
        check=True,
    )
    return str(out)


def test_encode_merges_still_runs(clip, tmp_path):
    out = str(tmp_path / "out.gif")
    report = encode(clip, out, EncodeOptions(fps=10, lead_hold=0.5, end_hold=1.5))
    assert report["decoded_frames"] == 30
    assert report["kept_frames"] == 3, report  # one frame per distinct scene
    assert report["merged_frames"] == 27
    assert report["lead_hold_s"] == 1.0  # the first still already lasts longer than the lead hold
    assert report["end_hold_s"] == 1.5
    assert report["duration_s"] == pytest.approx(3.5, abs=0.01)
    with open(out + ".json") as fh:
        assert json.load(fh) == report
    r = check(out, Limits(max_duration=4, max_changes=2, min_end_hold=1.5))
    assert r.ok, r.failures
    assert r.measurements.changed_frames == 2  # exactly kept_frames - 1: the shared palette adds no noise
    assert r.measurements.hold_at_end


def test_encode_marker_and_scale(clip, tmp_path):
    out = str(tmp_path / "marked.gif")
    report = encode(clip, out, EncodeOptions(fps=10, max_width=80, marker=(110, 40, 31, 31)))
    assert (report["width"], report["height"]) == (80, 60)
    assert report["marker"] == [110, 40, 31, 31]
    im = Image.open(out).convert("RGB")
    # the marker is drawn at half scale: x 55, y 20, 16 wide; its left edge carries the marker's exact colour
    assert im.getpixel((55, 28)) == (230, 40, 40)


def test_encode_cli(clip, tmp_path, capsys):
    out = str(tmp_path / "cli.gif")
    assert main(["encode", clip, out, "--fps", "5", "--marker", "10,40,31,31", "--marker-shape", "ellipse"]) == 0
    assert '"kept_frames"' in capsys.readouterr().out
    assert main(["encode", str(tmp_path / "nope.mp4"), out]) == 2
    assert main(["encode", clip, out, "--marker", "1,2"]) == 2


def test_encode_crop_moves_marker(clip, tmp_path):
    out = str(tmp_path / "cropped.gif")
    # keep the middle band of the clip: the moving box lives at y 40..70, the dark bar at y 100+ is cut off
    report = encode(clip, out, EncodeOptions(fps=10, crop=(0, 30, 160, 60), marker=(110, 40, 31, 31)))
    assert (report["width"], report["height"]) == (160, 60)
    assert report["crop"] == [0, 30, 160, 60]
    im = Image.open(out).convert("RGB")
    assert im.getpixel((110, 20)) == (230, 40, 40)  # marker's left edge, now at y 40-30
    assert im.getpixel((5, 55))[0] > 200  # no dark bar: it was below the crop


def test_encode_crop_outside_clip(clip, tmp_path):
    with pytest.raises(ValueError):
        encode(clip, str(tmp_path / "x.gif"), EncodeOptions(crop=(100, 100, 100, 100)))
    assert main(["encode", clip, str(tmp_path / "x.gif"), "--crop", "100,100,100,100"]) == 2


def test_encode_ignore_region(clip, tmp_path):
    # ignoring the whole band the box moves in leaves a clip with no changes at all
    out = str(tmp_path / "ignored.gif")
    report = encode(clip, out, EncodeOptions(fps=10, ignore=((0, 35, 160, 40),)))
    assert report["kept_frames"] == 1
    assert report["ignore"] == [[0, 35, 160, 40]]
    # ignore regions are mapped through crop and scale like the marker
    report = encode(clip, out, EncodeOptions(fps=10, max_width=80, crop=(0, 30, 160, 60), ignore=((0, 35, 160, 40),)))
    assert report["kept_frames"] == 1


def test_shared_palette_keeps_stills_identical(tmp_path):
    """Two RGB-identical frames must come out of the GIF pixel-identical, whatever the palette size."""
    from shotproof.encode import write_gif
    from shotproof.frames import diff_fraction, load_frames

    base = Image.new("RGB", (120, 80))
    px = base.load()
    for y in range(80):
        for x in range(120):
            px[x, y] = (x * 2, y * 3, (x + y) % 256)  # a gradient that a small palette must approximate
    other = base.copy()
    ImageDraw.Draw(other).rectangle((10, 10, 40, 40), fill=(255, 0, 0))
    out = str(tmp_path / "pal.gif")
    write_gif(out, [base, base.copy(), other, base.copy()], [100, 100, 100, 100], colors=32)
    frames = load_frames(out)
    # the writer folds the two identical opening frames into one, so three frames come back
    assert [f.duration_ms for f in frames] == [200, 100, 100]
    assert diff_fraction(frames[0].image, frames[2].image, tolerance=0) == 0.0
    assert diff_fraction(frames[0].image, frames[1].image) > 0.05


def test_marker_colour_survives_a_small_palette(tmp_path):
    """A thin marker over a busy frame must keep its own palette entry even at 16 colours."""
    from shotproof.encode import draw_marker, write_gif

    base = Image.new("RGB", (640, 360))
    px = base.load()
    for y in range(360):
        for x in range(640):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
    marked = draw_marker(base, (100, 100, 200, 60), "rect", (230, 40, 40), 4)
    out = str(tmp_path / "m.gif")
    write_gif(out, [marked], [500], colors=16, keep=[(230, 40, 40)])
    assert Image.open(out).convert("RGB").getpixel((100, 130)) == (230, 40, 40)
