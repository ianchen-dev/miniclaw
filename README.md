# your-claw

your-claw 是一个模块化的 AI Agent 框架，基于 FastAPI 脚手架构建，将教程代码工程化实现。

## ✨ 特色功能

### 已实现功能

- ✅ **Agent 循环 (s01)**: while True + stop_reason 核心循环，messages[] 状态管理
- ✅ **工具使用 (s02)**: TOOLS schema + TOOL_HANDLERS 分发，内层工具调用循环
- ✅ **会话与上下文保护 (s03)**: JSONL 持久化，SessionStore，ContextGuard 3阶段溢出重试
- ✅ **通道 (s04)**: InboundMessage 统一格式，Channel ABC，CLI/Telegram/飞书实现
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
your-claw/
├── coder/                           # 核心应用模块
│    ├── agent/                   # Agent 循环
│    │   └── loop.py              # AgentLoop 类
│    ├── cli/                     # CLI 工具
│    │   └── __init__.py          # 颜色输出、输入提示
│    ├── prompts/                 # 提示词管理
│    │   └── __init__.py          # 系统提示词
│    ├── tools/                   # 工具组件
│    │   ├── __init__.py          # 工具导出
│    │   ├── schema.py            # TOOLS schema 定义
│    │   └── handlers.py          # 工具处理器
│    ├── session/                 # 会话组件 (s03)
│    │   ├── __init__.py          # 会话导出
│    │   ├── store.py             # SessionStore - JSONL 持久化
│    │   └── guard.py             # ContextGuard - 上下文保护
│    └── channels/                # 通道实现 (s04+)
│    └── gateway/                 # 网关与路由 (s05)
│       ├── __init__.py          # 网关组件导出
│       ├── routing.py           # BindingTable 五层路由
│       ├── agent_manager.py     # AgentManager 多agent管理
│       ├── server.py            # GatewayServer WebSocket网关
│       └── event_loop.py        # 共享事件循环
│    └── intelligence/            # 智能层 (s06)
│        ├── __init__.py          # 智能层组件导出
│        ├── bootstrap.py         # BootstrapLoader 文件加载
│        ├── skills.py            # SkillsManager 技能发现
│        ├── memory.py            # MemoryStore 记忆存储和搜索
│        └── prompt_builder.py    # 8 层提示词组装
│    └── scheduler/               # 调度器 (s07)
│        ├── __init__.py          # 调度器组件导出
│        ├── heartbeat.py         # HeartbeatRunner 心跳运行器
│        └── cron.py              # CronService 定时任务服务
│    └── delivery/                # 消息投递 (s08)
│        ├── __init__.py          # 投递组件导出
│        ├── queue.py             # DeliveryQueue 持久化队列
│        └── runner.py            # DeliveryRunner 后台投递线程
│    └── resilience/              # 弹性组件 (s09)
│        ├── __init__.py          # 弹性组件导出
│        ├── failure.py           # FailoverReason 失败分类
│        ├── profile.py           # AuthProfile, ProfileManager
│        └── runner.py            # ResilienceRunner 三层重试
│    └── concurrency/             # 并发组件 (s10)
│        ├── __init__.py          # 并发组件导出
│        └── queue.py             # LaneQueue, CommandQueue
│    ├── settings.py                  # 配置管理
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
uv venv --python 3.11

# 激活虚拟环境
source ./.venv/bin/activate

# 安装依赖和设置开发环境
uv run setup-dev
```

#### 3. 启动开发服务器

```bash
# 使用管理脚本启动
python manage.py runserver

# 或者使用UV脚本
uv run runserver
```

访问 <http://127.0.0.1:8000> 查看应用。

### 配置文件

创建 `.env` 文件进行环境配置（从 `.env.example` 复制）：

```env
# ===========================================
# 日志配置
# ===========================================
# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# ===========================================
# Agent 配置 (s01)
# ===========================================
# API密钥 (必填)
API_KEY=your-api-key-here
# 模型ID (默认: claude-sonnet-4-20250514)
MODEL_ID=claude-sonnet-4-20250514
# API基础URL (可选，用于自定义端点或代理)
API_BASE_URL=
# 最大token数 (默认: 8096)
MAX_TOKENS=8096

