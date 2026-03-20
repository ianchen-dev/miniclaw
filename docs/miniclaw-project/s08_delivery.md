# 第 08 节: 消息投递

> 先写磁盘, 再尝试发送. 崩溃安全.

## 架构

```
    Agent Reply / Heartbeat / Cron
              |
        chunk_message()          split by platform limits
              |                  (telegram=4096, discord=2000, etc.)
              v
        DeliveryQueue.enqueue()
          1. Generate unique ID
          2. Write to .tmp.{pid}.{id}.json
          3. fsync()
          4. os.replace() to {id}.json    <-- WRITE-AHEAD
              |
              v
        DeliveryRunner (background thread, 1s scan)
              |
         deliver_fn(channel, to, text)
            /          \
        success      failure
          |              |
        ack()         fail()
        (delete       (retry_count++, compute backoff,
         .json)        update .json on disk)
                         |
                    retry_count >= 5?
                      |yes
                    move to failed/

    Backoff: [5s, 25s, 2min, 10min] with +/-20% jitter
```

## 模块结构

```
coder/components/delivery/
├── __init__.py          # 组件导出
├── queue.py             # DeliveryQueue + QueuedDelivery + chunk_message
└── runner.py            # DeliveryRunner 后台投递线程
```

## 核心组件

### 1. DeliveryQueue

磁盘持久化的可靠投递队列，使用预写日志模式。

```python
from coder.components.delivery import DeliveryQueue, chunk_message

# 初始化队列
queue = DeliveryQueue()

# 入队消息 (自动原子写入磁盘)
delivery_id = queue.enqueue("telegram", "user123", "Hello!")

# 按平台限制分片
long_text = "..." * 5000
chunks = chunk_message(long_text, "telegram")  # telegram 限制 4096 字符
for chunk in chunks:
    queue.enqueue("telegram", "user123", chunk)

# 加载待处理条目
pending = queue.load_pending()
for entry in pending:
    print(f"{entry.id}: {entry.channel} -> {entry.to}")

# 确认投递成功
queue.ack(delivery_id)

# 标记投递失败 (自动计算退避时间)
queue.fail(delivery_id, "Network timeout")

# 重试所有失败的条目
count = queue.retry_failed()
```

### 2. DeliveryRunner

后台投递线程，每秒扫描待处理条目。

```python
from coder.components.delivery import DeliveryQueue, DeliveryRunner

queue = DeliveryQueue()

# 定义投递函数
def deliver_fn(channel: str, to: str, text: str) -> None:
    # 实际投递逻辑
    if channel == "telegram":
        # telegram_api.send(to, text)
        pass
    elif channel == "discord":
        # discord_api.send(to, text)
        pass
    print(f"[{channel}] -> {to}: {text[:50]}...")

# 创建运行器
runner = DeliveryRunner(queue, deliver_fn, verbose=True)

# 启动后台线程 (自动执行恢复扫描)
runner.start()

# 获取统计
stats = runner.get_stats()
# {
#     "pending": 3,
#     "failed": 1,
#     "total_attempted": 10,
#     "total_succeeded": 9,
#     "total_failed": 1,
# }

# 停止运行器
runner.stop()
```

### 3. chunk_message

按平台限制分片消息，尊重段落边界。

```python
from coder.components.delivery import chunk_message, CHANNEL_LIMITS

# 平台限制
print(CHANNEL_LIMITS)
# {
#     "telegram": 4096,
#     "telegram_caption": 1024,
#     "discord": 2000,
#     "whatsapp": 4096,
#     "feishu": 4096,
#     "cli": 10000,
#     "default": 4096,
# }

# 分片长消息
long_text = "第一段...\n\n第二段...\n\n第三段..." * 100
chunks = chunk_message(long_text, "telegram")

for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}: {len(chunk)} chars")
```

## 原子写入机制

三步保证崩溃安全:

```python
def _write_entry(self, entry: QueuedDelivery) -> None:
    final_path = self.queue_dir / f"{entry.id}.json"
    tmp_path = self.queue_dir / f".tmp.{os.getpid()}.{entry.id}.json"

    data = json.dumps(entry.to_dict(), indent=2, ensure_ascii=False)

    # 第 1 步: 写入临时文件
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        # 第 2 步: fsync -- 数据已落盘
        os.fsync(f.fileno())

    # 第 3 步: 原子替换
    os.replace(str(tmp_path), str(final_path))  # POSIX 原子操作
```

崩溃场景:
- 写入 `.tmp.*.json` 时崩溃 → 孤立的临时文件，无害
- `fsync()` 后崩溃 → 临时文件完整，无害
- `os.replace()` 时崩溃 → 要么旧文件，要么新文件，绝不会是半写文件

