"""``shotproof record``: drive one scripted interaction and capture the display to a .mov (macOS only).

The pointer is moved with CoreGraphics through ``ctypes`` (no extra packages), text is typed through
``osascript``, and the display is recorded with the system ``screencapture -V``. The sequence is:
stillness, one direct pointer move, an optional click and keystrokes, then the pointer parked outside the
changing region so the tail of the clip is a clean still that ``encode`` can hold.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

Point = Tuple[float, float]


@dataclass
class RecordOptions:
    out: str
    seconds: float = 6.0
    move_to: Optional[Point] = None
    click: bool = False
    keys: Optional[str] = None
    park: Optional[Point] = None
    lead: float = 1.0
    settle: float = 0.3
    display: int = 1


def parse_point(text: str) -> Point:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise ValueError("a point is X,Y")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError("a point is two numbers X,Y") from None


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CoreGraphics:
    """The few CoreGraphics calls needed to move and click the pointer."""

    MOVED, LDOWN, LUP = 5, 1, 2
    LEFT = 0

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("record works on macOS only")
        path = ctypes.util.find_library("CoreGraphics") or "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        self.cg = ctypes.CDLL(path)
        self.cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        self.cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, _CGPoint, ctypes.c_uint32]
        self.cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self.cg.CGWarpMouseCursorPosition.argtypes = [_CGPoint]
        cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation") or "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.cf = cf

    def _post(self, kind: int, p: Point) -> None:
        ev = self.cg.CGEventCreateMouseEvent(None, kind, _CGPoint(*p), self.LEFT)
        if not ev:
            raise RuntimeError("CGEventCreateMouseEvent failed")
        self.cg.CGEventPost(0, ev)  # kCGHIDEventTap
        self.cf.CFRelease(ev)

    def move(self, p: Point) -> None:
        """One direct move: a warp followed by a single moved event, so no path is animated."""
        self.cg.CGWarpMouseCursorPosition(_CGPoint(*p))
        self._post(self.MOVED, p)

    def click(self, p: Point) -> None:
        self._post(self.LDOWN, p)
        time.sleep(0.06)
        self._post(self.LUP, p)


def type_text(text: str) -> None:
    script = 'tell application "System Events" to keystroke ' + _applescript_string(text)
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def plan(opts: RecordOptions) -> List[str]:
    """The timed sequence ``record`` will perform, one line per step, with no side effects."""
    _validate(opts)
    t = 0.0
    steps: List[str] = []
    if opts.park:
        steps.append(f"{t:5.2f}s  park pointer at {opts.park[0]:g},{opts.park[1]:g}")
    steps.append(f"{t:5.2f}s  start recording display {opts.display} for {opts.seconds:g}s -> {opts.out}")
    t += opts.lead
    if opts.move_to:
        steps.append(f"{t:5.2f}s  move pointer to {opts.move_to[0]:g},{opts.move_to[1]:g}")
        t += opts.settle
        if opts.click:
            steps.append(f"{t:5.2f}s  click")
    if opts.keys:
        t += opts.settle
        steps.append(f"{t:5.2f}s  type {opts.keys!r}")
    if opts.park:
        t += opts.settle
        steps.append(f"{t:5.2f}s  park pointer at {opts.park[0]:g},{opts.park[1]:g}")
    steps.append(f"{opts.seconds:5.2f}s  recording ends")
    if t >= opts.seconds:
        steps.append(f"WARNING: the last action is at {t:.2f}s but the recording ends at {opts.seconds:g}s")
    return steps


def _validate(opts: RecordOptions) -> None:
    if opts.seconds < 1 or opts.seconds != int(opts.seconds):
        raise ValueError("seconds must be a whole number of at least 1 (screencapture counts whole seconds)")
    if opts.click and opts.move_to is None:
        raise ValueError("--click needs --move-to")


def record(opts: RecordOptions) -> str:
    if sys.platform != "darwin" or not shutil.which("screencapture"):
        raise RuntimeError("record needs macOS with screencapture")
    _validate(opts)
    out = os.path.abspath(opts.out)
    if os.path.exists(out):
        os.remove(out)
    cg = _CoreGraphics()
    if opts.park:
        cg.move(opts.park)  # start where the clip will end, so the lead-in is already clean
    proc = subprocess.Popen(
        ["screencapture", "-x", "-V", str(int(opts.seconds)), "-D", str(opts.display), out],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        time.sleep(opts.lead)
        if opts.move_to:
            cg.move(opts.move_to)
            time.sleep(opts.settle)
            if opts.click:
                cg.click(opts.move_to)
        if opts.keys:
            time.sleep(opts.settle)
            type_text(opts.keys)
        if opts.park:
            time.sleep(opts.settle)
            cg.move(opts.park)
        err = proc.communicate()[1].decode(errors="replace")
    finally:
        if proc.poll() is None:
            proc.terminate()
    if proc.returncode not in (0, None) or not os.path.exists(out):
        raise RuntimeError(f"screencapture failed ({proc.returncode}): {err.strip()}")
    return out
