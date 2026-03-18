# 第 03 节: 会话与上下文保护 - 工程化实现

> 会话就是 JSONL 文件。追加写入，读取时重放。过大时进行摘要压缩。

## 架构

```
    User Input
        |
        v
    SessionStore.load_session()  --> rebuild messages[] from JSONL
        |
        v
    ContextGuard.guard_api_call()
        |
        +-- Attempt 0: normal call
        |       |
        |   overflow? --no--> success
        |       |yes
        +-- Attempt 1: truncate oversized tool results
        |       |
        |   overflow? --no--> success
        |       |yes
        +-- Attempt 2: compact history via LLM summary
        |       |
        |   overflow? --yes--> raise
        |
    SessionStore.save_turn()  --> append to JSONL
        |
        v
    Print response

    File layout:
    workspace/.sessions/agents/{agent_id}/sessions/{session_id}.jsonl
    workspace/.sessions/agents/{agent_id}/sessions.json  (index)
```

## 工程化架构

教程中的单文件代码被拆分为模块化组件:

```
coder/components/
├── cli/                    # CLI 工具组件 (扩展)
│   └── __init__.py         # 新增 print_session, print_warn, print_context_bar
├── session/                # 会话组件 (新增)
│   ├── __init__.py         # 导出
│   ├── store.py            # SessionStore - JSONL 持久化
│   └── guard.py            # ContextGuard - 三阶段溢出保护
└── agent/                  # Agent 核心组件 (更新)
    ├── __init__.py
    └── loop.py             # AgentLoop 类 - 新增会话支持和 REPL 命令
```

## 核心文件说明

### 1. 配置扩展 (coder/settings.py)

添加了会话相关配置:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...

    # 会话配置 (s03)
    context_safe_limit: int = 180000  # 上下文安全限制 (tokens)
    session_workspace: str = "workspace/.sessions"  # 会话存储目录
```

### 2. CLI 组件扩展 (coder/components/cli/__init__.py)

新增会话相关输出函数:

| 函数 | 用途 |
|------|------|
| `print_warn(text)` | 打印警告文本（黄色） |
| `print_session(text)` | 打印会话相关文本（紫色） |
| `print_context_bar(estimated, max_tokens)` | 打印上下文使用进度条 |

新增颜色常量:

| 常量 | 用途 |
|------|------|
| `MAGENTA` | 紫色，用于会话相关输出 |
| `RED` | 红色，用于高使用率警告 |

### 3. 会话存储 (coder/components/session/store.py)

`SessionStore` 类实现 JSONL 持久化:

```python
class SessionStore:
    """管理 agent 会话的持久化存储。"""

    def __init__(self, agent_id: str = "default", workspace: Optional[Path] = None):
        """初始化会话存储"""

    def create_session(self, label: str = "") -> str:
        """创建新会话"""

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """从 JSONL 重建 API 格式的 messages[]"""

    def save_turn(self, role: str, content: Any) -> None:
        """保存一轮对话"""

    def save_tool_result(self, tool_use_id: str, name: str,
                         tool_input: Dict[str, Any], result: str) -> None:
        """保存工具调用和结果"""

    def list_sessions(self) -> List[Tuple[str, Dict[str, Any]]]:
        """列出所有会话，按最后活跃时间倒序"""

    def _rebuild_history(self, path: Path) -> List[Dict[str, Any]]:
        """从 JSONL 行重建 API 格式的消息列表"""
```

#### JSONL 记录类型

```python
{"type": "user", "content": "Hello", "ts": 1234567890}
{"type": "assistant", "content": [{"type": "text", "text": "Hi!"}], "ts": ...}
{"type": "tool_use", "tool_use_id": "toolu_...", "name": "read_file", "input": {...}, "ts": ...}
{"type": "tool_result", "tool_use_id": "toolu_...", "content": "file contents", "ts": ...}
```

#### _rebuild_history() 重建规则

`_rebuild_history()` 方法将扁平的 JSONL 记录转换回 API 兼容的 messages[]:

- 消息必须 user/assistant 交替
- tool_use 块属于 assistant 消息
- tool_result 块属于 user 消息（连续的 tool_result 合并到同一个 user 消息）

### 4. 上下文保护 (coder/components/session/guard.py)

`ContextGuard` 类实现三阶段溢出重试:

```python
class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    def __init__(self, max_tokens: Optional[int] = None):
        """初始化"""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算文本的 token 数量"""

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 数量"""

    def truncate_tool_result(self, result: str, max_fraction: float = 0.3) -> str:
        """在换行边界处只保留头部进行截断"""

    def compact_history(self, messages: List[Dict[str, Any]], ...) -> List[Dict[str, Any]]:
        """将前 50% 的消息压缩为 LLM 生成的摘要"""

    def guard_api_call(self, api_key: str, model: str, system: str,
                       messages: List[Dict[str, Any]], ...) -> Any:
        """三阶段重试: 正常调用 -> 截断工具结果 -> 压缩历史"""
```

#### 三阶段重试策略

```
Attempt 0: 正常调用
    |
    overflow?
    |yes
    v
Attempt 1: 截断过大的工具结果
    |
    overflow?
    |yes
    v
Attempt 2: 通过 LLM 摘要压缩历史 (50%)
    |
    overflow?
    |yes
    v
