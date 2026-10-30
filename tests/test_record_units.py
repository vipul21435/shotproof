from __future__ import annotations

import pytest

from shotproof.record import RecordOptions, _applescript_string, parse_point, record


def test_parse_point():
    assert parse_point("10, 20.5") == (10.0, 20.5)
    for bad in ("1", "a,b", "1,2,3"):
        with pytest.raises(ValueError):
            parse_point(bad)


def test_applescript_string_escapes():
    assert _applescript_string('say "hi"\\') == '"say \\"hi\\"\\\\"'


def test_record_argument_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("shotproof.record.sys.platform", "darwin")
    monkeypatch.setattr("shotproof.record.shutil.which", lambda name: "/usr/sbin/screencapture")
    with pytest.raises(ValueError):
        record(RecordOptions(out=str(tmp_path / "a.mov"), seconds=0))
    with pytest.raises(ValueError):
        record(RecordOptions(out=str(tmp_path / "a.mov"), click=True))


def test_record_refuses_other_platforms(tmp_path, monkeypatch):
    monkeypatch.setattr("shotproof.record.sys.platform", "linux")
    with pytest.raises(RuntimeError):
        record(RecordOptions(out=str(tmp_path / "a.mov")))
