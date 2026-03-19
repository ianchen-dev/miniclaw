"""
并发组件 - LaneQueue 和 CommandQueue

提供命名 lane 系统用于任务调度和并发控制。每个 lane 是一个 FIFO 队列，
带可配置的 max_concurrency。任务以 callable 入队，在专用线程中执行，
通过 concurrent.futures.Future 对象返回结果。

特性:
- 命名 lane: 每个 lane 有独立名称 (如 "main", "cron", "heartbeat")
- max_concurrency: 每个 lane 限制同时运行的任务数，默认为 1 (串行)
- Generation 追踪: 支持 reset_all() 时的重启恢复
- 用户优先: 用户输入进入 main lane 并阻塞等待结果

用法:
    from coder.concurrency import CommandQueue, LANE_MAIN

    cmd_queue = CommandQueue()

    # 创建默认 lanes
    cmd_queue.get_or_create_lane(LANE_MAIN, max_concurrency=1)
    cmd_queue.get_or_create_lane(LANE_CRON, max_concurrency=1)
    cmd_queue.get_or_create_lane(LANE_HEARTBEAT, max_concurrency=1)

    # 入队任务
    future = cmd_queue.enqueue(LANE_MAIN, lambda: "hello")
    result = future.result(timeout=30)  # 阻塞等待结果

    # 查看状态
    stats = cmd_queue.stats()

    # 重启恢复
    cmd_queue.reset_all()
"""

from coder.concurrency.queue import (
    LANE_CRON,
    LANE_HEARTBEAT,
    LANE_MAIN,
    CommandQueue,
    LaneQueue,
)


__all__ = [
    "LaneQueue",
    "CommandQueue",
    "LANE_MAIN",
    "LANE_CRON",
    "LANE_HEARTBEAT",
]
