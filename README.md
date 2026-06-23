# 赛博女仆 Desktop Pet

基于 PySide6 的桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆/猫娘角色，通过状态机驱动交互和动画。

---

## 版本

**当前版本：v1.1.0** · 2026-06-28

- 修复：聊天记录无界增长导致的内存泄漏问题
- 修复：频繁跳舞/换装时 QMenu/QDialog 对象累积不释放
- 优化：预加载双身份精灵图，换装瞬时完成无 GDI 内存抖动
- 重命名：将主文件名字由 `main.py` 改为 `cyber-maid.py`
- 修复：安装版运行时无法写入配置文件（自动重定向至 `%APPDATA%\DesktopPet\`）

完整的版本演进记录见 [`upgrade_log.md`](./upgrade_log.md)

---

## 项目结构

```
Desktop pet/
├── src/                    # 源代码
│   ├── cyber-maid.py       # 核心 + 状态机 + 事件 + 绘制
│   ├── chat.py             # AI 聊天 + 配置管理 + OpenAI SDK 集成
│   ├── dance.py            # 跳舞功能（3 种模式）
│   ├── game.py             # 石头剪刀布游戏
│   ├── memory.py           # 长期记忆持久化存储
│   ├── config.json         # 非敏感配置（身份 / 舞蹈数据，可上传）
│   ├── env                 # 敏感配置（API Key / Model / URL，不上传）
│   ├── memory.md           # 长期记忆持久化文件
│   └── images/             # 精灵图（maid + catgirl 各 18 张）
├── dist/                   # Nuitka 打包输出
├── .venv/                  # Python 虚拟环境
├── .gitignore
├── CLAUDE.md               # Claude Code 项目指引
└── requirements.txt        # Python 依赖
```

---

## 功能

### 交互式桌面宠物
- 左键点击触发随机状态反应（卖萌/惊吓/道歉）
- 拖拽移动窗口
- 右键弹出功能菜单（游戏/跳舞/聊天/换装）

### AI 聊天
- 基于 OpenAI SDK（兼容 DeepSeek API）
- 自定义 API Key / Base URL / Model
- 24 页内置 DeepSeek 配置引导教程

### 长期记忆
- AI 自动记住主人的偏好和习惯，跨会话持久化
- 支持关键词自动保存和 AI 自主记忆两种方式

### 石头剪刀布
- 宠物随机出拳并展示对应表情，持续游戏直到退出

### 跳舞
- 随机模式：随机 3~6 个动作，2~4 次循环
- 已保存模式：翻页浏览已保存的编排
- 自定义模式：选择动作 + 循环次数

### 换装系统
- 女仆 / 猫娘 两种身份一键切换
- 配套主题色自动切换（粉 / 灰）
- 身份持久化到配置文件

---

## 下载与安装

### 方式一：一键安装（推荐）

从 [Releases 页面](https://github.com/mingger77/Desktop-pet/releases) 下载 `赛博女仆_Setup.exe`，双击运行，按提示完成安装。

安装后可在 Windows 开始菜单或应用列表中找到“赛博女仆”。

### 方式二：便携压缩包

从 [Releases 页面](https://github.com/mingger77/Desktop-pet/releases) 下载 `Desktop-pet.zip`，解压后双击 `main.exe` 即可运行，无需安装。

---

## 首次使用

1. 启动程序后，右键点击女仆打开功能菜单。
2. 进入 **“设置”** → **“聊天配置”**，填入你的 API Key 和 Base URL（内置 DeepSeek 配置引导）。
3. 保存后即可开始聊天，女仆会记住你的偏好和习惯。

> 安装版数据存储位置：`%APPDATA%\DesktopPet\`（含 config.json、env、memory.md），清除数据或重装时请留意此目录。

> 提示：如果不使用 AI 聊天功能，女仆的基础交互（换装、跳舞、猜拳、拖拽、点击反应）均可离线使用。

---

## 依赖

- PySide6 >= 6.11 — GUI 框架
- openai >= 2.41.0 — AI 聊天 SDK
- Nuitka（可选）— exe 打包

---

## 开发说明

项目采用 Mixin 多继承模式分离功能模块：

```
DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin)
├── DanceMixin  → dance.py（跳舞）
├── GameMixin   → game.py（游戏）
├── ChatMixin   → chat.py（聊天 + 配置 + 记忆）
└── MemoryStore → memory.py（记忆存储）
```


如果你希望从源码运行或自行打包：

1. 创建虚拟环境：`python -m venv .venv`
2. 安装依赖：`.venv/Scripts/python -m pip install -r requirements.txt`
3. 运行：`.venv/Scripts/python src/cyber-maid.py`
4. 打包（需要 Nuitka）：参考 `CLAUDE.md` 中的打包命令

---

## 鸣谢

- **Claude Code**：我的赛博工友。代码编写、架构设计、Bug 修复……它是这个项目中从不喊累的那一半。
- **Hermes Agent (Nous Research)**：长期记忆系统的设计从 Hermes 的记忆架构中获得了关键启发，特此致谢。
- **GPT-image-2**：项目中的角色精灵图由 GPT-image-2 生成。
- **ifThink404**：你赠予我的那颗 star，是这个项目收到的第一份来自陌生人的认可。它让我相信，赛博女仆值得被继续做下去。