# 历史设计决策（Design Decisions）

> 记录项目开发过程中的关键设计决策、方案对比和选择理由。

---

## 决策 1：Mixin 多文件模式（替代单文件）

**日期**：2026-06

**问题**：初始项目为单文件 monolithic 结构（超过 1000 行），难以维护和扩展。

**方案对比**：

| 方案 | 描述 | 复杂度 |
|------|------|--------|
| A | 保持单文件，按功能分区 | 低，但长期不可维护 |
| B | Mixin 模式：主类 + 多个 Mixin 文件 | 中，Python 多继承 |
| C | 独立窗口类 + 组合模式 | 高，需要重构信号槽 |

**选择**：方案 B

**理由**：
- Mixin 可以无缝访问 DesktopPet 的核心属性（self.state, self._change_state 等），无需重构信号槽
- 每个 Mixin 文件聚焦单一职责（游戏/跳舞/聊天），符合 SRP
- 调用链不变：`contextMenuEvent → self._start_dance() → DanceMixin`
- 独立 QDialog 子类放在 dance.py 中（DanceSelectorDialog, DanceCustomizeDialog），不增加文件数量

**影响**：
- main.py 从 1000+ 行降为 324 行
- chat.py 960 行（最重，因包含 AI 聊天 + 配置 + 教程 + 高级设置）
- 需要导入 _THEMES 常量（dance.py 从 chat.py import）

---

## 决策 2：queue.Queue 线程通信（替代 QTimer.singleShot）

**日期**：2026-06

**问题**：后台线程调用 `QTimer.singleShot(0, callback)` 不生效——PySide6 的计时器只在主线程事件循环中触发。

**方案对比**：

| 方案 | 描述 |
|------|------|
| A | queue.Queue + 主线程轮询（_tick 中 get_nowait） |
| B | QMetaObject.invokeMethod 跨线程信号 |
| C | PySide6 Signal + QThread |

**选择**：方案 A

**理由**：实现最简单，无需定义 Signal/slot，_tick 本身 60FPS 轮询，get_nowait 开销极低。

**影响**：main.py 增加 _reply_queue 属性，_tick 增加轮询逻辑。

---

## 决策 3：非流式 API 调用（替代 SSE Streaming）

**日期**：2026-06

**问题**：SSE 流式输出在多轮消息 + 工具调用场景下管理复杂度高。

**方案对比**：

| 方案 | 用户体验 | 实现复杂度 |
|------|---------|-----------|
| 流式 | 逐字显示，延迟低 | 高（需管理 stream buffer + tool call 拼接） |
| 非流式 | 等待后一次性显示 | 低（直接返回完整消息） |

**选择**：非流式

**理由**：
- 工具调用场景需要完整消息体（含 tool_calls），流式需要做 buffer 拼接
- 第二轮 API 调用（tool call 后）天然不适合流式
- 简化代码，降低故障概率

**影响**：_do_api_request 使用 `client.chat.completions.create()`（无 stream=True），一次性返回。

---

## 决策 4：游戏对话框不关闭（持续游戏）

**日期**：2026-06

**问题**：玩家点击石头/剪刀/布后，对话框关闭然后重新打开，体验割裂。

**方案对比**：

| 方案 | 描述 |
|------|------|
| A | 选择后关闭 → QTimer.singleShot 重新打开 |
| B | 选择后不关闭，对话框保持打开，仅宠物状态变化 |

**选择**：方案 B

**理由**：
- 对话框保持打开，玩家看到宠物出拳的同时，下一轮选择按钮立即可用
- 去掉 `_on_player_choice` 中的 `dialog.accept()` 调用
- _on_game_timeout 中结果展示完毕后回到 "cute" 状态，对话框内容不变

**影响**：对话框生命周期从「每次选择开/关」变为「一次打开直到退出」。

---

## 决策 5：换装后重载图片（而非预加载全部）

**日期**：2026-06

**问题**：换装时需要切换 maid/catgirl 两套精灵图，共 36 张。

**方案对比**：

| 方案 | 内存 | 切换速度 |
|------|------|---------|
| 预加载全部（36 张都在内存） | 高 | 瞬间切换 |
| 按身份按需加载（18 张在内存） | 低 | 数百毫秒延迟 |

**选择**：按身份按需加载

