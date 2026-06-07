# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Desktop Pet

PySide6 桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆角色，通过状态机驱动交互和动画。

## Commands

```bash
# 运行
.venv/Scripts/python main.py

# 安装依赖
.venv/Scripts/python -m pip install -r requirements.txt

# Nuitka 打包为独立 exe
.venv/Scripts/python -m nuitka main.py \
    --standalone \
    --enable-plugin=pyside6 \
    --include-data-dir=images=images \
    --windows-console-mode=disable \
    --output-dir=dist \
    --product-name=DesktopPet \
    --file-version=1.0.0 \
    --msvc=latest
```

Virtual env: `.venv/` (Python 3.13, PySide6 6.11)

## Architecture

Single-file application (`main.py`) with one class `DesktopPet(QWidget)`.

### State machine

```
stand ──10min idle──→ lazy
  │                      │
  ├─left click───────────┤
  ▼                      ▼
 cute/scaried      cute/scaried/apologize
 (1.5s auto return)    (1.5s auto return)
  │                      │
  └──────────┬───────────┘
             ▼
           stand
        [right-click menu → 游戏]
        cute → 玩家选择 → stone/scissors/paper (1.5s) → win/lose/draw (2s) → stand
```

### Key methods

| Method | Purpose |
|--------|---------|
| `_setup_window()` | Frameless, transparent, always-on-top |
| `_load_images()` | Loads `images/<role>--<state>.png` into `self.images` dict |
| `_change_state(new_state)` | State transition, resizes window to sprite size |
| `_trigger_interaction()` | Random reaction on click (probabilities depend on current state) |
| `_float_offset()` | Y-axis bobbing animation per state (sinusoidal) |
| `_start_game()` / `_end_game()` | Rock-paper-scissors game loop |

### Timers

- **Animation**: 60 FPS (16ms), drives `_tick()` → `paintEvent()`
- **Idle**: 10 min, transitions `stand` → `lazy`
- **State timeout**: 1.5s single-shot, returns to `stand` after triggered states
- **Game timer**: single-shot, drives game phase transitions

### Sprites (12 images)

`images/maid--{state}.png` — states: `stand`, `lazy`, `cute`, `scaried`, `apologize`, `stone`, `scissors`, `paper`, `win`, `lose`, `draw`, `work` (reserved)

### Interaction

- **Left-click** (no drag): triggers reaction based on current state
- **Drag**: moves window (activated when manhattan distance > 5px)
- **Right-click**: context menu with "游戏" (game) and "退出" (quit)
