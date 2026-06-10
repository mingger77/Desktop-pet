# 架构分析（Architecture Analysis）

> 基于静态代码阅读分析，分析日期：2026-06-10。

---

## 一、项目概览

### 项目目标

PySide6 桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆/猫娘角色，通过状态机驱动交互和动画。支持右键菜单交互、AI 聊天（OpenAI SDK）、石头剪刀布游戏、跳舞动画、换装主题切换。

### 技术栈

| 层次 | 技术 |
|---|---|
| GUI 框架 | PySide6 (Qt for Python) |
| AI SDK | openai (OpenAI SDK，兼容 DeepSeek API) |
| 打包 | Nuitka (standalone exe) |
| Python | 3.13 |

### 入口文件

`main.py`（末尾 `if __name__ == "__main__"` 创建 QApplication + DesktopPet 实例）

---

## 二、模块拓扑树

```
main.py (DesktopPet: QWidget + Mixins)
├── DanceMixin (dance.py)
│   ├── DanceSelectorDialog (QDialog)
│   ├── DanceCustomizeDialog (QDialog)
│   └── 保存舞蹈管理 (_load_saved_dances / _save_saved_dances)
├── GameMixin (game.py)
│   └── 游戏对话框 (_show_choice_dialog)
├── ChatMixin (chat.py)
│   ├── 配置管理 (_load_config / _save_config)
│   ├── 工作模式菜单 (_show_work_menu)
│   ├── API 设置对话框 (_show_setup_dialog)
│   ├── AI 聊天对话框 (_show_chat_dialog)
│   ├── 24 页教程 (_show_tutorial)
│   └── API 请求 (_do_api_request)
└── 配置层
    └── config.json (持久化)

模块依赖关系：

main.py ──import──→ dance.py / game.py / chat.py
dance.py ──import──→ chat.py (_THEMES 常量)
```

---

## 三、核心数据流（Data Flow）

### 3.1 启动流程

```
main.py: QApplication()
  → DesktopPet.__init__()
    → _setup_window()          // 无边框透明置顶窗口
    → _load_config()           // 从 config.json 加载 API key/identity（必须先于 _load_images）
    → _load_images()           // 按 self._identity 前缀加载精灵图
    → _init_state()            // state = "stand"
    → _setup_timers()          // 动画 16ms + 空闲 10min + 状态 1.5s + 游戏
    → _setup_ui()              // 右键菜单策略
  → pet.show()
  → app.exec()
```

### 3.2 右键菜单交互数据流

```
contextMenuEvent
  → while True:
      → QMenu.exec()           // 显示 5 项菜单
      → 游戏 → _start_game()
      → 跳舞 → _start_dance()
      → 聊天 → _start_work()
      → 换装 → _switch_identity()
      → 退出 → QApplication.quit()
      // 点击菜单外或聊天打开时 break
```

### 3.3 AI 聊天数据流

```
用户输入
  ↓
_send_message()
  ↓ 后台线程
_do_api_request()
  → OpenAI client.chat.completions.create()
    ↓ 若 web_search 开启
    kwargs["extra_body"] = {"web_search": True}
  → reply = msg.content
  ↓ queue.Queue
_on_api_reply()  // 主线程 UI 更新
```

### 3.4 配置数据流

```
config.json
  ├── api_key: str
  ├── base_url: str
  ├── model: str
  ├── identity: "maid" | "catgirl"
  └── saved_dances: [{"poses": [...], "loops": int}]

读取路径：
  DesktopPet.__init__() → _load_config()
  DanceMixin._load_saved_dances()

写入路径：
  ChatMixin._save_config()
  DesktopPet._switch_identity()
  DanceMixin._save_saved_dances()
```

---

## 四、状态机分析

### 状态定义

项目显式使用状态机驱动。状态存储于 `self.state`，图片集按状态命名。

### 状态全集（18 种）

基础状态：`stand`, `lazy`
触发状态：`cute`, `scaried`, `apologize`
游戏状态：`stone`, `scissors`, `paper`, `win`, `lose`, `draw`
工作状态：`work`
舞蹈状态：`dance1` ~ `dance6`

### 状态转移图

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
  ├── 跳舞  → DanceSelectorDialog → dance1~6 序列 (1s/step) → stand
  ├── 聊天  → work → chat dialog (modeless)
  ├── 换装  → switch identity (同状态不同图片)
  └── 退出  → quit
