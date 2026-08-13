from pathlib import Path
from unittest.mock import patch

import numpy as np

from src import padinput
from src.capture import WindowCapture
from src.settings import GameProfile
from src.window_locator import WindowLocator


def test_window_not_found_returns_zero_hwnd():
    profile = GameProfile("missing", ("不存在的窗口",), Path("missing.png"))
    with patch("win32gui.EnumWindows"):
        capture = WindowCapture(WindowLocator((profile,)))
    assert capture.hwnd == 0
    assert not capture.is_window_found()


def test_capture_publishes_and_clears_global_hwnd():
    profile = GameProfile("nte", ("NTE",), Path("nte.png"))

    def enumerate_window(callback, extra):
        with patch("win32gui.IsWindowVisible", return_value=True), patch(
            "win32gui.GetWindowText",
            return_value="NTE",
        ):
            callback(12345, extra)

    with patch("win32gui.EnumWindows", side_effect=enumerate_window), patch.object(
        WindowCapture,
        "_start_wgc",
    ), patch.object(padinput.PAD_INPUT, "reset"):
        capture = WindowCapture(WindowLocator((profile,)))

    assert padinput.get_hwnd() == 12345

    with patch.object(padinput.PAD_INPUT, "reset"):
        capture._clear_target()

    assert padinput.get_hwnd() == 0


def test_locator_supports_simplified_and_traditional_titles():
    profile = GameProfile("yihuan", ("异环", "異環"), __import__("pathlib").Path("yihuan.png"))

    def enumerate_windows(callback, extra):
        with patch("win32gui.IsWindowVisible", return_value=True), patch(
            "win32gui.GetWindowText", return_value="異環"
        ):
            callback(12345, extra)

    with patch("win32gui.EnumWindows", side_effect=enumerate_windows):
        match = WindowLocator((profile,)).find()
    assert match is not None
    assert match.hwnd == 12345
    assert match.profile.lang == "yihuan"


def test_locator_prefers_exact_title_over_partial_match():
    profile = GameProfile("nte", ("NTE",), Path("nte.png"))
    titles = {
        10001: "nte-fishing - Visual Studio Code",
        10002: "NTE",
    }

    def enumerate_windows(callback, extra):
        with patch("win32gui.IsWindowVisible", return_value=True), patch(
            "win32gui.GetWindowText", side_effect=lambda hwnd: titles[hwnd]
        ):
            for hwnd in titles:
                callback(hwnd, extra)

    with patch("win32gui.EnumWindows", side_effect=enumerate_windows):
        match = WindowLocator((profile,)).find()

    assert match is not None
    assert match.hwnd == 10002
    assert match.title == "NTE"


def test_get_frame_returns_correct_shape():
    image = np.zeros((1440, 2304, 3), dtype=np.uint8)

    def enumerate_windows(callback, extra):
        with patch("win32gui.IsWindowVisible", return_value=True), patch(
            "win32gui.GetWindowText", return_value="NTE"
        ):
            callback(12345, extra)

    with patch("win32gui.EnumWindows", side_effect=enumerate_windows), patch(
        "win32gui.IsWindow", return_value=True
    ), patch("win32gui.GetClientRect", return_value=(0, 0, 2304, 1440)), patch(
        "src.capture.WindowCapture._mss_capture", return_value=image
    ):
        capture = WindowCapture(WindowLocator((GameProfile("nte", ("NTE",), Path("nte.png")),)))
        frame = capture.get_frame(region=(0.0, 0.0, 0.5, 0.5))
    assert frame is not None
    assert frame.shape == (720, 1152, 3)


def test_get_frame_crops_cached_full_frame_only_once():
    image = np.full((1440, 2304, 3), 50, dtype=np.uint8)

    def enumerate_windows(callback, extra):
        with patch("win32gui.IsWindowVisible", return_value=True), patch(
            "win32gui.GetWindowText", return_value="NTE"
        ):
            callback(12345, extra)

    with patch("win32gui.EnumWindows", side_effect=enumerate_windows), patch(
        "win32gui.IsWindow", return_value=True
    ), patch("win32gui.GetClientRect", return_value=(0, 0, 2304, 1440)):
        capture = WindowCapture(WindowLocator((GameProfile("nte", ("NTE",), Path("nte.png")),)))
        capture._latest_frame = image
        with patch.object(capture, "_mss_capture") as fallback:
            frame = capture.get_frame(region=(0.0, 0.0, 0.5, 0.5))

    assert frame is not None
    assert frame.shape == (720, 1152, 3)
    fallback.assert_not_called()
