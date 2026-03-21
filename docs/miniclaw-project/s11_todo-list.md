# s11: Todo-List 功能实现教程

> *"没有计划的 agent 走哪算哪"* -- 先列步骤再动手，完成率翻倍。

## 目录

1. [问题背景](#问题背景)
2. [解决方案概述](#解决方案概述)
3. [架构设计](#架构设计)
4. [实现步骤](#实现步骤)
5. [核心代码解析](#核心代码解析)
6. [测试与验证](#测试与验证)
7. [使用示例](#使用示例)

---

## 问题背景

在多步任务中，大型语言模型（LLM）会面临以下问题：

- **进度丢失**：模型忘记已完成哪些步骤
- **任务漂移**：Agent 偏离原始计划
- **执行不完整**：跳过某些步骤或重复执行
- **上下文稀释**：长对话中，计划逐渐被挤出注意力范围

一个 10 步重构任务可能只完成 1-3 步就开始即兴发挥，因为后续步骤已经被工具结果和其他对话挤出注意力窗口。

---

## 解决方案概述

```
用户输入 → Agent Loop → LLM → stop_reason?
                              ↓
              "stop"       "tool_calls"
                 ↓              ↓
             响应输出      执行工具
                                  ↓
                           ┌──────┴──────┐
                           │  + todo 工具 │
                           └──────┬──────┘
                                  ↓
                      TodoManager.update()
                                  ↓
                        渲染 todo 列表
                                  ↓
                  追踪使用情况 (nag 计数器)
```

### 核心机制

1. **TodoManager**：存储带状态的待办事项，强制同一时间只能有一个 `in_progress`
2. **todo 工具**：像其他工具一样加入调度表
3. **nag reminder**：模型连续 3 轮以上不调用 `todo` 时注入提醒

---

## 架构设计

### 组件关系图

```
┌─────────────────────────────────────────────────────────┐
│                    AgentLoop (s01)                      │
│  ┌───────────────────────────────────────────────────┐ │
│  │   _rounds_since_todo: int = 0                     │ │
│  │   _todo_manager: TodoManager                      │ │
│  └───────────────────────────────────────────────────┘ │
│                         │                               │
│                         │ 注入                          │
│                         ↓                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │         _handle_tool_calls()                      │ │
│  │   - 检测 todo 工具使用                             │ │
│  │   - 更新计数器                                     │ │
│  │   - 注入 nag 提醒                                  │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          │ 调用
                          ↓
┌─────────────────────────────────────────────────────────┐
│              coder/tools/handlers.py (s02)              │
│  ┌───────────────────────────────────────────────────┐ │
│  │   TodoManager                                     │ │
│  │   - update(items: List[Dict]) -> str             │ │
│  │   - render() -> str                               │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────┐ │
│  │   tool_todo(items: List[Dict]) -> str             │ │
│  │   TOOL_HANDLERS["todo"] = tool_todo               │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          │ 定义
                          ↓
┌─────────────────────────────────────────────────────────┐
│              coder/tools/schema.py (s02)                │
│  ┌───────────────────────────────────────────────────┐ │
│  │   TODO_TOOLS: List[Dict[str, Any]]                │ │
│  │   - 工具名称: "todo"                               │ │
│  │   - 参数: items (array)                           │ │
│  │   - 状态: pending/in_progress/completed           │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          │ 配置
                          ↓
┌─────────────────────────────────────────────────────────┐
│                coder/settings.py                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │   todo_enabled: bool = True                       │ │
│  │   todo_nag_threshold: int = 3                     │ │
│  │   todo_max_items: int = 20                       │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 实现步骤

### 步骤 1: 实现 TodoManager 类

**文件**: `coder/tools/handlers.py`

```python
class TodoManager:
    """
    管理 Todo 列表状态，提供验证和渲染功能。

    验证规则:
        - 最多 20 个条目
        - 每个条目必须有 id (str), text (非空), status (pending/in_progress/completed)
        - 只能有一个条目处于 in_progress 状态
    """

    def __init__(self, max_items: int = 20) -> None:
        self.items: List[Dict[str, str]] = []
        self.max_items = max_items

    def update(self, items: List[Dict[str, Any]]) -> str:
        """更新 Todo 列表，带完整验证"""
        # 验证: 最大条目数
        if len(items) > self.max_items:
            raise ValueError(f"Too many todo items (max {self.max_items}, got {len(items)})")

        # 验证: 每个条目的字段
        valid_statuses = {"pending", "in_progress", "completed"}
        in_progress_count = 0

        for item in items:
            # 检查必需字段
            if "id" not in item or "text" not in item or "status" not in item:
                raise ValueError("Todo item missing required field")

            # 验证 text 非空
            if not item["text"].strip():
                raise ValueError("Todo item 'text' cannot be empty")

            # 验证 status 值
            if item["status"] not in valid_statuses:
                raise ValueError(f"Invalid status '{item['status']}'")

            # 统计 in_progress 数量
            if item["status"] == "in_progress":
                in_progress_count += 1

        # 验证: 只能有一个 in_progress
        if in_progress_count > 1:
            raise ValueError("Only one todo can be in_progress at a time")

        self.items = items
        return self.render()

    def render(self) -> str:
        """渲染 Todo 列表为格式化字符串"""
        if not self.items:
            return "No todos."

        lines = []
        completed_count = 0

        for item in self.items:
            status = item["status"]
            item_id = item["id"]
            text = item["text"]

            if status == "pending":
                marker = "[ ]"
            elif status == "in_progress":
                marker = "[>]"
            else:  # completed
                marker = "[x]"
                completed_count += 1

            lines.append(f"{marker} #{item_id}: {text}")

        lines.append(f"({completed_count}/{len(self.items)} completed)")
        return "\n".join(lines)
```

### 步骤 2: 添加 todo 工具处理器

**文件**: `coder/tools/handlers.py`

```python
# Todo 管理器实例 (单例)
_todo_manager: TodoManager | None = None

def get_todo_manager() -> TodoManager | None:
    """获取 Todo 管理器单例实例"""
    global _todo_manager
    return _todo_manager

def set_todo_manager(manager: TodoManager) -> None:
    """设置 Todo 管理器单例实例（由 AgentLoop 注入）"""
    global _todo_manager
    _todo_manager = manager

def tool_todo(items: List[Dict[str, Any]]) -> str:
    """更新任务列表，用于规划和跟踪多步骤任务的进度"""
    print_tool("todo", f"{len(items)} items")
    try:
        manager = get_todo_manager()
        if manager is None:
            return "Error: Todo manager not initialized"
        return manager.update(items)
    except Exception as exc:
        return f"Error: {exc}"

# 添加到 TOOL_HANDLERS
TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    # ... 其他工具 ...
    "todo": tool_todo,
}
```

### 步骤 3: 定义 todo 工具 schema

**文件**: `coder/tools/schema.py`

```python
# Todo 工具 (s11)
TODO_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": (
                "Update your task list. Use this to plan and track progress "
                "on multi-step tasks. Only one task can be in_progress at a time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                            },
                            "required": ["id", "text", "status"],
                        }
                    }
                },
                "required": ["items"],
            },
        },
    },
]

