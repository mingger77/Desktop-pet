# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供项目指引。

## 项目：桌面宠物（Desktop Pet）

PySide6 桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆/猫娘角色，通过状态机驱动交互和动画。

## 命令

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

虚拟环境：`.venv/`（Python 3.13）

## 依赖

```
PySide6>=6.11, openai>=2.41.0, python-pptx>=1.0.2, python-docx>=1.2.0, openpyxl>=3.1.5, fpdf2>=2.8.7
```

## 架构

多文件 Mixin 模式分离功能。

```
main.py    — DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin): 核心 + 状态机 + 事件 + 绘制
chat.py    — ChatMixin: AI 聊天 + 配置管理 + OpenAI SDK 集成
game.py    — GameMixin: 石头剪刀布游戏
dance.py   — DanceMixin + 对话框类: 3 种跳舞模式
work.py    — 文档生成器 (PPT/Word/Excel/PDF) + OpenAI function calling 工具定义
```

### 状态机

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
  ├── 聊天  → work menu → chat dialog or config
  ├── 换装  → switch identity (maid/catgirl)
  └── 退出  → quit
```

### 文件职责

| 文件 | 职责 | 关键方法 |
|------|------|---------|
| `main.py` | DesktopPet 核心 | `_setup_window()`, `_load_images()`（按身份加载）, `_change_state()`, `_trigger_interaction()`, `_float_offset()`, `_switch_identity()`, 事件, `_tick()`, `paintEvent()` |
| `chat.py` | AI 聊天 + 配置 | `ChatMixin`: `_start_work()`, `_show_chat_dialog()`, `_send_message()`, `_do_api_request()` (OpenAI SDK), `_show_setup_dialog()`, `_show_advanced_settings()`, `_show_tutorial()`, `_work_mode()`, `_upload_file()`, `_read_file_content()` |
| `game.py` | 石头剪刀布 | `GameMixin`: `_start_game()`, `_on_player_choice()`, `_on_game_timeout()`, `_show_game_result()` |
| `dance.py` | 跳舞 | `DanceMixin`: `_start_dance()`, `_play_dance_sequence()`, 3 种模式; `DanceSelectorDialog`, `DanceCustomizeDialog` |
| `work.py` | 文档生成 | `generate_pptx/docx/xlsx/pdf()`, `generate_document()`, `GENERATE_DOC_TOOL` (function calling 定义), `handle_tool_call()` |
| `config.json` | 持久化配置 | `api_key`, `base_url`, `model`, `identity`, `saved_dances`, `output_dir` |

### 定时器

- **动画**：60 FPS (16ms)，驱动 `_tick()` → `paintEvent()`
- **空闲**：10 分钟，`stand` → `lazy`
- **状态超时**：1.5s 单次，触发状态后回到 `stand`；也用于跳舞步进 (1s)
- **游戏定时器**：单次，驱动游戏阶段切换

### 精灵图（36 张）

两种身份各 18 张：
- 女仆：`images/maid--{state}.png`
- 猫娘：`images/catgirl--{state}.png`

状态列表：`stand`, `lazy`, `cute`, `scaried`, `apologize`, `stone`, `scissors`, `paper`, `win`, `lose`, `draw`, `work`, `dance1` ~ `dance6`

`_load_images()` 根据 `self._identity` 前缀加载对应图片集。

### 交互

- **左键单击**（非拖拽）：基于当前状态触发反应（stand → 70% cute / 30% scaried；lazy → 5% cute / 20% scaried / 75% apologize）
- **拖拽**：移动窗口（曼哈顿距离 > 5px 激活）
- **右键菜单**：循环显示，子页面返回后回到主菜单。5 项——游戏、跳舞、聊天、换装、退出
- **游戏对话框**：玩家选择后不关闭，仅在点击「退出游戏」时关闭
- **跳舞选择器**：3 种模式 + 返回，「返回」直接回到主菜单
- **聊天对话框**：布局为 `[输入框] [📎] [发送]` + 第二行 `[工作模式] [联网模式] [位置配置] [关闭]`
- **换装**：右键菜单「换装」在女仆/猫娘间切换，身份持久化到 config.json

### 主题系统（分点 7+8）

根据身份自动切换：

| 属性 | 女仆 | 猫娘 |
|------|------|------|
| 对话框背景 | #FFF0F5 浅粉 | #F0F0F0 浅灰 |
| 边框色 | #FF69B4 | #999 |
| 强调文字 | #FF1493 | #333 |
| 标签文字 | #8B4513 | #8B4513 |
| 输入框边框 | #FFB6C1 | #CCC |
| 按钮文字 | #FF69B4 | #666 |

`_THEMES` 字典定义在 `chat.py`，通过 `self._theme()` 访问。

### 文件上传（分点 5）

聊天输入框旁的 `@` 按钮支持上传文件：
- 格式：txt / docx / xlsx / pptx
- 大小限制：10MB
- 内容自动读取后填入输入框，可预览后发送

### 工具调用流程

1. 用户开启「工作模式」开关 → API 请求包含 `GENERATE_DOC_TOOL`
2. 模型返回 `tool_calls` → `handle_tool_call()` 生成文档
3. 文档保存到 `_output_dir`（通过「位置配置」设置）
4. 第二轮 API 请求携带工具结果 → 模型返回确认回复

# 项目文档

文档位置：
.\MARKDOWNS\

项目改动规范：
PROJECT_UPGRADE_SKILL.md

代码阅读规范：
CODE_READING_SKILL.md

需求池：
UPGRADE.md

架构分析：
ANALYSIS.md

历史设计决策：
DECISIONS.md

版本变更记录：
CHANGELOG.md

`Hermes`源码分析报告：
HERMES.md
