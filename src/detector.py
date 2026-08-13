"""Single-frame computer-vision probes for the fishing mini-game."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.settings import GameProfile, settings
from src.types import SliderDirection

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TemplateMatch:
    left: int
    top: int
    right: int
    bottom: int
    score: float

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2


@dataclass
class ProbeTrace:
    """Debug payload containing only checks performed for one frame."""

    bar_checked: bool = False
    bar_visible: bool = False
    fish_area_checked: bool = False
    raw_segments: tuple[tuple[int, int], ...] = ()
    fish_left: int | None = None
    fish_right: int | None = None
    marker_checked: bool = False
    marker_match: TemplateMatch | None = None
    player_x: int | None = None
    slider_direction: SliderDirection = SliderDirection.NEUTRAL
    merge_limit: float | None = None
    result_checked: bool = False
    result_match: TemplateMatch | None = None
    result_score: float | None = None
    hook_checked: bool = False
    hook_visible: bool = False


def _load_template(path: Path) -> np.ndarray | None:
    try:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            return image
        return np.array(Image.open(path).convert("L"), dtype=np.uint8)
    except Exception as exc:
        log.warning("Unable to load template %s: %s", path, exc)
        return None


class FrameProbe:
    """Lazy, cached vision operations over exactly one full client frame."""

    def __init__(self, detector: "StateDetector", frame: np.ndarray):
        self._detector = detector
        self._frame = frame
        self.trace = ProbeTrace()
        self._bar_rect: tuple[int, int, int, int] | None = None
        self._bar_hsv: np.ndarray | None = None
        self._column_mask: np.ndarray | None = None
        self._raw_segments: list[tuple[int, int]] | None = None

    def _bar_roi(self) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        if self._bar_rect is None:
            height, width = self._frame.shape[:2]
            self._bar_rect = (
                int(width * settings.bar_x_start_ratio),
                int(height * settings.bar_y_start_ratio),
                int(width * settings.bar_x_end_ratio),
                int(height * settings.bar_y_end_ratio),
            )
        x1, y1, x2, y2 = self._bar_rect
        return self._frame[y1:y2, x1:x2], self._bar_rect

    def detect_bar(self) -> bool:
        if self.trace.bar_checked:
            return self.trace.bar_visible
        self.trace.bar_checked = True
        bar, _rect = self._bar_roi()
        if bar.size == 0:
            return False
        self._bar_hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
        mask = self._detector._slider_mask(self._bar_hsv)
        self._column_mask = mask.any(axis=0)
        self.trace.bar_visible = int(mask.sum()) > settings.slider_px_threshold
        return self.trace.bar_visible

    def detect_fish_area(self) -> bool:
        if self.trace.fish_area_checked:
            return bool(self._raw_segments)
        self.trace.fish_area_checked = True
        if not self.detect_bar() or self._column_mask is None:
            return False
        self._raw_segments = self._detector._segments_from_columns(self._column_mask)
        x1 = self._bar_roi()[1][0]
        self.trace.raw_segments = tuple(
            (left + x1, right + x1) for left, right in self._raw_segments
        )
        return bool(self._raw_segments)

    def detect_marker(self) -> bool:
        if self.trace.marker_checked:
            return self.trace.marker_match is not None
        self.trace.marker_checked = True
        self.trace.marker_match = self._detector._find_marker_tmpl(self._frame)
        if self.trace.marker_match is not None:
            self.trace.player_x = self.trace.marker_match.center_x
        return self.trace.marker_match is not None

    def resolve_slider(self) -> SliderDirection | None:
        if not self._raw_segments or self.trace.marker_match is None:
            return None
        marker_width = self.trace.marker_match.right - self.trace.marker_match.left
        merge_limit = self._detector._slider_merge_gap_limit(marker_width)
        merged = self._detector._merge_segments(self._raw_segments, merge_limit)
        if not merged:
            return None
        local_left, local_right = max(
            merged,
            key=lambda segment: segment[1] - segment[0],
        )
        bar_x1 = self._bar_roi()[1][0]
        self.trace.fish_left = bar_x1 + local_left
        self.trace.fish_right = bar_x1 + local_right
        self.trace.merge_limit = merge_limit
        self.trace.slider_direction = self._detector._direction_from_positions(
            self.trace.fish_left,
            self.trace.fish_right,
            self.trace.player_x,
        )
        return self.trace.slider_direction

    def detect_result(self) -> bool:
        if self.trace.result_checked:
            return self.trace.result_match is not None
        self.trace.result_checked = True
        match, score = self._detector._find_result_match(self._frame)
        self.trace.result_match = match
        self.trace.result_score = score
        return match is not None

    def detect_hook(self) -> bool:
        if self.trace.hook_checked:
            return self.trace.hook_visible
        self.trace.hook_checked = True
        self.trace.hook_visible = self._detector._is_hook(self._frame)
        return self.trace.hook_visible


class StateDetector:
    """Template owner and factory for independent per-frame probes."""

    def __init__(self, profile: GameProfile | None = None):
        self.profile = profile
        self._marker_template = _load_template(settings.marker_template)
        self._hook_template = _load_template(settings.hook_template)
        self._result_template: np.ndarray | None = None
        self.set_profile(profile)

    def set_profile(self, profile: GameProfile | None) -> None:
        self.profile = profile
        self._result_template = _load_template(profile.result_template) if profile else None

    def for_frame(self, frame: np.ndarray) -> FrameProbe:
        return FrameProbe(self, frame)

    def _slider_mask(self, hsv: np.ndarray) -> np.ndarray:
        return (
            (hsv[:, :, 0] >= settings.slider_h_low)
            & (hsv[:, :, 0] <= settings.slider_h_high)
            & (hsv[:, :, 1] > settings.slider_s_min)
            & (hsv[:, :, 2] > settings.slider_v_min)
        )

    @staticmethod
    def _segments_from_columns(column_mask: np.ndarray) -> list[tuple[int, int]]:
        columns = np.where(column_mask)[0]
        if len(columns) == 0:
            return []
        segments: list[tuple[int, int]] = []
        start = previous = int(columns[0])
        for column in columns[1:]:
            column = int(column)
            if column != previous + 1:
                segments.append((start, previous))
                start = column
            previous = column
        segments.append((start, previous))
        return segments

    @staticmethod
    def _merge_segments(
        segments: list[tuple[int, int]],
        merge_limit: float,
    ) -> list[tuple[int, int]]:
        if not segments:
            return []
        merged: list[tuple[int, int]] = []
        start, right = segments[0]
        for next_left, next_right in segments[1:]:
            gap = next_left - right - 1
            if gap < merge_limit:
                right = next_right
            else:
                merged.append((start, right))
                start, right = next_left, next_right
        merged.append((start, right))
        return merged

    @staticmethod
    def _slider_merge_gap_limit(marker_width: int | None) -> float:
        if marker_width is None or marker_width <= 0:
            return 5.0
        return max(5.0, marker_width * settings.slider_merge_gap_marker_ratio)

    def _direction_from_positions(
        self,
        fish_left: int | None,
        fish_right: int | None,
        player_x: int | None,
    ) -> SliderDirection:
        if fish_left is None or fish_right is None or player_x is None:
            return SliderDirection.NEUTRAL
        max_dist = (fish_right - fish_left) * settings.slider_max_dist_ratio
        if player_x < fish_left + max_dist:
            return SliderDirection.RIGHT
        if player_x > fish_right - max_dist:
            return SliderDirection.LEFT
        return SliderDirection.NEUTRAL

    def _find_marker_tmpl(self, frame: np.ndarray) -> TemplateMatch | None:
        template = self._marker_template
        if template is None:
            return None
        height, width = frame.shape[:2]
        y1 = max(0, int(height * (settings.bar_y_start_ratio - 0.01)))
        y2 = min(height, int(height * (settings.bar_y_end_ratio + 0.01)))
        x1 = max(0, int(width * (settings.bar_x_start_ratio - 0.02)))
        x2 = min(width, int(width * (settings.bar_x_end_ratio + 0.02)))
        region = frame[y1:y2, x1:x2]
        if (
            region.size == 0
            or region.shape[0] < template.shape[0]
            or region.shape[1] < template.shape[1]
        ):
            return None
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score < settings.marker_template_threshold:
            return None
        template_height, template_width = template.shape[:2]
        left, top = x1 + location[0], y1 + location[1]
        return TemplateMatch(
            left,
            top,
            left + template_width,
            top + template_height,
            score,
        )

    def _is_hook(self, frame: np.ndarray) -> bool:
        template = self._hook_template
        if template is None:
            return False
        height, width = frame.shape[:2]
        icon = frame[
            int(height * settings.hook_y_start_ratio):int(height * settings.hook_y_end_ratio),
            int(width * settings.hook_x_start_ratio):int(width * settings.hook_x_end_ratio),
        ]
        if icon.size == 0:
            return False
        icon_binary = self._binary_white_pattern(icon)
        template_binary = self._binary_white_pattern(template)
        template_height, template_width = template_binary.shape[:2]
        region_height, region_width = icon_binary.shape[:2]
        if template_height < 2 or template_width < 2:
            return False

        base_scale = min(region_width / template_width, region_height / template_height)
        scales = (base_scale, *np.linspace(max(0.5, base_scale * 0.6), base_scale * 1.05, 8))
        for scale in scales:
            scaled_width = int(template_width * scale)
            scaled_height = int(template_height * scale)
            if (
                scaled_width < 2
                or scaled_height < 2
                or scaled_width > region_width
                or scaled_height > region_height
            ):
                continue
            scaled_template = cv2.resize(
                template_binary,
                (scaled_width, scaled_height),
                interpolation=cv2.INTER_NEAREST,
            )
            result = cv2.matchTemplate(
                icon_binary,
                scaled_template,
                cv2.TM_CCOEFF_NORMED,
            )
            _, score, _, _ = cv2.minMaxLoc(result)
            if score >= settings.hook_template_threshold:
                return True
        return False

    @staticmethod
    def _binary_white_pattern(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            image,
            settings.hook_binary_threshold,
            255,
            cv2.THRESH_BINARY,
        )
        return binary

    def _find_result_match(
        self,
        frame: np.ndarray,
    ) -> tuple[TemplateMatch | None, float | None]:
        template = self._result_template
        if template is None:
            return None, None
        height, width = frame.shape[:2]
        y1 = int(height * settings.result_search_y_start)
        y2 = int(height * settings.result_search_y_end)
        x1 = int(width * settings.result_search_x_start)
        x2 = int(width * settings.result_search_x_end)
        region = frame[y1:y2, x1:x2]
        if region.size == 0:
            return None, None
        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        template_height, template_width = template.shape[:2]
        best: TemplateMatch | None = None
        best_score: float | None = None
        for scale in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6):
            scaled_width = int(template_width * scale)
            scaled_height = int(template_height * scale)
            if (
                scaled_width < 2
                or scaled_height < 2
                or scaled_width > region_gray.shape[1]
                or scaled_height > region_gray.shape[0]
            ):
                continue
            scaled = cv2.resize(
                template,
                (scaled_width, scaled_height),
                interpolation=cv2.INTER_AREA,
            )
            result = cv2.matchTemplate(region_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            if best_score is None or score > best_score:
                best_score = score
                left, top = x1 + location[0], y1 + location[1]
                best = TemplateMatch(
                    left,
                    top,
                    left + scaled_width,
                    top + scaled_height,
                    score,
                )
        if best_score is None or best_score < settings.result_template_threshold:
            return None, best_score
        return best, best_score