# 更新完整工具列表
TOOLS: List[Dict[str, Any]] = BASE_TOOLS + MEMORY_TOOLS + TODO_TOOLS
```

### 步骤 4: 集成到 Agent Loop

**文件**: `coder/agent/loop.py`

```python
class AgentLoop:
    def __init__(self, ...):
        # ... 其他初始化 ...

        # Todo 组件 (s11)
        self._rounds_since_todo = 0
        self._todo_manager = None

        # 初始化 Todo 管理器
        if getattr(settings, "todo_enabled", True):
            from coder.tools import TodoManager, set_todo_manager

            max_items = getattr(settings, "todo_max_items", 20)
            self._todo_manager = TodoManager(max_items=max_items)
            set_todo_manager(self._todo_manager)

    def _handle_tool_calls(self, assistant_message: Any) -> bool:
        """处理工具调用，包含 nag 提醒逻辑"""
        self.messages.append(self._build_assistant_message(assistant_message))

        tool_results = []

        # 检测是否使用了 todo 工具 (s11)
        used_todo = False
        for tool_call in assistant_message.tool_calls or []:
            if tool_call.function.name == "todo":
                used_todo = True
                break

        # 更新计数器
        if used_todo:
            self._rounds_since_todo = 0
        else:
            self._rounds_since_todo += 1

        # 注入 nag 提醒 (s11)
        nag_threshold = getattr(settings, "todo_nag_threshold", 3)
        if self._rounds_since_todo >= nag_threshold:
            reminder = {
                "role": "user",
                "content": "<reminder>Update your todos. Use the todo tool to track your progress.</reminder>",
            }
            tool_results.insert(0, reminder)

        # ... 执行其他工具调用 ...
