"""
debug_run.py — 交互式全自动钓鱼 + 可视化窗口。

按键:
  F12   开始/停止
  Q     退出

可视化窗口说明:
  绿框   = 鱼滑块
  红线   = 玩家竖线
  蓝框   = 上钩检测区域
  黄框   = 钓鱼条区域
"""

import sys
import time
import random
import threading
import traceback
import ctypes
import cv2
import numpy as np
import config
from src.capture import WindowCapture
from src.detector import StateDetector, GameState
from src.controller import FishingController

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 终端输出（改用普通 print，确保可见） ─────────────────
def log(msg: str):
    """带时间戳的日志输出。"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


# ── 诊断：列出所有匹配窗口 ──────────────────────────────
import win32gui
_matched_windows = []
def _enum_win_cb(hwnd, _):
    if win32gui.IsWindowVisible(hwnd) and config.GAME_WINDOW_TITLE in win32gui.GetWindowText(hwnd):
        title = win32gui.GetWindowText(hwnd)
        _matched_windows.append((hwnd, title))
win32gui.EnumWindows(_enum_win_cb, None)
if _matched_windows:
    log("找到以下匹配窗口:")
    for hwnd, title in _matched_windows:
        log(f"  hwnd={hwnd}  title='{title}'")
else:
    log(f"未找到包含 '{config.GAME_WINDOW_TITLE}' 的窗口")

cap = WindowCapture(config.GAME_WINDOW_TITLE)
det = StateDetector()

if not cap.is_window_found():
    log(f"错误：找不到包含 '{config.GAME_WINDOW_TITLE}' 的窗口")
    sys.exit(1)

w, h = cap.get_window_size()
_cap_title = win32gui.GetWindowText(cap.hwnd)
log(f"已选中窗口: hwnd={cap.hwnd} title='{_cap_title}' 尺寸={w}x{h}")
log(f"输入方法: {config.INPUT_METHOD}")
log("按 F12 开始/停止  按 Ctrl+Q 退出")

bot_active = False
running = True

_KEY_TOGGLE = 0x7B  # F12
_KEY_CTRL   = 0x11  # Ctrl

_DISPLAY_W = 1280
_DISPLAY_H = 540

# ── 可视化 ───────────────────────────────────────────────
_WIN_NAME = "NTE Fishing Bot"
if config.SHOW_PREVIEW_WINDOW:
    cv2.namedWindow(_WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(_WIN_NAME, _DISPLAY_W, _DISPLAY_H)

_cap_title = win32gui.GetWindowText(cap.hwnd)

_blank = np.zeros((_DISPLAY_H, _DISPLAY_W, 3), dtype=np.uint8)
cv2.putText(_blank, "等待游戏窗口...", (50, _DISPLAY_H // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)

def _show(vis):
    """仅在预览开关打开时显示窗口。"""
    if config.SHOW_PREVIEW_WINDOW:
        cv2.imshow(_WIN_NAME, vis)

_show(_blank)

_frame_count = 0


def annotate_frame(frame, state, fl, fr, px, blue_px, slider_px, active,
                   wait_text: str = ""):
    """绘制调试信息。"""
    global _frame_count
    _frame_count += 1
    vis = frame.copy()
    fh, fw = vis.shape[:2]

    # 钓鱼条区域（黄框）
    bx1 = int(fw * config.BAR_X_START_RATIO)
    bx2 = int(fw * config.BAR_X_END_RATIO)
    by1 = int(fh * config.BAR_Y_START_RATIO)
    by2 = int(fh * config.BAR_Y_END_RATIO)
    cv2.rectangle(vis, (bx1, by1), (bx2, by2), (0, 255, 255), 2)

    # 绿色鱼滑块
    if fl is not None and fr is not None:
        cv2.rectangle(vis, (bx1 + fl, by1), (bx1 + fr, by2), (0, 255, 0), 2)
        center = bx1 + (fl + fr) // 2
        cv2.line(vis, (center, by1), (center, by2), (0, 255, 0), 1)

    # 玩家竖线（红）
    if px is not None:
        px_g = bx1 + px
        cv2.line(vis, (px_g, by1), (px_g, by2), (0, 0, 255), 3)

    # 误差方向
    if fl and fr and px:
        cx = bx1 + (fl + fr) // 2
        px_g = bx1 + px
        err = px_g - cx
        if abs(err) > 10:
            dir_text = "A <<" if err > 0 else ">> D"
            cv2.putText(vis, dir_text, (cx, by1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # 上钩检测区（蓝框）
    hx1 = int(fw * config.HOOK_X_START_RATIO)
    hx2 = int(fw * config.HOOK_X_END_RATIO)
    hy1 = int(fh * config.HOOK_Y_START_RATIO)
    hy2 = int(fh * config.HOOK_Y_END_RATIO)
    color = (255, 0, 0) if blue_px > config.BITE_BLUE_PX_THRESHOLD else (100, 100, 100)
    cv2.rectangle(vis, (hx1, hy1), (hx2, hy2), color, 2)

    # 状态文字（第1行：运行状态）
    status = f"{'RUN' if active else 'STOP'}  {state.name}  "
    status += f"蓝px={blue_px} 滑px={slider_px}  "
    if fl and fr and px:
        err = px - (fl + fr) / 2
        status += f"误差={err:.0f}"
    cv2.putText(vis, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (0, 255, 0) if active else (200, 200, 200), 2)

    # 诊断信息（第2行：窗口标题 + 帧计数）
    diag = f"帧#{_frame_count} 窗口: {_cap_title}"
    cv2.putText(vis, diag, (10, _DISPLAY_H - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

    if wait_text:
        cv2.putText(vis, wait_text, (50, _DISPLAY_H - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)

    # 缩放到显示尺寸
    if fw != _DISPLAY_W or fh != _DISPLAY_H:
        vis = cv2.resize(vis, (_DISPLAY_W, _DISPLAY_H), interpolation=cv2.INTER_LINEAR)
    return vis


# ── 主循环 ───────────────────────────────────────────────
def loop():
    global bot_active, running
    cast_at: float | None = None
    prev_state: GameState | None = None
    controller: FishingController | None = None
    waiting_for_bite = False
    needs_dismiss = False
    f12_prev = False
    last_frame = _blank.copy()
    skip_until = 0.0
    skip_reason = ""
    heartbeat = 0.0

    log("主循环开始")

    while running:
        try:
            # ═══ 1. 窗口消息处理 + 帧率控制 ═══
            # 33ms = ~30fps，足够处理窗口消息
            cv2.waitKey(33)

            # ═══ 2. 按键检测 ═══
            ctrl_now = ctypes.windll.user32.GetAsyncKeyState(_KEY_CTRL) & 0x8000
            q_now = ctypes.windll.user32.GetAsyncKeyState(0x51) & 0x8000  # Q
            if ctrl_now and q_now:
                log("按 Ctrl+Q 退出")
                running = False
                break
            f12_now = bool(ctypes.windll.user32.GetAsyncKeyState(_KEY_TOGGLE) & 0x8000)
            if f12_now and not f12_prev:
                bot_active = not bot_active
                if bot_active:
                    waiting_for_bite = False
                    needs_dismiss = False
                    cast_at = None
                log(f"{'已启动' if bot_active else '已停止'}")
            f12_prev = f12_now



            # ═══ 3. 非阻塞等待 ═══
            now = time.time()
            if now < skip_until:
                vis = annotate_frame(last_frame, prev_state or GameState.IDLE,
                                     None, None, None, 0, 0, bot_active,
                                     wait_text=skip_reason)
                _show(vis)
                continue

            # ═══ 4. 截图 ═══
            frame = cap.get_frame()
            if frame is None:
                skip_until = time.time() + 0.5
                skip_reason = "等待游戏窗口..."
                continue

            last_frame = frame.copy()
            fh, fw = frame.shape[:2]

            if controller is None:
                controller = FishingController(cap.hwnd, method=config.INPUT_METHOD)
                log(f"控制器已初始化 method={config.INPUT_METHOD}")

            # ═══ 5. 检测 ═══
            # 蓝色像素
            icon = frame[
                int(fh * config.HOOK_Y_START_RATIO):int(fh * config.HOOK_Y_END_RATIO),
                int(fw * config.HOOK_X_START_RATIO):int(fw * config.HOOK_X_END_RATIO)
            ]
            if icon.size > 0:
                hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
                blue_px = int((
                    (hsv[:, :, 0] >= config.BITE_BLUE_H_LOW) &
                    (hsv[:, :, 0] <= config.BITE_BLUE_H_HIGH) &
                    (hsv[:, :, 1] > config.BITE_BLUE_S_MIN) &
                    (hsv[:, :, 2] > config.BITE_BLUE_V_MIN)
                ).sum())
            else:
                blue_px = 0

            bar = frame[
                int(fh * config.BAR_Y_START_RATIO):int(fh * config.BAR_Y_END_RATIO),
                int(fw * config.BAR_X_START_RATIO):int(fw * config.BAR_X_END_RATIO)
            ]
            if bar.size > 0:
                bar_hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
                slider_px = int(det._slider_mask(bar_hsv).sum())
            else:
                slider_px = 0

            state = det.detect_state(frame)
            fl, fr, px = det.detect_fishing_positions(frame)

            # ═══ 6. 状态切换 ═══
            if state != prev_state:
                log(f"状态: {prev_state.name if prev_state else '-'} → {state.name}")

                if state == GameState.BITE and bot_active:
                    log("上钩! 按 F")
                    if controller:
                        controller.press_cast()
                    skip_until = time.time() + 0.3
                    skip_reason = "等待上钩确认..."
                    vis = annotate_frame(frame, state, fl, fr, px,
                                         blue_px, slider_px, bot_active,
                                         wait_text="上钩! 按 F...")
                    _show(vis)
                    prev_state = state
                    continue

                if state == GameState.IDLE and prev_state == GameState.FISHING and bot_active:
                    needs_dismiss = True
                    dismiss_wait = random.uniform(5, 8)
                    skip_until = time.time() + dismiss_wait
                    skip_reason = f"钓鱼结束 等待结算界麵…({dismiss_wait:.0f}s)"
                    vis = annotate_frame(frame, state, fl, fr, px,
                                         blue_px, slider_px, bot_active,
                                         wait_text="钓鱼结束 等待结算")
                    _show(vis)
                    prev_state = state
                    continue

                prev_state = state

            # ═══ 7. 自动钓鱼 ═══
            if bot_active and controller is not None:
                if state == GameState.FISHING:
                    waiting_for_bite = False
                    if fl is not None and fr is not None and px is not None:
                        error = px - (fl + fr) / 2
                        log(f"[FISHING] 误差={error:.0f} → 按{'A' if error > 0 else 'D'}")
                        controller.hold_direction(error)
                    else:
                        log(f"[FISHING] 检测失败")
                        controller.release_all()

                elif state == GameState.BITE:
                    log(f"[BITE] 上钩了")
                    controller.release_all()

                else:  # IDLE
                    controller.release_all()
                    if needs_dismiss:
                        log(f"[IDLE] 鼠标点击边缘关闭结算界面")
                        cx = int(fw * config.BITE_CLICK_X_RATIO) + random.randint(-30, 30)
                        cy = int(fh * config.BITE_CLICK_Y_RATIO) + random.randint(-30, 30)
                        controller.click_bite(cx, cy)
                        needs_dismiss = False
                        waiting_for_bite = False
                        skip_until = time.time() + config.RESULT_WAIT_SEC
                        skip_reason = "结算关闭中..."
                        vis = annotate_frame(frame, state, fl, fr, px,
                                             blue_px, slider_px, bot_active,
                                             wait_text="关闭结算")
                        _show(vis)
                        continue
                    elif not waiting_for_bite:
                        log(f"[IDLE] → 抛竿 hwnd={controller.hwnd}")
                        controller.press_cast()
                        cast_at = time.time()
                        waiting_for_bite = True
                        skip_until = time.time() + config.CAST_WAIT_SEC
                        skip_reason = "抛竿后等待..."
                        vis = annotate_frame(frame, state, fl, fr, px,
                                             blue_px, slider_px, bot_active,
                                             wait_text="抛竿中...")
                        _show(vis)
                        continue
                    else:
                        wait = time.time() - cast_at
                        if wait > config.MAX_WAIT_SEC:
                            log(f"[IDLE] 超时 {wait:.0f}s，重新抛竿")
                            controller.press_cast()
                            cast_at = time.time()
                            skip_until = time.time() + config.CAST_WAIT_SEC
                            skip_reason = "超时重抛..."
                            vis = annotate_frame(frame, state, fl, fr, px,
                                                 blue_px, slider_px, bot_active,
                                                 wait_text="超时重抛")
                            _show(vis)
                            continue
            else:
                pass  # 停止模式，不输出每帧信息

            # ═══ 8. 显示 ═══
            vis = annotate_frame(frame, state, fl, fr, px, blue_px, slider_px, bot_active)
            _show(vis)

            # 心跳（每 5 秒确认循环活着）
            if time.time() - heartbeat > 5:
                heartbeat = time.time()
                log(f"心跳: state={state.name} active={bot_active} 蓝px={blue_px}")

        except Exception:
            traceback.print_exc()
            running = False
            break

    # 清理
    if controller is not None:
        controller.release_all()
    if config.SHOW_PREVIEW_WINDOW:
        cv2.destroyWindow(_WIN_NAME)
    log("已退出")


try:
    loop()
except KeyboardInterrupt:
    if config.SHOW_PREVIEW_WINDOW:
        cv2.destroyWindow(_WIN_NAME)
    log("已退出")
