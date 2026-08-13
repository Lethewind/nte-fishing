from pathlib import Path

import cv2
import numpy as np

from src.detector import StateDetector, TemplateMatch
from src.settings import settings
from src.types import SliderDirection


HOOK_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "hook.png"
MARKER_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "marker_template.png"


def frame_with_blue_bar() -> np.ndarray:
    hsv = np.zeros((600, 1000, 3), dtype=np.uint8)
    hsv[30:70, 350:650] = (82, 220, 220)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def frame_with_fishing_bar() -> np.ndarray:
    frame = frame_with_blue_bar()
    marker = cv2.imread(str(MARKER_TEMPLATE), cv2.IMREAD_GRAYSCALE)
    assert marker is not None
    frame[40:62, 500:505] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return frame


def frame_with_hook() -> np.ndarray:
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    hook = cv2.imread(str(HOOK_TEMPLATE), cv2.IMREAD_COLOR)
    assert hook is not None
    frame[492:564, 891:969] = hook
    return frame


def test_probe_detects_hook_only_when_requested():
    probe = StateDetector().for_frame(frame_with_hook())

    assert probe.detect_hook()
    assert probe.trace.hook_checked
    assert probe.trace.hook_visible
    assert not probe.trace.result_checked


def test_blue_hook_roi_does_not_match_white_hook_pattern():
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    hsv = np.zeros((78, 80, 3), dtype=np.uint8)
    hsv[:] = (82, 220, 220)
    frame[492:570, 890:970] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    assert not StateDetector().for_frame(frame).detect_hook()


def test_experience_bar_is_not_a_bar_candidate():
    hsv = np.zeros((600, 1000, 3), dtype=np.uint8)
    hsv[30:65, 350:650] = (165, 210, 245)
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    assert not StateDetector().for_frame(frame).detect_bar()


def test_fish_segments_exist_before_marker_and_merge_after_marker(monkeypatch):
    detector = StateDetector()
    frame = frame_with_blue_bar()
    frame[30:70, 500:505] = 0
    marker = TemplateMatch(500, 40, 505, 62, 1.0)
    monkeypatch.setattr(detector, "_find_marker_tmpl", lambda _frame: marker)
    probe = detector.for_frame(frame)

    assert probe.detect_bar()
    assert probe.detect_fish_area()
    assert probe.trace.raw_segments == ((350, 499), (505, 649))
    assert not probe.trace.marker_checked

    assert probe.detect_marker()
    assert probe.resolve_slider() is SliderDirection.NEUTRAL
    assert (probe.trace.fish_left, probe.trace.fish_right) == (350, 649)
    assert probe.trace.player_x == marker.center_x
    assert probe.trace.merge_limit == 10.0


def test_real_fishing_frame_returns_complete_single_frame_evidence():
    probe = StateDetector().for_frame(frame_with_fishing_bar())

    assert probe.detect_bar()
    assert probe.detect_fish_area()
    assert probe.detect_marker()
    assert probe.resolve_slider() is SliderDirection.NEUTRAL
    assert probe.trace.fish_left == 350
    assert probe.trace.fish_right == 649
    assert probe.trace.marker_match is not None


def test_marker_outside_fish_does_not_expand_fish_area(monkeypatch):
    detector = StateDetector()
    marker = TemplateMatch(300, 40, 305, 62, 1.0)
    monkeypatch.setattr(detector, "_find_marker_tmpl", lambda _frame: marker)
    probe = detector.for_frame(frame_with_blue_bar())

    assert probe.detect_bar()
    assert probe.detect_fish_area()
    assert probe.detect_marker()
    assert probe.resolve_slider() is SliderDirection.RIGHT
    assert (probe.trace.fish_left, probe.trace.fish_right) == (350, 649)


def test_direction_uses_merged_bounds_and_raw_marker_center():
    detector = StateDetector()
    assert detector._direction_from_positions(100, 200, 0) is SliderDirection.RIGHT
    assert detector._direction_from_positions(100, 200, 350) is SliderDirection.LEFT

    max_dist = (200 - 100) * settings.slider_max_dist_ratio
    assert detector._direction_from_positions(
        100,
        200,
        int(100 + max_dist - 1),
    ) is SliderDirection.RIGHT
    assert detector._direction_from_positions(
        100,
        200,
        int(100 + max_dist + 1),
    ) is SliderDirection.NEUTRAL
    assert detector._direction_from_positions(
        100,
        200,
        int(200 - max_dist + 1),
    ) is SliderDirection.LEFT


def test_gap_below_twice_marker_width_is_merged():
    segments = [(100, 149), (159, 209)]
    assert StateDetector._merge_segments(segments, 10.0) == [(100, 209)]


def test_gap_at_twice_marker_width_is_not_merged():
    segments = [(100, 139), (150, 219)]
    assert StateDetector._merge_segments(segments, 10.0) == segments


def test_all_small_gaps_are_merged():
    segments = [(20, 49), (53, 79), (88, 109), (115, 169)]
    assert StateDetector._merge_segments(segments, 10.0) == [(20, 169)]


def test_each_frame_has_independent_probe_trace():
    detector = StateDetector()
    first = detector.for_frame(frame_with_blue_bar())
    second = detector.for_frame(np.zeros((600, 1000, 3), dtype=np.uint8))

    assert first.detect_bar()
    assert not second.detect_bar()
    assert first.trace is not second.trace
    assert not second.trace.fish_area_checked


def test_result_detection_uses_configured_roi(monkeypatch):
    detector = StateDetector()
    detector._result_template = np.zeros((2, 2), dtype=np.uint8)
    regions = []

    def match_template(region, _template, _method):
        regions.append(region.shape)
        return np.zeros((1, 1), dtype=np.float32)

    monkeypatch.setattr(cv2, "matchTemplate", match_template)
    monkeypatch.setattr(cv2, "minMaxLoc", lambda _result: (0.0, 0.0, 0.0, (0, 0)))
    probe = detector.for_frame(np.zeros((100, 200, 3), dtype=np.uint8))

    assert not probe.detect_result()
    assert probe.trace.result_score == 0.0
    expected_height = int(100 * settings.result_search_y_end) - int(
        100 * settings.result_search_y_start
    )
    expected_width = int(200 * settings.result_search_x_end) - int(
        200 * settings.result_search_x_start
    )
    assert regions[0] == (expected_height, expected_width)


def test_result_match_returns_full_frame_bounds_and_best_score(monkeypatch):
    detector = StateDetector()
    detector._result_template = np.zeros((10, 20), dtype=np.uint8)
    scores = iter([0.1, 0.2, 0.3, 0.4, 0.5, 0.9, 0.6, 0.5, 0.4, 0.3, 0.2])
    monkeypatch.setattr(
        cv2,
        "matchTemplate",
        lambda *_args, **_kwargs: np.zeros((1, 1), dtype=np.float32),
    )
    monkeypatch.setattr(
        cv2,
        "minMaxLoc",
        lambda _result: (0.0, next(scores), (0, 0), (10, 5)),
    )
    probe = detector.for_frame(np.zeros((1000, 2000, 3), dtype=np.uint8))

    assert probe.detect_result()
    match = probe.trace.result_match
    assert match is not None
    assert match.score == 0.9
    assert match.left == int(2000 * settings.result_search_x_start) + 10
    assert match.top == int(1000 * settings.result_search_y_start) + 5
    assert probe.trace.result_score == 0.9
