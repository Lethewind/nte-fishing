"""State-machine-owned fishing detection and input decisions."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from src.settings import Settings, settings
from src.types import SliderDirection


class VisionProbe(Protocol):
    """Lazy operations available for one captured frame."""

    def detect_bar(self) -> bool: ...

    def detect_fish_area(self) -> bool: ...

    def detect_marker(self) -> bool: ...

    def resolve_slider(self) -> SliderDirection | None: ...

    def detect_result(self) -> bool: ...

    def detect_hook(self) -> bool: ...


class MachineState(Enum):
    NO_WINDOW = auto()
    SEARCHING = auto()
    FISHING = auto()


class Action(Enum):
    PRESS_F = auto()
    PRESS_ESCAPE = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    RELEASE_SLIDER = auto()


@dataclass(frozen=True)
class Transition:
    state: MachineState
    actions: tuple[Action, ...] = ()
    status: str = ""


class StateMachine:
    def __init__(
        self,
        app_settings: Settings = settings,
        rng: random.Random | None = None,
    ):
        self.settings = app_settings
        self._rng = rng or random.Random()
        self.state = MachineState.NO_WINDOW
        self._next_press_at: float | None = None
        self._next_escape_at: float | None = None

    def _schedule_press(self, now: float) -> None:
        low = max(0.0, self.settings.idle_press_min_sec)
        high = max(low, self.settings.idle_press_max_sec)
        self._next_press_at = now + self._rng.uniform(low, high)

    def _set_state(self, state: MachineState) -> None:
        self.state = state

    def _fishing_transition(
        self,
        direction: SliderDirection,
    ) -> Transition:
        self._set_state(MachineState.FISHING)
        self._next_press_at = None
        self._next_escape_at = None
        actions = {
            SliderDirection.LEFT: (Action.MOVE_LEFT,),
            SliderDirection.RIGHT: (Action.MOVE_RIGHT,),
            SliderDirection.NEUTRAL: (Action.RELEASE_SLIDER,),
        }.get(direction, (Action.RELEASE_SLIDER,))
        return Transition(self.state, actions, "FISHING")

    def _result_transition(
        self,
        now: float,
        release: bool,
    ) -> Transition:
        self._set_state(MachineState.SEARCHING)
        self._next_press_at = None
        actions: list[Action] = []
        if release:
            actions.append(Action.RELEASE_SLIDER)
        if self._next_escape_at is None or now >= self._next_escape_at:
            actions.append(Action.PRESS_ESCAPE)
            self._next_escape_at = now + self.settings.result_esc_cooldown_sec
            return Transition(self.state, tuple(actions), "PRESS_ESCAPE")
        return Transition(self.state, tuple(actions), "WAIT_RESULT")

    def _hook_transition(
        self,
        now: float,
        release: bool,
    ) -> Transition:
        self._set_state(MachineState.SEARCHING)
        self._next_escape_at = None
        actions: list[Action] = []
        if release:
            actions.append(Action.RELEASE_SLIDER)
        if self._next_press_at is None:
            self._schedule_press(now)
        if self._next_press_at is not None and now >= self._next_press_at:
            actions.append(Action.PRESS_F)
            self._schedule_press(now)
            return Transition(self.state, tuple(actions), "PRESS_F")
        return Transition(self.state, tuple(actions), "WAIT_PRESS_F")

    def step(self, probe: VisionProbe | None, now: float) -> Transition:
        if probe is None:
            actions = () if self.state is MachineState.NO_WINDOW else (Action.RELEASE_SLIDER,)
            self._set_state(MachineState.NO_WINDOW)
            self._next_press_at = None
            self._next_escape_at = None
            return Transition(self.state, actions, "NO_WINDOW")

        was_fishing = self.state is MachineState.FISHING
        bar_candidate = probe.detect_bar()
        fishing_incomplete = False

        if bar_candidate:
            if probe.detect_fish_area():
                if probe.detect_marker():
                    direction = probe.resolve_slider()
                    if direction is not None:
                        return self._fishing_transition(direction)
            fishing_incomplete = True

        release = was_fishing or fishing_incomplete
        if probe.detect_result():
            return self._result_transition(now, release)
        if probe.detect_hook():
            return self._hook_transition(now, release)

        self._next_press_at = None
        if was_fishing:
            self._set_state(MachineState.FISHING)
            return Transition(
                self.state,
                (Action.RELEASE_SLIDER,),
                "RETRY_FISHING",
            )

        self._set_state(MachineState.SEARCHING)
        actions = (Action.RELEASE_SLIDER,) if fishing_incomplete else ()
        return Transition(self.state, actions, "WAIT_HOOK")
