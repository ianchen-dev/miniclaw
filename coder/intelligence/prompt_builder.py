"""
系统提示词组装器

8 层提示词组装的核心实现:
    1. Identity (身份)
    2. Soul (性格)
    3. Tools guidance (工具使用指南)
    4. Skills (技能)
    5. Memory (常驻 + 召回的记忆)
    6. Bootstrap (剩余的引导文件)
    7. Runtime context (运行时上下文)
    8. Channel hints (通道提示)

更靠前的层 = 对行为影响力更强
SOUL.md 在第 2 层正是这个原因
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from coder.intelligence.memory import MemoryStore
from coder.settings import settings


def auto_recall(user_message: str, memory_store: Optional[MemoryStore] = None, top_k: Optional[int] = None) -> str:
    """
    根据用户消息自动搜索相关记忆

    将结果注入到系统提示词中。

    Args:
        user_message: 用户消息
        memory_store: 记忆存储实例, 如果为 None 则创建新实例
        top_k: 返回结果数量, 默认 3

    Returns:
        格式化的记忆上下文字符串
    """
    if memory_store is None:
        memory_store = MemoryStore()

    if top_k is None:
        top_k = 3

    results = memory_store.hybrid_search(user_message, top_k=top_k)
    if not results:
        return ""

    return "\n".join(f"- [{r['path']}] {r['snippet']}" for r in results)


def build_system_prompt(
    mode: str = "full",
    bootstrap: Optional[Dict[str, str]] = None,
    skills_block: str = "",
    memory_context: str = "",
    agent_id: str = "main",
    channel: str = "terminal",
    model_id: Optional[str] = None,
) -> str:
    """
    构建 8 层系统提示词

    每轮重新构建 -- 上一轮可能更新了记忆。

    Args:
        mode: 提示词模式
            - "full": 主 agent, 包含所有层
            - "minimal": 子 agent / cron, 只包含核心层
            - "none": 最小化, 只包含身份
        bootstrap: Bootstrap 文件内容映射
        skills_block: 格式化后的技能块
        memory_context: 自动召回的记忆上下文
        agent_id: Agent 标识符
        channel: 通道类型 (terminal/telegram/discord/slack)
        model_id: 模型 ID

    Returns:
        组装好的系统提示词
    """
    if bootstrap is None:
        bootstrap = {}

    sections: List[str] = []

    # 第 1 层: 身份 -- 来自 IDENTITY.md 或默认值
    identity = bootstrap.get("IDENTITY.md", "").strip()
    sections.append(identity if identity else "You are a helpful personal AI assistant.")

    # 第 2 层: 灵魂 -- 人格注入, 越靠前影响力越强
    if mode == "full":
        soul = bootstrap.get("SOUL.md", "").strip()
        if soul:
            sections.append(f"## Personality\n\n{soul}")

    # 第 3 层: 工具使用指南
    tools_md = bootstrap.get("TOOLS.md", "").strip()
    if tools_md:
        sections.append(f"## Tool Usage Guidelines\n\n{tools_md}")

    # 第 4 层: 技能
    if mode == "full" and skills_block:
        sections.append(skills_block)

    # 第 5 层: 记忆 -- 长期记忆 + 本轮自动搜索结果
    if mode == "full":
        mem_md = bootstrap.get("MEMORY.md", "").strip()
        parts: List[str] = []
        if mem_md:
            parts.append(f"### Evergreen Memory\n\n{mem_md}")
        if memory_context:
            parts.append(f"### Recalled Memories (auto-searched)\n\n{memory_context}")
        if parts:
            sections.append("## Memory\n\n" + "\n\n".join(parts))
        sections.append(
            "## Memory Instructions\n\n"
            "- Use memory_write to save important user facts and preferences.\n"
            "- Reference remembered facts naturally in conversation.\n"
            "- Use memory_search to recall specific past information."
        )

    # 第 6 层: Bootstrap 上下文 -- 剩余的 Bootstrap 文件
    if mode in ("full", "minimal"):
        for name in ["HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "USER.md"]:
            content = bootstrap.get(name, "").strip()
            if content:
                sections.append(f"## {name.replace('.md', '')}\n\n{content}")

    # 第 7 层: 运行时上下文
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model = model_id or settings.model_id
    sections.append(
        f"## Runtime Context\n\n"
        f"- Agent ID: {agent_id}\n"
        f"- Model: {model}\n"
        f"- Channel: {channel}\n"
        f"- Current time: {now}\n"
        f"- Prompt mode: {mode}"
    )

    # 第 8 层: 渠道提示
    hints = {
        "terminal": "You are responding via a terminal REPL. Markdown is supported.",
        "telegram": "You are responding via Telegram. Keep messages concise.",
        "discord": "You are responding via Discord. Keep messages under 2000 characters.",
        "slack": "You are responding via Slack. Use Slack mrkdwn formatting.",
    }
    sections.append(f"## Channel\n\n{hints.get(channel, f'You are responding via {channel}.')}")

    return "\n\n".join(sections)


__all__ = [
    "build_system_prompt",
    "auto_recall",
]
