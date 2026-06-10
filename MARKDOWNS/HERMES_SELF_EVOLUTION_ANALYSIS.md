# Hermes Agent 自主进化系统分析

> 本文档基于 Hermes Agent（Nous Research 开源项目）的源代码静态分析编写。
> 项目地址：https://github.com/nousresearch/hermes-agent
> 分析版本：0.16.0
>
> 目标读者：无法直接访问 Hermes 源码的项目组。
> 本文档独立完整，无需配合源码阅读。

---

## 第一章：概述

### 1.1 什么是"自主进化"

"自主进化"（self-evolution / self-improvement）是 Hermes Agent 区别于普通 LLM 对话框架的核心能力：**Agent 能在无人干预的情况下，从对话经验中提取有价值的信息，并主动更新自己的知识和行为模式**。

具体来说，自主进化体现在三个层次：

| 层次 | 进化方式 | 频率 | 效果 |
|---|---|---|---|
| **记忆层** | 从对话提取用户偏好和环境事实 | 每 N 轮对话 | 下次会话不再需要重复告知 |
| **技能层** | 从成功经验中抽象出可复用的工作流程 | 每 N 轮对话 | 同类任务越来越高效准确 |
| **技能库层** | 归档旧技能、合并重复技能、构建类级伞状技能 | 每 7 天 | 技能库保持精简和高质量 |

### 1.2 核心矛盾

自主进化系统需要同时满足三个互相矛盾的需求：

| 矛盾 | 描述 |
|---|---|
| **学习 vs 阻塞** | Agent 需要从对话中学习，但如果学习过程阻塞了用户交互，体验会不可接受 |
| **主动 vs 安全** | Agent 需要主动修改记忆和技能，但不能因此产生危险副作用 |
| **短期 vs 长期** | 从单次对话提取的"碎片"需要被整合为稳定的知识，而不是堆积为垃圾 |

Hermes 的解决方案是**双回路架构**（Two-Loop Architecture）：

```
用户交互
    │
    ▼
┌─────────────────────────────────┐
│    回路一：快速学习回路           │
│  (Background Review)             │
│  每 N 轮触发                     │
│  fork 子 Agent 后台运行           │
│  非阻塞                          │
│  学习结果: 记忆 + 技能更新        │
└──────────┬──────────────────────┘
           │ 累积
           ▼
┌─────────────────────────────────┐
│    回路二：慢速整理回路           │
│  (Curator)                       │
│  每 7 天触发                      │
│  自动化状态迁移 + LLM 整合        │
│  结果: 技能库归档 / 合并 / 清理   │
└──────────────────────────────────┘
```

---

## 第二章：系统架构

### 2.1 自主进化模块全景

```
AIAgent (run_agent.py)
│
├── 计数器系统 (Nudge System)           [感知层]
│   ├── _memory_nudge_interval = 10     ← 每 10 轮触发记忆审查
│   ├── _skill_nudge_interval = 10      ← 每 10 次迭代触发技能审查
│   ├── _turns_since_memory             ← 记忆计数器 (hydration 恢复)
│   └── _iters_since_skill              ← 技能计数器
│
├── 快速学习回路                         [执行层]
│   ├── turn_finalizer.py: 审查触发      ← 对话收尾阶段
│   │   └── _spawn_background_review()
│   ├── background_review.py: 审查执行    ← fork 子 Agent
│   │   ├── _MEMORY_REVIEW_PROMPT       ← 记忆审查提示词
│   │   ├── _SKILL_REVIEW_PROMPT        ← 技能审查提示词
│   │   ├── _COMBINED_REVIEW_PROMPT     ← 综合审查提示词
│   │   ├── _run_review_in_thread()     ← 后台线程执行体
│   │   ├── summarize_background_review_actions() ← 结果摘要
│   │   └── build_memory_write_metadata() ← 溯源元数据
│   └── skill_manage_tool.py: 技能执行   ← 实际的技能 CRUD
│       ├── _create_skill()             ← 创建技能
│       ├── _edit_skill()               ← 编辑技能
│       ├── _patch_skill()              ← 局部修改
│       └── _delete_skill()             ← 删除技能
│
├── 慢速整理回路                         [执行层]
│   ├── agent/curator.py: 审查器主逻辑   ← 1849 行核心
│   │   ├── maybe_run_curator()         ← 触发入口
│   │   ├── should_run_now()            ← 时间门控
│   │   ├── apply_automatic_transitions() ← 自动状态迁移
│   │   ├── _llm_pass()                 ← LLM 整合
│   │   └── run_curator_review()        ← 完整审查流程
│   ├── agent/curator_backup.py: 备份系统 ← 696 行
│   │   ├── backup_skills()             ← 快照
│   │   └── restore_from_backup()       ← 回滚
│   ├── hermes_cli/curator.py: CLI 命令  ← 用户交互
│   │   ├── status / run / pause / resume
│   │   ├── pin / unpin / archive / prune
│   │   └── restore / backup / rollback / list-archived
│   └── tools/skill_usage.py: 生命周期管理
│       ├── active / stale / archived    ← 三态
│       ├── bump_patch() / forget()      ← 用法追踪
│       └── .curator_suppressed          ← 内置技能抑制
│
└── 技能工具层                           [工具层]
    ├── tools/skill_manager_tool.py      ← skill_manage 工具
    ├── tools/skills_tool.py             ← skills_list / skill_view
    ├── tools/skills_hub.py              ← 技能来源适配器
    ├── tools/skills_guard.py            ← 安全扫描
    ├── tools/skills_sync.py             ← 同步机制
    └── tools/skill_provenance.py        ← 溯源追踪
```

