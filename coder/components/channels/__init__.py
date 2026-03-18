"""
Channels 组件 - 多通道消息收发

提供统一的消息通道抽象，支持 CLI、Telegram、飞书等平台。

架构:
    Telegram ----.                          .---- sendMessage API
    Feishu -------+-- InboundMessage ---+---- im/v1/messages
    CLI (stdin) --'    Agent Loop        '---- print(stdout)

核心概念:
    - InboundMessage: 统一的消息格式，所有通道都归一化为此结构
    - Channel ABC: receive() + send() 接口契约
    - ChannelManager: 通道注册和管理

用法:
    from coder.components.channels import (
        Channel,
        InboundMessage,
        ChannelAccount,
        ChannelManager,
        CLIChannel,
        TelegramChannel,
        FeishuChannel,
    )

    # 创建通道管理器
    mgr = ChannelManager()

    # 注册 CLI 通道
    cli = CLIChannel()
    mgr.register(cli)

    # 注册 Telegram 通道
    from coder.settings import settings
    if settings.telegram_bot_token:
        acc = ChannelAccount(
            channel="telegram",
            account_id="tg-primary",
            token=settings.telegram_bot_token,
            config={"allowed_chats": settings.telegram_allowed_chats}
        )
        mgr.accounts.append(acc)
        mgr.register(TelegramChannel(acc))

    # 接收和发送消息
    if msg := cli.receive():
        # 处理消息...
        mgr.get(msg.channel).send(msg.peer_id, "Hello!")
"""

from coder.components.channels.schema import InboundMessage, ChannelAccount, build_session_key
from coder.components.channels.base import Channel
from coder.components.channels.manager import ChannelManager
from coder.components.channels.cli_channel import CLIChannel

# 条件导入：需要 httpx 的通道
try:
    from coder.components.channels.telegram_channel import TelegramChannel
except ImportError:
    TelegramChannel = None  # type: ignore

try:
    from coder.components.channels.feishu_channel import FeishuChannel
except ImportError:
    FeishuChannel = None  # type: ignore

__all__ = [
    # 数据结构
    "InboundMessage",
    "ChannelAccount",
    "build_session_key",
    # 基类
    "Channel",
    # 管理器
    "ChannelManager",
    # 通道实现
    "CLIChannel",
    "TelegramChannel",
    "FeishuChannel",
]
