# 【Your-project-name】

【Your-project-name】，

## ✨ 特色功能

### 已实现功能

### 规划中功能

### 架构特色

- 🏗️ **模块化设计**: FastAPI 应用与扩展组件完全分离，遵循软件工程最佳实践
- 🔧 **类型安全配置**: 基于 Pydantic Settings 的环境配置管理
- ⚙️ **离线文档**: 自托管的 Swagger UI 和 ReDoc，支持多端点文档
- 🚀 **开发工具链**: 完整的代码格式化、检查和提交工具
- 🧪 **测试框架**: 基于 Pytest 的测试环境

## 项目结构

```
fastapi-scaffold/
├── coder/                           # 核心应用模块
│   ├── common/                      # 公共工具模块
│   │   ├── exception_handler.py     # 异常处理器
│   │   ├── logger.py                # 日志配置
│   │   ├── path.py                  # 路径管理
│   │   ├── time.py                  # 时间工具
│   │   └── ...                      # 其他工具
│   ├── middleware/                  # 中间件
│   ├── utils/                       # 工具函数
│   ├── application.py               # FastAPI 应用配置
│   ├── settings.py                  # 配置管理
│   └── run.py                       # 服务启动器
├── extended/                        # 框架扩展
│   └── fastapi/                     # FastAPI 扩展
│       └── responses.py             # 自定义响应类
├── scripts/                         # 开发脚本
│   └── dev/                         # 开发工具
│       ├── setup_dev.py             # 环境设置
│       ├── check_dev.py             # 环境检查
│       └── format_code.py           # 代码格式化
├── static/                          # 静态文件
│   ├── assets/                      # 静态资源
│   └── swagger/                     # Swagger UI 资源
├── templates/                       # Jinja2 模板
├── tests/                           # 测试文件
│   └── studies/                     # 研究和测试
├── logs/                            # 日志文件
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
