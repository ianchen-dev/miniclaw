"""
Gateway 组件 - 网关与路由 (s05)

实现多 agent 路由系统和 WebSocket 网关。

核心组件:
    - BindingTable: 五层路由绑定表
    - AgentManager: 多 agent 管理器
    - GatewayServer: WebSocket 网关服务器
    - build_session_key: 会话键构建器

路由层级 (从最具体到最通用):
    Tier 1: peer_id    - 将特定用户路由到某个 agent
    Tier 2: guild_id   - guild/服务器级别
    Tier 3: account_id - bot 账号级别
    Tier 4: channel    - 整个通道 (如所有 Telegram)
    Tier 5: default    - 兜底

Example:
    >>> from coder.gateway import AgentManager, AgentConfig, BindingTable, Binding
    >>>
    >>> # 创建 agent 管理器
    >>> mgr = AgentManager()
    >>> mgr.register(AgentConfig(id="luna", name="Luna", personality="warm and encouraging."))
    >>>
    >>> # 创建绑定表
    >>> bt = BindingTable()
    >>> bt.add(Binding(agent_id="luna", tier=5, match_key="default", match_value="*"))
    >>>
    >>> # 解析路由
    >>> agent_id, binding = bt.resolve(channel="cli", peer_id="user1")
    >>> print(agent_id)  # "luna"
"""

from coder.gateway.agent_manager import (
    AgentConfig,
    AgentManager,
)
from coder.gateway.event_loop import (
    get_event_loop,
    run_async,
    stop_event_loop,
)
from coder.gateway.routing import (
    DEFAULT_AGENT_ID,
    Binding,
    BindingTable,
    normalize_agent_id,
)
from coder.gateway.server import GatewayServer


__all__ = [
    # 路由
    "Binding",
    "BindingTable",
    "normalize_agent_id",
    "DEFAULT_AGENT_ID",
    # Agent 管理
    "AgentConfig",
    "AgentManager",
    # 网关服务器
    "GatewayServer",
    # 事件循环
    "get_event_loop",
    "run_async",
    "stop_event_loop",
]
