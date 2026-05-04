# src/main.py
import os
import time
import logging
import random
import threading
import cv2
import numpy as np
import config
from src.capture import WindowCapture
from src.detector import StateDetector, GameState
from src.controller import FishingController

log = logging.getLogger(__name__)

_DIAG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'nte-fishing')
os.makedirs(_DIAG_DIR, exist_ok=True)
_DIAG_LOG = os.path.join(_DIAG_DIR, 'diag.log')


def _diag(msg: str):
    with open(_DIAG_LOG, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%H:%M:%S')} [main] {msg}\n")


# ── 调试可视化 ─────────────────────────────────────────
_DISPLAY_W = 1280
_DISPLAY_H = 540


def annotate_frame(frame, state, fl, fr, px, blue_px, slider_px, active, wait_text=""):
    """绘制调试信息到画面（from debug_run.py）。"""
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
    if fl is not None and fr is not None and px is not None:
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

    # 状态文字
    status = f"{'RUN' if active else 'STOP'}  {state.name}  "
    status += f"蓝px={blue_px} 滑px={slider_px}  "
    if fl is not None and fr is not None and px is not None:
        err = px - (fl + fr) / 2
        status += f"误差={err:.0f}"
    cv2.putText(vis, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (0, 255, 0) if active else (200, 200, 200), 2)

    if wait_text:
        cv2.putText(vis, wait_text, (50, fh - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)

    # 缩放到统一显示尺寸
    if fw != _DISPLAY_W or fh != _DISPLAY_H:
        vis = cv2.resize(vis, (_DISPLAY_W, _DISPLAY_H), interpolation=cv2.INTER_LINEAR)
    return vis


class FishingBot:

    def __init__(self):
        _diag("FishingBot.__init__")
        self.capturer = WindowCapture(config.GAME_WINDOW_TITLE)
        self.detector = StateDetector()
        self.controller: FishingController | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_log: str = "已停止"
        # 调试窗口
        self._preview_enabled = False
        self._latest_vis: np.ndarray | None = None
        # 结算卡死检测
        self._bite_cycle_count = 0
        _diag(f"  hwnd={self.capturer.hwnd} WindowCapture OK")

    def start(self):
        _diag("start() 被调用")
        if self._thread is not None and self._thread.is_alive():
            _diag("  start: 已经在运行，跳过")
            return
        self._stop_event.clear()
        self._state_log = "运行中"
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        # 调试窗口显示线程（独立循环）
        threading.Thread(target=self._display_loop, daemon=True).start()
        log.info("Bot 已启动")
        _diag("  _loop 线程已启动")

    def stop(self):
        self._stop_event.set()
        _diag("stop() 被调用")
        log.info("Bot 停止信号已发送")

    def toggle(self):
        if self.is_running:
            self.stop()
        else:
            self.start()

    def toggle_preview(self):
        self._preview_enabled = not self._preview_enabled
        _diag(f"preview → {self._preview_enabled}")

    @property
    def preview_enabled(self) -> bool:
        return self._preview_enabled

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set() and (
            self._thread is not None and self._thread.is_alive()
        )

    @property
    def status(self) -> str:
        return self._state_log

    def _loop(self):
        _diag("_loop 线程开始运行")
        cast_at: float | None = None
        prev_state: GameState | None = None
        waiting_for_bite = False
        needs_dismiss = False
        skip_until = 0.0
        loop_count = 0

        while not self._stop_event.is_set():
            loop_count += 1

            if time.time() < skip_until:
                time.sleep(config.LOOP_INTERVAL)
                continue

            frame = self.capturer.get_frame()
            if frame is None:
                self._state_log = "找不到游戏窗口"
                if loop_count % 30 == 0:
                    _diag(f"get_frame() 返回 None (第{loop_count}次)")
                time.sleep(1.0)
                continue

            if loop_count == 1:
                _diag(f"首帧到达: shape={frame.shape if frame is not None else 'None'} mean={frame.mean():.1f}")

            if self.controller is None:
                w, h = self.capturer.get_window_size()
                _diag(f"创建 FishingController hwnd={self.capturer.hwnd} method={config.INPUT_METHOD} 尺寸={w}x{h}")
                self.controller = FishingController(
                    self.capturer.hwnd, method=config.INPUT_METHOD)
                _diag(f"FishingController 创建完成 method={self.controller.method}")

            state = self.detector.detect_state(frame)

            if state != prev_state:
                log.info("状态切换: %s → %s", prev_state.name if prev_state else "None", state.name)
                _diag(f"状态切换: {prev_state.name if prev_state else 'None'} → {state.name}")

            fl = fr = px = None

            # 结算卡死检测：连续 BITE 无 FISHING → 点窗口中央
            if state == GameState.FISHING:
                self._bite_cycle_count = 0
            elif state == GameState.BITE and prev_state != GameState.BITE:
                self._bite_cycle_count += 1

            if state == GameState.FISHING:
                waiting_for_bite = False
                self._state_log = "钓鱼中"
                fl, fr, px = self.detector.detect_fishing_positions(frame)
                if fl is not None and fr is not None and px is not None:
                    error = px - (fl + fr) / 2
                    self.controller.hold_direction(error, px, fl, fr)
                else:
                    self.controller.release_all()

            elif state == GameState.BITE:
                self.controller.release_all()

                # 卡死超过阈值 → 点窗口中央（结算界面关不掉）
                if self._bite_cycle_count >= config.BITE_STUCK_THRESHOLD:
                    w, h = self.capturer.get_window_size()
                    cx = int(w * 0.5) + random.randint(-80, 80)
                    cy = int(h * 0.5) + random.randint(-50, 50)
                    _diag(f"结算卡死 {self._bite_cycle_count} 次，点击窗口中央 ({cx},{cy})")
                    self.controller.click_bite(cx, cy)
                    self._bite_cycle_count = 0
                    needs_dismiss = False
                    waiting_for_bite = False
                    skip_until = time.time() + config.RESULT_WAIT_SEC
                    prev_state = state
                    continue

                self._state_log = "上钩！按F"
                _diag("BITE → press_cast()")
                self.controller.press_cast()
                skip_until = time.time() + 0.3

            elif state == GameState.RESULT:
                self.controller.release_all()
                waiting_for_bite = False
                self._bite_cycle_count = 0

                # 首次进入结算：等待后点击关闭
                if state != prev_state:
                    dismiss_wait = random.uniform(5, 8)
                    skip_until = time.time() + dismiss_wait
                    self._state_log = f"结算 ({dismiss_wait:.0f}s)"
                    _diag(f"结算界面，等待 {dismiss_wait:.0f}s 后关闭")
                    prev_state = state
                    continue

                if time.time() >= skip_until:
                    w, h = self.capturer.get_window_size()
                    cx = int(w * config.BITE_CLICK_X_RATIO) + random.randint(-30, 30)
                    cy = int(h * config.BITE_CLICK_Y_RATIO) + random.randint(-30, 30)
                    _diag(f"关闭结算，点击 ({cx}, {cy})")
                    self.controller.click_bite(cx, cy)
                    skip_until = time.time() + config.RESULT_WAIT_SEC
                    prev_state = state
                    continue

                self._state_log = "结算中"

            else:  # IDLE
                self.controller.release_all()

                now = time.time()
                if not waiting_for_bite:
                    self._state_log = "抛竿中"
                    _diag("IDLE → press_cast()")
                    self.controller.press_cast()
                    cast_at = now
                    waiting_for_bite = True
                    skip_until = time.time() + config.CAST_WAIT_SEC
                    prev_state = state
                    continue

                # 等待上钩（超时重抛）
                wait = now - cast_at
                if wait > config.MAX_WAIT_SEC:
                    _diag(f"超时 {wait:.0f}s，重新抛竿")
                    self.controller.press_cast()
                    cast_at = now
                    skip_until = time.time() + config.CAST_WAIT_SEC
                    self._state_log = "超时重抛"
                    prev_state = state
                    continue

                self._state_log = f"等待上钩 ({wait:.0f}s)"

            prev_state = state

            # ── 调试可视化 ──────────────────────────────
            if self._preview_enabled:
                fh, fw = frame.shape[:2]
                # 蓝色像素（上钩检测）
                icon = frame[
                    int(fh * config.HOOK_Y_START_RATIO):int(fh * config.HOOK_Y_END_RATIO),
                    int(fw * config.HOOK_X_START_RATIO):int(fw * config.HOOK_X_END_RATIO)
                ]
                if icon.size > 0:
                    hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
                    blue_px = int(((hsv[:, :, 0] >= config.BITE_BLUE_H_LOW) &
                                   (hsv[:, :, 0] <= config.BITE_BLUE_H_HIGH) &
                                   (hsv[:, :, 1] > config.BITE_BLUE_S_MIN) &
                                   (hsv[:, :, 2] > config.BITE_BLUE_V_MIN)).sum())
                else:
                    blue_px = 0
                # 滑块像素
                bar = frame[
                    int(fh * config.BAR_Y_START_RATIO):int(fh * config.BAR_Y_END_RATIO),
                    int(fw * config.BAR_X_START_RATIO):int(fw * config.BAR_X_END_RATIO)
                ]
                if bar.size > 0:
                    bar_hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
                    slider_px = int(self.detector._slider_mask(bar_hsv).sum())
                else:
                    slider_px = 0

                self._latest_vis = annotate_frame(
                    frame, state, fl, fr, px,
                    blue_px, slider_px, True,
                    wait_text=self._state_log,
                )

        if self.controller is not None:
            self.controller.release_all()
        self._state_log = "已停止"
        _diag("_loop 线程退出")

    def _display_loop(self):
        """后台线程：OpenCV 调试窗口。"""
        WIN_NAME = "NTE Fishing Bot"
        win_shown = False
        while not self._stop_event.is_set():
            if self._preview_enabled:
                if not win_shown:
                    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(WIN_NAME, _DISPLAY_W, _DISPLAY_H)
                    win_shown = True
                if self._latest_vis is not None:
                    cv2.imshow(WIN_NAME, self._latest_vis)
                key = cv2.waitKey(33) & 0xFF
                if key == ord('q'):
                    self._preview_enabled = False
                try:
                    if cv2.getWindowProperty(WIN_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        self._preview_enabled = False
                except:
                    pass
            else:
                if win_shown:
                    try:
                        cv2.destroyWindow(WIN_NAME)
                    except:
                        pass
                    win_shown = False
                time.sleep(0.1)
        if win_shown:
            try:
                cv2.destroyWindow(WIN_NAME)
            except:
                pass
