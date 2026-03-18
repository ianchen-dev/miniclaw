# s10 并发 - LaneQueue 与 CommandQueue

> 命名 lane 序列化混沌

## 概述

s10 实现了基于命名 lane 的并发控制系统，用于任务调度和执行。每个 lane 是一个独立的 FIFO 队列，带可配置的 `max_concurrency`。任务以 callable 入队，在专用线程中执行，通过 `concurrent.futures.Future` 返回结果。

## 架构

```
    Incoming Work
        |
    CommandQueue.enqueue(lane, fn)
        |
    +---v---+    +--------+    +-----------+
    | main  |    |  cron  |    | heartbeat |
    | max=1 |    | max=1  |    |   max=1   |
    | FIFO  |    | FIFO   |    |   FIFO    |
    +---+---+    +---+----+    +-----+-----+
        |            |              |
    [active]     [active]       [active]
        |            |              |
    _task_done   _task_done    _task_done
        |            |              |
    _pump()      _pump()       _pump()
    (dequeue     (dequeue      (dequeue
     next if      next if        next if
     active<max)  active<max)    active<max)
```

## 核心组件

### 1. LaneQueue - 命名 FIFO 队列

`LaneQueue` 是核心原语，提供:

- **命名 lane**: 每个 lane 有独立名称 (如 `"main"`, `"cron"`, `"heartbeat"`)
- **max_concurrency**: 限制同时运行的任务数，默认为 1 (串行执行)
- **_pump() 循环**: 任务完成后自动出队更多任务
- **Generation 追踪**: 支持重启恢复

```python
from coder.components.concurrency import LaneQueue

# 创建一个串行执行的 lane
lane = LaneQueue("main", max_concurrency=1)

# 入队任务
future = lane.enqueue(lambda: do_work())

# 阻塞等待结果
result = future.result(timeout=30)

# 获取统计信息
stats = lane.stats()
# {
#     "name": "main",
#     "queue_depth": 0,
#     "active": 0,
#     "max_concurrency": 1,
#     "generation": 0
# }
```

### 2. CommandQueue - 中央调度器

`CommandQueue` 管理多个 lane，按名称路由任务:

- **惰性创建**: Lane 在首次使用时创建
- **reset_all()**: 递增所有 generation，用于重启恢复
- **wait_for_all()**: 等待所有 lane 变为空闲

```python
from coder.components.concurrency import CommandQueue, LANE_MAIN, LANE_CRON, LANE_HEARTBEAT

# 创建调度器
cmd_queue = CommandQueue()

# 创建默认 lanes
cmd_queue.get_or_create_lane(LANE_MAIN, max_concurrency=1)
cmd_queue.get_or_create_lane(LANE_CRON, max_concurrency=1)
cmd_queue.get_or_create_lane(LANE_HEARTBEAT, max_concurrency=1)

# 入队任务到指定 lane
future = cmd_queue.enqueue(LANE_MAIN, lambda: process_user_input())

# 查看所有 lane 状态
stats = cmd_queue.stats()

# 重启恢复 (递增所有 generation)
cmd_queue.reset_all()

# 等待所有任务完成
cmd_queue.wait_for_all(timeout=10.0)
```

### 3. 标准 Lane 名称

```python
LANE_MAIN = "main"           # 用户交互
LANE_CRON = "cron"           # Cron 定时任务
LANE_HEARTBEAT = "heartbeat" # 心跳任务
```

## Generation 追踪

generation 计数器解决了一个微妙的问题: 如果系统在任务进行中重启，那些任务可能完成并尝试用过期状态泵送队列。通过递增 generation，所有旧回调变成无害的空操作:

```python
# 任务入队时记录当前 generation
future = lane.enqueue(fn)  # 使用 lane._generation

# 任务完成时检查 generation
def _task_done(self, gen):
    with self._condition:
        self._active_count -= 1
        if gen == self._generation:
            self._pump()  # 当前 generation: 正常流程
        # else: 过期任务 -- 不泵送，让其安静结束
        self._condition.notify_all()
```

## 与调度器集成

### HeartbeatRunner 集成

s10 更新了 `HeartbeatRunner`，支持 `CommandQueue` 基于 lane 的调度:

```python
from coder.components.scheduler import HeartbeatRunner
from coder.components.concurrency import CommandQueue

# 创建 CommandQueue
cmd_queue = CommandQueue()

# 创建心跳运行器 (推荐方式)
heartbeat = HeartbeatRunner(
    workspace=Path("workspace"),
    command_queue=cmd_queue,  # s10+ 推荐
)
heartbeat.start()

# 向后兼容: 使用 Lock
lane_lock = threading.Lock()
heartbeat_legacy = HeartbeatRunner(
    workspace=Path("workspace"),
    lane_lock=lane_lock,  # s07 兼容
)
```

