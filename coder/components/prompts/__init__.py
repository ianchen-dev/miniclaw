"""
提示词组件 - 系统提示词管理

提供系统提示词的定义和组装功能。
s06 扩展为 8 层动态组装。

用法:
    from coder.components.prompts import get_system_prompt

    # 简单模式 (不使用智能层)
    prompt = get_system_prompt()

    # 完整模式 (使用智能层)
    from coder.components.intelligence import (
        BootstrapLoader, SkillsManager, MemoryStore,
        build_system_prompt, auto_recall
    )
    loader = BootstrapLoader()
    bootstrap = loader.load_all(mode="full")
    skills_mgr = SkillsManager()
    skills_mgr.discover()
    memory_store = MemoryStore()
    memory_context = auto_recall("user message", memory_store)
    prompt = build_system_prompt(
        mode="full",
        bootstrap=bootstrap,
        skills_block=skills_mgr.format_prompt_block(),
        memory_context=memory_context,
    )
"""

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions directly."


def get_system_prompt(
    mode: str = "simple",
    bootstrap: Optional[Dict[str, str]] = None,
    skills_block: str = "",
    memory_context: str = "",
    agent_id: str = "main",
    channel: str = "terminal",
) -> str:
    """
    获取系统提示词

    Args:
        mode: 提示词模式
            - "simple": 返回默认提示词 (向后兼容)
            - "full": 使用智能层 8 层组装
            - "minimal": 最小化提示词
        bootstrap: Bootstrap 文件内容映射 (智能层模式)
        skills_block: 格式化后的技能块 (智能层模式)
        memory_context: 自动召回的记忆上下文 (智能层模式)
        agent_id: Agent 标识符 (智能层模式)
        channel: 通道类型 (智能层模式)

    Returns:
        系统提示词
    """
    if mode == "simple":
        return DEFAULT_SYSTEM_PROMPT

    # 使用智能层组装
    from coder.components.intelligence import build_system_prompt

    return build_system_prompt(
        mode=mode,
        bootstrap=bootstrap,
        skills_block=skills_block,
        memory_context=memory_context,
        agent_id=agent_id,
        channel=channel,
    )


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "get_system_prompt",
]
