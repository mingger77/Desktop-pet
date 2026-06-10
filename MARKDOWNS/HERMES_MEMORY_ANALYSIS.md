# Hermes Agent 长期记忆系统分析

> 本文档基于 Hermes Agent（Nous Research 开源项目）的源代码静态分析编写。
> 项目地址：https://github.com/nousresearch/hermes-agent
> 分析版本：0.16.0
>
> 目标读者：无法直接访问 Hermes 源码的项目组。
> 本文档独立完整，无需配合源码阅读。

---

## 第一章：项目背景

### 1.1 Hermes Agent 是什么

Hermes Agent 是一个**开源 AI 智能体框架**，由 Nous Research 开发。它允许用户通过 CLI、终端 UI（TUI）、Web 面板、桌面应用以及 20+ 消息平台（Telegram / Discord / 微信 / Slack 等）与 LLM 驱动的 Agent 交互。

核心定位是"能够自主进化的智能体"——这意味着它能：
- **记住**跨会话的用户偏好和环境信息
- **反思**自己的行为并主动改进
- **扩展**通过技能系统和工具生态

### 1.2 记忆系统解决的问题

AI 智能体的对话本质上是一个**无状态过程**——每次 API 调用都需要把完整的上下文塞进提示词（prompt）。这种无状态性带来了三个根本矛盾：

| 矛盾 | 描述 |
|---|---|
| **稳定 vs 实时** | LLM 提供商的 API 缓存要求系统提示词字节不变；但记忆写入是实时发生的 |
| **成本 vs 完整** | 上下文越长，API 调用越贵（尤其 Anthropic 按 token 计费）；但截断会丢失信息 |
| **能力 vs 安全** | 在系统提示词中插入用户可写的内容（记忆）是 prompt injection 的天然入口 |

Hermes 的记忆系统就是为解决这三个矛盾而设计的。

---

## 第二章：系统架构

### 2.1 三层记忆架构总览

Hermes 的记忆不是单一模块，而是**三层堆叠**：

