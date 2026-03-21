"""
工具处理器实现

实现每个工具的具体逻辑，并提供分发函数。

安全特性:
    - safe_path(): 防止路径穿越攻击
    - truncate(): 限制输出长度，防止撑爆上下文
    - 危险命令过滤
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Union

from coder.cli import print_tool
from coder.intelligence.memory import MemoryStore
from coder.settings import settings


# 工具输出最大字符数 -- 防止超大输出撑爆上下文
MAX_TOOL_OUTPUT = getattr(settings, "max_tool_output", 50000)

# 工作目录 -- 所有文件操作相对于此目录，防止路径穿越
WORKDIR = Path.cwd() / "workspace"

# 记忆存储实例 (单例)
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """获取记忆存储单例实例。"""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore(workspace_dir=WORKDIR)
    return _memory_store


def set_memory_store(store: MemoryStore) -> None:
    """设置记忆存储单例实例（由 AgentLoop 注入）。"""
    global _memory_store
    _memory_store = store


# ---------------------------------------------------------------------------
# Todo 管理器 (s11)
# ---------------------------------------------------------------------------


class TodoManager:
    """
    管理 Todo 列表状态，提供验证和渲染功能。

    验证规则:
        - 最多 20 个条目
        - 每个条目必须有 id (str), text (非空), status (pending/in_progress/completed)
        - 只能有一个条目处于 in_progress 状态
    """

    def __init__(self, max_items: int = 20) -> None:
        """
        初始化 Todo 管理器。

        Args:
            max_items: 最大条目数，默认从配置读取
        """
        self.items: List[Dict[str, str]] = []
        self.max_items = max_items

    def update(self, items: List[Dict[str, Any]]) -> str:
        """
        更新 Todo 列表，带完整验证。

        Args:
            items: Todo 条目列表，每个条目包含 id, text, status

        Returns:
            渲染后的 Todo 列表字符串

        Raises:
            ValueError: 验证失败时抛出
        """
        # 验证: 最大条目数
        if len(items) > self.max_items:
            raise ValueError(f"Too many todo items (max {self.max_items}, got {len(items)})")

        # 验证: 每个条目的字段
        valid_statuses = {"pending", "in_progress", "completed"}
        in_progress_count = 0

        for item in items:
            # 检查必需字段
            if "id" not in item:
                raise ValueError("Todo item missing 'id' field")
            if "text" not in item:
                raise ValueError("Todo item missing 'text' field")
            if "status" not in item:
                raise ValueError("Todo item missing 'status' field")

            # 验证字段类型
            if not isinstance(item["id"], str):
                raise ValueError(f"Todo item 'id' must be string, got {type(item['id']).__name__}")
            if not isinstance(item["text"], str):
                raise ValueError(f"Todo item 'text' must be string, got {type(item['text']).__name__}")
            if not isinstance(item["status"], str):
                raise ValueError(f"Todo item 'status' must be string, got {type(item['status']).__name__}")

            # 验证 text 非空
            if not item["text"].strip():
                raise ValueError("Todo item 'text' cannot be empty")

            # 验证 status 值
            if item["status"] not in valid_statuses:
                raise ValueError(f"Invalid status '{item['status']}', must be one of: {valid_statuses}")

            # 统计 in_progress 数量
            if item["status"] == "in_progress":
                in_progress_count += 1

        # 验证: 只能有一个 in_progress
        if in_progress_count > 1:
            raise ValueError(f"Only one todo can be in_progress at a time (found {in_progress_count})")

        self.items = items
        return self.render()

    def render(self) -> str:
        """
        渲染 Todo 列表为格式化字符串。

        格式:
            [ ] #1: task name
            [>] #2: current task (in_progress)
            [x] #3: completed task
            (1/3 completed)
        """
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


# Todo 管理器实例 (单例)
_todo_manager: TodoManager | None = None


def get_todo_manager() -> TodoManager | None:
    """获取 Todo 管理器单例实例。"""
    global _todo_manager
    return _todo_manager


def set_todo_manager(manager: TodoManager) -> None:
    """设置 Todo 管理器单例实例（由 AgentLoop 注入）。"""
    global _todo_manager
    _todo_manager = manager


# ---------------------------------------------------------------------------
# 安全辅助函数
# ---------------------------------------------------------------------------


def safe_path(raw: str) -> Path:
    """
    将用户/模型传入的路径解析为安全的绝对路径。
    防止路径穿越: 最终路径必须在 WORKDIR 之下。
    """
    target = (WORKDIR / raw).resolve()
    if not str(target).startswith(str(WORKDIR)):
        raise ValueError(f"Path traversal blocked: {raw} resolves outside WORKDIR")
    return target


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """截断过长的输出，并附上提示。"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
# 每个工具函数接收关键字参数 (和 schema 中的 properties 对应),
# 返回字符串结果。错误通过返回 "Error: ..." 传递给模型。
# ---------------------------------------------------------------------------


