"""``shotproof encode``: decode a clip at a fixed rate, drop codec-noise frames, hold the ends, write a GIF."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

from PIL import Image, ImageDraw

from .frames import Rect, is_change, parse_rect  # noqa: F401  (parse_rect is re-exported for the CLI)

Marker = Tuple[int, int, int, int]  # x, y, w, h in clip pixels
Crop = Tuple[int, int, int, int]  # x, y, w, h in clip pixels


@dataclass
class EncodeOptions:
    fps: float = 8.0
    lead_hold: float = 0.5
    end_hold: float = 1.5
    tolerance: int = 8
    min_fraction: float = 0.0005
    max_width: Optional[int] = None
    crop: Optional[Crop] = None
    marker: Optional[Marker] = None
    ignore: Tuple[Rect, ...] = ()  # clip-pixel regions left out of change detection
    marker_shape: str = "rect"
    marker_color: Tuple[int, int, int] = (230, 40, 40)
    marker_width: int = 4
    colors: int = 128


def parse_marker(text: str) -> Marker:
    return parse_rect(text, "marker")


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError:  # pragma: no cover - exercised only without the extra
        raise RuntimeError("encode needs imageio-ffmpeg: pip install 'shotproof[encode]'") from None
    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_size(ffmpeg: str, clip: str) -> Tuple[int, int]:
    """Read the clip's pixel size from ffmpeg's stream line (ffprobe is not bundled)."""
    import re

    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", clip], capture_output=True, text=True)
    m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", proc.stderr)
    if not m:
        raise ValueError(f"cannot read a video stream from {clip}")
    return int(m.group(1)), int(m.group(2))


def _geometry(size: Tuple[int, int], crop: Optional[Crop], max_width: Optional[int]) -> Tuple[Optional[Crop], int, int, float, float]:
    """Resolve the crop against the clip size and the output size; returns (crop, out_w, out_h, sx, sy).

    ``sx``/``sy`` map cropped-clip pixels to output pixels; they differ slightly because the output height
    is rounded to an even number for the encoder.
    """
    w, h = size
    if crop:
        x, y, cw, ch = crop
        if x < 0 or y < 0 or x + cw > w or y + ch > h:
            raise ValueError(f"crop {crop} is outside the {w}x{h} clip")
        w, h = cw, ch
    src_w, src_h = w, h
    if max_width and w > max_width:
        h = max(2, round(h * max_width / w)) & ~1
        w = max_width
    return crop, w, h, w / src_w, h / src_h


def decode_frames(clip: str, fps: float, max_width: Optional[int] = None, crop: Optional[Crop] = None) -> Iterator[Image.Image]:
    """Yield RGB frames of ``clip`` sampled at ``fps``, cropped and scaled to ``max_width`` if given."""
    if not os.path.exists(clip):
        raise FileNotFoundError(clip)
    ffmpeg = _ffmpeg()
    crop, w, h, _, _ = _geometry(_probe_size(ffmpeg, clip), crop, max_width)
    filters = [f"fps={fps}"]
    if crop:
        filters.append("crop={2}:{3}:{0}:{1}".format(*crop))
    filters.append(f"scale={w}:{h}")
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", clip,
        "-vf", ",".join(filters),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    # stderr goes to a temporary file, not a pipe: a chatty failure must not block ffmpeg while we read stdout.
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf)
        assert proc.stdout is not None
        nbytes = w * h * 3
        try:
            while True:
                buf = proc.stdout.read(nbytes)
                if len(buf) < nbytes:
                    break
                yield Image.frombytes("RGB", (w, h), buf)
        finally:
            proc.stdout.close()
            code = proc.wait()
            errf.seek(0)
            err = errf.read().decode(errors="replace")
        if code != 0:
            raise RuntimeError(f"ffmpeg failed: {err.strip()}")


def merge_frames(frames: List[Image.Image], frame_ms: int, tolerance: int, min_fraction: float,
                 ignore: Optional[List[Rect]] = None) -> Tuple[List[Image.Image], List[int]]:
    """Collapse runs of frames that differ only by codec noise into one frame with a longer duration."""
    if not frames:
        return [], []
    kept = [frames[0]]
    durations = [frame_ms]
    for f in frames[1:]:
        if is_change(kept[-1], f, tolerance, min_fraction, ignore):
            kept.append(f)
            durations.append(frame_ms)
        else:
            durations[-1] += frame_ms
    return kept, durations


def draw_marker(im: Image.Image, marker: Marker, shape: str, color: Tuple[int, int, int], width: int) -> Image.Image:
    out = im.copy()
    x, y, w, h = marker
    box = (x, y, x + w - 1, y + h - 1)
    d = ImageDraw.Draw(out)
    if shape == "ellipse":
        d.ellipse(box, outline=color, width=width)
    else:
        d.rectangle(box, outline=color, width=width)
    return out


def gif_delays(durations: List[int]) -> List[int]:
    """What the GIF will actually carry: whole centiseconds, and never below the 20 ms browsers honour."""
    return [max(20, round(d / 10) * 10) for d in durations]


def write_gif(path: str, frames: List[Image.Image], durations: List[int], colors: int) -> None:
    pal = [f.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations, loop=0, disposal=1, optimize=False)


def encode(clip: str, out: str, opts: EncodeOptions) -> dict:
    """Encode ``clip`` to ``out`` and return the report (also written as ``out`` + ``.json``)."""
    if opts.fps <= 0:
        raise ValueError("fps must be positive")
    frame_ms = max(1, round(1000.0 / opts.fps))
    raw = list(decode_frames(clip, opts.fps, opts.max_width, opts.crop))
    if not raw:
        raise ValueError(f"no frames decoded from {clip}")
    to_output = None
    if opts.marker or opts.ignore:
        # Marker and ignore regions are given in clip pixels; move them into the cropped, scaled output.
        _, _, _, sx, sy = _geometry(_probe_size(_ffmpeg(), clip), opts.crop, opts.max_width)
        ox, oy = (opts.crop[0], opts.crop[1]) if opts.crop else (0, 0)

        def to_output(rect: Rect) -> Rect:
            x, y, w, h = rect
            return round((x - ox) * sx), round((y - oy) * sy), max(1, round(w * sx)), max(1, round(h * sy))

    ignore = [to_output(r) for r in opts.ignore] if opts.ignore else None
    frames, durations = merge_frames(raw, frame_ms, opts.tolerance, opts.min_fraction, ignore)
    if opts.marker:
        frames = [draw_marker(f, to_output(opts.marker), opts.marker_shape, opts.marker_color, opts.marker_width) for f in frames]
    durations[0] = max(durations[0], round(opts.lead_hold * 1000))
    durations[-1] = max(durations[-1], round(opts.end_hold * 1000))
    durations = gif_delays(durations)  # report what the file carries, not what was asked for
    write_gif(out, frames, durations, opts.colors)
    report = {
        "input": os.path.basename(clip),
        "output": os.path.basename(out),
        "fps": opts.fps,
        "decoded_frames": len(raw),
        "kept_frames": len(frames),
        "merged_frames": len(raw) - len(frames),
        "duration_s": round(sum(durations) / 1000.0, 3),
        "lead_hold_s": round(durations[0] / 1000.0, 3),
        "end_hold_s": round(durations[-1] / 1000.0, 3),
        "width": frames[0].size[0],
        "height": frames[0].size[1],
        "bytes": os.path.getsize(out),
        "crop": list(opts.crop) if opts.crop else None,
        "ignore": [list(r) for r in opts.ignore],
        "marker": list(opts.marker) if opts.marker else None,
        "marker_shape": opts.marker_shape if opts.marker else None,
    }
    with open(out + ".json", "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    return report
