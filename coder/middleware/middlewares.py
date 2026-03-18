import contextvars
import logging
import time
import uuid
from typing import Any, AsyncIterable

from fastapi.responses import Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from typing_extensions import override

from coder.common.bgtask import BgTasks


_logger = logging.getLogger(__name__)

# 创建上下文变量用于存储trace_id
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


class TraceMiddleware(BaseHTTPMiddleware):
    """链路追踪中间件 - 为每个请求生成或传递trace_id"""

    def __init__(self, app: ASGIApp, trace_header: str = "X-Trace-ID") -> None:
        super().__init__(app)
        self.app = app
        self.trace_header = trace_header

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """处理链路追踪ID"""
        # 从请求头获取trace_id，如果没有则生成新的
        trace_id = request.headers.get(self.trace_header)
        if not trace_id:
            trace_id = str(uuid.uuid4())

        # 设置到上下文变量中
        trace_id_var.set(trace_id)

        # 调用下一个中间件或路由处理函数
        response = await call_next(request)

        # 将trace_id添加到响应头中
        response.headers[self.trace_header] = trace_id

        return response


class UseTimeMiddleware(BaseHTTPMiddleware):
    """计算耗时中间件 - 支持流式响应的准确耗时统计"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.app = app

    async def _wrap_streaming_response(
        self, original_generator: AsyncIterable[Any], request: Request, start_time: float
    ) -> AsyncIterable[Any]:
        """包装流式响应生成器，在流式输出完全结束时记录真正的耗时"""
        try:
            async for chunk in original_generator:
                yield chunk
        finally:
            # 流式输出完全结束，记录真正的耗时
            process_time = time.time() - start_time
            _logger.info(f"{request.method} {request.url} - 流式响应完成 - 总耗时: {process_time:.3f}s")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """请求耗时统计 - 区分普通响应和流式响应"""
        start_time = time.time()

        # 调用下一个中间件或路由处理函数
        result = await call_next(request)

        # 添加调试日志 - 使用info级别确保可见
        _logger.debug(f"[中间件调试] 请求路径: {request.method} {request.url}")
        _logger.debug(f"[中间件调试] 响应类型: {type(result).__name__}")

        # 更安全的流式响应检测：尝试访问body_iterator属性
        try:
            # 使用动态属性访问避免类型检查器错误
            body_iterator = getattr(result, "body_iterator", None)
            response_type_name = type(result).__name__

            # 尝试从headers获取Content-Type
            headers = getattr(result, "headers", {})
            if headers:
                media_type = headers.get("content-type") or headers.get("Content-Type")

            # 确保media_type不是None
            media_type = media_type or ""

            _logger.debug(f"[中间件调试] 媒体类型: {media_type}")

            # 检测条件分解
            has_body_iterator = body_iterator is not None
            has_streaming_in_name = "stream" in response_type_name.lower()
            # 更宽泛的流式媒体类型检测
            is_streaming_media_type = media_type and (
                media_type.startswith("text/event-stream")
                or media_type.startswith("application/x-ndjson")
                or media_type.startswith("text/plain")
            )

            # 更严格的流式响应检测逻辑
            is_streaming = has_body_iterator and has_streaming_in_name and is_streaming_media_type

            # 详细调试信息
            _logger.debug(f"[流式检测] 类型: {response_type_name}, 媒体类型: '{media_type}'")
            _logger.debug(
                f"[流式检测] has_body_iterator: {has_body_iterator}, has_streaming_in_name: {has_streaming_in_name}, is_streaming_media_type: {is_streaming_media_type}"
            )

        except (AttributeError, TypeError) as e:
            _logger.debug(f"[中间件调试] 流式响应检测失败: {e}")
            is_streaming = False
            body_iterator = None

        _logger.debug(f"[中间件调试] 是否为流式响应(基于属性): {is_streaming}")

        # 如果是流式响应，显示更多信息
        if is_streaming:
            status_code = getattr(result, "status_code", "unknown")
            _logger.debug(f"[中间件调试] 流式响应详情 - status_code: {status_code}, media_type: {media_type}")

        # 检查是否为流式响应
        if is_streaming and body_iterator is not None:
            # 流式响应：包装生成器以获取准确的结束时间
            wrapped_generator = self._wrap_streaming_response(body_iterator, request, start_time)

            # 创建新的StreamingResponse，使用包装后的生成器
            new_response = StreamingResponse(
                wrapped_generator,
                status_code=getattr(result, "status_code", 200),
                headers=dict(getattr(result, "headers", {})),
                media_type=getattr(result, "media_type", "text/plain"),
                background=getattr(result, "background", None),
            )

            # 记录流式响应开始时间（生成器创建时间）
            initial_process_time = time.time() - start_time
            new_response.headers["X-Process-Time"] = str(initial_process_time)
            _logger.info(f"{request.method} {request.url} - 流式响应开始 - 初始耗时: {initial_process_time:.3f}s")

            return new_response
        else:
            # 普通响应：使用原有逻辑
            process_time = time.time() - start_time
            result.headers["X-Process-Time"] = str(process_time)
            _logger.info(f"{request.method} {request.url} - {result.status_code} - 请求耗时: {process_time:.3f}s")

            return result


class SimpleBaseMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        response = await self.before_request(request) or self.app
        await response(request.scope, request.receive, send)
        await self.after_request(request)

    async def before_request(self, request: Request):
        return self.app

    async def after_request(self, request: Request):
        return None


class BackGroundTaskMiddleware(SimpleBaseMiddleware):
    @override
    async def before_request(self, request: Request):
        await BgTasks.init_bg_tasks_obj()

    @override
    async def after_request(self, request: Request):
        await BgTasks.execute_tasks()


def get_trace_id() -> str:
    """获取当前请求的trace_id"""
    return trace_id_var.get("")
