"""
工具处理器实现

实现每个工具的具体逻辑，并提供分发函数。

安全特性:
    - safe_path(): 防止路径穿越攻击
    - truncate(): 限制输出长度，防止撑爆上下文
    - 危险命令过滤
"""

import subprocess
from pathlib import Path
from typing import Any, Callable, Dict

from coder.cli import print_tool
from coder.settings import settings


# 工具输出最大字符数 -- 防止超大输出撑爆上下文
MAX_TOOL_OUTPUT = getattr(settings, "max_tool_output", 50000)

# 工作目录 -- 所有文件操作相对于此目录，防止路径穿越
WORKDIR = Path.cwd()


# ---------------------------------------------------------------------------
# 安全辅助函数
# ---------------------------------------------------------------------------


def safe_path(raw: str) -> Path:
    """
    将用户/模型传入的路径解析为安全的绝对路径。
    防止路径穿越: 最终路径必须在 WORKDIR 之下。

    Args:
        raw: 原始路径字符串

    Returns:
        解析后的安全 Path 对象

    Raises:
        ValueError: 如果路径尝试穿越到 WORKDIR 之外
    """
    target = (WORKDIR / raw).resolve()
    if not str(target).startswith(str(WORKDIR)):
        raise ValueError(f"Path traversal blocked: {raw} resolves outside WORKDIR")
    return target


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """
    截断过长的输出，并附上提示。

    Args:
        text: 原始文本
        limit: 最大字符数

    Returns:
        截断后的文本
    """
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
    """
    执行 shell 命令并返回输出。

    Args:
        command: 要执行的 shell 命令
        timeout: 超时时间（秒）

    Returns:
        命令输出或错误信息
    """
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
    """
    读取文件内容。

    Args:
        file_path: 文件路径（相对于工作目录）

    Returns:
        文件内容或错误信息
    """
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
    """
    写入内容到文件。父目录不存在时自动创建。

    Args:
        file_path: 文件路径（相对于工作目录）
        content: 要写入的内容

    Returns:
        操作结果信息
    """
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
    这和 OpenClaw 的 edit 工具逻辑一致。

    Args:
        file_path: 文件路径（相对于工作目录）
        old_string: 要查找和替换的文本（必须唯一）
        new_string: 替换后的文本

    Returns:
        操作结果信息
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


# ---------------------------------------------------------------------------
# 工具调度表
# ---------------------------------------------------------------------------

TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
}


# ---------------------------------------------------------------------------
# 工具分发函数
# ---------------------------------------------------------------------------


def process_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    根据工具名分发到对应的处理函数。
    这就是整个 "agent" 的核心调度逻辑。

    错误作为字符串返回（而非抛出异常），这样模型可以看到错误并自行修正。

    Args:
        tool_name: 工具名称
        tool_input: 工具输入参数

    Returns:
        工具执行结果或错误信息
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return handler(**tool_input)
    except TypeError as exc:
        return f"Error: Invalid arguments for {tool_name}: {exc}"
    except Exception as exc:
        return f"Error: {tool_name} failed: {exc}"


__all__ = [
    "MAX_TOOL_OUTPUT",
    "WORKDIR",
    "safe_path",
    "truncate",
    "tool_bash",
    "tool_read_file",
    "tool_write_file",
    "tool_edit_file",
    "TOOL_HANDLERS",
    "process_tool_call",
]