### 2.2 启动触发点

快速学习回路（Background Review）由 **turn_finalizer.py** 在每轮对话收尾时触发：

```python
# turn_finalizer.py (每轮对话结束时的检查)
if final_response and not interrupted:
    if _should_review_memory or _should_review_skills:
        agent._spawn_background_review(
            messages_snapshot=list(messages),
            review_memory=_should_review_memory,
            review_skills=_should_review_skills,
        )
```

慢速整理回路（Curator）有两个启动入口：

```python
# 入口 A: CLI 启动时
# cli.py, 每次 hermes 命令启动
maybe_run_curator(idle_for_seconds=float("inf"))

# 入口 B: Gateway 定时器
# gateway/run.py, 每 N 个 tick 检查
if tick_count % curator_interval == 0:
    maybe_run_curator(idle_for_seconds=actual_idle)
```

---

## 第三章：快速学习回路（Background Review）

### 3.1 触发器系统

两个独立的计数器驱动快速学习回路：

```python
# 记忆计数器 (在 turn_context.py 中初始化)
agent._turns_since_memory += 1
if agent._turns_since_memory >= agent._memory_nudge_interval:  # 默认 10
    _should_review_memory = True
    agent._turns_since_memory = 0

# 技能计数器 (在 conversation_loop.py 中递增)
agent._iters_since_skill += 1   # 每次工具调用迭代 +1
# 当 skill_manage 工具被成功调用时，计数器清零 (在 tool_executor.py 中)
```

**Nudge 计数器的 Hydration**——跨重启恢复：

```python
# 即使网关重启, 计数器的节奏不会丢失
# 从历史消息中恢复
prior_user_turns = count_prior_user_messages(messages)
agent._turns_since_memory = prior_user_turns % agent._memory_nudge_interval
```

**计数器清零的触发条件**：
- `_turns_since_memory`：达到阈值后自动归零
- `_iters_since_skill`：在 `tool_executor.py` 中，当 `skill_manage` 工具成功执行时归零

### 3.2 核心算法：Fork 审查

```
触发: 每轮对话结束, 满足阈值且未中断
    │
    ▼
_spawn_background_review()           [run_agent.py:1406]
    │ 创建 daemon 线程
    ▼
_run_review_in_thread()              [background_review.py:327]
    │
    ├── 1. 安全初始化
    │   ├── auto-deny callback  ← 所有危险命令自动拒绝
    │   └── stdout/stderr → /dev/null  ← 静默执行
    │
    ├── 2. 获取父 Agent 运行时
    │   ├── provider, model, base_url, api_key
    │   └── 如果 api_mode == "codex_app_server", 降级为 "codex_responses"
    │
    ├── 3. 创建 fork Agent
    │   ├── max_iterations=16          ← 限制步数
    │   ├── skip_memory=True           ← 不碰外部 memory provider
    │   ├── quiet_mode=True            ← 不输出日志
    │   ├── shared: _memory_store      ← 共享内置记忆 (父 Agent 的!)
    │   ├── inherited: _cached_system_prompt ← 命中前缀缓存
    │   ├── override: compression_enabled=False ← 防 session 分裂
    │   └── override: nudge_intervals=0 ← fork 不自触发
    │
    ├── 4. 安装工具白名单
    │   └── 只允许: memory / skill_manage 工具集
    │       └── set_thread_tool_whitelist(whitelist)
    │
    ├── 5. 运行审查对话
    │   ├── user_message = 审查提示词 (见 3.3)
    │   ├── conversation_history = 本轮对话快照
    │   └── run_conversation()
    │
    ├── 6. 提取审查结果
    │   └── summarize_background_review_actions()
    │       ├── 遍历 fork 的全部 tool 消息
    │       ├── 跳过 prior_snapshot 中已有的操作 (去重)
    │       └── 收集 "created/updated/added/removed" 信息
    │
    └── 7. 展示给用户
        └── "Self-improvement review: Memory updated · Skill patched"
```