# ===========================================
# 会话配置 (s03)
# ===========================================
# 上下文安全限制 (tokens)
CONTEXT_SAFE_LIMIT=180000
# 会话存储目录
SESSION_WORKSPACE=workspace/.sessions

# ===========================================
# 通道配置 (s04)
# ===========================================
# Telegram Bot 配置
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# TELEGRAM_ALLOWED_CHATS=12345,67890    (可选白名单，逗号分隔的聊天ID)

# 飞书/Lark 配置
# FEISHU_APP_ID=cli_xxxxx
# FEISHU_APP_SECRET=xxxxx
# FEISHU_ENCRYPT_KEY=                    (可选，事件订阅加密key)
# FEISHU_BOT_OPEN_ID=                    (可选，用于群聊@检测)
# FEISHU_IS_LARK=False                   (True 表示使用 Lark 国际版)

# ===========================================
# 网关配置 (s05)
# ===========================================
# 是否启用 WebSocket 网关
GATEWAY_ENABLED=False
# 网关监听地址
GATEWAY_HOST=localhost
# 网关监听端口
GATEWAY_PORT=8765
# Agent 配置目录
AGENTS_BASE_DIR=workspace/.agents
# 最大并发 agent 数量
MAX_CONCURRENT_AGENTS=4

# ===========================================
# 智能层配置 (s06)
# ===========================================
# 工作区目录
WORKSPACE_DIR=workspace
# 单个 Bootstrap 文件最大字符数
MAX_FILE_CHARS=20000
# Bootstrap 文件总字符数上限
MAX_TOTAL_CHARS=150000
# 最大技能数量
MAX_SKILLS=150
# 技能提示词块最大字符数
MAX_SKILLS_PROMPT=30000
# 记忆搜索默认返回数量
MEMORY_TOP_K=5
# 记忆时间衰减率
MEMORY_DECAY_RATE=0.01
# MMR 重排序的 lambda 参数
MMR_LAMBDA=0.7

# ===========================================
# 心跳与 Cron 配置 (s07)
# ===========================================
# 心跳间隔 (秒)
HEARTBEAT_INTERVAL=1800
# 心跳活跃开始时间 (小时, 0-23)
HEARTBEAT_ACTIVE_START=9
# 心跳活跃结束时间 (小时, 0-23)
HEARTBEAT_ACTIVE_END=22
# 心跳输出队列最大大小
HEARTBEAT_MAX_QUEUE_SIZE=10
# Cron 任务连续错误自动禁用阈值
CRON_AUTO_DISABLE_THRESHOLD=5

# ===========================================
# 弹性配置 (s09)
# ===========================================
# 备选模型链，逗号分隔 (当主模型失败时尝试)
# RESILIENCE_FALLBACK_MODELS=claude-haiku-4-20250514,gpt-4o-mini
RESILIENCE_FALLBACK_MODELS=
# 最大溢出压缩尝试次数
RESILIENCE_MAX_OVERFLOW_COMPACTION=3
```

### 运行 Agent

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

### 健康检查

应用启动后，可以通过健康检查端点验证服务状态：

```bash
curl http://127.0.0.1:8000/actuator/health
```

**响应示例：**

```json
{
  "status": "UP"
}
```

## 开发指南

### 配置管理

在 `coder/settings.py` 中添加新配置：

```python
class Settings(BaseSettings):
    # 新增配置项
    my_feature_enabled: bool = False
    my_api_key: str = ""

    class Config:
        env_file = ".env"
```

## 技术栈

- **LLM 调用**: LiteLLM (支持多种模型)
- **依赖管理**: UV
- **类型检查**: Pyright 1.1.391
- **代码质量**: Ruff 0.11.2, Pre-commit 4.2.0
- **测试框架**: Pytest 8.3.5

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
