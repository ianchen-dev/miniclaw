# 第 01 节: Agent 循环 - 工程化实现

> Agent 就是 `while True` + `stop_reason`.

## 架构

```
    User Input
        |
        v
    messages[] <-- append {role: "user", ...}
        |
        v
    LLM API (litellm.completion)
        |
        v
    finish_reason?
      /         \
   "stop"     "tool_calls"
     |            |
   Print       (第 02 节)
     |
     v
    messages[] <-- append {role: "assistant", ...}
     |
     +--- 回到循环, 等待下一次输入
```

## 工程化架构

教程中的单文件代码被拆分为模块化组件:

```
coder/components/
├── cli/                    # CLI 工具组件
│   └── __init__.py         # 颜色输出、输入提示
├── prompts/                # 提示词组件
│   └── __init__.py         # 系统提示词管理
└── agent/                  # Agent 核心组件
    ├── __init__.py         # 导出
    └── loop.py             # AgentLoop 类实现
```

## 核心文件说明

### 1. 配置扩展 (coder/settings.py)

添加了 Agent 相关配置:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...

    # Agent 配置 (s01)
    api_key: Optional[str] = None
    model_id: str = "claude-sonnet-4-20250514"
    api_base_url: Optional[str] = None
    max_tokens: int = 8096
```

### 2. CLI 组件 (coder/components/cli/__init__.py)

提供终端交互工具:

| 函数 | 用途 |
|------|------|
| `colored_user()` | 返回带颜色的用户输入提示符 |
| `print_assistant(text)` | 打印助手回复 |
| `print_info(text)` | 打印灰色信息文本 |
| `print_error(text)` | 打印错误文本 |
| `print_banner(title, model)` | 打印启动横幅 |
| `print_goodbye()` | 打印再见消息 |

### 3. 提示词组件 (coder/components/prompts/__init__.py)

管理系统提示词:

```python
DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant..."

def get_system_prompt() -> str:
    """获取系统提示词"""
    return DEFAULT_SYSTEM_PROMPT
```

> 后续章节将扩展为 8 层动态组装。

### 4. Agent 循环 (coder/components/agent/loop.py)

核心 `AgentLoop` 类:

```python
class AgentLoop:
    """Agent 循环类"""

    def __init__(self, model_id=None, api_key=None, ...):
        """初始化，支持参数覆盖配置"""

    def run(self) -> None:
        """运行主循环"""

    # 内部方法
    def _get_user_input(self) -> Optional[str]
    def _call_llm(self) -> Optional[ModelResponse]
    def _process_response(self, response) -> None
    def _handle_stop(self, assistant_message) -> None
    def _handle_tool_calls(self, assistant_message) -> None  # 预留
```

## 使用方法

### 1. 配置环境变量

```bash
# .env
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514
API_BASE_URL=  # 可选，用于自定义端点
```

### 2. 运行 Agent 循环

```python
from coder.components.agent import AgentLoop

# 使用默认配置
loop = AgentLoop()
loop.run()

# 或自定义配置
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    system_prompt="You are a code reviewer."
)
loop.run()
```

### 3. 便捷函数

```python
from coder.components.agent import run_agent_loop

run_agent_loop()  # 快速启动
```

## 设计决策

### 为什么使用类而不是函数?

1. **状态封装**: `messages[]` 作为实例属性，便于扩展（如会话持久化）
2. **配置注入**: 支持运行时覆盖配置，便于测试
3. **方法分离**: 每个处理逻辑独立，便于扩展（如 s02 添加工具支持）

### finish_reason 对照表

| finish_reason | 含义 | 动作 |
|---------------|------|------|
| `"stop"` | 模型完成了回复 | 打印, 继续循环 |
| `"tool_calls"` | 模型想调用工具 | 执行, 反馈结果 (s02) |
| `"length"` | 回复被 token 限制截断 | 打印部分文本 |

## 与教程代码的对比

| 方面 | 教程 (s01_agent_loop.py) | 工程化实现 |
|------|-------------------------|-----------|
| 循环位置 | 单文件函数 | `AgentLoop` 类 |
| 消息存储 | 函数内局部变量 | 实例属性 |
| 配置管理 | 直接读取环境变量 | Pydantic Settings |
| CLI 工具 | 内联定义 | 独立组件 |
| 系统提示词 | 硬编码字符串 | 独立组件，支持扩展 |
| 错误处理 | 弹出消息，继续 | 同上，方法分离 |

## 后续扩展

- **s02**: 在 `_handle_tool_calls()` 中实现工具执行
- **s03**: 添加 `SessionStore` 持久化 `messages`
- **s06**: 扩展 `get_system_prompt()` 为 8 层组装
