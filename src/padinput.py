"""Keyboard input backends and fishing-direction key assignment."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable

import win32api
import win32gui

from src.settings import settings
from src.types import SliderDirection

HWND: int = 0

VK_MAP = {
    "a": 0x41,
    "d": 0x44,
    "f": 0x46,
    "escape": 0x1B,
    "left": 0x25,
    "right": 0x27,
}
SCAN_MAP = {
    "a": 0x1E,
    "d": 0x20,
    "f": 0x21,
    "escape": 0x01,
    "left": 0x4B,
    "right": 0x4D,
}
DIRECTION_ASSIGNMENTS = {
    "ad": {
        SliderDirection.LEFT: "a",
        SliderDirection.RIGHT: "d",
    },
    "arrows": {
        SliderDirection.LEFT: "left",
        SliderDirection.RIGHT: "right",
    },
}

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_ACTIVATE = 0x0006
WM_SETFOCUS = 0x0007
WA_ACTIVE = 1
OUR_MARKER = 0xDEAD_CA7E

_PostMessage = ctypes.windll.user32.PostMessageW
_SendMessage = ctypes.windll.user32.SendMessageW
_MESSAGE_FUNCTIONS: dict[str, Callable[..., int]] = {
    "postmessage": _PostMessage,
    "sendmessage": _SendMessage,
}


def get_hwnd() -> int:
    """Return the latest window handle published by WindowCapture."""
    return HWND


class PadInput:
    def __init__(
        self,
        inputfn: str = "sendmessage",
        assigntype: str = "ad",
        activation_hints: bool = False,
    ):
        inputfn = inputfn.lower()
        assigntype = assigntype.lower()
        if inputfn not in {*_MESSAGE_FUNCTIONS, "foreground"}:
            raise ValueError(f"Unsupported input function: {inputfn}")
        if assigntype not in DIRECTION_ASSIGNMENTS:
            raise ValueError(f"Unsupported assignment type: {assigntype}")

        self.inputfn = inputfn
        self.assigntype = assigntype
        self.activation_hints = activation_hints
        self._message_fn = _MESSAGE_FUNCTIONS.get(inputfn)
        self._held_key: str | None = None
        self._foreground_previous: int | None = None
        self._foreground_acquired = False

    @staticmethod
    def _validate_key(key: str) -> None:
        if key not in VK_MAP:
            raise ValueError(f"Unsupported key: {key}")

    @staticmethod
    def _lparam(key: str, up: bool = False) -> int:
        scan = SCAN_MAP[key]
        extended = 1 if key in {"left", "right"} else 0
        value = 1 | (scan << 16) | (extended << 24)
        if up:
            value |= (1 << 30) | (1 << 31)
        return value

    def _send_message_key(
        self,
        key: str,
        up: bool,
        fn: Callable[..., int],
    ) -> None:
        hwnd = get_hwnd()
        if not hwnd:
            return
        if not up and self.activation_hints:
            previous = int(win32gui.GetForegroundWindow() or 0)
            fn(hwnd, WM_ACTIVATE, WA_ACTIVE, previous)
            fn(hwnd, WM_SETFOCUS, previous, 0)
        fn(hwnd, WM_KEYUP if up else WM_KEYDOWN, VK_MAP[key], self._lparam(key, up))

    def _foreground_activate(self) -> bool:
        hwnd = get_hwnd()
        if not hwnd:
            return False

        previous = int(win32gui.GetForegroundWindow() or 0)
        if previous == hwnd:
            return True

        user32 = ctypes.windll.user32
        get_thread = user32.GetWindowThreadProcessId
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        previous_thread = get_thread(previous, None) if previous else 0
        target_thread = get_thread(hwnd, None)
        attached: list[int] = []
        for thread_id in (previous_thread, target_thread):
            if thread_id and thread_id != current_thread and thread_id not in attached:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        try:
            user32.ShowWindow(hwnd, 9)
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            for thread_id in reversed(attached):
                user32.AttachThreadInput(current_thread, thread_id, False)

        for _ in range(20):
            if int(win32gui.GetForegroundWindow() or 0) == hwnd:
                self._foreground_previous = previous if previous != hwnd else None
                self._foreground_acquired = True
                return True
            time.sleep(0.01)
        self._foreground_acquired = False
        return False

    @staticmethod
    def _send_input_key(key: str, up: bool = False) -> None:
        if not get_hwnd():
            return

        class KeyInput(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_uint16),
                ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class InputUnion(ctypes.Union):
            _fields_ = [("ki", KeyInput), ("padding", ctypes.c_byte * 32)]

        class Input(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("union", InputUnion)]

        item = Input()
        item.type = 1
        item.union.ki.wVk = VK_MAP[key]
        item.union.ki.wScan = win32api.MapVirtualKey(VK_MAP[key], 0)
        item.union.ki.dwFlags = 0x0002 if up else 0
        item.union.ki.dwExtraInfo = OUR_MARKER
        ctypes.windll.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))

    def _down(self, key: str) -> None:
        if self.inputfn == "foreground":
            if self._foreground_activate():
                self._send_input_key(key)
                return
            self._send_message_key(key, False, _SendMessage)
            return
        assert self._message_fn is not None
        self._send_message_key(key, False, self._message_fn)

    def _up(self, key: str) -> None:
        if self.inputfn == "foreground":
            if self._foreground_activate():
                self._send_input_key(key, True)
                return
            self._send_message_key(key, True, _SendMessage)
            return
        assert self._message_fn is not None
        self._send_message_key(key, True, self._message_fn)

    def press(self, key: str) -> None:
        """Hold one key, releasing the previously held key when necessary."""
        self._validate_key(key)
        if self._held_key == key:
            return
        self.release()
        self._down(key)
        self._held_key = key

    def tap(self, key: str) -> None:
        """Send one complete key-down/key-up pair without retaining it."""
        self._validate_key(key)
        self._down(key)
        if self.inputfn == "foreground":
            time.sleep(0.05)
        self._up(key)

    def release(self) -> None:
        """Release the currently held key, if any."""
        if self._held_key is None:
            return
        key, self._held_key = self._held_key, None
        self._up(key)

    def slide(self, direction: SliderDirection) -> None:
        if direction is SliderDirection.NEUTRAL:
            self.release()
            return
        self.press(DIRECTION_ASSIGNMENTS[self.assigntype][direction])

    def reset(self) -> None:
        """Release input and restore focus acquired by the foreground backend."""
        self.release()
        hwnd = get_hwnd()
        if (
            self.inputfn == "foreground"
            and self._foreground_acquired
            and hwnd
            and win32gui.GetForegroundWindow() == hwnd
            and self._foreground_previous
            and self._foreground_previous != hwnd
        ):
            ctypes.windll.user32.SetForegroundWindow(self._foreground_previous)
        self._foreground_previous = None
        self._foreground_acquired = False


PAD_INPUT = PadInput(
    settings.input_function,
    settings.input_assignment,
    settings.send_activation_hints,
)
