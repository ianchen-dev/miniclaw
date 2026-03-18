"""
心跳运行器 - 后台定期检查任务

心跳运行器使用 Lane 互斥机制，确保用户消息始终优先于后台任务。
当用户正在与 Agent 交互时，心跳任务会自动让步。

s10 更新: 支持 CommandQueue 基于 lane 的调度，替代原有的锁机制。
当提供 command_queue 时，使用 lane 统计信息进行非阻塞检查。

用法:
    # 方式1: 使用 CommandQueue (推荐，s10+)
    from coder.components.scheduler import HeartbeatRunner
    from coder.components.concurrency import CommandQueue, LANE_HEARTBEAT

    cmd_queue = CommandQueue()
    heartbeat = HeartbeatRunner(
        workspace=Path("workspace"),
        command_queue=cmd_queue,
    )
    heartbeat.start()

    # 方式2: 使用 Lock (向后兼容，s07)
    from coder.components.scheduler import HeartbeatRunner

    lane_lock = threading.Lock()
    heartbeat = HeartbeatRunner(
        workspace=Path("workspace"),
        lane_lock=lane_lock,
    )
    heartbeat.start()

    # 检查状态
    status = heartbeat.status()

    # 手动触发
    result = heartbeat.trigger()

    # 获取输出
    outputs = heartbeat.drain_output()

    # 停止
    heartbeat.stop()
"""

import concurrent.futures
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from coder.settings import settings


