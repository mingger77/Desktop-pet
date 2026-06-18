# 赛博女仆 Desktop Pet

基于 PySide6 的桌面宠物应用。无边框透明置顶窗口，使用 PNG 精灵图展示女仆/猫娘角色，通过状态机驱动交互和动画。

## 项目结构

```
Desktop pet/
├── src/                    # 源代码
│   ├── main.py             # 核心 + 状态机 + 事件 + 绘制
│   ├── chat.py             # AI 聊天 + 配置管理 + OpenAI SDK 集成
│   ├── dance.py            # 跳舞功能（3 种模式）
│   ├── game.py             # 石头剪刀布游戏
│   ├── memory.py           # 长期记忆持久化存储
│   ├── config.json         # 非敏感配置（身份 / 舞蹈数据，可上传）
│   └── env                 # 敏感配置（API Key / Model / URL，不上传）
│   └── images/             # 精灵图（maid + catgirl 各 18 张）
├── dist/                   # Nuitka 打包输出
├── .venv/                  # Python 虚拟环境
├── .gitignore
├── CLAUDE.md               # Claude Code 项目指引
└── requirements.txt        # Python 依赖
```

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

## 运行

```bash
# 从源码运行
.venv/Scripts/python src/main.py

# 打包为独立 exe
.venv/Scripts/python -m nuitka src/main.py \
    --standalone \
    --enable-plugin=pyside6 \
    --include-data-dir=src/images=images \
    --include-data-file=src/config.json=config.json \
    --windows-icon-from-ico=src/images/cyber_maid.ico \
    --windows-console-mode=disable \
    --output-dir=dist \
    --product-name=DesktopPet \
    --file-version=1.0.0 \
    --msvc=latest
```

打包后双击 `dist/main.dist/main.exe` 即可运行。

## 依赖

- PySide6 >= 6.11 — GUI 框架
- openai >= 2.41.0 — AI 聊天 SDK
- Nuitka（可选）— exe 打包

## 开发说明

项目采用 Mixin 多继承模式分离功能模块：

```
DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin)
├── DanceMixin  → dance.py（跳舞）
├── GameMixin   → game.py（游戏）
├── ChatMixin   → chat.py（聊天 + 配置 + 记忆）
└── MemoryStore → memory.py（记忆存储）
```

## 鸣谢

- 本项目由 Claude Code 辅助完成，Claude Code 承担了代码编写、架构设计、Bug 修复等大量工作，是名副其实的"赛博工友"
- 长期记忆系统的设计参考了 Nous Research 开源的 Hermes Agent 项目的记忆架构，特此致谢
- 项目中的精灵图由 GPT-image-2 生成，在此表示感谢