### 3.3 三种审查提示词

#### 记忆审查（_MEMORY_REVIEW_PROMPT，~10 行）

```
"Review the conversation above and consider saving to memory if appropriate.
Focus on:
1. Has the user revealed things about themselves — their persona, desires,
   preferences, or personal details worth remembering?
2. Has the user expressed expectations about how you should behave, their work
   style, or ways they want you to operate?

If something stands out, save it using the memory tool.
If nothing is worth saving, just say 'Nothing to save.' and stop."
```

审查范围：用户画像、偏好、行为期望。

#### 技能审查（_SKILL_REVIEW_PROMPT，~110 行）

```
"Review the conversation above and update the skill library.

Signals to look for (any one of these warrants action):
  • User corrected your style, tone, format, legibility, or verbosity.
    Frustration signals like 'stop doing X', 'this is too verbose',
    'don't format like this'... are FIRST-CLASS skill signals.
  • User corrected your workflow, approach, or sequence of steps.
  • Non-trivial technique, fix, workaround, debugging path emerged.
  • A skill that got loaded turned out to be wrong or outdated — patch it NOW.

Preference order — pick the earliest that fits:
  1. UPDATE A CURRENTLY-LOADED SKILL (was loaded via /skill-name or skill_view)
  2. UPDATE AN EXISTING UMBRELLA (find via skills_list + skill_view)
  3. ADD A SUPPORT FILE (references/ templates/ scripts/)
  4. CREATE A NEW CLASS-LEVEL UMBRELLA SKILL

Protected skills (DO NOT edit):
  • Bundled skills (shipped with Hermes, e.g. 'hermes-agent')
  • Hub-installed skills (installed via 'hermes skills install')

'Nothing to save.' is a real option but should NOT be the default.
If the session ran smoothly with no corrections and produced no new
technique, just say 'Nothing to save.' and stop. Otherwise, act."
```

审查范围：操作优先级、用户纠错信号、技术方案发现。

#### 综合审查（_COMBINED_REVIEW_PROMPT，~80 行）

同时覆盖记忆和技能两个维度，提示词结构为记忆版块 + 技能版块的组合。

### 3.4 安全边界

| 安全层 | 机制 | 目的 |
|---|---|---|
| **工具白名单** | 只注册 memory + skills 工具集 | 防止 fork 执行危险操作 |
| **Auto-deny Callback** | 所有受保护命令自动拒绝 | 防止死锁（父进程 TUI） |
| **External Provider 隔离** | `skip_memory=True` | 防止审查引导语泄漏到用户记忆 |
| **压缩禁用** | `compression_enabled=False` | 防止 session 分叉（issue #38727） |
| **静默执行** | stdout/stderr → /dev/null | 不干扰用户界面 |
| **迭代限制** | `max_iterations=16` | 防止审查无限循环 |
| **计数归零** | nudge_intervals = 0 | 防止 fork 自触发无限递归 |

关于 `skip_memory=True` 的详细说明（来自源码第 384-398 行的注释）：

```python
# skip_memory=True keeps the review fork from touching external memory
# plugins (honcho, mem0, supermemory, etc.). Without it, the fork's
# __init__ rebuilds its own _memory_manager from config, scoped to the
# parent's session_id, and run_conversation() then leaks the harness
# prompt into the user's real memory namespace via three ingestion sites:
# on_turn_start, prefetch_all, and sync_all.
# Built-in MEMORY.md / USER.md state is re-bound from the parent below
# so memory(action="add") writes from the review still land on disk;
# the review just has zero side effects on external providers.
```

### 3.5 去重与结果展示

```python
def summarize_background_review_actions(review_messages, prior_snapshot):
    """遍历审查 Agent 的 tool 消息, 去重, 构建可读摘要"""
    # 1. 收集 prior_snapshot 中已有的 tool_call_id 和 content
    existing_ids = set()
    existing_contents = set()
    for prior in prior_snapshot:
        if prior.get("role") == "tool":
            if tcid := prior.get("tool_call_id"):
                existing_ids.add(tcid)
            else:
                existing_contents.add(prior.get("content", ""))

    # 2. 遍历 review_messages, 跳过已存在的
    actions = []
    for msg in review_messages:
        if msg.get("role") != "tool":
            continue
        if msg.get("tool_call_id") in existing_ids:
            continue
        # 3. 解析 JSON, 提取成功操作的消息
        data = json.loads(msg.get("content", "{}"))
        if data.get("success"):
            message = data.get("message", "")
            if "added" in message.lower():
                actions.append("Memory updated")
            elif "updated" in message.lower():
                actions.append("Skill updated")
            # ...

    return actions  # ["Memory updated", "Skill patched"]
```