```

### 步骤 5: 添加 /todo CLI 命令

**文件**: `coder/agent/loop.py`

```python
def _handle_todo_command(self, command: str) -> Tuple[bool, bool]:
    """处理 Todo 相关的 REPL 命令 (s11)"""
    cmd, arg = self._parse_command(command)

    if cmd == "/todo":
        print_info("--- Current Todos ---")
        if self._todo_manager:
            print(self._todo_manager.render())
        else:
            print_info("  (Todo manager not initialized)")
        return True, True

    return False, True

# 在 _handle_repl_command 中调用
def _handle_repl_command(self, command: str) -> Tuple[bool, bool]:
    # ... 其他命令处理 ...

    # 先尝试 Todo 命令 (s11)
    handled, should_continue = self._handle_todo_command(command)
    if handled:
        return handled, should_continue

    # ... 其他命令处理 ...
```

### 步骤 6: 添加配置选项

**文件**: `coder/settings.py`

```python
class Settings(BaseSettings):
    # ... 其他配置 ...

    # Todo 配置 (s11)
    todo_enabled: bool = True           # 是否启用 todo 工具
    todo_nag_threshold: int = 3         # 多少轮不使用 todo 后显示提醒
    todo_max_items: int = 20            # 最大 todo 条目数
```

---

## 核心代码解析

### 1. TodoManager 验证逻辑

```python
# 验证规则
- 最多 20 个条目: if len(items) > self.max_items
- 每个条目必须有 id, text, status: 检查字段存在性
- text 必须非空: if not item["text"].strip()
- status 必须是有效值: if item["status"] not in valid_statuses
- 只能有一个 in_progress: if in_progress_count > 1
```

**设计决策**：
- **单一 in_progress**：强制顺序聚焦，防止多任务反模式
- **最大 20 条目**：防止上下文膨胀
- **简单验证**：快速、可预测的行为

### 2. Nag Reminder 机制

```python
# 在 _handle_tool_calls 中
used_todo = any(tc.function.name == "todo" for tc in assistant_message.tool_calls)

if used_todo:
    self._rounds_since_todo = 0  # 重置计数器
else:
    self._rounds_since_todo += 1  # 增加计数

# 注入提醒
if self._rounds_since_todo >= nag_threshold:
    reminder = {
        "role": "user",
        "content": "<reminder>Update your todos...</reminder>"
    }
    tool_results.insert(0, reminder)
```

**工作原理**：
- 每次工具调用后检查是否使用了 `todo`
- 如果 3 轮（默认阈值）未使用，注入提醒消息
- 提醒作为用户消息插入，确保模型注意到

### 3. 单例模式设计

```python
# 模块级单例变量
_todo_manager: TodoManager | None = None

def get_todo_manager() -> TodoManager | None:
    """获取单例实例"""
    global _todo_manager
    return _todo_manager

def set_todo_manager(manager: TodoManager) -> None:
    """设置单例实例（由 AgentLoop 注入）"""
    global _todo_manager
    _todo_manager = manager
```

**黑盒解耦**：`tool_todo` 通过 `get_todo_manager()` 获取实例，不直接依赖 `AgentLoop`，符合依赖注入原则。

---

## 测试与验证

### 单元测试结构

```python
class TestTodoManagerValidation:
    """测试 TodoManager 验证逻辑"""

    def test_todo_manager_max_items(self):
        """验证: 最多 20 个条目"""
        manager = TodoManager(max_items=20)
        items = [{"id": str(i), "text": f"Task {i}", "status": "pending"}
                 for i in range(20)]
        result = manager.update(items)
        assert "(0/20 completed)" in result

        # 21 个条目应该失败
        items.append({"id": "21", "text": "Task 21", "status": "pending"})
        with pytest.raises(ValueError, match="Too many todo items"):
            manager.update(items)

    def test_todo_manager_single_in_progress(self):
        """验证: 只能有一个 in_progress"""
        manager = TodoManager()
        items = [
            {"id": "1", "text": "Task 1", "status": "in_progress"},
            {"id": "2", "text": "Task 2", "status": "pending"},
        ]
        result = manager.update(items)
        assert "[>]" in result
        assert "[ ]" in result

        # 两个 in_progress 应该失败
        items[1]["status"] = "in_progress"
        with pytest.raises(ValueError, match="Only one todo can be in_progress"):
            manager.update(items)
```

### 运行测试

```bash
# 运行 todo 相关测试
uv run pytest tests/tools/test_todo.py -v

