# TankLapse

**Lightweight interval screenshot capture & timelapse utility**

TankLapse writes every frame **directly to local disk** as individual lightweight image files.  
This design completely avoids RAM overload and supports **truly infinite-duration recordings**.  
When you stop, frames are automatically stitched into a high-framerate MP4 via FFmpeg.

Perfect for documenting long coding sessions, design work, research, or any activity you want to turn into a smooth timelapse without worrying about memory.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

## Features

- **Disk-first capture** – frames never accumulate in RAM
- **Infinite duration** – run for hours or days without memory growth
- **Configurable interval** (from 0.2 s upward)
- **Multi-monitor support**
- **JPEG (quality adjustable) or PNG** output
- **Automatic MP4 stitching** on stop (or manual)
- **High-framerate export** (1–120 FPS)
- **Clean, lightweight Tkinter GUI** – no Electron bloat
- **Cross-platform** (Windows, macOS, Linux)

## Requirements

| Component     | Notes                                      |
|---------------|--------------------------------------------|
| Python        | 3.9 or newer                               |
| FFmpeg        | Must be installed and available on `PATH`  |
| mss + Pillow  | Installed via `pip` (see below)            |

### Install FFmpeg

- **Windows**: `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Debian/Ubuntu) or equivalent

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/TankLapse.git
cd TankLapse

# (Recommended) create a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Run
python -m tanklapse
```

## Usage

1. Choose an **output folder** (a timestamped `session_…` subfolder will be created automatically).
2. Set the **capture interval**, monitor, image format and quality.
3. Choose desired **output FPS** and CRF (video quality).
4. Click **Start Capture**.
5. Work as usual – TankLapse quietly writes frames to disk.
6. Click **Stop**. If “Automatically stitch” is enabled, an MP4 is created immediately.
7. You can also click **Stitch existing frames** later on any session folder.

### Frame naming

Frames are saved as sequential zero-padded files:

```
frame_00000000.jpg
frame_00000001.jpg
frame_00000002.jpg
…
```

This guarantees correct ordering for FFmpeg.

## Project Structure

```
TankLapse/
├── tanklapse/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py          # Tkinter GUI
│   ├── capture.py      # Interval screenshot engine (disk-first)
│   └── video.py        # FFmpeg stitching helper
├── requirements.txt
├── LICENSE
└── README.md
```

## How it avoids RAM overload

Traditional screen recorders keep frames (or a rolling buffer) in memory.  
TankLapse never does that:

1. `mss` grabs the screen → PIL Image is created
2. Image is immediately written to disk as JPEG/PNG
3. Image object is discarded
4. Only a tiny counter and a few status variables stay in RAM

You can leave it running for days; memory usage stays flat.

## Roadmap / Ideas for contributors

- [ ] System tray icon + minimize-to-tray
- [ ] Global hotkeys (start/stop)
- [ ] Pause when user is idle
- [ ] Region / window capture (not just full monitor)
- [ ] Optional audio track
- [ ] Progress bar during stitching
- [ ] Dark mode
- [ ] Pre-built binaries (PyInstaller / Nuitka)

Pull requests are very welcome!

## License

MIT – see [LICENSE](LICENSE).

---

Made for long sessions and peace of mind.  
Happy timelapsing! 🎬
