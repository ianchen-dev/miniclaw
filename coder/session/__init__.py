"""
Session 组件 - 会话持久化与上下文保护

提供:
    - SessionStore: JSONL 持久化存储
    - ContextGuard: 三阶段上下文溢出保护

用法:
    from coder.session import SessionStore, ContextGuard

    # 创建会话存储
    store = SessionStore(agent_id="my-agent")
    session_id = store.create_session("my-session")

    # 保存对话
    store.save_turn("user", "Hello")
    store.save_turn("assistant", [{"type": "text", "text": "Hi!"}])

    # 恢复会话
    messages = store.load_session(session_id)

    # 上下文保护
    guard = ContextGuard()
    response = guard.guard_api_call(
        api_key=api_key,
        model=model,
        system=system_prompt,
        messages=messages,
    )
"""

from coder.session.guard import ContextGuard, _serialize_messages_for_summary
from coder.session.store import SessionStore


__all__ = [
    "SessionStore",
    "ContextGuard",
    "_serialize_messages_for_summary",
]
