"""
消息投递组件 - 可靠消息投递队列

提供磁盘持久化的消息投递机制:
- DeliveryQueue: 磁盘持久化队列，原子写入
- DeliveryRunner: 后台投递线程，指数退避重试
- chunk_message: 按平台限制分片消息

特性:
- 预写日志: 先写入磁盘，再尝试投递
- 原子写入: tmp + fsync + os.replace，崩溃安全
- 指数退避: [5s, 25s, 2min, 10min] + 20% 抖动
- 启动恢复: 自动重试上次崩溃前遗留的待投递条目
"""

from coder.components.delivery.queue import (
    DeliveryQueue,
    QueuedDelivery,
    compute_backoff_ms,
    chunk_message,
    CHANNEL_LIMITS,
    BACKOFF_MS,
    MAX_RETRIES,
)
from coder.components.delivery.runner import DeliveryRunner

__all__ = [
    "DeliveryQueue",
    "QueuedDelivery",
    "DeliveryRunner",
    "compute_backoff_ms",
    "chunk_message",
    "CHANNEL_LIMITS",
    "BACKOFF_MS",
    "MAX_RETRIES",
]
