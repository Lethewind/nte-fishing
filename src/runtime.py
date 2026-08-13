"""Runtime orchestration for the fishing bot."""

from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from src.capture import WindowCapture
from src.detector import FrameProbe, ProbeTrace, StateDetector
from src.padinput import PAD_INPUT
from src.settings import settings
from src.state_machine import Action, MachineState, StateMachine
from src.types import SliderDirection

log = logging.getLogger(__name__)

DISPLAY_SIZE = (1280, 540)


def annotate_frame(
    frame: np.ndarray,
    trace: ProbeTrace | None,
    state_name: str,
    status: str,
) -> np.ndarray:
    """Render exactly the probe results used by the state machine."""
    image = frame.copy()
    height, width = image.shape[:2]
    bar_x1 = int(width * settings.bar_x_start_ratio)
    bar_x2 = int(width * settings.bar_x_end_ratio)
    bar_y1 = int(height * settings.bar_y_start_ratio)
    bar_y2 = int(height * settings.bar_y_end_ratio)

    if trace and trace.bar_checked:
        color = (0, 255, 255) if trace.bar_visible else (100, 100, 100)
        cv2.rectangle(image, (bar_x1, bar_y1), (bar_x2, bar_y2), color, 2)

    if trace and trace.fish_area_checked:
        for left, right in trace.raw_segments:
            cv2.rectangle(
                image,
                (left, bar_y1 + 2),
                (right, bar_y2 - 2),
                (0, 165, 255),
                1,
            )

    if trace and trace.fish_left is not None and trace.fish_right is not None:
        left, right = trace.fish_left, trace.fish_right
        cv2.rectangle(image, (left, bar_y1), (right, bar_y2), (0, 255, 0), 2)
        max_dist = (right - left) * settings.slider_max_dist_ratio
        neutral_left = int(left + max_dist)
        neutral_right = int(right - max_dist)
        cv2.line(image, (neutral_left, bar_y1), (neutral_left, bar_y2), (255, 255, 0), 1)
        cv2.line(image, (neutral_right, bar_y1), (neutral_right, bar_y2), (255, 255, 0), 1)

    if trace and trace.marker_match is not None:
        marker = trace.marker_match
        cv2.rectangle(
            image,
            (marker.left, marker.top),
            (marker.right, marker.bottom),
            (0, 0, 255),
            1,
        )
        cv2.line(image, (marker.center_x, bar_y1), (marker.center_x, bar_y2), (0, 0, 255), 3)

    if trace and trace.bar_checked:
        cv2.putText(
            image,
            "FISH "
            f"raw={trace.raw_segments or '-'} "
            f"area={trace.fish_left}:{trace.fish_right} "
            f"marker={trace.player_x} "
            f"merge<{trace.merge_limit if trace.merge_limit is not None else '-'} "
            f"dir={trace.slider_direction.name}",
            (10, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (0, 255, 0),
            1,
        )

    if trace and trace.result_checked:
        result_x1 = int(width * settings.result_search_x_start)
        result_x2 = int(width * settings.result_search_x_end)
        result_y1 = int(height * settings.result_search_y_start)
        result_y2 = int(height * settings.result_search_y_end)
        cv2.rectangle(
            image,
            (result_x1, result_y1),
            (result_x2, result_y2),
            (255, 0, 255),
            2,
        )
        if trace.result_score is not None:
            cv2.putText(
                image,
                f"RESULT score={trace.result_score:.3f}",
                (10, 82),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 165, 255),
                2,
            )
        if trace.result_match is not None:
            match = trace.result_match
            cv2.rectangle(
                image,
                (match.left, match.top),
                (match.right, match.bottom),
                (0, 165, 255),
                2,
            )
            cv2.putText(
                image,
                "ESC",
                (match.left, max(15, match.top - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 165, 255),
                1,
            )

    if trace and trace.hook_checked:
        hook_x1 = int(width * settings.hook_x_start_ratio)
        hook_x2 = int(width * settings.hook_x_end_ratio)
        hook_y1 = int(height * settings.hook_y_start_ratio)
        hook_y2 = int(height * settings.hook_y_end_ratio)
        color = (255, 0, 0) if trace.hook_visible else (100, 100, 100)
        cv2.rectangle(image, (hook_x1, hook_y1), (hook_x2, hook_y2), color, 2)

    cv2.putText(
        image,
        f"RUN {state_name}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
    )
    if status:
        cv2.putText(
            image,
            status,
            (50, height - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
        )
    if (width, height) != DISPLAY_SIZE:
        image = cv2.resize(image, DISPLAY_SIZE, interpolation=cv2.INTER_LINEAR)
    return image


class FishingRuntime:
    def __init__(self):
        self.capture = WindowCapture()
        self.detector = StateDetector(self.capture.active_profile)
        self.machine = StateMachine()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._display_thread: threading.Thread | None = None
        self._preview_enabled = settings.show_preview
        self._latest_vis: np.ndarray | None = None
        self._state_log = "Stopped"

    @property
    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    @property
    def status(self) -> str:
        return self._state_log

    @property
    def preview_enabled(self) -> bool:
        return self._preview_enabled

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self.machine = StateMachine()
        self._state_log = "Starting"
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="fishing-runtime",
        )
        self._thread.start()
        self._display_thread = threading.Thread(
            target=self._display_loop,
            daemon=True,
            name="fishing-preview",
        )
        self._display_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        PAD_INPUT.reset()
        self._state_log = "Stopped"

    def toggle(self) -> None:
        self.stop() if self.is_running else self.start()

    def toggle_preview(self) -> None:
        self._preview_enabled = not self._preview_enabled

    @staticmethod
    def _execute(action: Action) -> None:
        if action is Action.PRESS_F:
            PAD_INPUT.tap("f")
        elif action is Action.PRESS_ESCAPE:
            PAD_INPUT.tap("escape")
        elif action is Action.MOVE_LEFT:
            PAD_INPUT.slide(SliderDirection.LEFT)
        elif action is Action.MOVE_RIGHT:
            PAD_INPUT.slide(SliderDirection.RIGHT)
        elif action is Action.RELEASE_SLIDER:
            PAD_INPUT.release()

    def _capture_probe(self) -> tuple[np.ndarray | None, FrameProbe | None]:
        frame = self.capture.get_frame()
        profile = self.capture.active_profile
        if profile != self.detector.profile:
            self.detector.set_profile(profile)
        if frame is None or not self.capture.is_window_found():
            return frame, None
        return frame, self.detector.for_frame(frame)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            cycle_started = time.perf_counter()
            now = time.monotonic()

            capture_started = time.perf_counter()
            frame, probe = self._capture_probe()
            capture_ms = (time.perf_counter() - capture_started) * 1000

            decision_started = time.perf_counter()
            transition = self.machine.step(probe, now)
            for action in transition.actions:
                self._execute(action)
            decision_ms = (time.perf_counter() - decision_started) * 1000
            self._state_log = f"{transition.state.name}: {transition.status}".strip()
            trace = probe.trace if probe is not None else None

            render_started = time.perf_counter()
            if frame is not None and self._preview_enabled:
                self._latest_vis = annotate_frame(
                    frame,
                    trace,
                    transition.state.name,
                    self._state_log,
                )
            render_ms = (time.perf_counter() - render_started) * 1000

            interval = (
                settings.fishing_loop_interval
                if transition.state is MachineState.FISHING
                else settings.loop_interval
            )
            processing_ms = (time.perf_counter() - cycle_started) * 1000
            remaining_sleep = max(0.0, interval - processing_ms / 1000)
            sleep_started = time.perf_counter()
            if remaining_sleep > 0:
                time.sleep(remaining_sleep)
            sleep_ms = (time.perf_counter() - sleep_started) * 1000
            cycle_ms = (time.perf_counter() - cycle_started) * 1000

            log.info(
                "loop state=%s frame=%s capture=%.1fms decision=%.1fms "
                "bar=%s fish=%s:%s marker=%s direction=%s result_score=%s "
                "hook=%s render=%.1fms processing=%.1fms sleep=%.1fms "
                "cycle=%.1fms target=%.1fms",
                transition.state.name,
                frame is not None,
                capture_ms,
                decision_ms,
                trace.bar_visible if trace else False,
                trace.fish_left if trace else None,
                trace.fish_right if trace else None,
                trace.player_x if trace else None,
                trace.slider_direction.name if trace else SliderDirection.NEUTRAL.name,
                (
                    f"{trace.result_score:.3f}"
                    if trace and trace.result_score is not None
                    else "-"
                ),
                trace.hook_visible if trace else False,
                render_ms,
                processing_ms,
                sleep_ms,
                cycle_ms,
                interval * 1000,
            )

        PAD_INPUT.reset()

    def _display_loop(self) -> None:
        window_name = "NTE Fishing Bot"
        shown = False
        while not self._stop_event.is_set():
            if not self._preview_enabled:
                if shown:
                    try:
                        cv2.destroyWindow(window_name)
                    except cv2.error:
                        pass
                    shown = False
                time.sleep(0.1)
                continue
            if not shown:
                cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window_name, *DISPLAY_SIZE)
                shown = True
            if self._latest_vis is not None:
                cv2.imshow(window_name, self._latest_vis)
            if cv2.waitKey(33) & 0xFF == ord("q"):
                self._preview_enabled = False
                continue
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    self._preview_enabled = False
                    shown = False
            except cv2.error:
                self._preview_enabled = False
                shown = False
        if shown:
            try:
                cv2.destroyWindow(window_name)
            except cv2.error:
                pass
