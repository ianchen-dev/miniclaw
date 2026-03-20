"""
并发队列 - LaneQueue 和 CommandQueue 实现

命名 lane 系统用于任务调度和并发控制。每个 lane 是一个 FIFO 队列，
带可配置的 max_concurrency。任务以 callable 入队，在专用线程中执行，
通过 concurrent.futures.Future 对象返回结果。

核心特性:
- 命名 lane: 每个 lane 有独立名称 (如 "main", "cron", "heartbeat")
- max_concurrency: 每个 lane 限制同时运行的任务数，默认为 1 (串行)
- _pump() 循环: 任务完成后自动出队更多任务，无需外部调度器
- 基于 Future 的结果: enqueue() 返回 Future，支持阻塞等待或回调
- Generation 追踪: 支持 reset_all() 时的重启恢复

用法:
    from coder.concurrency import CommandQueue, LANE_MAIN

    cmd_queue = CommandQueue()
    future = cmd_queue.enqueue(LANE_MAIN, lambda: "hello")
    result = future.result(timeout=30)  # 阻塞等待结果
"""

import concurrent.futures
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional


class LaneQueue:
    """
    命名 FIFO 队列，最多并行运行 max_concurrency 个任务

    每个入队的 callable 在自己的线程中运行。结果通过
    concurrent.futures.Future 投递。generation 计数器支持重启恢复:
    当 generation 递增后，来自旧 generation 的过期任务完成时
    不会重新泵送队列。

    Attributes:
        name: Lane 名称
        max_concurrency: 最大并发任务数

    Example:
        lane = LaneQueue("main", max_concurrency=1)
        future = lane.enqueue(lambda: do_work())
        result = future.result()
    """

    def __init__(self, name: str, max_concurrency: int = 1) -> None:
        """
        初始化 LaneQueue

        Args:
            name: Lane 名称
            max_concurrency: 最大并发任务数，默认 1 (串行执行)
        """
        self.name = name
        self.max_concurrency = max(1, max_concurrency)

        # 内部状态
        self._deque: deque[tuple[Callable[[], Any], concurrent.futures.Future, int]] = deque()
        self._condition = threading.Condition()
        self._active_count = 0
        self._generation = 0

    @property
    def generation(self) -> int:
        """获取当前 generation 计数器"""
        with self._condition:
            return self._generation

    @generation.setter
    def generation(self, value: int) -> None:
        """设置 generation 计数器"""
        with self._condition:
            self._generation = value
            self._condition.notify_all()

    def enqueue(
        self,
        fn: Callable[[], Any],
        generation: Optional[int] = None,
    ) -> concurrent.futures.Future:
        """
        将 callable 加入队列，返回结果的 Future

        如果 generation 为 None，使用当前 lane 的 generation。

        Args:
            fn: 要执行的 callable
            generation: 可选的 generation 标识

        Returns:
            concurrent.futures.Future 对象，可用于获取结果
        """
        future: concurrent.futures.Future = concurrent.futures.Future()

        with self._condition:
            gen = generation if generation is not None else self._generation
            self._deque.append((fn, future, gen))
            self._pump()

        return future

    def _pump(self) -> None:
        """
        从 deque 弹出任务并运行，直到 active >= max_concurrency

        调用时必须持有 self._condition。
        """
        while self._active_count < self.max_concurrency and self._deque:
            fn, future, gen = self._deque.popleft()
            self._active_count += 1

            t = threading.Thread(
                target=self._run_task,
                args=(fn, future, gen),
                daemon=True,
                name=f"lane-{self.name}",
            )
            t.start()

    def _run_task(
        self,
        fn: Callable[[], Any],
        future: concurrent.futures.Future,
        gen: int,
    ) -> None:
        """
        执行 fn，设置 future 结果，然后调用 _task_done

        Args:
            fn: 要执行的 callable
            future: 结果 Future
            gen: 任务所属的 generation
        """
        try:
            result = fn()
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)
        finally:
            self._task_done(gen)

    def _task_done(self, gen: int) -> None:
        """
        递减活跃计数，仅在 generation 匹配时重新泵送

        Args:
            gen: 完成任务的 generation
        """
        with self._condition:
            self._active_count -= 1

            # 只有当前 generation 的任务才会触发新的 pump
            if gen == self._generation:
                self._pump()

            self._condition.notify_all()

    def wait_for_idle(self, timeout: Optional[float] = None) -> bool:
        """
        阻塞直到 active_count == 0 且 deque 为空

        Args:
            timeout: 超时时间 (秒)，None 表示无限等待

        Returns:
            True 表示达到空闲，False 表示超时
        """
        deadline = (time.monotonic() + timeout) if timeout is not None else None

        with self._condition:
            while self._active_count > 0 or len(self._deque) > 0:
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                self._condition.wait(timeout=remaining)

            return True

    def stats(self) -> Dict[str, Any]:
        """
        获取 lane 统计信息

        Returns:
            包含 name, queue_depth, active, max_concurrency, generation 的字典
        """
        with self._condition:
            return {
                "name": self.name,
                "queue_depth": len(self._deque),
                "active": self._active_count,
                "max_concurrency": self.max_concurrency,
                "generation": self._generation,
            }


