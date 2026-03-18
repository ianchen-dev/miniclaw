import contextlib
import logging
import os
import time
from datetime import datetime

from coder.common.path import LOG_FOLDER
from coder.common.time import ChinaTimeZone
from coder.settings import settings


# 确保日志目录存在
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER, exist_ok=True)

# 记录应用启动开始时间
start_time = time.time()

_logger = logging.getLogger(__name__)


_logger.info(
    f"\n🚀 Lowcode-Coder-Engine 应用开始启动... ({datetime.now(tz=ChinaTimeZone).strftime('%Y-%m-%d %H:%M:%S')})"
)

from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, List, Union

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.routing import BaseRoute

from coder.common.exception_handler import register_exception_handlers
from coder.common.path import ROOT_DIR
from coder.middleware import make_middlewares
from extended.fastapi.responses import ORJSONResponse


APP_NAME = "Lowcode-Coder-Engine"


def __remove_route(url: str, routes: List[Union[APIRoute, BaseRoute]]) -> None:
    """
    移除路由
    """
    idx = None
    for i, r in enumerate(routes):
        if isinstance(r, APIRoute) and r.path.lower() == url.lower():
            idx = i
            break
    if isinstance(idx, int):
        routes.pop(idx)


def __make_fastapi_offline(
    fast_app: FastAPI,
    static_dir: Path,
    static_url: str,
    doc_endpoints: List[Dict[str, Any]],
) -> None:
    """配置FastAPI应用使用离线文档，支持多个文档端点

    该函数允许FastAPI应用使用本地静态文件提供Swagger和ReDoc文档，
    而不依赖CDN资源。同时支持为不同API路径配置独立的文档页面。

    Args:
        fast_app (FastAPI): FastAPI应用实例
        static_dir (Path, optional): 静态文件目录路径. 默认为ROOT_DIR/"static".
        static_url (str, optional): 静态文件URL前缀. 默认为"/static-offline-docs".
        doc_endpoints (list, optional): 文档端点配置列表. 每个配置项包含:
            - pattern: 路由匹配的正则表达式
            - title: 文档标题
            - docs_url: Swagger UI的URL路径
            - redoc_url: ReDoc的URL路径
            - enabled: 是否启用该文档端点
    """

    # 如果全局禁用了OpenAPI，则直接返回，不创建任何文档端点
    if fast_app.openapi_url is None:
        return

    import re

    from fastapi.openapi.docs import (
        get_redoc_html,
        get_swagger_ui_html,
    )
    from fastapi.openapi.utils import get_openapi
    from fastapi.staticfiles import StaticFiles

    # 挂载静态文件
    fast_app.mount(
        static_url,
        StaticFiles(directory=Path(static_dir / "swagger").as_posix()),
        name="static-offline-docs",
    )

    for endpoint in doc_endpoints:
        # 检查该文档端点是否启用
        if not endpoint.get("enabled", True):
            continue

        pattern_str = endpoint.get("pattern", None)  # 默认匹配所有路由
        title_suffix = endpoint.get("title", "API文档")
        docs_url = endpoint.get("docs_url", None)
        redoc_url = endpoint.get("redoc_url", None)

        # 生成 OpenAPI URL
        openapi_url = f"/openapi-{title_suffix.replace(' ', '-').lower()}.json"

        # 自定义 OpenAPI 生成
        @fast_app.get(
            path=openapi_url,
            include_in_schema=False,
        )
        async def get_custom_openapi(
            pattern_str=pattern_str,
            title_suffix=title_suffix,
        ):
            # 编译正则表达式
            pattern = re.compile(pattern_str)

            # 创建空文档作为默认情况
            empty_openapi = get_openapi(
                title=f"{APP_NAME} - {title_suffix}",
                version="0.1.0",
                routes=[],
            )

            # 其他文档，使用正则匹配
            routes = [route for route in fast_app.routes if hasattr(route, "path") and pattern.match(str(route.path))]

            # 如果没有匹配的路由，返回空文档
            if not routes:
                return empty_openapi

            return get_openapi(
                title=f"{APP_NAME} - {title_suffix}",
                version="0.1.0",
                routes=routes,
            )

        # 添加 Swagger UI
        if docs_url:
            __remove_route(
                url=docs_url,
                routes=fast_app.routes,
            )

            @fast_app.get(
                path=docs_url,
                include_in_schema=False,
            )
            async def custom_swagger_ui_html(
                request: Request,
                openapi_url=openapi_url,
                title_suffix=title_suffix,
            ):
                root = request.scope.get("root_path")
                return get_swagger_ui_html(
                    openapi_url=f"{root}{openapi_url}",
                    title=f"{APP_NAME} - {title_suffix} - Swagger UI",
                    swagger_js_url="/static-offline-docs/swagger-ui-bundle.js",
                    swagger_css_url="/static-offline-docs/swagger-ui.css",
                    swagger_favicon_url="/static-offline-docs/favicon.png",
                )

        # 添加 ReDoc
        if redoc_url:
            __remove_route(
                url=redoc_url,
                routes=fast_app.routes,
            )

            @fast_app.get(
                path=redoc_url,
                include_in_schema=False,
            )
            async def custom_redoc_html(
                request: Request,
                openapi_url=openapi_url,
                title_suffix=title_suffix,
            ):
                root = request.scope.get("root_path")
                return get_redoc_html(
                    openapi_url=f"{root}{openapi_url}",
                    title=f"{APP_NAME} - {title_suffix} - ReDoc",
                    redoc_js_url="/static-offline-docs/redoc.standalone.js",
                    with_google_fonts=False,
                    redoc_favicon_url="/static-offline-docs/favicon.png",
                )


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动事件

    # 计算并打印启动耗时
    completion_time = datetime.now(tz=ChinaTimeZone)
    end_time = completion_time.timestamp()
    startup_duration = end_time - start_time

    print(
        "\n"
        + "=" * 60
        + "\n"
        + "🎉 Lowcode-Coder-Engine 应用启动完成！"
        + "\n"
        + f"📊 启动耗时: {startup_duration:.3f} 秒"
        + "\n"
        + f"⏰ 完成时间: {completion_time.strftime('%Y-%m-%d %H:%M:%S')}"
        + "\n"
        + f"🔗 访问地址: http://127.0.0.1:{settings.port}\n"
        + f"🔗 API文档: http://127.0.0.1:{settings.port}/docs\n"
        + "\n"
        + "=" * 60
        + "\n",
    )

    yield
    # 关闭事件
    _logger.info("应用正在关闭...")


