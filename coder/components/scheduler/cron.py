"""
Cron 服务 - 定时任务调度

支持三种调度类型:
- at: 一次性任务，指定时间执行
- every: 固定间隔任务
- cron: Cron 表达式任务

特性:
- 连续错误自动禁用
- 任务运行日志
- 输出队列

用法:
    from coder.components.scheduler import CronService

    cron_svc = CronService(Path("workspace/CRON.json"))

    # 列出任务
    jobs = cron_svc.list_jobs()

    # 手动触发任务
    result = cron_svc.trigger_job("daily-check")

    # 获取输出
    outputs = cron_svc.drain_output()
"""

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from croniter import croniter

from coder.settings import settings


@dataclass
class CronJob:
    """
    Cron 任务定义

    Attributes:
        id: 任务唯一标识
        name: 任务名称
        enabled: 是否启用
        schedule_kind: 调度类型 ("at" | "every" | "cron")
        schedule_config: 调度配置
        payload: 任务负载
        delete_after_run: 执行后是否删除 (仅对 "at" 类型有效)
        consecutive_errors: 连续错误次数
        last_run_at: 上次运行时间戳
        next_run_at: 下次运行时间戳
    """

    id: str
    name: str
    enabled: bool
    schedule_kind: str  # "at" | "every" | "cron"
    schedule_config: Dict[str, Any]
    payload: Dict[str, Any]
    delete_after_run: bool = False
    consecutive_errors: int = 0
    last_run_at: float = 0.0
    next_run_at: float = 0.0


