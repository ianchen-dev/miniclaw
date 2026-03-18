"""
提示词组件 - 系统提示词管理

提供系统提示词的定义和组装功能。
后续章节将扩展为8层动态组装。
"""

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions directly."


def get_system_prompt() -> str:
    """
    获取系统提示词

    当前返回默认提示词，后续章节将实现:
    - 动态加载
    - 8层组装
    - 上下文注入
    """
    return DEFAULT_SYSTEM_PROMPT


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "get_system_prompt",
]
