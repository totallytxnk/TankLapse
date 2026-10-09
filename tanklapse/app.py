#!/usr/bin/env python3
"""
TankLapse – Lightweight interval screenshot capture & timelapse utility.

Frames are written directly to disk to support infinite-duration recordings
without RAM overload. On completion they are automatically stitched into
a high-framerate MP4 via FFmpeg.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .capture import CaptureEngine
from .video import check_ffmpeg, stitch_frames, estimate_video_duration


def _truncate_path(path: str, max_len: int = 42) -> str:
    """Middle-ellipsis truncation for long paths."""
    if len(path) <= max_len:
        return path
    keep = (max_len - 3) // 2
    return path[:keep] + "..." + path[-keep:]


class TankLapseApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("TankLapse")
        self.geometry("420x480")
        self.minsize(380, 420)
        self.resizable(True, True)

        # State
        self.capture: Optional[CaptureEngine] = None
        self.frames_dir: Optional[Path] = None
        self._status_after_id: Optional[str] = None
        self._full_output_path = ""

        # Hardcoded defaults (Advanced overrides these)
        self.format_var = tk.StringVar(value="JPEG")
        self.quality_var = tk.IntVar(value=85)

        self._build_ui()
        self._refresh_monitors()
        self._update_ffmpeg_status()

        # Prefer a writable user folder (cwd can be System32 when launched from Explorer)
        videos = Path.home() / "Videos" / "TankLapse"
        docs = Path.home() / "Documents" / "TankLapse"
        default_dir = videos if (Path.home() / "Videos").exists() else docs
        self._set_output(str(default_dir))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=(10, 8))
        main.pack(fill=tk.BOTH, expand=True)

        # --- Output ---
        out_row = ttk.Frame(main)
        out_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(out_row, text="Output", width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.output_display = tk.StringVar()
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_display, state="readonly")
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(out_row, text="…", width=3, command=self._browse_folder).pack(side=tk.RIGHT)

        # --- Capture row ---
        cap = ttk.Frame(main)
        cap.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(cap, text="Interval (s)", width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.interval_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(cap, from_=0.2, to=3600, increment=0.5,
                    textvariable=self.interval_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(cap, text="Monitor").pack(side=tk.LEFT)
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(cap, textvariable=self.monitor_var,
                                          state="readonly", width=18)
        self.monitor_combo.pack(side=tk.LEFT, padx=(4, 0))

        # --- Video row ---
        vid = ttk.Frame(main)
        vid.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(vid, text="FPS", width=9, anchor=tk.W).pack(side=tk.LEFT)
        self.fps_var = tk.IntVar(value=30)
        ttk.Spinbox(vid, from_=1, to=120, textvariable=self.fps_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(vid, text="CRF").pack(side=tk.LEFT)
        self.crf_var = tk.IntVar(value=23)
        ttk.Spinbox(vid, from_=15, to=35, textvariable=self.crf_var, width=6).pack(side=tk.LEFT, padx=(4, 12))

        self.auto_stitch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(vid, text="Auto-stitch", variable=self.auto_stitch_var).pack(side=tk.LEFT)

        # --- Advanced (collapsed) ---
        self.adv_visible = tk.BooleanVar(value=False)
        self.adv_toggle = ttk.Checkbutton(
            main, text="Advanced", variable=self.adv_visible,
            command=self._toggle_advanced
        )
        self.adv_toggle.pack(anchor=tk.W, pady=(2, 0))

        self.adv_frame = ttk.Frame(main)

        ttk.Label(self.adv_frame, text="Format", width=9, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Combobox(self.adv_frame, textvariable=self.format_var,
                     values=["JPEG", "PNG"], state="readonly", width=6).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(self.adv_frame, text="Quality").pack(side=tk.LEFT)
        ttk.Spinbox(self.adv_frame, from_=1, to=100, textvariable=self.quality_var, width=6).pack(side=tk.LEFT, padx=(4, 0))

        # --- Actions ---
        self.actions = ttk.Frame(main)
        self.actions.pack(fill=tk.X, pady=(8, 6))

        self.action_btn = ttk.Button(self.actions, text="Start", command=self._toggle_capture)
        self.action_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.stitch_btn = ttk.Button(self.actions, text="Stitch", command=self._manual_stitch, width=10)
        self.stitch_btn.pack(side=tk.RIGHT)

        # --- Status ---
        status = ttk.Frame(main)
        status.pack(fill=tk.BOTH, expand=True)

        info = ttk.Frame(status)
        info.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(info, textvariable=self.status_var).pack(side=tk.LEFT)

        self.frames_var = tk.StringVar(value="0 frames")
        ttk.Label(info, textvariable=self.frames_var).pack(side=tk.RIGHT)

        self.elapsed_var = tk.StringVar(value="00:00:00")
        ttk.Label(info, textvariable=self.elapsed_var, foreground="#666").pack(side=tk.RIGHT, padx=(0, 10))

        self.ffmpeg_var = tk.StringVar()
        ttk.Label(status, textvariable=self.ffmpeg_var, foreground="#888",
                  font=("Segoe UI", 8)).pack(anchor=tk.W, pady=(2, 2))

        self.log = tk.Text(status, height=8, wrap=tk.WORD, state=tk.DISABLED,
                           font=("Consolas", 8), relief=tk.FLAT,
                           background="#f5f5f5")
        self.log.pack(fill=tk.BOTH, expand=True)

    def _toggle_advanced(self) -> None:
        if self.adv_visible.get():
            self.adv_frame.pack(fill=tk.X, pady=(0, 4), after=self.adv_toggle)
        else:
            self.adv_frame.pack_forget()

    # ------------------------------------------------------------------ Helpers
    def _set_output(self, path: str) -> None:
        self._full_output_path = path
        self.output_display.set(_truncate_path(path))

    def _log(self, msg: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self._set_output(path)

    def _refresh_monitors(self) -> None:
        try:
            monitors = CaptureEngine.list_monitors()
            values = [f"{m['index']}  {m['width']}×{m['height']}" for m in monitors]
            self.monitor_combo["values"] = values
            if values:
                self.monitor_combo.current(0)
        except Exception as exc:
            self._log(f"Monitors: {exc}")
            self.monitor_combo["values"] = ["1"]
            self.monitor_combo.current(0)

    def _update_ffmpeg_status(self) -> None:
        if check_ffmpeg():
            self.ffmpeg_var.set("FFmpeg OK")
        else:
            self.ffmpeg_var.set("FFmpeg missing – install to enable stitch")

    def _get_monitor_index(self) -> int:
        sel = self.monitor_var.get()
        try:
            return int(sel.split()[0])
        except Exception:
            return 1

    # ------------------------------------------------------------------ Capture
    def _toggle_capture(self) -> None:
        if self.capture and self.capture.is_running:
            self._stop_capture()
        else:
            self._start_capture()

    def _start_capture(self) -> None:
        out = Path(self._full_output_path).expanduser()
        if not out:
            messagebox.showerror("Error", "Choose an output folder.")
            return

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

        self.action_btn.configure(text="Stop")
        self.stitch_btn.configure(state=tk.DISABLED)
        self.status_var.set("Capturing")
        self._log(f"Start  {interval}s  →  {self.frames_dir.name}")
        self._poll_status()

    def _stop_capture(self) -> None:
        if not self.capture:
            return

        self.capture.stop()
        self.action_btn.configure(text="Start")
        self.stitch_btn.configure(state=tk.NORMAL)

        frames = self.capture.frame_count
        elapsed = self.capture.elapsed_seconds
        self.status_var.set("Stopped")
        self._log(f"Stop   {frames} frames  {timedelta(seconds=int(elapsed))}")

        if self._status_after_id:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None

        if self.auto_stitch_var.get() and frames > 0:
            self._do_stitch()

    def _on_frame(self, count: int, path: Path) -> None:
        self.after(0, lambda: self.frames_var.set(f"{count} frames"))

    def _on_capture_error(self, exc: Exception) -> None:
        self.after(0, lambda: self._log(f"Error  {exc}"))

    def _poll_status(self) -> None:
        if self.capture and self.capture.is_running:
            elapsed = int(self.capture.elapsed_seconds)
            self.elapsed_var.set(str(timedelta(seconds=elapsed)))
            self._status_after_id = self.after(500, self._poll_status)

    # ------------------------------------------------------------------ Stitch
    def _manual_stitch(self) -> None:
        if self.frames_dir and self.frames_dir.exists():
            self._do_stitch()
        else:
            folder = filedialog.askdirectory(title="Frames folder")
            if folder:
                self.frames_dir = Path(folder)
                self._do_stitch()

    def _do_stitch(self) -> None:
        if not self.frames_dir or not self.frames_dir.exists():
            messagebox.showerror("Error", "No frames folder.")
            return

        frames = sorted(self.frames_dir.glob("frame_*.*"))
        if not frames:
            messagebox.showerror("Error", "No frame_*.jpg/png found.")
            return

        fps = self.fps_var.get()
        crf = self.crf_var.get()
        fmt = self.format_var.get().lower()
        if fmt == "jpeg":
            fmt = "jpg"

        out_name = f"timelapse_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fps}fps.mp4"
        output_path = self.frames_dir.parent / out_name

        duration = estimate_video_duration(len(frames), fps)
        self.status_var.set("Stitching…")
        self._log(f"Stitch {len(frames)} frames @ {fps}fps")
        self.action_btn.configure(state=tk.DISABLED)
        self.stitch_btn.configure(state=tk.DISABLED)

        def worker():
            try:
                result = stitch_frames(
                    frames_dir=self.frames_dir,
                    output_path=output_path,
                    fps=fps,
                    image_format=fmt,
                    crf=crf,
                    on_progress=lambda line: self.after(0, lambda l=line: self._log(l)),
                )
                self.after(0, lambda: self._stitch_done(result, len(frames), duration))
            except Exception as exc:
                self.after(0, lambda: self._stitch_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _stitch_done(self, path: Path, frame_count: int, duration: float) -> None:
        self.status_var.set("Done")
        self._log(f"OK     {path.name}  ({frame_count}f / {duration:.1f}s)")
        self.action_btn.configure(state=tk.NORMAL, text="Start")
        self.stitch_btn.configure(state=tk.NORMAL)

    def _stitch_failed(self, exc: Exception) -> None:
        self.status_var.set("Failed")
        self._log(f"Fail   {exc}")
        self.action_btn.configure(state=tk.NORMAL, text="Start")
        self.stitch_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Stitch failed", str(exc))


def main() -> None:
    app = TankLapseApp()
    app.mainloop()


if __name__ == "__main__":
    main()
