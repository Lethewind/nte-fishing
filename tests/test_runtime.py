from unittest.mock import Mock, patch

import numpy as np

from src.detector import ProbeTrace
from src.runtime import FishingRuntime, annotate_frame
from src.state_machine import Action


def test_capture_probe_uses_one_full_frame_for_detector():
    runtime = FishingRuntime.__new__(FishingRuntime)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    profile = object()
    runtime.capture = Mock()
    runtime.capture.get_frame.return_value = frame
    runtime.capture.is_window_found.return_value = True
    runtime.capture.active_profile = profile
    runtime.detector = Mock()
    runtime.detector.profile = profile
    probe = object()
    runtime.detector.for_frame.return_value = probe

    captured, result = runtime._capture_probe()

    assert captured is frame
    assert result is probe
    runtime.capture.get_frame.assert_called_once_with()
    runtime.detector.for_frame.assert_called_once_with(frame)


def test_capture_probe_returns_none_when_window_is_invalid():
    runtime = FishingRuntime.__new__(FishingRuntime)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    runtime.capture = Mock()
    runtime.capture.get_frame.return_value = frame
    runtime.capture.is_window_found.return_value = False
    runtime.capture.active_profile = None
    runtime.detector = Mock()
    runtime.detector.profile = None

    captured, probe = runtime._capture_probe()

    assert captured is frame
    assert probe is None
    runtime.detector.for_frame.assert_not_called()


def test_runtime_executes_escape_action():
    with patch("src.runtime.PAD_INPUT.tap") as tap:
        FishingRuntime._execute(Action.PRESS_ESCAPE)
    tap.assert_called_once_with("escape")


def test_debug_uses_full_frame_probe_coordinates():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    trace = ProbeTrace(
        bar_checked=True,
        bar_visible=True,
        fish_area_checked=True,
        raw_segments=((60, 80),),
        fish_left=60,
        fish_right=80,
    )

    rendered = annotate_frame(frame, trace, "FISHING", "FISHING")

    assert rendered.shape == (540, 1280, 3)
