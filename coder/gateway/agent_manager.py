"""
Agent 管理器

多 agent 注册中心，每个 agent 有自己的配置、性格和模型。

AgentConfig: 单个 agent 的配置
AgentManager: 管理多个 agent 的注册中心
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from coder.gateway.routing import normalize_agent_id
from coder.settings import settings


@dataclass
class AgentConfig:
    """
    Agent 配置。

    Attributes:
        id: agent 唯一标识符
        name: agent 显示名称
        personality: agent 性格描述
        model: 使用的模型 ID (空表示使用全局 MODEL_ID)
        dm_scope: 会话隔离范围 ("main", "per-peer", "per-channel-peer", "per-account-channel-peer")
        tools: 可用工具列表 (None 表示使用默认工具)
        extra: 额外配置字典
    """

    id: str
    name: str
    personality: str = ""
    model: str = ""
    dm_scope: str = "per-peer"
    tools: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def effective_model(self) -> str:
        """
        获取有效模型 ID。

        Returns:
            配置的模型 ID 或全局默认模型 ID
        """
        return self.model or settings.model_id

    def system_prompt(self) -> str:
        """
        生成系统提示词。

        Returns:
            基于 agent 配置生成的系统提示词
        """
        parts = [f"You are {self.name}."]
        if self.personality:
            parts.append(f"Your personality: {self.personality}")
        parts.append("Answer questions helpfully and stay in character.")
        return " ".join(parts)


class AgentManager:
    """
    Agent 管理器。

    负责注册、管理和查询多个 agent。

    Example:
        >>> mgr = AgentManager()
        >>> mgr.register(AgentConfig(id="luna", name="Luna", personality="warm, curious, and encouraging."))
        >>> agent = mgr.get_agent("luna")
        >>> print(agent.name)  # "Luna"
    """

    def __init__(self, agents_base: Optional[Path] = None) -> None:
        """
        初始化 Agent 管理器。

        Args:
            agents_base: agent 配置目录基础路径，默认使用 settings.agents_base_dir
        """
        self._agents: Dict[str, AgentConfig] = {}
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

        # 设置 agent 基础目录
        if agents_base:
            self._agents_base = agents_base
        else:
            self._agents_base = Path(settings.agents_base_dir)

        # 确保 agent 基础目录存在
        self._agents_base.mkdir(parents=True, exist_ok=True)

    def register(self, config: AgentConfig) -> None:
        """
        注册 agent。

        Args:
            config: agent 配置
        """
        aid = normalize_agent_id(config.id)
        config.id = aid
        self._agents[aid] = config

        # 创建 agent 专用目录
        agent_dir = self._agents_base / aid
        agent_dir.mkdir(parents=True, exist_ok=True)

        # 创建 sessions 子目录
        (agent_dir / "sessions").mkdir(parents=True, exist_ok=True)

        # 创建 workspace 子目录
        workspace_dir = Path(settings.session_workspace).parent / f"workspace-{aid}"
        workspace_dir.mkdir(parents=True, exist_ok=True)

    def unregister(self, agent_id: str) -> bool:
        """
        注销 agent。

        Args:
            agent_id: agent ID

        Returns:
            True 如果注销成功，False 如果 agent 不存在
        """
        aid = normalize_agent_id(agent_id)
        if aid in self._agents:
            del self._agents[aid]
            # 清理该 agent 的会话
            keys_to_remove = [k for k in self._sessions if k.startswith(f"agent:{aid}:")]
            for k in keys_to_remove:
                del self._sessions[k]
            return True
        return False

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """
        获取 agent 配置。

        Args:
            agent_id: agent ID

        Returns:
            agent 配置，如果不存在则返回 None
        """
        return self._agents.get(normalize_agent_id(agent_id))

    def list_agents(self) -> List[AgentConfig]:
        """
        列出所有 agent。

        Returns:
            agent 配置列表
        """
        return list(self._agents.values())

    def get_session(self, session_key: str) -> List[Dict[str, Any]]:
        """
        获取会话消息历史。

        Args:
            session_key: 会话键

        Returns:
            消息历史列表
        """
        if session_key not in self._sessions:
            self._sessions[session_key] = []
        return self._sessions[session_key]

    def set_session(self, session_key: str, messages: List[Dict[str, Any]]) -> None:
        """
        设置会话消息历史。

        Args:
            session_key: 会话键
            messages: 消息历史列表
        """
        self._sessions[session_key] = messages

    def clear_session(self, session_key: str) -> bool:
        """
        清空会话。

        Args:
            session_key: 会话键

        Returns:
            True 如果清空成功，False 如果会话不存在
        """
        if session_key in self._sessions:
            self._sessions[session_key] = []
            return True
        return False

    def list_sessions(self, agent_id: str = "") -> Dict[str, int]:
        """
        列出会话。

        Args:
            agent_id: 可选的 agent ID 过滤

        Returns:
            会话键到消息数量的映射
        """
        aid = normalize_agent_id(agent_id) if agent_id else ""
        return {k: len(v) for k, v in self._sessions.items() if not aid or k.startswith(f"agent:{aid}:")}


__all__ = [
    "AgentConfig",
    "AgentManager",
]
