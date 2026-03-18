"""
消息投递队列 - 磁盘持久化的可靠投递队列

预写日志模式: 先写入磁盘，再尝试投递。
原子写入: 临时文件 + os.replace()，崩溃安全。

用法:
    from coder.components.delivery import DeliveryQueue, chunk_message

    queue = DeliveryQueue()

    # 入队消息
    delivery_id = queue.enqueue("telegram", "user123", "Hello!")

    # 按平台限制分片
    chunks = chunk_message(long_text, "telegram")
    for chunk in chunks:
        queue.enqueue("telegram", "user123", chunk)

    # 加载待处理条目
    pending = queue.load_pending()

    # 确认投递成功
    queue.ack(delivery_id)

    # 标记投递失败 (自动重试或移入 failed/)
    queue.fail(delivery_id, "Network error")
"""

import json
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from coder.settings import settings

# 指数退避时间表 (毫秒)
BACKOFF_MS: List[int] = [5_000, 25_000, 120_000, 600_000]  # [5s, 25s, 2min, 10min]

# 最大重试次数
MAX_RETRIES: int = 5

# 平台消息长度限制
CHANNEL_LIMITS: Dict[str, int] = {
    "telegram": 4096,
    "telegram_caption": 1024,
    "discord": 2000,
    "whatsapp": 4096,
    "feishu": 4096,
    "cli": 10000,  # CLI 无实际限制
    "default": 4096,
}


@dataclass
class QueuedDelivery:
    """
    队列投递条目

    Attributes:
        id: 唯一标识符
        channel: 渠道名称 (telegram, discord, cli 等)
        to: 目标地址 (用户ID, 频道ID 等)
        text: 消息内容
        retry_count: 重试次数
        last_error: 最后一次错误信息
        enqueued_at: 入队时间戳
        next_retry_at: 下次重试时间戳
    """

    id: str
    channel: str
    to: str
    text: str
    retry_count: int = 0
    last_error: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    next_retry_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "channel": self.channel,
            "to": self.to,
            "text": self.text,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "enqueued_at": self.enqueued_at,
            "next_retry_at": self.next_retry_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "QueuedDelivery":
        """从字典创建"""
        return QueuedDelivery(
            id=data["id"],
            channel=data["channel"],
            to=data["to"],
            text=data["text"],
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
            enqueued_at=data.get("enqueued_at", 0.0),
            next_retry_at=data.get("next_retry_at", 0.0),
        )


