# Hermes Agent 记忆系统深度解析

> 本文档基于 Hermes Agent（Nous Research 开源项目）的源代码分析，深入解析其记忆系统的架构设计、核心思想和代码实现。

---

## 一、概览：三层记忆架构

Hermes 的记忆不是单一模块，而是**三层叠构**：

```
┌─────────────────────────────────────────────────────────────┐
│  第三层: 背景自我回顾 (Background Review)                    │
│  agent/background_review.py — 每轮对话后 fork 子 Agent      │
│  反思自己: "我该记住什么？该更新什么技能？"                    │
├─────────────────────────────────────────────────────────────┤
│  第二层: 长期持久记忆 (Persistent Memory)                    │
│  tools/memory_tool.py → MEMORY.md + USER.md                 │
│  agent/memory_manager.py → 外部 Memory Provider 编排         │
│  核心思想: 冻结快照 + 原子写入 + 注入检测                      │
├─────────────────────────────────────────────────────────────┤
│  第一层: 短期工作记忆 (Working Memory)                       │
│  tools/todo_tool.py — 当前会话待办清单                       │
│  agent/turn_context.py — nudge 计数器                         │
│  核心思想: 压缩后重新注入, 计数器中文化                        │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│  基础设施层: SQLite 状态仓库 + 检查点系统                     │
│  hermes_state.py — SessionDB (FTS5 全文搜索)                 │
│  tools/checkpoint_manager.py — Git 快照式文件版本管理         │
│  agent/context_compressor.py — 上下文压缩 (压缩即分裂)       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、第一层：工作记忆 (Working Memory)

### 2.1 TodoStore — 会话待办清单

**文件**: `tools/todo_tool.py`

**关键设计**: 纯内存的、每 Agent 实例一份的待办列表。核心挑战是**如何在上下文压缩后存活**。

```python
class TodoStore:
    def write(self, todos, merge=False):
        # merge=False → 全量替换; merge=True → 按 id 合并更新
        pass

    def format_for_injection(self):
        # 只返回 pending/in_progress 的活跃项
        # 在上下文压缩后被调用, 重新注入到 LLM 的上下文
        return None if not active_items else rendered_text

    def read(self):
        return copy(self._items)  # 返回快照, 防止外部修改
```

**核心思想**: `format_for_injection()` 是连接短期记忆和长期压缩的桥梁——压缩发生时，待办清单不会丢失，而是被注入到压缩后的消息中。

**约束**:
- `MAX_TODO_CONTENT_CHARS = 4000`（每条）
- `MAX_TODO_ITEMS = 256`（总数）
- 四种状态: `pending` / `in_progress` / `completed` / `cancelled`

### 2.2 Nudge 机制 — 周期性自我提醒

**文件**: `agent/turn_context.py` (line 184-217)

```python
# 每轮对话开始时
agent._turns_since_memory += 1
if agent._turns_since_memory >= agent._memory_nudge_interval:
    should_review_memory = True
    agent._turns_since_memory = 0
```

**关键设计**: Nudge 计数器做了**中文化 (hydration)** 处理——即使网关缓存重启，Agent 从历史消息中恢复时，计数器会从 `prior_user_turns % interval` 开始，保证节奏不被打乱。

```python
# 会话启动时, 从历史消息计数恢复
_turns_since_memory = prior_user_turns % _memory_nudge_interval
# 配置: nudge_interval = 10 (默认, 可在 config.yaml 中覆盖)
```

三种 Nudge 类型并存：

| Nudge 类型 | 触发条件 | 作用 |
|---|---|---|
| Memory Nudge | 每 10 轮对话 | 触发记忆背景审查 |
| Skill Nudge | 每 10 次工具调用 | 触发技能审查 |
| Post-Tool Empty Nudge | 模型返回空内容 | 追加恢复提示 |

---

## 三、第二层：长期持久记忆 (核心)

这是整个记忆系统的灵魂所在。核心思想围绕一个矛盾展开：**LLM 看到的上下文需要稳定（否则前缀缓存失效），但记忆需要实时更新**。

### 3.1 冻结快照模式 (Frozen Snapshot)

**文件**: `tools/memory_tool.py` — `MemoryStore` 类

```python
# MemoryStore 初始化时
def load_from_disk(self):
    self.memory_entries = read_and_dedup("MEMORY.md")
    self.user_entries = read_and_dedup("USER.md")
    # ★ 关键: 创建一次性冻结快照
    self._system_prompt_snapshot = {
        "memory": self._sanitize_entries_for_snapshot(
            self.memory_entries, "MEMORY.md"
        ),
        "user": self._sanitize_entries_for_snapshot(
            self.user_entries, "USER.md"
        ),
    }

