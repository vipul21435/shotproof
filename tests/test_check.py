from __future__ import annotations

from shotproof.check import Limits, check, measure
from shotproof.cli import main

RED = (200, 30, 30)
BLUE = (30, 30, 200)


def test_measure_counts_changes_and_holds(gif_factory):
    path = gif_factory([(RED, 500), (RED, 500), (BLUE, 100), (BLUE, 100), (BLUE, 1500)])
    m = measure(path)
    assert m.frames == 5
    assert m.duration_s == 2.7
    assert m.changed_frames == 1
    assert m.longest_hold_s == 1.7
    assert m.end_hold_s == 1.7
    assert m.hold_at_end is True
    assert (m.width, m.height) == (64, 48)


def test_hold_not_at_end(gif_factory):
    path = gif_factory([(RED, 2000), (BLUE, 100), (RED, 100), (BLUE, 200)])
    m = measure(path)
    assert m.changed_frames == 3
    assert m.longest_hold_s == 2.0
    assert m.end_hold_s == 0.2
    assert m.hold_at_end is False


def test_codec_noise_is_not_a_change(gif_factory):
    path = gif_factory([(RED, 100), ((203, 32, 29), 100), (RED, 100)])
    assert measure(path).changed_frames == 0


def test_limits_fail(gif_factory):
    path = gif_factory([(RED, 3000), (BLUE, 3000), (RED, 3000), (BLUE, 3000)])
    r = check(path, Limits(max_duration=10.0, max_changes=2, min_end_hold=5.0, max_bytes=10))
    assert not r.ok
    joined = " ".join(r.failures)
    assert "duration 12.0s" in joined
    assert "3 changed frames" in joined
    assert "final still lasts 3.0s" in joined
    assert "bytes exceeds 10" in joined


def test_limits_pass(gif_factory):
    path = gif_factory([(RED, 500), (BLUE, 200), (BLUE, 1800)])
    r = check(path, Limits(max_duration=3.0, max_changes=1, min_end_hold=1.5, max_hold=2.5, max_width=100, max_height=100))
    assert r.ok, r.failures


def test_undecodable_file(tmp_path):
    bad = tmp_path / "bad.gif"
    bad.write_bytes(b"GIF89a" + b"\x00" * 10)
    r = check(str(bad), Limits())
    assert r.measurements is None
    assert r.failures and r.failures[0].startswith("decode:")


def test_cli_exit_codes(gif_factory, capsys):
    path = gif_factory([(RED, 500), (BLUE, 1500)])
    assert main(["check", path]) == 0
    assert main(["check", path, "--max-changes", "0"]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert main(["check", path, "--json", "--no-limit"]) == 0
    assert '"ok": true' in capsys.readouterr().out
    assert main(["check", str(path) + ".missing"]) == 1  # decode failure is a failed check
