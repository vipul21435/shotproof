from __future__ import annotations

import os

from shotproof.cli import main
from shotproof.record import RecordOptions, plan

RED = (200, 30, 30)
BLUE = (30, 30, 200)


def test_frames_writes_every_frame(gif_factory, tmp_path, capsys):
    path = gif_factory([(RED, 500), (BLUE, 1500)])
    out = tmp_path / "dump"
    assert main(["frames", path, str(out)]) == 0
    names = sorted(os.listdir(out))
    assert names == ["clip1-000.png", "clip1-001.png"]
    assert "clip1-001.png 1500ms" in capsys.readouterr().out


def test_frames_on_bad_file(tmp_path):
    assert main(["frames", str(tmp_path / "missing.gif"), str(tmp_path / "d")]) == 2


def test_plan_sequence_and_warning():
    steps = plan(RecordOptions(out="x.mov", seconds=6, move_to=(10, 20), click=True, park=(1, 1), lead=1.5, settle=0.4))
    assert steps[0].endswith("park pointer at 1,1")
    assert any(s.startswith(" 1.50s  move pointer to 10,20") for s in steps)
    assert any(s.startswith(" 1.90s  click") for s in steps)
    assert any(s.startswith(" 2.30s  park pointer") for s in steps)
    assert not any(s.startswith("WARNING") for s in steps)
    late = plan(RecordOptions(out="x.mov", seconds=1, keys="hi", lead=1.0))
    assert late[-1].startswith("WARNING")


def test_record_dry_run_cli(capsys):
    assert main(["record", "x.mov", "--move-to", "5,5", "--click", "--dry-run"]) == 0
    assert "click" in capsys.readouterr().out
    assert main(["record", "x.mov", "--click", "--dry-run"]) == 2


def test_frames_sheet_and_listing(gif_factory, tmp_path, capsys):
    from PIL import Image

    path = gif_factory([(RED, 500), (BLUE, 1500), (RED, 100), (BLUE, 100)])
    sheet = tmp_path / "sheet.png"
    assert main(["frames", path, "--sheet", str(sheet), "--columns", "2", "--thumb-width", "32"]) == 0
    im = Image.open(sheet)
    assert im.size[0] == 2 * (32 + 8) + 8
    assert im.size[1] > 2 * 24
    assert main(["frames", path]) == 0
    assert "1 1500ms" in capsys.readouterr().out