### CronService 集成

s10 更新了 `CronService`，支持通过 `CommandQueue` 调度任务:

```python
from coder.components.scheduler import CronService
from coder.components.concurrency import CommandQueue

# 创建 CommandQueue
cmd_queue = CommandQueue()

# 创建 Cron 服务 (推荐方式)
cron_svc = CronService(
    cron_file=Path("workspace/CRON.json"),
    command_queue=cmd_queue,  # s10+ 推荐
)
```

## CLI 输出函数

s10 添加了 lane 相关的 CLI 输出函数:

```python
from coder.components.cli import print_lane, print_lanes_stats, print_queue_status

# 打印单条 lane 消息 (自动根据 lane 名称着色)
print_lane("main", "processing...")

# 打印所有 lanes 统计信息
stats = cmd_queue.stats()
print_lanes_stats(stats)
#   main          active=[.]  queued=0  max=1  gen=0
#   cron          active=[.]  queued=0  max=1  gen=0
#   heartbeat     active=[.]  queued=0  max=1  gen=0

# 打印队列状态 (仅显示有任务的 lane)
print_queue_status(stats)
```

## 配置

在 `coder/settings.py` 中添加了并发相关配置:

```python
# 并发配置 (s10)
lane_main_max_concurrency: int = 1        # main lane 最大并发数
lane_cron_max_concurrency: int = 1        # cron lane 最大并发数
lane_heartbeat_max_concurrency: int = 1   # heartbeat lane 最大并发数
```

## 完整示例

```python
import threading
import time
from pathlib import Path
from concurrent.futures import Future

from coder.components.concurrency import CommandQueue, LANE_MAIN, LANE_CRON, LANE_HEARTBEAT
from coder.components.scheduler import HeartbeatRunner, CronService
from coder.components.cli import print_lane, print_lanes_stats

def main():
    # 1. 创建 CommandQueue
    cmd_queue = CommandQueue()

    # 2. 创建默认 lanes
    cmd_queue.get_or_create_lane(LANE_MAIN, max_concurrency=1)
    cmd_queue.get_or_create_lane(LANE_CRON, max_concurrency=1)
    cmd_queue.get_or_create_lane(LANE_HEARTBEAT, max_concurrency=1)

    # 3. 创建调度器
    workspace = Path("workspace")

    heartbeat = HeartbeatRunner(
        workspace=workspace,
        command_queue=cmd_queue,
    )

    cron_svc = CronService(
        cron_file=workspace / "CRON.json",
        command_queue=cmd_queue,
    )

    # 4. 启动后台服务
    heartbeat.start()

    # 5. 启动 cron tick 循环
    cron_stop = threading.Event()
    def cron_loop():
        while not cron_stop.is_set():
            cron_svc.tick()
            cron_stop.wait(timeout=1.0)
    threading.Thread(target=cron_loop, daemon=True, name="cron-tick").start()

    # 6. 查看状态
    print_lanes_stats(cmd_queue.stats())

    # 7. 入队用户任务
    def process_user_input():
        # 处理用户输入...
        return "result"

    future = cmd_queue.enqueue(LANE_MAIN, process_user_input)
    result = future.result(timeout=30)

    # 8. 获取后台任务输出
    for msg in heartbeat.drain_output():
        print_lane(LANE_HEARTBEAT, msg)

    for msg in cron_svc.drain_output():
        print_lane(LANE_CRON, msg)

    # 9. 优雅关闭
    heartbeat.stop()
    cron_stop.set()
    cmd_queue.wait_for_all(timeout=3.0)

if __name__ == "__main__":
    main()
```

## 文件结构

```
coder/components/concurrency/
    __init__.py      # 组件导出
    queue.py         # LaneQueue, CommandQueue 实现

coder/components/scheduler/
    heartbeat.py     # HeartbeatRunner (已更新支持 CommandQueue)
    cron.py          # CronService (已更新支持 CommandQueue)

coder/components/cli/
    __init__.py      # 新增 print_lane, print_lanes_stats, print_queue_status
```

## 设计要点

1. **用户优先**: 用户输入进入 `main` lane 并阻塞等待结果。后台工作 (心跳、cron) 进入独立的 lane，永远不阻塞 REPL。

2. **自泵送设计**: `_pump()` 循环意味着不需要外部调度器。每个任务完成后，lane 自动检查并出队更多任务。

3. **基于 Condition 的同步**: `threading.Condition` 替代了原始的 `threading.Lock`。这使得 `wait_for_idle()` 能高效地睡眠等待通知，而非轮询。

4. **向后兼容**: `HeartbeatRunner` 和 `CronService` 同时支持旧的 lock 模式和新的 CommandQueue 模式。

5. **类型安全**: 所有组件都有完整的类型注解，支持静态类型检查。
