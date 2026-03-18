# s05: 网关与路由

> 一张绑定表将 (channel, peer) 映射到 agent_id. 最具体的匹配优先.

## 概述

本章节实现了多 agent 路由系统和 WebSocket 网关，支持:

- **五层路由解析**: 从最具体到最通用进行匹配
- **多 Agent 管理**: 每个 agent 有独立的配置和性格
- **会话隔离**: 通过 `dm_scope` 控制会话隔离粒度
- **WebSocket 网关**: 支持 JSON-RPC 2.0 协议的远程访问

## 架构

```
    Inbound Message (channel, account_id, peer_id, text)
           |
    +------v------+     +----------+
    |   Gateway    | <-- | WS/REPL  |  JSON-RPC 2.0
    +------+------+     +----------+
           |
    +------v------+
    | BindingTable |  5-tier resolution:
    +------+------+    T1: peer_id     (most specific)
           |           T2: guild_id
           |           T3: account_id
           |           T4: channel
           |           T5: default     (least specific)
           |
     (agent_id, binding)
           |
    +------v---------+
    | build_session_key() |  dm_scope controls isolation
    +------+---------+
           |
    +------v------+
    | AgentManager |  per-agent config / personality / sessions
    +------+------+
           |
        LLM API
```

## 核心组件

### 1. BindingTable - 路由绑定表

```python
from coder.components.gateway import BindingTable, Binding

bt = BindingTable()

# 添加绑定 (按优先级排序)
bt.add(Binding(agent_id="luna", tier=5, match_key="default", match_value="*"))
bt.add(Binding(agent_id="sage", tier=4, match_key="channel", match_value="telegram"))
bt.add(Binding(agent_id="sage", tier=1, match_key="peer_id",
               match_value="discord:admin-001", priority=10))

# 解析路由
agent_id, binding = bt.resolve(channel="telegram", peer_id="user2")
# agent_id = "sage"
```

### 2. AgentManager - 多 Agent 管理

```python
from coder.components.gateway import AgentManager, AgentConfig

mgr = AgentManager()

# 注册 agent
mgr.register(AgentConfig(
    id="luna",
    name="Luna",
    personality="warm, curious, and encouraging. You love asking follow-up questions.",
    dm_scope="per-peer",  # 会话隔离粒度
))

mgr.register(AgentConfig(
    id="sage",
    name="Sage",
    personality="direct, analytical, and concise. You prefer facts over opinions.",
    model="claude-opus-4-20250514",  # 可选：覆盖默认模型
))

# 获取 agent
agent = mgr.get_agent("luna")
print(agent.system_prompt())
# "You are Luna. Your personality: warm, curious, and encouraging..."
```

### 3. 会话键构建

```python
from coder.components.channels.schema import build_session_key

# dm_scope = "per-peer" (默认)
key = build_session_key(
    channel="telegram",
    account_id="bot001",
    peer_id="user123",
    agent_id="luna",
    dm_scope="per-peer"
)
# "agent:luna:direct:user123"

# dm_scope = "per-channel-peer"
key = build_session_key(..., dm_scope="per-channel-peer")
# "agent:luna:telegram:direct:user123"

# dm_scope = "per-account-channel-peer"
key = build_session_key(..., dm_scope="per-account-channel-peer")
# "agent:luna:telegram:bot001:direct:user123"

# dm_scope = "main"
key = build_session_key(..., dm_scope="main")
# "agent:luna:main"
```

### 4. GatewayServer - WebSocket 网关

```python
from coder.components.gateway import GatewayServer, AgentManager, BindingTable
import asyncio

mgr = AgentManager()
bt = BindingTable()

# 配置绑定...

gw = GatewayServer(mgr, bt, host="localhost", port=8765)
await gw.start()
```

**JSON-RPC 2.0 方法**:

| 方法 | 描述 | 参数 |
|------|------|------|
| `send` | 发送消息 | `text`, `channel`, `peer_id`, `agent_id?` |
| `bindings.set` | 设置绑定 | `agent_id`, `tier`, `match_key`, `match_value`, `priority?` |
| `bindings.list` | 列出绑定 | - |
| `sessions.list` | 列出会话 | `agent_id?` |
| `agents.list` | 列出 agent | - |
| `status` | 网关状态 | - |

**示例请求**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "send",
  "params": {
    "text": "Hello!",
    "channel": "websocket",
    "peer_id": "user1"
  }
}
```

**示例响应**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "agent_id": "luna",
    "session_key": "agent:luna:direct:user1",
    "reply": "Hello! How can I help you today?"
  }
}
```

## 路由层级