去重意义：审查 fork 继承了父进程的 `conversation_history`，其中已包含之前回合成功的记忆/技能操作。不加去重的话，每一轮审查都会把之前已有的成功操作重新"汇报"一遍。

---

## 第四章：慢速整理回路（Curator）

### 4.1 设计思想

快速学习回路（Background Review）生成的是**碎片化的、局部的**知识——每轮审查可能创建一个小技能、修改一条记忆。随着时间推移，技能库会膨胀，出现重复、过时、过于狭窄的技能。

Curator 的角色就是**定期整理**：归档过时技能、合并重叠技能、构建更抽象的"伞状技能"（umbrella skill）。

### 4.2 触发门控

```python
def should_run_now():
    # 1. 必须启用 (curator.enabled, 默认 True)
    # 2. 必须未暂停 (curator.paused)
    # 3. 必须距离上次运行 >= interval_hours (默认 168h = 7天)
    # 4. 必须系统空闲 idle_for_seconds >= min_idle_hours (默认 2h)
    # 5. 首次运行 (全新安装) 只标记时间, 推迟到下一周期
```

### 4.3 完整审查流程

```
maybe_run_curator()
  │
  ├── should_run_now() 检查通过?
  │   ├── 否 → 跳过, 等待下次
  │   └── 是 → 继续
  │
  ├── 1. 预运行快照
  │   └── agent/curator_backup.py
  │       └── tar.gz ~/.hermes/skills/ (跳过 .curator_backups/ .hub/)
  │
  ├── 2. 自动状态迁移 (apply_automatic_transitions)
  │   ├── 遍历每个 curator 管理的技能
  │   ├── skipped: pinned skills
  │   ├── idle > stale_after_days (30天):  active → stale
  │   ├── idle > archive_after_days (90天): stale → archived
  │   └── stale 后又被使用了: stale → active (重新激活)
  │
  ├── 3. LLM 整合 (需获取压缩锁，防止与 background_review 并发)
  │   ├── 渲染候选技能列表 (agent-created skills + 使用统计)
  │   ├── if 存在候选:
  │   │   └── fork AIAgent (max_iterations=9999)
  │   │       └── CURATOR_REVIEW_PROMPT 指令:
  │   │           "分析技能库, 识别前缀聚类, 合并窄技能到伞状技能
  │   │            使用 skill_manage(action=delete, absorbed_into=<umbrella>)
  │   │            使用 skill_manage(action=patch) 更新伞状技能"
  │   │
  │   └── CURATOR_DRY_RUN_BANNER 变体: 跳过所有修改 (仅模拟)
  │
  ├── 4. 生成报告
  │   └── ~/.hermes/logs/curator/{YYYYMMDD-HHMMSS}/
  │       ├── run.json               ← 结构化结果
  │       ├── REPORT.md              ← 人类可读报告
  │       └── cron_rewrites.json     ← cron job 引用重写
  │
  └── 5. Cron 技能引用重写
      └── 如果有技能被归档, 更新 cron jobs 中的引用
```

### 4.4 技能生命周期

```
        创建 (skill_manage create / hub install)
          │
          ▼
       ┌──────┐
       │active│ ← 正常使用中
       └──┬───┘
           │ 超过 30 天未使用
           ▼
       ┌──────┐
       │stale │ ← 标记为过时 (仍可被使用, 使用后自动恢复)
       └──┬───┘
           │ 超过 90 天未使用
           ▼
       ┌─────────┐
       │archived │ ← 归档到 .archive/ (可恢复)
       └─────────┘
           │ LLM 整合或 curator prune
           ▼
       ┌──────────┐
       │  deleted  │ ← 彻底删除 (absorbed_into 记录去向)
       └──────────┘
```

**关键规则**：
- Curator **从不删除技能**，只归档（archive），可通过 `hermes curator restore <name>` 恢复
- `pinned` 的技能跳过所有自动迁移，但不会阻止内容更新
- 内置技能（bundled）可以被归档（`curator.prune_builtins` 控制）
- Hub 安装的技能 Curator 不会碰

### 4.5 三层去向判定系统

当 Curator 归档一个技能时，会尝试判断它是"被合并了"还是"被清理了"：

| 判定来源 | 优先级 | 方式 |
|---|---|---|
| **模型声明** | 最高 | `skill_manage(action=delete, absorbed_into="umbrella-name")` |
| **审计日志** | 中 | `on_memory_write` / `on_delegation` 事件记录 |
| **启发式** | 低 | 名称前缀匹配、工具调用模式分析 |

