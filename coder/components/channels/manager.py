"""
通道管理器

持有所有活跃通道的注册中心。
"""

from typing import Dict, List

from coder.components.channels.base import Channel
from coder.components.channels.schema import ChannelAccount
from coder.components.cli import BLUE, RESET


class ChannelManager:
    """
    通道管理器。

    负责注册、管理和关闭所有活跃的通道。

    Attributes:
        channels: 已注册的通道字典，键为通道名称
        accounts: 已配置的账号列表
    """

    def __init__(self) -> None:
        """初始化通道管理器。"""
        self.channels: Dict[str, Channel] = {}
        self.accounts: List[ChannelAccount] = []

    def register(self, channel: Channel) -> None:
        """
        注册一个通道。

        Args:
            channel: 要注册的通道实例
        """
        self.channels[channel.name] = channel
        print(f"{BLUE}  [+] Channel registered: {channel.name}{RESET}")

    def unregister(self, name: str) -> bool:
        """
        注销一个通道。

        Args:
            name: 通道名称

        Returns:
            True 如果注销成功，False 如果通道不存在
        """
        if name in self.channels:
            channel = self.channels.pop(name)
            channel.close()
            return True
        return False

    def list_channels(self) -> List[str]:
        """
        列出所有已注册的通道名称。

        Returns:
            通道名称列表
        """
        return list(self.channels.keys())

    def get(self, name: str) -> Channel | None:
        """
        获取指定名称的通道。

        Args:
            name: 通道名称

        Returns:
            通道实例，如果不存在则返回 None
        """
        return self.channels.get(name)

    def close_all(self) -> None:
        """关闭所有已注册的通道。"""
        for ch in self.channels.values():
            ch.close()
        self.channels.clear()


__all__ = [
    "ChannelManager",
]