class CronService:
    """
    Cron 任务服务

    从 CRON.json 加载任务定义，每秒检查一次是否有任务到期。
    支持三种调度类型，连续错误超过阈值后自动禁用任务。
    """

    def __init__(self, cron_file: Path, workspace: Optional[Path] = None) -> None:
        """
        初始化 Cron 服务

        Args:
            cron_file: CRON.json 文件路径
            workspace: 工作区目录，用于运行日志存储
        """
        self.cron_file = cron_file
        self.jobs: List[CronJob] = []

        # 工作区
        self._workspace = workspace or cron_file.parent

        # 输出队列
        self._output_queue: List[str] = []
        self._queue_lock = threading.Lock()

        # 运行日志
        self._log_dir = self._workspace / "cron"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = self._log_dir / "cron-runs.jsonl"

        # 加载任务
        self.load_jobs()

    def load_jobs(self) -> None:
        """从 CRON.json 加载任务定义"""
        self.jobs.clear()

        if not self.cron_file.exists():
            return

        try:
            raw = json.loads(self.cron_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._queue_output(f"CRON.json load error: {exc}")
            return

        now = time.time()

        for jd in raw.get("jobs", []):
            sched = jd.get("schedule", {})
            kind = sched.get("kind", "")

            # 验证调度类型
            if kind not in ("at", "every", "cron"):
                continue

            job = CronJob(
                id=jd.get("id", ""),
                name=jd.get("name", ""),
                enabled=jd.get("enabled", True),
                schedule_kind=kind,
                schedule_config=sched,
                payload=jd.get("payload", {}),
                delete_after_run=jd.get("delete_after_run", False),
            )

            # 计算下次运行时间
            job.next_run_at = self._compute_next(job, now)
            self.jobs.append(job)

    def _compute_next(self, job: CronJob, now: float) -> float:
        """
        计算下次运行时间戳

        Args:
            job: Cron 任务
            now: 当前时间戳

        Returns:
            下次运行时间戳，如果没有后续调度则返回 0.0
        """
        cfg = job.schedule_config

        if job.schedule_kind == "at":
            # 一次性任务
            try:
                ts = datetime.fromisoformat(cfg.get("at", "")).timestamp()
                return ts if ts > now else 0.0
            except (ValueError, OSError):
                return 0.0

        elif job.schedule_kind == "every":
            # 固定间隔任务
            every = cfg.get("every_seconds", 3600)

            try:
                anchor = datetime.fromisoformat(cfg.get("anchor", "")).timestamp()
            except (ValueError, OSError, TypeError):
                anchor = now

            if now < anchor:
                return anchor

            # 对齐到锚点，保证触发时间可预测
            steps = int((now - anchor) / every) + 1
            return anchor + steps * every

        elif job.schedule_kind == "cron":
            # Cron 表达式任务
            expr = cfg.get("expr", "")
            if not expr:
                return 0.0

            try:
                return croniter(expr, datetime.fromtimestamp(now)).get_next(datetime).timestamp()
            except (ValueError, KeyError):
                return 0.0

        return 0.0

    def tick(self) -> None:
        """
        每秒调用一次，检查并执行到期的任务

        应该在后台线程中循环调用。
        """
        now = time.time()
        remove_ids: List[str] = []

        for job in self.jobs:
            # 跳过禁用或未到期的任务
            if not job.enabled or job.next_run_at <= 0 or now < job.next_run_at:
                continue

            # 执行任务
            self._run_job(job, now)

            # 标记一次性任务删除
            if job.delete_after_run and job.schedule_kind == "at":
                remove_ids.append(job.id)

        # 删除标记的任务
        if remove_ids:
            self.jobs = [j for j in self.jobs if j.id not in remove_ids]

    def _run_job(self, job: CronJob, now: float) -> None:
        """
        执行单个 Cron 任务

        Args:
            job: Cron 任务
            now: 当前时间戳
        """
        payload = job.payload
        kind = payload.get("kind", "")

        output = ""
        status = "ok"
        error = ""

        try:
            if kind == "agent_turn":
                # Agent 单轮任务
                msg = payload.get("message", "")
                if not msg:
                    output, status = "[empty message]", "skipped"
                else:
                    sys_prompt = (
                        "You are performing a scheduled background task. Be concise. "
                        f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    output = self._run_single_turn(msg, sys_prompt)

            elif kind == "system_event":
                # 系统事件
                output = payload.get("text", "")
                if not output:
                    status = "skipped"

            else:
                output, status, error = f"[unknown kind: {kind}]", "error", f"unknown kind: {kind}"

        except Exception as exc:
            status, error, output = "error", str(exc), f"[cron error: {exc}]"

        # 更新任务状态
        job.last_run_at = now

        if status == "error":
            job.consecutive_errors += 1

            # 检查是否需要自动禁用
            if job.consecutive_errors >= settings.cron_auto_disable_threshold:
                job.enabled = False
                msg = f"Job '{job.name}' auto-disabled after {job.consecutive_errors} consecutive errors: {error}"
                self._queue_output(msg)
        else:
            job.consecutive_errors = 0

        # 计算下次运行时间
        job.next_run_at = self._compute_next(job, now)

        # 记录运行日志
        entry = {
            "job_id": job.id,
            "run_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "status": status,
            "output_preview": output[:200],
        }
        if error:
            entry["error"] = error

        try:
            with open(self._run_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

        # 将输出发送到队列
        if output and status != "skipped":
            self._queue_output(f"[{job.name}] {output}")

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

            choice = response.choices[0]
            return choice.message.content or ""

        except Exception as exc:
            return f"[LLM error: {exc}]"

    def _queue_output(self, text: str) -> None:
        """将输出发送到队列"""
        with self._queue_lock:
            self._output_queue.append(text)

    def trigger_job(self, job_id: str) -> str:
        """
        手动触发指定任务

        Args:
            job_id: 任务 ID

        Returns:
            触发结果说明
        """
        for job in self.jobs:
            if job.id == job_id:
                self._run_job(job, time.time())
                return f"'{job.name}' triggered (errors={job.consecutive_errors})"

        return f"Job '{job_id}' not found"

    def drain_output(self) -> List[str]:
        """
        获取并清空输出队列

        Returns:
            输出消息列表
        """
        with self._queue_lock:
            items = list(self._output_queue)
            self._output_queue.clear()
            return items

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        列出所有任务及其状态

        Returns:
            任务状态列表
        """
        now = time.time()
        result = []

        for job in self.jobs:
            nxt = max(0.0, job.next_run_at - now) if job.next_run_at > 0 else None

            result.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "enabled": job.enabled,
                    "kind": job.schedule_kind,
                    "errors": job.consecutive_errors,
                    "last_run": datetime.fromtimestamp(job.last_run_at).isoformat() if job.last_run_at > 0 else "never",
                    "next_run": datetime.fromtimestamp(job.next_run_at).isoformat() if job.next_run_at > 0 else "n/a",
                    "next_in": round(nxt) if nxt is not None else None,
                }
            )

        return result
