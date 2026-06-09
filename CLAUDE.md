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

### 项目改动原则

0. **注意：** 对项目进行改动时，必须遵循以下规定。

1. 所有项目更新需求统一写在 `UPGRADE.md` 中。

2. 针对每个分点的具体要求，在正式修改前，先给出总体落地计划。

3. 正式修改前，务必评估修改难度。

4. 评估难度时，必须从以下三个维度给出 `Low / Medium / High` 的明确评级：
   - **上下文污染度**：是否改动多个文件
   - **线程安全性**：是否涉及异步/信号槽
   - **资产完整度**：是否影响原有程序效果

5. 当修改难度 **均为 Low** 或 **仅有一个 Medium** 时，可直接修改。

6. 直接修改过程中，若出现编译报错、PyQt 事件死锁或 Nuitka 构建失败，**必须立即停止**，严禁擅自继续打补丁，应主动汇报报错并等待指示。

7. 若分点满足以下任一条件，必须给出方案：
   - 改动涉及多线程、PyQt 事件循环（Event Loop）或网络异步请求
   - 改动涉及跨文件修改（同时改动 2 个及以上 `.py` 文件）
   - 改动涉及持久化数据结构（如更新 JSON 记忆账本、修改配置字段）
   - 修改难度有一个维度为 `High`
   - 修改难度有 2 个或 3 个维度为 `Medium`
   - 单条更新要求中包含 2 个或 3 个"且/并/以及"等逻辑并列句（即包含多个业务子任务）

8. 若分点满足以下任一条件，必须将分点拆成若干子分点，并对子分点按上述原则重新执行滚动审计：
   - 修改难度有两个及以上为 `High`
   - 单条更新要求中包含 4个及以上"且/并/以及"等逻辑并列句

9. 汇报计划时必须包含：改动了哪些文件、新增了哪些依赖、是否会破坏现有事件、以及如何进行本地测试。

10. 每个分点执行完毕后，停止当前对话。

11. 任何时候修改或生成文件，**绝对不允许**超出项目根目录或指定的 `workspace/` 沙盒路径，严禁触碰任何系统级敏感盘符与注册表。

12. 在开始新一轮 `UPGRADE.md` 的分点前，必须先检查本地 Git 状态是否为 Clean。若前一个分点测试失败，必须有明确指令指引回滚，不得带着脏代码继续往下进行。

