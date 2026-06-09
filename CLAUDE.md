# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Desktop Pet

PySide6 桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆角色，通过状态机驱动交互和动画。

## Commands

```bash
# 运行
.venv/Scripts/python main.py

# 安装依赖
.venv/Scripts/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

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

Virtual env: `.venv/` (Python 3.13)

## Dependencies

```
PySide6>=6.11, openai>=2.41.0, python-pptx>=1.0.2, python-docx>=1.2.0, openpyxl>=3.1.5, fpdf2>=2.8.7
```

## Architecture

Multi-file application using Mixin pattern for feature separation.

```
main.py    — DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin): core + state machine + events + drawing
chat.py    — ChatMixin: AI chat, config management, OpenAI SDK integration
game.py    — GameMixin: rock-paper-scissors game
dance.py   — DanceMixin + dialog classes: 3 dance modes
work.py    — Document generator (PPT/Word/Excel/PDF) + OpenAI function calling tool definition
```

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
        [right-click menu]
  ├── 游戏  → cute → stone/scissors/paper (1.5s) → win/lose/draw (2s) → stand
  ├── 跳舞  → DanceSelectorDialog → 3 modes (random/saved/custom)
  ├── 工作  → work menu → chat dialog or config
  └── 退出  → quit
```

### Files

| File | Responsibility | Key classes/methods |
|------|---------------|-------------------|
| `main.py` | DesktopPet core | `_setup_window()`, `_load_images()`, `_change_state()`, `_trigger_interaction()`, `_float_offset()`, events, `_tick()`, `paintEvent()` |
| `chat.py` | AI chat + config | `ChatMixin`: `_start_work()`, `_show_chat_dialog()`, `_send_message()`, `_do_api_request()` (OpenAI SDK), `_show_setup_dialog()`, `_show_advanced_settings()`, `_show_tutorial()`, `_work_mode()` |
| `game.py` | Rock-paper-scissors | `GameMixin`: `_start_game()`, `_on_player_choice()`, `_on_game_timeout()`, `_show_game_result()` |
| `dance.py` | Dance | `DanceMixin`: `_start_dance()`, `_play_dance_sequence()`, 3 modes; `DanceSelectorDialog`, `DanceCustomizeDialog` |
| `work.py` | Document generation | `generate_pptx/docx/xlsx/pdf()`, `generate_document()`, `GENERATE_DOC_TOOL` (function calling schema), `handle_tool_call()` |
| `config.json` | Persistent config | `api_key`, `base_url`, `model`, `saved_dances`, `output_dir` |

### Timers

- **Animation**: 60 FPS (16ms), drives `_tick()` → `paintEvent()`
- **Idle**: 10 min, transitions `stand` → `lazy`
- **State timeout**: 1.5s single-shot, returns to `stand` after triggered states; also used for dance steps (1s)
- **Game timer**: single-shot, drives game phase transitions

### Sprites (18 images)

`images/maid--{state}.png` — states: `stand`, `lazy`, `cute`, `scaried`, `apologize`, `stone`, `scissors`, `paper`, `win`, `lose`, `draw`, `work`, `dance1` ~ `dance6`

### Interaction

- **Left-click** (no drag): triggers reaction based on current state (stand → 70% cute / 30% scaried; lazy → 5% cute / 20% scaried / 75% apologize)
- **Drag**: moves window (activated when manhattan distance > 5px)
- **Right-click**: context menu with "游戏" (game), "跳舞" (dance), "工作" (work), "退出" (quit)
- **Game dialog**: persists after player choice, only closes on "退出游戏"
- **Dance selector**: 3 modes with sub-dialogs, "返回" goes back to previous menu
- **Chat dialog**: input+send row, toggle buttons (工作模式/联网模式/位置配置/close), streaming via queue, tools via OpenAI function calling

### Tool calling flow

1. User enables "工作模式" toggle → API request includes `GENERATE_DOC_TOOL`
2. Model returns `tool_calls` → `handle_tool_call()` generates document
3. Document saved to `_output_dir` (configurable via "位置配置")
4. Second API request with tool result → model responds with confirmation

### 项目改动原则

0. 注意！注意！注意！当对项目进行改动时，一定要遵循以下规定

1. 所有项目更新的要求都放在 UPGRADE.md 上

2. 针对分点提出的要求，在正式修改项目之前，务必务必要评估修改的难度

3. 当修改难度较低时，可直接修改

4. 当修改难度较高或者要求字数超过 80 字时，一定要规划出合理的执行方案，在我同意方案后再开始执行

5. 在分点执行完毕时停止当前对话
