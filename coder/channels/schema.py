"""
通道数据结构

定义所有通道统一的消息格式和账号配置。

InboundMessage: 所有通道都规范化为此结构。Agent 循环只看到 InboundMessage。
ChannelAccount: 每个 bot 的配置。同一通道类型可以运行多个 bot。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class InboundMessage:
    """
    所有通道都规范化为此结构。

    Agent 循环只看到 InboundMessage，永远不接触平台特定的负载。

    Attributes:
        text: 消息文本内容
        sender_id: 发送者ID
        channel: 通道类型 ("cli", "telegram", "feishu")
        account_id: 接收消息的 bot 账号ID
        peer_id: 会话ID，编码了会话范围:
            - Telegram 私聊: user_id
            - Telegram 群组: chat_id
            - Telegram 话题: chat_id:topic:thread_id
            - 飞书单聊: user_id
            - 飞书群组: chat_id
        is_group: 是否是群组消息
        media: 媒体附件列表
        raw: 原始平台消息数据
    """

    text: str
    sender_id: str
    channel: str = ""
    account_id: str = ""
    peer_id: str = ""
    is_group: bool = False
    media: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelAccount:
    """
    每个 bot 的配置。

    同一通道类型可以运行多个 bot（例如多个 Telegram bot）。

    Attributes:
        channel: 通道类型 ("cli", "telegram", "feishu")
        account_id: bot 账号唯一标识
        token: 认证令牌（如 Telegram bot token）
        config: 额外配置字典
    """

    channel: str
    account_id: str
    token: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


def build_session_key(
    channel: str,
    account_id: str,
    peer_id: str,
    agent_id: str = "main",
    dm_scope: str = "per-peer",
) -> str:
    """
    构建会话键。

    dm_scope 控制私聊隔离粒度:
        - "main": agent:{id}:main - 所有人共享一个会话
        - "per-peer": agent:{id}:direct:{peer} - 每个用户隔离
        - "per-channel-peer": agent:{id}:{ch}:direct:{peer} - 每个平台的不同会话
        - "per-account-channel-peer": agent:{id}:{ch}:{acc}:direct:{peer} - 最大隔离度

    Args:
        channel: 通道类型
        account_id: bot 账号ID
        peer_id: 会话ID
        agent_id: agent ID (默认 "main")
        dm_scope: 会话隔离范围 (默认 "per-peer")

    Returns:
        格式化的会话键字符串
    """
    from coder.gateway.routing import normalize_agent_id

    aid = normalize_agent_id(agent_id)
    ch = (channel or "unknown").strip().lower()
    acc = (account_id or "default").strip().lower()
    pid = (peer_id or "").strip().lower()

    if not pid:
        return f"agent:{aid}:main"

    if dm_scope == "per-account-channel-peer":
        return f"agent:{aid}:{ch}:{acc}:direct:{pid}"
    if dm_scope == "per-channel-peer":
        return f"agent:{aid}:{ch}:direct:{pid}"
    if dm_scope == "per-peer":
        return f"agent:{aid}:direct:{pid}"
    return f"agent:{aid}:main"


__all__ = [
    "InboundMessage",
    "ChannelAccount",
    "build_session_key",
]
