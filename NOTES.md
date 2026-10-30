# Notes

State of the repository as of its first day.

## What works

- `shotproof check`: every limit in the README, JSON output, exit codes 0/1/2, full-decode failure. Tested.
- `shotproof encode`: fixed-rate decode through the bundled ffmpeg, noise-frame merging, lead and end holds,
  width scaling, one rectangle or ellipse marker, JSON report. Tested end to end on a synthetic H.264 clip.
- `shotproof record`: CoreGraphics pointer warp, click and parking through `ctypes`, keystrokes through
  `osascript`, capture through `screencapture -V`. Argument checks are tested; the native path was run by hand
  to make `docs/demo.gif`, whose numbers are in the README.
- GitHub Actions runs the test suite on Python 3.9 and 3.12 (ubuntu).

## Not done

- `record` has no automated test of the native path; it needs a display.
- Multi-display capture, audio and window-only capture are out of scope.
- The `--keys` path of `record` was not exercised in the demo.
- No PyPI release; install from the repository.

## Repository visibility

The repository was created private. To make it public:

```
gh repo edit vipul21435/shotproof --visibility public --accept-visibility-change-consequences
```
