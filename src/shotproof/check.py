"""``shotproof check``: verify a GIF against limits and report measurements."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from .frames import load_frames, is_change


@dataclass
class Measurements:
    frames: int
    duration_s: float
    changed_frames: int
    longest_hold_s: float
    end_hold_s: float
    hold_at_end: bool
    bytes: int
    width: int
    height: int


@dataclass
class Limits:
    max_duration: Optional[float] = 10.0
    max_changes: Optional[int] = 32
    min_end_hold: Optional[float] = None  # seconds; the file must finish on a still at least this long
    max_hold: Optional[float] = None  # seconds; longest still run anywhere
    max_bytes: Optional[int] = 3_500_000
    max_width: Optional[int] = None
    max_height: Optional[int] = None


@dataclass
class Result:
    measurements: Optional[Measurements]
    failures: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "failures": self.failures,
            "measurements": asdict(self.measurements) if self.measurements else None,
        }


def measure(path: str, tolerance: int = 8, min_fraction: float = 0.0005) -> Measurements:
    frames = load_frames(path)
    if not frames:
        raise ValueError("no frames")
    changed = 0
    longest = 0.0
    run = frames[0].duration_ms / 1000.0
    for prev, cur in zip(frames, frames[1:]):
        if is_change(prev.image, cur.image, tolerance, min_fraction):
            changed += 1
            longest = max(longest, run)
            run = cur.duration_ms / 1000.0
        else:
            run += cur.duration_ms / 1000.0
    longest = max(longest, run)
    # ``run`` now holds the trailing still, which ends the file.
    end_hold = run
    w, h = frames[0].image.size
    return Measurements(
        frames=len(frames),
        duration_s=round(sum(f.duration_ms for f in frames) / 1000.0, 3),
        changed_frames=changed,
        longest_hold_s=round(longest, 3),
        end_hold_s=round(end_hold, 3),
        hold_at_end=end_hold >= longest,
        bytes=os.path.getsize(path),
        width=w,
        height=h,
    )


def check(path: str, limits: Limits, tolerance: int = 8, min_fraction: float = 0.0005) -> Result:
    try:
        m = measure(path, tolerance, min_fraction)
    except ValueError as exc:
        return Result(None, [f"decode: {exc}"])
    fails: List[str] = []
    if limits.max_duration is not None and m.duration_s > limits.max_duration:
        fails.append(f"duration {m.duration_s}s exceeds {limits.max_duration}s")
    if limits.max_changes is not None and m.changed_frames > limits.max_changes:
        fails.append(f"{m.changed_frames} changed frames exceeds {limits.max_changes}")
    if limits.min_end_hold is not None and m.end_hold_s < limits.min_end_hold:
        fails.append(f"final still lasts {m.end_hold_s}s, needs at least {limits.min_end_hold}s")
    if limits.max_hold is not None and m.longest_hold_s > limits.max_hold:
        fails.append(f"longest still {m.longest_hold_s}s exceeds {limits.max_hold}s")
    if limits.max_bytes is not None and m.bytes > limits.max_bytes:
        fails.append(f"{m.bytes} bytes exceeds {limits.max_bytes}")
    if limits.max_width is not None and m.width > limits.max_width:
        fails.append(f"width {m.width} exceeds {limits.max_width}")
    if limits.max_height is not None and m.height > limits.max_height:
        fails.append(f"height {m.height} exceeds {limits.max_height}")
    return Result(m, fails)
