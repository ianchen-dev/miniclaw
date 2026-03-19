"""
工具 Schema 定义

定义 Agent 可用的工具，供 LLM API 调用。
每个工具包含 type, function (name, description, parameters)。

OpenAI API 工具格式:
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "Tool description",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    }

工具分组:
    - 基础工具 (s02): bash, read_file, write_file, edit_file
    - 记忆工具 (s06): memory_write, memory_search
"""

from typing import List, Dict, Any

# 基础工具 (s02)
BASE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a shell command and return its output. Use for system commands, git, package managers, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default 30.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to working directory).",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file. Creates parent directories if needed. Overwrites existing content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to working directory).",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace an exact string in a file with a new string. "
                "The old_string must appear exactly once in the file. "
                "Always read the file first to get the exact text to replace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to working directory).",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace. Must be unique.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
    },
]

# 记忆工具 (s06)
MEMORY_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": (
                "Save an important fact or observation to long-term memory. "
                "Use when you learn something worth remembering about the user or context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The fact or observation to remember.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category: preference, fact, context, etc.",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search stored memories for relevant information, ranked by similarity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max results. Default: 5.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# 完整工具列表 (基础 + 记忆)
TOOLS: List[Dict[str, Any]] = BASE_TOOLS + MEMORY_TOOLS


__all__ = ["TOOLS", "BASE_TOOLS", "MEMORY_TOOLS"]