def tool_bash(command: str, timeout: int = 30) -> str:
    """执行 shell 命令并返回输出。"""
    # 基础安全检查: 拒绝明显危险的命令
    dangerous = ["rm -rf /", "mkfs", "> /dev/sd", "dd if="]
    for pattern in dangerous:
        if pattern in command:
            return f"Error: Refused to run dangerous command containing '{pattern}'"

    print_tool("bash", command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKDIR),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_read_file(file_path: str) -> str:
    """读取文件内容。"""
    print_tool("read_file", file_path)
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        if not target.is_file():
            return f"Error: Not a file: {file_path}"
        content = target.read_text(encoding="utf-8")
        return truncate(content)
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_write_file(file_path: str, content: str) -> str:
    """写入内容到文件。父目录不存在时自动创建。"""
    print_tool("write_file", file_path)
    try:
        target = safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """
    精确替换文件中的文本。
    old_string 必须在文件中恰好出现一次，否则报错。
    """
    print_tool("edit_file", f"{file_path} (replace {len(old_string)} chars)")
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"

        content = target.read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            return "Error: old_string not found in file. Make sure it matches exactly."
        if count > 1:
            return f"Error: old_string found {count} times. It must be unique. Provide more surrounding context."

        new_content = content.replace(old_string, new_string, 1)
        target.write_text(new_content, encoding="utf-8")
        return f"Successfully edited {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_memory_write(content: str, category: str = "general") -> str:
    """保存重要信息到长期记忆。"""
    print_tool("memory_write", f"{len(content)} chars")
    try:
        store = get_memory_store()
        return store.write_memory(content, category=category)
    except Exception as exc:
        return f"Error: {exc}"


def tool_memory_search(query: str, top_k: int = 5) -> str:
    """搜索存储的记忆（使用混合搜索: TF-IDF + 向量 + 时间衰减 + MMR 重排序）。"""
    print_tool("memory_search", query)
    try:
        store = get_memory_store()
        results = store.hybrid_search(query, top_k=top_k)
        if not results:
            return f"No matches for '{query}'."
        lines = [f"[{r['path']}] (score: {r['score']})\n{r['snippet']}" for r in results]
        return "\n\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def tool_todo(items: List[Dict[str, Any]]) -> str:
    """更新任务列表，用于规划和跟踪多步骤任务的进度。"""
    print_tool("todo", f"{len(items)} items")
    try:
        manager = get_todo_manager()
        if manager is None:
            return "Error: Todo manager not initialized. Enable todo feature in settings."
        return manager.update(items)
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 工具调度表
# ---------------------------------------------------------------------------

TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "memory_write": tool_memory_write,
    "memory_search": tool_memory_search,
    "todo": tool_todo,
}


# ---------------------------------------------------------------------------
# 工具分发函数
# ---------------------------------------------------------------------------


def process_tool_call(tool_name: str, tool_input: Union[Dict[str, Any], str]) -> str:
    """
    根据工具名分发到对应的处理函数。
    错误作为字符串返回，这样模型可以看到错误并自行修正。
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"

    # 处理 tool_input 可能是字符串的情况 (某些 API 返回 JSON 字符串)
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError as exc:
            return f"Error: Failed to parse tool_input as JSON: {exc}"
        if not isinstance(tool_input, dict):
            return f"Error: tool_input must be a JSON object, got {type(tool_input).__name__}"

    try:
        return handler(**tool_input)
    except TypeError as exc:
        return f"Error: Invalid arguments for {tool_name}: {exc}"
    except Exception as exc:
        return f"Error: {tool_name} failed: {exc}"


__all__ = [
    "MAX_TOOL_OUTPUT",
    "WORKDIR",
    "get_memory_store",
    "set_memory_store",
    "TodoManager",
    "get_todo_manager",
    "set_todo_manager",
    "safe_path",
    "truncate",
    "tool_bash",
    "tool_read_file",
    "tool_write_file",
    "tool_edit_file",
    "tool_memory_write",
    "tool_memory_search",
    "tool_todo",
    "TOOL_HANDLERS",
    "process_tool_call",
]
