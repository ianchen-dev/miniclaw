# 第 02 节: 工具使用 - 工程化实现

> 工具 = 数据 (schema) + 处理函数映射表. 模型选一个名字, 你查表执行.

## 架构

```
    User Input
        |
        v
    messages[] --> LLM API (tools=TOOLS)
                       |
                  finish_reason?
                  /          \
            "stop"       "tool_calls"
               |              |
             Print    for each tool_call:
                        TOOL_HANDLERS[name](**input)
                              |
                        tool_result
                              |
                        messages[] <-- {role:"tool", content: result}
                              |
                        back to LLM --> may chain more tools
                                          or "stop" --> Print
```

外层 `while True` 与第 01 节完全相同. 唯一的新增是一个**内层** while 循环,
在 `finish_reason == "tool_calls"` 时持续调用 LLM.

## 工程化架构

教程中的单文件代码被拆分为模块化组件:

```
coder/components/
├── cli/                    # CLI 工具组件 (扩展)
│   └── __init__.py         # 新增 print_tool() 函数
├── tools/                  # 工具组件 (新增)
│   ├── __init__.py         # 导出
│   ├── schema.py           # TOOLS schema 定义
│   └── handlers.py         # 工具处理器 + 分发函数
└── agent/                  # Agent 核心组件 (更新)
    ├── __init__.py
    └── loop.py             # AgentLoop 类 - 新增工具支持
```

## 核心文件说明

### 1. 配置扩展 (coder/settings.py)

添加了工具相关配置:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...

    # 工具配置 (s02)
    max_tool_output: int = 50000  # 工具输出最大字符数
```

### 2. CLI 组件扩展 (coder/components/cli/**init**.py)

新增工具调用输出函数:

| 函数 | 用途 |
|------|------|
| `print_tool(name, detail)` | 打印工具调用信息 |
| `print_banner(title, model, extra_info)` | 扩展支持额外信息行 |

### 3. 工具 Schema (coder/components/tools/schema.py)

定义 Agent 可用的工具 schema:

```python
TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command...",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", ...},
                "timeout": {"type": "integer", ...},
            },
            "required": ["command"],
        },
    },
    # ... read_file, write_file, edit_file
]
```

### 4. 工具处理器 (coder/components/tools/handlers.py)

包含工具实现和分发逻辑:

```python
# 安全辅助函数
def safe_path(raw: str) -> Path:
    """防止路径穿越"""

def truncate(text: str, limit: int) -> str:
    """截断过长输出"""

# 工具实现
def tool_bash(command: str, timeout: int = 30) -> str: ...
def tool_read_file(file_path: str) -> str: ...
def tool_write_file(file_path: str, content: str) -> str: ...
def tool_edit_file(file_path: str, old_string: str, new_string: str) -> str: ...

# 调度表
TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
}

# 分发函数
def process_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """字典查找 + **kwargs 分发"""
```

### 5. Agent 循环更新 (coder/components/agent/loop.py)

核心改动:

```python
class AgentLoop:
    def __init__(self, ..., tools: Optional[List[Dict[str, Any]]] = None):
        self.tools = tools
        # 如果启用工具，扩展系统提示词
        if self.tools:
            self.system_prompt = f"{TOOL_SYSTEM_PROMPT_EXTENSION}\n\n{base_prompt}"

    def _call_llm(self) -> Optional[ModelResponse]:
        kwargs = {...}
        if self.tools:
            kwargs["tools"] = self.tools  # 传入工具 schema
        return litellm.completion(**kwargs)

    def _handle_tool_calls(self, assistant_message: Any) -> bool:
        """处理工具调用，返回 False 表示继续内层循环"""
        # 1. 添加助手消息（包含 tool_calls）
        # 2. 执行每个工具调用
        # 3. 将工具结果添加到历史
        return False  # 继续内层循环

    def run(self) -> None:
        while True:
            # 获取用户输入
            user_input = self._get_user_input()
            self.messages.append({"role": "user", "content": user_input})

            # 内层循环：处理工具调用
            while True:
                response = self._call_llm()
                should_break = self._process_response(response)
                if should_break:
                    break
```

## 使用方法

### 1. 配置环境变量

```bash
# .env
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514
MAX_TOOL_OUTPUT=50000
```

### 2. 运行带工具的 Agent

```python
from coder.components.agent import AgentLoop, run_agent_loop
from coder.components.tools import TOOLS

# 方式1: 快速启动
run_agent_loop(tools=TOOLS)

# 方式2: 自定义配置
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    tools=TOOLS,
)
loop.run()

# 方式3: 不使用工具（与 s01 相同）
loop = AgentLoop()
loop.run()
```

### 3. 添加新工具

添加新工具只需两步:

```python
# 1. 在 schema.py 中添加 schema
TOOLS.append({
    "name": "my_tool",
    "description": "My custom tool",
    "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...],
    },
})

# 2. 在 handlers.py 中添加处理器
def tool_my_tool(**kwargs) -> str:
    """我的自定义工具"""
    return "result"

TOOL_HANDLERS["my_tool"] = tool_my_tool
```

循环本身不需要任何改动。

## 工具清单

| 工具名 | 功能 | 安全特性 |
|--------|------|----------|
| `bash` | 执行 shell 命令 | 危险命令过滤 |
| `read_file` | 读取文件内容 | 路径穿越保护 |
| `write_file` | 写入文件 | 路径穿越保护 |
| `edit_file` | 精确替换文本 | 唯一性检查 |

## 安全特性

### 1. 路径穿越保护

```python
def safe_path(raw: str) -> Path:
    target = (WORKDIR / raw).resolve()
    if not str(target).startswith(str(WORKDIR)):
        raise ValueError(f"Path traversal blocked: {raw}")
    return target
```

### 2. 输出截断

```python
def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"
```

### 3. 危险命令过滤

```python
dangerous = ["rm -rf /", "mkfs", "> /dev/sd", "dd if="]
for pattern in dangerous:
    if pattern in command:
        return f"Error: Refused to run dangerous command"
```

## 与教程代码的对比

| 方面 | 教程 (s02_tool_use.py) | 工程化实现 |
|------|------------------------|-----------|
| 工具定义 | 单文件内联 | 独立 schema.py 模块 |
| 工具处理器 | 单文件内联 | 独立 handlers.py 模块 |
| 分发函数 | 内联 | 独立函数，可复用 |
| Agent 循环 | 函数式 | AgentLoop 类方法 |
| 配置管理 | 直接读取环境变量 | Pydantic Settings |
| 安全函数 | 内联 | 独立，可测试 |
| 错误处理 | 返回字符串 | 同上，模块化 |

## 试一试

```bash
# 启动 Agent（需要配置 .env）
python -c "from coder.components.agent import run_agent_loop; from coder.components.tools import TOOLS; run_agent_loop(tools=TOOLS)"

# 让它执行命令
# You > 当前目录下有哪些文件?

# 让它读取文件
# You > 读取 README.md 的内容

# 让它创建和编辑文件
# You > 创建一个名为 hello.txt 的文件, 内容是 "Hello World"
# You > 把 hello.txt 中的 "World" 改成 "Miniclaw"

# 观察它链式调用工具 (读取 -> 编辑 -> 验证)
# You > 在 hello.txt 顶部添加一行注释
```

## 后续扩展

- **s03**: 添加 `SessionStore` 持久化 `messages`，`ContextGuard` 上下文保护
- **s04**: 扩展为多通道支持
- **s06**: 扩展 `get_system_prompt()` 为 8 层组装