模型声明的 `absorbed_into` 是权威信号：
- `absorbed_into="programming-python"` → 内容被合并到该伞状技能
- `absorbed_into=""` → 真正的清理，无转发目标
- `absorbed_into` 未提供 → 兼容旧版本，但下游工具需要猜测

---

## 第五章：技能系统（自主进化的载体）

### 5.1 技能作为"程序性记忆"

技能（skill）是 Hermes 自主进化的**核心载体**。它与记忆（memory）有明确的分工：

```
记忆 (Memory):
  "who the user is and what the current situation is"
  用户偏好 → 保存到 USER.md
  环境事实 → 保存到 MEMORY.md

技能 (Skill):
  "how to do this class of task for this user"
  工作流程 → 创建 SKILL.md
  技术方案 → 创建 SKILL.md + references/
  模板 → 创建 templates/
  脚本 → 创建 scripts/
```

### 5.2 技能目录结构

```
~/.hermes/skills/
├── my-skill/
│   ├── SKILL.md           # 主指令 (必需, YAML frontmatter + Markdown)
│   ├── references/        # 参考文档 (可选)
│   │   ├── api-guide.md
│   │   └── examples.md
│   ├── templates/         # 输出模板 (可选)
│   │   └── report.md
│   ├── scripts/           # 可执行脚本 (可选)
│   │   └── verify.sh
│   └── assets/            # 补充文件 (agentskills.io 标准)
└── category-name/
    └── another-skill/
        └── SKILL.md
```

### 5.3 SKILL.md 格式

```yaml
---
name: skill-name                    # 必需, 最长 64 字符
description: Brief description      # 必需, 最长 1024 字符
version: 1.0.0                      # 可选
platforms: [macos, linux, windows]  # 可选, 限制平台
prerequisites:                      # 可选
  env_vars: [API_KEY]
  commands: [curl, jq]
---

# Skill Title

完整的使用说明...

## 触发条件

在什么情况下应该使用这个技能...

## 步骤

1. 第一步...
2. 第二步...

## 注意事项

- 常见的坑...
```

### 5.4 skill_manage 工具

Agent 通过 `skill_manage` 工具操作技能，提供六个动作：

| 动作 | 功能 | 适用场景 |
|---|---|---|
| `create` | 创建新技能（完整 SKILL.md） | 发现新的可复用工作流 |
| `patch` | 局部替换（old_string / new_string） | 修复/更新现有技能的局部内容 |
| `edit` | 全量重写 SKILL.md | 大规模重构 |
| `delete` | 删除技能（支持 absorbed_into） | 合并或清理 |
| `write_file` | 添加/覆盖支持文件 | 扩展参考文档/模板/脚本 |
| `remove_file` | 删除支持文件 | 清理 |

**安全扫描**：创建和编辑时，如果 `skills.guard_agent_created` 启用，会通过 `tools/skills_guard.py` 进行安全扫描。默认关闭，因为 Agent 已经可以通过 terminal() 执行相同的代码路径。

**缓存失效**：每次技能变更后，调用 `clear_skills_system_prompt_cache()` 清除系统提示词缓存，使下次对话加载最新技能。

### 5.5 技能溯源

```python
# tools/skill_provenance.py
# 区分技能来源:
# - "agent_created": 背景审查 fork 创建的 (curator 可以管理)
# - "user_written": 用户/CLI 命令创建的 (curator 尊重)
# - "bundled": 内置技能 (curator 只可归档, 不修改)
# - "hub_installed": 从市场安装的 (curator 不碰)
```

`is_background_review()` 函数检查当前执行上下文是否来自背景审查 fork，如果是，则创建的技能标记为 `agent_created`，curator 后续可以对其做归档和合并。

---

## 第六章：双回路的协同

### 6.1 时序关系

```
t0: User: "帮我写个 Python 脚本处理 CSV 文件"
    Agent: [完成任务]  ← 用户满意

t1: turn_finalizer: _spawn_background_review()
    → fork Agent 审查对话
    → 判断: "这是一个可复用的数据处理流程"
    → skill_manage(create, name="process-csv")
    → 输出: "Self-improvement review: Skill created"

    (此后的对话中, 如果再次处理 CSV, Agent 会加载 process-csv 技能)

t7 (7 天后, CLI 启动):
    maybe_run_curator()
    → apply_automatic_transitions()
      → process-csv 最近被使用了 → 保持 active
    → _llm_pass()
      → 注意到有 process-csv 和 plot-data 两个技能
      → 决定合并到 umbrella "data-analysis"
      → skill_manage(delete, name="process-csv", absorbed_into="data-analysis")
      → skill_manage(delete, name="plot-data", absorbed_into="data-analysis")
      → skill_manage(patch, name="data-analysis", ...)
    → 生成 REPORT.md
```

