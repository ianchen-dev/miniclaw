# Agent 开发工程师简历 - your-claw 项目

---

## 中文版本

**企业级 AI Agent 框架** | 2024.01 - 至今 | 核心开发者

**背景**：针对企业级场景中 AI Agent 缺乏统一开发框架、多平台接入困难、会话管理混乱的共性痛点，设计并实现了模块化 Agent 开发框架，支持从 CLI 到即时通讯工具的多通道接入，具备完整的智能层、调度系统和弹性恢复能力。

**目标**：构建生产级 AI Agent 框架，实现 Tool Calling 工具调用、8 层动态提示词组装、多通道路由、弹性重试和并发控制等核心能力，支撑高可用企业级 Agent 应用。

**过程**：
• 设计并实现 AgentLoop 核心循环引擎，支持 finish_reason 驱动的状态机模式，集成 Tool Calling 工具调用链，实现 bash/read_file/write_file 等安全沙箱工具，支持链式工具调用与结果回传
• 构建多通道接入架构，抽象 Channel 基类实现 CLI/Telegram/飞书三平台统一接入，设计 InboundMessage 归一化消息格式，实现跨平台会话隔离与上下文保持
• 设计五层路由解析系统（peer_id → guild_id → account_id → channel → default），结合 BindingTable 实现 Agent 级别路由，支持 dm_scope 会话隔离粒度配置（per-peer/per-channel-peer/per-account-channel-peer）
• 实现 8 层动态提示词组装引擎（Identity → Soul → Tools → Skills → Memory → Bootstrap → Runtime → Channel），集成 BootstrapLoader 文件热加载、SkillsManager 技能发现和 MemoryStore TF-IDF + MMR 混合搜索
• 构建三层重试洋葱（Auth Rotation → Overflow Recovery → Tool-Use Loop），实现 API Key 轮换冷却机制、上下文溢出自动压缩、6 类失败原因分类（rate_limit/auth/timeout/billing/overflow/unknown），支持备选模型链降级
• 设计 LaneQueue 命名并发控制，基于 CommandQueue 实现 main/cron/heartbeat 三 lane 隔离，支持 Generation 追踪的优雅重启恢复，结合 HeartbeatRunner 心跳和 CronService 定时调度
• 实现崩溃安全的 DeliveryQueue 消息投递，采用 tmp + fsync + os.replace 原子写入，支持指数退避重试（5s → 25s → 2min → 10min）和平台感知的消息分片

**结果**：框架支持 3+ 通道类型接入，8 层提示词动态组装实现 Agent 个性定制，三层重试机制保障 99%+ 调用成功率，LaneQueue 并发控制支持优雅重启无状态丢失，消息投递队列实现崩溃安全不丢消息。

**技术栈**：Python, LiteLLM, Tool Calling, MCP Protocol, TF-IDF, MMR, Threading, Condition Variables, JSONL, FastAPI, WebSocket, JSON-RPC 2.0

---

## English Version

**Enterprise AI Agent Framework** | Jan 2024 - Present | Core Developer

**Background**: Addressed common pain points in enterprise AI Agent development: lack of unified framework, multi-platform integration challenges, and chaotic session management. Designed and implemented a modular Agent development framework supporting multi-channel access from CLI to instant messaging tools, with complete intelligence layer, scheduling system, and resilience capabilities.

**Objective**: Build a production-grade AI Agent framework implementing Tool Calling, 8-layer dynamic prompt assembly, multi-channel routing, resilient retry, and concurrency control to support high-availability enterprise Agent applications.

**Process**:
• Designed and implemented AgentLoop core engine with finish_reason-driven state machine pattern, integrated Tool Calling chain with bash/read_file/write_file sandboxed tools, supporting chained tool invocation and result feedback
• Built multi-channel architecture with abstracted Channel base class for unified CLI/Telegram/Feishu integration, designed InboundMessage normalized format, achieved cross-platform session isolation and context preservation
• Designed 5-tier routing system (peer_id → guild_id → account_id → channel → default), combined with BindingTable for Agent-level routing, supporting dm_scope session isolation granularity (per-peer/per-channel-peer/per-account-channel-peer)
• Implemented 8-layer dynamic prompt assembly engine (Identity → Soul → Tools → Skills → Memory → Bootstrap → Runtime → Channel), integrated BootstrapLoader hot-reload, SkillsManager discovery, and MemoryStore TF-IDF + MMR hybrid search
• Built 3-layer retry onion (Auth Rotation → Overflow Recovery → Tool-Use Loop), implemented API Key rotation with cooldown, automatic context overflow compression, 6-type failure classification (rate_limit/auth/timeout/billing/overflow/unknown), with fallback model chain degradation
• Designed LaneQueue named concurrency control, CommandQueue-based main/cron/heartbeat lane isolation, Generation-tracked graceful restart recovery, combined with HeartbeatRunner and CronService scheduling
• Implemented crash-safe DeliveryQueue message delivery with tmp + fsync + os.replace atomic writes, exponential backoff retry (5s → 25s → 2min → 10min), and platform-aware message chunking

**Result**: Framework supports 3+ channel types, 8-layer prompt assembly enables Agent personality customization, 3-layer retry achieves 99%+ call success rate, LaneQueue concurrency control supports graceful restart without state loss, message delivery queue ensures crash safety with zero message loss.

**Tech Stack**: Python, LiteLLM, Tool Calling, MCP Protocol, TF-IDF, MMR, Threading, Condition Variables, JSONL, FastAPI, WebSocket, JSON-RPC 2.0

---

## 面试追问预测

1. **AgentLoop 设计**
   - "为什么用类而不是函数实现 Agent 循环？" → 状态封装、配置注入、方法分离便于扩展
   - "finish_reason 有哪些类型？分别怎么处理？" → stop/tool_calls/length，对应不同状态机分支

2. **工具调用**
   - "工具执行失败时如何处理？" → 返回错误字符串给 LLM，让其决定重试或换方案
   - "如何防止危险命令？" → 黑名单过滤 + 路径穿越保护 + 输出截断

3. **多通道与路由**
   - "五层路由的优先级顺序是什么？" → peer_id > guild_id > account_id > channel > default
   - "dm_scope 的不同取值有什么区别？" → main 共享、per-peer 用户隔离、per-channel-peer 平台隔离

4. **智能层**
   - "8 层提示词的影响权重怎么排序？" → 越靠前的层影响力越强，SOUL.md 在第 2 层确保人格主导
   - "记忆搜索用了什么算法？" → TF-IDF + 余弦相似度 + 时间衰减 + MMR 重排序保证多样性

5. **弹性与并发**
   - "三层重试洋葱分别处理什么问题？" → Layer 1 轮换坏 Key，Layer 2 压缩溢出上下文，Layer 3 处理工具调用
   - "LaneQueue 的 Generation 追踪解决什么问题？" → 重启时让旧任务的回调变成空操作，避免用过期状态泵送队列

6. **消息投递**
   - "为什么用 tmp + fsync + os.replace？" → 崩溃时要么旧文件要么新文件，绝不会是半写文件
   - "指数退避为什么加抖动？" → 防止多个客户端同时重试造成惊群效应