# 系统提示词永远从快照读取, 不看到实时数据
def format_for_system_prompt(self, target):
    return self._system_prompt_snapshot.get(target)  # 可能是 None
```

**核心思想**: 系统提示词在一个会话内**永不改变**。即使用户在对话中写入了新记忆，LLM 在当前会话中也看不到——它用的是初始化时的冻结快照。

**为什么？** 因为 Anthropic 的 prompt caching 依赖系统提示词的稳定性，实时更新会导致缓存失效，增加延迟和成本（每次 ~5 秒的 cache miss）。

**那新记忆什么时候生效？**

1. **下一次会话开始时** — 冻结快照会被重建
2. **上下文压缩事件后** — 系统提示词会被失效并重建：

```python
# agent/system_prompt.py
def invalidate_system_prompt(agent):
    agent._system_prompt = None          # 清除缓存
    agent._memory_store.load_from_disk() # 重新加载 → 新快照
```

**安全注入检测**也是写入时的重要环节：

```python
def _scan_memory_content(self, content):
    # 使用 tools/threat_patterns.py 扫描 prompt injection 模式
    if matches_threat_pattern(content):
        raise ValueError("Memory content blocked: potential injection")
```

如果检测到威胁，原始内容保留在内存中（用户可以查看和删除），但**快照中被替换为 `[BLOCKED: ...]` 占位符**——安全而不丢数据。

### 3.2 原子写入与外部漂移检测

**文件**: `tools/memory_tool.py`

```python
def save_to_disk(self, target):
    f_path = self._get_path(target)
    # ★ 原子写入: 先写临时文件, 再 rename
    tmp = f_path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(f_path)  # os.replace = 原子操作

def _detect_external_drift(self, target):
    # ★ 检测外部修改: 如果磁盘内容和内存状态不一致
    # (比如用户用 vim 手动改了 MEMORY.md, 或者其他会话改了)
    # 则拒绝本次修改并备份文件
```

**核心思想**: MEMORY.md 不是数据库，只是一个 Markdown 文件。这意味着：

- **开放性**: 用户可以用任何编辑器手动修改
- **竞态**: 多个会话可能同时写入
- **一致性方案**: 文件锁 + 原子写入 + 漂移检测 三者配合

```python
# 文件锁
def _file_lock(self, path):
    # Unix: fcntl.flock, Windows: msvcrt.locking
    # 在单独的 .lock 文件上实现跨进程互斥
```

**条目分隔符**: `\n§\n` (section sign) — 允许条目内容包含多行文本。

**字符预算约束**（基于字符而非 token，因为字符是模型无关的）：
- memory（MEMORY.md）: **2200 字符**
- user（USER.md）: **1375 字符**

### 3.3 外部 Memory Provider 系统

**文件**: `agent/memory_provider.py` — `MemoryProvider` ABC

ABC 定义了记忆后端需要实现的接口：

```python
class MemoryProvider(ABC):
    # ★ 抽象方法: 每个后端必须实现
    @abstractmethod
    def get_tool_schemas(self):
        """返回该 provider 暴露的工具 schema"""
        ...

    @abstractmethod
    def prefetch(self, query, *, session_id):
        """每轮对话前召回相关记忆"""
        ...

    @abstractmethod
    def is_available(self):
        """检查配置/凭证是否可用"""
        ...

    # ★ 生命周期钩子 (可选)
    def on_turn_start(self, turn_number, message, **kwargs):
        """轮次开始"""
    def on_session_end(self, messages):
        """会话结束 → 提取事实"""
    def on_session_switch(self, new_session_id, **kwargs):
        """会话旋转 (分支/恢复/压缩)"""
    def on_pre_compress(self, messages):
        """压缩前提取洞察"""
    def on_delegation(self, task, result, child_session_id):
        """子代理工作的父侧观察"""
    def on_memory_write(self, action, target, content, metadata):
        """镜像内置记忆写入到外部后端"""
