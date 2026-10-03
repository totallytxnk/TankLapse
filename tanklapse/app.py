#!/usr/bin/env python3
"""
TankLapse – Lightweight interval screenshot capture & timelapse utility.

Frames are written directly to disk to support infinite-duration recordings
without RAM overload. On completion they are automatically stitched into
a high-framerate MP4 via FFmpeg.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .capture import CaptureEngine
from .video import check_ffmpeg, stitch_frames, estimate_video_duration


class TankLapseApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("TankLapse")
        self.geometry("520x620")
        self.minsize(480, 560)
        self.resizable(True, True)

        # State
        self.capture: Optional[CaptureEngine] = None
        self.frames_dir: Optional[Path] = None
        self._status_after_id: Optional[str] = None

        self._build_ui()
        self._refresh_monitors()
        self._update_ffmpeg_status()

        # Default output folder next to the script / cwd
        default_dir = Path.cwd() / "tanklapse_captures"
        self.output_var.set(str(default_dir))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Header ---
        header = ttk.Label(
            main,
            text="TankLapse",
            font=("Segoe UI", 18, "bold"),
        )
        header.pack(pady=(0, 2))
        sub = ttk.Label(
            main,
            text="Infinite-duration screenshot timelapse • frames go straight to disk",
            font=("Segoe UI", 9),
            foreground="#555",
        )
        sub.pack(pady=(0, 12))

        # --- Output folder ---
        folder_frame = ttk.LabelFrame(main, text="Output folder", padding=8)
        folder_frame.pack(fill=tk.X, **pad)

        self.output_var = tk.StringVar()
        entry = ttk.Entry(folder_frame, textvariable=self.output_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(folder_frame, text="Browse…", command=self._browse_folder).pack(side=tk.RIGHT)

        # --- Capture settings ---
        settings = ttk.LabelFrame(main, text="Capture settings", padding=8)
        settings.pack(fill=tk.X, **pad)

        # Interval
        row1 = ttk.Frame(settings)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Interval (seconds):").pack(side=tk.LEFT)
        self.interval_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(
            row1,
            from_=0.2,
            to=3600,
            increment=0.5,
            textvariable=self.interval_var,
            width=8,
        ).pack(side=tk.RIGHT)

        # Monitor
        row2 = ttk.Frame(settings)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Monitor:").pack(side=tk.LEFT)
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(
            row2, textvariable=self.monitor_var, state="readonly", width=28
        )
        self.monitor_combo.pack(side=tk.RIGHT)

        # Format & quality
        row3 = ttk.Frame(settings)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Image format:").pack(side=tk.LEFT)
        self.format_var = tk.StringVar(value="JPEG")
        ttk.Combobox(
            row3,
            textvariable=self.format_var,
            values=["JPEG", "PNG"],
            state="readonly",
            width=8,
        ).pack(side=tk.RIGHT)

        row4 = ttk.Frame(settings)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="JPEG quality (1-100):").pack(side=tk.LEFT)
        self.quality_var = tk.IntVar(value=85)
        ttk.Spinbox(
            row4,
            from_=1,
            to=100,
            textvariable=self.quality_var,
            width=8,
        ).pack(side=tk.RIGHT)

        # --- Video settings ---
        video = ttk.LabelFrame(main, text="Timelapse video settings", padding=8)
        video.pack(fill=tk.X, **pad)

        rowv1 = ttk.Frame(video)
        rowv1.pack(fill=tk.X, pady=2)
        ttk.Label(rowv1, text="Output FPS:").pack(side=tk.LEFT)
        self.fps_var = tk.IntVar(value=30)
        ttk.Spinbox(
            rowv1,
            from_=1,
            to=120,
            textvariable=self.fps_var,
            width=8,
        ).pack(side=tk.RIGHT)

        rowv2 = ttk.Frame(video)
        rowv2.pack(fill=tk.X, pady=2)
        ttk.Label(rowv2, text="CRF (quality, lower = better):").pack(side=tk.LEFT)
        self.crf_var = tk.IntVar(value=23)
        ttk.Spinbox(
            rowv2,
            from_=15,
            to=35,
            textvariable=self.crf_var,
            width=8,
        ).pack(side=tk.RIGHT)

        self.auto_stitch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            video,
            text="Automatically stitch MP4 when capture stops",
            variable=self.auto_stitch_var,
        ).pack(anchor=tk.W, pady=(6, 0))

        # --- Controls ---
        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, pady=12)

        self.start_btn = ttk.Button(
            controls, text="▶  Start Capture", command=self._start_capture
        )
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.stop_btn = ttk.Button(
            controls, text="⏹  Stop", command=self._stop_capture, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

        # Manual stitch button
        self.stitch_btn = ttk.Button(
            main, text="🎬  Stitch existing frames into MP4", command=self._manual_stitch
        )
        self.stitch_btn.pack(fill=tk.X, pady=(0, 8))

        # --- Status ---
        status_frame = ttk.LabelFrame(main, text="Status", padding=8)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            wraplength=460,
        ).pack(anchor=tk.W)

        self.frames_var = tk.StringVar(value="Frames: 0")
        ttk.Label(status_frame, textvariable=self.frames_var).pack(anchor=tk.W, pady=(4, 0))

        self.elapsed_var = tk.StringVar(value="Elapsed: 00:00:00")
        ttk.Label(status_frame, textvariable=self.elapsed_var).pack(anchor=tk.W)

        self.ffmpeg_var = tk.StringVar()
        ttk.Label(
            status_frame,
            textvariable=self.ffmpeg_var,
            foreground="#666",
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W, pady=(8, 0))

        # Progress / log area
        self.log = tk.Text(status_frame, height=6, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 8))
        self.log.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    # ------------------------------------------------------------------ Helpers
    def _log(self, msg: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_var.set(path)

    def _refresh_monitors(self) -> None:
        try:
            monitors = CaptureEngine.list_monitors()
            values = []
            for m in monitors:
                label = f"Monitor {m['index']}  ({m['width']}×{m['height']})"
                values.append(label)
            self.monitor_combo["values"] = values
            if values:
                self.monitor_combo.current(0)
        except Exception as exc:
            self._log(f"Could not list monitors: {exc}")
            self.monitor_combo["values"] = ["Monitor 1"]
            self.monitor_combo.current(0)

    def _update_ffmpeg_status(self) -> None:
        if check_ffmpeg():
            self.ffmpeg_var.set("✓ FFmpeg found – video stitching available")
        else:
            self.ffmpeg_var.set(
                "⚠ FFmpeg not found – install it to enable MP4 export "
                "(see README)"
            )

    def _get_monitor_index(self) -> int:
        sel = self.monitor_var.get()
        try:
            # "Monitor 1  (1920×1080)" → 1
            return int(sel.split()[1])
        except Exception:
            return 1

    # ------------------------------------------------------------------ Capture
    def _start_capture(self) -> None:
        out = Path(self.output_var.get()).expanduser()
        if not out:
            messagebox.showerror("Error", "Please choose an output folder.")
            return

        # Create a unique session subfolder so multiple runs don't mix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.frames_dir = out / f"session_{timestamp}"
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        interval = self.interval_var.get()
        fmt = self.format_var.get()
        quality = self.quality_var.get()
        monitor = self._get_monitor_index()

        self.capture = CaptureEngine(
            output_dir=self.frames_dir,
            interval=interval,
            monitor=monitor,
            image_format=fmt,
            jpeg_quality=quality,
            on_frame=self._on_frame,
            on_error=self._on_capture_error,
        )

        self.capture.start()

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.stitch_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"Capturing → {self.frames_dir}")
        self._log(f"Started capture @ {interval}s interval → {self.frames_dir}")
        self._poll_status()

    def _stop_capture(self) -> None:
        if not self.capture:
            return

        self.capture.stop()
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.stitch_btn.configure(state=tk.NORMAL)

        frames = self.capture.frame_count
        elapsed = self.capture.elapsed_seconds
        self.status_var.set(f"Stopped – {frames} frames captured")
        self._log(f"Stopped. {frames} frames in {timedelta(seconds=int(elapsed))}")

        if self._status_after_id:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None

        if self.auto_stitch_var.get() and frames > 0:
            self._do_stitch()

    def _on_frame(self, count: int, path: Path) -> None:
        # Called from capture thread – schedule UI update on main thread
        self.after(0, lambda: self.frames_var.set(f"Frames: {count}"))

    def _on_capture_error(self, exc: Exception) -> None:
        self.after(0, lambda: self._log(f"Capture error: {exc}"))

    def _poll_status(self) -> None:
        if self.capture and self.capture.is_running:
            elapsed = int(self.capture.elapsed_seconds)
            self.elapsed_var.set(f"Elapsed: {timedelta(seconds=elapsed)}")
            self._status_after_id = self.after(500, self._poll_status)

    # ------------------------------------------------------------------ Stitch
    def _manual_stitch(self) -> None:
        if self.frames_dir and self.frames_dir.exists():
            self._do_stitch()
        else:
            # Let user pick a folder that already contains frames
            folder = filedialog.askdirectory(title="Select folder containing frame_*.jpg/png")
            if folder:
                self.frames_dir = Path(folder)
                self._do_stitch()

    def _do_stitch(self) -> None:
        if not self.frames_dir or not self.frames_dir.exists():
            messagebox.showerror("Error", "No frames folder selected.")
            return

        # Count frames
        frames = sorted(self.frames_dir.glob("frame_*.*"))
        if not frames:
            messagebox.showerror("Error", "No frame_*.jpg/png files found in the folder.")
            return

        fps = self.fps_var.get()
        crf = self.crf_var.get()
        fmt = self.format_var.get().lower()
        if fmt == "jpeg":
            fmt = "jpg"

        out_name = f"timelapse_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fps}fps.mp4"
        output_path = self.frames_dir.parent / out_name

        duration = estimate_video_duration(len(frames), fps)
        self.status_var.set(f"Stitching {len(frames)} frames → {fps} FPS MP4…")
        self._log(f"Stitching {len(frames)} frames @ {fps} fps (≈{duration:.1f}s video)")
        self.start_btn.configure(state=tk.DISABLED)
        self.stitch_btn.configure(state=tk.DISABLED)

        def worker():
            try:
                result = stitch_frames(
                    frames_dir=self.frames_dir,
                    output_path=output_path,
                    fps=fps,
                    image_format=fmt,
                    crf=crf,
                    on_progress=lambda line: self.after(0, lambda: self._log(line)),
                )
                self.after(0, lambda: self._stitch_done(result, len(frames), duration))
            except Exception as exc:
                self.after(0, lambda: self._stitch_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _stitch_done(self, path: Path, frame_count: int, duration: float) -> None:
        self.status_var.set(f"Done! Video saved → {path.name}")
        self._log(f"✓ Video ready: {path}  ({frame_count} frames, {duration:.1f}s)")
        self.start_btn.configure(state=tk.NORMAL)
        self.stitch_btn.configure(state=tk.NORMAL)
        messagebox.showinfo(
            "Timelapse ready",
            f"Video created successfully!\n\n{path}\n\n"
            f"{frame_count} frames → {duration:.1f} seconds @ {self.fps_var.get()} FPS",
        )

    def _stitch_failed(self, exc: Exception) -> None:
        self.status_var.set("Stitching failed")
        self._log(f"✗ Stitch error: {exc}")
        self.start_btn.configure(state=tk.NORMAL)
        self.stitch_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Stitching failed", str(exc))


def main() -> None:
    app = TankLapseApp()
    app.mainloop()


if __name__ == "__main__":
    main()