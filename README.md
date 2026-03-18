# your-claw

your-claw 是一个模块化的 AI Agent 框架，基于 FastAPI 脚手架构建，将教程代码工程化实现。

## ✨ 特色功能

### 已实现功能

- ✅ **Agent 循环 (s01)**: while True + stop_reason 核心循环，messages[] 状态管理
- ✅ **工具使用 (s02)**: TOOLS schema + TOOL_HANDLERS 分发，内层工具调用循环
- ✅ **模块化组件**: CLI、提示词、Agent 循环、工具独立封装
- ✅ **类型安全配置**: Pydantic Settings 配置管理

### 规划中功能
- 🔲 **会话与上下文保护 (s03)**: JSONL 持久化，ContextGuard
- 🔲 **通道 (s04)**: CLI/Telegram/飞书实现
- 🔲 **网关与路由 (s05)**: 多 agent，WebSocket 网关
- 🔲 **智能层 (s06)**: 8层提示词组装，MemoryStore
- 🔲 **心跳与 Cron (s07)**: Lane 互斥，CronService
- 🔲 **消息投递 (s08)**: DeliveryQueue 持久化
- 🔲 **弹性 (s09)**: 重试洋葱，key轮换
- 🔲 **并发 (s10)**: LaneQueue，CommandQueue

### 架构特色

- 🏗️ **模块化设计**: FastAPI 应用与扩展组件完全分离，遵循软件工程最佳实践
- 🔧 **类型安全配置**: 基于 Pydantic Settings 的环境配置管理
- ⚙️ **离线文档**: 自托管的 Swagger UI 和 ReDoc，支持多端点文档
- 🚀 **开发工具链**: 完整的代码格式化、检查和提交工具
- 🧪 **测试框架**: 基于 Pytest 的测试环境

## 项目结构

```
your-claw/
├── coder/                           # 核心应用模块
│   ├── common/                      # 公共工具模块
│   │   ├── exception_handler.py     # 异常处理器
│   │   ├── logger.py                # 日志配置
│   │   ├── path.py                  # 路径管理
│   │   └── time.py                  # 时间工具
│   ├── components/                  # Agent 组件
│   │   ├── agent/                   # Agent 循环
│   │   │   ├── __init__.py
│   │   │   └── loop.py              # AgentLoop 类
│   │   ├── cli/                     # CLI 工具
│   │   │   └── __init__.py          # 颜色输出、输入提示
│   │   ├── prompts/                 # 提示词管理
│   │   │   └── __init__.py          # 系统提示词
│   │   ├── tools/                   # 工具组件
│   │   │   ├── __init__.py          # 工具导出
│   │   │   ├── schema.py            # TOOLS schema 定义
│   │   │   └── handlers.py          # 工具处理器
│   │   └── channels/                # 通道实现 (s04+)
│   ├── middleware/                  # 中间件
│   ├── controllers/                 # API 控制器
│   ├── application.py               # FastAPI 应用配置
│   ├── settings.py                  # 配置管理
│   └── run.py                       # 服务启动器
├── docs/
│   ├── scaffold/                    # 脚手架文档
│   ├── your-claw-guide/             # 教程文档
│   └── your-claw-project/           # 工程化文档
├── extended/                        # 框架扩展
├── scripts/                         # 开发脚本
├── static/                          # 静态文件
├── tests/                           # 测试文件
├── manage.py                        # 管理脚本
└── pyproject.toml                   # 项目配置和依赖
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

创建 `.env` 文件进行环境配置：

```env
# 服务配置
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO

# API文档配置
API_DOCS_ENABLED=true

# CORS配置
CORS_ALLOWED_ORIGIN_PATTERNS=["*"]

# Agent 配置
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514
API_BASE_URL=
MAX_TOKENS=8096
```

### 运行 Agent

```python
from coder.components.agent import AgentLoop, run_agent_loop
from coder.components.tools import TOOLS

# 方式1: 快速启动（无工具）
run_agent_loop()

# 方式2: 快速启动（带工具）
run_agent_loop(tools=TOOLS)

# 方式3: 自定义配置
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    system_prompt="You are a code reviewer.",
    tools=TOOLS,  # 可选：启用工具支持
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

### 应用架构

项目采用**模块化架构设计**，遵循 FastAPI 最佳实践：

- **应用层**: FastAPI 应用配置、中间件和路由管理
- **业务层**: 控制器、服务和业务逻辑实现
- **工具层**: 公共工具、扩展和配置管理

### 添加新功能

#### 1. 创建新的路由控制器

```python
# coder/controllers/my_controller.py
from fastapi import APIRouter
from extended.fastapi.responses import ORJSONResponse

router = APIRouter(prefix="/api/v1/my", tags=["我的功能"])

@router.get("/")
async def get_my_data() -> ORJSONResponse:
    return ORJSONResponse({"message": "Hello World"})
```

#### 2. 注册路由到应用

```python
# coder/application.py
from coder.controllers.my_controller import router as my_router

app.include_router(my_router)
```

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

### 中间件开发

```python
# coder/middleware/my_middleware.py
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class MyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 请求预处理
        response = await call_next(request)
        # 响应后处理
        return response
```

## 技术栈

- **Web 框架**: FastAPI 0.115.12 with standard extras
- **LLM 调用**: LiteLLM (支持多种模型)
- **配置管理**: Pydantic Settings 2.8.1
- **依赖管理**: UV
- **类型检查**: Pyright 1.1.391
- **代码质量**: Ruff 0.11.2, Pre-commit 4.2.0
- **测试框架**: Pytest 8.3.5
- **服务器**: Uvicorn 0.34.3

## 开发命令

```bash
# 开发环境设置
uv run setup-dev      # 设置开发环境和 pre-commit hooks
uv run check-dev      # 检查开发环境状态
uv run format-code    # 格式化和检查代码

# 运行应用
python manage.py runserver  # 启动开发服务器
uv run runserver           # 或使用 UV 脚本启动

# 代码质量
uv run pre-commit run --all-files  # 手动运行所有检查
uv run cz commit                   # 规范化提交
```

## 常见问题

### 开发环境问题

**UV 未安装**

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Pre-commit hooks 未生效**

```bash
# 重新安装 hooks
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 手动运行检查
uv run pre-commit run --all-files
```

### 服务问题

**端口被占用**

```bash
# 检查端口占用
lsof -i :8000

# 修改端口配置
echo "PORT=8001" >> .env
```

**应用启动失败**

```bash
# 检查日志文件
tail -f logs/app.log

# 检查配置
uv run check-dev
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
