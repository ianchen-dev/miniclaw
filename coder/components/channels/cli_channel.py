"""
CLI 通道实现

最简单的通道实现，使用标准输入输出。
receive() 包装 input()，send() 包装 print()。
"""

from typing import Any

from coder.components.channels.base import Channel
from coder.components.channels.schema import InboundMessage
from coder.components.cli import colored_user, print_assistant


class CLIChannel(Channel):
    """
    命令行通道。

    通过标准输入输出与用户交互。适用于本地开发和测试。

    Attributes:
        name: 通道名称，固定为 "cli"
        account_id: bot 账号ID，固定为 "cli-local"
    """

    name = "cli"

    def __init__(self) -> None:
        """初始化 CLI 通道。"""
        self.account_id = "cli-local"

    def receive(self) -> InboundMessage | None:
        """
        从标准输入接收消息。

        Returns:
            InboundMessage 如果用户输入了内容，None 如果用户退出或输入为空
        """
        try:
            text = input(colored_user()).strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if not text:
            return None

        return InboundMessage(
            text=text,
            sender_id="cli-user",
            channel="cli",
            account_id=self.account_id,
            peer_id="cli-user",
        )

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        """
        打印消息到标准输出。

        Args:
            to: 目标ID（CLI 通道忽略此参数）
            text: 消息文本
            **kwargs: 额外参数（CLI 通道忽略）

        Returns:
            总是返回 True
        """
        print_assistant(text)
        return True


__all__ = [
    "CLIChannel",
]
