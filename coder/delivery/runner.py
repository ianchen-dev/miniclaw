"""
消息投递运行器 - 后台投递线程

后台线程每秒扫描待投递条目，使用指数退避策略处理失败重试。
启动时执行恢复扫描，处理上次崩溃遗留的条目。

用法:
    from coder.delivery import DeliveryQueue, DeliveryRunner

    queue = DeliveryQueue()

    def deliver_fn(channel: str, to: str, text: str) -> None:
        # 实际投递逻辑
        print(f"[{channel}] -> {to}: {text}")

    runner = DeliveryRunner(queue, deliver_fn)
    runner.start()

    # 入队消息
    queue.enqueue("telegram", "user123", "Hello!")

    # 获取统计
    stats = runner.get_stats()

    # 停止
    runner.stop()
"""

import threading
import time
from typing import Any, Callable, Dict, Optional

from coder.cli import print_info, print_warn
from coder.delivery.queue import (
    MAX_RETRIES,
    DeliveryQueue,
    compute_backoff_ms,
)


# 投递函数类型
DeliverFn = Callable[[str, str, str], None]


class DeliveryRunner:
    """
    消息投递运行器

    后台线程每秒扫描待投递条目。只处理 next_retry_at 已到期的条目。
    启动时执行恢复扫描，处理上次崩溃遗留的条目。

    工作流程:
    1. start() - 运行恢复扫描，启动后台线程
    2. _background_loop() - 每秒扫描待处理条目
    3. _process_pending() - 处理到期的条目
    4. 成功 -> ack()，失败 -> fail()
    """

    def __init__(
        self,
        queue: DeliveryQueue,
        deliver_fn: DeliverFn,
        verbose: bool = True,
    ) -> None:
        """
        初始化投递运行器

        Args:
            queue: 投递队列
            deliver_fn: 投递函数 (channel, to, text) -> None
            verbose: 是否打印详细信息
        """
        self.queue = queue
        self.deliver_fn = deliver_fn
        self.verbose = verbose

        # 控制标志
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # 统计
        self.total_attempted: int = 0
        self.total_succeeded: int = 0
        self.total_failed: int = 0

    def start(self) -> None:
        """运行恢复扫描，然后启动后台投递线程"""
        self._recovery_scan()
        self._thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
            name="delivery-runner",
        )
        self._thread.start()

    def _recovery_scan(self) -> None:
        """启动时统计待处理和失败条目"""
        pending = self.queue.load_pending()
        failed = self.queue.load_failed()

        if not self.verbose:
            return

        parts = []
        if pending:
            parts.append(f"{len(pending)} pending")
        if failed:
            parts.append(f"{len(failed)} failed")

        if parts:
            print_info(f"[delivery] Recovery: {', '.join(parts)}")
        else:
            print_info("[delivery] Recovery: queue is clean")

    def _background_loop(self) -> None:
        """后台循环"""
        while not self._stop_event.is_set():
            try:
                self._process_pending()
            except Exception as exc:
                if self.verbose:
                    print_warn(f"[delivery] Loop error: {exc}")

            self._stop_event.wait(timeout=1.0)

    def _process_pending(self) -> None:
        """
        处理所有 next_retry_at <= now 的待处理条目

        成功 -> ack()
        失败 -> fail() + 退避
        """
        pending = self.queue.load_pending()
        now = time.time()

        for entry in pending:
            if self._stop_event.is_set():
                break

            # 跳过未到期的条目
            if entry.next_retry_at > now:
                continue

            self.total_attempted += 1

            try:
                # 尝试投递
                self.deliver_fn(entry.channel, entry.to, entry.text)
                self.queue.ack(entry.id)
                self.total_succeeded += 1

            except Exception as exc:
                # 投递失败
                error_msg = str(exc)
                self.queue.fail(entry.id, error_msg)
                self.total_failed += 1

                if not self.verbose:
                    continue

                retry_info = f"retry {entry.retry_count + 1}/{MAX_RETRIES}"

                if entry.retry_count + 1 >= MAX_RETRIES:
                    # 达到最大重试次数，移入 failed/
                    print_warn(f"[delivery] {entry.id[:8]}... -> failed/ ({retry_info}): {error_msg}")
                else:
                    # 计算下次重试时间
                    backoff = compute_backoff_ms(entry.retry_count + 1)
                    print_warn(
                        f"[delivery] {entry.id[:8]}... failed ({retry_info}), "
                        f"next retry in {backoff / 1000:.0f}s: {error_msg}"
                    )

    def stop(self) -> None:
        """停止投递运行器"""
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取投递统计信息

        Returns:
            统计信息字典
        """
        pending = self.queue.load_pending()
        failed = self.queue.load_failed()

        return {
            "pending": len(pending),
            "failed": len(failed),
            "total_attempted": self.total_attempted,
            "total_succeeded": self.total_succeeded,
            "total_failed": self.total_failed,
        }

    def is_running(self) -> bool:
        """检查运行器是否在运行"""
        return self._thread is not None and self._thread.is_alive()
