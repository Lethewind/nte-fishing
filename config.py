GAME_WINDOW_TITLE = "异环"
TOGGLE_HOTKEY = "f12"
LOOP_INTERVAL = 0.033        # 主循环间隔（秒），约 30fps

# 钓鱼条检测区域（相对于窗口尺寸的比例）
BAR_Y_START_RATIO = 0.05     # 竖线 Y 轴起始
BAR_Y_END_RATIO   = 0.18     # 竖线 Y 轴结束
BAR_X_START_RATIO = 0.15
BAR_X_END_RATIO   = 0.85

# 鱼的滑块颜色（HSV，OpenCV 0-179 range）
SLIDER_H_LOW  = 75
SLIDER_H_HIGH = 90
SLIDER_S_MIN  = 150
SLIDER_V_MIN  = 180
SLIDER_PX_THRESHOLD = 200    # 最少像素数才判定条形可见

# 玩家竖线颜色
MARKER_H_LOW  = 15
MARKER_H_HIGH = 45
MARKER_S_MIN  = 80
MARKER_V_MIN  = 200
MARKER_MAX_WIDTH = 20        # 竖线宽度上限（像素）
MARKER_MIN_HEIGHT = 8         # 每列最低标记色像素数（过滤远处灯光干扰）
MARKER_INNER_X_START_RATIO = 0.10   # 排除左侧图标区（相对 bar 宽度）
MARKER_INNER_X_END_RATIO   = 0.94   # 排除右侧图标区（相对 bar 宽度）

# 钩子图标区域（相对比例）
HOOK_Y_START_RATIO = 0.82
HOOK_Y_END_RATIO   = 0.95
HOOK_X_START_RATIO = 0.89
HOOK_X_END_RATIO   = 0.97
BITE_BLUE_H_LOW    = 100     # 上钩蓝圈 HSV Hue 下限
BITE_BLUE_H_HIGH   = 130     # 上钩蓝圈 HSV Hue 上限
BITE_BLUE_S_MIN    = 150     # 上钩蓝圈最低饱和度
BITE_BLUE_V_MIN    = 150     # 上钩蓝圈最低亮度
BITE_BLUE_PX_THRESHOLD = 500 # 亮蓝像素数超过此值 → 上钩（idle ≈ 0，bite > 1000）

# 结算文字识别（模板匹配 "点击空白区域关闭"）
RESULT_SEARCH_X_START = 0.20   # 搜索区域：屏幕底部偏中央
RESULT_SEARCH_X_END   = 0.80
RESULT_SEARCH_Y_START = 0.80
RESULT_SEARCH_Y_END   = 0.95
RESULT_TEMPLATE_THRESHOLD = 0.6  # 模板匹配阈值（0~1），越高越严格

# 结算关闭点击位置（窗口相对坐标比例）
BITE_CLICK_X_RATIO = 0.5
BITE_CLICK_Y_RATIO = 0.5

# 结算卡死检测：连续 BITE 循环超过此阈值 → 强制窗口中央点击
BITE_STUCK_THRESHOLD = 6

PLAYER_MAX_DIST_FROM_FISH = 400  # 竖线距鱼滑块中心超过此值视为假阳性

# 按键控制参数
# 缓动函数控制参数
# easing_delta = -(竖线 - 鱼中心) * EASING_FACTOR
# |easing_delta| > EASING_RELEASE_THRESHOLD 时按键，否则松手
EASING_FACTOR           = 0.12   # 缓动系数，越小越平滑（推荐 0.08~0.20）
EASING_RELEASE_THRESHOLD = 3     # 缓动 delta 松手阈值
MISS_MAX_ERROR          = 250    # 误差超过此值视为脱钩（像素）

# 旧式死区控制（保留未用，以后可能切换）
# DEAD_ZONE = 10
# INNER_DEAD_ZONE = 25

KEY_SCALE                = 1.0   # 按键时长系数（ms/px）
KEY_MAX_DURATION         = 0.15  # 单次最大按键时长（秒）
KEY_MIN_DURATION         = 0.01  # 单次最小按键时长（秒）

# 输入注入方法
#   "postmessage"  — PostMessageW（幕后运行，不影响前台窗口）
#   "sendmessage"  — SendMessageW（同步等待处理，兼容性略好）
#   "foreground"   — 窗口置前 + SendInput（影响前台，但兼容性最好）
#   "arrow_pm"     — 方向键 PostMessage（如果游戏绑定的是方向键）
#INPUT_METHOD = "postmessage"
INPUT_METHOD = "foreground"
# 状态机时序
CAST_WAIT_SEC    = 1.0       # 抛竿后等待时间（秒）
END_WAIT_SEC     = 5.0       # 钓鱼结束后等待结果界面出现（秒）
RESULT_WAIT_SEC  = 1.0       # 按 ESC 后等待界面关闭（秒）
MAX_WAIT_SEC     = 60.0      # 等待上钩超时（秒），超时重新抛竿

# 启动倒计时（秒）：给用户切换到游戏窗口的时间
STARTUP_DELAY_SEC = 5

# 是否显示 OpenCV 预览窗口（调试用）
SHOW_PREVIEW_WINDOW = False