```

### 定时器驱动

| 定时器 | 间隔 | 作用 |
|--------|------|------|
| `_anim_timer` | 16ms (60 FPS) | 帧动画 + _float_offset |
| `_idle_timer` | 600s (10min) | stand → lazy |
| `_state_timer` | 1.5s (单次) | 触发状态超时回归 |
| `_game_timer` | 1.5s/2s (单次) | 游戏阶段切换 |

---

## 五、外部依赖清单

| 依赖 | 用途 | 来源 |
|------|------|------|
| PySide6 | GUI 框架（QWidget, QDialog, QTimer, QPainter） | PyPI |
| openai | OpenAI SDK（API 调用） | PyPI |
| DeepSeek API | AI 聊天后端（兼容 OpenAI 协议） | 远程 API |

---

## 六、关键逻辑分析

### 6.1 Mixin 多继承模式

```python
class DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin):
```

各 Mixin 通过 `self._identity`、`self.state`、`self._theme()` 等属性访问共享状态。Mixin 方法可以调用 DesktopPet 的核心方法（`_change_state`、`_idle_timer` 等）。

**调用链示例**：`right-click 跳舞` → `contextMenuEvent` → `_start_dance()` (DanceMixin) → `DanceSelectorDialog.get_choice()` → `_play_dance_sequence()` → `_change_state()` (DesktopPet) → `_state_timer.start()` → `_on_dance_step()` (DanceMixin) → `_end_dance()` → `_change_state("stand")`。

### 6.2 嵌套事件循环

右键菜单通过 `while True` + `menu.exec()` 实现嵌套事件循环。子对话框（游戏、跳舞选择器等）通过 `dialog.exec()` 阻塞，返回后回到主菜单循环。聊天对话框使用 `dialog.show()`（非模态），因此当聊天打开时 `break` 跳出循环。

### 6.3 线程安全 API 通信

```python
# 后台线程写入
threading.Thread(target=self._do_api_request, daemon=True).start()
# 在 _do_api_request 末尾
self._reply_queue.put(reply)

# 主线程 60FPS 轮询
def _tick(self):
    try:
        reply = self._reply_queue.get_nowait()
        self._on_api_reply(reply)
    except queue.Empty:
        pass
```

不使用流式输出（之前尝试过 SSE streaming 后回退）。后台线程完成全部 API 调用（含可能的第二轮 tool call），一次性通过 queue 传递结果。

### 6.4 动态主题系统

主题通过 `_THEMES` 字典定义，ChatMixin 提供 `_theme()` 访问方法：

```python
_THEMES = {
    "maid":    {"bg": "#FFF0F5", "border": "#FF69B4", "text_bold": "#FF1493",
                "label": "#8B4513", "input_border": "#FFB6C1", "btn_text": "#FF69B4"},
    "catgirl": {"bg": "#F0F0F0", "border": "#999999", "text_bold": "#333333",
                "label": "#8B4513", "input_border": "#CCCCCC", "btn_text": "#666666"},
}
```

每个对话框的 stylesheet 使用 f-string + `t = self._theme()` 动态插值。独立 QDialog 子类通过 `self.parent()._theme()` 获取主题。

---

## 七、数据流简化

### 7.1 聊天交互简化

v1.1.0 移除了文档生成（work.py）和文件读取功能后，聊天数据流大幅简化：

1. 用户发送消息 → 后台线程调用 API（仅携带聊天历史，无 tools 参数）
2. API 返回文本回复 → queue.Queue 传递到主线程
3. 主线程更新 UI 显示

不再需要：
- 工具调用（tool_calls）处理
- 第二轮 API 请求
- 输出目录管理
- 文件读取与解析

### 7.2 跳舞导航重构

v1.1.0 将 _start_dance 改为 while 循环结构：

```
while True:
    跳舞选择器 (modal)
    ├── 返回 → break
    ├── 随机 → 播放 → break
    ├── 已保存 → 子页面 → 返回 → continue (回到选择器)
    │                      └─ 播放 → break
    └── 自定义 → 子页面 → 取消 → continue (回到选择器)
                           ├─ 播放 → break
                           └─ 保存 → break
```

这种方法使得子页面的「返回」「取消」按钮自然回到上一级（跳舞选择器），而非直接回到主菜单。

---

## 八、已知问题

### 【事实】requirements.txt 缺少 openai 依赖

chat.py 中 `from openai import OpenAI`，但 requirements.txt 未列出 openai。

### 【推断】_show_advanced_settings() 是死代码

chat.py 中 `_show_advanced_settings()` 方法定义了完整的高级设置对话框，但一直没有被任何地方调用。

### 【推断】猫娘标签文字色与预期不一致

`_THEMES["catgirl"]["label"] = "#8B4513"`（棕色），与女仆相同。根据设计预期应改为灰色系（如 #555555）。

---

## 九、审计范围

### 已审计

- main.py（全部 324 行）
- chat.py（全部 960 行）
- dance.py（全部 631 行）
- game.py（全部 142 行）
- work.py（全部 196 行）
- config.json
- requirements.txt
- MARKDOWNS 文档

### 未审计

- images/ 目录（图片文件）
- dist/（构建产物）
- .venv/（虚拟环境）

### 可信度

High — 所有 Python 源文件已全部静态分析。

---

*分析日期：2026-06-10 | 分析方式：静态代码阅读*
