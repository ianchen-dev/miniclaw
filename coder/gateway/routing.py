"""
路由绑定组件

实现五层路由解析系统，将 (channel, peer) 映射到 agent_id。

路由层级 (从最具体到最通用):
    Tier 1: peer_id    - 将特定用户路由到某个 agent
    Tier 2: guild_id   - guild/服务器级别
    Tier 3: account_id - bot 账号级别
    Tier 4: channel    - 整个通道 (如所有 Telegram)
    Tier 5: default    - 兜底
"""

import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

# Agent ID 标准化
VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
DEFAULT_AGENT_ID = "main"


def normalize_agent_id(value: str) -> str:
    """
    标准化 agent ID。

    Args:
        value: 原始 agent ID

    Returns:
        标准化后的 agent ID
    """
    trimmed = value.strip()
    if not trimmed:
        return DEFAULT_AGENT_ID
    if VALID_ID_RE.match(trimmed):
        return trimmed.lower()
    cleaned = INVALID_CHARS_RE.sub("-", trimmed.lower()).strip("-")[:64]
    return cleaned or DEFAULT_AGENT_ID


@dataclass
class Binding:
    """
    路由绑定配置。

    Attributes:
        agent_id: 目标 agent ID
        tier: 层级 (1-5, 越小越具体)
        match_key: 匹配键 ("peer_id" | "guild_id" | "account_id" | "channel" | "default")
        match_value: 匹配值 (例如 "telegram:12345", "discord", "*")
        priority: 同层内的优先级 (越大越优先)
    """

    agent_id: str
    tier: int  # 1-5, 越小越具体
    match_key: str  # "peer_id" | "guild_id" | "account_id" | "channel" | "default"
    match_value: str  # 例如 "telegram:12345", "discord", "*"
    priority: int = 0  # 同层内, 越大越优先

    def display(self) -> str:
        """
        返回绑定的显示字符串。

        Returns:
            格式化的绑定信息
        """
        names = {1: "peer", 2: "guild", 3: "account", 4: "channel", 5: "default"}
        label = names.get(self.tier, f"tier-{self.tier}")
        return f"[{label}] {self.match_key}={self.match_value} -> agent:{self.agent_id} (pri={self.priority})"


class BindingTable:
    """
    路由绑定表。

    维护一个按 (tier, -priority) 排序的绑定列表。
    解析时从 Tier 1 到 Tier 5 遍历，首次匹配即返回。

    Example:
        >>> bt = BindingTable()
        >>> bt.add(Binding(agent_id="luna", tier=5, match_key="default", match_value="*"))
        >>> bt.add(Binding(agent_id="sage", tier=4, match_key="channel", match_value="telegram"))
        >>> agent_id, binding = bt.resolve(channel="telegram", peer_id="user1")
        >>> print(agent_id)  # "sage"
    """

    def __init__(self) -> None:
        """初始化绑定表。"""
        self._bindings: List[Binding] = []

    def add(self, binding: Binding) -> None:
        """
        添加绑定。

        Args:
            binding: 要添加的绑定配置
        """
        self._bindings.append(binding)
        # 按 tier 升序，priority 降序排序
        self._bindings.sort(key=lambda b: (b.tier, -b.priority))

    def remove(self, agent_id: str, match_key: str, match_value: str) -> bool:
        """
        移除绑定。

        Args:
            agent_id: agent ID
            match_key: 匹配键
            match_value: 匹配值

        Returns:
            True 如果移除成功，False 如果绑定不存在
        """
        before = len(self._bindings)
        self._bindings = [
            b
            for b in self._bindings
            if not (b.agent_id == agent_id and b.match_key == match_key and b.match_value == match_value)
        ]
        return len(self._bindings) < before

    def list_all(self) -> List[Binding]:
        """
        列出所有绑定。

        Returns:
            绑定列表的副本
        """
        return list(self._bindings)

    def clear(self) -> None:
        """清空所有绑定。"""
        self._bindings.clear()

    def resolve(
        self,
        channel: str = "",
        account_id: str = "",
        guild_id: str = "",
        peer_id: str = "",
    ) -> Tuple[Optional[str], Optional[Binding]]:
        """
        解析路由。

        遍历第 1-5 层，第一个匹配的获胜。

        Args:
            channel: 通道类型
            account_id: bot 账号 ID
            guild_id: guild/服务器 ID
            peer_id: 用户/会话 ID

        Returns:
            (agent_id, matched_binding) 元组，如果没有匹配则返回 (None, None)
        """
        for b in self._bindings:
            if b.tier == 1 and b.match_key == "peer_id":
                # peer_id 可以是 "channel:peer_id" 格式或纯 "peer_id"
                if ":" in b.match_value:
                    if b.match_value == f"{channel}:{peer_id}":
                        return b.agent_id, b
                elif b.match_value == peer_id:
                    return b.agent_id, b
            elif (
                (b.tier == 2 and b.match_key == "guild_id" and b.match_value == guild_id)
                or (b.tier == 3 and b.match_key == "account_id" and b.match_value == account_id)
                or (b.tier == 4 and b.match_key == "channel" and b.match_value == channel)
                or (b.tier == 5 and b.match_key == "default")
            ):
                return b.agent_id, b
        return None, None


__all__ = [
    "Binding",
    "BindingTable",
    "normalize_agent_id",
    "DEFAULT_AGENT_ID",
]
