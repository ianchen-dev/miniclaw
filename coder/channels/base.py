"""
Channel 抽象基类

定义所有通道必须实现的接口契约。

添加新平台只需实现两个方法:
    - receive(): 接收消息，返回 InboundMessage 或 None
    - send(): 发送消息到指定目标
"""

from abc import ABC, abstractmethod
from typing import Any

from coder.channels.schema import InboundMessage


class Channel(ABC):
    """
    通道抽象基类。

    所有通道实现都必须继承此类并实现 receive() 和 send() 方法。

    Attributes:
        name: 通道名称标识符
    """

    name: str = "unknown"

    @abstractmethod
    def receive(self) -> InboundMessage | None:
        """
        接收一条消息。

        Returns:
            InboundMessage 如果有消息，None 如果没有消息或应该退出
        """
        ...

    @abstractmethod
    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        """
        发送消息到指定目标。

        Args:
            to: 目标ID（如 chat_id, user_id）
            text: 消息文本
            **kwargs: 额外参数（如 reply_to, parse_mode 等）

        Returns:
            True 表示发送成功，False 表示发送失败
        """
        ...

    def close(self) -> None:
        """
        关闭通道，释放资源。

        子类可以覆盖此方法以执行清理操作。
        """
        return None


__all__ = [
    "Channel",
]
