# 第 07 节: 心跳与 Cron

> 一个定时器线程检查"该不该运行", 然后将任务排入与用户消息相同的队列.

## 架构

```
    Main Lane (user input):
        User Input --> lane_lock.acquire() -------> LLM --> Print
                       (blocking: always wins)

    Heartbeat Lane (background thread, 1s poll):
        should_run()?
            |no --> sleep 1s
            |yes
        _execute():
            lane_lock.acquire(blocking=False)
                |fail --> yield (user has priority)
                |success
            build prompt from HEARTBEAT.md + SOUL.md + MEMORY.md
                |
            run_agent_single_turn()
                |
            parse: "HEARTBEAT_OK"? --> suppress
                   meaningful text? --> duplicate? --> suppress
                                           |no
                                       output_queue.append()

    Cron Service (background thread, 1s tick):
        CRON.json --> load jobs --> tick() every 1s
            |
        for each job: enabled? --> due? --> _run_job()
            |
        error? --> consecutive_errors++ --> >=5? --> auto-disable
            |ok
        consecutive_errors = 0 --> log to cron-runs.jsonl
```

## 模块结构

```
coder/components/scheduler/
├── __init__.py          # 组件导出
├── heartbeat.py         # HeartbeatRunner 心跳运行器
└── cron.py              # CronService + CronJob 定时任务服务
```

## 核心组件

### 1. HeartbeatRunner

心跳运行器定期检查是否应该运行，通过 Lane 互斥机制确保用户优先。

```python
from coder.components.scheduler import HeartbeatRunner
import threading
from pathlib import Path

# 创建 Lane 互斥锁
lane_lock = threading.Lock()

# 初始化心跳运行器
heartbeat = HeartbeatRunner(
    workspace=Path("workspace"),
    lane_lock=lane_lock,
    interval=1800.0,           # 30 分钟间隔
    active_hours=(9, 22),      # 9:00 - 22:00 活跃
    max_queue_size=10,         # 输出队列最大 10 条
)

# 启动后台线程
heartbeat.start()

# 检查状态
status = heartbeat.status()
# {
#     "enabled": True,
#     "running": False,
#     "should_run": True,
#     "reason": "all checks passed",
#     "last_run": "2024-01-15T10:30:00",
#     "next_in": "1500s",
#     "interval": "1800s",
#     "active_hours": "9:00-22:00",
#     "queue_size": 0,
# }

# 手动触发
result = heartbeat.trigger()
# "triggered, output queued (245 chars)"

# 获取输出
outputs = heartbeat.drain_output()
for msg in outputs:
    print(msg)

# 停止
heartbeat.stop()
```

### 2. CronService

Cron 任务服务支持三种调度类型: `at` (一次性)、`every` (固定间隔)、`cron` (Cron 表达式)。

```python
from coder.components.scheduler import CronService
from pathlib import Path

# 初始化 Cron 服务
cron_svc = CronService(
    cron_file=Path("workspace/CRON.json"),
    workspace=Path("workspace"),
)

# 列出所有任务
jobs = cron_svc.list_jobs()
for job in jobs:
    print(f"{job['id']}: {job['name']} - next in {job['next_in']}s")

# 手动触发任务
result = cron_svc.trigger_job("daily-check")

# 获取输出
outputs = cron_svc.drain_output()

# 后台循环 (每秒调用)
# cron_svc.tick()
```

### 3. CronJob 配置

在 `workspace/CRON.json` 中定义任务:

```json
{
  "jobs": [
    {
      "id": "daily-check",
      "name": "Daily Check",
      "enabled": true,
      "schedule": {
        "kind": "cron",
        "expr": "0 9 * * *"
      },
      "payload": {
        "kind": "agent_turn",
        "message": "Generate a daily summary of recent activities."
      }
    },
    {
      "id": "hourly-reminder",
      "name": "Hourly Reminder",
      "enabled": true,
      "schedule": {
        "kind": "every",
        "every_seconds": 3600,
        "anchor": "2024-01-01T00:00:00"
      },
      "payload": {
        "kind": "agent_turn",
        "message": "Check if there are any pending tasks."
      }
    },
    {
      "id": "one-time-task",
      "name": "One-time Task",
      "enabled": true,
      "delete_after_run": true,
      "schedule": {
        "kind": "at",
        "at": "2024-01-15T14:30:00"
      },
      "payload": {
        "kind": "system_event",
        "text": "[System] Scheduled maintenance starting in 30 minutes."
      }
    }
  ]
}
```

### 4. 心跳配置

在 `workspace/HEARTBEAT.md` 中定义心跳指令:

```markdown
# Heartbeat Instructions

Check if there are any unread reminders or pending tasks.
Reply with "HEARTBEAT_OK" if nothing to report.
Otherwise, provide a brief summary of what needs attention.
```

## Lane 互斥机制

最重要的设计原则: 用户消息始终优先于后台任务。

```python
import threading

lane_lock = threading.Lock()

# Main lane: 阻塞获取. 用户始终能进入。
lane_lock.acquire()
try:
    # 处理用户消息, 调用 LLM
    pass
finally:
    lane_lock.release()

# Heartbeat lane: 非阻塞获取. 用户活跃时让步。
acquired = lane_lock.acquire(blocking=False)
if not acquired:
    # 用户持有锁, 跳过本次心跳
    return
try:
    # 执行心跳任务
    pass
finally:
    lane_lock.release()
```