**理由**：精灵图是 PNG 文件，36 张预加载对桌面应用无意义——同一时间只有一个身份可见。换装时重载 18 张图片耗时可接受（本地文件 IO）。

**影响**：_load_images() 按 self._identity 前缀过滤，_switch_identity() 调用 _load_images() + _init_state() + update()。

---

## 决策 6：f-string + _THEMES 实现主题（而非 QSS 变量）

**日期**：2026-06

**问题**：两套主题色（女仆粉/猫娘灰）需要应用到所有对话框 stylesheet 中。

**方案对比**：

| 方案 | 描述 |
|------|------|
| A | Python f-string + _THEMES 字典插值 |
| B | QSS 自定义属性 + qproperty 变量 |
| C | 两套独立 QSS 文件切换 |

**选择**：方案 A

**理由**：
- f-string 是 Python 原生特性，零额外依赖
- 每个对话框只需要加一行 `t = self._theme()` 即可访问主题色
- 不需要额外 QSS 文件管理

**注意**：CSS 中的 `{` 需要在 f-string 中写为 `{{`（双花括号转义），这是多个 bug 的根源。

**影响**：全项目约 58 处 stylesheet 改为 f-string。独立 QDialog 子类通过 `self.parent()._theme()` 获取。

---

## 决策 7：嵌套事件循环实现菜单导航（替代状态机菜单）

**日期**：2026-06

**问题**：右键菜单 → 子页面 → 返回主菜单，需要正确处理事件循环嵌套。

**方案**：`while True` + `menu.exec()` 阻塞式嵌套

**理由**：
- 游戏、跳舞、配置等对话框使用 `dialog.exec()`（模态），会阻塞并进入嵌套事件循环
- while True 保证了返回后重新显示主菜单
- 聊天对话框使用 `dialog.show()`（非模态），因此在聊天打开时 `break`

**影响**：contextMenuEvent 的 while True 循环在所有子页面返回后才会退出。跳舞等场景需要特别注意子对话框的 reject/accept 逻辑。

---

## 决策 8：文档生成使用 function calling（而非手动 JSON 解析）

**日期**：2026-06

**问题**：AI 需要能够生成 Office 文档（PPT/Word/Excel/PDF）。

**方案**：通过 OpenAI function calling 机制

```
用户请求 → API (含 GENERATE_DOC_TOOL) → model 返回 tool_calls
→ handle_tool_call() → generate_document() → 保存文件
→ 第二轮 API 获取确认回复
```

**理由**：
- function calling 让模型自行决定何时及如何调用文档生成，比手动 JSON 解析更可靠
- tool schema 定义了 `type`/`title`/`content` 的约束，模型按 schema 输出结构化数据
- 旧版 _work_mode() + _extract_json() 保留作为备选

**影响**：work.py 定义了 GENERATE_DOC_TOOL + handle_tool_call，chat.py 在 work_mode_enabled 时 attach 到 API 请求。

---

## 决策 9：24 页引导教程（而非外部文档链接）

**日期**：2026-06

**问题**：用户需要完整的 DeepSeek API 配置引导。

**方案**：24 页系统内置翻页教程（_TUTORIAL_PAGES 列表 + QTextEdit 显示）

**理由**：
- 内置教程离线可用，不依赖外部网站
- 每一步可翻页查看，从注册 → 实名认证 → API Key → 充值 → 验证，全流程覆盖
- 用列表分页（`list.__setitem__` 修改页码），避免闭包变量绑定问题

**影响**：chat.py 增加 _TUTORIAL_PAGES 列表（24 项）+ _show_tutorial 方法，以独立 QDialog 显示。

---

## 决策 10：独立 QDialog 子类（DanceSelectorDialog / DanceCustomizeDialog）

**日期**：2026-06

**问题**：跳舞选择器和自定义编舞对话框包含复杂 UI 逻辑（复选框、SpinBox、状态管理），不适合放在 Mixin 方法中。

**方案**：定义独立的 QDialog 子类

**理由**：
- 封装状态（_choice, _result）和 UI 初始化
- 通过 `get_choice()` / `get_custom_dance()` 返回结果，接口清晰
- 主题通过 `self.parent()._theme()` 获取

**影响**：dance.py 增加两个 QDialog 子类（共约 250 行），DanceMixin 保持简洁。