```

**文件**: `agent/memory_manager.py` — `MemoryManager`

MemoryManager 是编排中心，协调内置记忆 + 至多一个外部 Provider：

```python
class MemoryManager:
    def prefetch_all(self, query, *, session_id):
        """★ 每轮对话前: 从所有 provider 召回相关记忆"""
        for provider in self.providers:
            try:
                raw = provider.prefetch(query, session_id=session_id)
                results.append(raw)
            except Exception:
                continue  # 故障隔离
        return build_memory_context_block("\n".join(results))

    def sync_all(self, user_content, assistant_content, *,
                 session_id, messages):
        """★ 每轮对话后: 后台同步到外部 provider"""
        self._bg_executor.submit(self._do_sync, ...)

    def queue_prefetch_all(self, query, *, session_id):
        """★ 后台预取下一轮记忆"""
        self._bg_executor.submit(self._do_prefetch, ...)
```

**关键数据流**:

```
每轮对话开始
  → MemoryManager.prefetch_all(query)
    → 外部 Provider 返回相关记忆片段
    → 包装在 <memory-context>...</memory-context> 栅栏中
    → 注入到用户消息前 (仅 API 调用时有, 不入库)

每轮对话结束
  → MemoryManager.sync_all(user_msg, assistant_msg)
    → 后台线程调用 Provider.sync_turn()
    → Provider 自行决定是否需要持久化
```

**记忆管理器中的后台执行器**使用单工作线程 `ThreadPoolExecutor(max_workers=1)` 保证 turn 的顺序性。

### 3.4 上下文栅栏 (Context Fencing)

**文件**: `agent/memory_manager.py`

```python
def build_memory_context_block(raw_context):
    # 外部 provider 召回的记忆用栅栏包裹
    return (
        f"<memory-context>\n{raw_context}\n</memory-context>\n"
        "[system note: ...]"
    )

class StreamingContextScrubber:
    """★ 流式输出时, 逐字符清除栅栏标签
       防止 <memory-context> 泄漏到用户界面"""
    def __init__(self):
        self._buffer = ""
        self._state = "IDLE"  # IDLE / IN_FENCE / AFTER_FENCE

    def feed(self, text):
        """状态机: 识别开始标签 → 跳过内容 → 识别结束标签"""
        result = []
        for char in text:
            match self._state:
                case "IDLE":
                    self._buffer += char
                    if "<memory-context>" in self._buffer:
                        visible, _ = self._buffer.split("<memory-context>", 1)
                        result.append(visible)
                        self._buffer = ""
                        self._state = "IN_FENCE"
                case "IN_FENCE":
                    self._buffer += char
                    if "</memory-context>" in self._buffer:
                        self._buffer = ""
                        self._state = "AFTER_FENCE"
                case "AFTER_FENCE":
                    result.append(char)
        return "".join(result)

    def flush(self):
        """流结束时释放缓冲区"""
        ...

    def reset(self):
        """每轮对话重置"""
        self._buffer = ""
        self._state = "IDLE"
```

**核心思想**: 外部记忆是**注入到 API 调用中的辅助信息，不应该被用户看到，也不应该被持久化**。流式清除器作为一个状态机在逐 token 的输出流中实时过滤这些栅栏标记。

---

## 四、第三层：背景自我回顾 (Background Review)

**文件**: `agent/background_review.py`

这是 Hermes 最接近"自主进化"的设计——**每轮有意义的对话后，一个后台线程 fork 出一个精简 Agent，回顾对话并自问"我应该记住什么？"**

三种审查提示词：

```python
_MEMORY_REVIEW_PROMPT = """
回顾刚才的对话, 思考是否需要保存关于用户的信息:
用户画像、偏好、习惯、行为期望、重要环境事实...

使用 memory 工具来保存发现。
如果无需保存, 回复 "Nothing to save."
"""

_SKILL_REVIEW_PROMPT = """
考虑是否需要更新或创建技能:
重复出现的任务、可自动化的流程...

使用 skill_manage 工具。
"""