| Tier | Match Key | 说明 | 示例 |
|------|-----------|------|------|
| 1 | peer_id | 特定用户 | `discord:admin-001` 或 `user123` |
| 2 | guild_id | 服务器级别 | `guild-abc` |
| 3 | account_id | Bot 账号 | `bot-001` |
| 4 | channel | 通道类型 | `telegram`, `discord` |
| 5 | default | 默认兜底 | `*` |

**匹配优先级**:
1. 先按 tier 排序 (1-5)
2. 同 tier 内按 priority 降序

## 会话隔离 (dm_scope)

| dm_scope | Key 格式 | 效果 |
|----------|----------|------|
| `main` | `agent:{id}:main` | 所有人共享一个会话 |
| `per-peer` | `agent:{id}:direct:{peer}` | 每个用户隔离 |
| `per-channel-peer` | `agent:{id}:{ch}:direct:{peer}` | 每个平台的不同会话 |
| `per-account-channel-peer` | `agent:{id}:{ch}:{acc}:direct:{peer}` | 最大隔离度 |

## 配置

### settings.py

```python
class Settings(BaseSettings):
    # 网关配置 (s05)
    gateway_enabled: bool = False
    gateway_host: str = "localhost"
    gateway_port: int = 8765
    agents_base_dir: str = "workspace/.agents"
    max_concurrent_agents: int = 4
```

### .env

```bash
# 网关配置 (s05)
GATEWAY_ENABLED=False
GATEWAY_HOST=localhost
GATEWAY_PORT=8765
AGENTS_BASE_DIR=workspace/.agents
MAX_CONCURRENT_AGENTS=4
```

## 完整示例

```python
from coder.components.gateway import (
    AgentManager,
    AgentConfig,
    BindingTable,
    Binding,
    GatewayServer,
    run_async,
)
from coder.components.channels.schema import build_session_key

# 1. 创建 agent 管理器
mgr = AgentManager()

# 2. 注册多个 agent
mgr.register(AgentConfig(
    id="luna",
    name="Luna",
    personality="warm, curious, and encouraging.",
    dm_scope="per-peer",
))

mgr.register(AgentConfig(
    id="sage",
    name="Sage",
    personality="direct, analytical, and concise.",
    dm_scope="per-peer",
))

# 3. 创建绑定表
bt = BindingTable()
bt.add(Binding(agent_id="luna", tier=5, match_key="default", match_value="*"))
bt.add(Binding(agent_id="sage", tier=4, match_key="channel", match_value="telegram"))
bt.add(Binding(agent_id="sage", tier=1, match_key="peer_id",
               match_value="discord:admin-001", priority=10))

# 4. 测试路由
def test_route(channel: str, peer_id: str):
    agent_id, binding = bt.resolve(channel=channel, peer_id=peer_id)
    agent = mgr.get_agent(agent_id or "main")
    session_key = build_session_key(
        channel=channel,
        account_id="",
        peer_id=peer_id,
        agent_id=agent_id or "main",
        dm_scope=agent.dm_scope if agent else "per-peer",
    )
    print(f"  {channel}/{peer_id} -> {agent_id} | {session_key}")

test_route("cli", "user1")        # -> luna
test_route("telegram", "user2")   # -> sage
test_route("discord", "admin-001") # -> sage (tier 1 match)

# 5. 启动网关 (可选)
async def start_gateway():
    gw = GatewayServer(mgr, bt)
    await gw.start()
    print("Gateway running on ws://localhost:8765")

# run_async(start_gateway())
```

## 文件结构

```
coder/components/gateway/
├── __init__.py          # 组件导出
├── routing.py           # BindingTable + Binding
├── agent_manager.py     # AgentConfig + AgentManager
├── server.py            # GatewayServer
└── event_loop.py        # 共享事件循环管理
```

## 与 s04 的集成

s05 的路由系统与 s04 的通道系统无缝集成:

```python
from coder.components.channels import ChannelManager, CLIChannel
from coder.components.gateway import AgentManager, BindingTable

# 通道管理器接收消息
ch_mgr = ChannelManager()
ch_mgr.register(CLIChannel())

# 路由系统决定目标 agent
bt = BindingTable()
mgr = AgentManager()

# 处理消息
for channel in ch_mgr.channels.values():
    while msg := channel.receive():
        agent_id, _ = bt.resolve(
            channel=msg.channel,
            account_id=msg.account_id,
            peer_id=msg.peer_id,
        )
        agent = mgr.get_agent(agent_id or "main")
        # ... 调用 agent 处理消息
```

## 下一步

- **s06 智能层**: 8层提示词组装，MemoryStore
- **s07 心跳与 Cron**: Lane 互斥，CronService
- **s08 消息投递**: DeliveryQueue 持久化
