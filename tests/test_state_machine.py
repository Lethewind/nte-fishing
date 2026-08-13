from src.settings import settings
from src.state_machine import Action, MachineState, StateMachine
from src.types import SliderDirection


class FixedRandom:
    def uniform(self, low, _high):
        return low


class FakeProbe:
    def __init__(
        self,
        *,
        bar=False,
        fish=False,
        marker=False,
        direction=SliderDirection.NEUTRAL,
        result=False,
        hook=False,
    ):
        self.bar = bar
        self.fish = fish
        self.marker = marker
        self.direction = direction
        self.result = result
        self.hook = hook
        self.calls: list[str] = []

    def detect_bar(self):
        self.calls.append("bar")
        return self.bar

    def detect_fish_area(self):
        self.calls.append("fish_area")
        return self.fish

    def detect_marker(self):
        self.calls.append("marker")
        return self.marker

    def resolve_slider(self):
        self.calls.append("resolve")
        return self.direction

    def detect_result(self):
        self.calls.append("result")
        return self.result

    def detect_hook(self):
        self.calls.append("hook")
        return self.hook


def test_hook_schedules_repeated_f_without_hidden_visual_state():
    machine = StateMachine(rng=FixedRandom())

    first = FakeProbe(hook=True)
    assert machine.step(first, 0.0).state is MachineState.SEARCHING
    assert first.calls == ["bar", "result", "hook"]

    early = machine.step(FakeProbe(hook=True), settings.idle_press_min_sec - 0.01)
    assert early.actions == ()
    due = machine.step(FakeProbe(hook=True), settings.idle_press_min_sec)
    assert due.actions == (Action.PRESS_F,)


def test_valid_fishing_short_circuits_result_and_hook():
    machine = StateMachine(rng=FixedRandom())
    probe = FakeProbe(
        bar=True,
        fish=True,
        marker=True,
        direction=SliderDirection.RIGHT,
        result=True,
        hook=True,
    )

    transition = machine.step(probe, 0.0)

    assert transition.state is MachineState.FISHING
    assert transition.actions == (Action.MOVE_RIGHT,)
    assert probe.calls == ["bar", "fish_area", "marker", "resolve"]


def test_neutral_fishing_releases_slider():
    machine = StateMachine(rng=FixedRandom())
    transition = machine.step(
        FakeProbe(bar=True, fish=True, marker=True),
        0.0,
    )
    assert transition.state is MachineState.FISHING
    assert transition.actions == (Action.RELEASE_SLIDER,)


def test_missing_fish_area_skips_marker_and_falls_back_to_result_then_hook():
    machine = StateMachine(rng=FixedRandom())
    probe = FakeProbe(bar=True, fish=False, marker=True, hook=True)

    transition = machine.step(probe, 0.0)

    assert transition.state is MachineState.SEARCHING
    assert transition.actions == (Action.RELEASE_SLIDER,)
    assert probe.calls == ["bar", "fish_area", "result", "hook"]


def test_missing_marker_can_detect_result_in_same_frame():
    machine = StateMachine(rng=FixedRandom())
    probe = FakeProbe(bar=True, fish=True, marker=False, result=True, hook=True)

    transition = machine.step(probe, 0.0)

    assert transition.state is MachineState.SEARCHING
    assert transition.actions == (Action.RELEASE_SLIDER, Action.PRESS_ESCAPE)
    assert probe.calls == ["bar", "fish_area", "marker", "result"]


def test_result_escape_is_throttled_for_three_seconds_and_wins_over_hook():
    machine = StateMachine(rng=FixedRandom())

    first = FakeProbe(result=True, hook=True)
    assert machine.step(first, 1.0).actions == (Action.PRESS_ESCAPE,)
    assert first.calls == ["bar", "result"]

    early = machine.step(
        FakeProbe(result=True),
        1.0 + settings.result_esc_cooldown_sec - 0.01,
    )
    assert early.actions == ()
    due = machine.step(
        FakeProbe(result=True),
        1.0 + settings.result_esc_cooldown_sec,
    )
    assert due.actions == (Action.PRESS_ESCAPE,)


def test_result_cooldown_survives_unknown_frame_but_hook_resets_it():
    machine = StateMachine(rng=FixedRandom())
    machine.step(FakeProbe(result=True), 1.0)
    machine.step(FakeProbe(), 1.1)
    assert machine.step(FakeProbe(result=True), 1.2).actions == ()

    machine.step(FakeProbe(hook=True), 1.3)
    assert machine.step(FakeProbe(result=True), 1.4).actions == (Action.PRESS_ESCAPE,)


def test_fishing_with_no_evidence_releases_and_stays_high_refresh():
    machine = StateMachine(rng=FixedRandom())
    machine.state = MachineState.FISHING
    probe = FakeProbe()

    transition = machine.step(probe, 0.0)

    assert transition.state is MachineState.FISHING
    assert transition.actions == (Action.RELEASE_SLIDER,)
    assert transition.status == "RETRY_FISHING"
    assert probe.calls == ["bar", "result", "hook"]


def test_missing_window_releases_slider_and_enters_no_window():
    machine = StateMachine(rng=FixedRandom())
    machine.state = MachineState.FISHING

    transition = machine.step(None, 0.0)

    assert transition.state is MachineState.NO_WINDOW
    assert transition.actions == (Action.RELEASE_SLIDER,)