def compute_backoff_ms(retry_count: int) -> int:
    """
    计算指数退避时间 (毫秒)

    带 +/- 20% 抖动以避免惊群效应。

    Args:
        retry_count: 重试次数 (从 1 开始)

    Returns:
        退避时间 (毫秒)
    """
    if retry_count <= 0:
        return 0
    idx = min(retry_count - 1, len(BACKOFF_MS) - 1)
    base = BACKOFF_MS[idx]
    jitter = random.randint(-base // 5, base // 5)  # +/- 20%
    return max(0, base + jitter)


def chunk_message(text: str, channel: str = "default") -> List[str]:
    """
    将消息按平台限制分片

    两级拆分: 先按段落，再硬切。

    Args:
        text: 原始消息文本
        channel: 渠道名称

    Returns:
        分片后的消息列表
    """
    if not text:
        return []

    limit = CHANNEL_LIMITS.get(channel, CHANNEL_LIMITS["default"])

    if len(text) <= limit:
        return [text]

    chunks: List[str] = []

    # 先尝试按段落分割
    for para in text.split("\n\n"):
        if chunks and len(chunks[-1]) + len(para) + 2 <= limit:
            # 可以追加到上一个分片
            chunks[-1] += "\n\n" + para
        else:
            # 需要硬切
            while len(para) > limit:
                chunks.append(para[:limit])
                para = para[limit:]
            if para:
                chunks.append(para)

    return chunks or [text[:limit]]


class DeliveryQueue:
    """
    磁盘持久化的可靠投递队列

    预写日志模式: 先写入磁盘，再尝试投递。
    原子写入: 临时文件 + os.replace()，崩溃安全。

    工作流程:
    1. enqueue() - 创建条目并原子写入磁盘
    2. DeliveryRunner - 后台线程处理待投递条目
    3. ack() - 投递成功，删除队列文件
    4. fail() - 投递失败，更新重试状态或移入 failed/
    """

    def __init__(self, queue_dir: Optional[Path] = None) -> None:
        """
        初始化投递队列

        Args:
            queue_dir: 队列存储目录，默认为 workspace/.delivery-queue
        """
        workspace = Path(settings.workspace_dir)
        self.queue_dir = queue_dir or workspace / ".delivery-queue"
        self.failed_dir = self.queue_dir / "failed"

        # 确保目录存在
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._lock = threading.Lock()

    def enqueue(self, channel: str, to: str, text: str) -> str:
        """
        创建队列条目并原子写入磁盘

        Args:
            channel: 渠道名称
            to: 目标地址
            text: 消息内容

        Returns:
            delivery_id: 投递条目 ID
        """
        delivery_id = uuid.uuid4().hex[:12]
        entry = QueuedDelivery(
            id=delivery_id,
            channel=channel,
            to=to,
            text=text,
            enqueued_at=time.time(),
            next_retry_at=0.0,
        )
        self._write_entry(entry)
        return delivery_id

    def _write_entry(self, entry: QueuedDelivery) -> None:
        """
        通过 tmp + os.replace() 实现原子写入

        三步保证:
        1. 写入 .tmp.{pid}.{id}.json (崩溃 = 孤立的临时文件, 无害)
        2. fsync() -- 数据已落盘
        3. os.replace() -- 原子交换 (崩溃 = 旧文件或新文件, 绝不会是半写文件)
        """
        final_path = self.queue_dir / f"{entry.id}.json"
        tmp_path = self.queue_dir / f".tmp.{os.getpid()}.{entry.id}.json"

        data = json.dumps(entry.to_dict(), indent=2, ensure_ascii=False)

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # 数据已落盘

        os.replace(str(tmp_path), str(final_path))  # 原子操作

    def _read_entry(self, delivery_id: str) -> Optional[QueuedDelivery]:
        """
        读取队列条目

        Args:
            delivery_id: 投递条目 ID

        Returns:
            队列条目，如果不存在则返回 None
        """
        file_path = self.queue_dir / f"{delivery_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return QueuedDelivery.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def ack(self, delivery_id: str) -> None:
        """
        投递成功 - 删除队列文件

        Args:
            delivery_id: 投递条目 ID
        """
        file_path = self.queue_dir / f"{delivery_id}.json"
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass

    def fail(self, delivery_id: str, error: str) -> None:
        """
        投递失败 - 递增重试计数，计算下次重试时间

        重试耗尽时移入 failed/ 目录。

        Args:
            delivery_id: 投递条目 ID
            error: 错误信息
        """
        entry = self._read_entry(delivery_id)
        if entry is None:
            return

        entry.retry_count += 1
        entry.last_error = error

        if entry.retry_count >= MAX_RETRIES:
            self.move_to_failed(delivery_id)
            return

        backoff_ms = compute_backoff_ms(entry.retry_count)
        entry.next_retry_at = time.time() + backoff_ms / 1000.0
        self._write_entry(entry)

    def move_to_failed(self, delivery_id: str) -> None:
        """
        将条目移入 failed/ 目录

        Args:
            delivery_id: 投递条目 ID
        """
        src = self.queue_dir / f"{delivery_id}.json"
        dst = self.failed_dir / f"{delivery_id}.json"
        try:
            os.replace(str(src), str(dst))
        except FileNotFoundError:
            pass

    def load_pending(self) -> List[QueuedDelivery]:
        """
        扫描队列目录，加载所有待处理条目

        按入队时间排序。

        Returns:
            待处理条目列表
        """
        entries: List[QueuedDelivery] = []

        if not self.queue_dir.exists():
            return entries

        for file_path in self.queue_dir.glob("*.json"):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                entries.append(QueuedDelivery.from_dict(data))
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        entries.sort(key=lambda e: e.enqueued_at)
        return entries

    def load_failed(self) -> List[QueuedDelivery]:
        """
        扫描 failed/ 目录，加载所有失败条目

        按入队时间排序。

        Returns:
            失败条目列表
        """
        entries: List[QueuedDelivery] = []

        if not self.failed_dir.exists():
            return entries

        for file_path in self.failed_dir.glob("*.json"):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                entries.append(QueuedDelivery.from_dict(data))
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        entries.sort(key=lambda e: e.enqueued_at)
        return entries

    def retry_failed(self) -> int:
        """
        将所有 failed/ 条目移回队列，重置重试计数

        Returns:
            移动的条目数量
        """
        count = 0

        if not self.failed_dir.exists():
            return count

        for file_path in self.failed_dir.glob("*.json"):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                entry = QueuedDelivery.from_dict(data)
                entry.retry_count = 0
                entry.last_error = None
                entry.next_retry_at = 0.0
                self._write_entry(entry)
                file_path.unlink()
                count += 1
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        return count

    def get_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息

        Returns:
            统计信息字典
        """
        pending = self.load_pending()
        failed = self.load_failed()
        return {
            "pending": len(pending),
            "failed": len(failed),
        }
