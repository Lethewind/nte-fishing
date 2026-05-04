# src/controller.py
import ctypes
import ctypes.wintypes
import logging
import time
import win32api
import config

log = logging.getLogger(__name__)

VK_MAP = {
    'f':      0x46,
    'd':      0x44,
    'a':      0x41,
    'escape': 0x1B,
    'left':   0x25,
    'right':  0x27,
}

_SCAN_MAP = {
    'a': 0x1E,
    'd': 0x20,
    'f': 0x21,
    'escape': 0x01,
    'left':  0x4B,
    'right': 0x4D,
}

# Windows messages
_WM_KEYDOWN = 0x0100
_WM_KEYUP   = 0x0101
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP   = 0x0202

# lParam helpers: (repeat=1) | (scan<<16) | (extended<<24) | (prev_down<<30) | (transition<<31)
def _lp_keydown(sc: int, extended: int = 0) -> int:
    return 1 | (sc << 16) | (extended << 24)

def _lp_keyup(sc: int, extended: int = 0) -> int:
    return 1 | (sc << 16) | (extended << 24) | (1 << 30) | (1 << 31)

# Win32 API
_PostMessage = ctypes.windll.user32.PostMessageW
_SendMessage = ctypes.windll.user32.SendMessageW
_GetForegroundWindow = ctypes.windll.user32.GetForegroundWindow
_GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
_AttachThreadInput = ctypes.windll.user32.AttachThreadInput
_SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
_BringWindowToTop = ctypes.windll.user32.BringWindowToTop
_ShowWindow = ctypes.windll.user32.ShowWindow

# ── SendInput helpers (for foreground mode) ──────────────────────────────
OUR_MARKER: int = 0xDEAD_CA7E

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_uint16),
        ("wScan",       ctypes.c_uint16),
        ("dwFlags",     ctypes.c_uint32),
        ("time",        ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]

class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("_u", _INPUT_UNION)]

_KEYEVENTF_KEYUP = 0x0002

def _sendinput(vk: int, up: bool = False):
    inp = _INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp._u.ki.wVk = vk
    inp._u.ki.wScan = win32api.MapVirtualKey(vk, 0)
    inp._u.ki.dwFlags = _KEYEVENTF_KEYUP if up else 0
    inp._u.ki.dwExtraInfo = OUR_MARKER
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _set_foreground(hwnd: int) -> None:
    """通过 AttachThreadInput 可靠地将窗口带到前台。"""
    fore = _GetForegroundWindow()
    fore_tid = _GetWindowThreadProcessId(fore, None)
    target_tid = _GetWindowThreadProcessId(hwnd, None)
    if fore_tid != target_tid:
        _AttachThreadInput(fore_tid, target_tid, True)
    _BringWindowToTop(hwnd)
    _SetForegroundWindow(hwnd)
    _ShowWindow(hwnd, 5)  # SW_SHOW
    if fore_tid != target_tid:
        _AttachThreadInput(fore_tid, target_tid, False)