class CommandQueue:
    """
    中央调度器，将 callable 路由到命名的 LaneQueue

    Lane 在首次使用时惰性创建。reset_all() 递增所有 generation 计数器，
    使得来自上一个生命周期的过期任务不会重新泵送队列。

    Example:
        cmd_queue = CommandQueue()
        future = cmd_queue.enqueue("main", lambda: do_work())
        result = future.result()
    """

    def __init__(self) -> None:
        """初始化 CommandQueue"""
        self._lanes: Dict[str, LaneQueue] = {}
        self._lock = threading.Lock()

    def get_or_create_lane(self, name: str, max_concurrency: int = 1) -> LaneQueue:
        """
        获取已有 lane 或创建新的

        Args:
            name: Lane 名称
            max_concurrency: 创建新 lane 时的最大并发数

        Returns:
            LaneQueue 实例
        """
        with self._lock:
            if name not in self._lanes:
                self._lanes[name] = LaneQueue(name, max_concurrency)
            return self._lanes[name]

    def enqueue(
        self,
        lane_name: str,
        fn: Callable[[], Any],
    ) -> concurrent.futures.Future:
        """
        将 callable 路由到指定 lane，返回 Future

        Args:
            lane_name: 目标 lane 名称
            fn: 要执行的 callable

        Returns:
            concurrent.futures.Future 对象
        """
        lane = self.get_or_create_lane(lane_name)
        return lane.enqueue(fn)

    def reset_all(self) -> Dict[str, int]:
        """
        递增所有 lane 的 generation，用于重启恢复

        Returns:
            lane_name -> new_generation 的字典
        """
        result: Dict[str, int] = {}

        with self._lock:
            for name, lane in self._lanes.items():
                lane.generation += 1
                result[name] = lane.generation

        return result

    def wait_for_all(self, timeout: float = 10.0) -> bool:
        """
        等待所有 lane 变为空闲

        Args:
            timeout: 超时时间 (秒)

        Returns:
            True 表示全部空闲，False 表示超时
        """
        deadline = time.monotonic() + timeout

        with self._lock:
            lanes = list(self._lanes.values())

        for lane in lanes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if not lane.wait_for_idle(timeout=remaining):
                return False

        return True

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """
        汇总所有 lane 的统计信息

        Returns:
            lane_name -> stats dict 的字典
        """
        with self._lock:
            return {name: lane.stats() for name, lane in self._lanes.items()}

    def lane_names(self) -> List[str]:
        """
        获取所有 lane 名称

        Returns:
            lane 名称列表
        """
        with self._lock:
            return list(self._lanes.keys())

    def get_lane(self, name: str) -> Optional[LaneQueue]:
        """
        获取指定名称的 lane，不创建

        Args:
            name: Lane 名称

        Returns:
            LaneQueue 实例或 None
        """
        with self._lock:
            return self._lanes.get(name)


# ---------------------------------------------------------------------------
# 标准 Lane 名称常量
# ---------------------------------------------------------------------------

#: 主 lane，用于用户交互
LANE_MAIN = "main"

#: Cron 任务 lane
LANE_CRON = "cron"

#: 心跳任务 lane
LANE_HEARTBEAT = "heartbeat"
