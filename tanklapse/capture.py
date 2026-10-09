"""
Capture engine for TankLapse.

Writes every frame directly to disk as a lightweight image file.
No frames are kept in RAM, enabling truly infinite-duration recordings.
"""

from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Callable, Optional

import mss
from PIL import Image


class CaptureEngine:
    """Interval screenshot capture that streams frames straight to disk."""

    def __init__(
        self,
        output_dir: Path,
        interval: float = 1.0,
        monitor: int = 1,
        image_format: str = "JPEG",
        jpeg_quality: int = 85,
        on_frame: Optional[Callable[[int, Path], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        self.output_dir = Path(output_dir)
        self.interval = max(0.1, float(interval))
        self.monitor = monitor
        self.image_format = image_format.upper()
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.on_frame = on_frame
        self.on_error = on_error

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_count = 0
        self._start_time: Optional[float] = None
        self._running = False

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @property
    def file_extension(self) -> str:
        """Extension actually used on disk (.jpg not .jpeg)."""
        if self.image_format == "JPEG":
            return "jpg"
        return self.image_format.lower()

    def start(self) -> None:
        if self._running:
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self._frame_count = 0
        self._start_time = time.time()
        self._running = True

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2.0)
        self._running = False

    def _capture_loop(self) -> None:
        try:
            with mss.mss() as sct:
                mon = (
                    sct.monitors[self.monitor]
                    if self.monitor < len(sct.monitors)
                    else sct.monitors[1]
                )
                ext = self.file_extension

                while not self._stop_event.is_set():
                    loop_start = time.perf_counter()

                    try:
                        # Ensure directory still exists (user may have deleted it)
                        self.output_dir.mkdir(parents=True, exist_ok=True)

                        sct_img = sct.grab(mon)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                        filename = f"frame_{self._frame_count:08d}.{ext}"
                        filepath = self.output_dir / filename

                        if self.image_format == "JPEG":
                            img.save(filepath, "JPEG", quality=self.jpeg_quality, optimize=True)
                        else:
                            # PNG: skip optimize on large frames (much faster, same size-ish)
                            img.save(filepath, "PNG")

                        self._frame_count += 1

                        if self.on_frame:
                            self.on_frame(self._frame_count, filepath)

                    except Exception as exc:
                        if self.on_error:
                            self.on_error(exc)

                    # Precise interval — never pass a negative sleep
                    elapsed = time.perf_counter() - loop_start
                    sleep_time = self.interval - elapsed
                    if sleep_time > 0.001:
                        end_wait = time.perf_counter() + sleep_time
                        while not self._stop_event.is_set():
                            remaining = end_wait - time.perf_counter()
                            if remaining <= 0:
                                break
                            time.sleep(min(0.05, remaining))

        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
        finally:
            self._running = False

    @staticmethod
    def list_monitors() -> list[dict]:
        """Return a list of available monitors for UI selection."""
        with mss.mss() as sct:
            return [
                {
                    "index": i,
                    "left": m["left"],
                    "top": m["top"],
                    "width": m["width"],
                    "height": m["height"],
                }
                for i, m in enumerate(sct.monitors)
                if i > 0
            ]