raise Exception
```

#### compact_history() 压缩策略

- 压缩前 50% 的消息
- 保留最后 N 条消息 (N = max(4, 总数的 20%)) 不变
- 将旧消息序列化为纯文本，让 LLM 生成摘要
- 用摘要 + "Understood" 对替换旧消息

### 5. Agent 循环更新 (coder/components/agent/loop.py)

核心改动:

```python
class AgentLoop:
    def __init__(self, ..., enable_session: bool = False, agent_id: str = "default"):
        """新增 enable_session 和 agent_id 参数"""

        # 会话存储和上下文保护 (s03)
        if self.enable_session:
            from coder.components.session import SessionStore, ContextGuard
            self._store = SessionStore(agent_id=self.agent_id)
            self._guard = ContextGuard()

    def _call_llm(self) -> Optional[ModelResponse]:
        """调用 LLM API（带上下文保护）"""
        if self._guard:
            return self._guard.guard_api_call(...)

    def _handle_repl_command(self, command: str) -> Tuple[bool, bool]:
        """处理以 / 开头的 REPL 命令"""

    def _init_session(self) -> None:
        """初始化会话：恢复最近的会话或创建新会话"""

    def run(self) -> None:
        """运行 Agent 循环"""
        if self.enable_session:
            self._init_session()
        # ... REPL 命令处理 ...
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/new [label]` | 创建新会话 |
| `/list` | 列出所有会话 |
| `/switch <id>` | 切换到指定会话（支持前缀匹配） |
| `/context` | 显示上下文 token 使用情况 |
| `/compact` | 手动压缩对话历史 |
| `/help` | 显示帮助信息 |
| `quit` / `exit` | 退出 REPL |

## 使用方法

### 1. 配置环境变量

```bash
# .env
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514
CONTEXT_SAFE_LIMIT=180000
SESSION_WORKSPACE=workspace/.sessions
```

### 2. 运行带会话持久化的 Agent

```python
from coder.components.agent import AgentLoop, run_agent_loop
from coder.components.tools import TOOLS

# 方式1: 快速启动（带工具和会话）
run_agent_loop(tools=TOOLS, enable_session=True)

# 方式2: 自定义配置
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    tools=TOOLS,
    enable_session=True,
    agent_id="my-project",
)
loop.run()

# 方式3: 不使用会话（与 s02 相同）
loop = AgentLoop(tools=TOOLS)
loop.run()
```

### 3. 直接使用会话组件

```python
from coder.components.session import SessionStore, ContextGuard

# 创建会话存储
store = SessionStore(agent_id="my-agent")
session_id = store.create_session("my-session")

# 保存对话
store.save_turn("user", "Hello")
store.save_turn("assistant", [{"type": "text", "text": "Hi!"}])

# 恢复会话
messages = store.load_session(session_id)

# 上下文保护
guard = ContextGuard()
response = guard.guard_api_call(
    api_key=api_key,
    model=model,
    system=system_prompt,
    messages=messages,
    tools=TOOLS,
)
```

## 文件布局

```
workspace/.sessions/
└── agents/
    └── {agent_id}/
        ├── sessions.json      # 会话索引
        └── sessions/
            ├── {session_id_1}.jsonl
            ├── {session_id_2}.jsonl
            └── ...
```

### sessions.json 索引格式

```json
{
  "abc123def456": {
    "label": "my-project",
    "created_at": "2024-01-15T10:30:00Z",
    "last_active": "2024-01-15T11:45:00Z",
    "message_count": 42
  }
}
```

## 与教程代码的对比

| 方面 | 教程 (s03_sessions.py) | 工程化实现 |
|------|------------------------|-----------|
| 会话存储 | 单文件内联 | 独立 store.py 模块 |
| 上下文保护 | 单文件内联 | 独立 guard.py 模块 |
| API 客户端 | Anthropic SDK | LiteLLM（兼容多模型） |
| 消息格式 | Anthropic 格式 | LiteLLM 通用格式 |
| REPL 命令 | 内联函数 | AgentLoop 方法 |
| 配置管理 | 直接读取环境变量 | Pydantic Settings |
| 工具调用 | Anthropic tool_use | LiteLLM tool_calls |

## 安全特性

### 1. Token 估算

```python
@staticmethod
def estimate_tokens(text: str) -> int:
    return len(text) // 4  # 简单启发式
```

### 2. 工具结果截断

```python
def truncate_tool_result(self, result: str, max_fraction: float = 0.3) -> str:
    """在换行边界处只保留头部"""
    max_chars = int(self.max_tokens * 4 * max_fraction)
    if len(result) <= max_chars:
        return result
    cut = result.rfind("\n", 0, max_chars)
    ...
```

### 3. 历史压缩

- 保留关键上下文
- 生成简洁摘要
- 自动失败回退

## 试一试

```bash
# 启动 Agent（需要配置 .env）
python -c "from coder.components.agent import run_agent_loop; from coder.components.tools import TOOLS; run_agent_loop(tools=TOOLS, enable_session=True)"

# 创建会话并在会话之间切换
# You > /new my-project
# You > 给我讲讲 Python 生成器
# You > /new experiments
# You > 2+2 等于多少?
# You > /switch my-p     (前缀匹配)

# 查看上下文使用情况
# You > /context
# Context usage: ~1,234 / 180,000 tokens
# [####--------------------------] 0.7%

# 上下文过大时手动压缩
# You > /compact
```

## 后续扩展

- **s04**: 添加多通道支持 (CLI/Telegram/飞书)
- **s05**: 添加 AgentManager 多 agent 支持
- **s06**: 扩展 `get_system_prompt()` 为 8 层组装
