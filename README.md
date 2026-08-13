# nte-fishing

[繁體中文](README.zh-TW.md)

A Windows fishing helper for 异环/異環 and NTE. It locates the game window
dynamically, captures it in the background, and drives the fishing loop through
a small state machine.

## Run

Python 3.11 or newer is required.

```powershell
uv sync
uv run run.py
```

`run.py` is the production entry point. Use the tray menu or F12 to start and
stop the runtime. Closing the OpenCV preview only disables the preview; it does
not stop fishing.

## How it works

The core loop captures one full client frame and lets the state machine request
lazy vision probes in this order:

```text
bar
├─ found   → fish-area segments → marker → LEFT / RIGHT / RELEASE
└─ missing or incomplete → result → hook
                            │        └─ tap F on schedule
                            └─ tap ESC, throttled to once per 3 seconds
```

Only three runtime states are used: `NO_WINDOW`, `SEARCHING`, and `FISHING`.
Fishing runs at the high refresh interval; all other states use the normal loop
interval.

## Configuration

Copy `.env.example` to `.env`. The local `.env` is ignored by Git.

Input transport and direction assignment are independent:

```env
INPUT_FUNCTION=sendmessage   # sendmessage, postmessage, foreground
INPUT_ASSIGNMENT=ad          # ad, arrows
SEND_ACTIVATION_HINTS=false  # experimental WM_ACTIVATE/WM_SETFOCUS hints
```

`sendmessage` and `postmessage` can target a background HWND, but a game may
still ignore input while it is not foreground. `foreground` uses SendInput after
activating the game window.

### Languages and result templates

Window titles are mapped by language. The result template path is derived from
the language key:

```text
<lang> → WINDOW_TITLES_<LANG> → assets/click_bank_<lang>.png
```

Current defaults:

```env
LANGUAGES=zh,zhtw
WINDOW_TITLES_ZH=异环,異環
WINDOW_TITLES_ZHTW=NTE
```

To add Japanese support, for example:

1. Add `jp` to `LANGUAGES`.
2. Set `WINDOW_TITLES_JP` to comma-separated title aliases.
3. Add `assets/click_bank_jp.png`.

The same convention supports `click_bank_en.png` or any other language key
without changing Python code. Language order also determines priority when
aliases overlap; exact title matches are always preferred over partial matches.

## Project layout

```text
assets/                 templates and application icon
src/state_machine.py    probe order, states, timers, and actions
src/detector.py         single-frame lazy CV probes
src/runtime.py          capture/decision/input loop and debug rendering
src/padinput.py         input backend and A/D or arrow assignment
src/capture.py          HWND discovery integration and frame capture
run.py                  production entry point
```

## Tests and packaging

```powershell
uv run pytest
uv run pyinstaller nte-fishing.spec
```

The PyInstaller spec bundles the templates from `assets/`.