__fastapi_config = {}
# 如果禁用API文档，则不生成API文档
if not settings.api_docs_enabled:
    __fastapi_config = {
        "openapi_url": None,
        "docs_url": None,
        "redoc_url": None,
    }


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
    middleware=make_middlewares(),  # 注册中间件（过滤器）
    version="0.1.0",
    **__fastapi_config,
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")

# 配置 Jinja2 模板
templates = Jinja2Templates(directory=ROOT_DIR / "templates")

# 注册异常处理器
register_exception_handlers(app)

if settings.api_docs_enabled:
    # 设置基本的openapi_url，后续可能会被自定义的openapi端点覆盖
    app.openapi_url = "/openapi.json"

    __make_fastapi_offline(
        fast_app=app,
        static_dir=ROOT_DIR / "static",
        static_url="/static-offline-docs",
        doc_endpoints=[
            {
                "enabled": True,
                "pattern": "^/api/v[0-9]+/common",
                "title": "公共API文档",
                "docs_url": "/docs",
                "redoc_url": "/redoc",
            },
        ],
    )


@app.get(
    path="/actuator/health",
    summary="健康检测",
    tags=["内置"],
)
async def health() -> ORJSONResponse:
    """
    健康检测
    """
    return ORJSONResponse(
        status_code=HTTPStatus.OK.value,
        content={
            "status": "UP",
        },
    )


_logger.info("🚀 before api_router...")


# 加载路由
# 注意：路由注册顺序非常重要！FastAPI 会按照注册顺序进行路由匹配
# 更具体的路由应该注册在前面，更通用的路由应该注册在后面
# 这是因为 FastAPI 使用第一个匹配的路由，而不是最匹配的路由

# API 路由 - 最具体的路由，应该最先注册
# 所有 /api 开头的请求都会先尝试匹配这个路由
# 例如：/api/v1/users/, /api/v1/groups/ 等
# from coder.controllers import api_router
# 注册核心路由
from coder.controllers import api_router


app.include_router(api_router, prefix="/api")

_logger.info("🚀 after api_router...")


# app.include_router(api_router, prefix="/api")