```
┌──────────────────────────────────────────────────────────────────┐
│ 第三层: 背景自我回顾 (Background Review)                          │
│ 职责: 每轮对话后, 自动检查是否需要保存记忆或更新技能               │
│ 方式: fork 一个子 Agent 在后台运行, 不阻塞用户                     │
│ 文件: agent/background_review.py                                  │
├──────────────────────────────────────────────────────────────────┤
│ 第二层: 长期持久记忆 (Persistent Memory)                           │
│ 职责: 存储跨会话持久信息 (用户画像 + Agent 笔记)                   │
│ 方式: MEMORY.md / USER.md 文件 + 外部 Memory Provider 接口        │
│ 核心文件: tools/memory_tool.py, agent/memory_manager.py            │
│          agent/memory_provider.py                                  │
├──────────────────────────────────────────────────────────────────┤
│ 第一层: 短期工作记忆 (Working Memory)                              │
│ 职责: 当前会话的任务追踪                                         │
│ 方式: TodoStore (内存) + Nudge 计数器 (每 N 轮触发审查)            │
│ 文件: tools/todo_tool.py, agent/turn_context.py                    │
└──────────────────────────────────────────────────────────────────┘
       ↓ 持久化
┌──────────────────────────────────────────────────────────────────┐
│ 基础设施层                                                        │
│ SQLite SessionDB (hermes_state.py): 会话历史 + FTS5 全文搜索       │
│ Git Checkpoints (tools/checkpoint_manager.py): 文件快照 / 回滚     │
│ 上下文压缩 (agent/conversation_compression.py): 会话自动分裂       │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 相关组件全景图

```
run_agent.py: AIAgent (主类)
├── agent_init.py: 初始化
│   ├── MemoryStore           [tools/memory_tool.py]    内置记忆
│   ├── MemoryManager         [agent/memory_manager.py] 外部 Provider 编排
│   └── MemoryProvider(ABC)   [agent/memory_provider.py] 外部后端接口
│
├── turn_context.py: 每轮对话序章
│   ├── MemoryManager.prefetch_all()     ← 预取外部记忆
│   ├── _turns_since_memory 计数器       ← Nudge 触发
│   └── MemoryManager.on_turn_start()   ← 通知 Provider
│
├── conversation_loop.py: 主对话循环
│   ├── API 消息组装 → build_memory_context_block() 注入记忆
│   ├── StreamingContextScrubber 流式输出过滤
│   └── memory tool 调用分发 → MemoryStore
│
├── turn_finalizer.py: 收尾
│   ├── _sync_external_memory_for_turn() ← 同步到外部 Provider
│   └── _spawn_background_review()      ← 启动后台审查
│
├── system_prompt.py: 系统提示词组装
│   └── MemoryStore.format_for_system_prompt() → 冻结快照
│
├── conversation_compression.py: 上下文压缩
│   ├── invalidate_system_prompt() ← 重建系统提示词
│   │   └── MemoryStore.load_from_disk() ← 重新加载记忆
│   └── on_session_switch() ← 通知 Provider
│
├── background_review.py: 后台审查
│   ├── fork AIAgent (共享 MemoryStore)
│   ├── 运行审查提示词 → 调用 memory / skill_manage
│   └── summarize_background_review_actions()
│
└── MemoryProvider 插件          [plugins/memory/*/]
    ├── Honcho (persistent store)
    ├── Hindsight (review engine)
    ├── Mem0 (personalized AI memory)
    └── ...
```

---

## 第三章：核心机制详解

### 3.1 冻结快照模式 (Frozen Snapshot)

这是整个长期记忆系统的**基石**。

#### 问题

Anthropic 的 API 使用**前缀缓存**（prefix caching）：如果系统提示词的字节序列在多次调用中相同，API 提供商会缓存其 KV 状态，后续调用延迟从 ~5 秒降到 ~0.5 秒。但代价是——**系统提示词不能变**。

这意味着：如果每次记忆写入都更新系统提示词，每次 API 调用都会 cache miss。

#### 解决方案

```python
# MemoryStore 有两个状态

# 状态 A: 实时状态 (用于工具响应)
self.memory_entries: List[str]  # ← 每次 add/replace/remove 后更新
self.user_entries: List[str]

# 状态 B: 冻结快照 (用于系统提示词)
self._system_prompt_snapshot: Dict[str, str]  # ← 只在 load_from_disk() 时设置
```

**工作流程**：

```
对话开始：
  → MemoryStore.load_from_disk()
    → 读取 MEMORY.md → memory_entries (实时状态)
    → 读取 USER.md → user_entries (实时状态)
    → 渲染 → _system_prompt_snapshot (冻结快照) ← 此后永不改变

对话中：
  → LLM 调用 memory(action="add", content="用户喜欢简洁的回答")
    → MemoryStore.add()
      → memory_entries.append("用户喜欢简洁的回答")    ← 实时状态更新
      → save_to_disk() → MEMORY.md 文件立即写入       ← 持久化
      → _system_prompt_snapshot 不变                  ← 系统提示词不更新

对话结束（下一轮对话开始）：
  → MemoryStore.load_from_disk()
    → 此时 "用户喜欢简洁的回答" 已经在 MEMORY.md 中
    → 新的 _system_prompt_snapshot 包含这条记忆
```

**优点**：前缀缓存在整个会话中始终保持命中。
**代价**：当前会话写入的记忆，在当前会话的系统提示词中不可见。工具调用的返回值可以实时反映，但 LLM 需要主动通过 memory(read) 来读取。

#### 快照格式

```text
══════════════════════════════════════════
MEMORY (your personal notes) [45% — 990/2,200 chars]
══════════════════════════════════════════
用户喜欢简洁的回答
§
项目使用 pytest 框架
§
用户在 Windows 11 上工作
```

`§`（section sign, U+00A7）是条目分隔符。字符数预算（不是 token 数）是因为字符计数与模型无关。

#### 约束限制

| 存储 | 最大字符 | 用途 |
|---|---|---|
| MEMORY.md | 2,200 | Agent 笔记（环境、约定、工具技巧） |
| USER.md | 1,375 | 用户画像（偏好、沟通风格、习惯） |

### 3.2 原子写入与并发安全

#### 问题

MEMORY.md 是一个普通文件，不是数据库。多个会话、多个进程可能同时写入。用户也可能手动编辑。

#### 解决方案：三步保护

```
第一步: 文件锁 (_file_lock)
  使用 .lock 文件 + fcntl (Unix) / msvcrt (Windows)
  单独的 .lock 文件 → 不干扰原子 rename

第二步: 外部漂移检测 (_detect_external_drift)
  写入前重新解析磁盘文件:
    - 往返检测: 解析→重序列化后的字节是否一致?
    - 条目超限: 是否有单条 > 整个存储的字符预算?
  如果检测到漂移:
    → 备份原始文件为 .bak.<timestamp>
    → 拒绝本次写入

第三步: 原子写入 (_write_file)
  不使用 "open(w) + flock" 模式 (先截断再锁有竞态窗口)
  改为: tempfile.mkstemp() → write → fsync → os.replace()
  读者永远看到完整的旧文件或完整的新文件
```

**漂移检测的两个信号**：

```
信号1: 往返不匹配
  假设磁盘文件内容是:
    entry1\n§\nentry2\n§\n外部工具追加的内容
  解析→重序列化后:
    entry1\n§\nentry2
  和 raw bytes 不匹配 → 漂移

信号2: 条目超限
  假设某个条目的长度:
    len("外部工具追加的大量内容......") > 2200
  单条超过整个存储的预算 → 这不是 memory 工具自己写入的 → 漂移
```

### 3.3 威胁检测 (Injection Prevention)

#### 问题

记忆内容最终进入系统提示词。如果攻击者能通过某种渠道在 MEMORY.md 中写入恶意指令（prompt injection），Agent 可能被操控。

#### 解决方案

```
写入时检测 (写入路径):
  MemoryStore.add()
    → _scan_memory_content(content)
      → tools/threat_patterns.first_threat_message(content, scope="strict")
    → 如果匹配 → 拒绝本次写入, 返回错误

加载时检测 (快照路径):
  MemoryStore.load_from_disk()
    → _sanitize_entries_for_snapshot()
      → 对 memory_entries 的每条运行 scan_for_threats(entry, scope="strict")
      → 匹配 → 用 [BLOCKED: ...] 占位符替换
      → 不匹配 → 原样保留
    → 占位符进入冻结快照
    → 原始内容保留在 memory_entries (用户可以用 memory(read) 查看并删除)
```

**为什么写入和加载时做两次检测**？
- 写入时检测：阻止新的恶意内容进入
- 加载时检测：捕获文件被其他工具/手动编辑污染的情况

**为什么不是直接删除而是替换为占位符**？
- 如果直接删除，攻击者把恶意内容注入到 MEMORY.md 后，用户无法通过 tool 看到它，且攻击者达成了"删除证据"的目的
- 占位符方案：系统提示词不受影响，但用户能看到提示"有条目被阻止"，可以决定是否删除

### 3.4 外部 Memory Provider 系统

#### 架构

内置的 MEMORY.md/USER.md 是"够用"的记忆方案。对于需要更丰富语义检索的场景，Hermes 定义了外部 Provider 接口。

```
MemoryProvider (ABC)
├── name → 标识符 ("honcho", "hindsight", "mem0")
├── is_available() → 检查凭证
├── initialize(session_id, **kwargs) → 初始化
├── get_tool_schemas() → 返回工具定义列表
│
├── 生命周期方法 (可选):
│   ├── system_prompt_block() → 静态提示词片段
│   ├── prefetch(query) → 每轮前召回
│   ├── queue_prefetch(query) → 后台预取下一轮
│   ├── sync_turn(user, assistant) → 每轮后同步
│   ├── handle_tool_call() → 处理工具调用
│   ├── shutdown() → 清理
│
├── 事件钩子 (可选):
│   ├── on_turn_start() → 轮次开始
│   ├── on_session_end() → 会话结束
│   ├── on_session_switch() → session_id 轮换
│   ├── on_pre_compress() → 上下文压缩前
│   ├── on_memory_write() → 内置记忆写入时
│   └── on_delegation() → 子任务完成时
```

**关键约束：最多一个外部 Provider**

```python
def add_provider(self, provider):
    if not is_builtin and self._has_external:
        logger.warning("Rejected: already have an external provider.")
        return  # 拒绝注册
```

原因：每个 Provider 会注册自己的工具 schema。如果有两个外部 Provider，工具注册表会膨胀，且可能产生冲突。

#### 数据流

```
每轮对话开始:
  → MemoryManager.prefetch_all(query)
    → Provider A.prefetch(query) → 返回相关文本
    → 所有非空结果拼接
  → build_memory_context_block() 包装成栅栏
  → 注入到 API 调用 (不入库, 不被用户看到)

每轮对话结束:
  → MemoryManager.sync_all(user_msg, assistant_msg)
    → 后台线程 ThreadPoolExecutor(max_workers=1)
    → Provider A.sync_turn(user_msg, assistant_msg)
    → 保证 turn N 在 turn N+1 之前落地

后台预取下一轮:
  → MemoryManager.queue_prefetch_all(query)
    → 后台线程
    → Provider A.queue_prefetch(query) → 预热缓存
```

### 3.5 上下文栅栏 (Context Fencing)

#### 问题

外部 Provider 召回的记忆是通过**修改用户消息**来注入到 API 调用中的。具体来说，Hermes 把当前轮的用户消息复制一份，在前缀加上 Provider 的召回结果。这意味着：

1. 召回结果**不存储在数据库**中——它只存在于 API 请求中
2. 但如果 LLM 在响应中错误回显了这些内容，它们会出现在用户界面上
3. 召回的文本可能包含 Provider 自身的标记格式

#### 解决方案

```
注入格式:
  <memory-context>
  [System note: ...]
  
  (Provider 召回的内容)
  </memory-context>

输出过滤 (StreamingContextScrubber):
  → 一个状态机, 逐字符处理流式输出
  → 状态: IDLE → IN_FENCE → AFTER_FENCE
  → 识别 <memory-context> 打开 → 丢弃内容
  → 识别 </memory-context> 关闭 → 恢复输出
  → 跨 chunk 边界的部分标签被缓冲
```

状态机的关键挑战是**跨 chunk 边界**处理——流式输出的每个 delta 可能在任何位置切割文本。例如：

```
Chunk 1: "这是一个回答。<memory-con"
Chunk 2: "text>这不应该被看到</memory-context>继续"
```

scrubber 通过 `_max_partial_suffix()` 来识别 buff 的尾部是否是某个标签的前缀，如果是就把这部分保留，等待下一帧确认。

---

## 第四章：背景自我回顾系统

### 4.1 设计思想

这是 Hermes 最接近"自主进化"的设计。每轮有意义的对话后，**一个后台线程 fork 出一个子 Agent，回顾对话并自问"我应该记住什么？应该更新什么技能？"**

### 4.2 完整流程

```
每轮对话结束

  → 检查 Nudge 计数器:
     _turns_since_memory >= 10?  (默认)
     _iters_since_skill >= 10?   (默认)

  → 记忆同步 (非阻塞):
     MemoryManager.sync_all()     → 后台写入外部 Provider
     MemoryManager.queue_prefetch_all() → 后台预取

  → 启动审查 (如果达到阈值):
     _spawn_background_review()
       → spawn_background_review_thread()
         → _run_review_in_thread()

           1. 设置 auto-deny callback (所有交互操作自动拒绝)
           2. 获取父 Agent 的运行时信息 (provider, model, api_key, base_url)
           3. 创建 fork AIAgent (关键参数):
              - skip_memory=True          ← 不碰外部 memory provider
              - max_iterations=16         ← 限制步数
              - 共享父 Agent 的 _memory_store ← 写入内置记忆
              - 继承父 Agent 的缓存系统提示词  ← 命中前缀缓存
              - compression_enabled=False   ← 防止 session 分裂
           4. 安装工具白名单:
              只允许: memory 工具 + skill_manage 工具
              其他工具运行时拒绝
           5. 运行审查对话:
              user_message = _COMBINED_REVIEW_PROMPT
              conversation_history = 本轮对话的快照
           6. 提取审查结果:
              summarize_background_review_actions()
              去重 (跳过审查继承的历史中已有的操作)
           7. 向用户展示:
              "Self-improvement review: Memory updated · Skill patched"
```

### 4.3 三种审查提示词

| 类型 | 触发条件 | 审查目标 |
|---|---|---|
| 记忆审查 | `_turns_since_memory >= interval` | 用户画像、偏好、行为期望 |
| 技能审查 | `_iters_since_skill >= interval` | 工作流程、重复模式、新的技术方案 |
| 综合审查 | 两者同时触发 | 同时覆盖记忆和技能 |

记忆审查的提示词核心逻辑：

```
"Review the conversation above and consider saving to memory if appropriate.
Focus on:
1. Has the user revealed things about themselves — their persona, desires,
   preferences, or personal details worth remembering?
2. Has the user expressed expectations about how you should behave...?
If nothing is worth saving, just say 'Nothing to save.' and stop."
```

技能审查的提示词核心逻辑更详细（约 110 行），包含操作优先级：

```
Preference order — pick the earliest that fits:
  1. UPDATE A CURRENTLY-LOADED SKILL (skill_view 查看过的)
  2. UPDATE AN EXISTING UMBRELLA (skills_list 查找)
  3. ADD A SUPPORT FILE (references/ templates/ scripts/)
  4. CREATE A NEW CLASS-LEVEL UMBRELLA SKILL
```

### 4.4 安全边界

| 安全措施 | 实现 | 目的 |
|---|---|---|
| 工具白名单 | `set_thread_tool_whitelist()` | 只允许 memory + skill_manage |
| Auto-deny | `_bg_review_auto_deny()` | 危险命令自动拒绝 |
| 外部 Provider 隔离 | `skip_memory=True` | 不污染用户的外部记忆 |
| 禁用压缩 | `compression_enabled=False` | 防止 session 分裂竞争 |
| 共享快照 | 继承 `_cached_system_prompt` | 命中相同的前缀缓存 |
| 静音执行 | stdout/stderr → /dev/null | 不干扰用户界面 |

### 4.5 Nudge 计数器 hydration

Nudge 计数器有一个重要的细节：**跨重启恢复**。

```python
# turn_context.py (每轮开始时)
# 从历史消息中恢复计数器, 保持跨会话的节奏
if agent._memory_nudge_interval > 0:
    prior_user_turns = count_prior_user_messages(messages)
    agent._turns_since_memory = prior_user_turns % agent._memory_nudge_interval
```

这意味着即使网关缓存重启，Agent 也不会丢失"已经过了多少轮"这个状态，nudge 的节奏能正确延续。

---

## 第五章：记忆与上下文压缩的交互

### 5.1 压缩即分裂

Hermes 的上下文压缩不是"压缩当前上下文继续用"，而是**分裂成父子会话**：

```
原始会话: session_id = "abc123"
  ↓ (上下文超过 50% 阈值)
压缩事件触发:
  1. 获取压缩锁 (SQLite, 防并发)
  2. 通知外部 Provider: on_pre_compress()
  3. LLM 总结中间轮次
  4. 结束旧会话: session_db.end_session("abc123", "compression")
  5. 创建新会话: session_db.create_session(id="def456", parent="abc123")
  6. 失效系统提示词: invalidate_system_prompt()
     → MemoryStore.load_from_disk()  ← 重新加载记忆 (新快照)
  7. 重新注入 todo 清单
  8. 压缩头部声明: "记忆是权威的, 不要因为压缩而忽略记忆"
  9. 通知 Provider: on_session_switch("def456", parent="abc123")
```

### 5.2 链式结构

多次压缩形成链：

```
s1 (原始会话) → 压缩 → s2 → 再次压缩 → s3
                                    ↑ 当前活跃
```

这种链式结构对用户是透明的：
- `list_sessions_rich()` 使用递归 CTE 将链压缩为一条记录
- `search_messages()` 沿 parent 链回溯到根
- `resume s1` → 自动重定向到 s3（有最新消息的叶节点）

### 5.3 压缩锁

```
try_acquire_compression_lock(session_id, holder="main", ttl=300):
  事务: DELETE expired → INSERT OR IGNORE → SELECT 确认
  holder="pid:tid:nonce"
  ttl=300s (过期自动回收)
  
  → 如果 lock 获取失败 (被 background_review fork 持有)
    → 放弃本轮压缩, 返回未压缩的消息
```

解决场景：主进程和后台审查 fork 同时决定压缩同一个 session_id → 只有一个成功，另一个放弃。

### 5.4 压缩头部保护

压缩后的摘要中插入了以下声明，防止 LLM 认为"摘要可以替代原始记忆"：

```text
"Your persistent memory (MEMORY.md, USER.md) in the system prompt is
 ALWAYS authoritative and active — never ignore or deprioritize
 memory content due to this compaction note."
```

---

## 第六章：系统提示词中的记忆

### 6.1 三层结构

```python
build_system_prompt_parts(agent):
    stable层:
      - 身份声明 ("You are Hermes Agent...")
      - MEMORY_GUIDANCE (记忆使用指导)
      - 工具定义
      → 字节稳定, 用于前缀缓存

    context层:
      - 上下文文件 (规则, 任务说明)
      - Soul identity (人格设定, 可选)
      → 会话内稳定

    volatile层:
      - MemoryStore 冻结快照 (MEMORY.md)  ← 记忆在这里
      - MemoryStore 冻结快照 (USER.md)
      - 外部 Provider system_prompt_block()
      - 时间戳 / Session ID / 模型信息
      → 会话内稳定 (快照不变)
```

### 6.2 MEMORY_GUIDANCE 注入

在 prompt_builder.py 中定义了约 20 行的记忆使用指导：

```text
"You have persistent memory across sessions. Save durable facts using the
 memory tool: user preferences, environment details, tool quirks, and
 stable conventions.

 Do NOT save task progress, session outcomes, completed-work logs, or
 temporary TODO state to memory; use session_search to recall those from
 past transcripts.

 Write memories as declarative facts, not instructions to yourself.
 'User prefers concise responses' ✓ — 'Always respond concisely' ✗.
 Procedures and workflows belong in skills, not memory."
```

这是 Agent 的灵魂指令——告诉它该记什么、不该记什么、怎么记。

### 6.3 分段缓存策略

```
整个系统提示词作为一块整体的字符串被缓存 (agent._cached_system_prompt)
重建时机:
  - 会话初始化 (一次)
  - 上下文压缩后 (可能多次)

stable 层 + context 层 + volatile 层 拼接后一起缓存
Hermes 不发送"增量更新"——总是发送完整的系统提示词

这意味着:
  - 字节不变 = 缓存命中
  - 任何一层变化 (包括 volatile 层的时间戳) = 缓存 miss
```

这也是冻结快照模式如此重要的原因——volatile 层虽然标记为"易变"，但只要快照不变，volatile 层的字节就是稳定的。

---

## 第七章：关键代码路径

### 7.1 memory 工具注册

```python
MEMORY_SCHEMA = {
    "name": "memory",
    "description": "Save durable information to persistent memory that
                    survives across sessions...",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "target": {"type": "string", "enum": ["memory", "user"]},
            "content": {"type": "string"},
            "old_text": {"type": "string"},
        },
        "required": ["action", "target"],
    },
}

registry.register(
    name="memory",
    toolset="memory",
    schema=MEMORY_SCHEMA,
    handler=lambda args, **kw: memory_tool(
        action=args.get("action"),
        target=args.get("target", "memory"),
        content=args.get("content"),
        old_text=args.get("old_text"),
        store=kw.get("store"),
    ),
    emoji="🧠",
)
```

### 7.2 记忆写入完整链路

```
LLM: memory(action="add", target="memory", content="用户偏好简洁回答")

1. registry.dispatch("memory", args)
    → 查找 ToolEntry "memory"
    → 调用 handler

2. memory_tool()
    → 验证 action/target
    → store.add("memory", "用户偏好简洁回答")

3. MemoryStore.add("memory", content)
    a. content = content.strip()
    b. if not content → 拒绝
    c. _scan_memory_content(content) → 威胁检测
    d. with _file_lock(path):  ← 跨进程锁
        e. _reload_target("memory")
            → _detect_external_drift("memory") → 漂移检测
            → 从磁盘重新读取 → 合并其他会话的写入
        f. if content in entries → "duplicate" (去重)
        g. 计算新总字符数 → 检查预算
        h. entries.append(content)
        i. self.save_to_disk("memory")
            → _write_file(MEMORY.md, entries)
              → tempfile.mkstemp() + write + fsync + os.replace()
    j. 返回 _success_response()
       → 包含: 当前所有条目 + 使用率百分比 + 条目计数

4. MemoryManager.on_memory_write() (通知外部 Provider)
    → 跳过 "builtin" Provider
    → 检查 metadata 兼容性
    → 通知外部 Provider
```

### 7.3 记忆读取完整链路

```
系统提示词中:
  build_system_prompt()
    → MemoryStore.format_for_system_prompt("memory")
      → 返回 _system_prompt_snapshot["memory"]
      → 这是 load_from_disk() 时固定的内容

工具调用中:
  LLM: memory(action="add", ...) 返回后
    → 响应中包含 MemoryStore 当前的 memory_entries
    → 这是实时状态 (包括本次会话写入的)

外部 Provider:
  turn_context.py
    → MemoryManager.prefetch_all(query)
      → Provider A.prefetch(query)
    → build_memory_context_block() → <memory-context>栅栏
    → 注入 API 调用

会话历史搜索:
  LLM: session_search(query="用户偏好")
    → FTS5 搜索 (SQLite, unicode61 + trigram 双索引)
    → 返回匹配片段 + 上下文窗口
```

---

## 第八章：设计权衡总结

### 8.1 设计决策矩阵

| 决策 | 权衡 | 选择 | 原因 |
|---|---|---|---|
| **冻结快照** | 缓存性能 vs 信息新鲜度 | 缓存性能 | Anthropic 前缀缓存 ~5s vs 工具响应实时可用 |
| **原子写入** | 写入安全 vs 实现简单 | 安全优先 | 防止并发写入文件损坏 |
| **漂移检测** | 数据安全 vs 用户体验 | 安全优先 | 宁可拒绝写入也不静默覆盖外部内容 |
| **单外部 Provider** | 工具表简洁 vs 灵活 | 简洁优先 | 防止注册表膨胀 + 冲突 |
| **后台同步** | 响应速度 vs 时序保证 | 响应速度 | Provider 可能阻塞 ~298s |
| **审查 fork** | 安全隔离 vs 实现复杂度 | 安全优先 | 工具白名单 + auto-deny + 分进程 |
| **压缩即分裂** | 上下文连续 vs 数据可回溯 | 回溯优先 | 链式结构保证历史完整性 |
| **字符预算(非 token)** | 精细度 vs 模型无关性 | 模型无关 | token 计数依赖 tokenizer, 字符计数通用 |

### 8.2 已知限制

1. **快照滞后性**
   当前会话写入的记忆，在当前会话的系统提示词中不可见。LLM 需要主动通过工具响应获取最新状态。

2. **文件锁退化**
   当 `fcntl` 和 `msvcrt` 都不可用时，锁无声退化到无锁运行（代码第 219-221 行）。

3. **审查 fork 共享引用**
   fork Agent 共享父进程的 `_memory_store` 引用。两者同时写入是安全的（文件锁 + 原子操作），但需要注意这种共享关系。

4. **跨会话写入竞争**
   两个独立会话同时写入 MEMORY.md 时，后一个会触发漂移检测并被拒绝。需手动整合 `.bak` 文件。

5. **分隔符冲突**
   条目分隔符是 `§`（U+00A7）。如果条目内容本身包含这个字符，解析会错误分裂。这是设计选择——在大多数应用场景中，`§` 出现在记忆内容中的概率极低。

### 8.3 与 SessionDB 的边界

```
长期记忆系统 (MemoryStore):
  - 存储: ~/.hermes/memories/MEMORY.md
         ~/.hermes/memories/USER.md
  - 内容: 用户画像、Agent 笔记
  - 写入频率: 低 (每轮可能 0-3 次)
  - 访问方式: memory 工具 / 系统提示词注入

会话历史系统 (SessionDB):
  - 存储: ~/.hermes/state.db (SQLite + FTS5)
  - 内容: 完整的对话历史、token 计费
  - 写入频率: 高 (每条消息)
  - 访问方式: session_search 工具 / FTS5 全文搜索

指导原则:
  "Memory captures 'who the user is and what the current situation and
   state of your operations are'; skills capture 'how to do this class
   of task for this user'."
  "Do NOT save task progress, session outcomes, completed-work logs, or
   temporary TODO state to memory; use session_search to recall those."
```

---

## 附录 A：关键文件索引

| 文件 | 核心类/函数 | 职责 |
|---|---|---|
| `tools/memory_tool.py` | `MemoryStore` | MEMORY.md/USER.md 读写 + memory 工具 |
| `agent/memory_manager.py` | `MemoryManager` | Provider 编排 (prefetch/sync/钩子) |
| `agent/memory_provider.py` | `MemoryProvider` | 外部 Provider 抽象接口 |
| `agent/background_review.py` | `_run_review_in_thread()` | 后台自我审查 |
| `agent/conversation_compression.py` | `compress_context()` | 上下文压缩 + session 分裂 |
| `agent/turn_context.py` | `build_turn_context()` | Prefetch 触发 + nudge 计数 |
| `agent/turn_finalizer.py` | `finalize_turn()` | Sync 触发 + 背景审查调度 |
| `agent/system_prompt.py` | `build_system_prompt_parts()` | 系统提示词组装 |
| `agent/prompt_builder.py` | `MEMORY_GUIDANCE` | 记忆使用指导文本 |
| `run_agent.py` | `AIAgent` | 同步方法 + 背景审查启动 |
| `hermes_state.py` | `SessionDB` | SQLite 会话历史仓库 |
| `tools/session_search_tool.py` | `session_search()` | FTS5 会话搜索 |
| `tools/todo_tool.py` | `TodoStore` | 会话内待办清单 |
| `tools/threat_patterns.py` | `first_threat_message()` | 威胁模式检测 |

## 附录 B：配置项参考

| 配置键 | 默认值 | 作用 |
|---|---|---|
| `memory_enabled` | false | 启用 MEMORY.md |
| `user_profile_enabled` | false | 启用 USER.md |
| `memory.provider` | "" | 外部 Memory Provider 名称 |
| `memory.nudge_interval` | 10 | 记忆审查间隔(轮) |
| `memory.char_limit` | 2200 | MEMORY.md 字符预算 |
| `user.char_limit` | 1375 | USER.md 字符预算 |
| `skills.creation_nudge_interval` | 10 | 技能审查间隔(轮) |

## 附录 C：术语表

| 术语 | 含义 |
|---|---|
| Agent | 运行在 CLI/网关/TUI 中的 AI 对话实例 |
| Session | 一次连续的对话 |
| Turn | 一次用户输入 + Agent 响应 |
| Nudge | 周期性触发自省行为的计数器机制 |
| Freeze Snapshot | 会话开始时固定的记忆快照，用于系统提示词 |
| Memory Provider | 外部记忆后端（Honcho, Mem0 等） |
| Context Fence | `<memory-context>` 标签，防止外部记忆泄漏到 UI |
| Background Review | 后台子 Agent 自省，决定是否更新记忆/技能 |
| Compression | 上下文超过阈值时，LLM 总结中间轮次并分裂 Session |
| Compaction Lock | SQLite 锁，防止主进程和审查 fork 同时压缩 |
| External Drift | 磁盘文件被外部工具修改，与内存状态不一致 |
| Hydration | 从历史消息恢复 Nudge 计数器 |
