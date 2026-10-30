# shotproof

Record a screen interaction on macOS, encode it to a GIF, and prove the GIF meets explicit limits.

Three commands, one Python package, no service:

| command | does |
|---|---|
| `shotproof record` | (macOS) drives one scripted pointer move, click or keystroke, parks the pointer, and captures the display to a `.mov` |
| `shotproof encode` | turns a clip into a GIF: fixed decode rate, codec-noise frames merged, a leading still and a trailing hold, an optional stationary marker, and a JSON report beside the output |
| `shotproof check` | measures a GIF (duration, changed frames, longest still and whether it ends the file, byte and pixel size, full decode) and exits 1 when a limit is exceeded |

`check` is pure Python + Pillow and runs anywhere, CI included. Only `record` is macOS-bound.

Status: `check` and `encode` are implemented and tested. `record` is in progress.

## Install

```
pip install .            # check only
pip install '.[encode]'  # adds imageio-ffmpeg for encode
```

## Exit codes

0 every check passed · 1 a check failed (or the file did not decode) · 2 usage or input error.

## Licence

MIT.
