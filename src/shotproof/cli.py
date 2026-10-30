"""Command-line entry point. Exit codes: 0 pass, 1 a check failed, 2 usage or input error."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import List, Optional

from . import __version__
from .check import Limits, check


def _add_check_limits(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("limits (defaults suit a strict reviewer; change them with flags)")
    g.add_argument("--max-duration", type=float, default=10.0, metavar="S", help="total play time in seconds (default 10)")
    g.add_argument("--max-changes", type=int, default=32, metavar="N", help="visually changed frames allowed (default 32)")
    g.add_argument("--min-end-hold", type=float, default=None, metavar="S", help="the file must end on a still at least S seconds long")
    g.add_argument("--max-hold", type=float, default=None, metavar="S", help="no still run may exceed S seconds")
    g.add_argument("--max-bytes", type=int, default=3_500_000, metavar="B", help="file size (default 3500000)")
    g.add_argument("--max-width", type=int, default=None, metavar="PX")
    g.add_argument("--max-height", type=int, default=None, metavar="PX")
    g.add_argument("--no-limit", action="store_true", help="measure only; disable every default limit")
    s = p.add_argument_group("change detection")
    s.add_argument("--tolerance", type=int, default=8, metavar="LEVELS", help="per-channel difference treated as noise (default 8)")
    s.add_argument("--min-fraction", type=float, default=0.0005, metavar="F", help="fraction of pixels that must differ to count as a change (default 0.0005)")


def _limits_from(ns: argparse.Namespace) -> Limits:
    if ns.no_limit:
        return Limits(None, None, None, None, None, None, None)
    return Limits(
        max_duration=ns.max_duration,
        max_changes=ns.max_changes,
        min_end_hold=ns.min_end_hold,
        max_hold=ns.max_hold,
        max_bytes=ns.max_bytes,
        max_width=ns.max_width,
        max_height=ns.max_height,
    )


def cmd_check(ns: argparse.Namespace) -> int:
    limits = _limits_from(ns)
    missing = [g for g in ns.gifs if not os.path.exists(g)]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    results = {gif: check(gif, limits, ns.tolerance, ns.min_fraction) for gif in ns.gifs}
    all_ok = all(r.ok for r in results.values())
    if ns.json:
        payload = {gif: r.to_dict() for gif, r in results.items()}
        print(json.dumps(payload[ns.gifs[0]] if len(ns.gifs) == 1 else payload, indent=2))
    else:
        for gif, result in results.items():
            m = result.measurements
            if m:
                print(f"{gif}: {m.frames} frames, {m.duration_s}s, {m.changed_frames} changes, "
                      f"longest still {m.longest_hold_s}s, final still {m.end_hold_s}s, "
                      f"{m.width}x{m.height}, {m.bytes} bytes")
            for f in result.failures:
                print(f"{gif}: FAIL: {f}" if len(ns.gifs) > 1 else f"FAIL: {f}")
        print("PASS" if all_ok else "FAIL")
    if ns.report:
        with open(ns.report, "w") as fh:
            json.dump({gif: r.to_dict() for gif, r in results.items()}, fh, indent=2)
            fh.write("\n")
    return 0 if all_ok else 1


def cmd_encode(ns: argparse.Namespace) -> int:
    from .encode import encode, EncodeOptions, parse_marker, parse_rect

    marker = parse_marker(ns.marker) if ns.marker else None
    crop = parse_rect(ns.crop, "crop") if ns.crop else None
    opts = EncodeOptions(
        fps=ns.fps,
        lead_hold=ns.lead_hold,
        end_hold=ns.end_hold,
        tolerance=ns.tolerance,
        min_fraction=ns.min_fraction,
        max_width=ns.max_width,
        crop=crop,
        marker=marker,
        marker_shape=ns.marker_shape,
        colors=ns.colors,
    )
    report = encode(ns.clip, ns.out, opts)
    print(json.dumps(report, indent=2))
    return 0


def cmd_record(ns: argparse.Namespace) -> int:
    from .record import record, plan, RecordOptions, parse_point

    opts = RecordOptions(
        out=ns.out,
        seconds=ns.seconds,
        move_to=parse_point(ns.move_to) if ns.move_to else None,
        click=ns.click,
        keys=ns.keys,
        park=parse_point(ns.park) if ns.park else None,
        lead=ns.lead,
        settle=ns.settle,
        display=ns.display,
    )
    if ns.dry_run:
        for line in plan(opts):
            print(line)
        return 0
    path = record(opts)
    print(path)
    return 0


def cmd_frames(ns: argparse.Namespace) -> int:
    from .frames import contact_sheet, load_frames

    frames = load_frames(ns.gif)
    stem = os.path.splitext(os.path.basename(ns.gif))[0]
    if ns.sheet:
        contact_sheet(frames, ns.columns, ns.thumb_width).save(ns.sheet)
        print(f"{ns.sheet}: {len(frames)} frames")
    if ns.out_dir:
        os.makedirs(ns.out_dir, exist_ok=True)
        for i, f in enumerate(frames):
            f.image.save(os.path.join(ns.out_dir, f"{stem}-{i:03d}.png"))
            print(f"{stem}-{i:03d}.png {f.duration_ms}ms")
    if not ns.sheet and not ns.out_dir:
        for i, f in enumerate(frames):
            print(f"{i} {f.duration_ms}ms")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shotproof", description="Record a screen interaction, encode it to a GIF, and prove the GIF meets explicit limits.")
    p.add_argument("--version", action="version", version=f"shotproof {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="verify a GIF against limits; exit 1 if any fails")
    c.add_argument("gifs", nargs="+", metavar="gif", help="one or more GIFs; the exit code is 1 if any fails")
    c.add_argument("--json", action="store_true", help="print the measurements and failures as JSON")
    c.add_argument("--report", metavar="FILE", help="also write the results of every file as JSON to FILE")
    _add_check_limits(c)
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("encode", help="turn a screen recording into a GIF and write a JSON report beside it")
    e.add_argument("clip", help="input video (.mov/.mp4); needs imageio-ffmpeg")
    e.add_argument("out", help="output .gif")
    e.add_argument("--fps", type=float, default=8.0, help="decode rate (default 8)")
    e.add_argument("--lead-hold", type=float, default=0.5, metavar="S", help="hold the first frame for S seconds (default 0.5)")
    e.add_argument("--end-hold", type=float, default=1.5, metavar="S", help="hold the last frame for S seconds (default 1.5)")
    e.add_argument("--max-width", type=int, default=None, metavar="PX", help="scale down so width is at most PX")
    e.add_argument("--crop", default=None, metavar="X,Y,W,H", help="keep only this region of the clip, in clip pixels, before scaling")
    e.add_argument("--marker", default=None, metavar="X,Y,W,H", help="draw one stationary marker over this region")
    e.add_argument("--marker-shape", choices=["rect", "ellipse"], default="rect")
    e.add_argument("--colors", type=int, default=128, help="palette size (default 128)")
    e.add_argument("--tolerance", type=int, default=8, metavar="LEVELS")
    e.add_argument("--min-fraction", type=float, default=0.0005, metavar="F")
    e.set_defaults(func=cmd_encode)

    r = sub.add_parser("record", help="(macOS) drive one scripted interaction and capture the display to a .mov")
    r.add_argument("out", help="output .mov")
    r.add_argument("--seconds", type=float, default=6.0, help="recording length in whole seconds, at least 1 (default 6)")
    r.add_argument("--move-to", metavar="X,Y", help="move the pointer here before acting")
    r.add_argument("--click", action="store_true", help="click at the pointer")
    r.add_argument("--keys", metavar="TEXT", help="type this text after the click")
    r.add_argument("--park", metavar="X,Y", help="move the pointer here afterwards, outside the changing region")
    r.add_argument("--lead", type=float, default=1.0, metavar="S", help="seconds of stillness before the action (default 1)")
    r.add_argument("--settle", type=float, default=0.3, metavar="S", help="seconds between the move and the click (default 0.3)")
    r.add_argument("--display", type=int, default=1, help="display number as screencapture counts them (default 1, the main display)")
    r.add_argument("--dry-run", action="store_true", help="print the timed sequence and exit without touching the pointer or recording")
    r.set_defaults(func=cmd_record)

    f = sub.add_parser("frames", help="list a GIF's frames, dump them as PNGs, or draw a contact sheet")
    f.add_argument("gif")
    f.add_argument("out_dir", nargs="?", help="write one PNG per frame here")
    f.add_argument("--sheet", metavar="PNG", help="write one contact sheet with every frame and its duration")
    f.add_argument("--columns", type=int, default=3)
    f.add_argument("--thumb-width", type=int, default=320, metavar="PX")
    f.set_defaults(func=cmd_frames)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        return ns.func(ns)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"shotproof: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