_COMBINED_REVIEW_PROMPT = """
一次覆盖记忆和技能审查:
用户画像 + 技能需求一起考虑。
"""
```

审查流程的代码实现：

```python
def _run_review_in_thread(agent, messages_snapshot, prompt):
    # 1. 安装 auto-deny callback (拒绝所有危险操作)
    # 2. 创建 fork Agent (继承父 Agent 的 runtime)
    fork = AIAgent(
        provider=agent.provider,
        model=agent.model,
        api_key=agent.api_key,
        skip_memory=True,  # 不加载外部 memory provider
    )

    # ★ 共享父 Agent 的 MemoryStore
    #    fork 写入 memory, 父 Agent 就能读到
    fork._memory_store = agent._memory_store
    fork._memory_enabled = agent._memory_enabled
    fork._user_profile_enabled = agent._user_profile_enabled
    fork._memory_write_origin = "background_review"  # 来源追踪

    # ★ 工具白名单: 只能调用 memory 和 skill_manage
    fork._tool_whitelist = {"memory", "skill_manage"}

    # ★ 禁用压缩 (审查对话短, 不需要)
    fork._disable_compression = True

    # ★ 继承父 Agent 的缓存系统提示词
    #    保持 Anthropic prefix cache 有效
    fork._cached_system_prompt = agent._cached_system_prompt

    # 3. 运行审查对话
    fork.run_conversation(prompt, messages_snapshot)

    # 4. 总结结果
    summarize_background_review_actions(...)
    fork.shutdown()
```

**执行后的用户反馈**：

```python
def summarize_background_review_actions(review_messages, prior_snapshot):
    """遍历审查 Agent 的工具调用, 去重, 构建可读摘要"""
    actions = []
    for msg in review_messages:
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                # 跳过已存在于快照中的条目
                if tc["id"] in prior_tool_call_ids:
                    continue
                actions.append(f"{tc['function']['name']}: {tc['function']['arguments']}")
    return actions  # → "Self-improvement review: Memory updated"
```

**核心设计思想**:

| 思想 | 实现 | 目的 |
|---|---|---|
| **非阻塞** | daemon 线程, 用户不用等 | 不打断用户体验 |
| **安全隔离** | 工具白名单 + auto-deny callback | 防止 fork 误操作 |
| **共享状态** | fork 和父进程共享 `_memory_store` | 写入立即可见 |
| **去重** | `summarize_background_review_actions()` | 避免重复保存 |
| **来源追踪** | `_memory_write_origin = "background_review"` | 审计和镜像钩子 |

---

## 五、基础设施层

### 5.1 SessionDB — SQLite 状态仓库

**文件**: `hermes_state.py`（~3000 行）

这不是"记忆系统"本身，但它是支撑记忆的**基石存储**。

#### 五张核心表

```sql
-- schema_version: 单行记录, 当前 v15 (用于迁移追踪)
CREATE TABLE schema_version (version INTEGER);

-- sessions: 会话元数据
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,         -- 会话 ID
    source TEXT,                 -- 来源: cli, telegram, discord ...
    model TEXT,                  -- 使用的模型
    model_config TEXT,           -- JSON 配置
    system_prompt TEXT,          -- 系统提示词
    parent_session_id TEXT,      -- ★ 父会话链 (压缩链)
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    end_reason TEXT,             -- compression / finished / interrupted
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens INTEGER,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    title TEXT,
    api_call_count INTEGER,
    handoff_state TEXT,
    archived INTEGER DEFAULT 0
);

-- messages: 消息内容 (核心数据表)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT,                    -- user / assistant / tool / system
    content TEXT,                 -- 消息内容
    tool_call_id TEXT,
    tool_calls TEXT,              -- JSON
    tool_name TEXT,
    timestamp TIMESTAMP,
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT,
    reasoning_content TEXT,
    platform_message_id TEXT,
    active INTEGER DEFAULT 1      -- ★ 软删除 (rewind 用)
);

-- state_meta: key-value 元数据
CREATE TABLE state_meta (key TEXT, value TEXT);

