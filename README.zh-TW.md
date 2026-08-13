# nte-fishing

[English](README.md)

適用於異環／异环與 NTE 的 Windows 自動釣魚工具。程式會動態尋找遊戲
視窗、在背景擷取畫面，並透過精簡的狀態機執行完整釣魚流程。

## 執行方式

需要 Python 3.11 以上版本。

```powershell
uv sync
uv run run.py
```

`run.py` 是正式入口。可從系統匣選單或按 F12 啟動／停止。關閉 OpenCV
預覽視窗只會停用預覽，不會讓釣魚操作停止。

## 運作流程

Runtime 每輪只擷取一次完整 client frame，狀態機再按需觸發 Detector：

```text
bar
├─ 找到   → fish-area segments → marker → LEFT / RIGHT / RELEASE
└─ 未找到或證據不完整 → result → hook
                         │        └─ 依排程點按 F
                         └─ 點按 ESC，3 秒內最多一次
```

Runtime 只保留三個狀態：`NO_WINDOW`、`SEARCHING`、`FISHING`。只有
`FISHING` 使用高刷新率，其餘狀態使用一般輪詢間隔。

## 設定

將 `.env.example` 複製為 `.env` 後調整；本機 `.env` 不會被 Git 追蹤。

輸入後端與方向鍵配置互相獨立：

```env
INPUT_FUNCTION=sendmessage   # sendmessage、postmessage、foreground
INPUT_ASSIGNMENT=ad          # ad、arrows
SEND_ACTIVATION_HINTS=false  # 實驗性的 WM_ACTIVATE/WM_SETFOCUS 提示
```

`sendmessage` 與 `postmessage` 可以對背景 HWND 發送訊息，但遊戲仍可能在
非前景時主動忽略輸入。`foreground` 會先啟用遊戲視窗，再使用 SendInput。

### 語言與結算模板

視窗標題以語言代碼映射，結算圖片則直接由語言代碼推導：

```text
<lang> → WINDOW_TITLES_<LANG> → assets/click_bank_<lang>.png
```

目前預設：

```env
LANGUAGES=zh,zhtw
WINDOW_TITLES_ZH=异环,異環
WINDOW_TITLES_ZHTW=NTE
```

例如要新增日文：

1. 在 `LANGUAGES` 加入 `jp`。
2. 設定 `WINDOW_TITLES_JP`，多個標題以逗號分隔。
3. 加入 `assets/click_bank_jp.png`。

英文可使用相同規則加入 `click_bank_en.png`。不需修改 Python；當標題
aliases 重疊時，以 `LANGUAGES` 順序決定優先級，而精確標題匹配永遠優先
於部分匹配。

## 專案結構

```text
assets/                 模板圖片與程式圖示
src/state_machine.py    probe 順序、狀態、計時與 actions
src/detector.py         單 frame、按需執行的 CV probes
src/runtime.py          capture／decision／input loop 與 debug render
src/padinput.py         輸入後端及 A/D／方向鍵配置
src/capture.py          HWND 更新與畫面擷取
run.py                  正式入口
```

## 測試與打包

```powershell
uv run pytest
uv run pyinstaller nte-fishing.spec
```

PyInstaller spec 會從 `assets/` 收入所有正式模板。
