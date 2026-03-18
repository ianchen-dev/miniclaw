"""
WebSocket 网关服务器

实现 JSON-RPC 2.0 协议的 WebSocket 网关，用于远程消息发送和管理。

支持的 JSON-RPC 方法:
    - send: 发送消息到 agent
    - bindings.set: 设置路由绑定
    - bindings.list: 列出所有绑定
    - sessions.list: 列出会话
    - agents.list: 列出所有 agent
    - status: 获取网关状态
"""

import asyncio
import json
import time
from typing import Any, Callable, Dict, Set

from coder.components.gateway.routing import Binding, BindingTable, normalize_agent_id
from coder.components.gateway.agent_manager import AgentManager
from coder.components.channels.schema import build_session_key
from coder.components.cli import GREEN, RED, DIM


class GatewayServer:
    """
    WebSocket 网关服务器。

    实现 JSON-RPC 2.0 协议，支持远程消息发送和管理操作。

    Example:
        >>> mgr = AgentManager()
        >>> bindings = BindingTable()
        >>> gw = GatewayServer(mgr, bindings, host="localhost", port=8765)
        >>> await gw.start()
    """

    def __init__(
        self,
        manager: AgentManager,
        bindings: BindingTable,
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        """
        初始化网关服务器。

        Args:
            manager: Agent 管理器
            bindings: 路由绑定表
            host: 监听地址
            port: 监听端口
        """
        self._manager = manager
        self._bindings = bindings
        self._host = host
        self._port = port
        self._clients: Set[Any] = set()
        self._start_time = time.monotonic()
        self._server: Any = None
        self._running = False

    async def start(self) -> bool:
        """
        启动网关服务器。

        Returns:
            True 如果启动成功，False 如果失败
        """
        try:
            import websockets
        except ImportError:
            print(f"{RED}websockets not installed. Run: pip install websockets{DIM}")
            return False

        self._start_time = time.monotonic()
        self._running = True

        try:
            self._server = await websockets.serve(self._handle_connection, self._host, self._port)
            print(f"{GREEN}Gateway started on ws://{self._host}:{self._port}{DIM}")
            return True
        except Exception as exc:
            print(f"{RED}Failed to start gateway: {exc}{DIM}")
            self._running = False
            return False

    async def stop(self) -> None:
        """停止网关服务器。"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._running = False

    @property
    def is_running(self) -> bool:
        """返回服务器是否正在运行。"""
        return self._running

    @property
    def client_count(self) -> int:
        """返回当前连接的客户端数量。"""
        return len(self._clients)

    async def _handle_connection(self, websocket: Any, path: str = "") -> None:
        """
        处理 WebSocket 连接。

        Args:
            websocket: WebSocket 连接对象
            path: 请求路径
        """
        self._clients.add(websocket)
        try:
            async for raw_message in websocket:
                response = await self._dispatch_message(raw_message)
                if response:
                    await websocket.send(json.dumps(response))
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)

    def _notify_typing(self, agent_id: str, is_typing: bool) -> None:
        """
        通知所有客户端 typing 状态变化。

        Args:
            agent_id: agent ID
            is_typing: 是否正在输入
        """
        message = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "typing",
                "params": {"agent_id": agent_id, "typing": is_typing},
            }
        )
        for ws in list(self._clients):
            try:
                asyncio.ensure_future(ws.send(message))
            except Exception:
                self._clients.discard(ws)

    async def _dispatch_message(self, raw: str) -> Dict[str, Any]:
        """
        分发 JSON-RPC 消息。

        Args:
            raw: 原始消息字符串

        Returns:
            JSON-RPC 响应字典
        """
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            }

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # 方法映射
        methods: Dict[str, Callable] = {
            "send": self._method_send,
            "bindings.set": self._method_bindings_set,
            "bindings.list": self._method_bindings_list,
            "sessions.list": self._method_sessions_list,
            "agents.list": self._method_agents_list,
            "status": self._method_status,
        }

        handler = methods.get(method)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id,
            }

        try:
            result = await handler(params)
            return {"jsonrpc": "2.0", "result": result, "id": request_id}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": str(exc)},
                "id": request_id,
            }

    async def _method_send(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 send 方法。

        Args:
            params: 方法参数

        Returns:
            包含 agent_id, session_key 和 reply 的结果
        """
        text = params.get("text", "")
        if not text:
            raise ValueError("text is required")

        channel = params.get("channel", "websocket")
        peer_id = params.get("peer_id", "ws-client")
        account_id = params.get("account_id", "")
        guild_id = params.get("guild_id", "")

        # 确定目标 agent
        if params.get("agent_id"):
            # 强制指定 agent
            agent_id = normalize_agent_id(params["agent_id"])
            agent = self._manager.get_agent(agent_id)
            dm_scope = agent.dm_scope if agent else "per-peer"
            session_key = build_session_key(
                channel=channel,
                account_id=account_id,
                peer_id=peer_id,
                agent_id=agent_id,
                dm_scope=dm_scope,
            )
        else:
            # 通过路由解析
            agent_id, binding = self._bindings.resolve(
                channel=channel,
                account_id=account_id,
                guild_id=guild_id,
                peer_id=peer_id,
            )
            if not agent_id:
                agent_id = "main"
            agent = self._manager.get_agent(agent_id)
            dm_scope = agent.dm_scope if agent else "per-peer"
            session_key = build_session_key(
                channel=channel,
                account_id=account_id,
                peer_id=peer_id,
                agent_id=agent_id,
                dm_scope=dm_scope,
            )

        # 运行 agent (简化版本，实际应调用 AgentLoop)
        # 这里返回一个占位符，实际实现需要集成 AgentLoop
        reply = await self._run_agent(agent_id or "main", session_key, text)

        return {
            "agent_id": agent_id,
            "session_key": session_key,
            "reply": reply,
        }

    async def _run_agent(self, agent_id: str, session_key: str, text: str) -> str:
        """
        运行 agent 处理消息。

        Args:
            agent_id: agent ID
            session_key: 会话键
            text: 用户输入

        Returns:
            agent 回复
        """
        # TODO: 集成 AgentLoop
        # 这里是一个简化版本，实际应该调用 AgentLoop
        agent = self._manager.get_agent(agent_id)
        if not agent:
            return f"Error: agent '{agent_id}' not found"

        # 返回占位符回复
        return f"[{agent.name}] Received: {text}"

    async def _method_bindings_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 bindings.set 方法。

        Args:
            params: 方法参数

        Returns:
            操作结果
        """
        binding = Binding(
            agent_id=normalize_agent_id(params.get("agent_id", "")),
            tier=int(params.get("tier", 5)),
            match_key=params.get("match_key", "default"),
            match_value=params.get("match_value", "*"),
            priority=int(params.get("priority", 0)),
        )
        self._bindings.add(binding)
        return {"ok": True, "binding": binding.display()}

    async def _method_bindings_list(self, params: Dict[str, Any]) -> list:
        """
        处理 bindings.list 方法。

        Args:
            params: 方法参数

        Returns:
            绑定列表
        """
        return [
            {
                "agent_id": b.agent_id,
                "tier": b.tier,
                "match_key": b.match_key,
                "match_value": b.match_value,
                "priority": b.priority,
            }
            for b in self._bindings.list_all()
        ]

    async def _method_sessions_list(self, params: Dict[str, Any]) -> Dict[str, int]:
        """
        处理 sessions.list 方法。

        Args:
            params: 方法参数

        Returns:
            会话键到消息数量的映射
        """
        agent_id = params.get("agent_id", "")
        return self._manager.list_sessions(agent_id)

    async def _method_agents_list(self, params: Dict[str, Any]) -> list:
        """
        处理 agents.list 方法。

        Args:
            params: 方法参数

        Returns:
            agent 配置列表
        """
        return [
            {
                "id": a.id,
                "name": a.name,
                "model": a.effective_model,
                "dm_scope": a.dm_scope,
                "personality": a.personality,
            }
            for a in self._manager.list_agents()
        ]

    async def _method_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 status 方法。

        Args:
            params: 方法参数

        Returns:
            网关状态信息
        """
        return {
            "running": self._running,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "connected_clients": len(self._clients),
            "agent_count": len(self._manager.list_agents()),
            "binding_count": len(self._bindings.list_all()),
        }


__all__ = [
    "GatewayServer",
]
