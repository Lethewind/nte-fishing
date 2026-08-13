from unittest.mock import Mock, patch

import pytest

from src import padinput
from src.padinput import (
    WA_ACTIVE,
    WM_ACTIVATE,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SETFOCUS,
    PadInput,
    VK_MAP,
)
from src.types import SliderDirection


@pytest.fixture(autouse=True)
def target_hwnd(monkeypatch):
    monkeypatch.setattr(padinput, "HWND", 9876)


def test_get_hwnd_reads_current_global_handle():
    assert padinput.get_hwnd() == 9876


def test_input_function_and_assignment_are_independent():
    pad = PadInput("postmessage", "arrows")

    assert pad.inputfn == "postmessage"
    assert pad.assigntype == "arrows"


def test_invalid_input_configuration_fails_fast():
    with pytest.raises(ValueError, match="input function"):
        PadInput("invalid", "ad")
    with pytest.raises(ValueError, match="assignment type"):
        PadInput("sendmessage", "invalid")


def test_ad_assignment_maps_left_and_right():
    pad = PadInput("sendmessage", "ad")
    with patch.object(pad, "_down") as down, patch.object(pad, "_up") as up:
        pad.slide(SliderDirection.LEFT)
        pad.slide(SliderDirection.RIGHT)
        pad.release()

    assert [call.args[0] for call in down.call_args_list] == ["a", "d"]
    assert [call.args[0] for call in up.call_args_list] == ["a", "d"]


def test_arrow_assignment_maps_left_and_right():
    pad = PadInput("sendmessage", "arrows")
    with patch.object(pad, "_down") as down, patch.object(pad, "_up") as up:
        pad.slide(SliderDirection.LEFT)
        pad.slide(SliderDirection.RIGHT)
        pad.release()

    assert [call.args[0] for call in down.call_args_list] == ["left", "right"]
    assert [call.args[0] for call in up.call_args_list] == ["left", "right"]


def test_press_is_idempotent_and_releases_previous_key():
    pad = PadInput("sendmessage", "ad")
    with patch.object(pad, "_down") as down, patch.object(pad, "_up") as up:
        pad.press("a")
        pad.press("a")
        pad.press("d")
        pad.release()

    assert [call.args[0] for call in down.call_args_list] == ["a", "d"]
    assert [call.args[0] for call in up.call_args_list] == ["a", "d"]


def test_neutral_releases_held_direction():
    pad = PadInput("sendmessage", "ad")
    with patch.object(pad, "_down"), patch.object(pad, "_up") as up:
        pad.slide(SliderDirection.LEFT)
        pad.slide(SliderDirection.NEUTRAL)
    up.assert_called_once_with("a")


def test_tap_sends_down_and_up_without_holding_key():
    pad = PadInput("sendmessage", "ad")
    with patch.object(pad, "_down") as down, patch.object(pad, "_up") as up:
        pad.tap("f")
        pad.tap("escape")

    assert [call.args[0] for call in down.call_args_list] == ["f", "escape"]
    assert [call.args[0] for call in up.call_args_list] == ["f", "escape"]
    assert pad._held_key is None


@pytest.mark.parametrize("inputfn", ["sendmessage", "postmessage"])
def test_message_backend_emits_escape(inputfn):
    pad = PadInput(inputfn, "ad")
    message_fn = Mock()
    pad._message_fn = message_fn

    pad.tap("escape")

    message_fn.assert_any_call(
        9876,
        WM_KEYDOWN,
        VK_MAP["escape"],
        pad._lparam("escape"),
    )
    message_fn.assert_any_call(
        9876,
        WM_KEYUP,
        VK_MAP["escape"],
        pad._lparam("escape", True),
    )


def test_foreground_backend_uses_sendinput():
    pad = PadInput("foreground", "ad")
    with patch.object(pad, "_foreground_activate", return_value=True), patch.object(
        pad,
        "_send_input_key",
    ) as send_input:
        pad.tap("escape")
    send_input.assert_any_call("escape")
    send_input.assert_any_call("escape", True)


def test_foreground_activation_is_retried_after_focus_is_lost():
    pad = PadInput("foreground", "ad")
    with patch(
        "src.padinput.win32gui.GetForegroundWindow",
        side_effect=[111, 111, 9876],
    ), patch(
        "src.padinput.ctypes.windll.kernel32.GetCurrentThreadId",
        return_value=33,
    ), patch(
        "src.padinput.ctypes.windll.user32.GetWindowThreadProcessId",
        return_value=22,
    ), patch(
        "src.padinput.ctypes.windll.user32.AttachThreadInput",
        return_value=1,
    ), patch("src.padinput.ctypes.windll.user32.SetForegroundWindow") as set_foreground:
        assert pad._foreground_activate()

    set_foreground.assert_called_once_with(9876)


def test_foreground_falls_back_to_sendmessage():
    pad = PadInput("foreground", "ad")
    with patch.object(pad, "_foreground_activate", return_value=False), patch.object(
        pad,
        "_send_message_key",
    ) as send_message:
        pad.tap("escape")

    assert [call.args[:2] for call in send_message.call_args_list] == [
        ("escape", False),
        ("escape", True),
    ]


def test_activation_hints_are_sent_before_key_down_only():
    pad = PadInput("sendmessage", "ad", activation_hints=True)
    message_fn = Mock()
    pad._message_fn = message_fn
    with patch("src.padinput.win32gui.GetForegroundWindow", return_value=111):
        pad.tap("f")

    assert [call.args for call in message_fn.call_args_list] == [
        (9876, WM_ACTIVATE, WA_ACTIVE, 111),
        (9876, WM_SETFOCUS, 111, 0),
        (9876, WM_KEYDOWN, VK_MAP["f"], pad._lparam("f")),
        (9876, WM_KEYUP, VK_MAP["f"], pad._lparam("f", True)),
    ]


def test_activation_hints_can_be_disabled():
    pad = PadInput("sendmessage", "ad", activation_hints=False)
    message_fn = Mock()
    pad._message_fn = message_fn

    pad.tap("f")

    assert [call.args[1] for call in message_fn.call_args_list] == [
        WM_KEYDOWN,
        WM_KEYUP,
    ]
