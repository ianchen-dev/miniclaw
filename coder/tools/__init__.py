"""
Tools 组件 - 工具定义与处理器

提供 Agent 可用的工具:
    - bash: 执行 shell 命令
    - read_file: 读取文件内容
    - write_file: 写入文件
    - edit_file: 精确替换文件中的文本
    - memory_write: 保存记忆 (s06)
    - memory_search: 搜索记忆 (s06)

核心概念:
    TOOLS = 告诉模型 "你有哪些工具可用" (JSON schema)
    TOOL_HANDLERS = 告诉代码 "收到工具调用时执行什么函数" (dict)

用法:
    from coder.tools import TOOLS, TOOL_HANDLERS, process_tool_call

    # 获取工具 schema 传给 LLM
    response = litellm.completion(..., tools=TOOLS)

    # 分发工具调用
    result = process_tool_call(tool_name, tool_input)

    # 只使用基础工具 (不包含记忆工具)
    from coder.tools.schema import BASE_TOOLS
    response = litellm.completion(..., tools=BASE_TOOLS)
"""

from coder.tools.handlers import (
    TOOL_HANDLERS,
    process_tool_call,
    tool_memory_search,
    tool_memory_write,
)
from coder.tools.schema import BASE_TOOLS, MEMORY_TOOLS, TOOLS


__all__ = [
    "TOOLS",
    "BASE_TOOLS",
    "MEMORY_TOOLS",
    "TOOL_HANDLERS",
    "process_tool_call",
    "tool_memory_write",
    "tool_memory_search",
]
