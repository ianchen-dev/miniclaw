"""性能监控中间件

提供API请求的性能监控和耗时统计功能
"""

import time
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


_logger = logger.bind(name=__name__)


class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """性能监控中间件

    记录每个请求的响应时间、状态码等性能指标
    """

    def __init__(
        self,
        app,
        slow_request_threshold: float = 1.0,  # 慢请求阈值（秒）
        log_all_requests: bool = False,  # 是否记录所有请求
    ):
        """初始化性能监控中间件

        Args:
            app: FastAPI应用实例
            slow_request_threshold: 慢请求阈值（秒），超过此时间的请求会被特别记录
            log_all_requests: 是否记录所有请求（包括正常速度的请求）
        """
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold
        self.log_all_requests = log_all_requests

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录性能指标

        Args:
            request: 请求对象
            call_next: 下一个处理函数

        Returns:
            Response: 响应对象
        """
        # 记录开始时间
        start_time = time.time()

        # 获取请求信息
        method = request.method
        url = str(request.url)
        client_host = request.client.host if request.client else "unknown"

        # 处理请求
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # 记录异常
            duration = time.time() - start_time
            _logger.error(
                f"❌ 请求异常 | {method} {url} | 客户端: {client_host} | 耗时: {duration:.3f}s | 异常: {str(e)}"
            )
            raise
        else:
            # 计算耗时
            duration = time.time() - start_time

            # 添加性能头信息
            response.headers["X-Process-Time"] = f"{duration:.3f}"

            # 判断是否为慢请求
            is_slow = duration > self.slow_request_threshold

            # 记录日志
            if is_slow or self.log_all_requests:
                log_level = "warning" if is_slow else "info"
                log_icon = "🐌" if is_slow else "✅"

                log_message = (
                    f"{log_icon} API请求 | {method} {url} | "
                    f"状态码: {status_code} | "
                    f"耗时: {duration:.3f}s | "
                    f"客户端: {client_host}"
                )

                if is_slow:
                    log_message += f" | ⚠️ 慢请求（阈值: {self.slow_request_threshold}s）"

                getattr(_logger, log_level)(log_message)

            return response

def get_performance_middleware(
    slow_request_threshold: float = 1.0,
    log_all_requests: bool = False,
) -> Callable:
    """获取性能监控中间件工厂函数

    Args:
        slow_request_threshold: 慢请求阈值（秒）
        log_all_requests: 是否记录所有请求

    Returns:
        Callable: 中间件工厂函数
    """

    def middleware_factory(app):
        return PerformanceMonitorMiddleware(
            app,
            slow_request_threshold=slow_request_threshold,
            log_all_requests=log_all_requests,
        )

    return middleware_factory