class HeartbeatRunner:
    """
    心跳运行器

    定期检查是否应该运行心跳任务，通过 Lane 互斥机制确保用户优先。

    工作流程:
    1. 后台线程每秒检查一次 should_run()
    2. 如果满足条件，检查 lane 是否可用
    3. 如果可用则执行心跳任务 (通过 CommandQueue 入队或直接执行)
    4. 解析响应，去除 HEARTBEAT_OK 标记
    5. 去重后将结果放入输出队列

    s10 更新:
    - 支持 command_queue 参数，使用 lane-based 调度
    - 向后兼容 lane_lock 参数
    """

    def __init__(
        self,
        workspace: Path,
        lane_lock: Optional[threading.Lock] = None,
        interval: Optional[float] = None,
        active_hours: Optional[Tuple[int, int]] = None,
        max_queue_size: Optional[int] = None,
        command_queue: Optional[Any] = None,  # CommandQueue 类型，避免循环导入
    ) -> None:
        """
        初始化心跳运行器

        Args:
            workspace: 工作区目录
            lane_lock: Lane 互斥锁，与主循环共享 (s07 兼容模式)
            interval: 心跳间隔 (秒)，默认从配置读取
            active_hours: 活跃时间范围 (开始小时, 结束小时)，默认从配置读取
            max_queue_size: 输出队列最大大小，默认从配置读取
            command_queue: CommandQueue 实例，用于 lane-based 调度 (s10+ 推荐)
        """
        self.workspace = workspace
        self.heartbeat_path = workspace / "HEARTBEAT.md"
        self.lane_lock = lane_lock
        self.command_queue = command_queue
        self.interval = interval or settings.heartbeat_interval
        self.active_hours = active_hours or (
            settings.heartbeat_active_start,
            settings.heartbeat_active_end,
        )
        self.max_queue_size = max_queue_size or settings.heartbeat_max_queue_size

        # 状态
        self.last_run_at: float = 0.0
        self.running: bool = False
        self._stopped: bool = False
        self._thread: Optional[threading.Thread] = None

        # 输出队列
        self._output_queue: list[str] = []
        self._queue_lock = threading.Lock()
        self._last_output: str = ""

    def should_run(self) -> Tuple[bool, str]:
        """
        检查是否应该运行心跳任务

        4 项前置检查:
        1. HEARTBEAT.md 文件存在
        2. HEARTBEAT.md 内容非空
        3. 间隔时间已过
        4. 在活跃时间范围内
        5. 当前没有在运行

        Returns:
            (是否应该运行, 原因说明)
        """
        # 检查文件存在
        if not self.heartbeat_path.exists():
            return False, "HEARTBEAT.md not found"

        # 检查内容非空
        if not self.heartbeat_path.read_text(encoding="utf-8").strip():
            return False, "HEARTBEAT.md is empty"

        # 检查间隔
        now = time.time()
        elapsed = now - self.last_run_at
        if elapsed < self.interval:
            return False, f"interval not elapsed ({self.interval - elapsed:.0f}s remaining)"

        # 检查活跃时间
        hour = datetime.now().hour
        start_hour, end_hour = self.active_hours
        # 处理跨午夜的情况，如 (22, 6) 表示 22:00 到次日 06:00
        if start_hour <= end_hour:
            in_hours = start_hour <= hour < end_hour
        else:
            in_hours = not (end_hour <= hour < start_hour)

        if not in_hours:
            return False, f"outside active hours ({start_hour}:00-{end_hour}:00)"

        # 检查是否已在运行
        if self.running:
            return False, "already running"

        return True, "all checks passed"

    def _parse_response(self, response: str) -> Optional[str]:
        """
        解析心跳响应

        HEARTBEAT_OK 表示没有需要报告的内容。
        如果响应只包含 HEARTBEAT_OK 或很短，返回 None。

        Args:
            response: LLM 响应文本

        Returns:
            有意义的内容，或 None 表示无输出
        """
        if "HEARTBEAT_OK" in response:
            # 去除 HEARTBEAT_OK 标记
            stripped = response.replace("HEARTBEAT_OK", "").strip()
            # 如果剩余内容很短，认为是空
            return stripped if len(stripped) > 5 else None

        return response.strip() or None

    def _build_heartbeat_prompt(self) -> Tuple[str, str]:
        """
        构建心跳提示词

        从 HEARTBEAT.md 读取指令，结合 MEMORY.md 构建完整提示。

        Returns:
            (用户指令, 系统提示词)
        """
        # 读取心跳指令
        instructions = self.heartbeat_path.read_text(encoding="utf-8").strip()

        # 读取记忆
        memory_path = self.workspace / "MEMORY.md"
        memory_content = ""
        if memory_path.exists():
            memory_content = memory_path.read_text(encoding="utf-8").strip()

        # 读取灵魂
        soul_path = self.workspace / "SOUL.md"
        soul_content = "You are a helpful AI assistant."
        if soul_path.exists():
            soul_content = soul_path.read_text(encoding="utf-8").strip()

        # 构建系统提示词
        extra_parts = []
        if memory_content:
            extra_parts.append(f"## Known Context\n\n{memory_content}")
        extra_parts.append(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        extra = "\n\n".join(extra_parts)
        system_prompt = f"{soul_content}\n\n{extra}" if extra else soul_content

        return instructions, system_prompt

    def _execute_with_queue(self) -> None:
        """
        使用 CommandQueue 执行心跳 (s10+)

        通过 lane 统计信息进行非阻塞检查，如果 lane 不忙则入队执行。
        """
        from coder.components.concurrency import LANE_HEARTBEAT

        # 检查 heartbeat lane 是否有活跃任务
        lane_stats = self.command_queue.get_or_create_lane(LANE_HEARTBEAT).stats()
        if lane_stats["active"] > 0:
            # lane 正忙，跳过本次心跳
            return

        def _do_heartbeat() -> Optional[str]:
            """执行心跳任务"""
            instructions, sys_prompt = self._build_heartbeat_prompt()
            if not instructions:
                return None
            response = self._run_single_turn(instructions, sys_prompt)
            return self._parse_response(response)

        future = self.command_queue.enqueue(LANE_HEARTBEAT, _do_heartbeat)

        def _on_done(f: concurrent.futures.Future) -> None:
            """任务完成回调"""
            self.last_run_at = time.time()
            try:
                meaningful = f.result()
                if meaningful is None:
                    return
                # 去重
                if meaningful.strip() == self._last_output:
                    return
                self._last_output = meaningful.strip()
                # 放入输出队列
                with self._queue_lock:
                    if len(self._output_queue) < self.max_queue_size:
                        self._output_queue.append(meaningful)
            except Exception as exc:
                with self._queue_lock:
                    self._output_queue.append(f"[heartbeat error: {exc}]")

        future.add_done_callback(_on_done)

    def _execute_with_lock(self) -> None:
        """
        使用 Lock 执行心跳 (s07 兼容)

        非阻塞获取锁；如果忙则跳过（用户优先）。
        """
        # 非阻塞获取锁
        acquired = self.lane_lock.acquire(blocking=False)
        if not acquired:
            # 用户持有锁，跳过本次心跳
            return

        self.running = True
        try:
            # 构建提示词
            instructions, sys_prompt = self._build_heartbeat_prompt()
            if not instructions:
                return

            # 调用 LLM (单轮，不使用工具)
            response = self._run_single_turn(instructions, sys_prompt)

            # 解析响应
            meaningful = self._parse_response(response)
            if meaningful is None:
                return

            # 去重
            if meaningful.strip() == self._last_output:
                return

            self._last_output = meaningful.strip()

            # 放入输出队列
            with self._queue_lock:
                if len(self._output_queue) < self.max_queue_size:
                    self._output_queue.append(meaningful)

        except Exception as exc:
            # 错误也放入队列
            with self._queue_lock:
                self._output_queue.append(f"[heartbeat error: {exc}]")

        finally:
            self.running = False
            self.last_run_at = time.time()
            self.lane_lock.release()

    def _execute(self) -> None:
        """
        执行一次心跳运行

        根据 command_queue 或 lane_lock 选择执行方式。
        """
        if self.command_queue is not None:
            self._execute_with_queue()
        elif self.lane_lock is not None:
            self._execute_with_lock()

    def _run_single_turn(self, prompt: str, system_prompt: str) -> str:
        """
        执行单轮 LLM 调用

        Args:
            prompt: 用户提示
            system_prompt: 系统提示词

        Returns:
            LLM 响应文本
        """
        import litellm

        try:
            kwargs: Dict[str, Any] = {
                "model": settings.model_id,
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "api_key": settings.api_key,
                "stream": False,
            }

            if settings.api_base_url:
                kwargs["api_base"] = settings.api_base_url

            response = litellm.completion(**kwargs)

            # 提取文本
            choice = response.choices[0]
            return choice.message.content or ""

        except Exception as exc:
            return f"[LLM error: {exc}]"

    def _loop(self) -> None:
        """后台循环"""
        while not self._stopped:
            try:
                ok, _ = self.should_run()
                if ok:
                    self._execute()
            except Exception:
                pass
            time.sleep(1.0)

    def start(self) -> None:
        """启动心跳运行器"""
        if self._thread is not None:
            return

        self._stopped = False
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="heartbeat",
        )
        self._thread.start()

    def stop(self) -> None:
        """停止心跳运行器"""
        self._stopped = True
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def drain_output(self) -> list[str]:
        """
        获取并清空输出队列

        Returns:
            输出消息列表
        """
        with self._queue_lock:
            items = list(self._output_queue)
            self._output_queue.clear()
            return items

    def heartbeat_tick(self) -> None:
        """
        手动触发一次心跳 tick (s10+)

        与 trigger() 不同，这个方法遵循所有前置检查。
        """
        ok, reason = self.should_run()
        if not ok:
            return

        if self.command_queue is not None:
            self._execute_with_queue()
        elif self.lane_lock is not None:
            self._execute_with_lock()

    def trigger(self) -> str:
        """
        手动触发心跳

        绕过间隔检查，立即执行一次心跳。

        Returns:
            触发结果说明
        """
        # 使用 CommandQueue 模式
        if self.command_queue is not None:
            from coder.components.concurrency import LANE_HEARTBEAT

            lane_stats = self.command_queue.get_or_create_lane(LANE_HEARTBEAT).stats()
            if lane_stats["active"] > 0:
                return "heartbeat lane occupied, cannot trigger"

            instructions, sys_prompt = self._build_heartbeat_prompt()
            if not instructions:
                return "HEARTBEAT.md is empty"

            def _do_trigger() -> Optional[str]:
                response = self._run_single_turn(instructions, sys_prompt)
                return self._parse_response(response)

            future = self.command_queue.enqueue(LANE_HEARTBEAT, _do_trigger)

            try:
                meaningful = future.result(timeout=60)
                if meaningful is None:
                    return "HEARTBEAT_OK (nothing to report)"

                if meaningful.strip() == self._last_output:
                    return "duplicate content (skipped)"

                self._last_output = meaningful.strip()
                self.last_run_at = time.time()

                with self._queue_lock:
                    self._output_queue.append(meaningful)

                return f"triggered, output queued ({len(meaningful)} chars)"

            except concurrent.futures.TimeoutError:
                return "trigger timed out"
            except Exception as exc:
                return f"trigger failed: {exc}"

        # 使用 Lock 模式 (向后兼容)
        if self.lane_lock is None:
            return "no lane_lock or command_queue configured"

        acquired = self.lane_lock.acquire(blocking=False)
        if not acquired:
            return "main lane occupied, cannot trigger"

        self.running = True
        try:
            instructions, sys_prompt = self._build_heartbeat_prompt()
            if not instructions:
                return "HEARTBEAT.md is empty"

            response = self._run_single_turn(instructions, sys_prompt)
            meaningful = self._parse_response(response)

            if meaningful is None:
                return "HEARTBEAT_OK (nothing to report)"

            if meaningful.strip() == self._last_output:
                return "duplicate content (skipped)"

            self._last_output = meaningful.strip()

            with self._queue_lock:
                self._output_queue.append(meaningful)

            return f"triggered, output queued ({len(meaningful)} chars)"

        except Exception as exc:
            return f"trigger failed: {exc}"

        finally:
            self.running = False
            self.last_run_at = time.time()
            self.lane_lock.release()

    def status(self) -> Dict[str, Any]:
        """
        获取心跳运行器状态

        Returns:
            状态字典
        """
        now = time.time()
        elapsed = now - self.last_run_at if self.last_run_at > 0 else None
        next_in = max(0.0, self.interval - elapsed) if elapsed is not None else self.interval

        ok, reason = self.should_run()

        with self._queue_lock:
            qsize = len(self._output_queue)

        return {
            "enabled": self.heartbeat_path.exists(),
            "running": self.running,
            "should_run": ok,
            "reason": reason,
            "last_run": datetime.fromtimestamp(self.last_run_at).isoformat() if self.last_run_at > 0 else "never",
            "next_in": f"{round(next_in)}s",
            "interval": f"{self.interval}s",
            "active_hours": f"{self.active_hours[0]}:00-{self.active_hours[1]}:00",
            "queue_size": qsize,
        }