## 指数退避策略

```python
from coder.components.delivery import compute_backoff_ms, BACKOFF_MS, MAX_RETRIES

# 退避时间表
print(BACKOFF_MS)  # [5000, 25000, 120000, 600000]  (毫秒)
# 即 [5s, 25s, 2min, 10min]

print(MAX_RETRIES)  # 5

# 计算退避时间 (带 +/- 20% 抖动)
for retry in range(1, 6):
    backoff = compute_backoff_ms(retry)
    print(f"Retry {retry}: {backoff/1000:.1f}s")
# Retry 1: 5.2s (5s +/- 20%)
# Retry 2: 24.8s (25s +/- 20%)
# Retry 3: 118.5s (2min +/- 20%)
# Retry 4: 605.3s (10min +/- 20%)
# Retry 5: 598.7s (10min +/- 20%)
```

## 投递生命周期

```
1. enqueue() → 写入磁盘，next_retry_at=0
              ↓
2. DeliveryRunner 扫描 → next_retry_at <= now?
              ↓yes
3. 调用 deliver_fn(channel, to, text)
              ↓
   ┌──────────┴──────────┐
   ↓                     ↓
成功                    失败
   ↓                     ↓
ack()                  fail()
   ↓                     ↓
删除文件         retry_count++
                     ↓
               retry_count >= 5?
                ↓yes    ↓no
           move_to_failed  计算退避时间
                           ↓
                     更新 next_retry_at
                           ↓
                     写入磁盘，等待重试
```

## 与 AgentLoop 集成

```python
from coder.components.agent import AgentLoop
from coder.components.delivery import DeliveryQueue, DeliveryRunner
from coder.components.tools import TOOLS

# 创建投递队列
queue = DeliveryQueue()

# 定义投递函数
def deliver_fn(channel: str, to: str, text: str) -> None:
    # 实际投递到各平台
    print(f"[{channel}] -> {text}")

# 创建运行器
runner = DeliveryRunner(queue, deliver_fn)
runner.start()

# 创建 Agent 循环
loop = AgentLoop(tools=TOOLS)

# 在处理响应后入队
# response_text = "..."
# chunks = chunk_message(response_text, "telegram")
# for chunk in chunks:
#     queue.enqueue("telegram", "user123", chunk)
```

## REPL 命令

可添加以下 REPL 命令来管理投递队列:

| 命令 | 说明 |
|------|------|
| `/queue` | 显示待投递条目 |
| `/failed` | 显示失败条目 |
| `/retry` | 重试所有失败条目 |
| `/delivery-stats` | 显示投递统计 |

## 配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| `delivery_queue_dir` | `DELIVERY_QUEUE_DIR` | `workspace/.delivery-queue` | 投递队列目录 |
| `delivery_max_retries` | `DELIVERY_MAX_RETRIES` | `5` | 最大重试次数 |
| `delivery_verbose` | `DELIVERY_VERBOSE` | `True` | 是否打印详细信息 |

## 文件说明

| 文件/目录 | 说明 |
|-----------|------|
| `workspace/.delivery-queue/` | 队列存储目录 |
| `workspace/.delivery-queue/*.json` | 待投递条目 |
| `workspace/.delivery-queue/failed/*.json` | 失败条目 |
| `workspace/.delivery-queue/.tmp.*.json` | 临时文件 (崩溃后可安全删除) |

## 运行示例

```python
from coder.components.delivery import DeliveryQueue, DeliveryRunner, chunk_message

# 初始化
queue = DeliveryQueue()

def deliver_fn(channel: str, to: str, text: str) -> None:
    # 模拟投递
    import random
    if random.random() < 0.3:  # 30% 失败率
        raise ConnectionError("Network error")
    print(f"[{channel}] -> {to}: {text[:30]}...")

runner = DeliveryRunner(queue, deliver_fn, verbose=True)
runner.start()

# 入队消息
long_text = "这是一条很长的消息..." * 100
chunks = chunk_message(long_text, "telegram")
for chunk in chunks:
    queue.enqueue("telegram", "user123", chunk)

# 等待投递
import time
time.sleep(5)

# 查看统计
stats = runner.get_stats()
print(f"Stats: {stats}")

# 停止
runner.stop()
```

## 设计原则

1. **崩溃安全**: 先写磁盘，再尝试投递，进程崩溃不会丢失消息
2. **原子写入**: tmp + fsync + os.replace 确保文件完整性
3. **指数退避**: 避免对故障服务造成压力，抖动防止惊群效应
4. **平台感知**: chunk_message 尊重各平台消息长度限制
5. **可观测性**: 丰富的统计接口和详细日志