# 运行所有测试
uv run pytest
```

---

## 使用示例

### 示例 1: 代码重构任务

**用户输入**:
```
Refactor the file hello.py: add type hints, docstrings, and a main guard
```

**Agent 行为**:
```
Round 1: Agent 调用 todo 工具创建计划
  → todo([{"id": "1", "text": "add type hints", "status": "pending"},
          {"id": "2", "text": "add docstrings", "status": "pending"},
          {"id": "3", "text": "add main guard", "status": "pending"}])
  → _rounds_since_todo = 0

Round 2: Agent 将第一个任务设为进行中
  → todo([{"id": "1", "text": "add type hints", "status": "in_progress"},
          {"id": "2", "text": "add docstrings", "status": "pending"},
          {"id": "3", "text": "add main guard", "status": "pending"}])
  → _rounds_since_todo = 0

Round 3: Agent 执行编辑
  → edit_file(...)
  → _rounds_since_todo = 1

Round 4: Agent 完成第一个任务，开始第二个
  → todo([{"id": "1", "text": "add type hints", "status": "completed"},
          {"id": "2", "text": "add docstrings", "status": "in_progress"},
          {"id": "3", "text": "add main guard", "status": "pending"}])
  → _rounds_since_todo = 0
```

### 示例 2: Nag Reminder 触发

```
Round 1: Agent 直接编辑文件，未调用 todo
  → _rounds_since_todo = 1

Round 2: Agent 继续编辑
  → _rounds_since_todo = 2

Round 3: Agent 继续编辑
  → _rounds_since_todo = 3
  → 注入提醒: "<reminder>Update your todos. Use the todo tool to track your progress.</reminder>"
```

### 示例 3: 使用 /todo 命令查看状态

```
User: /todo

Output:
--- Current Todos ---
[x] #1: add type hints
[>] #2: add docstrings
[ ] #3: add main guard
(1/3 completed)
```

---

## 数据流对比

### 正常流程（使用 todo）

```
Round 1: 用户请求重构
  → LLM 调用 todo 创建计划
  → _rounds_since_todo = 0

Round 2: LLM 更新 todo 状态
  → _rounds_since_todo = 0

Round 3: LLM 执行工具
  → _rounds_since_todo = 1

Round 4: LLM 更新 todo 状态
  → _rounds_since_todo = 0 (重置!)
```

### Nag 流程（不使用 todo）

```
Round 1: 用户请求重构
  → LLM 直接执行工具
  → _rounds_since_todo = 1

Round 2: LLM 继续执行
  → _rounds_since_todo = 2

Round 3: LLM 继续执行
  → _rounds_since_todo = 3
  → 注入 <reminder>Update your todos...</reminder>
```

---

## 相对 s02 的变更

| 组件           | 之前 (s02)       | 之后 (s11)                     |
|----------------|------------------|--------------------------------|
| 工具数量       | 4                | 5 (+todo)                      |
| 规划能力       | 无               | 带状态的 TodoManager           |
| Nag 注入       | 无               | 3 轮后注入 `<reminder>`        |
| Agent loop     | 简单分发         | + `_rounds_since_todo` 计数器  |
| 配置项         | 基础配置         | + `todo_enabled` 等 3 项配置   |

---

## 设计权衡

### 简单性 vs 持久化
- **选择**: 仅内存存储
- **理由**: 每对话状态足够；持久化增加复杂度，当前场景无明确收益

### 严格性 vs 灵活性
- **选择**: 单一 `in_progress` 强制执行
- **理由**: 防止多任务反模式；强制顺序聚焦提高完成率

### Nag 阈值
- **选择**: 3 轮默认值
- **理由**: 平衡提醒频率而不烦人；可通过配置调整

---

## 环境变量配置

在 `.env` 文件中添加：

```bash
# Todo 配置 (s11)
TODO_ENABLED=true
TODO_NAG_THRESHOLD=3
TODO_MAX_ITEMS=20
```

---

## 总结

Todo-List 功能通过以下机制解决多步任务跟踪问题：

1. **可见性**: Agent 的计划对用户可见且可追踪
2. **顺序聚焦**: 强制单一 `in_progress` 状态
3. **问责机制**: Nag reminder 制造更新压力
4. **减少完成时间**: 通过更好的规划减少任务完成时间

整个实现遵循 Miniclaw 的设计哲学：轻量级、已验证的模式、约 100 行核心代码。

---

## 参考资源

- 原始提案: `openspec/changes/archive/2026-03-21-add-todo-tool/`
- 设计文档: `openspec/changes/archive/2026-03-21-add-todo-tool/design.md`
- 任务清单: `openspec/changes/archive/2026-03-21-add-todo-tool/tasks.md`
- 参考实现: `docs/not-committed/plan/todolist/referance/s11-todo-write.md`
