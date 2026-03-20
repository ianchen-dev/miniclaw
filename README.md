# Miniclaw

Miniclaw : 你的AI助手

- Miniclaw 是一款受[Openclaw](https://github.com/openclaw/openclaw)启发的超轻量级个人 AI 助手
- 用 2% 的代码实现openclaw核心agent功能
- 适合个人快速学习[Openclaw](https://github.com/openclaw/openclaw)的核心功能

## ✨ 特色功能

### 已实现功能

- ✅ **Agent 循环 (s01)**: while True + stop_reason 核心循环，messages[] 状态管理
- ✅ **工具使用 (s02)**: TOOLS schema + TOOL_HANDLERS 分发，内层工具调用循环
- ✅ **会话与上下文保护 (s03)**: JSONL 持久化，SessionStore，ContextGuard 3阶段溢出重试
- ✅ **通道 (s04)**: InboundMessage 统一格式，Channel ABC，CLI/Telegram/飞书，huo实现
- ✅ **网关与路由 (s05)**: BindingTable 5层路由，AgentManager 多agent，WebSocket 网关
- ✅ **智能层 (s06)**: 8层提示词组装，BootstrapLoader，MemoryStore TF-IDF+MMR搜索
- ✅ **心跳与 Cron (s07)**: Lane 互斥，HeartbeatRunner，CronService 3种调度
- ✅ **消息投递 (s08)**: DeliveryQueue 磁盘持久化，原子写入，指数退避重试
- ✅ **弹性 (s09)**: 3层重试洋葱，AuthProfile key轮换，备选模型链
- ✅ **并发 (s10)**: LaneQueue 命名lane，CommandQueue 调度器，Generation 追踪
- ✅ **模块化组件**: CLI、提示词、Agent 循环、工具、会话、通道、网关、智能层、调度器、投递、弹性、并发独立封装
- ✅ **类型安全配置**: Pydantic Settings 配置管理

## 项目结构

```
Miniclaw/
├── coder/                           # 核心应用模块
│    ├── agent/                   # Agent 循环
│    │   └── loop.py              # AgentLoop 类
│    ├── cli/                     # CLI 工具
│    ├── prompts/                 # 提示词管理
│    ├── tools/                   # 工具组件
│    │   ├── schema.py            # TOOLS schema 定义
│    │   └── handlers.py          # 工具处理器
│    ├── session/                 # 会话组件 (s03)
│    │   ├── store.py             # SessionStore - JSONL 持久化
│    │   └── guard.py             # ContextGuard - 上下文保护
│    └── channels/                # 通道实现 (s04+)
│    └── gateway/                 # 网关与路由 (s05)
│       ├── routing.py           # BindingTable 五层路由
│       ├── agent_manager.py     # AgentManager 多agent管理
│       ├── server.py            # GatewayServer WebSocket网关
│       └── event_loop.py        # 共享事件循环
│    └── intelligence/            # 智能层 (s06)
│        ├── bootstrap.py         # BootstrapLoader 文件加载
│        ├── skills.py            # SkillsManager 技能发现
│        ├── memory.py            # MemoryStore 记忆存储和搜索
│        └── prompt_builder.py    # 8 层提示词组装
│    └── scheduler/               # 调度器 (s07)
│        ├── heartbeat.py         # HeartbeatRunner 心跳运行器
│        └── cron.py              # CronService 定时任务服务
│    └── delivery/                # 消息投递 (s08)
│        ├── queue.py             # DeliveryQueue 持久化队列
│        └── runner.py            # DeliveryRunner 后台投递线程
│    └── resilience/              # 弹性组件 (s09)
│        ├── failure.py           # FailoverReason 失败分类
│        ├── profile.py           # AuthProfile, ProfileManager
│        └── runner.py            # ResilienceRunner 三层重试
│    └── concurrency/             # 并发组件 (s10)
│        └── queue.py             # LaneQueue, CommandQueue
│    ├── settings.py              # 配置管理
```

## 快速开始

### 环境要求

- Python 3.10-3.12
- UV (推荐) 或 pip

### 安装步骤

#### 1. 克隆项目

```bash
git clone <repository-url>
cd fastapi-scaffold
```

#### 2. 安装依赖

```bash
# 使用UV创建虚拟环境
# 激活虚拟环境
# 安装依赖和设置开发环境
uv run setup-dev
```

#### 3. 配置环境变量

见 .env.example 文件，根据需要创建并配置 `.env` 文件。

#### 4. 启动CLI

```bash
uv run miniclaw
```

### 自定义运行 Agent

```python
from coder.agent import AgentLoop, run_agent_loop
from coder.tools import TOOLS

# 方式1: 快速启动（无工具）
run_agent_loop()

# 方式2: 快速启动（带工具）
run_agent_loop(tools=TOOLS)

# 方式3: 快速启动（带工具和会话持久化）
run_agent_loop(tools=TOOLS, enable_session=True)

# 方式4: 快速启动（带智能层）
run_agent_loop(tools=TOOLS, enable_intelligence=True)

# 方式5: 自定义配置
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    system_prompt="You ae a code reviewer.",
    tools=TOOLS,  # 可选：启用工具支持
    enable_session=True,  # 可选：启用会话持久化 (s03)
    enable_intelligence=True,  # 可选：启用智能层 (s06)
    agent_id="my-agent",  # 可选：Agent 标识符
)
loop.run()
```

## 开发命令

```bash
# 开发环境设置
uv run setup-dev      # 设置开发环境和 pre-commit hooks
uv run check-dev      # 检查开发环境状态
uv run format-code    # 格式化和检查代码

# 代码质量
uv run pre-commit run --all-files  # 手动运行所有检查
uv run cz commit                   # 规范化提交
```

## 常见问题

### 开发环境问题

**Pre-commit hooks 未生效**

```bash
# 重新安装 hooks
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 手动运行检查
uv run pre-commit run --all-files
```

### 开发问题

**代码格式化失败**

```bash
# 检查 Ruff 配置
uv run ruff check coder/

# 强制格式化
uv run format-code --targets coder/ extended/ manage.py
```

**类型检查错误**

```bash
# 运行 Pyright 检查
uv run pyright coder/

# 检查配置文件
cat pyproject.toml | grep -A 20 "\[tool.pyright\]"
```