### 6.2 互锁机制：压缩锁

快速回路（Background Review）和慢速回路（Curator）都是通过 fork AIAgent 运行的，都可能触发上下文压缩。如果两者同时压缩同一个 session_id，会产生两个孤儿子会话。

```python
# 压缩锁 (在 hermes_state.py 中, session_id 级别)
# 两个回路共享同一个 session_id 检查机制
try_acquire_compression_lock(session_id, holder, ttl=300):
    事务: DELETE expired → INSERT OR IGNORE
    → 成功: 获得锁, 可以压缩
    → 失败: 放弃本轮压缩

# Background Review 的防护:
review_agent.compression_enabled = False  # 直接禁用压缩

# Curator 的防护:
# Curator 在运行前获取压缩锁, 获取失败则跳过本轮
```

### 6.3 共享状态与隔离

| 组件 | 快速回路 (Background Review) | 慢速回路 (Curator) |
|---|---|---|
| **执行方式** | daemon 线程 | 当前线程 / 定时器 |
| **fork 参数** | `skip_memory=True` | 完整初始化 |
| **工具权限** | memory + skills 白名单 | 完整工具集 (9999 次) |
| **共享状态** | 父 Agent 的 `_memory_store` | 独立实例 |
| **压缩** | 禁用 | 启用 (需获取锁) |
| **最大迭代** | 16 | 9999 |
| **用户可见性** | 展示摘要 "Self-improvement: ..." | REPORT.md 写入日志目录 |

### 6.4 前缀缓存继承

两个回路都继承了父进程的 `_cached_system_prompt`，这是一个重要的成本优化：

```python
# 背景审查 fork:
review_agent._cached_system_prompt = agent._cached_system_prompt

# Curator fork:
# (同样继承父进程的缓存系统提示词)
```

没有这个继承，fork 每次都会重建系统提示词（新的时间戳、新的 session_id、不同的工具集），导致前缀缓存 miss。在 Sonnet 4.5 上，这意味着 ~26% 的端到端成本增加。

---

## 第七章：安全分析

### 7.1 安全边界总览

```
┌──────────────────────────────────────────────────────┐
│                    用户交互                            │
│  CLI / TUI / Gateway / ACP                           │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│                AIAgent 主进程                          │
│  - 完整工具集 (file/terminal/browser/web/...)         │
│  - 所有修改直接落地                                   │
└──────────────┬──────────────────┬────────────────────┘
               │                  │
               ▼                  ▼
┌────────────────────────┐ ┌──────────────────────────┐
│ Background Review Fork  │ │ Curator Fork              │
│ - 工具白名单            │ │ - 完整工具集              │
│ - auto-deny             │ │ - auto-deny               │
│ - skip_memory           │ │ - 获取压缩锁              │
│ - 禁用压缩              │ │ - max_iterations=9999     │
│ - max_iterations=16     │ │ - 结果写入日志            │
│ - 结果展示给用户        │ └──────────────────────────┘
└────────────────────────┘
```

### 7.2 风险清单

| 风险 | 场景 | 缓解措施 |
|---|---|---|
| **引导语泄漏** | 审查 fork 的提示词被写入外部记忆 | `skip_memory=True` + `_memory_write_origin = "background_review"` |
| **Session 分叉** | 两个进程同时压缩同一个 session_id | 压缩锁 + 审查 fork 禁用压缩 |
| **审查死锁** | 审查 fork 触发 TUI 交互 | `auto-deny` callback |
| **无限循环** | 审查 fork 自己触发自己的审查 | nudge_intervals = 0 |
| **成本爆炸** | Curator 运行时间过长 | 受父进程迭代预算控制 |
| **技能丢失** | Curator 误删有用技能 | 仅归档不删除 + 备份系统 + restore 命令 |
| **注入污染** | 恶意用户通过记忆写入引导审查 fork | 威胁检测 `_scan_memory_content` |
| **缓存成本** | fork 不继承缓存系统提示词 | `_cached_system_prompt` 显式继承 |

---

## 第八章：代码路径参考

### 8.1 快速回路：完整调用链

```
turn_finalizer.py:360-401
  if final_response and not interrupted:
    if _should_review_memory or _should_review_skills:
      agent._spawn_background_review(...)
        │
        ▼
run_agent.py:1406-1428 (AIAgent._spawn_background_review)
  target, prompt = spawn_background_review_thread(...)
  t = threading.Thread(target=target, daemon=True, name="bg-review")
  t.start()
        │
        ▼
background_review.py:573-598 (spawn_background_review_thread)
  # 选择提示词
  if review_memory and review_skills: prompt = _COMBINED_REVIEW_PROMPT
  elif review_memory: prompt = _MEMORY_REVIEW_PROMPT
  else: prompt = _SKILL_REVIEW_PROMPT
  return lambda: _run_review_in_thread(agent, messages_snapshot, prompt)
        │
        ▼
background_review.py:327-570 (_run_review_in_thread)
  # 见第三章 3.2 节完整流程
```

