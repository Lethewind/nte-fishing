# src/detector.py
import os
import sys
from enum import Enum, auto
import cv2
import numpy as np
from PIL import Image
import config


class GameState(Enum):
    IDLE = auto()
    BITE = auto()
    FISHING = auto()
    RESULT = auto()   # 结算/结果界面


def _try_load_template(filename: str) -> np.ndarray | None:
    """加载模板图片，兼容 PyInstaller 打包后的路径和 cv2 解码问题。"""
    # 定位资源目录
    if hasattr(sys, '_MEIPASS'):
        base = os.path.join(sys._MEIPASS, 'src')
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    path = os.path.join(base, filename)

    # 优先 cv2 直接读（最快）
    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if tpl is not None:
        return tpl

    # cv2 失败 → 用 PIL 读再转（解决打包后 PNG 解码 DLL 缺失问题）
    try:
        pil_img = Image.open(path).convert('L')
        tpl = np.array(pil_img, dtype=np.uint8)
        return tpl
    except Exception:
        return None


class StateDetector:

    def __init__(self):
        self._marker_template = _try_load_template('marker_template.png')
        self._result_template = _try_load_template('click_bank_close.png')
        self._last_px: int | None = None

    def detect_state(self, frame: np.ndarray) -> GameState:
        if self._is_bar_visible(frame):
            return GameState.FISHING
        # 结算界面检测优先于 BITE（结算也可能有蓝色图标）
        if self._is_result_screen(frame):
            return GameState.RESULT
        if self._is_bite(frame):
            return GameState.BITE
        return GameState.IDLE

    def detect_fishing_positions(self, frame: np.ndarray) -> tuple[int | None, int | None, int | None]:
        """返回 (fish_left, fish_right, player_x)。"""
        h, w = frame.shape[:2]
        bx1 = int(w * config.BAR_X_START_RATIO)
        bx2 = int(w * config.BAR_X_END_RATIO)
        by1 = int(h * config.BAR_Y_START_RATIO)
        by2 = int(h * config.BAR_Y_END_RATIO)

        bar = frame[by1:by2, bx1:bx2]
        bar_hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)

        fish_left, fish_right = self._find_slider(bar_hsv)

        # 竖线搜索区域比滑块区域宽 3%，确保边缘也能检测到
        mx1 = int(w * max(0, config.BAR_X_START_RATIO - 0.03))
        mx2 = int(w * min(1.0, config.BAR_X_END_RATIO + 0.03))
        marker_region = frame[by1:by2, mx1:mx2]
        marker_hsv = cv2.cvtColor(marker_region, cv2.COLOR_BGR2HSV)
        margin = bx1 - mx1  # bar 坐标 = marker 坐标 - margin

        # 玩家竖线：先模板匹配，再颜色法，最后亮度差降级
        player_x = self._find_marker_tmpl(frame) if fish_left is not None else None
        if player_x is not None:
            player_x = player_x - bx1  # 转 bar 坐标系
        else:
            player_x = self._find_marker_color(marker_hsv) if fish_left is not None else None
            if player_x is not None:
                player_x = player_x - margin  # 从 marker 区域坐标转 bar 坐标
        if player_x is None:
            # 颜色法也失败时，降级为亮度差法
            player_x = self._find_marker_brightness(bar_hsv) if fish_left is not None else None

        # 过滤假阳性
        if fish_left is not None and fish_right is not None and player_x is not None:
            fish_center = (fish_left + fish_right) / 2
            if abs(player_x - fish_center) > config.PLAYER_MAX_DIST_FROM_FISH:
                player_x = None

        # 时间平滑：限制每帧最大位移 60px（防跳变，同时允许随真实移动逐渐到达边缘）
        if fish_left is not None:
            if player_x is not None:
                if self._last_px is not None:
                    diff = player_x - self._last_px
                    if abs(diff) > 60:
                        player_x = self._last_px + (60 if diff > 0 else -60)
                self._last_px = player_x
            elif self._last_px is not None:
                # 本帧未检测到竖线，用上一帧位置兜底（避免短暂检测失败就松手跑鱼）
                player_x = self._last_px
        else:
            self._last_px = None  # 钓鱼条消失时重置，避免跨会话干扰

        return fish_left, fish_right, player_x

    def _is_bar_visible(self, frame: np.ndarray) -> bool:
        h, w = frame.shape[:2]
        bar = frame[
            int(h * config.BAR_Y_START_RATIO):int(h * config.BAR_Y_END_RATIO),
            int(w * config.BAR_X_START_RATIO):int(w * config.BAR_X_END_RATIO)
        ]
        hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
        mask = self._slider_mask(hsv)
        return int(mask.sum()) > config.SLIDER_PX_THRESHOLD

    def _is_bite(self, frame: np.ndarray) -> bool:
        h, w = frame.shape[:2]
        icon = frame[
            int(h * config.HOOK_Y_START_RATIO):int(h * config.HOOK_Y_END_RATIO),
            int(w * config.HOOK_X_START_RATIO):int(w * config.HOOK_X_END_RATIO)
        ]
        hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
        blue_mask = (
            (hsv[:, :, 0] >= config.BITE_BLUE_H_LOW) &
            (hsv[:, :, 0] <= config.BITE_BLUE_H_HIGH) &
            (hsv[:, :, 1] > config.BITE_BLUE_S_MIN) &
            (hsv[:, :, 2] > config.BITE_BLUE_V_MIN)
        )
        return int(blue_mask.sum()) > config.BITE_BLUE_PX_THRESHOLD

    def _is_result_screen(self, frame: np.ndarray) -> bool:
        """多尺度模板匹配识别结算文字"点击空白区域关闭"（兼容不同分辨率）。"""
        if self._result_template is None:
            return False
        h, w = frame.shape[:2]
        sy1 = int(h * config.RESULT_SEARCH_Y_START)
        sy2 = int(h * config.RESULT_SEARCH_Y_END)
        sx1 = int(w * config.RESULT_SEARCH_X_START)
        sx2 = int(w * config.RESULT_SEARCH_X_END)
        if sy2 - sy1 < self._result_template.shape[0] or sx2 - sx1 < self._result_template.shape[1]:
            return False
        region = frame[sy1:sy2, sx1:sx2]
        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        t_h, t_w = self._result_template.shape[:2]
        # 分辨率自适应：从 0.6x 到 1.6x 搜索（覆盖 720p → 4K）
        for scale in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6):
            sw, sh = int(t_w * scale), int(t_h * scale)
            if sw > region_gray.shape[1] or sh > region_gray.shape[0]:
                continue
            scaled = cv2.resize(self._result_template, (sw, sh), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(region_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= config.RESULT_TEMPLATE_THRESHOLD:
                return True
        return False

    def _slider_mask(self, hsv: np.ndarray) -> np.ndarray:
        return (
            (hsv[:, :, 0] >= config.SLIDER_H_LOW) &
            (hsv[:, :, 0] <= config.SLIDER_H_HIGH) &
            (hsv[:, :, 1] > config.SLIDER_S_MIN) &
            (hsv[:, :, 2] > config.SLIDER_V_MIN)
        )

    def _find_slider(self, bar_hsv: np.ndarray) -> tuple[int | None, int | None]:
        mask = self._slider_mask(bar_hsv)
        cols = np.where(mask.any(axis=0))[0]
        if len(cols) == 0:
            return None, None
        # 分组为连续段，取最宽的段（右侧常有1-4px虚假段）
        segments: list[tuple[int, int]] = []
        s = p = int(cols[0])
        for c in cols[1:]:
            if c - p > 5:
                segments.append((s, p))
                s = int(c)
            p = int(c)
        segments.append((s, p))
        best = max(segments, key=lambda g: g[1] - g[0])
        return best[0], best[1]

    def _marker_mask(self, hsv: np.ndarray) -> np.ndarray:
        """玩家竖线颜色掩码（黄色/亮白）。"""
        return (
            (hsv[:, :, 0] >= config.MARKER_H_LOW) &
            (hsv[:, :, 0] <= config.MARKER_H_HIGH) &
            (hsv[:, :, 1] > config.MARKER_S_MIN) &
            (hsv[:, :, 2] >= config.MARKER_V_MIN)
        )

    def _find_marker_color(self, bar_hsv: np.ndarray) -> int | None:
        """通过颜色掩码找玩家竖线（比亮度差法可靠）。"""
        mask = self._marker_mask(bar_hsv)
        # 每列需足够标记色像素才算有效候选（排除远景灯光仅 1–2px 的噪点）
        col_counts = mask.sum(axis=0)
        cols = np.where(col_counts >= config.MARKER_MIN_HEIGHT)[0]
        if len(cols) == 0:
            return None
        # 分组连续段
        segments: list[tuple[int, int]] = []
        s = p = int(cols[0])
        for c in cols[1:]:
            if c - p > 3:
                segments.append((s, p))
                s = int(c)
            p = int(c)
        segments.append((s, p))
        # 竖线很细，取最窄的段
        narrow = [(s, p) for s, p in segments if (p - s) < config.MARKER_MAX_WIDTH]
        if not narrow:
            return None
        best = min(narrow, key=lambda g: g[1] - g[0])
        return int(np.mean(best))

    def _find_marker_tmpl(self, frame: np.ndarray) -> int | None:
        """模板匹配找玩家竖线，返回全局 x 坐标。"""
        if self._marker_template is None:
            return None
        h, w = frame.shape[:2]
        # 搜索区域略大于 bar（补偿 y 偏移）
        sy1 = max(0, int(h * (config.BAR_Y_START_RATIO - 0.01)))
        sy2 = min(h, int(h * (config.BAR_Y_END_RATIO + 0.01)))
        sx1 = max(0, int(w * (config.BAR_X_START_RATIO - 0.02)))
        sx2 = min(w, int(w * (config.BAR_X_END_RATIO + 0.02)))
        region = frame[sy1:sy2, sx1:sx2]
        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(region_gray, self._marker_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < 0.6:  # 匹配度不足
            return None
        return max_loc[0] + sx1  # 全局 x

    def _find_marker_brightness(self, bar_hsv: np.ndarray) -> int | None:
        """亮度差法找竖线（降级方案），返回 bar 内 x 坐标。"""
        bar_h, bar_w = bar_hsv.shape[:2]
        v = bar_hsv[:, :, 2].astype(float)
        # 零化绿色鱼滑块像素，避免滑块边缘被误检为玩家竖线
        v[self._slider_mask(bar_hsv)] = 0
        col_avg = v.mean(axis=0)
        diff = np.zeros(bar_w)
        for i in range(5, bar_w - 5):
            diff[i] = col_avg[i] - np.mean([col_avg[i - 5], col_avg[i + 5]])

        ix0 = int(bar_w * config.MARKER_INNER_X_START_RATIO)
        ix1 = int(bar_w * config.MARKER_INNER_X_END_RATIO)
        inner_diff = diff[ix0:ix1]

        threshold = np.percentile(inner_diff, 95)
        cols = np.where(inner_diff >= threshold)[0]
        if len(cols) == 0:
            return None

        groups = []
        s, p = int(cols[0]), int(cols[0])
        for c in cols[1:]:
            if c - p > 3:
                groups.append((s, p))
                s = int(c)
            p = int(c)
        groups.append((s, p))

        narrow = [(s, p) for s, p in groups if (p - s) < config.MARKER_MAX_WIDTH]
        if not narrow:
            best = int(inner_diff.argmax())
            if inner_diff[best] > 2:
                return best + ix0
            return None
        best = min(narrow, key=lambda g: g[1] - g[0])
        return int(np.mean(best)) + ix0
