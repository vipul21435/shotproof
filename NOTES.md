# Notes

State of the repository at the end of its first day of work.

## What works

- `shotproof check`: every limit in the README, several files at once, `--json`, `--report`, `--ignore`
  regions, exit codes 0/1/2, full-decode failure, browser delay clamp (< 20 ms plays as 100 ms). Tested.
- `shotproof encode`: fixed-rate decode through the bundled ffmpeg, noise-frame merging on the raw RGB frames,
  one shared palette for the whole file so stills come back pixel-identical, lead and end holds, `--crop`,
  `--max-width`, one rectangle or ellipse marker, `--ignore`, delays rounded to what the GIF carries before
  they are reported. Tested end to end on a synthetic H.264 clip.
- `shotproof frames`: list, dump as PNGs, or draw a contact sheet. Tested.
- `shotproof record`: CoreGraphics pointer warp, click and parking through `ctypes`, keystrokes through
  `osascript`, capture through `screencapture -V`, `--dry-run` prints the timed plan. The plan and argument
  checks are tested; the native path was run by hand to make `docs/demo.gif`, whose numbers are in the README.
- GitHub Actions runs the suite on Python 3.9 and 3.12 on ubuntu and macOS, plus a `record --dry-run` on macOS.

## Known gaps

- `record` has no automated test of the native path; it needs a display and the Screen Recording and
  Accessibility permissions.
- `encode` merges on the decoded RGB frames and `check` measures the palette-mapped output, so near the change
  threshold `check` can count one change fewer than `encode` kept (the demo: 6 kept, 4 changes). Merging on
  the quantised frames instead was tried and rejected: palette boundaries amplify codec noise and tripled the
  kept frames.
- Multi-display capture, audio and window-only capture are out of scope. The `--keys` path of `record` was
  not exercised in the demo.
- No PyPI release; install from the repository.

## Repository visibility

The repository was created private. To make it public:

```
gh repo edit vipul21435/shotproof --visibility public --accept-visibility-change-consequences
```
