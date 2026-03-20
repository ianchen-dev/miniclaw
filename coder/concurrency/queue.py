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
from typing import Any, Callable, Deque, Dict, List, NamedTuple, Optional


class _QueuedTask(NamedTuple):
    """A task waiting in the queue with its Future and generation."""

    func: Callable[[], Any]
    future: concurrent.futures.Future
    generation: int


class LaneQueue:
    """
    命名 FIFO 队列，最多并行运行 max_concurrency 个任务。

    任务在独立线程中执行，结果通过 Future 返回。generation 机制支持重启恢复：
    旧 generation 的任务完成时不会触发新任务执行。
    """

    def __init__(self, name: str, max_concurrency: int = 1) -> None:
        self.name = name
        self.max_concurrency = max(1, max_concurrency)
        self._deque: Deque[_QueuedTask] = deque()
        self._condition = threading.Condition()
        self._active_count = 0
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    @generation.setter
    def generation(self, value: int) -> None:
        with self._condition:
            self._generation = value
            self._condition.notify_all()

    def enqueue(
        self,
        func: Callable[[], Any],
        generation: Optional[int] = None,
    ) -> concurrent.futures.Future:
        """将 callable 加入队列，返回结果的 Future。"""
        future = concurrent.futures.Future()
        with self._condition:
            gen = generation if generation is not None else self._generation
            self._deque.append(_QueuedTask(func, future, gen))
            self._pump()
        return future

    def _pump(self) -> None:
        """从队列弹出任务并启动，直到达到 max_concurrency。"""
        while self._active_count < self.max_concurrency and self._deque:
            task = self._deque.popleft()
            self._active_count += 1
            threading.Thread(
                target=self._run_task,
                args=(task.func, task.future, task.generation),
                daemon=True,
                name=f"lane-{self.name}",
            ).start()

    def _run_task(
        self,
        func: Callable[[], Any],
        future: concurrent.futures.Future,
        generation: int,
    ) -> None:
        """执行任务，设置结果，完成后调用 _task_done。"""
        try:
            future.set_result(func())
        except Exception as exc:
            future.set_exception(exc)
        finally:
            self._task_done(generation)

    def _task_done(self, generation: int) -> None:
        """递减活跃计数，若 generation 匹配则继续 pump。"""
        with self._condition:
            self._active_count -= 1
            if generation == self._generation:
                self._pump()
            self._condition.notify_all()

    def wait_for_idle(self, timeout: Optional[float] = None) -> bool:
        """阻塞直到队列为空且无活跃任务。"""
        deadline = time.monotonic() + timeout if timeout else None

        with self._condition:
            while self._active_count > 0 or self._deque:
                remaining = deadline - time.monotonic() if deadline else None
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def stats(self) -> Dict[str, Any]:
        """返回 lane 统计信息。"""
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
    中央调度器，将 callable 路由到命名的 LaneQueue。

    Lane 惰性创建。reset_all() 递增所有 generation，使旧任务不触发新任务。
    """

    def __init__(self) -> None:
        self._lanes: Dict[str, LaneQueue] = {}
        self._lock = threading.Lock()

    def get_or_create_lane(self, name: str, max_concurrency: int = 1) -> LaneQueue:
        """获取已有 lane 或创建新的。"""
        with self._lock:
            if name not in self._lanes:
                self._lanes[name] = LaneQueue(name, max_concurrency)
            return self._lanes[name]

    def enqueue(
        self,
        lane_name: str,
        func: Callable[[], Any],
    ) -> concurrent.futures.Future:
        """将 callable 路由到指定 lane，返回 Future。"""
        return self.get_or_create_lane(lane_name).enqueue(func)

    def reset_all(self) -> Dict[str, int]:
        """递增所有 lane 的 generation，返回新的 generation 值。"""
        with self._lock:
            return {name: self._bump_generation(lane) for name, lane in self._lanes.items()}

    def _bump_generation(self, lane: LaneQueue) -> int:
        lane.generation += 1
        return lane.generation

    def wait_for_all(self, timeout: float = 10.0) -> bool:
        """等待所有 lane 变为空闲。"""
        deadline = time.monotonic() + timeout
        with self._lock:
            lanes = list(self._lanes.values())

        for lane in lanes:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not lane.wait_for_idle(timeout=remaining):
                return False
        return True

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """汇总所有 lane 的统计信息。"""
        with self._lock:
            return {name: lane.stats() for name, lane in self._lanes.items()}

    def lane_names(self) -> List[str]:
        """获取所有 lane 名称。"""
        with self._lock:
            return list(self._lanes.keys())

    def get_lane(self, name: str) -> Optional[LaneQueue]:
        """获取指定 lane，不存在则返回 None。"""
        with self._lock:
            return self._lanes.get(name)


# 标准 Lane 名称常量
LANE_MAIN = "main"  # 用户交互
LANE_CRON = "cron"  # Cron 任务
LANE_HEARTBEAT = "heartbeat"  # 心跳任务
