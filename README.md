# VideoCheck

A macOS desktop utility for batch-inspecting video file metadata, built with PyQt5.

Drag video files into the window (or browse) and VideoCheck scans them in parallel, showing:

| Column | Source |
|---|---|
| Size, FPS, Duration (HH:MM:SS:FF), Resolution, Aspect Ratio | ffprobe |
| Video Codec, Color Space, Audio Codec, Channels | ffprobe |
| Peak dB | ffmpeg `volumedetect` |

Rows sort numerically by column, export to CSV in displayed order, and can be removed with Delete/Backspace. "Open in Finder" reveals the selected file.

## Requirements

- Python 3.10+
- ffmpeg and ffprobe on your PATH (`brew install ffmpeg`)

## Running from source

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python videocheck_qt.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

## Building the app

```bash
pip install -r requirements-dev.txt
pyinstaller VideoCheck.spec
```

The spec bundles an `ffmpeg` binary alongside the executable for the Peak dB scan; place a statically-linked ffmpeg build at the project root before building.

## Project layout

- `videocheck_qt.py` — the current PyQt5 app
- `videocheck.py` — legacy PySimpleGUI prototype, kept for reference
- `tests/` — pytest + pytest-qt suite (runs headless via `QT_QPA_PLATFORM=offscreen`)

© 2025 Liam P. Gordon
