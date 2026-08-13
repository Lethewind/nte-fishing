"""System-tray entry point and F12 toggle hook."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading

import pystray
from PIL import Image, ImageDraw

from src.main import FishingBot

VK_F12 = 0x7B
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100

_HOOK_LPARAM = ctypes.c_ssize_t
_CALL_NEXT_ARGS = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, _HOOK_LPARAM]


def _configure_call_next_hook(function):
    """Declare the pointer-sized Win32 signature used by CallNextHookEx."""
    function.restype = _HOOK_LPARAM
    function.argtypes = _CALL_NEXT_ARGS
    return function


class KeyboardHook:
    def __init__(self, callback):
        self.callback = callback
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        hook_proc_type = ctypes.WINFUNCTYPE(
            _HOOK_LPARAM, ctypes.c_int, ctypes.c_uint, _HOOK_LPARAM
        )
        call_next = _configure_call_next_hook(ctypes.windll.user32.CallNextHookEx)

        class KeyboardData(ctypes.Structure):
            _fields_ = [("vkCode", ctypes.c_uint32), ("scanCode", ctypes.c_uint32),
                        ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                        ("dwExtraInfo", ctypes.c_size_t)]

        @hook_proc_type
        def procedure(code, message, pointer):
            if code >= 0 and message == WM_KEYDOWN:
                data = ctypes.cast(ctypes.c_void_p(pointer), ctypes.POINTER(KeyboardData)).contents
                if data.vkCode == VK_F12:
                    self.callback()
            return call_next(None, code, message, pointer)

        def run() -> None:
            hook = ctypes.windll.user32.SetWindowsHookExW(WH_KEYBOARD_LL, procedure, None, 0)
            if not hook:
                return
            msg = ctypes.wintypes.MSG()
            while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
            ctypes.windll.user32.UnhookWindowsHookEx(hook)

        self.thread = threading.Thread(target=run, daemon=True, name="f12-hook")
        self.thread.start()


def _icon(color: str) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((4, 4, 28, 28), fill=color)
    return image


def run_tray() -> None:
    bot = FishingBot()
    icon_ref: list[pystray.Icon] = []

    def refresh_icon() -> None:
        if icon_ref:
            icon_ref[0].icon = _icon("green" if bot.is_running else "gray")
            icon_ref[0].title = f"NTE Fishing Bot - {bot.status}"

    def toggle(_icon=None, _item=None) -> None:
        bot.toggle()
        refresh_icon()

    def toggle_preview(_icon=None, _item=None) -> None:
        bot.toggle_preview()

    def quit_app(icon, _item) -> None:
        bot.stop()
        icon.stop()

    icon = pystray.Icon(
        "NTE Fishing Bot",
        _icon("gray"),
        "NTE Fishing Bot - 已停止",
        pystray.Menu(
            pystray.MenuItem("啟動／停止", toggle, default=True),
            pystray.MenuItem("預覽視窗", toggle_preview, checked=lambda _icon: bot.preview_enabled),
            pystray.MenuItem("結束", quit_app),
        ),
    )
    icon_ref.append(icon)
    KeyboardHook(toggle).start()
    icon.run()
