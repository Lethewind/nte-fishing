"""Window discovery and background-capable frame capture."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading

import cv2
import mss
import numpy as np
import win32gui
import win32ui
from windows_capture import Frame, InternalCaptureControl, WindowsCapture as _WGCapture

from src import padinput
from src.settings import GameProfile, settings
from src.window_locator import WindowLocator, WindowMatch

log = logging.getLogger(__name__)

_PW_RENDERFULLCONTENT = 0x00000002


class WindowCapture:
    def __init__(
        self,
        locator: WindowLocator | None = None,
    ):
        self.locator = locator or WindowLocator()
        self.match: WindowMatch | None = None
        self.hwnd = 0
        self.profile: GameProfile | None = None
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._sct = mss.MSS()
        self.refresh_hwnd()

    @property
    def active_profile(self) -> GameProfile | None:
        return self.profile

    def is_window_found(self) -> bool:
        return self.match is not None and self.locator.is_valid(self.match)

    def refresh_hwnd(self) -> WindowMatch | None:
        match = self.locator.find()
        if match is None:
            self._clear_target()
            return None
        changed = match.hwnd != self.hwnd
        if changed:
            padinput.PAD_INPUT.reset()
        self.match = match
        self.hwnd = match.hwnd
        self.profile = match.profile
        padinput.HWND = self.hwnd
        if changed:
            with self._lock:
                self._latest_frame = None
            self._start_wgc()
        return match

    def _clear_target(self) -> None:
        padinput.PAD_INPUT.reset()
        self.match = None
        self.profile = None
        self.hwnd = 0
        padinput.HWND = 0
        with self._lock:
            self._latest_frame = None

    def _ensure_target(self) -> bool:
        if self.is_window_found():
            return True
        return self.refresh_hwnd() is not None

    def get_frame(
        self, region: tuple[float, float, float, float] | None = None
    ) -> np.ndarray | None:
        if not self._ensure_target():
            return None

        with self._lock:
            full_frame = self._latest_frame
        frame = full_frame
        if frame is not None and frame.mean() < 5:
            frame = None
        if frame is None:
            frame = self._print_window_capture()
        if frame is None:
            frame = self._mss_capture()
        if frame is None:
            return frame
        return self.crop_frame(frame, region)

    @staticmethod
    def crop_frame(
        frame: np.ndarray | None,
        region: tuple[float, float, float, float] | None,
    ) -> np.ndarray | None:
        if frame is None or region is None:
            return frame
        height, width = frame.shape[:2]
        x1, y1 = int(region[0] * width), int(region[1] * height)
        x2, y2 = int(region[2] * width), int(region[3] * height)
        return frame[y1:y2, x1:x2]

    def _start_wgc(self) -> None:
        target_hwnd = self.hwnd
        if not target_hwnd:
            return
        try:
            capture = _WGCapture(
                cursor_capture=False,
                draw_border=False,
                window_hwnd=target_hwnd,
            )

            @capture.event
            def on_frame_arrived(frame: Frame, _control: InternalCaptureControl):
                if self.hwnd != target_hwnd:
                    return
                try:
                    bgr = frame.frame_buffer[:, :, :3].copy()
                    rect = win32gui.GetClientRect(target_hwnd)
                    width, height = rect[2], rect[3]
                    if width > 0 and height > 0 and (bgr.shape[1] != width or bgr.shape[0] != height):
                        bgr = cv2.resize(bgr, (width, height), interpolation=cv2.INTER_LINEAR)
                    with self._lock:
                        self._latest_frame = bgr
                except Exception as exc:
                    log.debug("WGC frame error: %s", exc)

            @capture.event
            def on_closed():
                if self.hwnd == target_hwnd:
                    with self._lock:
                        self._latest_frame = None

            def run_capture() -> None:
                try:
                    capture.start()
                except Exception as exc:
                    log.debug("WGC start failed: %s", exc)

            threading.Thread(target=run_capture, daemon=True, name="wgc-capture").start()
        except Exception as exc:
            log.debug("WGC unavailable: %s", exc)

    def _print_window_capture(self) -> np.ndarray | None:
        try:
            rect = win32gui.GetClientRect(self.hwnd)
            width, height = rect[2], rect[3]
            if width <= 0 or height <= 0:
                return None
            window_dc = win32gui.GetDC(self.hwnd)
            source_dc = win32ui.CreateDCFromHandle(window_dc)
            memory_dc = source_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source_dc, width, height)
            memory_dc.SelectObject(bitmap)
            ctypes.windll.user32.PrintWindow(
                self.hwnd, memory_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT
            )
            raw = bitmap.GetBitmapBits(True)
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))[:, :, :3].copy()
            win32gui.DeleteObject(bitmap.GetHandle())
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, window_dc)
            return None if frame.mean() < 5 else frame
        except Exception as exc:
            log.debug("PrintWindow capture failed: %s", exc)
            return None

    def _mss_capture(self) -> np.ndarray | None:
        try:
            rect = win32gui.GetClientRect(self.hwnd)
            width, height = rect[2], rect[3]
            if width <= 0 or height <= 0:
                return None
            point = ctypes.wintypes.POINT(0, 0)
            ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(point))
            monitor = {"left": point.x, "top": point.y, "width": width, "height": height}
            return np.array(self._sct.grab(monitor))[:, :, :3]
        except Exception as exc:
            log.debug("mss capture failed: %s", exc)
            return None
