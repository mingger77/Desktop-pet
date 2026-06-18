# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供项目指引。

## 项目：桌面宠物（Desktop Pet）

PySide6 桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆/猫娘角色，通过状态机驱动交互和动画。

## 命令

```bash
# 运行
.venv/Scripts/python src/main.py

# 安装依赖
.venv/Scripts/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Nuitka 打包为独立 exe
.venv/Scripts/python -m nuitka src/main.py \
    --standalone \
    --enable-plugin=pyside6 \
    --include-data-dir=images=images \
    --include-data-file=src/config.json=config.json \
    --windows-console-mode=disable \
    --output-dir=dist \
    --product-name=DesktopPet \
    --file-version=1.0.0 \
    --msvc=latest
```

虚拟环境：`.venv/`（Python 3.13）

## 依赖

```
PySide6>=6.11, openai>=2.41.0
```

## 架构

多文件 Mixin 模式分离功能。

```
src/main.py    — DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin): 核心 + 状态机 + 事件 + 绘制
src/chat.py    — ChatMixin: AI 聊天 + 配置管理 + OpenAI SDK 集成
src/game.py    — GameMixin: 石头剪刀布游戏
src/dance.py   — DanceMixin + 对话框类: 3 种跳舞模式
src/memory.py  — MemoryStore: 长期记忆持久化存储层
src/config.json — 非敏感配置（身份/舞蹈数据，可上传）
src/env        — 敏感配置（API Key/Model/URL，不上传）
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
| `src/main.py` | DesktopPet 核心 | `_setup_window()`, `_load_images()`（按身份加载）, `_change_state()`, `_trigger_interaction()`, `_float_offset()`, `_switch_identity()`, 事件, `_tick()`, `paintEvent()` |
| `src/chat.py` | AI 聊天 + 配置 + 记忆 | `ChatMixin`: `_start_work()`, `_show_chat_dialog()`, `_send_message()`, `_auto_save_memory()`, `_do_api_request()` (OpenAI SDK + MEMORY_TOOL), `_handle_memory_tool()`, `_show_setup_dialog()`, `_show_tutorial()`, `_show_work_menu()`, `_load_config()`, `_save_config()`, `_theme()`, `_close_chat()` |
| `src/game.py` | 石头剪刀布 | `GameMixin`: `_start_game()`, `_show_choice_dialog()`, `_on_player_choice()`, `_on_game_timeout()`, `_show_game_result()`, `_end_game()` |
| `src/dance.py` | 跳舞 | `DanceMixin`: `_start_dance()`, `_play_dance_sequence()`, `_start_random_dance()`, `_show_saved_dances()`, `_start_custom_dance()`, `_save_new_dance()`, `_on_dance_step()`, `_end_dance()`; `DanceSelectorDialog(QDialog)`, `DanceCustomizeDialog(QDialog)` |
| `src/memory.py` | 长期记忆 | `MemoryStore.load()`, `save()`, `add()`, `remove()`, `format_for_prompt()`, `usage_percent()` |
| `src/config.json` | 非敏感持久化配置 | `identity`, `saved_dances` |
| `src/env` | 敏感 API 配置（不上传） | `api_key`, `model`, `base_url` |

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
- **跳舞选择器**：3 种模式 + 返回；已保存/自定义的「返回」回到选择器，非主菜单
- **聊天对话框**：布局为 `[输入框] [发送]` + 第二行 `[关闭]`；入口为工作菜单（开始聊天/修改配置/取消）
- **换装**：右键菜单「换装」在女仆/猫娘间切换，身份持久化到 config.json

### 主题系统

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

### 长期记忆

基于 Hermes Agent 记忆架构简化实现：

- `memory.py` — `MemoryStore`：`memory.md` 文件的原子读写（`tempfile` + `os.replace`）
- 条目用 `§` 分隔，字符预算 2200
- 两种写入方式：
  1. **主动检测**：`_auto_save_memory()` 在用户消息中匹配记忆关键词（"记住"、"我喜欢"等），直接写入
  2. **模型自主**：`MEMORY_TOOL` function calling，AI 在对话中自行调用 `memory(action="add")`
- 每次 API 调用前从 `memory.md` 加载记忆，注入为 system 消息
- 输出目录：`src/memory.md`