class FishingController:

    def __init__(self, hwnd: int, method: str = "postmessage"):
        """
        method:
          "postmessage"  — PostMessageW (幕后, 不影响前台)
          "sendmessage"  — SendMessageW (同步等待处理)
          "foreground"   — 窗口置前 + SendInput (首次激活, 结束后恢复)
          "arrow_pm"     — 方向键 PostMessage
        """
        self.hwnd = hwnd
        self.method = method
        self._held_key: str | None = None
        # foreground 模式专用
        self._fg_brought = False
        self._fg_prev = None
        # 脱钩恢复：记录脱钩前最后一帧的有效误差方向
        self._last_good_error: float | None = None

    # ── 底层按键方法 ────────────────────────────────────

    def _pm_down(self, key: str):
        sc = _SCAN_MAP.get(key, 0)
        ext = 1 if key in ('left', 'right') else 0
        _PostMessage(self.hwnd, _WM_KEYDOWN, VK_MAP[key], _lp_keydown(sc, ext))

    def _pm_up(self, key: str):
        sc = _SCAN_MAP.get(key, 0)
        ext = 1 if key in ('left', 'right') else 0
        _PostMessage(self.hwnd, _WM_KEYUP, VK_MAP[key], _lp_keyup(sc, ext))

    def _sm_down(self, key: str):
        sc = _SCAN_MAP.get(key, 0)
        ext = 1 if key in ('left', 'right') else 0
        _SendMessage(self.hwnd, _WM_KEYDOWN, VK_MAP[key], _lp_keydown(sc, ext))

    def _sm_up(self, key: str):
        sc = _SCAN_MAP.get(key, 0)
        ext = 1 if key in ('left', 'right') else 0
        _SendMessage(self.hwnd, _WM_KEYUP, VK_MAP[key], _lp_keyup(sc, ext))

    def _fg_activate(self):
        """首次使用时将游戏窗口置前（仅一次）。"""
        if not self._fg_brought:
            self._fg_prev = _GetForegroundWindow()
            _set_foreground(self.hwnd)
            time.sleep(0.03)
            self._fg_brought = True

    def _fg_down(self, key: str):
        self._fg_activate()
        _sendinput(VK_MAP[key])

    def _fg_up(self, key: str):
        _sendinput(VK_MAP[key], up=True)

    def _tap(self, key: str):
        """单次击键（按下+松开），适合 F / ESC。"""
        if self.method == "foreground":
            self._fg_activate()
            _sendinput(VK_MAP[key])
            time.sleep(0.05)
            _sendinput(VK_MAP[key], up=True)
        elif self.method == "sendmessage":
            self._sm_down(key)
            self._sm_up(key)
        else:
            self._pm_down(key)
            self._pm_up(key)

    # ── 鼠标点击 ────────────────────────────────────────

    def _mouse_foreground(self, x: int, y: int):
        """前台模式鼠标点击：ClientToScreen + SetCursorPos + mouse_event。"""
        self._fg_activate()
        pt = ctypes.wintypes.POINT(x, y)
        ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        ctypes.windll.user32.SetCursorPos(pt.x, pt.y)
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP

    # ── 公开方法 ────────────────────────────────────────

    def press_cast(self):
        log.debug("press_cast")
        self._tap('f')

    def click_dismiss(self):
        log.debug("click_dismiss")
        self._tap('escape')

    def click_bite(self, x: int = 0, y: int = 0):
        """鼠标左键点击指定坐标（前台模式用 SendInput，否则用 PostMessage）。"""
        if self.method == "foreground":
            self._mouse_foreground(x, y)
        else:
            lparam = x | (y << 16)
            _PostMessage(self.hwnd, _WM_LBUTTONDOWN, 1, lparam)
            time.sleep(0.05)
            _PostMessage(self.hwnd, _WM_LBUTTONUP, 0, lparam)

    def hold_direction(self, error: float, px: int | None = None,
                       fl: int | None = None, fr: int | None = None):
        """缓动函数控制竖线逼近鱼滑块中心。

        每帧计算 easing_delta = -(fish_center - px) * factor
        当 delta 超过松手阈值时按方向键，否则松手。
        误差超过 MISS_MAX_ERROR 时尝试恢复（参考上次有效位置的方向）。
        """

        # ── 脱钩检测与恢复 ────────────────────────────
        if abs(error) > config.MISS_MAX_ERROR:
            log.debug("脱钩: 误差=%.0f 超过阈值 %d", error, config.MISS_MAX_ERROR)
            # 先松手
            if self._held_key:
                self._key_up(self._held_key)
                self._held_key = None
            # 尝试恢复：朝上次有效位置的反方向追
            if self._last_good_error is not None:
                target = 'a' if self._last_good_error > 0 else 'd'
                if self.method == "arrow_pm":
                    target = 'left' if target == 'a' else 'right'
                self._key_down(target)
                self._held_key = target
            return

        # ── 记录有效误差（未脱钩时的方向）──────────────
        self._last_good_error = error

        # ── 缓动函数控制 ──────────────────────────────
        easing_delta = -error * config.EASING_FACTOR

        if easing_delta > config.EASING_RELEASE_THRESHOLD:
            target = 'd'
        elif easing_delta < -config.EASING_RELEASE_THRESHOLD:
            target = 'a'
        else:
            target = None

        # arrow_pm 模式
        if target is not None and self.method == "arrow_pm":
            target = 'left' if target == 'a' else 'right'

        # 已按着目标键 → 什么都不做
        if self._held_key == target:
            return

        # 切换按键
        if self._held_key:
            self._key_up(self._held_key)
        if target:
            self._key_down(target)
        self._held_key = target

    def release_all(self):
        if self._held_key:
            self._key_up(self._held_key)
            self._held_key = None
        # foreground 模式：恢复前台窗口
        if self.method == "foreground" and self._fg_brought:
            if self._fg_prev and self._fg_prev != self.hwnd:
                _set_foreground(self._fg_prev)
            self._fg_brought = False
            self._fg_prev = None

    # ── 根据 method 派发 ────────────────────────────────

    def _key_down(self, key: str):
        if self.method == "sendmessage":
            self._sm_down(key)
        elif self.method == "foreground":
            self._fg_down(key)
        else:
            self._pm_down(key)

    def _key_up(self, key: str):
        if self.method == "sendmessage":
            self._sm_up(key)
        elif self.method == "foreground":
            self._fg_up(key)
        else:
            self._pm_up(key)
