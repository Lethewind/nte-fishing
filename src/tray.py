# src/tray.py
import os
import time
import threading
import ctypes
import ctypes.wintypes
import pystray
from PIL import Image, ImageDraw
import config
from src.main import FishingBot

_VK_F12 = 0x7B

# ── 诊断日志 ──────────────────────────────────────────
_DIAG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'nte-fishing')
os.makedirs(_DIAG_DIR, exist_ok=True)
_DIAG_LOG = os.path.join(_DIAG_DIR, 'diag.log')


def _diag(msg: str):
    with open(_DIAG_LOG, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


# ── 全局 F12 热键：WH_KEYBOARD_LL 低层键盘钩子 ──────

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      ctypes.c_uint32),
        ("scanCode",    ctypes.c_uint32),
        ("flags",       ctypes.c_uint32),
        ("time",        ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

# 64-bit Windows: lParam = LPARAM = LONG_PTR = 8 字节
_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_ssize_t)
_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100


def _start_ll_hook(on_f12):
    """在后台线程安装 WH_KEYBOARD_LL 钩子 + 消息循环。"""
    # 64-bit 修复：显式声明 CallNextHookEx 参数类型
    _CallNextHookEx = ctypes.windll.user32.CallNextHookEx
    _CallNextHookEx.restype = ctypes.c_long
    _CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ssize_t]

    @_HOOKPROC
    def _proc(nCode, wParam, lParam):
        if nCode >= 0 and wParam == _WM_KEYDOWN:
            kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == _VK_F12:
                on_f12()
        return _CallNextHookEx(None, nCode, wParam, lParam)

    def _thread():
        hook = ctypes.windll.user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, _proc, None, 0)
        if not hook:
            _diag(f"WH_KEYBOARD_LL 安装失败 (err={ctypes.windll.kernel32.GetLastError()})")
            return
        _diag("WH_KEYBOARD_LL 钩子已安装")
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        ctypes.windll.user32.UnhookWindowsHookEx(hook)
        _diag("WH_KEYBOARD_LL 钩子已卸载")

    t = threading.Thread(target=_thread, daemon=True)
    t.start()
    return t


# ── 托盘图标 ──────────────────────────────────────────

def _make_icon(color: str) -> Image.Image:
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 28, 28), fill=color)
    return img


def run_tray():
    _diag("run_tray() 开始")
    bot = FishingBot()
    icon_ref: list[pystray.Icon] = []

    def on_toggle(source: str = ""):
        _diag(f"on_toggle source={source}")
        bot.toggle()
        if icon_ref:
            icon_ref[0].icon = _make_icon('green' if bot.is_running else 'gray')
            icon_ref[0].title = f"NTE Fishing Bot — {bot.status}"
        _diag(f"  is_running={bot.is_running} status={bot.status}")

    def on_toggle_menu(icon, item):
        on_toggle(source="menu")

    def on_toggle_preview(icon, item):
        bot.toggle_preview()

    def on_quit(icon, item):
        bot.stop()
        icon.stop()

    icon = pystray.Icon(
        name="NTE Fishing Bot",
        icon=_make_icon('gray'),
        title="NTE Fishing Bot — 已停止",
        menu=pystray.Menu(
            pystray.MenuItem("开始/暂停", on_toggle_menu, default=True),
            pystray.MenuItem("调试窗口", on_toggle_preview,
                             checked=lambda icon: bot.preview_enabled),
            pystray.MenuItem("退出", on_quit),
        )
    )
    icon_ref.append(icon)

    # WH_KEYBOARD_LL 钩子（编译 exe 中最可靠的全局热键方案）
    _start_ll_hook(lambda: on_toggle(source="ll_hook"))

    _diag("主线程进入 icon.run()")
    icon.run()
    _diag("icon.run() 返回，退出")
