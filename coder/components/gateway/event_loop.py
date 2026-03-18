"""
共享事件循环管理

在 daemon 线程中运行 asyncio 事件循环，供同步代码调用异步函数。

使用场景:
    - REPL 中启动 WebSocket 服务器
    - 同步上下文中调用异步 agent 运行器
"""

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

# 全局事件循环和线程
_event_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    获取或创建共享事件循环。

    如果事件循环不存在或已停止，则在 daemon 线程中创建新的。

    Returns:
        共享的 asyncio 事件循环
    """
    global _event_loop, _loop_thread

    with _loop_lock:
        if _event_loop is not None and _event_loop.is_running():
            return _event_loop

        # 创建新的事件循环
        _event_loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(_event_loop)
            _event_loop.run_forever()

        # 在 daemon 线程中运行
        _loop_thread = threading.Thread(target=_run, daemon=True, name="gateway-event-loop")
        _loop_thread.start()

        return _event_loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    在共享事件循环中运行协程并等待结果。

    Args:
        coro: 要运行的协程

    Returns:
        协程的返回值
    """
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def stop_event_loop() -> None:
    """
    停止共享事件循环。

    通常在程序退出时调用。
    """
    global _event_loop, _loop_thread

    with _loop_lock:
        if _event_loop is not None and _event_loop.is_running():
            _event_loop.call_soon_threadsafe(_event_loop.stop)
            _event_loop = None
            _loop_thread = None


__all__ = [
    "get_event_loop",
    "run_async",
    "stop_event_loop",
]