### 8.2 慢速回路：完整调用链

```
cli.py:10642-10655 / gateway/run.py:15427-15440
  maybe_run_curator(idle_for_seconds=...)
        │
        ▼
agent/curator.py:1830-1849 (maybe_run_curator)
  if not should_run_now(): return
  run_curator_review()
        │
        ▼
agent/curator.py:1420-1621 (run_curator_review)
  # 1. 预运行快照 (backup_skills)
  # 2. apply_automatic_transitions()
  # 3. _llm_pass() → fork AIAgent → CURATOR_REVIEW_PROMPT
  # 4. 生成 run.json + REPORT.md
  # 5. 重写 cron 引用
```

### 8.3 Nudge 计数器：完整数据流

```
agent_init.py:1108-1131 (初始化)
  _memory_nudge_interval = int(mem_config.get("nudge_interval", 10))
  _skill_nudge_interval = int(skills_config.get("creation_nudge_interval", 10))

turn_context.py:184-217 (每轮开始, 恢复 + 递增)
  prior_user_turns = count_prior_user_messages(messages)
  _turns_since_memory = prior_user_turns % _memory_nudge_interval
  _turns_since_memory += 1
  if _turns_since_memory >= _memory_nudge_interval:
    should_review_memory = True
    _turns_since_memory = 0

conversation_loop.py:516-520 (每次工具迭代递增)
  _iters_since_skill += 1

tool_executor.py (skill_manage 成功调用时清零)
  if tool_name == "skill_manage" and result.success:
    agent._iters_since_skill = 0

turn_finalizer.py:377-401 (收尾时检查)
  if _iters_since_skill >= _skill_nudge_interval:
    _should_review_skills = True
    _iters_since_skill = 0
  if final_response and not interrupted:
    agent._spawn_background_review(...)
```

---

## 第九章：设计权衡总结

### 9.1 核心决策矩阵