## should_run() 前置条件链

四个检查必须全部通过:

```python
def should_run(self) -> tuple[bool, str]:
    # 1. 检查 HEARTBEAT.md 文件存在
    if not self.heartbeat_path.exists():
        return False, "HEARTBEAT.md not found"

    # 2. 检查内容非空
    if not self.heartbeat_path.read_text(encoding="utf-8").strip():
        return False, "HEARTBEAT.md is empty"

    # 3. 检查间隔时间
    elapsed = time.time() - self.last_run_at
    if elapsed < self.interval:
        return False, f"interval not elapsed ({self.interval - elapsed:.0f}s remaining)"

    # 4. 检查活跃时间
    hour = datetime.now().hour
    s, e = self.active_hours
    in_hours = (s <= hour < e) if s <= e else not (e <= hour < s)
    if not in_hours:
        return False, f"outside active hours ({s}:00-{e}:00)"

    # 5. 检查是否已在运行
    if self.running:
        return False, "already running"

    return True, "all checks passed"
```

## HEARTBEAT_OK 协议

Agent 用 `HEARTBEAT_OK` 表示"没有需要报告的内容":

```python
def _parse_response(self, response: str) -> str | None:
    if "HEARTBEAT_OK" in response:
        stripped = response.replace("HEARTBEAT_OK", "").strip()
        return stripped if len(stripped) > 5 else None
    return response.strip() or None
```

## Cron 自动禁用

连续错误超过阈值后自动禁用任务:

```python
if status == "error":
    job.consecutive_errors += 1
    if job.consecutive_errors >= CRON_AUTO_DISABLE_THRESHOLD:
        job.enabled = False
        # 通知用户
else:
    job.consecutive_errors = 0
```

## 与 AgentLoop 集成

```python
from coder.components.agent import AgentLoop, run_agent_loop
from coder.components.tools import TOOLS

# 方式1: 快速启动
run_agent_loop(
    tools=TOOLS,
    enable_scheduler=True,
)

# 方式2: 自定义配置
loop = AgentLoop(
    tools=TOOLS,
    enable_scheduler=True,
    workspace=Path("workspace"),
)
loop.run()
```

## REPL 命令

启用调度器后，可使用以下 REPL 命令:

| 命令 | 说明 |
|------|------|
| `/heartbeat` | 显示心跳状态 |
| `/trigger` | 手动触发心跳 |
| `/cron` | 列出所有 Cron 任务 |
| `/cron-trigger <id>` | 手动触发指定 Cron 任务 |
| `/lanes` | 显示 Lane 锁状态 |

## 配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| `heartbeat_interval` | `HEARTBEAT_INTERVAL` | `1800.0` | 心跳间隔 (秒) |
| `heartbeat_active_start` | `HEARTBEAT_ACTIVE_START` | `9` | 活跃开始时间 (小时) |
| `heartbeat_active_end` | `HEARTBEAT_ACTIVE_END` | `22` | 活跃结束时间 (小时) |
| `heartbeat_max_queue_size` | `HEARTBEAT_MAX_QUEUE_SIZE` | `10` | 输出队列最大大小 |
| `cron_auto_disable_threshold` | `CRON_AUTO_DISABLE_THRESHOLD` | `5` | 连续错误自动禁用阈值 |

## 运行示例

```bash
# 创建 workspace/HEARTBEAT.md
echo "Check for pending tasks. Reply HEARTBEAT_OK if nothing to report." > workspace/HEARTBEAT.md

# 创建 workspace/CRON.json
cat > workspace/CRON.json << 'EOF'
{
  "jobs": [
    {
      "id": "test-job",
      "name": "Test Job",
      "enabled": true,
      "schedule": {"kind": "every", "every_seconds": 60},
      "payload": {"kind": "agent_turn", "message": "Say hello."}
    }
  ]
}
EOF

# 运行 Agent
python -c "
from coder.components.agent import run_agent_loop
from coder.components.tools import TOOLS
run_agent_loop(tools=TOOLS, enable_scheduler=True)
"

# 在 REPL 中:
# You > /heartbeat        # 检查心跳状态
# You > /trigger          # 手动触发心跳
# You > /cron             # 列出 cron 任务
# You > /cron-trigger test-job  # 手动触发任务
# You > /lanes            # 检查 lane 锁状态
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `workspace/HEARTBEAT.md` | 心跳指令文件 |
| `workspace/CRON.json` | Cron 任务定义 |
| `workspace/cron/cron-runs.jsonl` | Cron 运行日志 |

## 设计原则

1. **用户优先**: Lane 互斥确保用户消息始终优先于后台任务
2. **优雅降级**: 心跳任务在用户活跃时自动让步，不阻塞交互
3. **自动保护**: 连续错误的 Cron 任务自动禁用，避免无限重试
4. **输出队列**: 后台任务结果通过队列异步传递，不干扰主循环
5. **可观测性**: 丰富的 REPL 命令和状态查询接口
