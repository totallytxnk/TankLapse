"""
Video stitching module for TankLapse.

Uses system FFmpeg to turn sequential image frames into a high-framerate MP4.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def stitch_frames(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    image_format: str = "jpg",
    crf: int = 23,
    preset: str = "medium",
    on_progress: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    Stitch sequential frames into an MP4 using FFmpeg.

    Frames are expected to be named frame_00000000.jpg, frame_00000001.jpg, ...
    """
    if not check_ffmpeg():
        raise RuntimeError(
            "FFmpeg not found. Please install FFmpeg and ensure it is on your PATH.\n"
            "  Windows : https://ffmpeg.org/download.html or `winget install ffmpeg`\n"
            "  macOS   : `brew install ffmpeg`\n"
            "  Linux   : `sudo apt install ffmpeg` (or equivalent)"
        )

    frames_dir = Path(frames_dir)
    output_path = Path(output_path)

    # Detect actual extension used
    ext = image_format.lower()
    if ext == "jpeg":
        ext = "jpg"

    pattern = str(frames_dir / f"frame_%08d.{ext}")

    # Prefer libx264 for maximum compatibility
    cmd = [
        "ffmpeg",
        "-y",                          # overwrite
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",         # compatibility
        "-movflags", "+faststart",     # web-friendly
        str(output_path),
    ]

    if on_progress:
        on_progress(f"Running: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )

    # Stream output for progress feedback
    if process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line and on_progress:
                on_progress(line)

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg failed with exit code {return_code}")

    if not output_path.exists():
        raise RuntimeError("FFmpeg finished but output file was not created")

    return output_path


def estimate_video_duration(frame_count: int, fps: int) -> float:
    """Return expected video length in seconds."""
    if fps <= 0:
        return 0.0
    return frame_count / fps