-- compression_locks: 压缩锁 (防并发)
CREATE TABLE compression_locks (
    session_id TEXT PRIMARY KEY,
    holder TEXT,
    acquired_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

#### 关键设计一: WAL 模式 + 写竞争处理

```python
# hermes_state.py
# ★ 不用 SQLite 内置 busy handler, 而是应用层重试
#    随机抖动 20-150ms, 最多 15 次重试
#    避免多个进程的 convoy 效应

_WRITE_MAX_RETRIES = 15
_RETRY_BASE_DELAY = 1.0  # 1 second
_RETRY_JITTER = (0.02, 0.15)  # 20-150ms random jitter

def _write_with_retry(self, sql, params):
    for attempt in range(_WRITE_MAX_RETRIES):
        try:
            with self._lock:
                cursor.execute(sql, params)
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                delay = _RETRY_BASE_DELAY + random.uniform(*_RETRY_JITTER)
                time.sleep(delay)
                continue
            raise
```

**为什么不用 SQLite 内置 busy handler？** 多进程并发（gateway + CLI + worktree agents）时，确定性的重试会导致 convoy 效应——所有进程同时重试、同时碰撞。随机抖动使竞争自然分散。

**WAL 模式自动降级**: 在 NFS/SMB 等网络文件系统上，WAL 模式的文件锁不可靠，自动回退到 DELETE 模式。

```python
_WAL_INCOMPAT_MARKERS = [
    "nfs", "smb", "cifs", "fuse",
    "docker", "overlay", "aufs",
]
```

**定期检查点**: 每 50 次写入触发一次 WAL TRUNCATE checkpoint，防止 WAL 文件无限增长。

#### 关键设计二: FTS5 双索引全文搜索

```python
# 1. unicode61 分词器 — 英文等空格分隔语言
FTS_SQL = """
CREATE VIRTUAL TABLE messages_fts
USING fts5(
    content, tool_name, tool_calls,
    content='messages', content_rowid='id',
    tokenize='unicode61'
)
"""

# 2. trigram 分词器 — 中/日/韩文 (substring 匹配)
FTS_TRIGRAM_SQL = """
CREATE VIRTUAL TABLE messages_fts_trigram
USING fts5(
    content, tool_name, tool_calls,
    content='messages', content_rowid='id',
    tokenize='trigram'
)
"""
```

**搜索时的自动路由**:

```python
def search_messages(self, query, ...):
    # 分析查询中 CJK 字符数量
    cjk_count = sum(1 for c in query if is_cjk(c))

    if cjk_count >= 3:
        # 使用 trigram 索引
        results = self._search_trigram(query)
    elif 1 <= cjk_count <= 2:
        # 回退到 LIKE 子串搜索 (trigram 对短序列精度不足)
        results = self._search_like(query)
    else:
        # 使用 unicode61 索引
        results = self._search_unicode61(query)

    # FTS5 snippet() 高亮: >>>...<<<
    return [
        {
            "snippet": snippet_text,  # 含 >>>...<<< 标记
            "context_before": prev_msg,
            "context_after": next_msg,
            "session_metadata": ...
        }
        for ... in results
    ]
```

**FTS5 可用性探测**:

```python
def _sqlite_supports_fts5(self):
    """尝试创建临时 FTS5 表检测"""
    try:
        self._execute("CREATE VIRTUAL TABLE _test_fts USING fts5(content)")
        self._execute("DROP TABLE _test_fts")
        return True
    except sqlite3.OperationalError:
        # 例如: no such module: fts5 (旧版 Python sqlite3)
        # 静默降级, FTS 触发器被跳过
        return False
```

#### 关键设计三: 声明式 Schema 演化

```python
def _reconcile_columns(self):
    """★ 声明式 schema 演化

    1. 用内存 SQLite 解析 SCHEMA_SQL 获取预期列
    2. 对比实际表的 PRAGMA table_info
    3. ALTER TABLE ADD COLUMN 任何缺失列

    不需要写迁移脚本, 加列后重启即可
    """
    expected = self._parse_columns_from_schema()
    actual = self._get_live_columns()

    for table, columns in expected.items():
        for col_name, col_def in columns.items():
            if col_name not in actual.get(table, {}):
                self._execute(
                    f"ALTER TABLE {table} ADD COLUMN {col_def}"
                )
```

数据迁移（行级回溯）仍然使用版本门控块（例如 v10 添加 trigram FTS5, v11 重建索引, v12 回填 `active=1`）。

#### 关键设计四: 压缩即分裂

上下文压缩的完整生命周期：

```python
# agent/conversation_compression.py
def compress_context(agent, messages, system_message):
    # 1. 获取压缩锁 (SQLite)
    #    防止父进程和 background_review fork 同时压缩
    lock = agent._session_db.try_acquire_compression_lock(
        session_id, holder="main", ttl=300
    )
    if not lock:
        return messages  # 锁被占用, 跳过本轮压缩

    try:
        # 2. 通知外部 provider: on_pre_compress()
        agent._memory_manager.on_pre_compress(messages)

        # 3. 调用 LLM 总结中间轮次
        summary = agent.context_compressor.compress(messages, system_message)

        # 4. ★ 新旧 session 分裂
        agent._session_db.end_session(old_id, "compression")

        new_id = generate_session_id()
        agent._session_db.create_session(
            id=new_id,
            parent_session_id=old_id,  # ★ 形成链式结构
            ...
        )

        # 5. 失效并重建系统提示词 → 重新加载记忆
        invalidate_system_prompt(agent)

        # 6. 重新注入 todo 清单
        todo_block = agent._todo_store.format_for_injection()
        if todo_block:
            compressed_messages.append({"role": "user", "content": todo_block})

        # 7. ★ 压缩头部声明: 记忆是权威的
        SUMMARY_PREFIX = """
        Your persistent memory (MEMORY.md, USER.md) in the system prompt is
        ALWAYS authoritative and active — never ignore or deprioritize
        memory content due to this compaction note.
        """

        # 8. 通知 provider: on_session_switch()
        agent._memory_manager.on_session_switch(new_id, reason="compression")

        # 9. 释放压缩锁
        return compressed_messages
    finally:
        agent._session_db.release_compression_lock(session_id, "main")
```

**压缩锁**防止两个 Agent（主进程 + background_review fork）同时触发压缩产生孤儿子会话：

```python
class SessionDB:
    def try_acquire_compression_lock(self, session_id, holder, ttl=300):
        # 原子操作: DELETE 过期行 + INSERT OR IGNORE
        with self._lock:
            self._execute("DELETE FROM compression_locks WHERE expires_at < ?", (now,))
            self._execute(
                """INSERT OR IGNORE INTO compression_locks
                   (session_id, holder, acquired_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, holder, now, now + ttl)
            )
            return self._cursor.rowcount > 0
```

**链式结构的数据流**:

```
会话演变:
  s1 (原始会话)
    → 压缩 → s2 (child of s1)
      → 再次压缩 → s3 (child of s2)

列表展示 (list_sessions_rich):
  使用递归 CTE 将链压缩为一条记录
  s1 → s3 (展示最新的活跃时间)

会话搜索 (search_messages):
  沿 parent_session_id 链回溯到根
  去重: 每个链根只保留第一个命中

Resume 操作 (resolve_resume_session_id):
  resume s1 → 自动重定向到 s3 (有最新消息的 descendant)
```

**链接口**: `parent_session_id` 链 + 递归 CTE 查询：

```python
def list_sessions_rich(self, ...):
    """使用递归 CTE 压缩链式感知排序"""
    query = """
    WITH RECURSIVE chain(id, root_id, depth) AS (
        SELECT id, id, 0 FROM sessions
        WHERE parent_session_id IS NULL
        UNION ALL
        SELECT s.id, c.root_id, c.depth + 1
        FROM sessions s
        JOIN chain c ON s.parent_session_id = c.id
    )
    SELECT * FROM chain
    """
```

### 5.2 检查点系统 (Checkpoint Manager)

**文件**: `tools/checkpoint_manager.py`

```python
class CheckpointManager:
    """★ 透明文件系统快照
    基于 Git 的单共享仓库:
      ~/.hermes/checkpoints/store/
    - 内容可寻址: Git object DB 跨项目去重
    - 项目隔离: refs/hermes/<hash16> + indexes/<hash16>
    - 元数据: projects/<hash16>.json
    """

    def ensure_checkpoint(self, working_dir, reason):
        """工具调用前拍摄快照"""
        if not self.enabled or self._already_snapped_this_turn:
            return
        self._take(working_dir, reason)

    def _take(self, working_dir):
        """差分提交:
        1. git add -A (用项目级 index)
        2. 丢弃超限文件 (> max_file_size_mb)
        3. 无变化则跳过
        4. write-tree + commit-tree + update-ref
        5. 裁剪超量快照 (max_snapshots)
        6. 强制执行全局大小限制 (max_total_size_mb)
        """
        ...

    def restore(self, working_dir, commit_hash, file_path=None):
        """恢复文件 / 目录 (含回滚前快照)"""
        ...

    def diff(self, working_dir, commit_hash):
        """显示 vs 检查点的差异"""
        ...
```

**Git 隔离**: 每个 git 命令运行在干净的配置环境中，防止用户 gitconfig（GPG 签名、credential helper）干扰：

```python
_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
```

**核心思想**: 检查点让 Agent 可以**安全地探索**——任何文件修改都可以回滚。这是"自主进化"的前提：敢于修改，也能恢复。

### 5.3 会话搜索工具 (Session Search Tool)

**文件**: `tools/session_search_tool.py`

一个工具四种调用模式（无显式 mode 参数，通过参数推导）：

```python
# 1. DISCOVERY: 传入 query
#    → FTS5 搜索 → 沿 parent 链去重 → 返回锚定窗口
session_search(query="如何在 Python 中处理异步？")

# 2. SCROLL: 传入 session_id + around_message_id
#    → 居中窗口 ±N 条消息 → 链内跳转
session_search(session_id="...", around_message_id=123)

# 3. READ: 仅传入 session_id
#    → 倾倒整个会话 (大会话: 前20 + 后10)
session_search(session_id="...")
#    → 也用于解析 @session:<profile>/<id> 链接

# 4. BROWSE: 无参数
#    → 返回最近会话列表
session_search()
```

**跨 Profile 支持**: 可以访问其他 Hermes profile 的 state.db（只读模式），用于解析跨会话引用。

---

## 六、整体数据流全景

### 写入链路 (记忆是如何保存的)

```
Agent 主动写入:
  模型调用 memory(action="add", target="memory", content="...")
    → tools/memory_tool.py: memory_tool()
      → MemoryStore.add()
        → 威胁检测 (tools/threat_patterns.py)
        → 文件锁获取 (fcntl/msvcrt)
        → 外部漂移检测 (disk vs memory 一致性)
        → 字符预算检查 (2200 / 1375 chars)
        → 去重检查
        → 追加到内存列表
        → 原子写入磁盘 (tempfile + os.replace)
        → MemoryManager.on_memory_write() 通知外部 provider

后台自动写入:
  每轮对话结束 → 达到 nudge 阈值
    → background_review.py: spawn_background_review_thread()
      → fork Agent 运行审查提示词
        → 如果需要, 调用 memory(action="add")
        → 写入共享的 MemoryStore

外部 provider 同步:
  turn_finalizer.py → MemoryManager.sync_all()
    → 后台线程, 调用 Provider.sync_turn()
```

### 读取链路 (记忆是如何被看到的)

```
系统提示词中的记忆 (冻结快照):
  会话初始化 / 压缩重建
    → system_prompt.py: build_system_prompt()
      → MemoryStore.format_for_system_prompt("memory")
        → 返回初始化时的冻结快照 (永不改变)
      → MemoryStore.format_for_system_prompt("user")
        → 同上

外部 Provider 召回 (每轮对话前):
  build_turn_context()
    → MemoryManager.prefetch_all(query)
      → 外部 Provider 返回相关片段
      → build_memory_context_block() 栅栏包裹
      → 注入到 API 调用 (不入库, 不被用户看到)

会话历史搜索:
  模型调用 session_search(query="...")
    → session_search_tool.py
    → SessionDB.search_messages()
      → FTS5 搜索 (英文 unicode61, 中文 trigram)
      → 沿 parent 链回溯去重
      → 返回带 snippet 的上下文窗口
```

### 压缩与记忆的交互

```
上下文超过 50% 阈值
  → conversation_compression.py: compress_context()
    1. 获取压缩锁 (SQLite, 防并发)
    2. 外部 provider: on_pre_compress()
    3. LLM 总结中间轮次
    4. 分裂 session (parent_session_id 链式结构)
    5. 失效系统提示词 → 重新加载 MEMORY.md/USER.md → 新快照
    6. 重新注入 todo 清单 (format_for_injection())
    7. 压缩头部声明: 记忆是权威的
    8. 通知 provider: on_session_switch()
```

### 背景审查的完整流程

```
每轮对话结束 (finalize_turn)
  → 检查 nudge 阈值:
    _turns_since_memory >= _memory_nudge_interval (10)?
    _iters_since_skill >= _skill_nudge_interval (10)?

  → 记忆同步:
    agent._sync_external_memory_for_turn()
      → MemoryManager.sync_all() [后台线程]
      → MemoryManager.queue_prefetch_all() [后台线程]

  → 如果达到阈值:
    agent._spawn_background_review()
      → background_review.py: spawn_background_review_thread()
        → 创建 fork Agent:
          - skip_memory=True
          - 共享 _memory_store
          - 工具白名单 [memory, skill_manage]
          - auto-deny callback
          - 继承缓存系统提示词
        → 运行审查对话
        → summarize_background_review_actions()
        → 输出: "Self-improvement review: ..."
```

---

## 七、核心思想总结

| 思想 | 代码体现 | 解决什么问题 |
|---|---|---|
| **冻结快照** | `MemoryStore._system_prompt_snapshot` — 初始化时冻结，会话内不变 | 保持 prompt caching 有效，降低延迟和成本 |
| **原子写入** | `tempfile + os.replace()` | 防止写入中途崩溃导致文件损坏 |
| **外部漂移检测** | `MemoryStore._detect_external_drift()` | 防止并发写入冲突（多会话、手动编辑） |
| **注入检测** | `_scan_memory_content()` + `[BLOCKED]` 占位符 | 防止通过记忆注入恶意提示词 |
| **上下文栅栏** | `<memory-context>` 标签 + `StreamingContextScrubber` 状态机 | 外部记忆辅助 LLM 但不污染会话历史 |
| **压缩即分裂** | `parent_session_id` 链 + `compress_context()` | 历史可检索、压缩不丢信息、链式可回溯 |
| **自我回顾** | `background_review.py` — fork Agent 后台自省 | Agent 主动决定该记什么，不依赖用户指令 |
| **非阻塞** | `ThreadPoolExecutor(1)` 后台同步 + daemon 线程审查 | 记忆操作不阻塞用户交互 |
| **中文化计数** | `prior_user_turns % interval` hydration | 跨重启保持 nudge 节奏 |
| **FTS5 双索引** | `unicode61` + `trigram` 分词器 | 同时支持英文和中日韩文搜索 |
| **写竞争退避** | 随机抖动 20-150ms, 最多 15 次重试 | 避免多进程 convoy 效应 |
| **声明式 Schema** | `_reconcile_columns()` — 自动 ADD COLUMN | 无需写迁移脚本，加列即用 |
| **安全检查点** | Git 裸仓库 + `GIT_CONFIG_*=/dev/null` | 安全探索、任意文件修改可回滚 |
| **工具白名单** | fork Agent 只允许 `memory` + `skill_manage` | 后台审查不产生副作用 |

---

## 八、关键文件索引

| 文件 | 核心职责 |
|---|---|
| `tools/memory_tool.py` | MemoryStore 实现 (MEMORY.md/USER.md 读写), memory 工具 |
| `agent/memory_manager.py` | MemoryManager 编排 (prefetch/sync/生命周期钩子) |
| `agent/memory_provider.py` | MemoryProvider ABC (外部记忆后端接口) |
| `agent/background_review.py` | 后台自我审查 (fork Agent 反思记忆) |
| `agent/conversation_compression.py` | 上下文压缩 (session 分裂 + 记忆重载) |
| `agent/context_compressor.py` | ContextCompressor (LLM 总结实现) |
| `agent/turn_context.py` | 每轮对话序章 (nudge 计数 + prefetch 触发) |
| `agent/turn_finalizer.py` | 每轮对话收尾 (记忆同步触发) |
| `agent/system_prompt.py` | 系统提示词组装 (记忆快照注入) |
| `agent/conversation_loop.py` | 主对话循环 (记忆集成点) |
| `hermes_state.py` | SessionDB (SQLite + FTS5 状态仓库) |
| `tools/session_search_tool.py` | 会话搜索工具 (FTS5 封装) |
| `tools/checkpoint_manager.py` | 文件系统检查点 (Git 快照) |
| `tools/todo_tool.py` | 待办清单 (工作记忆) |
| `tools/threat_patterns.py` | 威胁模式检测 (注入防护) |
| `agent/agent_init.py` | 记忆系统初始化参数设置 |