| 决策 | 权衡 | 选择 | 理由 |
|---|---|---|---|
| **双回路 vs 单回路** | 即时响应 vs 全面整理 | 双回路 | 快速学习不阻塞，慢速整理保证库质量 |
| **Fork vs 内联** | 安全性 vs 资源消耗 | Fork | 进程隔离保证主 Agent 安全 |
| **工具白名单** | 审查效果 vs 风险控制 | 限制 memory + skills | 防止审查产生副作用 |
| **Auto-deny** | 用户交互 vs 安全死锁 | 自动拒绝 | 后台线程没有 TTY |
| **Skip_memory** | 外部记忆同步 vs 污染风险 | 跳过外部 Provider | 防止引导语泄漏 |
| **压缩禁用** | 上下文长度 vs Session 分叉 | 禁用 | 防 session 分裂 (issue #38727) |
| **默认 10 轮 nudge** | 学习频率 vs 成本 | 10 轮 | 兼顾学习机会与 API 成本 |
| **7 天 curator 间隔** | 整理频率 vs 资源消耗 | 7 天 | 大多数项目周粒度足够 |
| **归档不删除** | 存储空间 vs 安全性 | 归档 | 任何技能都可能被误删 |
| **absorbed_into 声明** | 精确性 vs 复杂度 | 模型声明 | 比启发式猜测可靠 |

### 9.2 已知限制

1. **快照滞后性**：背景审查写入的记忆，在当前会话内不进入系统提示词。如果需要当前会话立即生效，需要 LLM 主动通过 tool 读取。

2. **审查覆盖面有限**：`max_iterations=16` 限制了审查的深度。如果审查过程中的工具调用超过 16 次，会被强制截断。

3. **技能质量依赖模型能力**：审查提示词虽然精心设计，但模型对"什么值得记、什么不值得记"的判断仍然有限。

4. **Curator 的资源消耗**：Curator 在 LLM 整合阶段可能消耗大量 token（`max_iterations=9999`），虽然在空闲时运行，但完整一次 curator pass 的 API 成本不低。

5. **跨 Profile 无共享**：审查和 curator 都限制在当前 profile 的技能库内。不同 profile 之间的技能和记忆不共享。

### 9.3 与记忆系统的边界

```
记忆系统 (Memory):
  功能: 存储 "谁" 和 "什么"
  内容: 用户偏好 + 环境事实
  格式: MEMORY.md / USER.md
  变更方式: memory 工具 (add/replace/remove)
  审查工具: background_review fork
  整理: 无 (curator 不整理记忆)

技能系统 (Skill):
  功能: 存储 "怎么做"
  内容: 工作流程 + 技术方案
  格式: SKILL.md + references/templates/scripts
  变更方式: skill_manage 工具 (create/patch/edit/delete)
  审查工具: background_review fork
  整理: curator (归档/合并/清理)
```

---

## 附录 A：关键文件索引

| 文件 | 行数 | 核心职责 |
|---|---|---|
| `agent/background_review.py` | ~600 | 审查提示词 + fork Agent 驱动 + 结果摘要 |
| `agent/curator.py` | ~1,850 | Curator 主逻辑 + 自动迁移 + LLM 整合 |
| `agent/curator_backup.py` | ~700 | 技能库快照回滚 (tar.gz) |
| `agent/turn_finalizer.py` | ~500 | 审查触发 + 计数器检查 + 外部同步 |
| `agent/turn_context.py` | ~400 | Nudge 计数器 hydration + memory prefetch |
| `agent/conversation_loop.py` | ~4,200 | 技能计数器递增 + 主对话循环 |
| `agent/agent_init.py` | ~1,400 | Nudge 间隔初始化 |
| `agent/tool_executor.py` | ~1,800 | `skill_manage` 成功时计数器清零 |
| `tools/skill_manager_tool.py` | ~1,050 | `skill_manage` 工具 (create/patch/edit/delete) |
| `tools/skills_tool.py` | ~800 | `skills_list` / `skill_view` 工具 |
| `tools/skills_hub.py` | ~4,000+ | 技能来源适配器 (GitHub/URL/市场) |
| `tools/skills_guard.py` | ~900 | 技能安全扫描 |
| `tools/skills_sync.py` | ~900 | 技能同步 + `.curator_suppressed` 处理 |
| `tools/skill_usage.py` | ~500 | 技能生命周期 + 用法追踪 + pin 管理 |
| `tools/skill_provenance.py` | ~200 | 技能来源追踪 (agent_created vs user_written) |
| `tools/threat_patterns.py` | ~500 | 威胁模式检测 (记忆注入防护) |
| `run_agent.py` | ~6,000 | `_spawn_background_review` 方法 |
| `cli.py` | ~15,000 | Curator CLI 启动触发 |
| `gateway/run.py` | ~20,000 | Curator 定时器触发 |
| `hermes_cli/curator.py` | ~1,000 | Curator CLI 子命令 |
| `agent/prompt_builder.py` | ~1,000 | `clear_skills_system_prompt_cache()` |

## 附录 B：配置项参考

| 配置键 | 默认值 | 作用域 | 说明 |
|---|---|---|---|
| `memory.nudge_interval` | 10 | 记忆审查 | 多少轮触发一次 Background Review |
| `skills.creation_nudge_interval` | 10 | 技能审查 | 多少次迭代触发一次技能审查 |
| `curator.enabled` | true | Curator | 是否启用 Curator |
| `curator.paused` | false | Curator | 是否暂停 Curator |
| `curator.interval_hours` | 168 | Curator | 运行间隔（7 天） |
| `curator.min_idle_hours` | 2 | Curator | 需要系统空闲多久才运行 |
| `curator.stale_after_days` | 30 | Curator | 多少天未使用标记为 stale |
| `curator.archive_after_days` | 90 | Curator | 多少天 stale 后归档 |
| `curator.prune_builtins` | true | Curator | 是否允许归档内置技能 |
| `skills.guard_agent_created` | false | 安全 | Agent 创建技能时是否安全扫描 |

## 附录 C：术语表

| 术语 | 含义 |
|---|---|
| **Background Review** | 每 N 轮触发的后台审查，fork 子 Agent 自省 |
| **Curator** | 每 7 天触发的技能库整理器 |
| **Nudge** | 周期性触发自省行为的计数器机制 |
| **Fork Agent** | 继承父 Agent 运行时但受限运行的子 Agent |
| **Tool Whitelist** | 审查 fork 可调用的工具限制列表 |
| **Auto-deny** | 后台线程中自动拒绝危险命令的机制 |
| **Umbrella Skill** | 类级伞状技能，合并多个窄技能 |
| **absorbed_into** | 删除技能时声明的合并目标 |
| **Agent-created** | 背景审查 fork 创建的技能（curator 可管理） |
| **Hydration** | 从历史消息恢复 Nudge 计数器的过程 |
| **Skip Memory** | fork 时跳过外部 memory provider 加载 |
| **Compaction Lock** | SQLite 会话级压缩锁，防止 session 分叉 |
| **Prefix Cache** | LLM 提供商的前缀缓存，同字节序列复用 |
| **Progressive Disclosure** | 渐进式信息展示（skills_list → skill_view → files） |
